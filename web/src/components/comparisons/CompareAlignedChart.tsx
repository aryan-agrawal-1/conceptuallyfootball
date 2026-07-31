import { useMemo } from 'react'
import type { PlayerRow, PositionGroup, StatMeta } from '../../types/api'
import {
  barKindForMetricKey,
  radarGroupForMetric,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { formatValue } from '../../lib/format'
import {
  comparisonPercentileLabel,
  comparisonPlotPercentile,
  comparisonMarkerForSlot,
  COMPARISON_SLOT_STROKES,
} from '../../lib/comparisonConstants'
import { metricSemanticColor } from '../../lib/heatmap'
import { playerNameTitle, shortPlayerName } from '../../lib/entityLabels'
import { cn } from '../../lib/utils'
import {
  CompareMarkerIcon,
} from './CompareMarkerShape'

interface CompareAlignedPlayer {
  row: PlayerRow
  slot: number
}

interface CompareAlignedChartProps {
  metricKeys: string[]
  players: CompareAlignedPlayer[]
  meta: StatMeta
  positionGroup: PositionGroup
  rateMode: ProfileRateMode
  percentileMapForRow?: (row: PlayerRow) => Record<string, number | null>
  exportMode?: boolean
}

function playerRowKey(row: PlayerRow): string {
  return `${row.competition_code}:${row.season_label}:${row.canonical_player_id}`
}

function markerOffset(index: number, count: number): number {
  if (count === 2) return index === 0 ? -2 : 2
  if (count === 3) return (index - 1) * 7
  return 0
}

function semanticEnds(semantic: ReturnType<typeof metricSemanticColor>) {
  if (semantic === 'contextual') {
    return { left: 'Lower volume', right: 'Higher volume', note: 'Neutral low → high' }
  }
  if (semantic === 'negative') {
    return { left: 'Less favourable', right: 'More favourable', note: 'Lower is favourable' }
  }
  return { left: 'Less favourable', right: 'More favourable', note: 'Higher is favourable' }
}

export function CompareAlignedChart({
  metricKeys,
  players,
  meta,
  positionGroup,
  rateMode,
  percentileMapForRow,
  exportMode = false,
}: CompareAlignedChartProps) {
  const rows = useMemo(
    () =>
      metricKeys.map(key => {
        const barKind = barKindForMetricKey(key)
        const values = players.map(({ row, slot }) => {
          const resolved = resolveProfileMetric(
            row,
            rateMode,
            barKind,
            meta,
            percentileMapForRow?.(row) ?? row.percentiles,
          )
          const percentile = row.eligibility.percentiles_eligible ? resolved.percentile : null
          const semantic = metricSemanticColor(meta.metrics[resolved.metricKey] ?? meta.metrics[key])
          return {
            row,
            slot,
            metricKey: resolved.metricKey,
            raw: resolved.value,
            unit: resolved.formatUnit,
            percentile,
            plotPercentile: comparisonPlotPercentile(percentile, semantic),
          }
        })
        const metricDefinition = meta.metrics[values[0]?.metricKey ?? key] ?? meta.metrics[key]
        const semantic = metricSemanticColor(metricDefinition)
        const group = radarGroupForMetric(positionGroup, key, meta.metrics[key]?.group)
        return {
          key,
          label: stripPer90Suffix(meta.metrics[key]?.label ?? key),
          group,
          semantic,
          ends: semanticEnds(semantic),
          values,
        }
      }),
    [metricKeys, players, meta, positionGroup, rateMode, percentileMapForRow],
  )

  if (metricKeys.length === 0) {
    return <p className="py-12 text-center text-[12px] text-ink-muted">Select stats to plot.</p>
  }

  return (
    <div className={cn('w-full', exportMode && 'px-2')}>
      <div
        className={cn(
          'mb-3 grid items-center gap-3 border-b border-electric/15 pb-3',
          exportMode ? 'grid-cols-[220px_minmax(0,1fr)]' : 'sm:grid-cols-[180px_minmax(0,1fr)]',
        )}
      >
        <div className="hidden text-[9px] uppercase tracking-[0.2em] text-ink-muted sm:block">
          Metric
        </div>
        <div className="flex justify-between gap-4 text-[9px] uppercase tracking-[0.16em] text-ink-muted">
          <span>Scale start</span>
          <span>Scale end</span>
        </div>
      </div>

      <div className="divide-y divide-electric/10 border-y border-electric/10">
        {rows.map(row => {
          const plotted = row.values.flatMap(value =>
            value.plotPercentile == null ? [] : [value.plotPercentile],
          )
          const connector =
            players.length === 2 && plotted.length === 2
              ? { left: Math.min(...plotted), width: Math.abs(plotted[1] - plotted[0]) }
              : null
          return (
            <div
              key={row.key}
              className={cn(
                'grid gap-x-3 gap-y-2 py-3',
                exportMode ? 'grid-cols-[220px_minmax(0,1fr)]' : 'sm:grid-cols-[180px_minmax(0,1fr)]',
              )}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="h-4 w-1 shrink-0"
                    style={{ backgroundColor: row.group.color }}
                    aria-hidden="true"
                  />
                  <p className={cn('truncate font-semibold text-ink', exportMode ? 'text-[14px]' : 'text-[12px]')}>
                    {row.label}
                  </p>
                </div>
                <p
                  className={cn('mt-1 truncate uppercase tracking-[0.13em] text-ink-muted', exportMode ? 'text-[10px]' : 'text-[9px]')}
                  style={{ color: row.group.color }}
                >
                  {row.group.label}
                </p>
              </div>

              <div className="min-w-0">
                <div className="mb-1 flex items-center justify-between gap-3 text-[8px] uppercase tracking-[0.12em] text-ink-muted">
                  <span>{row.ends.left}</span>
                  <span className="text-right">{row.ends.right}</span>
                </div>
                <div className={cn('relative', exportMode ? 'h-10' : 'h-9')}>
                  <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line-bright/70" />
                  {[25, 50, 75].map(tick => (
                    <span
                      key={tick}
                      className="absolute top-1/2 h-2.5 w-px -translate-y-1/2 bg-line-bright/55"
                      style={{ left: `${tick}%` }}
                      aria-hidden="true"
                    />
                  ))}
                  {connector && (
                    <span
                      className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-ink-muted/65"
                      style={{ left: `${connector.left}%`, width: `${connector.width}%` }}
                      aria-hidden="true"
                    />
                  )}
                  {row.values.map((value, index) => {
                    if (value.plotPercentile == null) return null
                    const color = COMPARISON_SLOT_STROKES[value.slot % COMPARISON_SLOT_STROKES.length]
                    const shape = comparisonMarkerForSlot(value.slot)
                    const rawLabel = formatValue(value.raw, value.unit)
                    const percentileLabel =
                      value.percentile == null
                        ? 'percentile unavailable'
                        : comparisonPercentileLabel(value.percentile)
                    const accessibleLabel = `${value.row.canonical_player_name}, ${row.label}: ${rawLabel}, ${percentileLabel}. ${row.ends.note}.`
                    return (
                      <span
                        key={`${playerRowKey(value.row)}-${row.key}`}
                        role="img"
                        tabIndex={exportMode ? undefined : 0}
                        aria-label={exportMode ? undefined : accessibleLabel}
                        title={exportMode ? undefined : accessibleLabel}
                        className="group absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 outline-none"
                        style={{
                          left: `${value.plotPercentile}%`,
                          marginTop: markerOffset(index, row.values.length),
                        }}
                      >
                        <CompareMarkerIcon
                          slot={value.slot}
                          color={color}
                          className={cn(
                            exportMode ? 'size-4 border-2' : 'size-3.5 border-2',
                            'shadow-[0_0_0_2px_rgba(7,8,16,0.92)]',
                          )}
                        />
                        {!exportMode && (
                          <span className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-30 hidden min-w-[190px] -translate-x-1/2 border border-electric/35 bg-panel/95 px-2.5 py-2 text-[10px] leading-relaxed text-ink shadow-xl group-hover:block group-focus:block">
                            <span className="block text-ink-muted">{value.row.canonical_player_name}</span>
                            <span className="mt-0.5 block font-mono tabular-nums">
                              {rawLabel} · Pctl {value.percentile == null ? '—' : Math.round(value.percentile)}
                            </span>
                            <span className="mt-1 block text-[9px] text-ink-muted">
                              {shape} marker · {row.ends.note}
                            </span>
                          </span>
                        )}
                      </span>
                    )
                  })}
                </div>
                <div
                  className={cn(
                    'grid gap-x-3 gap-y-1',
                    row.values.length === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2',
                    exportMode && (row.values.length === 3 ? 'grid-cols-3' : 'grid-cols-2'),
                  )}
                >
                  {row.values.map(value => {
                    const color = COMPARISON_SLOT_STROKES[value.slot % COMPARISON_SLOT_STROKES.length]
                    return (
                      <div
                        key={`readout-${playerRowKey(value.row)}-${row.key}`}
                        className="flex min-w-0 items-center gap-1.5 text-[9px] font-mono tabular-nums"
                      >
                        <CompareMarkerIcon slot={value.slot} color={color} className="size-2" />
                        <span
                          className="truncate"
                          title={playerNameTitle(value.row.canonical_player_name)}
                          style={{ color }}
                        >
                          {shortPlayerName(value.row.canonical_player_name)}
                        </span>
                        <span className="shrink-0 text-ink-dim">
                          {formatValue(value.raw, value.unit)} · P{value.percentile == null ? '—' : Math.round(value.percentile)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
