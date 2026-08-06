import type { SearchPlayerMembership, SearchTeamMembership } from '../types/api'
import type { Scope } from '../context/ScopeContext'

const BIG_FIVE_COMPETITION_CODES = new Set(['ENG1', 'GER1', 'SPA1', 'FRA1', 'ITA1'])

type Membership = Pick<
  SearchPlayerMembership | SearchTeamMembership,
  'competition' | 'season' | 'aggregate_season' | 'competition_type' | 'include_in_domestic_aggregates'
>

function isDomesticAggregateMembership(membership: Membership): boolean {
  return (
    membership.competition_type !== 'continental_cup' &&
    membership.include_in_domestic_aggregates !== false
  )
}

export function scopeIncludesMembership(scope: Scope, membership: Membership): boolean {
  const membershipSeason =
    scope.competition === 'ALL' || scope.competition === 'BIG5'
      ? membership.aggregate_season ?? membership.season
      : membership.season
  if (membershipSeason !== scope.season) return false
  if (membership.competition === scope.competition) return true
  if (scope.competition === 'ALL') return isDomesticAggregateMembership(membership)
  if (scope.competition === 'BIG5') {
    return isDomesticAggregateMembership(membership) && BIG_FIVE_COMPETITION_CODES.has(membership.competition)
  }
  return false
}

export function membershipPriority(memberships: Membership[], scope: Scope): number {
  if (memberships.some(m => m.competition === scope.competition && m.season === scope.season)) return 0
  if (memberships.some(m => scopeIncludesMembership(scope, m))) return 1
  if (memberships.some(m => m.competition === scope.competition)) return 2
  return 3
}

export function preferredMembership<T extends Membership>(
  memberships: T[],
  scope: Scope,
): T | undefined {
  return (
    memberships.find(m => m.competition === scope.competition && m.season === scope.season) ??
    memberships.find(m => scopeIncludesMembership(scope, m)) ??
    memberships.find(m => m.competition === scope.competition) ??
    memberships[0]
  )
}
