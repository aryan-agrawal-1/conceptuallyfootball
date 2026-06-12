import type { PositionGroup, StatMeta } from '../types/api'
import { COMPARISON_STAT_MAX, COMPARISON_STAT_MIN } from './comparisonConstants'

export type ComparisonAxisPackId = 'attacking' | 'creativity' | 'carrying' | 'defending' | 'gk'

export interface ComparisonAxisPack {
  id: ComparisonAxisPackId
  label: string
  keys: string[]
}

const PACK_KEYS: Record<ComparisonAxisPackId, string[]> = {
  attacking: [
    'xg_per_90',
    'npxg_per_90',
    'goals_per_90',
    'shots_per_90',
    'npxg_per_shot',
    'goals_minus_npxg',
    'xa_per_90',
    'chance_involvement_per_90',
  ],
  creativity: [
    'xa_per_90',
    'key_passes_per_90',
    'big_chances_created_per_90',
    'xa_per_key_pass',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'completed_passes_per_90',
    'pass_accuracy',
  ],
  carrying: [
    'successful_dribbles_per_90',
    'successful_dribbles_percentage',
    'chance_involvement_per_90',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'ground_duels_won',
    'fouls',
    'pass_accuracy',
  ],
  defending: [
    'tackles_per_90',
    'interceptions_per_90',
    'clearances_per_90',
    'blocks_per_90',
    'defensive_action_density',
    'ball_recoveries',
    'aerial_duels_won',
    'ground_duels_won',
  ],
  gk: [
    'saves_per_90',
    'clean_sheet_rate',
    'saved_shots_inside_box_per_90',
    'runs_out_per_90',
    'pass_accuracy',
    'completed_passes_per_90',
    'accurate_long_balls_per_90',
    'penalty_saves',
  ],
}

const PACK_LABELS: Record<ComparisonAxisPackId, string> = {
  attacking: 'Attacking',
  creativity: 'Creativity',
  carrying: 'Carrying',
  defending: 'Defending',
  gk: 'GK',
}

const PACK_ORDER: Record<Exclude<PositionGroup, 'UNK'>, ComparisonAxisPackId[]> = {
  FWD: ['attacking', 'creativity', 'carrying', 'defending'],
  MID: ['creativity', 'carrying', 'attacking', 'defending'],
  DEF: ['defending', 'carrying', 'creativity', 'attacking'],
  GK: ['gk'],
}

export function comparisonAxisPacksForPosition(
  positionGroup: PositionGroup,
  meta: StatMeta,
  isUsable?: (key: string) => boolean,
): ComparisonAxisPack[] {
  const order = positionGroup === 'GK'
    ? PACK_ORDER.GK
    : PACK_ORDER[positionGroup === 'UNK' ? 'MID' : positionGroup]

  return order.flatMap(id => {
    const keys = PACK_KEYS[id]
      .filter(key => key in meta.metrics && !(positionGroup === 'GK' && key === 'rating') && (isUsable?.(key) ?? true))
      .slice(0, COMPARISON_STAT_MAX)

    return keys.length >= COMPARISON_STAT_MIN
      ? [{ id, label: PACK_LABELS[id], keys }]
      : []
  })
}
