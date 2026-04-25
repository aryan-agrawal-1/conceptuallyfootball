import type { MetricDefinition } from '../types/api'

export type ColumnUnit = MetricDefinition['unit'] | 'score' | 'integer'

export interface ColDef {
  id: string
  label: string
  unit?: ColumnUnit
  isScore?: boolean
  isMeta?: boolean
  isSticky?: boolean
  defaultVisible: boolean
  width: number
}

export interface ColGroupDef {
  id: string
  label: string
  cols: ColDef[]
}

/** Pixel width & height of square stat / club / minutes cells. */
export const STAT_CELL_PX = 54

const S = STAT_CELL_PX

export const COLUMN_GROUPS: ColGroupDef[] = [
  {
    id: 'meta',
    label: 'Player',
    cols: [
      { id: 'canonical_player_name', label: 'Player', isMeta: true, isSticky: true, defaultVisible: true, width: 152 },
      { id: 'canonical_team_name',   label: 'Club',   isMeta: true, defaultVisible: true, width: S },
      { id: 'minutes',               label: 'Mins',   isMeta: true, unit: 'integer', defaultVisible: true, width: S },
    ],
  },
  {
    id: 'scores',
    label: 'Scores',
    cols: [
      { id: 'finishing_score',    label: 'Fin',    isScore: true, unit: 'score', defaultVisible: true, width: S },
      { id: 'creation_score',     label: 'Cre',    isScore: true, unit: 'score', defaultVisible: true, width: S },
      { id: 'buildup_score',      label: 'Bld',    isScore: true, unit: 'score', defaultVisible: true, width: S },
      { id: 'ball_winning_score', label: 'BWin',   isScore: true, unit: 'score', defaultVisible: true, width: S },
      { id: 'involvement_score',  label: 'Inv',    isScore: true, unit: 'score', defaultVisible: true, width: S },
    ],
  },
  {
    id: 'defending',
    label: 'Defending',
    cols: [
      { id: 'tackles_per_90',           label: 'Tkl',    unit: 'per90', defaultVisible: true, width: S },
      { id: 'tackles_won',              label: 'TklW',   unit: 'total', defaultVisible: true, width: S },
      { id: 'tackles_won_percentage',   label: 'TklW%',  unit: 'percentage', defaultVisible: true, width: S },
      { id: 'interceptions_per_90',     label: 'Int',    unit: 'per90', defaultVisible: true, width: S },
      { id: 'clearances_per_90',        label: 'Clr',    unit: 'per90', defaultVisible: true, width: S },
      { id: 'blocks_per_90',            label: 'Blk',    unit: 'per90', defaultVisible: true, width: S },
      { id: 'defensive_action_density', label: 'DAct',   unit: 'per90', defaultVisible: true, width: S },
      { id: 'aerial_duels_won',         label: 'AirW',   unit: 'total', defaultVisible: true, width: S },
      { id: 'ground_duels_won',         label: 'GndW',   unit: 'total', defaultVisible: true, width: S },
      { id: 'ball_recoveries',          label: 'Rec',    unit: 'total', defaultVisible: true, width: S },
      { id: 'fouls',                    label: 'Foul',   unit: 'total', defaultVisible: false, width: S },
    ],
  },
  {
    id: 'passing_creative',
    label: 'Passing / Creative',
    cols: [
      { id: 'completed_passes_per_90',    label: 'Pass',   unit: 'per90',      defaultVisible: true, width: S },
      { id: 'key_passes_per_90',          label: 'KP',     unit: 'per90',      defaultVisible: true, width: S },
      { id: 'big_chances_created_per_90', label: 'BCC',    unit: 'per90',      defaultVisible: true, width: S },
      { id: 'pass_accuracy',              label: 'Acc%',   unit: 'percentage', defaultVisible: true, width: S },
      { id: 'xa_per_key_pass',            label: 'xA/KP',  unit: 'ratio',      defaultVisible: true, width: S },
      { id: 'buildup_share',              label: 'BldSh',  unit: 'share',      defaultVisible: true, width: S },
      { id: 'successful_dribbles_per_90', label: 'Drib',   unit: 'per90',      defaultVisible: true, width: S },
      { id: 'xgbuildup_per_90',           label: 'xGBld',  unit: 'per90',      defaultVisible: true, width: S },
      { id: 'xgchain_per_90',             label: 'xGChn',  unit: 'per90',      defaultVisible: true, width: S },
      { id: 'chance_involvement_per_90',  label: 'ChInv',  unit: 'per90',      defaultVisible: true, width: S },
    ],
  },
  {
    id: 'attacking',
    label: 'Attacking',
    cols: [
      { id: 'npxg_per_90',      label: 'NPxG',    unit: 'per90', defaultVisible: true, width: S },
      { id: 'xa_per_90',        label: 'xA',      unit: 'per90', defaultVisible: true, width: S },
      { id: 'goals_per_90',     label: 'Gls',     unit: 'per90', defaultVisible: true, width: S },
      { id: 'assists_per_90',   label: 'Ast',     unit: 'per90', defaultVisible: true, width: S },
      { id: 'shots_per_90',     label: 'Shots',   unit: 'per90', defaultVisible: true, width: S },
      { id: 'shots_on_target',  label: 'SoT',     unit: 'total', defaultVisible: true, width: S },
      { id: 'shots_off_target', label: 'Soff',    unit: 'total', defaultVisible: false, width: S },
      { id: 'successful_dribbles_percentage', label: 'Drb%', unit: 'percentage', defaultVisible: true, width: S },
      { id: 'offsides',         label: 'Off',     unit: 'total', defaultVisible: false, width: S },
      { id: 'npxg_per_shot',    label: 'NPxG/Sh', unit: 'ratio', defaultVisible: true, width: S },
      { id: 'goals_minus_xg',   label: 'G−xG',    unit: 'delta', defaultVisible: true, width: S },
      { id: 'goals_minus_npxg', label: 'NPG−xG',  unit: 'delta', defaultVisible: true, width: S },
    ],
  },
]

export const SCORE_GROUP_ID = 'scores' as const

/** Column ids for composite scores (percentiles within each outfield position). */
export const SCORE_COLUMN_IDS: string[] =
  COLUMN_GROUPS.find(g => g.id === SCORE_GROUP_ID)?.cols.map(c => c.id) ?? []

export const COL_BY_ID: Record<string, ColDef> = Object.fromEntries(
  COLUMN_GROUPS.flatMap(g => g.cols).map(c => [c.id, c]),
)

/** Initial column visibility: all metric columns on by default. */
export function buildDefaultVisibility(): Record<string, boolean> {
  return Object.fromEntries(
    COLUMN_GROUPS.flatMap(g => g.cols).map(c => [c.id, true]),
  )
}
