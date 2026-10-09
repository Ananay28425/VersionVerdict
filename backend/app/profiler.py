import re
import tomllib
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from .models import Dependency, Profile

MAX_FILE_BYTES = 256 * 1024
SUPPORTED_FILES = {'requirements.txt', 'pyproject.toml'}

def _add(text: str, source: str, profile: Profile):
    try:
        req = Requirement(text)
    except Exception:
        profile.warnings.append(f'{source}: unsupported declaration: {text[:100]}')
        return
    if req.url:
        profile.warnings.append(f'{source}: direct URL dependency {req.name} has unknown version')
        return
    if req.marker:
        profile.warnings.append(f'{source}: marker for {req.name} needs target context; skipped')
        return
    constraint = str(req.specifier) or 'unknown'
    exact = None
    specs = list(req.specifier)
    if len(specs) == 1 and specs[0].operator == '==' and '*' not in specs[0].version:
        exact = specs[0].version
    profile.dependencies.append(Dependency(name=canonicalize_name(req.name), constraint=constraint, exact=exact, source=source))

def parse_profile(name: str, files: list[tuple[str, bytes]], *, sqlalchemy_future: bool | None = None, pydantic_api_mode: str = 'native') -> Profile:
    profile = Profile(name=name, sqlalchemy_future=sqlalchemy_future, pydantic_api_mode=pydantic_api_mode)
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
                if line.startswith(('-r', '--requirement', '-e', '--editable', '--index', '--extra-index')):
                    profile.warnings.append(f'{filename}:{n}: directive needs external context; skipped')
                    continue
                _add(line, f'{filename}:{n}', profile)
        else:
            try:
                data = tomllib.loads(content)
            except tomllib.TOMLDecodeError as exc:
                raise ValueError('Invalid pyproject.toml') from exc
            project = data.get('project', {})
            if project.get('dynamic') and 'dependencies' in project['dynamic']:
                profile.warnings.append('Dynamic project dependencies cannot be resolved')
            for item in project.get('dependencies', []):
                _add(item, filename, profile)
            poetry = data.get('tool', {}).get('poetry', {}).get('dependencies', {})
            for pkg, spec in poetry.items():
                if pkg.lower() == 'python':
                    continue
                if isinstance(spec, str) and (spec.startswith(('^', '~')) or '*' in spec):
                    profile.warnings.append(f'{filename}: Poetry constraint for {pkg} needs resolution; skipped')
                elif isinstance(spec, str):
                    _add(f'{pkg}{spec if spec[:1] in "<>=!" else "==" + spec}', filename, profile)
                else:
                    profile.warnings.append(f'{filename}: unsupported Poetry declaration for {pkg}')
    by_name: dict[str, list[Dependency]] = {}
    for dep in profile.dependencies:
        by_name.setdefault(dep.name, []).append(dep)
    for pkg, deps in by_name.items():
        if len(deps) > 1:
            profile.warnings.append(f'{pkg}: multiple declarations require manual resolution')
    return profile

def version_for(profile: Profile, package: str) -> str | None:
    matches = [d for d in profile.dependencies if d.name == package]
    return matches[0].exact if len(matches) == 1 else None
