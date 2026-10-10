import re
import json
import configparser
from pathlib import Path

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import Dependency, Profile

MAX_FILE_BYTES = 256 * 1024
SUPPORTED_FILES = {'requirements.txt', 'pyproject.toml', 'package.json', 'Cargo.toml',
                   'go.mod', 'platformio.ini', 'environment.json'}
MAX_DEPENDENCIES = 200


class DeclaredDependency(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    version: str | None = Field(default=None, min_length=1, max_length=200)
    constraint: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode='after')
    def single_declaration(self):
        if self.version is not None and self.constraint is not None:
            raise ValueError('Declare version or constraint, not both')
        if self.version and re.search(r'[<>=*^~|,\s]', self.version):
            raise ValueError('version must be exact; use constraint for a range')
        if not self.name.strip():
            raise ValueError('Dependency name cannot be blank')
        return self


class DeclaredEnvironment(BaseModel):
    """Portable user declarations. No dependency resolution or code execution."""
    model_config = ConfigDict(extra='forbid')
    technology: str = Field(min_length=1, max_length=80)
    language: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=120)
    hardware: str | None = Field(default=None, max_length=120)
    dependencies: list[DeclaredDependency] = Field(default_factory=list, max_length=MAX_DEPENDENCIES)
    notes: str | None = Field(default=None, max_length=1000)


def target_name(value: str) -> str:
    return canonicalize_name(value.strip()).casefold()


def _declared(profile: Profile, name: str, value: object, source: str, ecosystem: str,
              *, exact: str | None = None):
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError(f'{source}: dependency name must contain 1 to 100 characters')
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError(f'{source}: dependency declaration must be a string of at most 200 characters')
    profile.dependencies.append(Dependency(name=target_name(name), constraint=value or 'unknown',
                                           exact=exact, source=source, ecosystem=ecosystem))


