import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Arrow, ContextPanel, Results, VerdictBadge } from './components'
import type { Capabilities, Context, Library, SearchResult } from './types'
import { demoFiles, prompts } from './types'

function initialContext(name: string): Context { return { name, file: null, extra: null, apiMode: 'unknown', future: 'unknown' } }
function responseError(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => typeof item?.msg === 'string' ? item.msg : fallback).join('; ')
  return fallback
}
async function readResponse(response: Response) {
  let body
  try { body = await response.json() } catch { throw new Error(`The backend returned an unreadable response (${response.status}). Check that the API is running.`) }
  if (!response.ok) throw new Error(responseError(body.detail, `Request failed (${response.status}).`))
  return body
}
function validateContext(context: Context, required: boolean) {
  if (!context.file && required) throw new Error(`Choose a dependency manifest for ${context.name || 'this project'}, or try an illustrative demo.`)
  if (context.extra && !context.file) throw new Error('A second manifest needs a primary manifest for the same project.')
  const files = [context.file, context.extra].filter((file): file is File => Boolean(file))
  if (files.some(file => !['requirements.txt', 'pyproject.toml'].includes(file.name))) throw new Error('Supported filenames are requirements.txt and pyproject.toml.')
  if (files.reduce((total, file) => total + file.size, 0) > 256 * 1024) throw new Error('Manifest files must total 256 KB or less per project.')
}

