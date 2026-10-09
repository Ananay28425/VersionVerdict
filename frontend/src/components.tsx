import { useId, useState } from 'react'
import type { Card, Context, Group, Library, SearchResult, Verdict } from './types'
import { verdictNames } from './types'

export function Arrow({ diagonal = false }: { diagonal?: boolean }) { return <span className="arrow" aria-hidden="true"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{diagonal ? <path d="M4 12 12 4M4 4h8v8" /> : <path d="M2.5 8h11M9 3.5 13.5 8 9 12.5" />}</svg></span> }
export function VerdictBadge({ label }: { label: Verdict }) { return <span className={`verdict ${label.toLowerCase()}`}><span className="verdict-dot" aria-hidden="true" />{verdictNames[label]}</span> }
const provenanceLabels: Record<string, string> = { authored_fixture: 'Authored illustrative source', reviewed_snapshot: 'Reviewed official-source snapshot', fetched_source: 'Fetched source content' }
function cardKey(card: Card) { return card.id || `${card.hit.id}:${card.recipe || 'unknown'}` }
export function host(url: string) { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url } }

function FilePicker({ file, onChange, optional, title }: { file: File | null; onChange: (file: File | null) => void; optional?: boolean; title: string }) {
  const id = useId()
  return <div className="manifest-picker"><label className="file-picker" htmlFor={id}>
    <span className="file-symbol" aria-hidden="true">{file ? '{ }' : '+'}</span>
    <span><strong>{file?.name || title}</strong><small>{file ? `${Math.ceil(file.size / 1024) || 1} KB · declared dependencies` : optional ? 'Optional second manifest' : 'requirements.txt or pyproject.toml'}</small></span>
    <span className="file-action">{file ? 'Change' : 'Choose file'}</span>
    <input id={id} type="file" accept=".txt,.toml" onChange={event => onChange(event.target.files?.[0] || null)} aria-label={title} />
  </label>{file && <button type="button" className="remove-file" onClick={() => onChange(null)} aria-label={`Remove ${title}`}>Remove</button>}</div>
}

export function ContextPanel({ letter, value, onChange, library }: { letter: string; value: Context; onChange: (context: Context) => void; library: Library }) {
  const update = (patch: Partial<Context>) => onChange({ ...value, ...patch })
  return <section className="context-panel" aria-label={`Project ${letter} context`}>
    <div className="context-title"><span className={`project-letter project-${letter.toLowerCase()}`}>{letter}</span><label>Project name<input value={value.name} onChange={event => update({ name: event.target.value })} maxLength={80} aria-label={`Project ${letter} name`} /></label></div>
    <FilePicker file={value.file} onChange={file => update({ file })} title={`Project ${letter} dependency manifest`} />
    <details className="extra-manifest"><summary>Include a second manifest</summary><FilePicker file={value.extra} onChange={extra => update({ extra })} title={`Project ${letter} second manifest`} optional /></details>
    {library === 'pydantic' ? <label className="field-label">Pydantic API namespace<select aria-label={`Project ${letter} Pydantic API namespace`} value={value.apiMode} onChange={event => update({ apiMode: event.target.value })}><option value="unknown">Unknown — keep verdicts conservative</option><option value="native">Native Pydantic APIs</option><option value="v1_shim">pydantic.v1 compatibility namespace</option></select></label> : <label className="field-label">SQLAlchemy 1.4 engine mode<select aria-label={`Project ${letter} SQLAlchemy engine mode`} value={value.future} onChange={event => update({ future: event.target.value })}><option value="unknown">Unknown — keep verdicts conservative</option><option value="false">Legacy · future=False</option><option value="true">Future · future=True</option></select></label>}
  </section>
}

function ProfileSummary({ group, letter }: { group: Group; letter: string }) {
  const pydantic = group.profile.dependencies.find(dependency => dependency.name === 'pydantic')
  const sqlalchemy = group.profile.dependencies.find(dependency => dependency.name === 'sqlalchemy')
  const apiContext = pydantic ? `API namespace: ${group.profile.pydantic_api_mode === 'v1_shim' ? 'pydantic.v1' : group.profile.pydantic_api_mode === 'native' ? 'native' : 'unknown'}`
    : sqlalchemy?.exact?.startsWith('2.') ? 'SQLAlchemy 2.x API · the 1.4 future setting does not apply'
    : sqlalchemy ? `SQLAlchemy 1.4 mode: ${group.profile.sqlalchemy_future === true ? 'future=True' : group.profile.sqlalchemy_future === false ? 'future=False' : 'unknown'}`
    : 'Supported library dependency is unresolved'
  return <div className="profile-summary"><div><span className={`project-letter project-${letter.toLowerCase()}`}>{letter}</span><h3>{group.profile.name}</h3></div><div className="dependency-list">{group.profile.dependencies.map((dependency, index) => <span className="dependency-chip" key={`${dependency.name}-${index}`}><strong>{dependency.name}</strong><code>{dependency.exact || dependency.constraint || 'unresolved'}</code><small>{dependency.exact ? 'declared pin' : 'unresolved'}</small></span>)}</div><p className="profile-api-context">{apiContext}</p>{group.profile.warnings.map((warning, index) => <p className="inline-notice" key={index}>{warning}</p>)}</div>
}

