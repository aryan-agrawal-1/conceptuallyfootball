import type { ColGroupDef } from './columns'

export type MatrixStarterVariant = 'outfield' | 'gk'

export interface MatrixStarterView {
  id: string
  label: string
  columnIds: string[]
  sortId: string
  sortDesc: boolean
}

const OUTFIELD_STARTER_VIEWS: MatrixStarterView[] = [
  {
    id: 'scouting',
    label: 'Scouting',
    sortId: 'npxg_per_90',
    sortDesc: true,
    columnIds: [
      'npxg_per_90',
      'xa_per_90',
      'key_passes_per_90',
      'xgbuildup_per_90',
      'successful_dribbles_per_90',
      'tackles_per_90',
      'interceptions_per_90',
      'aerial_duels_won',
    ],
  },
  {
    id: 'chance_creation',
    label: 'Chance Creation',
    sortId: 'xa_per_90',
    sortDesc: true,
    columnIds: [
      'xa_per_90',
      'key_passes_per_90',
      'big_chances_created_per_90',
      'xa_per_key_pass',
      'chance_involvement_per_90',
      'xgchain_per_90',
      'xgbuildup_per_90',
      'successful_dribbles_per_90',
    ],
  },
  {
    id: 'finishing',
    label: 'Finishing',
    sortId: 'npxg_per_90',
    sortDesc: true,
    columnIds: [
      'npxg_per_90',
      'goals_per_90',
      'shots_per_90',
      'shots_on_target',
      'npxg_per_shot',
      'goals_minus_xg',
      'goals_minus_npxg',
    ],
  },
  {
    id: 'ball_progression',
    label: 'Ball Progression',
    sortId: 'xgbuildup_per_90',
    sortDesc: true,
    columnIds: [
      'completed_passes_per_90',
      'pass_accuracy',
      'buildup_share',
      'xgbuildup_per_90',
      'xgchain_per_90',
      'successful_dribbles_per_90',
    ],
  },
  {
    id: 'defending',
    label: 'Defending',
    sortId: 'defensive_action_density',
    sortDesc: true,
    columnIds: [
      'tackles_per_90',
      'tackles_won_percentage',
      'interceptions_per_90',
      'clearances_per_90',
      'blocks_per_90',
      'defensive_action_density',
      'aerial_duels_won',
      'ground_duels_won',
      'ball_recoveries',
    ],
  },
]

const GK_STARTER_VIEWS: MatrixStarterView[] = [
  {
    id: 'gk_shot_stopping',
    label: 'GK Shot Stopping',
    sortId: 'saves_per_90',
    sortDesc: true,
    columnIds: [
      'saves_per_90',
      'clean_sheet_rate',
      'clean_sheets',
      'penalty_saves',
      'saved_shots_inside_box_per_90',
    ],
  },
  {
    id: 'gk_distribution',
    label: 'GK Distribution',
    sortId: 'accurate_long_balls_per_90',
    sortDesc: true,
    columnIds: [
      'pass_accuracy',
      'completed_passes_per_90',
      'accurate_long_balls_per_90',
    ],
  },
]

export function starterViewsForVariant(variant: MatrixStarterVariant): MatrixStarterView[] {
  return variant === 'gk' ? GK_STARTER_VIEWS : OUTFIELD_STARTER_VIEWS
}

export function visibilityForStarterView(
  view: MatrixStarterView,
  groups: ColGroupDef[],
): Record<string, boolean> {
  const selected = new Set(view.columnIds)
  return Object.fromEntries(
    groups.flatMap(group =>
      group.cols.map(col => [col.id, Boolean(col.isMeta) || selected.has(col.id)]),
    ),
  )
}
