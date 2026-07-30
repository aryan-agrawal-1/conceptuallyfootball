import type {
  MetricSemanticColor,
  ProfileMetricDistribution,
} from '../types/api'

export function distributionBenchmark(
  distribution: ProfileMetricDistribution,
  semanticColor: MetricSemanticColor,
): { label: string; value: number } | null {
  if (semanticColor === 'positive') {
    return { label: 'Favourable quartile', value: distribution.p75 }
  }
  if (semanticColor === 'negative') {
    return { label: 'Favourable quartile', value: distribution.p25 }
  }
  return null
}
