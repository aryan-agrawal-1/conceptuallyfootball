import type { ProfileRateMode } from './profileMetrics'

export interface ScopedPlayerRef {
  id: number
  competition: string
  season: string
}

export function scopedPlayerToken(ref: ScopedPlayerRef): string {
  return `${ref.competition}:${ref.season}:${ref.id}`
}

export function playerRowToScopedRef(row: {
  canonical_player_id: number
  competition_code: string
  season_label: string
}): ScopedPlayerRef {
  return {
    id: row.canonical_player_id,
    competition: row.competition_code,
    season: row.season_label,
  }
}

export function parsePlayerRefsParam(raw: string | null): ScopedPlayerRef[] {
  if (!raw?.trim()) return []
  const seen = new Set<string>()
  const out: ScopedPlayerRef[] = []
  for (const part of raw.split(',')) {
    const bits = part.trim().split(':')
    if (bits.length !== 3) continue
    const [competition, season, rawId] = bits
    const id = Number(rawId)
    if (!competition || !season || !Number.isFinite(id) || id <= 0) continue
    const ref = { competition, season, id }
    const token = scopedPlayerToken(ref)
    if (seen.has(token)) continue
    seen.add(token)
    out.push(ref)
    if (out.length >= 3) break
  }
  return out
}

export function parseStatsParam(raw: string | null): string[] | null {
  if (!raw?.trim()) return null
  const keys = raw.split(',').flatMap(s => {
    const key = s.trim()
    return key ? [key] : []
  })
  return keys.length ? keys : null
}

export function parseRateModeParam(raw: string | null): ProfileRateMode {
  return raw === 'full' ? 'full' : 'per90'
}