def _generic_manifest(filename: str, content: str, profile: Profile):
    if filename == 'environment.json':
        try:
            context = DeclaredEnvironment.model_validate_json(content)
        except ValidationError as exc:
            raise ValueError('Invalid environment.json: expected technology, optional context strings, and dependencies with name plus version or constraint') from exc
        if not context.technology.strip():
            raise ValueError('environment.json technology cannot be blank')
        for field in ('technology', 'language', 'platform', 'hardware', 'notes'):
            setattr(profile, field, getattr(context, field))
        for dep in context.dependencies:
            _declared(profile, dep.name, '==' + dep.version if dep.version else dep.constraint or 'unknown',
                      filename, 'declared', exact=dep.version)
    elif filename == 'package.json':
        try:
            data = json.loads(content)
        except ValueError as exc:
            raise ValueError('Invalid package.json') from exc
        if not isinstance(data, dict):
            raise ValueError('package.json must be an object')
        profile.language = profile.language or 'JavaScript / TypeScript'
        profile.platform = profile.platform or 'Node.js'
        for group in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
            deps = data.get(group, {})
            if not isinstance(deps, dict):
                raise ValueError(f'package.json {group} must be an object')
            for pkg, spec in deps.items():
                exact = spec if isinstance(spec, str) and re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?', spec) else None
                _declared(profile, pkg, spec, f'{filename}:{group}', 'npm', exact=exact)
        engines = data.get('engines', {})
        if isinstance(engines, dict) and isinstance(engines.get('node'), str):
            spec = engines['node']
            _declared(profile, 'node', spec, f'{filename}:engines', 'npm',
                      exact=spec if re.fullmatch(r'\d+\.\d+\.\d+', spec) else None)
    elif filename == 'Cargo.toml':
        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError('Invalid Cargo.toml') from exc
        profile.language = profile.language or 'Rust'
        tables = [(group, data.get(group, {})) for group in ('dependencies', 'dev-dependencies', 'build-dependencies')]
        targets = data.get('target', {})
        if not isinstance(targets, dict):
            raise ValueError('Cargo.toml target must be a table')
        for target, values in targets.items():
            if isinstance(values, dict):
                for group in ('dependencies', 'dev-dependencies', 'build-dependencies'):
                    if group in values:
                        tables.append((f'target.{target}.{group}', values[group]))
        for group, deps in tables:
            if not isinstance(deps, dict):
                raise ValueError(f'Cargo.toml {group} must be a table')
            for pkg, spec in deps.items():
                conditional = group.startswith('target.')
                if isinstance(spec, dict):
                    name = spec.get('package', pkg)
                    value = spec.get('version', 'unknown (path/git/workspace dependency)')
                    conditional = conditional or spec.get('optional', False)
                    if any(key in spec for key in ('git', 'path', 'workspace')):
                        conditional = True
                        profile.warnings.append(f'{name}: custom source or workspace dependency version is unresolved')
                else:
                    name, value = pkg, spec
                exact = value[1:].strip() if isinstance(value, str) and re.fullmatch(r'=\s*\d+\.\d+\.\d+', value) and not conditional else None
                _declared(profile, name, value, f'{filename}:{group}', 'cargo', exact=exact)
                if conditional:
                    profile.warnings.append(f'{name}: target or feature conditional; applicability needs build context')
    elif filename == 'go.mod':
        profile.language = profile.language or 'Go'
        in_require = False
        for number, raw in enumerate(content.splitlines(), 1):
            line = raw.split('//', 1)[0].strip()
            if line == 'require (':
                in_require = True
                continue
            if in_require and line == ')':
                in_require = False
                continue
            if line.startswith(('replace ', 'exclude ', 'retract ')):
                profile.warnings.append('go.mod replace/exclude/retract directives need module resolution; declarations are not installed versions')
            if line.startswith('go '):
                _declared(profile, 'go', '>=' + line[3:].strip(), f'{filename}:{number}', 'go')
            elif line.startswith('require ') or in_require:
                parts = (line[8:] if line.startswith('require ') else line).split()
                if not parts:
                    continue
                if len(parts) != 2 or not re.fullmatch(r'v\d+\.\d+\.\d+(?:[-+][\w.-]+)?', parts[1]):
                    raise ValueError('Unsupported go.mod require declaration')
                _declared(profile, parts[0], parts[1], f'{filename}:{number}', 'go', exact=parts[1][1:])
        if any('module resolution' in warning for warning in profile.warnings):
            for dep in profile.dependencies:
                if dep.ecosystem == 'go':
                    dep.exact = None
    elif filename == 'platformio.ini':
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        try:
            parser.read_string(content)
        except configparser.Error as exc:
            raise ValueError('Invalid platformio.ini') from exc
        profile.language = profile.language or 'C / C++'
        environments = [section for section in parser.sections() if section.startswith('env:')]
        if len(environments) > 1:
            profile.warnings.append('Multiple PlatformIO environments; declare the active environment in environment.json to resolve context')
        for section in environments:
            values = parser[section]
            if len(environments) == 1:
                profile.platform = values.get('platform')
                profile.hardware = values.get('board')
                profile.technology = values.get('framework') or profile.technology
            declarations = [('platform', values.get('platform', ''))]
            declarations += [('lib_deps', line.strip()) for line in values.get('lib_deps', '').splitlines() if line.strip()]
            for group, declaration in declarations:
                if not declaration:
                    continue
                pkg, separator, spec = declaration.rpartition('@')
                if not separator:
                    pkg, spec = declaration, 'unknown'
                exact = spec if len(environments) == 1 and re.fullmatch(r'\d+\.\d+\.\d+', spec) else None
                _declared(profile, pkg, spec, f'{filename}:{section}:{group}', 'platformio', exact=exact)


def _add(text: str, source: str, profile: Profile):
    try:
        req = Requirement(text)
    except InvalidRequirement:
        profile.warnings.append(f'{source}: unsupported declaration: {text[:100]}')
        return
    if req.url:
        profile.warnings.append(
            f'{source}: direct URL dependency {req.name} has unknown version'
        )
        profile.dependencies.append(
            Dependency(name=canonicalize_name(req.name), constraint='direct URL (unresolved)', source=source)
        )
        return
    if req.marker:
        profile.warnings.append(
            f'{source}: marker for {req.name} needs target context; version unresolved'
        )
        profile.dependencies.append(
            Dependency(
                name=canonicalize_name(req.name),
                constraint=f'{req.specifier or "unknown"}; {req.marker}',
                source=source,
            )
        )
        return
    constraint = str(req.specifier) or 'unknown'
    exact = None
    specs = list(req.specifier)
    if len(specs) == 1 and specs[0].operator == '==' and '*' not in specs[0].version:
        exact = specs[0].version
    profile.dependencies.append(
        Dependency(
            name=canonicalize_name(req.name),
            constraint=constraint,
            exact=exact,
            source=source,
        )
    )


