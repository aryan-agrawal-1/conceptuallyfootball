import { describe, expect, it } from 'vitest'
import {
  getHeatmapStyle,
  getPercentileTextColor,
  metricSemanticColor,
  semanticColorDescription,
} from '../src/lib/heatmap'

describe('metric semantic percentile colours', () => {
  it('defaults unclassified metrics to positive', () => {
    expect(metricSemanticColor(undefined)).toBe('positive')
  })

  it('reverses only colour interpretation, not the supplied percentile', () => {
    expect(getPercentileTextColor(10, 'negative')).toBe(
      getPercentileTextColor(90, 'positive'),
    )
    expect(getHeatmapStyle(90, true, 'negative')).not.toEqual(
      getHeatmapStyle(10, true, 'negative'),
    )
  })

  it('uses and explains a distinct contextual palette', () => {
    expect(metricSemanticColor({ semantic_color: 'contextual' })).toBe('contextual')
    expect(getPercentileTextColor(90, 'contextual')).not.toBe(
      getPercentileTextColor(90, 'positive'),
    )
    expect(semanticColorDescription('contextual')).toContain('not good or bad')
  })
})
