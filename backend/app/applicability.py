"""Conservative rules for four reviewed API recipes; never infer facts from snippets."""

import ast
import hashlib
import re
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version

from .evidence import allowed, cite, document
from .models import Card, Label, Profile, SearchHit
from .profiler import version_for

PYDANTIC_MIGRATION = 'https://github.com/pydantic/pydantic/blob/ca359e009fcfaff2a80df33cb99ee6ab21aaf033/docs/migration.md'
SQLA_MIGRATION = 'https://github.com/sqlalchemy/sqlalchemy/blob/e75a4651657f1d12dd747cc8e6f93d2815ea8936/doc/build/changelog/migration_20.rst'
FACTS = {
    'pydantic_old': ('Where possible, we have retained the deprecated methods with their old names\nto help ease migration, but calling them will emit `DeprecationWarning`s.', PYDANTIC_MIGRATION),
    'pydantic_new': ('| `parse_obj()` | `model_validate()` |', PYDANTIC_MIGRATION),
    'sqlalchemy_old': ('The Engine.execute() function/method is considered legacy as of the 1.x series of SQLAlchemy and will be removed in 2.0.', SQLA_MIGRATION),
    'sqlalchemy_new': ('All statement execution in SQLAlchemy 2.0 is performed by the Connection.execute() method of Connection', SQLA_MIGRATION),
}
SNAPSHOT_HASHES = {
    'pydantic_old': '9bf17e8ea8a85b05dbbaccc710f35f30eac8c43dbdc889a3e715b65aa19599ac',
    'pydantic_new': '9bf17e8ea8a85b05dbbaccc710f35f30eac8c43dbdc889a3e715b65aa19599ac',
    'sqlalchemy_old': '1b939c47f6d6ccc6ae822e5f2658a024d0769f4759f64bceb534a45a69ee372f',
    'sqlalchemy_new': '1b939c47f6d6ccc6ae822e5f2658a024d0769f4759f64bceb534a45a69ee372f',
}
RULESET_VERSION = '2026-10-10-scoped-v2'
RECIPES = {'pydantic_old': 'parse_obj()', 'pydantic_new': 'model_validate()',
           'sqlalchemy_old': 'Engine.execute()', 'sqlalchemy_new': 'Connection.execute()'}


@dataclass
class Recipe:
    rule: str
    block: dict
    namespace: str | None = None
    requirements: tuple[str, ...] = ()
    satisfied: bool = False
    engine_future: bool | None = None
    uses_connection_commit: bool = False


def _version(profile: Profile, library: str) -> Version | None:
    raw = version_for(profile, library)
    try:
        return Version(raw) if raw else None
    except InvalidVersion:
        return None


def _parse(code: str) -> ast.Module | None:
    lines = []
    for line in code.splitlines():
        # Python documentation often contains interactive prompts.
        lines.append(re.sub(r'^(\s*)(?:>>> |\.\.\. )', r'\1', line))
    try:
        return ast.parse('\n'.join(lines))
    except (SyntaxError, ValueError):
        return None


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f'{parent}.{node.attr}' if parent else None
    return None


def _local_receiver_shadow(call: ast.Call, receiver: str | None,
                           parents: dict[ast.AST, ast.AST]) -> bool:
    """Abstain for lexical bindings; this is not a general Python name resolver."""
    if not receiver:
        return False
    root_name = receiver.split('.')[0]
    ancestor = parents.get(call)
    while ancestor is not None:
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = ancestor.args
            parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            parameters.extend(arg for arg in (args.vararg, args.kwarg) if arg is not None)
            if any(arg.arg == root_name for arg in parameters):
                return True
            # A local assignment binds the name throughout the function, even
            # when the assignment follows the call. Nested bindings are also
            # conservatively excluded rather than claiming global resolution.
            if any(isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
                   and node.id == root_name for node in ast.walk(ancestor)):
                return True
        ancestor = parents.get(ancestor)
    return False


