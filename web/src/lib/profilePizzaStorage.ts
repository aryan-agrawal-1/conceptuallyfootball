import { PIZZA_SLICE_MIN, PIZZA_STORAGE_KEY, defaultPizzaMetricKeys } from './profileMetrics'
import type { PositionGroup } from '../types/api'

export function loadPizzaMetricKeys(fallbackPosition: PositionGroup): string[] {
  try {
    const raw = sessionStorage.getItem(PIZZA_STORAGE_KEY)
    if (!raw) return defaultPizzaMetricKeys(fallbackPosition)
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed) || parsed.length < PIZZA_SLICE_MIN) {
      return defaultPizzaMetricKeys(fallbackPosition)
    }
    return parsed.filter((k): k is string => typeof k === 'string')
  } catch {
    return defaultPizzaMetricKeys(fallbackPosition)
  }
}

export function savePizzaMetricKeys(keys: string[]) {
  sessionStorage.setItem(PIZZA_STORAGE_KEY, JSON.stringify(keys))
}