export function ResultCard({ card, index, onWitness }: { card: Card; index: number; onWitness: (id: string) => void }) {
  const [copied, setCopied] = useState(false)
  const sourceExample = card.evidence.find(evidence => evidence.source_kind.includes('recipe'))?.quote
  async function copyRecipe() {
    if (!card.recipe) return
    try { await navigator.clipboard.writeText(sourceExample || card.recipe); setCopied(true); window.setTimeout(() => setCopied(false), 1800) } catch { setCopied(false) }
  }
  return <article className="result-card">
    <div className="result-meta"><span className="rank">{String(index + 1).padStart(2, '0')}</span><VerdictBadge label={card.label} /><span className="source-host">{host(card.hit.url)}</span></div>
    <h4><a href={card.hit.url} target="_blank" rel="noopener noreferrer">{card.hit.title}<Arrow diagonal /></a></h4>
    <p className="result-explanation">{card.explanation}</p>
    {card.recipe && <div className="recipe"><code>{card.recipe}</code><button type="button" onClick={copyRecipe} aria-label={sourceExample ? 'Copy source example' : 'Copy API identifier'}>{copied ? 'Copied' : sourceExample ? 'Copy example' : 'Copy API'}</button></div>}
    {card.boundary && <p className="version-boundary"><span>Version boundary</span>{card.boundary}</p>}
    {!!card.preconditions?.length && <div className="preconditions"><strong>Conditions to check</strong><ul>{card.preconditions.map((condition, index) => <li key={index}>{condition}</li>)}</ul></div>}
    <details className="evidence-details"><summary>Inspect supporting evidence <span>{card.evidence.length} source{card.evidence.length === 1 ? '' : 's'} <Arrow /></span></summary>
      {card.evidence.length ? card.evidence.map((evidence, index) => <div className="evidence-quote" key={index}><div className="evidence-kind">{evidence.source_kind}{evidence.section && <span>{evidence.section}</span>}</div><p className="evidence-provenance">{evidence.provenance && <span>{provenanceLabels[evidence.provenance] || evidence.provenance}</span>}{evidence.fetched_at && <time dateTime={evidence.fetched_at}>Retrieved {evidence.fetched_at}</time>}</p><blockquote>{evidence.quote}</blockquote><a href={evidence.url} target="_blank" rel="noopener noreferrer">{host(evidence.url)} <Arrow diagonal /></a>{evidence.content_hash && <details className="hash-details"><summary>Content fingerprint</summary><code>{evidence.content_hash}</code></details>}</div>) : <p className="muted">No sufficiently verified recipe evidence was available. Search snippets alone cannot establish compatibility.</p>}
      {card.rule_id && <p className="rule-id">Applied rule <code>{card.rule_id}</code></p>}
      {card.witness_id && <button className="text-link witness-link" type="button" onClick={() => onWitness(card.witness_id!)}>Inspect reproducible recipe witness <Arrow /></button>}
    </details>
    <details className="search-provenance"><summary>Search provenance</summary>{card.hit.provenance?.length ? <ul>{card.hit.provenance.map((entry, index) => <li key={index}><strong>{entry.engine === 'google' ? 'SerpApi · Google Search' : entry.engine === 'bing' ? 'SerpApi · Bing Search' : entry.engine}</strong> · original position {entry.position}{entry.retrieval && ` · ${entry.retrieval}`}<code>{entry.query}</code>{entry.search_id && <small>Search ID: {entry.search_id}</small>}</li>)}</ul> : <p>Original search position: {card.hit.position}. Additional search metadata was not supplied.</p>}</details>
  </article>
}

