import type { ProfileRateMode } from './profileMetrics'

export function parsePlayerIdsParam(raw: string | null): number[] {
  if (!raw?.trim()) return []
  const parts = raw.split(',').map(s => Number(s.trim()))
  const ids = parts.filter(n => Number.isFinite(n) && n > 0)
  const seen = new Set<number>()
  const out: number[] = []
  for (const id of ids) {
    if (seen.has(id)) continue
    seen.add(id)
    out.push(id)
    if (out.length >= 3) break
  }
  return out
}

export function parseStatsParam(raw: string | null): string[] | null {
  if (!raw?.trim()) return null
  const keys = raw
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
  return keys.length ? keys : null
}

export function parseRateModeParam(raw: string | null): ProfileRateMode {
  return raw === 'full' ? 'full' : 'per90'
}
