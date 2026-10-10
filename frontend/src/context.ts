import type { Context } from './types'
import { supportedManifests } from './types'
export function initialContext(name: string): Context {
  return { name, file: null, extra: null, apiMode: 'unknown', future: 'unknown', inputMode: 'manual', version: '', language: '', platform: '', hardware: '', dependencies: '', notes: '' }
}
export function contextFiles(context: Context, technology: string): [File, File | null] {
  if (context.inputMode === 'file') {
    if (!context.file) throw new Error(`Choose a manifest for ${context.name || 'this environment'}, or switch to manual context.`)
    const files = [context.file, context.extra].filter((file): file is File => Boolean(file))
    if (files.some(file => !supportedManifests.includes(file.name))) throw new Error(`Supported manifests: ${supportedManifests.join(', ')}.`)
    if (files.reduce((total, file) => total + file.size, 0) > 256 * 1024) throw new Error('Manifest files must total 256 KB or less per environment.')
    return [context.file, context.extra]
  }
  const dependencies: { name: string; version?: string; constraint?: string }[] = []
  const addDependency = (name: string, value: string) => {
    if (!name.trim()) throw new Error('Each dependency needs a name.')
    if (!value.trim() || /^(unknown|unspecified|latest)$/i.test(value.trim())) dependencies.push({ name: name.trim() })
    else if (!/^(?:[<>=!~^]|https?:|git[+:]|file:|workspace:)|[*,|\s]/.test(value.trim())) dependencies.push({ name: name.trim(), version: value.trim() })
    else dependencies.push({ name: name.trim(), constraint: value.trim() })
  }
  addDependency(technology, context.version)
  for (const line of context.dependencies.split(/\r?\n/).filter(line => line.trim())) {
    const parts = line.trim().match(/^(@[\w.-]+\/[\w.-]+|[^\s=<>!~^@]+)\s*(.*)$/)
    if (!parts) throw new Error(`Cannot read dependency line: ${line}. Use name=version or name>=version.`)
    const raw = parts[2].trim()
    addDependency(parts[1], raw.startsWith('==') ? raw.slice(2) : raw.startsWith('=') || raw.startsWith('@') ? raw.slice(1) : raw)
  }
  const content = { technology: technology.trim(), dependencies, ...(context.language.trim() && { language: context.language.trim() }), ...(context.platform.trim() && { platform: context.platform.trim() }), ...(context.hardware.trim() && { hardware: context.hardware.trim() }), ...(context.notes.trim() && { notes: context.notes.trim() }) }
  return [new File([JSON.stringify(content, null, 2)], 'environment.json', { type: 'application/json' }), null]
}