def _recipes(doc: dict, library: str) -> list[Recipe]:
    recipes: list[Recipe] = []
    section = None
    imports: dict[str, str] = {}
    models: dict[str, str] = {}
    overrides: dict[str, set[str]] = {}
    engines: dict[str, bool | None] = {}
    for block in doc['blocks']:
        if not isinstance(block, dict) or not isinstance(block.get('code'), str):
            continue
        key = (block.get('scope_id'), block.get('heading'), block.get('section_id'))
        if key != section:
            imports, models, overrides, engines = {}, {}, {}, {}
            section = key
        tree = _parse(block['code'])
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f'{node.module}.{alias.name}'
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split('.')[0]] = alias.name
        # Resolve only direct, explicitly imported BaseModel inheritance.
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                models.pop(node.name, None)
                overrides.pop(node.name, None)
                namespaces = set()
                for base in node.bases:
                    name = _name(base)
                    qualified = imports.get(name, name)
                    if qualified in {'pydantic.BaseModel', 'pydantic.v1.BaseModel'}:
                        namespaces.add('v1_shim' if '.v1.' in qualified else 'native')
                if len(namespaces) == 1 and len(node.bases) == 1 and not node.keywords:
                    models[node.name] = namespaces.pop()
                    overrides[node.name] = {item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call_name = _name(node.value.func)
                qualified = imports.get(call_name, call_name)
                if qualified == 'sqlalchemy.create_engine':
                    future = next((keyword.value.value for keyword in node.value.keywords
                                   if keyword.arg == 'future' and isinstance(keyword.value, ast.Constant)
                                   and isinstance(keyword.value.value, bool)), None)
                    engines.update({target.id: future for target in node.targets if isinstance(target, ast.Name)})
                else:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            models.pop(target.id, None)
                            imports.pop(target.id, None)
                            engines.pop(target.id, None)
                        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                            overrides.setdefault(target.value.id, set()).add(target.attr)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                # A bare annotation does not change runtime binding.
                if isinstance(node, ast.AnnAssign) and node.value is None:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        models.pop(target.id, None)
                        imports.pop(target.id, None)
                        engines.pop(target.id, None)
                    elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                        overrides.setdefault(target.value.id, set()).add(target.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                models.pop(node.name, None)
                imports.pop(node.name, None)
                engines.pop(node.name, None)
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        connection_modes: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    expression = item.context_expr
                    if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                            and expression.func.attr in {'connect', 'begin'}
                            and _name(expression.func.value) in engines
                            and isinstance(item.optional_vars, ast.Name)):
                        connection_modes[item.optional_vars.id] = expression.func.attr
        seen: set[str] = set()
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            receiver = _name(call.func.value)
            if library == 'pydantic' and call.func.attr in {'parse_obj', 'model_validate'}:
                rid = 'pydantic_old' if call.func.attr == 'parse_obj' else 'pydantic_new'
                namespace = models.get(receiver)
                if receiver:
                    qualified = imports.get(receiver, receiver)
                    if qualified in {'pydantic.BaseModel', 'pydantic.v1.BaseModel'}:
                        namespace = 'v1_shim' if '.v1.' in qualified else 'native'
                requirements = ('Explicit pydantic BaseModel namespace and unmodified API',
                                'API availability only; input data, custom validators and complete program behavior are not verified')
                satisfied = (namespace is not None and call.func.attr not in overrides.get(receiver, set())
                             and not _local_receiver_shadow(call, receiver, parents))
                recipe = Recipe(rid, block, namespace, requirements, satisfied)
            elif library == 'sqlalchemy' and call.func.attr == 'execute':
                if receiver in engines:
                    recipe = Recipe('sqlalchemy_old', block, requirements=('Engine created by sqlalchemy.create_engine',),
                                    satisfied=True, engine_future=engines[receiver])
                elif receiver in connection_modes or receiver in {'conn', 'connection', 'Connection'}:
                    requirements = ['Connection created from a SQLAlchemy Engine', 'Statement explicitly wrapped in sqlalchemy.text(...)']
                    statement = call.args[0] if call.args else None
                    text_call = (isinstance(statement, ast.Call)
                                 and imports.get(_name(statement.func), _name(statement.func)) == 'sqlalchemy.text')
                    sql = statement.args[0] if text_call and statement.args else None
                    literal = sql.value if isinstance(sql, ast.Constant) and isinstance(sql.value, str) else None
                    mode = None
                    scope = None
                    source_future = None
                    ancestor = parents.get(call)
                    while ancestor is not None:
                        if isinstance(ancestor, ast.With):
                            for item in ancestor.items:
                                expression = item.context_expr
                                if (isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == receiver
                                        and isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                                        and _name(expression.func.value) in engines
                                        and expression.func.attr in {'begin', 'connect'}):
                                    mode = expression.func.attr
                                    scope = ancestor
                                    source_future = engines[_name(expression.func.value)]
                        ancestor = parents.get(ancestor)
                    # A commit counts only after this execute, directly in its open connection scope.
                    committed = bool(scope and any(
                        isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                        and isinstance(statement.value.func, ast.Attribute)
                        and statement.value.func.attr == 'commit'
                        and _name(statement.value.func.value) == receiver
                        and statement.lineno > call.lineno for statement in scope.body))
                    uses_commit = bool(scope and any(
                        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in {'commit', 'rollback'}
                        and _name(node.func.value) == receiver for node in ast.walk(scope)))
                    readonly = bool(literal and re.match(r'^\s*SELECT\b', literal, re.IGNORECASE))
                    requirements.append('Explicit transaction/commit for writes; SELECT does not promise persistence')
                    requirements.append('SQL syntax, schema, data and complete program behavior are not verified')
                    shadowed = any(
                        isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                        and any(isinstance(target, ast.Name) and target.id == receiver
                                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))
                        for node in ast.walk(tree))
                    satisfied = bool(mode and text_call and literal and not shadowed
                                     and not _local_receiver_shadow(call, receiver, parents)
                                     and (mode == 'begin' or committed or readonly))
                    recipe = Recipe('sqlalchemy_new', block, requirements=tuple(requirements), satisfied=satisfied,
                                    engine_future=source_future, uses_connection_commit=uses_commit)
                else:
                    continue
            else:
                continue
            if recipe.rule not in seen:
                recipes.append(recipe)
                seen.add(recipe.rule)
    return recipes


