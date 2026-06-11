import { HudFrame } from '../hud/Hud'
import { formatValue } from '../../lib/format'
import type { PlayerRow, StatMeta } from '../../types/api'
import {
  barKindForMetricKey,
  labelForBarSpec,
  profileBarSpecsForPosition,
  resolveProfileMetric,
  headerSpecsForPosition,
  resolveHeaderCard,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { cn } from '../../lib/utils'
import { getPercentileTextColor } from '../../lib/heatmap'

interface ProfileKeyStatsProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  percentileMap?: Record<string, number | null>
}

export function ProfileKeyStats({ player, rateMode, meta, percentileMap = player.percentiles }: ProfileKeyStatsProps) {
  const rawOnly = !player.eligibility.percentiles_eligible
  const seen = new Set<string>()
  const standoutSpecs = profileBarSpecsForPosition(player.position_group)
    .flatMap(spec => {
      const resolved = resolveProfileMetric(player, rateMode, spec.bar, meta, percentileMap)
      if (resolved.value == null || resolved.percentile == null) return []
      if (seen.has(resolved.metricKey)) return []
      seen.add(resolved.metricKey)
      return [{
        id: spec.id,
        label: labelForBarSpec(spec, meta),
        resolved,
      }]
    })
    .toSorted((left, right) =>
      (right.resolved.percentile ?? 0) - (left.resolved.percentile ?? 0) ||
      (right.resolved.value ?? 0) - (left.resolved.value ?? 0),
    )
    .slice(0, 4)

  const fallbackSpecs = headerSpecsForPosition(player.position_group).flatMap(spec => {
    const resolved = resolveHeaderCard(player, rateMode, spec, meta, percentileMap)
    return resolved.value == null ? [] : [{ spec, resolved }]
  })
  const usedMetricKeys = new Set(fallbackSpecs.map(({ resolved }) => resolved.metricKey))
  const rawFallbackSpecs = Object.entries(meta.metrics).flatMap(([key, def]) => {
    if (usedMetricKeys.has(key)) return []
    if (player.position_group === 'GK' && key === 'rating') return []
    const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(key), meta, percentileMap)
    if (resolved.value == null) return []
    return [
      {
        spec: {
          id: `fallback-${key}`,
          label: stripPer90Suffix(def.label),
          bar: barKindForMetricKey(key),
        },
        resolved: { ...resolved, label: stripPer90Suffix(def.label) },
      },
    ]
  })
  const rawSpecs = [...fallbackSpecs, ...rawFallbackSpecs].slice(0, 4)
  const displaySpecs = !rawOnly && standoutSpecs.length ? standoutSpecs : rawSpecs

  return (
    <HudFrame
      header={<span>Signal // Standout traits</span>}
      footer={
        rawOnly ? (
          <span className="text-electric/75">Percentile traits unlock once the sample is eligible</span>
        ) : undefined
      }
      className="w-full"
    >
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-0 divide-x divide-electric/10 border-t border-electric/10">
        {displaySpecs.map(item => {
          const id = 'spec' in item ? item.spec.id : item.id
          const label = 'spec' in item ? item.resolved.label : item.label
          const r = item.resolved
          const pct = !rawOnly && r.percentile != null ? r.percentile : null
          const pc = pct != null ? getPercentileTextColor(pct) : undefined
          return (
            <div
              key={id}
              className={cn(
                'p-4 flex flex-col gap-2 min-h-[96px]',
                rawOnly && 'bg-electric/[0.03]',
              )}
            >
              <span className="text-[10px] font-medium tracking-[0.2em] uppercase text-ink-muted">
                {label}
              </span>
              <span className="text-[26px] font-black text-ink leading-none tabular-nums">
                {formatValue(r.value, r.formatUnit)}
              </span>
              <div className="mt-auto flex items-center gap-2">
                <span className="text-[9px] tracking-[0.15em] uppercase text-ink-muted">
                  {rawOnly ? 'Rank' : 'Pctl'}
                </span>
                <span
                  className={cn(
                    'text-[12px] font-mono font-bold tabular-nums px-2 py-0.5 rounded border border-line-bright/60',
                    rawOnly
                      ? 'text-electric/85 border-electric/25 bg-electric/10 text-[10px] tracking-[0.12em] uppercase'
                      : pct == null && 'text-ink-muted border-line/50',
                  )}
                  style={
                    pct != null
                      ? { color: pc, borderColor: `${pc}55`, backgroundColor: `${pc}18` }
                      : undefined
                  }
                >
                  {rawOnly ? 'Raw' : pct != null ? Math.round(pct) : '—'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </HudFrame>
  )
}