export default function App() {
  const [library, setLibrary] = useState<Library>('pydantic')
  const [query, setQuery] = useState(prompts.pydantic)
  const [left, setLeft] = useState<Context>(initialContext('Project A'))
  const [right, setRight] = useState<Context>(initialContext('Project B'))
  const [compare, setCompare] = useState(true)
  const [secondary, setSecondary] = useState(false)
  const [refresh, setRefresh] = useState(false)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [connectionError, setConnectionError] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingMode, setPendingMode] = useState<'live' | 'recorded'>('live')
  const [error, setError] = useState('')
  const [artifact, setArtifact] = useState<{ title: string; body: unknown } | null>(null)
  const [artifactLoading, setArtifactLoading] = useState(false)
  const request = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const workspace = useRef<HTMLElement | null>(null)
  const artifactDialog = useRef<HTMLDialogElement | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/capabilities', { signal: controller.signal }).then(readResponse).then(setCapabilities).catch(cause => {
      if (!controller.signal.aborted) setConnectionError(cause instanceof Error ? cause.message : 'The API could not be reached.')
    })
    return () => { controller.abort(); request.current?.abort() }
  }, [])
  useEffect(() => {
    function focusQuery(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && !target?.closest('input, textarea, select, [contenteditable="true"], dialog')) {
        event.preventDefault()
        document.getElementById('query')?.focus()
      }
    }
    window.addEventListener('keydown', focusQuery)
    return () => window.removeEventListener('keydown', focusQuery)
  }, [])
  useEffect(() => {
    if (artifact && artifactDialog.current && !artifactDialog.current.open) artifactDialog.current.showModal()
  }, [artifact])

  function resetResults() {
    generation.current += 1
    request.current?.abort()
    setLoading(false)
    setResult(null)
    setError('')
  }
  function changeLibrary(value: Library) {
    resetResults()
    setLibrary(value)
    setQuery(prompts[value])
    setLeft(initialContext('Project A'))
    setRight(initialContext('Project B'))
  }

  async function search(mode: 'live' | 'recorded', selectedLeft = left, selectedRight = right, selectedLibrary = library, selectedQuery = query, comparing = compare) {
    const current = ++generation.current
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setError('')
    try {
      validateContext(selectedLeft, true)
      if (comparing) validateContext(selectedRight, true)
      if (selectedQuery.trim().length < 3) throw new Error('Enter a question with at least three characters.')
      setLoading(true)
      setPendingMode(mode)
      setResult(null)
      const body = new FormData()
      body.set('query', selectedQuery.trim())
      body.set('library', selectedLibrary)
      body.set('mode', mode)
      body.set('left_name', selectedLeft.name.trim() || 'Project A')
      body.set('left_file', selectedLeft.file!)
      body.set('left_pydantic_api_mode', selectedLeft.apiMode)
      body.set('left_sqlalchemy_future', selectedLeft.future)
      if (selectedLeft.extra) body.set('left_extra_file', selectedLeft.extra)
      if (comparing && selectedRight.file) {
        body.set('right_name', selectedRight.name.trim() || 'Project B')
        body.set('right_file', selectedRight.file)
        body.set('right_pydantic_api_mode', selectedRight.apiMode)
        body.set('right_sqlalchemy_future', selectedRight.future)
        if (selectedRight.extra) body.set('right_extra_file', selectedRight.extra)
      }
      body.set('include_secondary', String(mode === 'live' && secondary))
      body.set('refresh', String(mode === 'live' && refresh))
      const data: SearchResult = await fetch('/api/search', { method: 'POST', body, signal: controller.signal }).then(readResponse)
      if (current !== generation.current) return
      setResult(data)
      if (data.receipt) setCapabilities(previous => previous ? { ...previous, budget: { limit: data.receipt!.budget_limit, used: data.receipt!.budget_used, remaining: data.receipt!.budget_remaining } } : previous)
      window.setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 70)
    } catch (cause) {
      if (current === generation.current && !(cause instanceof DOMException && cause.name === 'AbortError')) {
        setError(cause instanceof Error ? cause.message : 'Search failed. Please try again.')
        void fetch('/api/capabilities', { signal: controller.signal }).then(readResponse).then(data => { if (current === generation.current) setCapabilities(data) }).catch(() => {})
      }
    } finally { if (current === generation.current) setLoading(false) }
  }

  async function demo(selectedLibrary: Library = library) {
    resetResults()
    const current = generation.current
    setLoading(true)
    setPendingMode('recorded')
    try {
      const files = await Promise.all(demoFiles[selectedLibrary].map(async filename => {
        const response = await fetch(`/fixtures/${filename}`)
        if (!response.ok) throw new Error('The bundled demo manifests are unavailable.')
        return new File([await response.text()], 'requirements.txt', { type: 'text/plain' })
      }))
      if (current !== generation.current) return
      const profiles: [Context, Context] = selectedLibrary === 'pydantic'
        ? [{ name: 'Pydantic 1.10', file: files[0], extra: null, apiMode: 'native', future: 'unknown' }, { name: 'Pydantic 2.9', file: files[1], extra: null, apiMode: 'native', future: 'unknown' }]
        : [{ name: 'SQLAlchemy 1.4', file: files[0], extra: null, apiMode: 'unknown', future: 'false' }, { name: 'SQLAlchemy 2.0', file: files[1], extra: null, apiMode: 'unknown', future: 'unknown' }]
      setLibrary(selectedLibrary)
      setLeft(profiles[0])
      setRight(profiles[1])
      setCompare(true)
      setQuery(prompts[selectedLibrary])
      workspace.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      await search('recorded', profiles[0], profiles[1], selectedLibrary, prompts[selectedLibrary], true)
    } catch (cause) {
      if (current === generation.current) { setError(cause instanceof Error ? cause.message : 'Demo could not be loaded.'); setLoading(false) }
    }
  }

  async function inspectArtifact(kind: 'witnesses' | 'evaluation', selectedId?: string) {
    setArtifactLoading(true)
    setError('')
    try {
      const body = await fetch(`/api/${kind}`).then(readResponse)
      const selectedCase = kind === 'witnesses' && selectedId && Array.isArray(body.cases) ? body.cases.find((item: { id: string }) => item.id === selectedId) : null
      setArtifact({ title: kind === 'witnesses' ? `Reviewed recipe witnesses${selectedId ? ` · ${selectedId}` : ''}` : 'Reproducible evaluation', body: selectedCase ? { scope: body.scope, checked_at: body.checked_at, case: selectedCase } : body })
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The verification artifact could not be loaded.') }
    finally { setArtifactLoading(false) }
  }
  function submit(event: FormEvent) { event.preventDefault(); void search('live') }
  const selectedWitnessStatus = artifact?.body && typeof artifact.body === 'object' && 'case' in artifact.body ? (artifact.body as { case?: { status?: string } }).case?.status : null
  const liveUnavailable = !capabilities?.live_search_configured
  const bingAvailable = !capabilities || capabilities.engines.some(engine => engine.id === 'bing')

  return <>
    <a className="skip-link" href="#workspace">Skip to the search workspace</a>
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="VersionVerdict home"><span className="brand-mark" aria-hidden="true">&gt;_</span><span>version<span className="brand-accent">verdict</span><small>The right answer for your version.</small></span></a>
        <nav aria-label="Main navigation"><a href="#workspace">/ workspace</a><a href="#evidence">/ evidence</a><a href="https://github.com/Ananay28425/VersionVerdict" target="_blank" rel="noopener noreferrer" className="repository-link">GitHub <Arrow diagonal /></a></nav>
      </header>
      <div className="session-bar"><span><span className={`status-light ${connectionError ? 'error' : capabilities ? 'ready' : 'pending'}`} aria-hidden="true" />{connectionError ? 'API disconnected' : capabilities ? capabilities.live_search_configured ? 'API connected · live search ready' : 'API connected · demo ready' : 'Connecting to API…'}</span><span className="session-provider">search provider: <strong>SerpApi only</strong></span><span className="session-shortcut"><kbd>/</kbd> focus query</span></div>
      <main id="top">
        <section className="hero">
          <div className="hero-copy"><p className="eyebrow"><span aria-hidden="true">//</span> VERSION-AWARE DEVELOPER SEARCH</p><h1>The right answer<br />for <em>your version.</em><span className="terminal-cursor" aria-hidden="true">_</span></h1><p className="hero-description">Your dependencies are part of the question. Search technical sources, compare environments, and trace each verdict to its evidence.</p><div className="hero-actions"><button className="button-primary" type="button" disabled={loading || !capabilities} onClick={() => void demo('pydantic')}>Try the version comparison <Arrow /></button><a className="button-secondary" href="#workspace">Open workspace <Arrow /></a></div><p className="hero-footnote">requirements.txt · pyproject.toml · deterministic rules</p></div>
          <div className="hero-example" aria-label="Illustrative example of different Pydantic verdicts">
            <div className="example-toolbar"><div className="terminal-dots" aria-hidden="true"><i /><i /><i /></div><span>version_check.py</span><span className="example-label">ILLUSTRATIVE</span></div>
            <div className="example-query"><p className="terminal-comment"># Same question. Two environments.</p><p><span className="syntax-keyword">from</span> pydantic <span className="syntax-keyword">import</span> BaseModel</p><p><span className="syntax-keyword">class</span> <span className="syntax-type">Model</span>(BaseModel):<br /><span className="code-indent">value: <span className="syntax-type">int</span></span></p><code>Model.<span className="syntax-function">model_validate</span>({'{'}<span className="syntax-string">'value'</span>: 1{'}'})</code></div>
            <div className="example-environments"><div><span className="example-context">ENV A / pydantic==1.10.15</span><VerdictBadge label="WRONG_VERSION" /><p>model_validate() is unavailable.</p></div><div><span className="example-context">ENV B / pydantic==2.9.2</span><VerdictBadge label="COMPATIBLE" /><p>Native V2 validation API.</p></div></div><div className="example-proof"><span aria-hidden="true">↳</span> Native API · reviewed migration boundary</div>
          </div>
        </section>
        <section id="how-it-works" className="workflow" aria-label="How VersionVerdict works"><div><span className="step-number">01</span><div><h2>profile_environment</h2><p>Declared pins, ranges & unknowns</p></div></div><div><span className="step-number">02</span><div><h2>retrieve_evidence</h2><p>SerpApi discovery & source inspection</p></div></div><div><span className="step-number">03</span><div><h2>compare_applicability</h2><p>Same sources. Version-specific verdicts.</p></div></div></section>
        <section className="workspace-section" id="workspace" ref={workspace}>
          <div className="section-heading"><div><span className="eyebrow">01 / WORKSPACE</span><h2>Set the context. Run the search.</h2></div><span className="scope-pill">PYTHON / PYDANTIC + SQLALCHEMY</span></div>
          <form className="workspace" onSubmit={submit}>
            <div className="panel-titlebar"><span><span className="terminal-prompt" aria-hidden="true">&gt;_</span> ~/versionverdict/workspace</span><span>MANIFESTS ONLY · NO CODE EXECUTION</span></div>
            <fieldset disabled={loading}>
              <div className="workspace-top"><label className="field-label library-field">Library<select aria-label="Library" value={library} onChange={event => changeLibrary(event.target.value as Library)}><option value="pydantic">Pydantic</option><option value="sqlalchemy">SQLAlchemy</option></select></label><label className="toggle-label"><input type="checkbox" checked={compare} onChange={event => { resetResults(); setCompare(event.target.checked) }} /><span>Compare two environments<small>One shared pool of sources</small></span></label><div className="demo-shortcuts"><span>LOAD A FIXTURE</span><button type="button" disabled={!capabilities} onClick={() => void demo(library)}>Try {library === 'pydantic' ? 'Pydantic' : 'SQLAlchemy'} demo <Arrow /></button></div></div>
              <div className={`context-grid ${compare ? '' : 'single'}`}><ContextPanel letter="A" value={left} library={library} onChange={value => { resetResults(); setLeft(value) }} />{compare && <ContextPanel letter="B" value={right} library={library} onChange={value => { resetResults(); setRight(value) }} />}</div>
              <div className="question-field"><div className="query-label"><label className="field-label" htmlFor="query">QUESTION / ERROR</label><span><kbd>Ctrl</kbd> + <kbd>Enter</kbd> live search</span></div><div className="command-input"><span className="terminal-prompt" aria-hidden="true">$</span><textarea id="query" value={query} onChange={event => { resetResults(); setQuery(event.target.value) }} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); if (!liveUnavailable && !loading) event.currentTarget.form?.requestSubmit() } }} minLength={3} maxLength={240} rows={2} required placeholder="Paste an error or ask about a version-sensitive API…" /></div><p>Checks cover model validation and SQL execution recipes. Unknown context remains uncertain.</p></div>
              <details className="retrieval-options"><summary>Search engines & request controls<span>SerpApi / Google{secondary ? ' + Bing' : ''}</span></summary><div className="engine-settings"><div className="engine-always"><span className="engine-check" aria-hidden="true">✓</span><span><strong>SerpApi · Google Search</strong><small>Primary engine · targeted official-documentation queries</small></span></div>{bingAvailable && <label className="check-option"><input type="checkbox" checked={secondary} onChange={event => { resetResults(); setSecondary(event.target.checked) }} /><span><strong>Add SerpApi · Bing Search</strong><small>One additional discovery query through SerpApi. Uses the same evidence rules.</small></span></label>}<label className="check-option"><input type="checkbox" checked={refresh} onChange={event => { resetResults(); setRefresh(event.target.checked) }} /><span><strong>Refresh instead of reusing the app cache</strong><small>May spend new API calls. Changing only the environment does not require a refresh.</small></span></label><p className="allowance-description">{capabilities ? `${capabilities.budget.remaining} of ${capabilities.budget.limit} calls remain in this app’s local allowance.` : 'A server-side app allowance protects shared search usage.'} This is separate from your SerpApi account balance.</p></div></details>
              <div className="workspace-actions"><button className="button-primary" type="submit" disabled={loading || liveUnavailable}>{loading ? pendingMode === 'recorded' ? 'Evaluating illustrative sources…' : 'Retrieving and checking sources…' : 'Run live search'}{loading ? <span className="spinner" aria-hidden="true" /> : <Arrow />}</button><button className="button-quiet" type="button" onClick={() => void demo(library)} disabled={loading || !capabilities}>Try illustrative demo</button><span>DEMO = 0 SEARCH CALLS</span></div>
            </fieldset>
            {capabilities?.live_search_configured === false && <p className="configuration-notice"><span className="notice-prefix">[CONFIG]</span> Live search is not configured on this server. Set <code>SERPAPI_KEY</code> on the backend to enable it; the illustrative demo remains available.</p>}
            {connectionError && <div className="connection-notice" role="alert"><strong>[API DISCONNECTED]</strong><p>{connectionError}</p><p>Start the combined service with <code>./scripts/start_preview.sh</code>. It serves this interface and the API together.</p><button className="text-link" type="button" onClick={() => window.location.reload()}>Retry connection <Arrow /></button></div>}
            {loading && <div className="loading-status" role="status"><span className="spinner" aria-hidden="true" /><p>{pendingMode === 'recorded' ? 'Evaluating bundled illustrative sources against both declared environments.' : 'Retrieving candidates through SerpApi and checking available source evidence.'}<small>{pendingMode === 'recorded' ? 'No live SerpApi request is made.' : 'Only completed responses appear below.'}</small></p><button type="button" className="text-link" onClick={resetResults}>Cancel</button></div>}
          </form>
        </section>
        {error && <div className="error-notice" role="alert"><strong>[REQUEST FAILED]</strong><p>{error}</p><button type="button" className="text-link" onClick={() => setError('')}>Dismiss</button></div>}
        {result && <Results key={`${result.mode}-${generation.current}`} result={result} onWitness={id => void inspectArtifact('witnesses', id)} />}
        <section className="trust-section" id="evidence"><div><span className="eyebrow">02 / EVIDENCE POLICY</span><h2>Every verdict has a trail.</h2><p>A missing source, unresolved version, or ambiguous API context stays uncertain. Inspect the code recipe, migration boundary, source fingerprint, and reproducible witness.</p><div className="artifact-actions"><button className="text-link" type="button" disabled={artifactLoading || !capabilities} onClick={() => void inspectArtifact('witnesses')}>Inspect recipe witnesses <Arrow /></button><button className="text-link" type="button" disabled={artifactLoading || !capabilities} onClick={() => void inspectArtifact('evaluation')}>Inspect evaluation <Arrow /></button></div></div><dl className="verdict-legend"><div><dt><VerdictBadge label="COMPATIBLE" /></dt><dd>Source evidence supports this recipe and context.</dd></div><div><dt><VerdictBadge label="WRONG_VERSION" /></dt><dd>A documented version or API boundary contradicts applicability.</dd></div><div><dt><VerdictBadge label="STALE" /></dt><dd>Documented deprecation or supersession applies.</dd></div><div><dt><VerdictBadge label="UNCERTAIN" /></dt><dd>Evidence cannot establish applicability.</dd></div></dl></section>
      </main>
      <footer className="site-footer"><span><span className="terminal-prompt" aria-hidden="true">&gt;_</span> VersionVerdict<span className="footer-tagline">The right answer for your version.</span></span><span>Search powered by <a href="https://serpapi.com/search-api" target="_blank" rel="noopener noreferrer">SerpApi <Arrow diagonal /></a><a href="https://github.com/Ananay28425/VersionVerdict" target="_blank" rel="noopener noreferrer">View source <Arrow diagonal /></a></span></footer>
      <div className="status-bar"><span><span className="status-light ready" aria-hidden="true" /> {result ? `${result.candidate_count} candidates / ${result.mode === 'recorded' ? 'illustrative' : result.mode}` : 'Awaiting query'}</span><span>{capabilities ? `local allowance ${capabilities.budget.remaining}/${capabilities.budget.limit}` : 'allowance unavailable'}<span className="status-divider">|</span> SerpApi only</span></div>
    </div>
    <dialog ref={artifactDialog} className="artifact-dialog" onClose={() => setArtifact(null)} onClick={event => { if (event.target === event.currentTarget) artifactDialog.current?.close() }}><div className="artifact-header"><div><span className="eyebrow">VERIFICATION ARTIFACT / JSON</span><h2>{artifact?.title}</h2></div><button type="button" onClick={() => artifactDialog.current?.close()} aria-label="Close verification artifact">×</button></div><p>{selectedWitnessStatus && <strong className={`artifact-status ${selectedWitnessStatus.toLowerCase()}`}>Recorded witness status: {selectedWitnessStatus}</strong>}Authored, reviewed test recipes. These records do not validate arbitrary uploaded code or every retrieved solution.</p><pre>{artifact ? JSON.stringify(artifact.body, null, 2) : ''}</pre></dialog>
  </>
}
