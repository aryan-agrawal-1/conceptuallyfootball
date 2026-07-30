import { describe, expect, it } from 'vitest'
import {
  rankBarCandidates,
  rankScatterPointsByTopRight,
  scatterLabelIds,
} from '../src/lib/visualiserRanking'
import { parseDataVisualiserParams } from '../src/lib/dataVisualiserUrl'

describe('visualiser chart relevance ranking', () => {
  it('shares descending combined x/y rank ordering with top-right highlights', () => {
    const ranked = rankScatterPointsByTopRight([
      { id: 1, x: 10, y: 10, tieBreak: 100 },
      { id: 2, x: 8, y: 9, tieBreak: 200 },
      { id: 3, x: 4, y: 2, tieBreak: 300 },
    ])

    expect(ranked.map(item => item.point.id)).toEqual([1, 2, 3])
    expect(ranked.map(item => item.rank)).toEqual([2, 4, 6])
  })

  it('retains deterministic tie-breaking without applying desirability semantics', () => {
    const ranked = rankScatterPointsByTopRight([
      { id: 2, x: 8, y: 8, tieBreak: 20 },
      { id: 1, x: 8, y: 8, tieBreak: 40 },
    ])

    expect(ranked.map(item => item.point.id)).toEqual([1, 2])
  })

  it('orders bar candidates in the selected top or bottom direction', () => {
    const rows = [
      { id: 1, label: 'One', value: 5 },
      { id: 2, label: 'Two', value: 10 },
      { id: 3, label: 'Three', value: -2 },
    ]

    expect(rankBarCandidates(rows, 'top').map(row => row.id)).toEqual([2, 1, 3])
    expect(rankBarCandidates(rows, 'bottom').map(row => row.id)).toEqual([3, 1, 2])
  })

  it('keeps labels enabled by default and focuses crowded charts on pins', () => {
    expect(parseDataVisualiserParams(new URLSearchParams()).labels).toBe(true)
    const pointIds = Array.from({ length: 21 }, (_, index) => index + 1)
    expect(scatterLabelIds(pointIds, [3, 9], true)).toEqual([3, 9])
    expect(scatterLabelIds(pointIds.slice(0, 20), [3, 9], true)).toEqual(
      pointIds.slice(0, 20),
    )
    expect(scatterLabelIds(pointIds, [3, 9], false)).toEqual([])
  })
})
