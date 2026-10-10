import type { SearchResult } from './types'
function safeLink(url: string) { try { const parsed = new URL(url); return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href.replace(/[()]/g, character => encodeURIComponent(character)) : '' } catch { return '' } }
function text(value: string) { return value.replace(/[\\`*_\[\]<>#|]/g, character => `\\${character}`).replace(/\r?\n/g, ' ') }
export function exportReport(result: SearchResult, query: string, technology: string, format: 'json' | 'markdown') {
  const generatedAt = new Date().toISOString()
  const report = { product: 'VersionVerdict', generated_at: generatedAt, technology, query, version_policy: 'Versions are declared context; rankings are not factual confidence scores.', ...result }
  let content = JSON.stringify(report, null, 2)
  if (format === 'markdown') {
    const lines = ['# VersionVerdict evidence report', '', `Generated: ${generatedAt}`, `Technology: ${text(technology)}`, `Question: ${text(query)}`, `Retrieval mode: ${text(result.mode)}`, '', 'Versions describe declared context. Rank is not a confidence percentage. Inspect source evidence before applying advice.', '']
    if (result.receipt) lines.push(`SerpApi calls: ${result.receipt.api_calls}; cache hits: ${result.receipt.cache_hits}; local allowance left: ${result.receipt.budget_remaining}/${result.receipt.budget_limit}.`, '')
    for (const warning of result.warnings) lines.push(`Warning: ${text(warning)}`, '')
    for (const group of result.results) {
      lines.push(`## ${text(group.profile.name)}`, '', `Context: ${[group.profile.technology, group.profile.language, group.profile.platform, group.profile.hardware].filter(Boolean).map(value => text(value!)).join(' / ')}`, '')
      for (const dependency of group.profile.dependencies) lines.push(`- ${text(dependency.name)}: ${text(dependency.exact || dependency.constraint || 'unknown')} (${dependency.exact ? 'declared pin' : 'unresolved version'})`)
      lines.push('')
      if (group.profile.notes) lines.push(`Notes: ${text(group.profile.notes)}`, '')
      for (const warning of group.profile.warnings) lines.push(`Warning: ${text(warning)}`, '')
      group.cards.forEach((card, index) => {
        lines.push(`### ${index + 1}. ${text(card.hit.title)}`, '', `Verdict: **${card.label}**`, `Source: ${safeLink(card.hit.url)}`, '', text(card.explanation), '')
        if (card.ranking_reasons?.length) {
          lines.push('Ranking signals (metadata only; not compatibility evidence):')
          for (const reason of card.ranking_reasons) lines.push(`- ${text(reason)}`)
          lines.push('')
        }
        if (card.recipe) lines.push(`API / recipe: ${text(card.recipe)}`, '')
        if (card.boundary) lines.push(`Version boundary: ${text(card.boundary)}`, '')
        for (const condition of card.preconditions || []) lines.push(`- Condition: ${text(condition)}`)
        for (const evidence of card.evidence) {
          lines.push('', `Evidence: ${safeLink(evidence.url)}`, `Type: ${text(evidence.source_kind)}; provenance: ${text(evidence.provenance || 'unspecified')}`, '')
          lines.push(...evidence.quote.split(/\r?\n/).map(line => `> ${text(line)}`), '')
          if (evidence.section) lines.push(`Section: ${text(evidence.section)}`)
          if (evidence.content_hash) lines.push(`Content hash: ${text(evidence.content_hash)}`)
          if (evidence.fetched_at) lines.push(`Fetched at: ${text(evidence.fetched_at)}`)
        }
        if (!card.evidence.length) lines.push('No sufficient source evidence was available.', '')
        for (const entry of card.hit.provenance || []) lines.push(`Search provenance: SerpApi ${text(entry.engine)}; query: ${text(entry.query)}; position: ${entry.position}; retrieval: ${text(entry.retrieval || 'unspecified')}`)
        if (card.rule_id) lines.push(`Rule: ${text(card.rule_id)}`)
        if (card.witness_id) lines.push(`Reviewed witness: ${text(card.witness_id)}`)
        lines.push('')
      })
    }
    lines.push('## Search plan', '', ...result.queries.map(query => `- ${text(query)}`))
    content = lines.join('\n')
  }
  const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `versionverdict-${technology.replace(/[^a-z0-9_-]/gi, '-').slice(0, 48) || 'evidence'}-${generatedAt.slice(0, 10)}.${format === 'json' ? 'json' : 'md'}`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
