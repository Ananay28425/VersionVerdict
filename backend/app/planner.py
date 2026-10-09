import re


def plan(query: str, library: str) -> list[str]:
    query = re.sub(r'\s+', ' ', query).strip()[:240]
    if library == 'pydantic':
        return [
            f'{query} pydantic',
            f'{query} pydantic v1 site:docs.pydantic.dev',
            f'{query} pydantic v2 site:docs.pydantic.dev',
        ]
    if library == 'sqlalchemy':
        return [
            f'{query} sqlalchemy',
            f'{query} sqlalchemy 1.4 2.0 site:docs.sqlalchemy.org',
        ]
    raise ValueError('Supported libraries: pydantic, sqlalchemy')
