import { formatValue } from './format'
import type { ProfileRateMode } from './profileMetrics'
import type { TeamDetailResponse, TeamStatMeta } from '../types/api'

/** No league-rank chip on key tiles for these (position & points are the table itself). */
export const TEAM_KEY_STATS_WITHOUT_RANK: ReadonlySet<string> = new Set(['rank', 'points'])

/** Layout matches backend `TEAM_STAT_GROUPS` (chances + set pieces merged). */
export type TeamSectionLayoutRow =
  | { kind: 'pair'; left: string; right: string }
  | { kind: 'single'; section: string }

export const TEAM_SECTION_LAYOUT: readonly TeamSectionLayoutRow[] = [
  { kind: 'pair', left: 'table', right: 'shooting' },
  { kind: 'pair', left: 'chances_set_pieces', right: 'passing' },
  { kind: 'pair', left: 'possession', right: 'defending' },
  { kind: 'single', section: 'discipline' },
]

/** Key tiles at top of team profile (subset of ranked_keys / stats). */
export const TEAM_KEY_STAT_KEYS: readonly string[] = [
  'rank',
  'points',
  'expected_goals',
  'expected_assists',
  'goals_for',
  'goals_against',
  'goal_difference',
  'average_ball_possession',
  'wins',
  'clean_sheets',
]

export type TeamStatFormatUnit =
  | 'integer'
  | 'percentage'
  | 'total'
  | 'delta'

export function teamStatFormatUnit(statKey: string): TeamStatFormatUnit {
  if (statKey === 'goal_difference') return 'delta'
  if (
    statKey.includes('percentage') ||
    statKey === 'average_ball_possession' ||
    statKey.endsWith('_percentage')
  ) {
    return 'percentage'
  }
  if (
    statKey === 'rank' ||
    statKey === 'points' ||
    statKey === 'matches' ||
    statKey === 'wins' ||
    statKey === 'draws' ||
    statKey === 'losses' ||
    statKey === 'goals_for' ||
    statKey === 'goals_against' ||
    statKey === 'clean_sheets'
  ) {
    return 'integer'
  }
  return 'total'
}

export function formatTeamStat(statKey: string, value: number | null | undefined): string {
  return formatValue(value ?? null, teamStatFormatUnit(statKey))
}

/**
 * Team "Per 90" uses the same control as player profiles: volume stats are scaled by
 * `matches` so each rate is comparable per match (equivalent to per 90 of one team match
 * unit). Percentages and table identifiers stay on season form.
 */
export function formatTeamStatMode(
  statKey: string,
  value: number | null | undefined,
  matches: number | null | undefined,
  mode: ProfileRateMode,
): string {
  const resolved = teamStatValueForMode(statKey, value, matches, mode)
  if (resolved == null) return '—'
  if (mode === 'full') return formatTeamStat(statKey, resolved)
  if (statKey === 'goal_difference') return formatValue(resolved, 'delta')
  if (teamStatFormatUnit(statKey) === 'percentage') return formatTeamStat(statKey, resolved)
  if (statKey === 'rank' || statKey === 'points' || statKey === 'matches') {
    return formatTeamStat(statKey, resolved)
  }
  return formatValue(resolved, 'per90')
}

export function teamStatValueForMode(
  statKey: string,
  value: number | null | undefined,
  matches: number | null | undefined,
  mode: ProfileRateMode,
): number | null {
  if (value == null) return null
  const m = matches != null && matches > 0 ? matches : null

  if (mode === 'full') {
    return value
  }

  if (teamStatFormatUnit(statKey) === 'percentage') {
    return value
  }

  if (statKey === 'rank' || statKey === 'points' || statKey === 'matches') {
    return value
  }

  if (!m) {
    return value
  }

  return value / m
}

export function teamKeyStatLabel(
  key: string,
  meta: TeamStatMeta | undefined,
): string {
  return meta?.stats[key]?.label ?? key.replace(/_/g, ' ')
}

export function teamKeyStatSpecs(
  team: TeamDetailResponse,
  meta: TeamStatMeta | undefined,
  mode: ProfileRateMode,
): Array<{
  key: string
  label: string
  value: string
  rank: number | null
  /** Hide the whole "Lg rank" row for table position & points. */
  showRankRow: boolean
}> {
  const matches = team.stats.matches ?? null
  const rankMap = mode === 'full' ? team.ranks : team.ranks_per_match
  return TEAM_KEY_STAT_KEYS.filter(k => team.stats[k] != null).map(key => ({
    key,
    label: teamKeyStatLabel(key, meta),
    value: formatTeamStatMode(key, team.stats[key], matches, mode),
    rank: rankMap[key] ?? null,
    showRankRow: !TEAM_KEY_STATS_WITHOUT_RANK.has(key),
  }))
}
