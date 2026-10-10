export const themes = [
  { id: 'pop', name: 'Pop art', description: 'Paper, yellow, coral & sky blue', colors: ['#FFD23F', '#FF6B6B', '#74B9FF', '#88D498', '#B8A9FA'] },
  { id: 'vibrant', name: 'Vibrant', description: 'Orange-red, cyan & lemon', colors: ['#FF4F00', '#00B3FF', '#FFEF00', '#6A0DAD'] },
  { id: 'industrial', name: 'Industrial', description: 'Concrete, charcoal & safety orange', colors: ['#7D7F7D', '#B5B5B5', '#FF3D00', '#00FFAE', '#1C1C1E'] },
  { id: 'retro', name: 'Retro', description: 'Mustard, mauve & muted teal', colors: ['#E5A93C', '#A39FA8', '#647345', '#3D7068'] },
] as const
export type Theme = typeof themes[number]['id']
export function savedTheme(): Theme {
  try { const value = localStorage.getItem('versionverdict.theme'); if (themes.some(theme => theme.id === value)) return value as Theme } catch { /* Storage may be disabled. */ }
  return 'pop'
}
export function ThemePicker({ value, onChange }: { value: Theme; onChange: (value: Theme) => void }) {
  return <details className="theme-picker"><summary><span className="theme-preview" aria-hidden="true">{themes.find(theme => theme.id === value)!.colors.slice(0, 3).map(color => <i key={color} style={{ background: color }} />)}</span><span>Theme / {themes.find(theme => theme.id === value)!.name}</span><span aria-hidden="true">⌄</span></summary><div className="theme-menu" role="group" aria-label="Color theme">{themes.map(theme => <button type="button" key={theme.id} aria-pressed={value === theme.id} onClick={() => onChange(theme.id)}><span className="theme-swatches" aria-hidden="true">{theme.colors.map(color => <i key={color} style={{ background: color }} />)}</span><span><strong>{theme.name}</strong><small>{theme.description}</small></span><span aria-hidden="true">{value === theme.id ? '✓' : ''}</span></button>)}</div></details>
}
