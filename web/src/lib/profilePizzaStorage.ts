import {
  LEGACY_PIZZA_STORAGE_KEY,
  PIZZA_SLICE_MIN,
  PIZZA_SLICE_SOFT_MAX,
  PIZZA_STORAGE_KEY,
  dedupeCanonicalMetricKeys,
  defaultPizzaMetricKeys,
  resolveRadarMetricKeys,
} from './profileMetrics'
import type { PositionGroup } from '../types/api'

interface StoredPizzaAxes {
  version: 2
  positions: Partial<Record<PositionGroup, string[]>>
}

function parseMetricKeys(raw: string | null): string[] | null {
  if (!raw) return null
  const parsed = JSON.parse(raw) as unknown
  if (!Array.isArray(parsed)) return null
  return parsed.filter((key): key is string => typeof key === 'string')
}

export function loadPizzaMetricKeys(fallbackPosition: PositionGroup): string[] {
  try {
    const raw = sessionStorage.getItem(PIZZA_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredPizzaAxes>
      const stored = parsed.version === 2 ? parsed.positions?.[fallbackPosition] : null
      if (Array.isArray(stored) && stored.length >= PIZZA_SLICE_MIN) {
        const stringKeys = stored.filter((key): key is string => typeof key === 'string')
        const deduped = dedupeCanonicalMetricKeys(stringKeys)
        return resolveRadarMetricKeys({
          position: fallbackPosition,
          current: deduped,
          available: [...stringKeys, ...defaultPizzaMetricKeys(fallbackPosition)],
          targetCount: Math.max(PIZZA_SLICE_MIN, Math.min(stringKeys.length, PIZZA_SLICE_SOFT_MAX)),
        })
      }
    }

    const legacy = parseMetricKeys(sessionStorage.getItem(LEGACY_PIZZA_STORAGE_KEY))
    if (legacy?.length) {
      const migrated = resolveRadarMetricKeys({
        position: fallbackPosition,
        current: dedupeCanonicalMetricKeys(legacy),
        available: [...legacy, ...defaultPizzaMetricKeys(fallbackPosition)],
        targetCount: PIZZA_SLICE_SOFT_MAX,
      })
      savePizzaMetricKeys(fallbackPosition, migrated)
      sessionStorage.removeItem(LEGACY_PIZZA_STORAGE_KEY)
      return migrated
    }

    return defaultPizzaMetricKeys(fallbackPosition)
  } catch {
    return defaultPizzaMetricKeys(fallbackPosition)
  }
}

export function savePizzaMetricKeys(position: PositionGroup, keys: string[]) {
  try {
    const raw = sessionStorage.getItem(PIZZA_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) as Partial<StoredPizzaAxes> : null
    const state: StoredPizzaAxes = {
      version: 2,
      positions: parsed?.version === 2 && parsed.positions ? parsed.positions : {},
    }
    state.positions[position] = dedupeCanonicalMetricKeys(keys)
    sessionStorage.setItem(PIZZA_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Storage can be unavailable in private browsing or constrained embeds.
  }
}
