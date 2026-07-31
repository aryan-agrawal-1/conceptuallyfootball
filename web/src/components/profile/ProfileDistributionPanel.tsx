import { useMemo } from 'react'
import { formatValue } from '../../lib/format'
import { distributionBenchmark } from '../../lib/profileDistributions'
import {
  barKindForMetricKey,
  radarGroupForMetric,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import type {
  MetricSemanticColor,
  PlayerRow,
  ProfileDistributionPayload,
  ProfileMetricDistribution,
  StatMeta,
} from '../../types/api'

interface ProfileDistributionPanelProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  metricKeys: string[]
  distributions?: ProfileDistributionPayload
  percentileMap?: Record<string, number | null>
  compact?: boolean
  light?: boolean
}

function distributionForMode(
  metricKey: string,
  rateMode: ProfileRateMode,
  resolvedMetricKey: string,
  payload: ProfileDistributionPayload,
): ProfileMetricDistribution | undefined {
  const base = payload.metrics[metricKey]
  const kind = barKindForMetricKey(metricKey)
  if (rateMode === 'full' && kind.kind === 'derivedSeasonFromPer90') {
    return base?.season_approx
  }
  return payload.metrics[resolvedMetricKey] ?? base
}

export function ProfileDistributionPanel({
  player,
  rateMode,
  meta,
  metricKeys,
  distributions,
  percentileMap = player.percentiles,
  compact = false,
  light = false,
}: ProfileDistributionPanelProps) {
  const rows = useMemo(
    () =>
      metricKeys.flatMap(metricKey => {
        if (!distributions) return []
        const resolved = resolveProfileMetric(
          player,
          rateMode,
          barKindForMetricKey(metricKey),
          meta,
          percentileMap,
        )
        const distribution = distributionForMode(
          metricKey,
          rateMode,
          resolved.metricKey,
          distributions,
        )
        if (!distribution || resolved.value == null) return []
        const semanticColor = meta.metrics[resolved.metricKey]?.semantic_color ?? 'positive'
        return [{
          metricKey,
          resolved,
          value: resolved.value,
          distribution,
          semanticColor,
          group: radarGroupForMetric(
            player.position_group,
            metricKey,
            meta.metrics[resolved.metricKey]?.group,
          ),
        }]
      }),
    [distributions, meta, metricKeys, percentileMap, player, rateMode],
  )

  if (!distributions || rows.length === 0) {
    return (
      <p className={light ? 'text-[12px] text-slate-600' : 'text-[12px] text-ink-muted'}>
        Distribution context is unavailable for this cohort.
      </p>
    )
  }

  const scopeLabel = `${distributions.context.competition_code} ${distributions.context.season_label}`

  return (
    <div>
      {!compact && (
        <div className="mb-4">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-electric">
                Cohort distributions
              </p>
              <p className="mt-1 text-[11px] text-ink-muted">
                Same {player.position_group === 'UNK' ? 'player' : player.position_group} cohort and percentile scope as the polar profile.
              </p>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-muted">
              {scopeLabel} · {distributions.cohort_count} eligible
            </p>
          </div>
          <div className="mt-3 border border-electric/15 bg-electric/[0.035] px-3 py-3">
            <p className="text-[9px] font-bold uppercase tracking-[0.2em] text-electric/85">
              How to read these
            </p>
            <p className="mt-1.5 max-w-5xl text-[10px] leading-relaxed text-ink-dim">
              Each strip shows where the eligible players sit from the lowest value on the
              left to the highest on the right. Taller bars mean more players fall in that
              range; they do not automatically mean better performance.
            </p>
            <ul className="mt-2 grid gap-x-6 gap-y-1 text-[9px] leading-relaxed text-ink-muted sm:grid-cols-2">
              <li><span className="font-bold text-ink-dim">Bright line + triangle:</span> this player&apos;s value.</li>
              <li><span className="font-bold text-ink-dim">P number:</span> percentile within this exact cohort.</li>
              <li><span className="font-bold text-ink-dim">Solid + dashed lines:</span> median and the middle 50% of players.</li>
              <li><span className="font-bold text-ink-dim">Coloured dot:</span> favourable quartile for directional metrics; contextual metrics omit it.</li>
            </ul>
          </div>
        </div>
      )}
      <div className={compact ? 'grid grid-cols-2 gap-3' : 'grid gap-3 md:grid-cols-2'}>
        {rows.map(row => (
          <DistributionStrip
            key={row.metricKey}
            label={stripPer90Suffix(meta.metrics[row.resolved.metricKey]?.label ?? row.metricKey)}
            value={row.value}
            percentile={row.resolved.percentile}
            formatUnit={row.resolved.formatUnit}
            distribution={row.distribution}
            semanticColor={row.semanticColor}
            color={row.group.color}
            compact={compact}
            light={light}
          />
        ))}
      </div>
    </div>
  )
}

