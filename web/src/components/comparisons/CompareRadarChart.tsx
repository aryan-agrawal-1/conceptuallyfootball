import { useId, useMemo, useRef, useState } from 'react'
import { scaleLinear } from 'd3-scale'
import type { PlayerRow, StatMeta } from '../../types/api'
import {
  barKindForMetricKey,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { formatValue } from '../../lib/format'
import {
  COMPARISON_SLOT_FILLS,
  COMPARISON_SLOT_STROKES,
} from '../../lib/comparisonConstants'
import { cn } from '../../lib/utils'

const CHART_SIZE = 440
const INNER_R = 52
const BAND = 132

function polar(theta: number, r: number): { x: number; y: number } {
  return { x: Math.sin(theta) * r, y: -Math.cos(theta) * r }
}

function buildClosedPath(points: { x: number; y: number }[]): string {
  if (!points.length) return ''
  const [p0, ...rest] = points
  return `M ${p0.x} ${p0.y} ${rest.map(p => `L ${p.x} ${p.y}`).join(' ')} Z`
}

function playerRowKey(row: PlayerRow): string {
  return `${row.competition_code}:${row.season_label}:${row.canonical_player_id}`
}

interface CompareRadarPlayer {
  row: PlayerRow
  slot: number
}

interface CompareRadarChartProps {
  metricKeys: string[]
  players: CompareRadarPlayer[]
  meta: StatMeta
  rateMode: ProfileRateMode
  hoveredStatIndex: number | null
  lockedStatIndex: number | null
  onHoverStat: (index: number | null) => void
  onClickStat: (index: number | null) => void
  percentileMapForRow?: (row: PlayerRow) => Record<string, number | null>
  exportMode?: boolean
}

export function CompareRadarChart({
  metricKeys,
  players,
  meta,
  rateMode,
  hoveredStatIndex,
  lockedStatIndex,
  onHoverStat,
  onClickStat,
  percentileMapForRow,
  exportMode = false,
}: CompareRadarChartProps) {
  const chartSize = exportMode ? 720 : CHART_SIZE
  const chartCenter = chartSize / 2
  const innerR = exportMode ? 86 : INNER_R
  const band = exportMode ? 214 : BAND
  const outerR = innerR + band
  const labelR = outerR + (exportMode ? 36 : 22)
  const coreFillId = useId().replace(/:/g, '')
  const wrapRef = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<{
    statIndex: number
    x: number
    y: number
  } | null>(null)

  function pointerToLocal(clientX: number, clientY: number) {
    const el = wrapRef.current
    if (!el) return { x: clientX, y: clientY }
    const r = el.getBoundingClientRect()
    return { x: clientX - r.left, y: clientY - r.top }
  }

  const axes = useMemo(() => {
    const n = Math.max(metricKeys.length, 1)
    const rScale = scaleLinear().domain([0, 100]).range([0, band])
    const span = (Math.PI * 2) / n

    return metricKeys.map((key, i) => {
      const theta = -Math.PI / 2 + i * span
      const labelPt = polar(theta, labelR)
      const midDeg = (theta * 180) / Math.PI

      const playerPoints = players.map(({ row, slot }) => {
        const kind = barKindForMetricKey(key)
        const resolved = resolveProfileMetric(row, rateMode, kind, meta, percentileMapForRow?.(row) ?? row.percentiles)
        const pctOk = row.eligibility.percentiles_eligible
        const pct = pctOk ? (resolved.percentile ?? 0) : 0
        const r = innerR + rScale(pct)
        const pt = polar(theta, r)
        return {
          slot,
          pt,
          pct: pctOk ? resolved.percentile : null,
          raw: resolved.value,
          formatUnit: resolved.formatUnit,
          pctOk,
          stroke: COMPARISON_SLOT_STROKES[slot % COMPARISON_SLOT_STROKES.length],
        }
      })

      return {
        key,
        theta,
        label: stripPer90Suffix(meta.metrics[key]?.label ?? key),
        labelPt,
        midDeg,
        playerPoints,
      }
    })
  }, [band, innerR, labelR, metricKeys, players, meta, rateMode, percentileMapForRow])

  const activeTipIndex = tip?.statIndex ?? null
  const highlightIndex = lockedStatIndex ?? hoveredStatIndex ?? activeTipIndex

  if (metricKeys.length === 0) {
    return (
      <p className="text-[12px] text-ink-muted text-center py-12">Select stats to plot.</p>
    )
  }

  return (
    <div ref={wrapRef} className="relative flex justify-center w-full min-w-0">
      <div className="flex flex-col items-center gap-4">
        <svg
          width={chartSize}
          height={chartSize}
          viewBox={`0 0 ${chartSize} ${chartSize}`}
          className="h-auto max-w-full overflow-visible text-electric/25"
          role="img"
          aria-label="Player comparison radar chart"
        >
          <g transform={`translate(${chartCenter}, ${chartCenter})`}>
            <circle
              r={innerR}
              fill={`url(#${coreFillId})`}
              stroke="rgba(74, 158, 245, 0.12)"
              strokeWidth={1}
            />
            {[0.25, 0.5, 0.75, 1].map((t, idx) => (
              <circle
                key={idx}
                r={innerR + t * band}
                fill="none"
                stroke="currentColor"
                strokeWidth={1}
                strokeDasharray={idx === 3 ? undefined : '2 4'}
              />
            ))}

            {axes.map((ax, i) => {
              const outer = polar(ax.theta, outerR)
              return (
                <line
                  key={`spoke-${ax.key}`}
                  x1={0}
                  y1={0}
                  x2={outer.x}
                  y2={outer.y}
                  stroke="currentColor"
                  strokeWidth={1}
                  strokeOpacity={highlightIndex === i ? 0.55 : 0.35}
                />
              )
            })}

            {players.map(({ row, slot }) => {
              if (!row.eligibility.percentiles_eligible) return null
              const pts = axes.map(ax => {
                const found = ax.playerPoints.find(p => p.slot === slot)
                return found?.pt
              })
              if (pts.some(p => !p)) return null
              const path = buildClosedPath(pts as { x: number; y: number }[])
              const fill = COMPARISON_SLOT_FILLS[slot % COMPARISON_SLOT_FILLS.length]
              const stroke = COMPARISON_SLOT_STROKES[slot % COMPARISON_SLOT_STROKES.length]
              return (
                <path
                  key={`poly-${playerRowKey(row)}`}
                  d={path}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={1.75}
                  fillOpacity={1}
                  className="pointer-events-none"
                />
              )
            })}

            {players.map(({ row, slot }) => {
              if (!row.eligibility.percentiles_eligible) return null
              return axes.map((ax, i) => {
                const pp = ax.playerPoints.find(p => p.slot === slot)
                if (!pp) return null
                return (
                  <g key={`node-${playerRowKey(row)}-${ax.key}`}>
                    <circle
                      cx={pp.pt.x}
                      cy={pp.pt.y}
                      r={exportMode ? 0 : 14}
                      fill="transparent"
                      className="cursor-crosshair"
                      onMouseEnter={e => {
                        if (exportMode) return
                        const { x, y } = pointerToLocal(e.clientX, e.clientY)
                        onHoverStat(i)
                        setTip({ statIndex: i, x, y })
                      }}
                      onMouseMove={e => {
                        if (exportMode) return
                        const { x, y } = pointerToLocal(e.clientX, e.clientY)
                        setTip(prev => (prev ? { ...prev, x, y } : { statIndex: i, x, y }))
                      }}
                      onMouseLeave={() => {
                        if (exportMode) return
                        onHoverStat(null)
                        setTip(null)
                      }}
                    />
                    <circle
                      cx={pp.pt.x}
                      cy={pp.pt.y}
                      r={4}
                      fill={pp.stroke}
                      stroke="rgba(7,8,16,0.95)"
                      strokeWidth={1}
                      pointerEvents="none"
                    />
                  </g>
                )
              })
            })}

            {axes.map((ax, i) => {
              const active = highlightIndex === i
              return (
                <AxisLabelButton
                  key={`lbl-${ax.key}`}
                  x={ax.labelPt.x}
                  y={ax.labelPt.y}
                  midDeg={ax.midDeg}
                  text={ax.label}
                  active={active}
                  exportMode={exportMode}
                  onEnter={() => onHoverStat(i)}
                  onLeave={() => onHoverStat(null)}
                  onClick={() => onClickStat(lockedStatIndex === i ? null : i)}
                />
              )
            })}
          </g>
        </svg>

        <div className={cn('flex flex-wrap justify-center', exportMode ? 'gap-3' : 'gap-2')}>
          {players.map(({ row, slot }) => (
            <div
              key={`legend-${row.canonical_player_id}`}
              className={cn('border border-electric/20 bg-panel/55', exportMode ? 'px-4 py-3' : 'px-3 py-2')}
            >
              <div className="flex items-center gap-2">
                <span
                  className="size-2 rounded-full"
                  style={{ background: COMPARISON_SLOT_STROKES[slot % COMPARISON_SLOT_STROKES.length] }}
                />
                <span className={cn('font-medium text-ink', exportMode ? 'text-[15px]' : 'text-[12px]')}>
                  {row.canonical_player_name}
                </span>
              </div>
              {row.canonical_team_name && (
                <div className={cn('mt-1 text-ink-muted', exportMode ? 'text-[12px]' : 'text-[10px]')}>
                  {row.canonical_team_name}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {tip != null && tip.statIndex >= 0 && tip.statIndex < axes.length && (
        <div
          className="absolute z-[100] pointer-events-none min-w-[180px] max-w-[min(100%,280px)] px-2.5 py-2 border border-electric/40 bg-panel/95 text-[11px] text-ink shadow-xl font-mono tabular-nums"
          style={{
            left: tip.x,
            top: tip.y,
            transform: 'translate(-50%, calc(-100% - 8px))',
          }}
        >
          <div className="text-ink-muted text-[9px] uppercase tracking-[0.2em] mb-1">
            {axes[tip.statIndex].label}
          </div>
          <div className="flex flex-col gap-1">
            {players.map(({ row, slot }) => {
              const ax = axes[tip.statIndex]
              const pp = ax.playerPoints.find(p => p.slot === slot)
              if (!pp) return null
              const kind = barKindForMetricKey(ax.key)
              const resolved = resolveProfileMetric(row, rateMode, kind, meta)
              return (
                <div key={row.canonical_player_id} className="flex items-baseline justify-between gap-2">
                  <span
                    className="truncate text-[10px] text-ink-dim"
                    style={{ color: pp.stroke }}
                  >
                    {row.canonical_player_name}
                  </span>
                  <span className="shrink-0 text-electric/90">
                    {formatValue(resolved.value, resolved.formatUnit)}
                    <span className="text-ink-muted mx-1">·</span>
                    Pctl{' '}
                    {pp.pctOk && pp.pct != null ? Math.round(pp.pct) : '—'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function AxisLabelButton({
  x,
  y,
  midDeg,
  text,
  active,
  onEnter,
  onLeave,
  onClick,
  exportMode,
}: {
  x: number
  y: number
  midDeg: number
  text: string
  onEnter: () => void
  onLeave: () => void
  onClick: () => void
  active: boolean
  exportMode: boolean
}) {
  const normalized = ((midDeg % 360) + 360) % 360
  const flip = normalized > 90 && normalized < 270
  const rotation = flip ? midDeg + 180 : midDeg
  return (
    <text
      x={x}
      y={y}
      fill={active ? 'rgba(74, 158, 245, 0.95)' : '#8A95B8'}
      fontSize={exportMode ? 13 : 9}
      fontWeight={600}
      fontFamily="ui-monospace, SFMono-Regular, monospace"
      textAnchor="middle"
      dominantBaseline="middle"
      transform={`rotate(${rotation} ${x} ${y})`}
      style={{ letterSpacing: '0.08em', textTransform: 'uppercase', cursor: exportMode ? 'default' : 'pointer' }}
      className={cn('select-none', active && 'underline decoration-electric/50')}
      onMouseEnter={() => {
        if (!exportMode) onEnter()
      }}
      onMouseLeave={() => {
        if (!exportMode) onLeave()
      }}
      onClick={e => {
        if (exportMode) return
        e.stopPropagation()
        onClick()
      }}
      onKeyDown={e => {
        if (exportMode) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      tabIndex={exportMode ? -1 : 0}
      role={exportMode ? undefined : 'button'}
    >
      {text}
    </text>
  )
}
