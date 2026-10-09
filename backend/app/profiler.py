import re
from pathlib import Path

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from .models import Dependency, Profile

MAX_FILE_BYTES = 256 * 1024
SUPPORTED_FILES = {'requirements.txt', 'pyproject.toml'}


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
            raise ValueError('Only requirements.txt and pyproject.toml are supported')
        try:
            content = body.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError(f'{filename} must be UTF-8') from exc
        if filename == 'requirements.txt':
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
        else:
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
    matches = [d for d in profile.dependencies if d.name == package]
    return matches[0].exact if len(matches) == 1 else None
