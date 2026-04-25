import { STAT_CELL_PX, buildDefaultVisibility, type ColGroupDef } from './columns'

const S = STAT_CELL_PX

/** Goalkeeper-only stat matrix (Sofascore goalkeeper metrics + distribution). */
export const COLUMN_GROUPS_GK: ColGroupDef[] = [
  {
    id: 'meta',
    label: 'Player',
    cols: [
      {
        id: 'canonical_player_name',
        label: 'Player',
        isMeta: true,
        isSticky: true,
        defaultVisible: true,
        width: 152,
      },
      { id: 'canonical_team_name', label: 'Club', isMeta: true, defaultVisible: true, width: S },
      { id: 'minutes', label: 'Mins', isMeta: true, unit: 'integer', defaultVisible: true, width: S },
      { id: 'appearances', label: 'Apps', isMeta: true, unit: 'integer', defaultVisible: true, width: S },
    ],
  },
  {
    id: 'shot_stopping',
    label: 'Shot stopping',
    cols: [
      { id: 'saves_per_90', label: 'Sv', unit: 'per90', defaultVisible: true, width: S },
      { id: 'clean_sheet_rate', label: 'CS%', unit: 'percentage', defaultVisible: true, width: S },
      { id: 'clean_sheets', label: 'CS', unit: 'total', defaultVisible: true, width: S },
      { id: 'penalty_saves', label: 'PenSv', unit: 'total', defaultVisible: true, width: S },
      {
        id: 'saved_shots_inside_box_per_90',
        label: 'BoxSv',
        unit: 'per90',
        defaultVisible: true,
        width: S,
      },
    ],
  },
  {
    id: 'sweeper',
    label: 'Sweeper',
    cols: [{ id: 'runs_out_per_90', label: 'Out', unit: 'per90', defaultVisible: true, width: S }],
  },
  {
    id: 'distribution',
    label: 'Distribution',
    cols: [
      { id: 'pass_accuracy', label: 'Pass%', unit: 'percentage', defaultVisible: true, width: S },
      { id: 'completed_passes_per_90', label: 'Pass', unit: 'per90', defaultVisible: true, width: S },
      { id: 'accurate_long_balls_per_90', label: 'Long', unit: 'per90', defaultVisible: true, width: S },
    ],
  },
]

export function buildGkDefaultVisibility(): Record<string, boolean> {
  return Object.fromEntries(COLUMN_GROUPS_GK.flatMap(g => g.cols).map(c => [c.id, true]))
}

export function buildMatrixVisibilityAll(): Record<string, boolean> {
  return { ...buildDefaultVisibility(), ...buildGkDefaultVisibility() }
}
