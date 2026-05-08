import type { PositionGroup, StatMeta } from '../types/api'

export type LabPosition = 'FWD' | 'MID' | 'DEF'

/** Medium-curated targets per position (must stay aligned with backend). */
export const TARGETS_BY_POSITION: Record<LabPosition, string[]> = {
  FWD: [
    'xg_per_90',
    'npxg_per_90',
    'goals_per_90',
    'shots_per_90',
    'assists_per_90',
    'key_passes_per_90',
    'chance_involvement_per_90',
    'goals_minus_npxg',
    'npxg_per_shot',
  ],
  MID: [
    'xg_per_90',
    'xa_per_90',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'key_passes_per_90',
    'big_chances_created_per_90',
    'completed_passes_per_90',
    'pass_accuracy',
    'chance_involvement_per_90',
  ],
  DEF: [
    'tackles_per_90',
    'interceptions_per_90',
    'clearances_per_90',
    'defensive_action_density',
    'ball_recoveries_per_90',
    'xgbuildup_per_90',
    'xg_per_90',
    'xa_per_90',
    'pass_accuracy',
  ],
}

export function isLabPosition(p: string | undefined): p is LabPosition {
  return p === 'FWD' || p === 'MID' || p === 'DEF'
}

export function toLabPosition(p: PositionGroup | string | undefined): LabPosition | null {
  if (p === 'FWD' || p === 'MID' || p === 'DEF') return p
  return null
}

/** Target-specific default predictors (raw metrics only). */
export function recommendedPredictorsForTarget(
  targetKey: string,
  position: LabPosition,
): string[] {
  void position
  const fwdAttack = ['shots_per_90', 'npxg_per_shot', 'key_passes_per_90', 'xgchain_per_90', 'chance_involvement_per_90']
  const midCreate = [
    'key_passes_per_90',
    'big_chances_created_per_90',
    'xa_per_90',
    'successful_dribbles_per_90',
    'xgchain_per_90',
    'completed_passes_per_90',
  ]
  const defProg = [
    'tackles_per_90',
    'interceptions_per_90',
    'ball_recoveries_per_90',
    'pass_accuracy',
    'xgbuildup_per_90',
    'completed_passes_per_90',
  ]

  const byTarget: Record<string, string[]> = {
    // FWD metrics
    xg_per_90: fwdAttack,
    npxg_per_90: fwdAttack,
    goals_per_90: ['npxg_per_90', 'shots_per_90', 'goals_minus_npxg', 'assists_per_90', 'npxg_per_shot'],
    shots_per_90: ['npxg_per_90', 'npxg_per_shot', 'goals_minus_npxg', 'key_passes_per_90'],
    assists_per_90: ['xa_per_90', 'key_passes_per_90', 'big_chances_created_per_90', 'xgchain_per_90'],
    key_passes_per_90: ['xa_per_90', 'big_chances_created_per_90', 'xgchain_per_90', 'successful_dribbles_per_90'],
    chance_involvement_per_90: ['xgchain_per_90', 'key_passes_per_90', 'shots_per_90', 'xgbuildup_per_90'],
    goals_minus_npxg: ['npxg_per_90', 'shots_per_90', 'npxg_per_shot', 'goals_per_90'],
    npxg_per_shot: ['shots_per_90', 'npxg_per_90', 'goals_minus_npxg', 'sot_rate'],
    // MID metrics
    xa_per_90: midCreate,
    xgchain_per_90: ['chance_involvement_per_90', 'xgbuildup_per_90', 'key_passes_per_90', 'shots_per_90'],
    xgbuildup_per_90: ['completed_passes_per_90', 'pass_accuracy', 'accurate_long_balls_per_90', 'xgchain_per_90'],
    big_chances_created_per_90: ['key_passes_per_90', 'xa_per_90', 'xgchain_per_90', 'successful_dribbles_per_90'],
    completed_passes_per_90: ['pass_accuracy', 'xgbuildup_per_90', 'accurate_long_balls_per_90', 'key_passes_per_90'],
    pass_accuracy: ['completed_passes_per_90', 'inaccurate_pass_rate', 'xgbuildup_per_90', 'key_passes_per_90'],
    // DEF metrics
    tackles_per_90: defProg,
    interceptions_per_90: defProg,
    clearances_per_90: ['aerial_duels_won_per_90', 'tackles_per_90', 'ball_recoveries_per_90', 'blocks_per_90'],
    defensive_action_density: ['tackles_per_90', 'interceptions_per_90', 'ball_recoveries_per_90', 'clearances_per_90'],
    ball_recoveries_per_90: ['tackles_per_90', 'interceptions_per_90', 'pass_accuracy', 'ground_duels_won_per_90'],
  }

  const pack = byTarget[targetKey]
  if (!pack) return midCreate
  return [...pack]
}

/** All raw metrics that can appear as predictors in packs (subset of known API metrics). */
export const PREDICTOR_METRIC_POOL: string[] = [
  'xg_per_90',
  'npxg_per_90',
  'shots_per_90',
  'npxg_per_shot',
  'goals_per_90',
  'assists_per_90',
  'goals_minus_npxg',
  'goals_minus_xg',
  'xa_per_90',
  'xgchain_per_90',
  'xgbuildup_per_90',
  'buildup_share',
  'key_passes_per_90',
  'big_chances_created_per_90',
  'successful_dribbles_per_90',
  'chance_involvement_per_90',
  'completed_passes_per_90',
  'pass_accuracy',
  'accurate_long_balls_per_90',
  'accurate_crosses_per_90',
  'tackles_per_90',
  'interceptions_per_90',
  'clearances_per_90',
  'blocks_per_90',
  'defensive_action_density',
  'ball_recoveries_per_90',
  'tackles_won_percentage',
  'ground_duels_won_per_90',
  'aerial_duels_won_per_90',
  'fouls_per_90',
  'errors_lead_to_goal_per_90',
  'offsides_per_90',
  'sot_rate',
  'inaccurate_pass_rate',
  'kp_share_per90',
]

const PREDICTOR_GROUP_ORDER = ['attack', 'volume', 'defending', 'efficiency_style'] as const
const PREDICTOR_GROUP_ORDER_SET = new Set<string>(PREDICTOR_GROUP_ORDER)

export interface PredictorGroupSlice {
  groupId: string
  groupLabel: string
  keys: string[]
}

/** Group predictor keys by `StatMeta` metric groups for readable lab UI. */
export function groupPredictorPool(meta: StatMeta | undefined): PredictorGroupSlice[] {
  if (!meta) return []
  const buckets = new Map<string, string[]>()
  for (const key of PREDICTOR_METRIC_POOL) {
    const def = meta.metrics[key]
    if (!def) continue
    const gid = def.group
    if (!buckets.has(gid)) buckets.set(gid, [])
    buckets.get(gid)!.push(key)
  }
  for (const keys of buckets.values()) {
    keys.sort((a, b) =>
      (meta.metrics[a]?.label ?? a).localeCompare(meta.metrics[b]?.label ?? b, undefined, {
        sensitivity: 'base',
      }),
    )
  }
  const out: PredictorGroupSlice[] = []
  for (const id of PREDICTOR_GROUP_ORDER) {
    const keys = buckets.get(id)
    if (keys?.length) {
      out.push({
        groupId: id,
        groupLabel: meta.metric_groups[id] ?? id,
        keys,
      })
    }
  }
  for (const [id, keys] of buckets) {
    if (!PREDICTOR_GROUP_ORDER_SET.has(id) && keys.length) {
      out.push({
        groupId: id,
        groupLabel: meta.metric_groups[id] ?? id,
        keys,
      })
    }
  }
  return out
}
