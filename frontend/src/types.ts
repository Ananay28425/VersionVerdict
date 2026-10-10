export type Library = 'pydantic' | 'sqlalchemy'
export type Verdict = 'COMPATIBLE' | 'WRONG_VERSION' | 'STALE' | 'UNCERTAIN'
export type Context = { name: string; file: File | null; extra: File | null; apiMode: string; future: string }
export type Evidence = { url: string; quote: string; source_kind: string; content_hash?: string; section?: string | null; provenance?: string; fetched_at?: string | null }
export type Provenance = { engine: string; query: string; position: number; search_id?: string | null; retrieval?: string }
export type Card = {
  id?: string | null
  hit: { id: string; title: string; url: string; snippet: string; position: number; provenance?: Provenance[] }
  label: Verdict
  explanation: string
  recipe: string | null
  evidence: Evidence[]
  rule_id?: string | null
  boundary?: string | null
  preconditions?: string[]
  witness_id?: string | null
}
export type Group = {
  profile: {
    name: string
    dependencies: { name: string; constraint: string; exact: string | null; source?: string }[]
    warnings: string[]
    pydantic_api_mode?: string
    sqlalchemy_future?: boolean | null
  }
  cards: Card[]
}
export type Receipt = { engines: string[]; api_calls: number; cache_hits: number; budget_limit: number; budget_used: number; budget_remaining: number; cache_ttl_seconds?: number }
export type SearchResult = { mode: string; candidate_count: number; queries: string[]; results: Group[]; warnings: string[]; receipt?: Receipt; pool_id?: string; rule_version?: string }
export type Capabilities = { engines: { id: string; name: string; optional: boolean }[]; budget: { limit: number; used: number; remaining: number }; live_search_configured: boolean }
export const prompts: Record<Library, string> = { pydantic: 'validate a dictionary into a Pydantic model', sqlalchemy: 'execute a SQL statement with SQLAlchemy' }
export const demoFiles: Record<Library, [string, string]> = { pydantic: ['pydantic-v1-requirements.txt', 'pydantic-v2-requirements.txt'], sqlalchemy: ['sqlalchemy-14-requirements.txt', 'sqlalchemy-20-requirements.txt'] }
export const verdictNames: Record<Verdict, string> = { COMPATIBLE: 'Compatible', WRONG_VERSION: 'Wrong version', STALE: 'Stale', UNCERTAIN: 'Uncertain' }