def parse_profile(
    name: str,
    files: list[tuple[str, bytes]],
    *,
    sqlalchemy_future: bool | None = None,
    pydantic_api_mode: str = 'native',
) -> Profile:
    profile = Profile(
        name=name,
        sqlalchemy_future=sqlalchemy_future,
        pydantic_api_mode=pydantic_api_mode,
    )
    if len(files) > 2 or sum(len(body) for _, body in files) > MAX_FILE_BYTES:
        raise ValueError('At most two files and 256 KiB combined are allowed')
    if pydantic_api_mode not in {'native', 'v1_shim', 'unknown'}:
        raise ValueError('Invalid Pydantic API mode')
    for filename, body in files:
        filename = Path(filename).name
        if filename not in SUPPORTED_FILES:
            raise ValueError('Unsupported manifest. Use ' + ', '.join(sorted(SUPPORTED_FILES)))
        try:
            content = body.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError(f'{filename} must be UTF-8') from exc
        if filename == 'requirements.txt':
            profile.language = profile.language or 'Python'
            for n, raw in enumerate(content.splitlines(), 1):
                line = raw.split(' #', 1)[0].strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith(
                    (
                        '-r',
                        '--requirement',
                        '-e',
                        '--editable',
                        '--index',
                        '--extra-index',
                    )
                ):
                    profile.warnings.append(
                        f'{filename}:{n}: directive needs external context; skipped'
                    )
                    continue
                _add(line, f'{filename}:{n}', profile)
        elif filename != 'pyproject.toml':
            _generic_manifest(filename, content, profile)
        else:
            profile.language = profile.language or 'Python'
            try:
                data = tomllib.loads(content)
            except tomllib.TOMLDecodeError as exc:
                raise ValueError('Invalid pyproject.toml') from exc
            project = data.get('project', {})
            if not isinstance(project, dict):
                raise ValueError('pyproject.toml project must be a table')
            dynamic = project.get('dynamic', [])
            if not isinstance(dynamic, list) or not all(isinstance(item, str) for item in dynamic):
                raise ValueError('project.dynamic must be a list of field names')
            if 'dependencies' in dynamic:
                profile.warnings.append(
                    'Dynamic project dependencies cannot be resolved'
                )
            dependencies = project.get('dependencies', [])
            if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
                raise ValueError('project.dependencies must be a list of requirement strings')
            if dependencies and 'dependencies' in dynamic:
                raise ValueError('project.dependencies cannot be both dynamic and statically declared')
            for item in dependencies:
                _add(item, filename, profile)
            tool = data.get('tool', {})
            if not isinstance(tool, dict):
                raise ValueError('pyproject.toml tool must be a table')
            poetry_table = tool.get('poetry', {})
            if not isinstance(poetry_table, dict):
                raise ValueError('tool.poetry must be a table')
            poetry = poetry_table.get('dependencies', {})
            if not isinstance(poetry, dict):
                raise ValueError('tool.poetry.dependencies must be a table')
            for pkg, spec in poetry.items():
                if pkg.lower() == 'python':
                    continue
                if isinstance(spec, str) and (
                    spec.startswith(('^', '~')) or '*' in spec
                ):
                    profile.warnings.append(
                        f'{filename}: Poetry constraint for {pkg} needs resolution'
                    )
                    _add(pkg, filename, profile)
                elif isinstance(spec, str):
                    _add(
                        f'{pkg}{spec if spec[:1] in "<>=!" else "==" + spec}',
                        filename,
                        profile,
                    )
                else:
                    profile.warnings.append(
                        f'{filename}: unsupported Poetry declaration for {pkg}'
                    )
                    _add(pkg, filename, profile)
    if len(profile.dependencies) > MAX_DEPENDENCIES:
        raise ValueError(f'At most {MAX_DEPENDENCIES} dependency declarations are allowed')
    by_name: dict[str, list[Dependency]] = {}
    for dep in profile.dependencies:
        by_name.setdefault(dep.name, []).append(dep)
    for pkg, deps in by_name.items():
        if len(deps) > 1:
            profile.warnings.append(
                f'{pkg}: multiple declarations require manual resolution'
            )
    return profile


def version_for(profile: Profile, package: str) -> str | None:
    matches = [d for d in profile.dependencies if target_name(d.name) == target_name(package)]
    return matches[0].exact if len(matches) == 1 else None
