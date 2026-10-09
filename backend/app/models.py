from enum import StrEnum
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

class Evidence(BaseModel):
    url: str
    quote: str
    source_kind: str
    content_hash: str

class Card(BaseModel):
    hit: SearchHit
    label: Label
    explanation: str
    recipe: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    score: int = 0

class ProfileResult(BaseModel):
    profile: Profile
    cards: list[Card]

class SearchResponse(BaseModel):
    mode: str
    queries: list[str]
    candidate_count: int
    results: list[ProfileResult]
    warnings: list[str] = Field(default_factory=list)
