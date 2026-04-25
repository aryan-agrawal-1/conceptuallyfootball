import type { MetricDefinition } from '../types/api'

type Unit = MetricDefinition['unit'] | 'score' | 'integer' | undefined

export function formatValue(value: number | null | undefined, unit: Unit): string {
  if (value === null || value === undefined) return '—'

  switch (unit) {
    case 'score':
      return Math.round(value).toString()
    case 'integer':
      return Math.round(value).toString()
    case 'percentage':
      return value.toFixed(1) + '%'
    case 'delta':
      return (value >= 0 ? '+' : '') + value.toFixed(2)
    case 'ratio':
    case 'share':
      return value.toFixed(3)
    case 'total':
      return value >= 10 ? value.toFixed(1) : value.toFixed(2)
    case 'per90':
      return value >= 10 ? value.toFixed(1) : value.toFixed(2)
    default:
      return value >= 100
        ? Math.round(value).toString()
        : value >= 10
          ? value.toFixed(1)
          : value.toFixed(2)
  }
}
