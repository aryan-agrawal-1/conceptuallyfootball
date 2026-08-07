import type { Scope } from '../context/ScopeContext'

export interface ProfileSliceMembership {
  competition: string
  competition_type?: 'domestic_league' | 'continental_cup'
  competition_season_id: number
  season: string
  aggregate_season?: string
}

export interface ProfileSlice {
  competition: string
  season: string
}

function compareCompetition<T extends ProfileSliceMembership>(a: T, b: T): number {
  const aDomestic = a.competition_type === 'domestic_league'
  const bDomestic = b.competition_type === 'domestic_league'
  if (aDomestic !== bDomestic) return aDomestic ? -1 : 1

  const codeComparison = a.competition.localeCompare(b.competition)
  if (codeComparison !== 0) return codeComparison
  return a.competition_season_id - b.competition_season_id
}

/**
 * Resolves a concrete player profile slice without changing the application's
 * global scope. Membership order is the source of truth for season fallback;
 * competition fallback is domestic-first and then stable by code/id.
 */
export function resolveProfileSlice<T extends ProfileSliceMembership>(
  memberships: T[],
  globalScope: Scope,
  requested: Partial<ProfileSlice>,
): ProfileSlice | undefined {
  if (!memberships.length) return undefined

  const seasons = [...new Set(memberships.map(membership => membership.season))]
  const globalAggregateSeason =
    globalScope.competition === 'ALL' || globalScope.competition === 'BIG5'
      ? memberships.find(membership => membership.aggregate_season === globalScope.season)?.season
      : undefined
  const season =
    (requested.season && seasons.includes(requested.season) ? requested.season : undefined) ??
    (seasons.includes(globalScope.season) ? globalScope.season : undefined) ??
    globalAggregateSeason ??
    seasons[0]
  if (!season) return undefined

  const inSeason = memberships.filter(membership => membership.season === season)
  const competition =
    (requested.competition &&
    inSeason.some(membership => membership.competition === requested.competition)
      ? requested.competition
      : undefined) ?? inSeason.toSorted(compareCompetition)[0]?.competition
  return competition ? { competition, season } : undefined
}

export function profileSliceMatchesParams(
  params: URLSearchParams,
  slice: ProfileSlice,
): boolean {
  return (
    params.get('profileCompetition') === slice.competition &&
    params.get('profileSeason') === slice.season
  )
}

export function withProfileSliceParams(params: URLSearchParams, slice: ProfileSlice): URLSearchParams {
  const next = new URLSearchParams(params)
  next.set('profileCompetition', slice.competition)
  next.set('profileSeason', slice.season)
  return next
}