function DistributionStrip({
  label,
  value,
  percentile,
  formatUnit,
  distribution,
  semanticColor,
  color,
  compact,
  light,
}: {
  label: string
  value: number
  percentile: number | null
  formatUnit: Parameters<typeof formatValue>[1]
  distribution: ProfileMetricDistribution
  semanticColor: MetricSemanticColor
  color: string
  compact: boolean
  light: boolean
}) {
  const width = 420
  const height = compact ? 82 : 96
  const chartTop = compact ? 28 : 34
  const chartBottom = height - 18
  const plotHeight = chartBottom - chartTop
  const maxBinCount = Math.max(1, ...distribution.bins.map(bin => bin.count))
  const domainSpan = distribution.max - distribution.min
  const x = (raw: number) => (
    domainSpan <= 0 ? width / 2 : ((raw - distribution.min) / domainSpan) * width
  )
  const benchmark = distributionBenchmark(distribution, semanticColor)
  const markerX = Math.max(0, Math.min(width, x(value)))
  const textColor = light ? '#10131A' : '#E4EAF8'
  const mutedColor = light ? '#596070' : '#8A95B8'
  const gridColor = light ? 'rgba(16,19,26,0.18)' : 'rgba(138,149,184,0.24)'

  return (
    <figure
      className={compact ? 'border p-3' : 'border border-electric/15 bg-mat/35 p-3'}
      style={compact ? { borderColor: `${color}44`, background: light ? 'rgba(255,255,255,0.38)' : 'rgba(7,8,16,0.32)' } : undefined}
      aria-label={`${label} distribution. Player value ${formatValue(value, formatUnit)}, percentile ${percentile == null ? 'unavailable' : Math.round(percentile)}.`}
    >
      <figcaption className="flex items-start justify-between gap-3">
        <span style={{ color }} className={compact ? 'text-[11px] font-bold uppercase tracking-[0.12em]' : 'text-[10px] font-bold uppercase tracking-[0.16em]'}>
          {label}
        </span>
        <span style={{ color: textColor }} className="font-mono text-[11px] font-bold tabular-nums">
          {formatValue(value, formatUnit)}
          {percentile != null && <span style={{ color: mutedColor }}> · P{Math.round(percentile)}</span>}
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-1 h-auto w-full overflow-visible"
        role="img"
        aria-hidden="true"
      >
        {distribution.bins.map((bin, index) => {
          const start = x(bin.start)
          const end = x(bin.end)
          const barWidth = Math.max(2, end - start - 2)
          const barHeight = (bin.count / maxBinCount) * plotHeight
          return (
            <rect
              key={`${bin.start}:${bin.end}:${index}`}
              x={start + 1}
              y={chartBottom - barHeight}
              width={barWidth}
              height={barHeight}
              rx={1}
              fill={color}
              fillOpacity={0.28 + (bin.count / maxBinCount) * 0.34}
            />
          )
        })}
        {[distribution.p25, distribution.median, distribution.p75].map((quartile, index) => (
          <line
            key={`${quartile}:${index}`}
            x1={x(quartile)}
            x2={x(quartile)}
            y1={chartTop - 3}
            y2={chartBottom + 2}
            stroke={index === 1 ? textColor : gridColor}
            strokeWidth={index === 1 ? 1.5 : 1}
            strokeDasharray={index === 1 ? undefined : '3 3'}
          />
        ))}
        {benchmark && (
          <circle
            cx={x(benchmark.value)}
            cy={chartTop - 7}
            r={3}
            fill={color}
          />
        )}
        <line
          x1={markerX}
          x2={markerX}
          y1={chartTop - 10}
          y2={chartBottom + 4}
          stroke={color}
          strokeWidth={3}
        />
        <path
          d={`M ${markerX - 5} ${chartTop - 12} L ${markerX + 5} ${chartTop - 12} L ${markerX} ${chartTop - 5} Z`}
          fill={color}
        />
        <text x={0} y={height - 3} fill={mutedColor} fontSize={9} fontFamily="ui-monospace, monospace">
          {formatValue(distribution.min, formatUnit)}
        </text>
        <text x={width} y={height - 3} fill={mutedColor} fontSize={9} textAnchor="end" fontFamily="ui-monospace, monospace">
          {formatValue(distribution.max, formatUnit)}
        </text>
      </svg>
      {!compact && (
        <p style={{ color: mutedColor }} className="mt-1 text-[9px] leading-relaxed">
          Q1 · median · Q3
          {benchmark
            ? ` · ${benchmark.label}: ${formatValue(benchmark.value, formatUnit)}`
            : ' · contextual metric: neither quartile is labelled elite'}
        </p>
      )}
    </figure>
  )
}
