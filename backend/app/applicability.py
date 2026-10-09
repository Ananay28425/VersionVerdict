from packaging.version import Version, InvalidVersion
from .models import Card, Evidence, Label, Profile, SearchHit
from .profiler import version_for
from .evidence import cite

# Quotes are from pinned official migration source revisions, reviewed before recording.
PYDANTIC_MIGRATION = 'https://github.com/pydantic/pydantic/blob/ca359e009fcfaff2a80df33cb99ee6ab21aaf033/docs/migration.md'
SQLA_MIGRATION = 'https://github.com/sqlalchemy/sqlalchemy/blob/e75a4651657f1d12dd747cc8e6f93d2815ea8936/doc/build/changelog/migration_20.rst'
FACTS = {
    'pydantic_old': ('Where possible, we have retained the deprecated methods with their old names', PYDANTIC_MIGRATION),
    'pydantic_new': ('`parse_obj()` | `model_validate()`', PYDANTIC_MIGRATION),
    'sqlalchemy_old': ('The Engine.execute() function/method is considered legacy as of the 1.x series of SQLAlchemy and will be removed in 2.0.', SQLA_MIGRATION),
    'sqlalchemy_new': ('All statement execution in SQLAlchemy 2.0 is performed by the Connection.execute() method of Connection', SQLA_MIGRATION),
}

def _version(profile: Profile, library: str) -> Version | None:
    raw = version_for(profile, library)
    try:
        return Version(raw) if raw else None
    except InvalidVersion:
        return None

def classify(hit: SearchHit, body: str | None, profile: Profile, library: str, facts_text: dict[str, str]) -> Card:
    base = Card(hit=hit, label=Label.UNCERTAIN, explanation='No verified recipe and version evidence for this source.')
    if not body:
        base.explanation = 'Source page could not be verified; search snippet is insufficient.'
        return base
    version = _version(profile, library)
    if version is None:
        base.explanation = 'Dependency version is a range, missing, or conflicting; applicability is unresolved.'
        return base
    major = version.major
    if library == 'pydantic' and not ((major == 1 and version.minor == 10) or (major == 2 and version.minor <= 14)):
        base.explanation = 'This Pydantic version is outside the verified rule range.'
        return base
    if library == 'sqlalchemy' and not ((major == 1 and version.minor == 4) or (major == 2 and version.minor == 0)):
        base.explanation = 'This SQLAlchemy version is outside the verified rule range.'
        return base
    descriptor = hit.title.lower()
    rules = {
        'pydantic': [('parse_obj', 'pydantic_old', 'parse_obj()'), ('model_validate', 'pydantic_new', 'model_validate()')],
        'sqlalchemy': [('engine.execute', 'sqlalchemy_old', 'Engine.execute()'), ('connection.execute', 'sqlalchemy_new', 'Connection.execute()')],
    }
    matches = [(rid, recipe) for token, rid, recipe in rules[library] if token in descriptor and token in body.lower()]
    if len(matches) != 1:
        base.explanation = 'Source contains no unique recognized recipe; mixed or ambiguous page.'
        return base
    rid, recipe = matches[0]
    quote, fact_url = FACTS[rid]
    fact_body = facts_text.get(rid, '')
    fact = cite(fact_url, quote, fact_body, 'official migration fact')
    recipe_quote = next((part for part in [recipe, recipe.removesuffix('()')] if part in body), None)
    source = cite(hit.url, recipe_quote, body, 'fetched recipe') if recipe_quote else None
    if not source or not fact:
        base.explanation = 'Required official evidence quote is missing.'
        return base
    base.recipe = recipe
    base.evidence = [source, fact]
    if library == 'pydantic':
        if profile.pydantic_api_mode != 'native':
            base.explanation = 'Pydantic API namespace is not confirmed native; v1 shim can change applicability.'
            return base
        if rid == 'pydantic_old':
            base.label = Label.COMPATIBLE if major == 1 else Label.STALE if major == 2 else Label.UNCERTAIN
            base.explanation = 'parse_obj() is native in Pydantic V1; V2 retains it with deprecation and recommends model_validate().'
        else:
            base.label = Label.WRONG_VERSION if major == 1 else Label.COMPATIBLE if major == 2 else Label.UNCERTAIN
            base.explanation = 'model_validate() is the V2 replacement for parse_obj(); native V1 models lack it.'
    elif rid == 'sqlalchemy_old':
        if major == 1 and profile.sqlalchemy_future is None:
            base.explanation = 'SQLAlchemy 1.4 future mode is unknown; Engine.execute() behavior depends on engine mode.'
            return base
        base.label = Label.STALE if major == 1 and profile.sqlalchemy_future is False else Label.WRONG_VERSION if major == 2 or profile.sqlalchemy_future is True else Label.UNCERTAIN
        base.explanation = 'Engine.execute() is legacy in SQLAlchemy 1.4 and removed in 2.0; 1.4 future mode also disables it.'
    else:
        base.label = Label.COMPATIBLE if major in {1, 2} else Label.UNCERTAIN
        base.explanation = 'Connection.execute() is documented replacement; check statement and transaction setup in linked source.'
    return base

ORDER = {Label.COMPATIBLE: 4, Label.UNCERTAIN: 3, Label.STALE: 2, Label.WRONG_VERSION: 1}

def rank(cards: list[Card]) -> list[Card]:
    for card in cards:
        card.score = ORDER[card.label] * 100 + len(card.evidence) * 10 - min(card.hit.position, 10)
    return sorted(cards, key=lambda c: (-c.score, c.hit.id))