def _fact(rule: str, facts_text: dict[str, str]):
    text = facts_text.get(rule, '')
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != SNAPSHOT_HASHES[rule]:
        return None
    quote, url = FACTS[rule]
    return cite(url, quote, text, 'reviewed official migration snapshot', provenance='reviewed_snapshot')


def _witness(rule: str, version: Version, profile: Profile) -> str | None:
    if rule.startswith('pydantic'):
        if version == Version('2.9.2') and profile.pydantic_api_mode == 'v1_shim':
            suffix = 'parse-obj' if rule == 'pydantic_old' else 'model-validate'
            return f'pydantic-v1-shim-{suffix}-v2'
        if profile.pydantic_api_mode == 'native' and version in {Version('1.10.15'), Version('2.9.2')}:
            suffix = 'parse-obj' if rule == 'pydantic_old' else 'model-validate'
            return f'pydantic-{suffix}-v{version.major}'
    elif rule == 'sqlalchemy_old':
        if version == Version('2.0.36'):
            return 'sqlalchemy-engine-execute-20'
        if version == Version('1.4.54') and profile.sqlalchemy_future is not None:
            return f'sqlalchemy-engine-execute-14-{"future" if profile.sqlalchemy_future else "legacy"}'
    elif rule == 'sqlalchemy_new':
        if version == Version('2.0.36'):
            return 'sqlalchemy-connection-text-20'
        if version == Version('1.4.54') and profile.sqlalchemy_future is True:
            return 'sqlalchemy-connection-text-14'
        if version == Version('1.4.54') and profile.sqlalchemy_future is False:
            return 'sqlalchemy-connection-text-14-legacy'
    return None


