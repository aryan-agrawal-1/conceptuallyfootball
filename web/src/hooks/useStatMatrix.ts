import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { fetchGkStatMatrix, fetchStatMatrix } from '../lib/api'
import type { MatrixFilters, MatrixResponse, PlayerRow } from '../types/api'

export const DEFAULT_FILTERS: MatrixFilters = {
  competition: 'ENG1',
  season: '2025-26',
  min_minutes: 900,
}

/**
 * Fetches all rows for a competition+season once and caches them.
 * queryKey only contains competition+season — team/position/min_minutes
 * are all handled client-side so changing them never triggers a fetch.
 */
export function useStatMatrix(filters: MatrixFilters) {
  const isGk = filters.position_group === 'GK'
  return useQuery<MatrixResponse, Error>({
    queryKey: ['stat-matrix', isGk ? 'gk' : 'outfield', filters.competition, filters.season],
    queryFn: () =>
      isGk
        ? fetchGkStatMatrix(filters.competition, filters.season, 'meta')
        : fetchStatMatrix(filters.competition, filters.season, 'meta'),
    staleTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
  })
}

/**
 * Pure client-side filter applied over the full cached dataset.
 * O(n) per keystroke, zero network.
 */
export function applyClientFilters(
  rows: PlayerRow[],
  filters: Pick<MatrixFilters, 'teams' | 'position_group' | 'min_minutes'>,
): PlayerRow[] {
  const teamsSet = filters.teams?.length ? new Set(filters.teams) : null
  return rows.filter(p => {
    if (filters.min_minutes > 0 && p.minutes < filters.min_minutes) return false
    if (filters.position_group && p.position_group !== filters.position_group) return false
    if (teamsSet && !teamsSet.has(p.canonical_team_name ?? '')) return false
    return true
  })
}