function Comparison({ result }: { result: SearchResult }) {
  const [left, right] = result.results
  if (!right) return <p className="empty-message">Add a second project to compare the same sources across environments.</p>
  const rightById = new Map(right.cards.map((card, index) => [cardKey(card), { card, rank: index + 1 }]))
  const rows = left.cards.map((card, index) => ({ card, leftRank: index + 1, right: rightById.get(cardKey(card)) }))
  const changed = rows.filter(row => row.right && (row.card.label !== row.right.card.label || row.leftRank !== row.right.rank)).length
  return <><div className="comparison-intro"><strong>{changed} result{changed === 1 ? '' : 's'} changed verdict or rank.</strong><p>Identical retrieved candidates. Different declared environments. A change in rank reflects applicability, not a factual confidence score.</p></div><div className="comparison-scroll"><table className="comparison-table"><thead><tr><th scope="col">Shared source / recipe</th><th scope="col">{left.profile.name}</th><th scope="col">{right.profile.name}</th><th scope="col">Why it changes</th></tr></thead><tbody>{rows.map(({ card, leftRank, right: counterpart }) => <tr key={cardKey(card)}><th scope="row"><a href={card.hit.url} target="_blank" rel="noopener noreferrer">{card.hit.title}<Arrow diagonal /></a><small>{card.recipe || host(card.hit.url)}</small><small>Original search position {card.hit.position}</small></th><td><VerdictBadge label={card.label} /><small>Rank {leftRank}</small></td><td>{counterpart ? <><VerdictBadge label={counterpart.card.label} /><small>Rank {counterpart.rank}{counterpart.rank !== leftRank ? ` · ${counterpart.rank < leftRank ? 'up' : 'down'} ${Math.abs(leftRank - counterpart.rank)}` : ''}</small></> : 'Not returned'}</td><td><p>{card.boundary || counterpart?.card.boundary || counterpart?.card.explanation || card.explanation}</p>{counterpart && card.label !== counterpart.card.label && <span className="changed-indicator">Verdict changes</span>}</td></tr>)}</tbody></table></div></>
}

export function Results({ result, onWitness }: { result: SearchResult; onWitness: (id: string) => void }) {
  const [view, setView] = useState<'sources' | 'comparison'>('sources')
  const isIllustrative = result.mode === 'recorded'
  const modeLabel = isIllustrative ? 'Illustrative demo · offline' : result.mode === 'cached' ? 'Cached search results' : result.mode === 'mixed' ? 'Live + cached search' : 'Live SerpApi retrieval'
  return <section className="results-section" id="results" aria-label="Search results"><div className="section-heading"><div><span className="eyebrow">THE VERDICT</span><h2>Same search. Your environment.</h2></div><span className={`mode-pill ${isIllustrative ? 'illustrative' : 'live'}`}><span aria-hidden="true" />{modeLabel}</span></div>
    <p className="results-description">{result.candidate_count} deduplicated candidate{result.candidate_count === 1 ? '' : 's'}{result.results.length === 2 ? ', evaluated against both projects.' : ', evaluated against your project.'} Exact versions are declared pins, not runtime observations.</p>
    {result.warnings.map((warning, index) => <p className="notice" key={index}>{warning}</p>)}
    {result.receipt && <div className="receipt"><div><span>Search engines</span><strong>{result.receipt.engines.length ? result.receipt.engines.map(engine => engine === 'google' ? 'SerpApi · Google' : engine === 'bing' ? 'SerpApi · Bing' : engine).join(' + ') : 'Offline fixture'}</strong></div><div><span>API calls this request</span><strong>{result.receipt.api_calls}</strong></div><div><span>Cached searches reused</span><strong>{result.receipt.cache_hits}</strong></div><div><span>App allowance left</span><strong>{result.receipt.budget_remaining} <small>/ {result.receipt.budget_limit}</small></strong></div><p>App allowance is a local guardrail. It does not report your account’s remaining SerpApi searches.</p></div>}
    <div className="results-controls"><div className="view-switch" aria-label="Result view"><button type="button" aria-pressed={view === 'sources'} onClick={() => setView('sources')}>Ranked sources</button><button type="button" aria-pressed={view === 'comparison'} onClick={() => setView('comparison')}>Version comparison</button></div><span>No confidence percentages. Inspect the evidence.</span></div>
    {!result.candidate_count ? <p className="empty-message">No search candidates were returned. Try a more specific API or error message.</p> : view === 'comparison' ? <Comparison result={result} /> : <div className={`result-columns ${result.results.length === 1 ? 'single' : ''}`}>{result.results.map((group, index) => <section key={`${group.profile.name}-${index}`}><ProfileSummary group={group} letter={index ? 'B' : 'A'} />{group.cards.map((card, cardIndex) => <ResultCard key={cardKey(card)} card={card} index={cardIndex} onWitness={onWitness} />)}</section>)}</div>}
    <details className="planned-queries"><summary>Inspect planned search queries <span>{result.queries.length}</span></summary><ol>{result.queries.map((query, index) => <li key={index}><code>{query}</code></li>)}</ol><p>Queries describe the retrieval plan. Consult the request receipt for actual API calls and cache reuse.</p></details>
  </section>
}
