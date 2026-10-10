import { useEffect, useId, useState } from 'react'
import type { Card, Context, Group, Library, SearchResult, Verdict } from './types'
import { supportedManifests, verdictNames } from './types'
import { exportReport } from './reports'

export function Arrow({ diagonal = false }: { diagonal?: boolean }) { return <span className="arrow" aria-hidden="true"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{diagonal ? <path d="M4 12 12 4M4 4h8v8" /> : <path d="M2.5 8h11M9 3.5 13.5 8 9 12.5" />}</svg></span> }
export function VerdictBadge({ label }: { label: Verdict }) { return <span className={`verdict ${label.toLowerCase()}`}><span className="verdict-dot" aria-hidden="true" />{verdictNames[label]}</span> }
const provenanceLabels: Record<string, string> = { authored_fixture: 'Authored illustrative source', reviewed_snapshot: 'Reviewed official-source snapshot', fetched_source: 'Fetched source content' }
function cardKey(card: Card) { return card.id || `${card.hit.id}:${card.recipe || 'unknown'}` }
export function host(url: string) { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url } }

function FilePicker({ file, onChange, optional, title }: { file: File | null; onChange: (file: File | null) => void; optional?: boolean; title: string }) {
  const id = useId()
  const [preview, setPreview] = useState<string[]>([])
  useEffect(() => {
    let active = true
    setPreview([])
    if (file && supportedManifests.includes(file.name)) {
      void file.slice(0, 4096).text().then(text => { if (active) setPreview(text.split(/\r?\n/).slice(0, 6)) }).catch(() => {})
    }
    return () => { active = false }
  }, [file])
  return <div className="manifest-picker"><label className="file-picker" htmlFor={id}>
    <span className="file-symbol" aria-hidden="true">{file ? '{ }' : '+'}</span>
    <span><strong>{file?.name || title}</strong><small>{file ? `${Math.ceil(file.size / 1024) || 1} KB · declared dependencies` : optional ? 'Optional second manifest' : 'Python · JS · Rust · Go · PlatformIO · JSON'}</small></span>
    <span className="file-action">{file ? 'Change' : 'Choose file'}</span>
    <input id={id} type="file" accept=".txt,.toml,.json,.mod,.ini" onChange={event => onChange(event.target.files?.[0] || null)} aria-label={title} />
  </label>{preview.length > 0 && <div className="manifest-preview" aria-label={`${title} content preview`}>{preview.map((line, index) => <div key={index}><span aria-hidden="true">{index + 1}</span><code>{line || ' '}</code></div>)}<small>First 6 lines / preview only</small></div>}{file && <button type="button" className="remove-file" onClick={() => onChange(null)} aria-label={`Remove ${title}`}>Remove</button>}</div>
}

export function ContextPanel({ letter, value, onChange, library }: { letter: string; value: Context; onChange: (context: Context) => void; library: Library }) {
  const update = (patch: Partial<Context>) => onChange({ ...value, ...patch })
  return <section className="context-panel" aria-label={`Project ${letter} context`}>
    <div className="context-title"><span className={`project-letter project-${letter.toLowerCase()}`}>{letter}</span><label>Environment name<input value={value.name} onChange={event => update({ name: event.target.value })} maxLength={80} aria-label={`Project ${letter} name`} /></label></div>
    <div className="input-mode view-switch" aria-label={`Project ${letter} context input`}><button type="button" aria-pressed={value.inputMode === 'manual'} onClick={() => update({ inputMode: 'manual' })}>Manual context</button><button type="button" aria-pressed={value.inputMode === 'file'} onClick={() => update({ inputMode: 'file' })}>Upload manifest</button></div>
    {value.inputMode === 'file' ? <><FilePicker file={value.file} onChange={file => update({ file })} title={`Project ${letter} dependency manifest`} /><details className="extra-manifest"><summary>Include a second manifest</summary><FilePicker file={value.extra} onChange={extra => update({ extra })} title={`Project ${letter} second manifest`} optional /></details><p className="context-help">requirements.txt · pyproject.toml · package.json · Cargo.toml · go.mod · platformio.ini · environment.json</p></> : <div className="manual-context">
      <label className="field-label">{library.trim() || 'Target'} version / constraint<input aria-label={`Project ${letter} target version`} value={value.version} onChange={event => update({ version: event.target.value })} maxLength={200} placeholder="e.g. 5.2.1 or >=5,<6 · blank = unknown" /></label>
      <div className="manual-grid"><label className="field-label">Language<input aria-label={`Project ${letter} language`} value={value.language} onChange={event => update({ language: event.target.value })} maxLength={120} placeholder="C / C++ / Rust / Python…" /></label><label className="field-label">Platform / OS<input aria-label={`Project ${letter} platform`} value={value.platform} onChange={event => update({ platform: event.target.value })} maxLength={120} placeholder="FreeRTOS / Linux / browser…" /></label></div>
      <label className="field-label">Hardware / architecture<input aria-label={`Project ${letter} hardware`} value={value.hardware} onChange={event => update({ hardware: event.target.value })} maxLength={120} placeholder="ESP32-S3 / STM32 / x86_64…" /></label>
      <details className="context-extra"><summary>Additional dependencies & constraints</summary><label className="field-label">One component per line<textarea aria-label={`Project ${letter} dependencies`} value={value.dependencies} onChange={event => update({ dependencies: event.target.value })} maxLength={8000} rows={3} placeholder={'gcc=13.2.0\nfreertos>=10.0'} /></label><label className="field-label">Relevant conditions / notes<textarea aria-label={`Project ${letter} notes`} value={value.notes} onChange={event => update({ notes: event.target.value })} maxLength={1000} rows={2} placeholder="Compiler flags, build mode, enabled features…" /></label></details>
      <p className="context-help">Explicit versions stay declared. Blank versions stay unknown. Manual context becomes environment.json.</p>
    </div>}
    {library.trim().toLowerCase() === 'pydantic' && <label className="field-label">Pydantic API namespace<select aria-label={`Project ${letter} Pydantic API namespace`} value={value.apiMode} onChange={event => update({ apiMode: event.target.value })}><option value="unknown">Unknown — keep verdicts conservative</option><option value="native">Native Pydantic APIs</option><option value="v1_shim">pydantic.v1 compatibility namespace</option></select></label>}
    {library.trim().toLowerCase() === 'sqlalchemy' && <label className="field-label">SQLAlchemy 1.4 engine mode<select aria-label={`Project ${letter} SQLAlchemy engine mode`} value={value.future} onChange={event => update({ future: event.target.value })}><option value="unknown">Unknown — keep verdicts conservative</option><option value="false">Legacy · future=False</option><option value="true">Future · future=True</option></select></label>}
  </section>
}

