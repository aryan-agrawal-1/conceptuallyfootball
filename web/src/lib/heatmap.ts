import type { CSSProperties } from 'react'
import type { MetricDefinition, MetricSemanticColor } from '../types/api'

/** Bad → good (reference palette, evenly spaced across percentiles). */
const POSITIVE_HEX_STOPS = [
  '#c084fc',
  '#e879f9',
  '#f0abfc',
  '#f5d0fe',
  '#fae8ff',
  '#e5e7eb',
  '#ccfbf1',
  '#99f6e4',
  '#5eead4',
  '#2dd4bf',
  '#14b8a6',
] as const

const NEGATIVE_HEX_STOPS = POSITIVE_HEX_STOPS.toReversed()

/** Descriptive low → high palette without good/bad endpoints. */
const CONTEXTUAL_HEX_STOPS = [
  '#d9e1ee',
  '#d0d9e8',
  '#c6d1e2',
  '#bdc9dc',
  '#b3c1d6',
  '#aab9d0',
  '#a0b1ca',
  '#97a9c4',
  '#8da1be',
  '#8499b8',
  '#7b91b2',
] as const

const PALETTES: Record<MetricSemanticColor, readonly string[]> = {
  positive: POSITIVE_HEX_STOPS,
  negative: NEGATIVE_HEX_STOPS,
  contextual: CONTEXTUAL_HEX_STOPS,
}

export const HEATMAP_GRADIENT_CSS = heatmapGradientCss('positive')

export function heatmapGradientCss(semanticColor: MetricSemanticColor): string {
  return `linear-gradient(90deg, ${PALETTES[semanticColor].join(', ')})`
}

interface RGB { r: number; g: number; b: number }

function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '')
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  }
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

/** Smooth blend through all reference stops (0–100 percentile). */
function interpolateHeatmapRgb(p: number, semanticColor: MetricSemanticColor): RGB {
  const palette = PALETTES[semanticColor]
  const percentileStops = palette.map((_, index) => (index / (palette.length - 1)) * 100)
  const rgbStops = palette.map(hexToRgb)
  const clamped = Math.max(0, Math.min(100, p))
  for (let i = 1; i < percentileStops.length; i++) {
    if (clamped <= percentileStops[i]) {
      const t =
        (clamped - percentileStops[i - 1]) /
        (percentileStops[i] - percentileStops[i - 1])
      const a = rgbStops[i - 1]
      const b = rgbStops[i]
      return {
        r: Math.round(lerp(a.r, b.r, t)),
        g: Math.round(lerp(a.g, b.g, t)),
        b: Math.round(lerp(a.b, b.b, t)),
      }
    }
  }
  const last = rgbStops[rgbStops.length - 1]
  return { ...last }
}

export function metricSemanticColor(
  definition: Pick<MetricDefinition, 'semantic_color'> | undefined,
): MetricSemanticColor {
  return definition?.semantic_color ?? 'positive'
}

export function semanticColorDescription(semanticColor: MetricSemanticColor): string {
  if (semanticColor === 'negative') {
    return 'Colour scale reversed: a lower statistical percentile receives the more positive colour.'
  }
  if (semanticColor === 'contextual') {
    return 'Neutral colour scale: the percentile describes relative volume, not good or bad performance.'
  }
  return 'Evaluative colour scale: a higher statistical percentile receives the more positive colour.'
}

export interface MinutesHeatRange {
  min: number
  max: number
}

export function getMinutesHeatRangeFromPlayers(rows: { minutes: number }[]): MinutesHeatRange | null {
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY
  for (const row of rows) {
    const m = row.minutes
    if (typeof m !== 'number' || m < 0) continue
    if (m < min) min = m
    if (m > max) max = m
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null
  return { min, max }
}

export function minutesHeatPercentileFromRange(
  minutes: number | null | undefined,
  range: MinutesHeatRange | null,
): number | null {
  if (minutes == null || !range) return null
  if (range.max === range.min) return 50
  const t = (100 * (minutes - range.min)) / (range.max - range.min)
  return Math.max(0, Math.min(100, t))
}

export function getHeatmapStyle(
  percentile: number | null,
  enabled = true,
  semanticColor: MetricSemanticColor = 'positive',
): CSSProperties {
  if (!enabled || percentile === null) return {}
  const rgb = interpolateHeatmapRgb(percentile, semanticColor)
  return {
    backgroundColor: `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`,
    color: '#000000',
  }
}

/** Solid colour for profile bars / legends (same gradient). */
export function getPercentileTextColor(
  percentile: number | null,
  semanticColor: MetricSemanticColor = 'positive',
): string {
  if (percentile === null) return 'rgba(78, 88, 120, 0.7)'
  const { r, g, b } = interpolateHeatmapRgb(percentile, semanticColor)
  return `rgb(${r}, ${g}, ${b})`
}
