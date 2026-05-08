import { HudFrame } from '../hud/Hud'
import { formatValue } from '../../lib/format'
import type { PlayerRow, StatMeta } from '../../types/api'
import {
  barKindForMetricKey,
  headerSpecsForPosition,
  resolveProfileMetric,
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
}

export function ProfileKeyStats({ player, rateMode, meta }: ProfileKeyStatsProps) {
  const primarySpecs = headerSpecsForPosition(player.position_group)
    .map(spec => ({ spec, resolved: resolveHeaderCard(player, rateMode, spec, meta) }))
    .filter(({ resolved }) => resolved.value != null)
  const usedMetricKeys = new Set(primarySpecs.map(({ resolved }) => resolved.metricKey))
  const fallbackSpecs = Object.entries(meta.metrics)
    .map(([key, def]) => {
      if (usedMetricKeys.has(key)) return null
      if (player.position_group === 'GK' && key === 'rating') return null
      const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(key), meta)
      if (resolved.value == null) return null
      return {
        spec: {
          id: `fallback-${key}`,
          label: stripPer90Suffix(def.label),
          bar: barKindForMetricKey(key),
        },
        resolved: { ...resolved, label: stripPer90Suffix(def.label) },
      }
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry != null)
  const specs = [...primarySpecs, ...fallbackSpecs].slice(0, 4)
  const rawOnly = !player.eligibility.percentiles_eligible

  return (
    <HudFrame
      header={<span>Signal // Key metrics</span>}
      footer={
        rawOnly ? (
          <span className="text-electric/75">Raw metric values · not percentile ranked</span>
        ) : undefined
      }
      className="w-full"
    >
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-0 divide-x divide-electric/10 border-t border-electric/10">
        {specs.map(({ spec, resolved: r }) => {
          const pct = !rawOnly && r.percentile != null ? r.percentile : null
          const pc = pct != null ? getPercentileTextColor(pct) : undefined
          return (
            <div
              key={spec.id}
              className={cn(
                'p-4 flex flex-col gap-2 min-h-[96px]',
                rawOnly && 'bg-electric/[0.03]',
              )}
            >
              <span className="text-[10px] font-medium tracking-[0.2em] uppercase text-ink-muted">
                {r.label}
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
