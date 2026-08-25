import type { GoalMouthCoordinate } from '../../types/eventMaps'

// Pitch-coordinate extent of the goal mouth (7.32m wide on a 68m pitch).
export const GOAL_Y_MIN = 44.62
export const GOAL_Y_MAX = 55.38

// GoalMouthZ runs 0..100 across roughly 6.8m of height, so the crossbar
// (2.44m) sits near 38 — confirmed empirically: no on-target shot exceeds
// 36.7, while off-target shots over the bar reach 100.
export const GOAL_CROSSBAR_Z = 38

// Boundary between the low and high bands: the halfway height of the goal.
export const GOAL_Z_LOW_MAX = GOAL_CROSSBAR_Z / 2
export const GOAL_COLUMNS = 3

export type GoalZone = {
  column: number
  row: number
}

// Columns are indexed by ascending pitch y, i.e. right-to-left from the
// shooter's perspective (shooter's left is the high-y side).

export function goalZone(goalMouth: GoalMouthCoordinate): GoalZone | null {
  const { y, z } = goalMouth
  if (y < GOAL_Y_MIN || y > GOAL_Y_MAX) return null
  if (z < 0 || z > 100) return null
  const column = Math.min(
    GOAL_COLUMNS - 1,
    Math.floor(((y - GOAL_Y_MIN) / (GOAL_Y_MAX - GOAL_Y_MIN)) * GOAL_COLUMNS),
  )
  return { column, row: z > GOAL_Z_LOW_MAX ? 1 : 0 }
}

const COLUMN_LABELS = ['right', 'centre', 'left'] as const

export function goalZoneLabel(zone: GoalZone): string {
  const height = zone.row === 1 ? 'high' : 'low'
  return `${height} ${COLUMN_LABELS[zone.column] ?? 'centre'}`
}
