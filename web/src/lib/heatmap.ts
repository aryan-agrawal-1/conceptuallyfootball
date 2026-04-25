import type { CSSProperties } from 'react'

/** Bad → good (reference palette, evenly spaced across percentiles). */
const HEX_STOPS = [
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

const P_STOPS = HEX_STOPS.map((_, i) => (i / (HEX_STOPS.length - 1)) * 100)

interface RGB { r: number; g: number; b: number }

function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '')
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  }
}

const RGB_STOPS: RGB[] = HEX_STOPS.map(hexToRgb)

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

/** Smooth blend through all reference stops (0–100 percentile). */
export function interpolateHeatmapRgb(p: number): RGB {
  const clamped = Math.max(0, Math.min(100, p))
  for (let i = 1; i < P_STOPS.length; i++) {
    if (clamped <= P_STOPS[i]) {
      const t = (clamped - P_STOPS[i - 1]) / (P_STOPS[i] - P_STOPS[i - 1])
      const a = RGB_STOPS[i - 1]
      const b = RGB_STOPS[i]
      return {
        r: Math.round(lerp(a.r, b.r, t)),
        g: Math.round(lerp(a.g, b.g, t)),
        b: Math.round(lerp(a.b, b.b, t)),
      }
    }
  }
  const last = RGB_STOPS[RGB_STOPS.length - 1]
  return { ...last }
}

/**
 * Minutes are not part of the API percentile payload. Map raw minutes to 0–100
 * using the min/max of the **currently loaded** table so the column still heatmaps
 * (more minutes → better / toward the cyan end).
 */
export function minutesHeatPercentile(
  minutes: number | null | undefined,
  allMinutes: (number | null | undefined)[],
): number | null {
  const range = getMinutesHeatRange(allMinutes)
  return minutesHeatPercentileFromRange(minutes, range)
}

export interface MinutesHeatRange {
  min: number
  max: number
}

export function getMinutesHeatRange(
  allMinutes: (number | null | undefined)[],
): MinutesHeatRange | null {
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY

  for (const minutes of allMinutes) {
    if (typeof minutes !== 'number' || minutes < 0) continue
    if (minutes < min) min = minutes
    if (minutes > max) max = minutes
  }

  if (!Number.isFinite(min) || !Number.isFinite(max)) return null
  return { min, max }
}

/** Same as `getMinutesHeatRange` but avoids allocating a `minutes[]` array first. */
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
): CSSProperties {
  if (!enabled || percentile === null) return {}
  const rgb = interpolateHeatmapRgb(percentile)
  return {
    backgroundColor: `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`,
    color: '#000000',
  }
}

/** Solid colour for profile bars / legends (same gradient). */
export function getPercentileTextColor(percentile: number | null): string {
  if (percentile === null) return 'rgba(78, 88, 120, 0.7)'
  const { r, g, b } = interpolateHeatmapRgb(percentile)
  return `rgb(${r}, ${g}, ${b})`
}
