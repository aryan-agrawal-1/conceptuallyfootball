import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSearchEntities } from '../lib/api'
import { useScope, type Scope } from '../context/ScopeContext'
import { preferredMembership, scopeIncludesMembership } from '../lib/scopeMembership'
import type {
  PlayerRow,
  SearchEntitiesResponse,
  SearchPlayerEntity,
  SearchPlayerMembership,
  SearchTeamEntity,
  SearchTeamMembership,
} from '../types/api'

const STALE_MS = 30 * 60 * 1000

export type SearchTeamRow = {
  canonical_team_id: number
  canonical_team_name: string
  totalMinutes?: number
}

function membershipForScope<T extends { competition: string; season: string }>(
  memberships: T[],
  scope: Scope,
): T | undefined {
  return memberships.find(m => scopeIncludesMembership(scope, m))
}

function toPlayerRow(entity: SearchPlayerEntity, membership: SearchPlayerMembership): PlayerRow {
  return {
    canonical_player_id: entity.canonical_player_id,
    canonical_player_name: entity.canonical_player_name,
    canonical_team_id: membership.canonical_team_id,
    canonical_team_name: membership.canonical_team_name,
    competition_season: membership.competition_season_id,
    competition_code: membership.competition,
    season_label: membership.season,
    position_group: membership.position_group,
    native_position: null,
    minutes: membership.minutes,
    formula_version: '',
    derived_run_id: null,
    eligibility: {
      percentiles_eligible: true,
      percentiles_ineligibility_reason: null,
      scores_eligible: true,
      scores_ineligibility_reason: null,
    },
    metrics: {},
    percentiles: {},
    scores: {},
    score_raw: {},
  }
}

export function resolveEntityScope(
  memberships: Array<SearchPlayerMembership | SearchTeamMembership>,
  scope: Scope,
): Scope | null {
  const match = preferredMembership(memberships, scope)
  return match ? { competition: match.competition, season: match.season } : null
}

export function resolveEntityMembership<T extends { competition: string; season: string }>(
  memberships: T[],
  scope: Scope,
): T | undefined {
  return preferredMembership(memberships, scope)
}

export function useSearchPaletteIndex(enabled: boolean) {
  const { scope } = useScope()
  const query = useQuery<SearchEntitiesResponse, Error>({
    queryKey: ['search-entities'],
    queryFn: fetchSearchEntities,
    staleTime: STALE_MS,
    enabled,
  })

  const playersSorted = useMemo(() => {
    return (query.data?.players ?? [])
      .map(entity => {
        const membership = membershipForScope(entity.memberships, scope)
        return membership ? toPlayerRow(entity, membership) : null
      })
      .filter((row): row is PlayerRow => row != null)
      .sort((a, b) => b.minutes - a.minutes)
  }, [query.data?.players, scope])

  const teamsSorted = useMemo((): SearchTeamRow[] => {
    return (query.data?.teams ?? [])
      .filter(entity => membershipForScope(entity.memberships, scope))
      .map(entity => ({
        canonical_team_id: entity.canonical_team_id,
        canonical_team_name: entity.canonical_team_name,
      }))
      .sort((a, b) => a.canonical_team_name.localeCompare(b.canonical_team_name))
  }, [query.data?.teams, scope])

  return {
    playersSorted,
    teamsSorted,
    globalPlayers: query.data?.players ?? [],
    globalTeams: query.data?.teams ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
  }
}

export type { SearchPlayerEntity, SearchTeamEntity }
