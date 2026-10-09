"""Small search plans shared across dependency profiles."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class QuerySpec:
    engine: str
    query: str


def plan(query: str, library: str, include_secondary: bool = False) -> list[QuerySpec]:
    query = re.sub(r'\s+', ' ', query).strip()[:240]
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
        raise ValueError('Supported libraries: pydantic, sqlalchemy')
    specs = [QuerySpec('google', value) for value in queries]
    if include_secondary:
        specs.append(QuerySpec('bing', f'{query} {library} migration'))
    return specs