function ProfileSummary({ group, letter }: { group: Group; letter: string }) {
  const target = group.profile.technology?.toLowerCase()
  const pydantic = (!target || target === 'pydantic') ? group.profile.dependencies.find(dependency => dependency.name === 'pydantic') : undefined
  const sqlalchemy = (!target || target === 'sqlalchemy') ? group.profile.dependencies.find(dependency => dependency.name === 'sqlalchemy') : undefined
  const apiContext = pydantic ? `API namespace: ${group.profile.pydantic_api_mode === 'v1_shim' ? 'pydantic.v1' : group.profile.pydantic_api_mode === 'native' ? 'native' : 'unknown'}`
    : sqlalchemy?.exact?.startsWith('2.') ? 'SQLAlchemy 2.x API · the 1.4 future setting does not apply'
    : sqlalchemy ? `SQLAlchemy 1.4 mode: ${group.profile.sqlalchemy_future === true ? 'future=True' : group.profile.sqlalchemy_future === false ? 'future=False' : 'unknown'}`
    : 'Unreviewed recipes remain uncertain unless fetched source evidence establishes an explicit applicability rule.'
  return <div className="profile-summary"><div><span className={`project-letter project-${letter.toLowerCase()}`}>{letter}</span><h3>{group.profile.name}</h3></div><div className="dependency-list">{group.profile.dependencies.map((dependency, index) => <span className="dependency-chip" key={`${dependency.name}-${index}`}><strong>{dependency.name}</strong><code>{dependency.exact || dependency.constraint || 'unresolved'}</code><small>{dependency.exact ? 'declared pin' : 'unresolved'}</small></span>)}</div><p className="profile-api-context">{[group.profile.technology, group.profile.language, group.profile.platform, group.profile.hardware].filter(Boolean).join(' / ')}</p><p className="profile-api-context">{apiContext}</p>{group.profile.notes && <p className="inline-notice">Context: {group.profile.notes}</p>}{group.profile.warnings.map((warning, index) => <p className="inline-notice" key={index}>{warning}</p>)}</div>
}