def classify_all(hit: SearchHit, body: str | None, profile: Profile, library: str,
                 facts_text: dict[str, str]) -> list[Card]:
    base = Card(hit=hit, id=hit.id, label=Label.UNCERTAIN, explanation='No verified recipe and version evidence for this source.')
    if not body or not allowed(hit.url):
        base.explanation = 'Source page could not be verified; a search snippet is insufficient.'
        return [base]
    doc = document(body)
    if not doc:
        base.explanation = 'Unstructured source text cannot establish a scoped code recipe.'
        return [base]
    candidates = _recipes(doc, library)
    if not candidates:
        base.explanation = 'No supported code recipe with scoped source evidence was found.'
        return [base]
    version = _version(profile, library)
    cards = []
    for recipe in candidates:
        card = Card(hit=hit, id=f'{hit.id}:{recipe.rule}:{hashlib.sha256(recipe.block["code"].encode()).hexdigest()[:10]}', recipe=RECIPES[recipe.rule], rule_id=recipe.rule,
                    label=Label.UNCERTAIN, explanation=base.explanation,
                    preconditions=list(recipe.requirements))
        source = cite(doc.get('source_url') or hit.url, recipe.block['code'].strip(), body,
                      'authored illustrative recipe' if doc.get('provenance') == 'authored_fixture' else 'fetched source recipe',
                      section=recipe.block.get('heading'))
        fact = _fact(recipe.rule, facts_text)
        card.evidence = [item for item in (source, fact) if item]
        extra_quote = None
        if recipe.namespace == 'v1_shim':
            extra_quote = 'As of `pydantic>=1.10.17`, the `pydantic.v1` namespace can be used within V1.'
        elif library == 'sqlalchemy':
            extra_quote = ('When the :paramref:`_sa.create_engine.future` flag is used, the :class:`_engine.Engine`\n'
                           'and :class:`_engine.Connection` objects support the 2.0 API fully and not at all\n'
                           'any legacy features')
        if fact and extra_quote:
            extra = cite(FACTS[recipe.rule][1], extra_quote, facts_text[recipe.rule],
                         'reviewed official migration snapshot', provenance='reviewed_snapshot')
            if extra:
                card.evidence.append(extra)
        if not source or not fact:
            card.explanation = 'Required scoped recipe or immutable reviewed migration evidence is missing.'
        elif version is None:
            card.explanation = 'Dependency version is a range, missing, or conflicting; applicability is unresolved.'
        elif version.is_prerelease or version.is_devrelease or version.local or version.is_postrelease:
            card.explanation = 'Prerelease, development, local, and postrelease versions are outside the reviewed rules.'
        elif library == 'pydantic' and not ((version.major == 1 and version.minor == 10) or (version.major == 2 and version.minor <= 14)):
            card.explanation = 'This Pydantic version is outside the reviewed rule range (1.10.x or 2.0–2.14.x).'
        elif library == 'sqlalchemy' and not ((version.major == 1 and version.minor == 4) or (version.major == 2 and version.minor == 0)):
            card.explanation = 'This SQLAlchemy version is outside the reviewed rule range (1.4.x or 2.0.x).'
        elif (library == 'sqlalchemy' and version.major == 1 and recipe.engine_future is not None
              and profile.sqlalchemy_future is not None and recipe.engine_future != profile.sqlalchemy_future):
            card.explanation = 'Recipe create_engine(future=...) conflicts with the project engine context; resolve the setting first.'
        elif library == 'sqlalchemy' and version.major == 2 and recipe.engine_future is False:
            card.explanation = 'SQLAlchemy 2.0 does not accept create_engine(future=False); this recipe engine cannot be created.'
        elif (library == 'sqlalchemy' and version.major == 1 and profile.sqlalchemy_future is False
              and recipe.uses_connection_commit):
            card.explanation = 'Connection.commit()/rollback() require the SQLAlchemy 1.4 future API or 2.0; this project uses the 1.4 legacy connection API.'
        elif not recipe.satisfied:
            card.explanation = 'Recipe context is incomplete: ' + '; '.join(recipe.requirements) + '.'
        elif library == 'pydantic':
            card.boundary = 'Pydantic 2.0: native model_validate introduced; native parse_obj deprecated.'
            mode = profile.pydantic_api_mode
            if mode not in {'native', 'v1_shim'} or recipe.namespace != mode:
                card.explanation = 'Source BaseModel namespace differs from, or is not confirmed by, the project API context.'
            elif mode == 'v1_shim' and version < Version('1.10.17'):
                card.label = Label.WRONG_VERSION
                card.explanation = 'The pydantic.v1 namespace is available in V1 only from 1.10.17, and in V2.'
            elif mode == 'v1_shim':
                card.boundary = 'pydantic.v1 preserves the V1 API in Pydantic 2; available in V1 from 1.10.17.'
                card.label = Label.COMPATIBLE if recipe.rule == 'pydantic_old' else Label.WRONG_VERSION
                card.explanation = 'The explicitly imported pydantic.v1 BaseModel exposes parse_obj, not native V2 model_validate.'
            elif recipe.rule == 'pydantic_old':
                card.label = Label.COMPATIBLE if version.major == 1 else Label.STALE
                card.explanation = 'Native BaseModel.parse_obj is supported in V1; V2 retains it with a deprecation warning.'
            else:
                card.label = Label.WRONG_VERSION if version.major == 1 else Label.COMPATIBLE
                card.explanation = 'Native BaseModel.model_validate is the V2 replacement; native V1 models lack this API.'
        elif recipe.rule == 'sqlalchemy_old':
            card.boundary = 'SQLAlchemy 2.0 removes Engine.execute; 1.4 future mode disables it.'
            if version.major == 1 and profile.sqlalchemy_future is None:
                card.explanation = 'SQLAlchemy 1.4 engine future mode is unknown; Engine.execute depends on that setting.'
            else:
                card.label = Label.STALE if version.major == 1 and profile.sqlalchemy_future is False else Label.WRONG_VERSION
                card.explanation = 'Engine.execute is legacy in SQLAlchemy 1.4; future mode disables it, and 2.0 removes it.'
        else:
            card.boundary = 'SQLAlchemy 2.0 requires executable statements and explicit write transactions.'
            if version.major == 1 and profile.sqlalchemy_future is None:
                card.explanation = 'SQLAlchemy 1.4 future mode is unknown; confirm engine context before applying this recipe.'
            else:
                card.label = Label.COMPATIBLE
                card.explanation = 'This scoped Connection.execute recipe explicitly uses text(...) and a supported connection/transaction context.'
        if version and card.label != Label.UNCERTAIN:
            card.witness_id = _witness(recipe.rule, version, profile)
        cards.append(card)
    return cards


def classify(hit: SearchHit, body: str | None, profile: Profile, library: str,
             facts_text: dict[str, str]) -> Card:
    """Legacy one-card interface: a mixed page must not collapse to one recipe verdict."""
    cards = classify_all(hit, body, profile, library, facts_text)
    if len(cards) == 1:
        return cards[0]
    return Card(hit=hit, id=hit.id, label=Label.UNCERTAIN,
                explanation='Source has multiple scoped recipes; inspect each recipe card separately.')


ORDER = {Label.COMPATIBLE: 4, Label.UNCERTAIN: 3, Label.STALE: 2, Label.WRONG_VERSION: 1}


def rank(cards: list[Card]) -> list[Card]:
    for card in cards:
        card.score = ORDER[card.label] * 100 + len(card.evidence) * 10 - min(card.hit.position, 10)
    return sorted(cards, key=lambda card: (-card.score, card.hit.id, card.rule_id or ''))
