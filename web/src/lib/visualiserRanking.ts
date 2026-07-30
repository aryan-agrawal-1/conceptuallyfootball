export interface ScatterRankDatum {
  id: number
  x: number
  y: number
  tieBreak?: number
}

export interface RankedScatterDatum<T extends ScatterRankDatum> {
  point: T
  rank: number
  xRank: number
  yRank: number
}

export interface BarRankDatum {
  id: number
  label: string
  value: number
}

function rankValuesDescending<T>(
  items: T[],
  valueFor: (item: T) => number | null | undefined,
): Map<T, number> {
  const ranked = items
    .flatMap(item => {
      const value = valueFor(item)
      return value == null || Number.isNaN(value) ? [] : [{ item, value }]
    })
    .toSorted((left, right) => right.value - left.value)

  const result = new Map<T, number>()
  let previousValue: number | undefined
  let currentRank = 0
  ranked.forEach((entry, index) => {
    if (previousValue == null || entry.value !== previousValue) {
      currentRank = index + 1
      previousValue = entry.value
    }
    result.set(entry.item, currentRank)
  })
  return result
}

/**
 * Rank plotted scatter points by their combined descending x/y position.
 * This is deliberately positional: metric desirability never reverses an axis.
 */
export function rankScatterPointsByTopRight<T extends ScatterRankDatum>(
  points: T[],
): RankedScatterDatum<T>[] {
  const xRanks = rankValuesDescending(points, point => point.x)
  const yRanks = rankValuesDescending(points, point => point.y)

  return points
    .flatMap(point => {
      const xRank = xRanks.get(point)
      const yRank = yRanks.get(point)
      if (xRank == null || yRank == null) return []
      return [{
        point,
        rank: xRank + yRank,
        xRank,
        yRank,
      }]
    })
    .toSorted((left, right) =>
      left.rank - right.rank ||
      (right.point.tieBreak ?? 0) - (left.point.tieBreak ?? 0) ||
      right.point.y - left.point.y ||
      right.point.x - left.point.x ||
      left.point.id - right.point.id,
    )
}

/** Order bar-picker candidates in the same direction as the visible top/bottom window. */
export function rankBarCandidates<T extends BarRankDatum>(
  rows: T[],
  window: 'top' | 'bottom' | 'all',
): T[] {
  const direction = window === 'bottom' ? 1 : -1
  return rows.toSorted((left, right) =>
    direction * (left.value - right.value) ||
    left.label.localeCompare(right.label) ||
    left.id - right.id,
  )
}

export function scatterLabelIds(
  allPointIds: number[],
  pinnedIds: number[],
  labelsEnabled: boolean,
): number[] {
  if (!labelsEnabled) return []
  return allPointIds.length <= 20 ? allPointIds : pinnedIds
}