export function ResultCard({ card, index, onWitness }: { card: Card; index: number; onWitness: (id: string) => void }) {
  const [copied, setCopied] = useState(false)
  const sourceExample = card.evidence.find(evidence => evidence.source_kind.includes('recipe'))?.quote
  async function copyRecipe() {
    if (!card.recipe) return
    try { await navigator.clipboard.writeText(sourceExample || card.recipe); setCopied(true); window.setTimeout(() => setCopied(false), 1800) } catch { setCopied(false) }
  }
  return <article className={`result-card result-${card.label.toLowerCase()}`}>
    <div className="result-meta"><span className="rank">{String(index + 1).padStart(2, '0')}</span><VerdictBadge label={card.label} /><span className="source-host">{host(card.hit.url)}</span></div>
    <h4><a href={card.hit.url} target="_blank" rel="noopener noreferrer">{card.hit.title}<Arrow diagonal /></a></h4>
    <p className="result-explanation">{card.explanation}</p>
    {!!card.ranking_reasons?.length && <details className="search-provenance"><summary>Ranking signals · metadata only</summary><p>These signals order results. They do not establish compatibility.</p><ul>{card.ranking_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></details>}
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

export function Results({ result, query, technology, onWitness }: { result: SearchResult; query: string; technology: string; onWitness: (id: string) => void }) {
  const [view, setView] = useState<'sources' | 'comparison'>('sources')
  const [filter, setFilter] = useState<Verdict | 'ALL'>('ALL')
  const [textFilter, setTextFilter] = useState('')
  const [exportError, setExportError] = useState('')
  const include = (card: Card) => (filter === 'ALL' || card.label === filter) && `${card.hit.title} ${card.explanation} ${card.recipe || ''} ${host(card.hit.url)}`.toLowerCase().includes(textFilter.toLowerCase())
  function download(format: 'json' | 'markdown') {
    try { exportReport(result, query, technology, format); setExportError('') } catch { setExportError('The browser could not save the report. Try another browser or allow downloads.') }
  }
  const isIllustrative = result.mode === 'recorded'
  const modeLabel = isIllustrative ? 'Illustrative demo · offline' : result.mode === 'cached' ? 'Cached search results' : result.mode === 'mixed' ? 'Live + cached search' : 'Live SerpApi retrieval'
  return <section className="results-section" id="results" aria-label="Search results"><div className="section-heading"><div><span className="eyebrow">THE VERDICT</span><h2>Same search. Your environment.</h2></div><span className={`mode-pill ${isIllustrative ? 'illustrative' : 'live'}`}><span aria-hidden="true" />{modeLabel}</span></div>
    <p className="results-description">{result.candidate_count} deduplicated candidate{result.candidate_count === 1 ? '' : 's'}{result.results.length === 2 ? ', evaluated against both projects.' : ', evaluated against your project.'} Exact versions are declared pins, not runtime observations.</p>
    {(result.pool_id || result.rule_version) && <div className="result-trace">{result.pool_id && <span>shared source pool <code>{result.pool_id}</code></span>}{result.rule_version && <span>rules <code>{result.rule_version}</code></span>}</div>}
    {result.warnings.map((warning, index) => <p className="notice" key={index}>{warning}</p>)}
    {result.receipt && <div className="receipt"><div><span>Search engines</span><strong>{result.receipt.engines.length ? result.receipt.engines.map(engine => engine === 'google' ? 'SerpApi · Google' : engine === 'bing' ? 'SerpApi · Bing' : engine).join(' + ') : 'Offline fixture'}</strong></div><div><span>API calls this request</span><strong>{result.receipt.api_calls}</strong></div><div><span>Cached searches reused</span><strong>{result.receipt.cache_hits}</strong></div><div><span>App allowance left</span><strong>{result.receipt.budget_remaining} <small>/ {result.receipt.budget_limit}</small></strong></div><p>App allowance is a local guardrail. It does not report your account’s remaining SerpApi searches.</p></div>}
    <div className="results-controls"><div className="view-switch" aria-label="Result view"><button type="button" aria-pressed={view === 'sources'} onClick={() => setView('sources')}>Ranked sources</button><button type="button" aria-pressed={view === 'comparison'} onClick={() => setView('comparison')}>Version comparison</button></div><div className="export-actions" aria-label="Export evidence report"><button className="button-quiet" type="button" onClick={() => download('markdown')}>Export .md ↓</button><button className="button-quiet" type="button" onClick={() => download('json')}>Export .json ↓</button></div></div>{exportError && <p className="notice" role="alert">{exportError}</p>}
    {view === 'sources' && <div className="result-filters"><label className="field-label">Verdict<select aria-label="Filter verdicts" value={filter} onChange={event => setFilter(event.target.value as Verdict | 'ALL')}><option value="ALL">All verdicts</option>{Object.entries(verdictNames).map(([label, name]) => <option key={label} value={label}>{name}</option>)}</select></label><label className="field-label">Find in results<input aria-label="Find in results" value={textFilter} onChange={event => setTextFilter(event.target.value)} placeholder="Source, API or explanation…" /></label><span>Evidence reports include the complete result set.</span></div>}
    {!result.candidate_count ? <p className="empty-message">No search candidates were returned. Try a more specific API or error message.</p> : view === 'comparison' ? <Comparison result={result} /> : <div className={`result-columns ${result.results.length === 1 ? 'single' : ''}`}>{result.results.map((group, index) => <section key={`${group.profile.name}-${index}`}><ProfileSummary group={group} letter={index ? 'B' : 'A'} />{group.cards.map((card, cardIndex) => include(card) ? <ResultCard key={cardKey(card)} card={card} index={cardIndex} onWitness={onWitness} /> : null)}{!group.cards.some(include) && <p className="empty-message">No sources match these filters.</p>}</section>)}</div>}
    <details className="planned-queries"><summary>Inspect planned search queries <span>{result.queries.length}</span></summary><ol>{result.queries.map((query, index) => <li key={index}><code>{query}</code></li>)}</ol><p>Queries describe the retrieval plan. Consult the request receipt for actual API calls and cache reuse.</p></details>
  </section>
}
