"""Small search plans shared across dependency profiles."""

import re
from dataclasses import dataclass

from .models import Profile
from .profiler import target_name


@dataclass(frozen=True)
class QuerySpec:
    engine: str
    query: str


def _phrase(value: str) -> str:
    """Keep generated values together; never inject bare OR/search operators."""
    value = re.sub(r'\s+', ' ', value.replace('"', ' ').replace('\\', ' ')).strip()
    return f'"{value}"'


def plan(
    query: str,
    library: str,
    include_secondary: bool = False,
    profiles: list[Profile] | None = None,
) -> list[QuerySpec]:
    query = re.sub(r'\s+', ' ', query).strip()[:240]
    library = re.sub(r'\s+', ' ', library).strip()
    if not 1 <= len(library) <= 80 or re.search(r'[\x00-\x1f\x7f]', library):
        raise ValueError('Technology must contain 1 to 80 printable characters')
    if library == 'pydantic':
        queries = [
            f'{query} pydantic',
            f'{query} pydantic v1 v2 migration (site:docs.pydantic.dev OR site:pydantic.dev/docs/validation)',
        ]
    elif library == 'sqlalchemy':
        queries = [
            f'{query} sqlalchemy',
            f'{query} sqlalchemy 1.4 2.0 site:docs.sqlalchemy.org',
        ]
    else:
        # One candidate pool serves every project. Versions are a union, never
        # a separate paid retrieval per side of the comparison.
        versions = []
        contexts = []
        for profile in profiles or []:
            for dep in profile.dependencies:
                if (
                    target_name(dep.name) == target_name(library)
                    and dep.exact
                    and dep.exact not in versions
                ):
                    versions.append(dep.exact)
            # Single-character language labels and broad platform prose can
            # overwhelm the question (e.g. C bare metal => dictionary results).
            # Hardware is a narrow optional hint, kept out of the broad query.
            value = profile.hardware
            if value and len(value) <= 40 and value not in contexts:
                contexts.append(value)
        version_hint = ' OR '.join(_phrase(value) for value in versions[:2])
        if len(versions) > 1:
            version_hint = f'({version_hint})'
        context_hint = _phrase(contexts[0]) if len(contexts) == 1 else ''
        queries = [
            f'{query} {_phrase(library)}',
            ' '.join(
                value
                for value in (
                    query,
                    _phrase(library),
                    version_hint,
                    context_hint,
                    'documentation compatibility migration',
                )
                if value
            ),
        ]
    specs = [QuerySpec('google', value) for value in queries]
    if include_secondary:
        specs.append(QuerySpec('bing', f'{query} {library} migration'))
    return specs
