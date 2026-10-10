export type Library = string
export type DemoLibrary = 'pydantic' | 'sqlalchemy'
export type Verdict = 'COMPATIBLE' | 'WRONG_VERSION' | 'STALE' | 'UNCERTAIN'
export type Context = {
  name: string; file: File | null; extra: File | null; apiMode: string; future: string
  inputMode: 'manual' | 'file'; version: string; language: string; platform: string; hardware: string; dependencies: string; notes: string
}
export type Evidence = { url: string; quote: string; source_kind: string; content_hash?: string; section?: string | null; provenance?: string; fetched_at?: string | null }
export type Provenance = { engine: string; query: string; position: number; search_id?: string | null; retrieval?: string }
export type Card = {
  id?: string | null
  hit: { id: string; title: string; url: string; snippet: string; position: number; provenance?: Provenance[] }
  label: Verdict; explanation: string; recipe: string | null; evidence: Evidence[]
  rule_id?: string | null; boundary?: string | null; preconditions?: string[]; witness_id?: string | null
  relevance_score?: number; ranking_reasons?: string[]
}
export type Group = {
  profile: {
    name: string; dependencies: { name: string; constraint: string; exact: string | null; source?: string }[]
    warnings: string[]; pydantic_api_mode?: string; sqlalchemy_future?: boolean | null
    technology?: string | null; language?: string | null; platform?: string | null; hardware?: string | null; notes?: string | null
  }
  cards: Card[]
}
export type Receipt = { engines: string[]; api_calls: number; cache_hits: number; budget_limit: number; budget_used: number; budget_remaining: number; cache_ttl_seconds?: number }
export type SearchResult = { mode: string; candidate_count: number; queries: string[]; results: Group[]; warnings: string[]; receipt?: Receipt; pool_id?: string; rule_version?: string }
export type Capabilities = { engines: { id: string; name: string; optional: boolean }[]; budget: { limit: number; used: number; remaining: number }; live_search_configured: boolean; universal_search?: boolean; supported_manifests?: string[] }
export const supportedManifests = ['requirements.txt', 'pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod', 'platformio.ini', 'environment.json']
export const prompts: Record<DemoLibrary, string> = { pydantic: 'validate a dictionary into a Pydantic model', sqlalchemy: 'execute a SQL statement with SQLAlchemy' }
export const demoFiles: Record<DemoLibrary, [string, string]> = { pydantic: ['pydantic-v1-requirements.txt', 'pydantic-v2-requirements.txt'], sqlalchemy: ['sqlalchemy-14-requirements.txt', 'sqlalchemy-20-requirements.txt'] }
export const verdictNames: Record<Verdict, string> = { COMPATIBLE: 'Compatible', WRONG_VERSION: 'Wrong version', STALE: 'Stale', UNCERTAIN: 'Uncertain' }
