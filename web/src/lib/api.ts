import type {
  CompetitionSeasonsCatalogResponse,
  GalaxyResponse,
  GalaxySimilarResponse,
  MatrixFilters,
  MatrixResponse,
  PlayerDetailResponse,
  RegressionLabFitResponse,
  SearchEntitiesResponse,
  TeamDetailResponse,
  TeamMatrixResponse,
  TeamSquadResponse,
} from '../types/api'

const BASE = '/api/v1'

/**
 * Fetches ALL player rows for a competition + season.
 * All subsequent filtering (team, position, min_minutes) and sorting happen
 * client-side so nothing triggers another network request.
 */
export async function fetchStatMatrix(
  competition: string,
  season: string,
  include?: string,
): Promise<MatrixResponse> {
  const p = new URLSearchParams()
  p.set('competition', competition)
  p.set('season', season)
  if (include) p.set('include', include)
  const res = await fetch(`${BASE}/player-seasons/derived-stats?${p}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

/** Goalkeeper-only matrix (Sofascore shot stopping + distribution). */
export async function fetchGkStatMatrix(
  competition: string,
  season: string,
  include?: string,
): Promise<MatrixResponse> {
  const p = new URLSearchParams()
  p.set('competition', competition)
  p.set('season', season)
  if (include) p.set('include', include)
  const res = await fetch(`${BASE}/player-seasons/gk-derived-stats?${p}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

/**
 * Single player season row for the Player Profile page (and any deep-dive views).
 * Use this instead of reusing the stat-matrix list response so the backend can
 * attach richer payload (sections, future profile-only metrics) without bloating
 * the matrix endpoint.
 */
export async function fetchPlayerDetail(
  playerId: number,
  filters: Pick<MatrixFilters, 'competition' | 'season'> & { include?: string; percentile_scope?: string },
): Promise<PlayerDetailResponse> {
  const p = new URLSearchParams()
  p.set('competition', filters.competition)
  p.set('season', filters.season)
  if (filters.include) p.set('include', filters.include)
  if (filters.percentile_scope) p.set('percentile_scope', filters.percentile_scope)
  const q = p.toString()
  const outfieldUrl = `${BASE}/player-seasons/derived-stats/${playerId}?${q}`
  // Detail payloads can carry scope percentiles. Force HTTP-cache revalidation so
  // the browser cannot hand comparisons/profile an older response first.
  const res = await fetch(outfieldUrl, { cache: 'no-cache' })
  if (res.ok) {
    return res.json()
  }
  if (res.status === 404) {
    const gkUrl = `${BASE}/player-seasons/gk-derived-stats/${playerId}?${q}`
    const gkRes = await fetch(gkUrl, { cache: 'no-cache' })
    if (gkRes.ok) {
      return gkRes.json()
    }
    const body = await gkRes.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${gkRes.status}`)
  }
  const body = await res.json().catch(() => ({}))
  throw new Error(body.detail ?? `API error ${res.status}`)
}

export async function fetchTeamDetail(
  canonicalTeamId: number,
  filters: Pick<MatrixFilters, 'competition' | 'season'> & { include?: string },
): Promise<TeamDetailResponse> {
  const p = new URLSearchParams()
  p.set('competition', filters.competition)
  p.set('season', filters.season)
  if (filters.include) p.set('include', filters.include)
  const res = await fetch(
    `${BASE}/team-seasons/stats/${canonicalTeamId}?${p.toString()}`,
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export async function fetchTeamStatMatrix(
  filters: Pick<MatrixFilters, 'competition' | 'season'> & { include?: string },
): Promise<TeamMatrixResponse> {
  const p = new URLSearchParams()
  p.set('competition', filters.competition)
  p.set('season', filters.season)
  if (filters.include) p.set('include', filters.include)
  const res = await fetch(`${BASE}/team-seasons/stats?${p.toString()}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export async function fetchTeamSquad(
  canonicalTeamId: number,
  filters: Pick<MatrixFilters, 'competition' | 'season'>,
): Promise<TeamSquadResponse> {
  const p = new URLSearchParams()
  p.set('competition', filters.competition)
  p.set('season', filters.season)
  const res = await fetch(
    `${BASE}/team-seasons/squad/${canonicalTeamId}?${p.toString()}`,
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export interface GalaxyFilters {
  competition: string
  season: string
  position_group?: string | string[]
  team?: string | string[]
  min_minutes: number
}

export async function fetchGalaxy(filters: GalaxyFilters): Promise<GalaxyResponse> {
  const p = new URLSearchParams()
  p.set('competition', filters.competition)
  p.set('season', filters.season)
  p.set('min_minutes', String(filters.min_minutes))
  appendFilterValues(p, 'position_group', filters.position_group)
  appendFilterValues(p, 'team', filters.team)
  const res = await fetch(`${BASE}/galaxy?${p}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

function appendFilterValues(p: URLSearchParams, key: string, value?: string | string[]) {
  if (!value) return
  const values = Array.isArray(value) ? value : [value]
  for (const entry of values) {
    if (entry) p.append(key, entry)
  }
}

export async function fetchGalaxySimilar(
  galaxyPlayerId: string,
  competition: string,
  season: string,
): Promise<GalaxySimilarResponse> {
  const p = new URLSearchParams()
  p.set('competition', competition)
  p.set('season', season)
  p.set('galaxy_player_id', galaxyPlayerId)
  const res = await fetch(`${BASE}/galaxy/similar?${p}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export interface RegressionLabFitRequest {
  competition: string
  season: string
  position_group: string
  canonical_player_ids: number[]
  target_key: string
  predictor_keys: string[]
}

export async function fetchRegressionLabFit(
  body: RegressionLabFitRequest,
): Promise<RegressionLabFitResponse> {
  const res = await fetch(`${BASE}/labs/regression/fit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}))
    throw new Error(errBody.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export async function fetchCompetitionSeasonsCatalog(): Promise<CompetitionSeasonsCatalogResponse> {
  const res = await fetch(`${BASE}/competition-seasons`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}

export async function fetchSearchEntities(): Promise<SearchEntitiesResponse> {
  const res = await fetch(`${BASE}/search/entities`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${res.status}`)
  }
  return res.json()
}
