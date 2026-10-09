from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Label(StrEnum):
    COMPATIBLE = 'COMPATIBLE'
    WRONG_VERSION = 'WRONG_VERSION'
    STALE = 'STALE'
    UNCERTAIN = 'UNCERTAIN'


class Dependency(BaseModel):
    name: str
    constraint: str
    exact: str | None = None
    source: str


class Profile(BaseModel):
    name: str
    dependencies: list[Dependency] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sqlalchemy_future: bool | None = None
    pydantic_api_mode: str = 'native'


class SearchHit(BaseModel):
    id: str
    title: str
    url: str
    snippet: str = ''
    position: int
    queries: list[str] = Field(default_factory=list)
    provenance: list['SearchProvenance'] = Field(default_factory=list)


class SearchProvenance(BaseModel):
    engine: Literal['google', 'bing'] = 'google'
    query: str
    position: int
    search_id: str | None = None
    retrieval: Literal['live', 'cached', 'illustrative'] = 'live'


class Evidence(BaseModel):
    url: str
    quote: str
    source_kind: str
    content_hash: str
    section: str | None = None
    provenance: str | None = None
    fetched_at: str | None = None


class Card(BaseModel):
    hit: SearchHit
    label: Label
    explanation: str
    recipe: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    score: int = 0
    id: str | None = None
    rule_id: str | None = None
    boundary: str | None = None
    preconditions: list[str] = Field(default_factory=list)
    witness_id: str | None = None


class ProfileResult(BaseModel):
    profile: Profile
    cards: list[Card]


class SearchReceipt(BaseModel):
    engines: list[str] = Field(default_factory=list)
    api_calls: int = 0
    cache_hits: int = 0
    budget_limit: int = 50
    budget_used: int = 0
    budget_remaining: int = 50
    cache_ttl_seconds: int = 86_400
    quota_scope: str = 'Application allocation; not the SerpApi account balance.'


class SearchResponse(BaseModel):
    mode: Literal['live', 'cached', 'mixed', 'recorded']
    queries: list[str]
    candidate_count: int
    results: list[ProfileResult]
    warnings: list[str] = Field(default_factory=list)
    receipt: SearchReceipt = Field(default_factory=SearchReceipt)
    pool_id: str = ''
    rule_version: str = '2026-10-09'
