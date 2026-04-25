/** Minutes below which we warn on comparisons (matches matrix default filter). */
export const COMPARISON_MIN_MINUTES_WARNING = 450

/** Same floor as profile polar chart. */
export const COMPARISON_STAT_MIN = 4

/** Hard cap for readability with overlapping players. */
export const COMPARISON_STAT_MAX = 10

/** Fixed slot colors: stroke + translucent fill (HUD-aligned). */
export const COMPARISON_SLOT_STROKES = [
  'rgba(74, 158, 245, 0.95)',
  'rgba(52, 211, 153, 0.95)',
  'rgba(251, 191, 36, 0.95)',
] as const

export const COMPARISON_SLOT_FILLS = [
  'rgba(74, 158, 245, 0.24)',
  'rgba(52, 211, 153, 0.24)',
  'rgba(251, 191, 36, 0.24)',
] as const
