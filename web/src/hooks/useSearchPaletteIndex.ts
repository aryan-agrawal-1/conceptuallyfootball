import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchGkStatMatrix, fetchStatMatrix } from '../lib/api'
import { DEFAULT_FILTERS } from './useStatMatrix'
import type { MatrixResponse, PlayerRow } from '../types/api'

const STALE_MS = 10 * 60 * 1000

export type SearchTeamRow = {
  canonical_team_id: number
  canonical_team_name: string
  totalMinutes: number
}

function mergeSearchIndex(
  outfield: MatrixResponse | undefined,
  gk: MatrixResponse | undefined,
): { playersSorted: PlayerRow[]; teamsSorted: SearchTeamRow[] } {
  const playerMap = new Map<number, PlayerRow>()
  for (const row of outfield?.results ?? []) {
    const prev = playerMap.get(row.canonical_player_id)
    if (!prev || row.minutes > prev.minutes) {
      playerMap.set(row.canonical_player_id, row)
    }
  }
  for (const row of gk?.results ?? []) {
    const prev = playerMap.get(row.canonical_player_id)
    if (!prev || row.minutes > prev.minutes) {
      playerMap.set(row.canonical_player_id, row)
    }
  }

  const playersSorted = [...playerMap.values()].sort((a, b) => b.minutes - a.minutes)

  const teamTotals = new Map<number, SearchTeamRow>()
  for (const p of playerMap.values()) {
    if (p.canonical_team_id == null || !p.canonical_team_name) continue
    const id = p.canonical_team_id
    const cur = teamTotals.get(id)
    if (cur) {
      cur.totalMinutes += p.minutes
    } else {
      teamTotals.set(id, {
        canonical_team_id: id,
        canonical_team_name: p.canonical_team_name,
        totalMinutes: p.minutes,
      })
    }
  }

  const teamsSorted = [...teamTotals.values()].sort((a, b) => b.totalMinutes - a.totalMinutes)

  return { playersSorted, teamsSorted }
}

/**
 * Loads outfield + GK matrix rows for the default competition/season when `enabled`.
 * Reuses the same query keys as `useStatMatrix` so navigating from Matrix warms cache.
 */
export function useSearchPaletteIndex(enabled: boolean) {
  const { competition, season } = DEFAULT_FILTERS

  const outfieldQuery = useQuery({
    queryKey: ['stat-matrix', 'outfield', competition, season],
    queryFn: () => fetchStatMatrix(competition, season, 'meta'),
    staleTime: STALE_MS,
    enabled,
  })

  const gkQuery = useQuery({
    queryKey: ['stat-matrix', 'gk', competition, season],
    queryFn: () => fetchGkStatMatrix(competition, season, 'meta'),
    staleTime: STALE_MS,
    enabled,
  })

  const { playersSorted, teamsSorted } = useMemo(
    () => mergeSearchIndex(outfieldQuery.data, gkQuery.data),
    [outfieldQuery.data, gkQuery.data],
  )

  return {
    playersSorted,
    teamsSorted,
    isLoading: outfieldQuery.isLoading || gkQuery.isLoading,
    isError: outfieldQuery.isError || gkQuery.isError,
    error: outfieldQuery.error ?? gkQuery.error,
  }
}
