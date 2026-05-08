import { useEffect, useMemo, useRef, useState } from 'react'
import { arc as d3Arc } from 'd3-shape'
import { scaleLinear } from 'd3-scale'
import { ChevronDown, X } from 'lucide-react'
import { HudCornerMarks, HudFrame } from '../hud/Hud'
import { formatValue } from '../../lib/format'
import type { PlayerRow, StatMeta } from '../../types/api'
import {
  PIZZA_SLICE_MIN,
  PIZZA_SLICE_SOFT_MAX,
  barKindForMetricKey,
  defaultPizzaMetricKeys,
  groupMetricsForPizzaPicker,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { loadPizzaMetricKeys, savePizzaMetricKeys } from '../../lib/profilePizzaStorage'
import { getPercentileTextColor } from '../../lib/heatmap'
import { cn } from '../../lib/utils'
import { ChartShareCard } from '../visualizer/ChartShareCard'

interface ProfilePizzaSectionProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
}

export function ProfilePizzaSection({ player, rateMode, meta }: ProfilePizzaSectionProps) {
  return (
    <ProfilePizzaSectionInner
      key={`${player.canonical_player_id}:${player.position_group}`}
      player={player}
      rateMode={rateMode}
      meta={meta}
    />
  )
}

function ProfilePizzaSectionInner({ player, rateMode, meta }: ProfilePizzaSectionProps) {
  const [keys, setKeys] = useState<string[]>(() => loadPizzaMetricKeys(player.position_group))
  const warnMax = keys.length > PIZZA_SLICE_SOFT_MAX
  const rawOnly = !player.eligibility.percentiles_eligible

  useEffect(() => {
    savePizzaMetricKeys(keys)
  }, [keys])

  const validKeys = useMemo(
    () =>
      keys.filter(
        k => {
          if (!(k in meta.metrics) || (player.position_group === 'GK' && k === 'rating')) {
            return false
          }
          const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(k), meta)
          return resolved.value != null
        },
      ),
    [keys, meta, player, rateMode],
  )

  const usableKeySet = useMemo(() => {
    const out = new Set<string>()
    for (const key of Object.keys(meta.metrics)) {
      if (player.position_group === 'GK' && key === 'rating') continue
      const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(key), meta)
      if (resolved.value != null) out.add(key)
    }
    return out
  }, [meta, player, rateMode])

  const sectionOrder = useMemo(() => Object.keys(meta.metric_groups), [meta.metric_groups])

  const chartKeys = useMemo(() => {
    if (validKeys.length >= PIZZA_SLICE_MIN) return validKeys
    const pad = defaultPizzaMetricKeys(player.position_group).filter(
      k => {
        if (!(k in meta.metrics) || validKeys.includes(k)) return false
        const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(k), meta)
        return resolved.value != null
      },
    )
    return [...validKeys, ...pad].slice(0, Math.max(PIZZA_SLICE_MIN, validKeys.length))
  }, [validKeys, meta, player, rateMode])

  useEffect(() => {
    if (keys.length === chartKeys.length && keys.every((key, index) => key === chartKeys[index])) return
    setKeys(chartKeys)
    // Only sync when the loaded/stored axes are invalid for this player scope.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartKeys])

  function removeKey(k: string) {
    setKeys(prev => {
      if (prev.length <= PIZZA_SLICE_MIN) return prev
      return prev.filter(x => x !== k)
    })
  }

  function addKey(k: string) {
    setKeys(prev => (prev.includes(k) ? prev : [...prev, k]))
  }

  return (
    <HudFrame
      header={<span>{rawOnly ? 'Polar profile // Raw axes' : 'Polar profile // Percentile shape'}</span>}
      className="w-full"
      footer={
        rawOnly ? (
          <span className="text-electric/75">Equal-length slices show selected raw metrics only</span>
        ) : warnMax ? (
          <span className="text-amber-400/90">
            {keys.length} axes — above {PIZZA_SLICE_SOFT_MAX} slices can get crowded.
          </span>
        ) : undefined
      }
    >
      <div className="p-4 flex flex-col lg:flex-row gap-8 items-start">
        <div className="flex-1 flex flex-col gap-4 justify-center w-full min-w-0">
          <div className="flex justify-end">
            <ChartShareCard
              title={`${player.canonical_player_name} · Polar profile`}
              subtitle={`${player.season_label} · ${player.canonical_team_name ?? 'No club'} · ${rateMode === 'per90' ? 'per 90 view' : 'season view'} · ${chartKeys.length} axes`}
              contextLabel="Player Profile · Polar chart"
              fileName={`${player.canonical_player_name}-polar-profile`}
              aspect="square"
              renderContent={({ exportMode }) => (
                <ProfilePizzaSvg
                  player={player}
                  rateMode={rateMode}
                  meta={meta}
                  metricKeys={chartKeys}
                  exportMode={exportMode}
                />
              )}
            />
          </div>
          <div className="flex justify-center w-full min-w-0">
            <ProfilePizzaSvg
              player={player}
              rateMode={rateMode}
              meta={meta}
              metricKeys={chartKeys}
            />
          </div>
        </div>
        <PizzaAxisPicker
          meta={meta}
          sectionOrder={sectionOrder}
          excludeMetricKeys={player.position_group === 'GK' ? ['rating'] : undefined}
          usableKeys={usableKeySet}
          selectedKeys={validKeys}
          onRemove={removeKey}
          onAdd={addKey}
          canRemove={validKeys.length > PIZZA_SLICE_MIN}
        />
      </div>
    </HudFrame>
  )
}

interface ProfilePizzaSvgProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  metricKeys: string[]
  exportMode?: boolean
}

/** Polar helpers — d3-arc convention (angle 0 = 12 o'clock, clockwise). */
function polar(angle: number, radius: number): { x: number; y: number } {
  return { x: Math.sin(angle) * radius, y: -Math.cos(angle) * radius }
}

const CHART_SIZE = 460
const INNER_R = 48
const BAND = 140

function ProfilePizzaSvg({ player, rateMode, meta, metricKeys, exportMode = false }: ProfilePizzaSvgProps) {
  const chartSize = exportMode ? 760 : CHART_SIZE
  const chartCenter = chartSize / 2
  const innerR = exportMode ? 82 : INNER_R
  const band = exportMode ? 220 : BAND
  const outerR = innerR + band
  const labelRingR = outerR + (exportMode ? 36 : 20)
  const chartWrapRef = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState<{
    label: string
    percentile: number | null
    x: number
    y: number
  } | null>(null)

  function pointerToLocal(clientX: number, clientY: number) {
    const el = chartWrapRef.current
    if (!el) return { x: clientX, y: clientY }
    const r = el.getBoundingClientRect()
    return { x: clientX - r.left, y: clientY - r.top }
  }

  const slices = useMemo(() => {
    const n = Math.max(metricKeys.length, 1)
    const pad = 0.02
    const total = Math.PI * 2
    const span = total / n
    const rScale = scaleLinear().domain([0, 100]).range([0, band])

    return metricKeys.map((key, i) => {
      const kind = barKindForMetricKey(key)
      const resolved = resolveProfileMetric(player, rateMode, kind, meta)
      const pctEligible = player.eligibility.percentiles_eligible
      const pct = pctEligible ? (resolved.percentile ?? 0) : 62
      const outer = innerR + rScale(pct)
      const start = i * span + pad
      const end = (i + 1) * span - pad
      const mid = (start + end) / 2

      const arcGen = d3Arc<unknown>()
        .innerRadius(innerR)
        .outerRadius(outer)
        .startAngle(start)
        .endAngle(end)
      const dPath = arcGen(null as unknown as Record<string, never>) ?? ''

      const inner = polar(mid, (innerR + outer) / 2)
      const outerLabel = polar(mid, labelRingR)

      return {
        key,
        d: dPath,
        fill: pctEligible ? getPercentileTextColor(pct) : 'rgba(74, 158, 245, 0.28)',
        valueFill: pctEligible ? '#000000' : '#E4EAF8',
        label: stripPer90Suffix(meta.metrics[key]?.label ?? key),
        raw: resolved.value,
        formatUnit: resolved.formatUnit,
        percentile: pctEligible ? resolved.percentile : null,
        inner,
        outerLabel,
        midDeg: (mid * 180) / Math.PI,
      }
    })
  }, [band, innerR, labelRingR, metricKeys, player, rateMode, meta])

  if (metricKeys.length === 0) {
    return (
      <p className="text-[12px] text-ink-muted text-center py-12">
        Select at least {PIZZA_SLICE_MIN} metrics below.
      </p>
    )
  }

  return (
    <div ref={chartWrapRef} className="relative inline-block">
      <svg
        width={chartSize}
        height={chartSize}
        viewBox={`0 0 ${chartSize} ${chartSize}`}
        className="text-electric/25 overflow-visible"
        role="img"
        aria-label={player.eligibility.percentiles_eligible ? 'Player percentile pizza chart' : 'Player raw metric polar chart'}
      >
        <g transform={`translate(${chartCenter}, ${chartCenter})`}>
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

          {slices.map(s => (
            <path
              key={s.key}
              d={s.d}
              fill={s.fill}
              fillOpacity={0.85}
              stroke="rgba(7,8,16,0.9)"
              strokeWidth={1.5}
              className="cursor-crosshair transition-[fill-opacity] hover:fill-opacity-100"
              onMouseEnter={e => {
                if (exportMode) return
                const { x, y } = pointerToLocal(e.clientX, e.clientY)
                setTip({ label: s.label, percentile: s.percentile, x, y })
              }}
              onMouseLeave={() => {
                if (exportMode) return
                setTip(null)
              }}
              onMouseMove={e => {
                if (exportMode) return
                const { x, y } = pointerToLocal(e.clientX, e.clientY)
                setTip(prev =>
                  prev
                    ? { ...prev, x, y }
                    : { label: s.label, percentile: s.percentile, x, y },
                )
              }}
            />
          ))}

          {slices.map(s => (
            <text
              key={`v-${s.key}`}
              x={s.inner.x}
              y={s.inner.y}
              fill={s.valueFill}
              fontSize={exportMode ? 16 : 11}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
              textAnchor="middle"
              dominantBaseline="middle"
              pointerEvents="none"
            >
              {formatValue(s.raw, s.formatUnit)}
            </text>
          ))}

          {slices.map(s => (
            <OuterLabel
              key={`l-${s.key}`}
              x={s.outerLabel.x}
              y={s.outerLabel.y}
              midDeg={s.midDeg}
              text={s.label}
              exportMode={exportMode}
            />
          ))}

          <circle r={innerR - 2} fill="#070810" stroke="#1F2438" strokeWidth={1} />
        </g>
      </svg>

      {tip && (
        <div
          className="absolute z-[100] pointer-events-none px-2.5 py-1.5 border border-electric/40 bg-panel/95 text-[11px] text-ink shadow-xl font-mono tabular-nums"
          style={{
            left: tip.x,
            top: tip.y,
            transform: 'translate(-50%, calc(-100% - 6px))',
          }}
        >
          <div className="text-ink-muted text-[9px] uppercase tracking-[0.2em] mb-0.5">
            {tip.label}
          </div>
          <div>
            Rank <span className="text-electric">{tip.percentile != null ? Math.round(tip.percentile) : 'Raw'}</span>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Outer-rim label. Rotates to sit tangent to the chart so it reads along the
 * circumference; flips upright on the lower half.
 */
function OuterLabel({
  x,
  y,
  midDeg,
  text,
  exportMode,
}: {
  x: number
  y: number
  midDeg: number
  text: string
  exportMode: boolean
}) {
  const normalized = ((midDeg % 360) + 360) % 360
  const flip = normalized > 90 && normalized < 270
  const rotation = flip ? midDeg + 180 : midDeg
  return (
    <text
      x={x}
      y={y}
      fill="#8A95B8"
      fontSize={exportMode ? 13 : 9}
      fontWeight={600}
      fontFamily="ui-monospace, SFMono-Regular, monospace"
      textAnchor="middle"
      dominantBaseline="middle"
      transform={`rotate(${rotation} ${x} ${y})`}
      style={{ letterSpacing: '0.08em', textTransform: 'uppercase' }}
      pointerEvents="none"
    >
      {text}
    </text>
  )
}

interface PizzaAxisPickerProps {
  meta: StatMeta
  sectionOrder: string[]
  /** Metrics omitted from the add-stat list (e.g. GK `rating`). */
  excludeMetricKeys?: readonly string[]
  selectedKeys: string[]
  usableKeys: Set<string>
  canRemove: boolean
  onRemove: (k: string) => void
  onAdd: (k: string) => void
}

function PizzaAxisPicker({
  meta,
  sectionOrder,
  excludeMetricKeys,
  selectedKeys,
  usableKeys,
  canRemove,
  onRemove,
  onAdd,
}: PizzaAxisPickerProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const grouped = useMemo(
    () =>
      groupMetricsForPizzaPicker(
        meta,
        excludeMetricKeys?.length ? [...excludeMetricKeys] : undefined,
      ),
    [meta, excludeMetricKeys],
  )

  const available = useMemo(() => {
    const sel = new Set(selectedKeys)
    return sectionOrder.flatMap(sec =>
      (grouped[sec] ?? [])
        .filter(({ key }) => !sel.has(key))
        .filter(({ key }) => usableKeys.has(key))
        .map(item => ({ ...item, section: sec })),
    )
  }, [grouped, sectionOrder, selectedKeys, usableKeys])

  return (
    <div className="w-full max-w-sm flex flex-col gap-3" ref={ref}>
      <p className="text-[10px] uppercase tracking-[0.2em] text-electric/80">Active axes</p>
      <div className="flex flex-wrap gap-1.5">
        {selectedKeys.map(k => {
          const label = stripPer90Suffix(meta.metrics[k]?.label ?? k)
          return (
            <button
              key={k}
              type="button"
              disabled={!canRemove}
              onClick={() => onRemove(k)}
              className={cn(
                'relative flex items-center gap-1 pl-2 pr-1 py-1 text-[10px] uppercase tracking-wide border',
                canRemove
                  ? 'border-electric/35 bg-electric/5 text-ink-dim hover:text-ink hover:border-electric/60'
                  : 'border-line opacity-50 cursor-not-allowed',
              )}
            >
              {canRemove && <HudCornerMarks size="size-1" />}
              <span className="truncate max-w-[140px]">{label}</span>
              <X size={11} className="opacity-60 shrink-0" />
            </button>
          )
        })}
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="relative w-full flex items-center justify-between gap-2 px-3 py-2 border border-electric/25 text-[11px] uppercase tracking-[0.15em] text-electric/90 hover:bg-electric/5"
        >
          <span>Add stat</span>
          <ChevronDown size={14} className={cn('transition-transform', open && 'rotate-180')} />
        </button>
        {open && (
          <div className="absolute left-0 right-0 top-full mt-1 z-50 max-h-64 overflow-y-auto border border-electric/25 bg-panel/98 shadow-xl">
            {available.length === 0 ? (
              <p className="p-3 text-[11px] text-ink-muted">All metrics selected.</p>
            ) : (
              sectionOrder.map(sec => {
                const items = available.filter(a => a.section === sec)
                if (!items.length) return null
                return (
                  <div key={sec} className="border-b border-electric/10 last:border-0">
                    <p className="px-2 py-1.5 text-[9px] uppercase tracking-widest text-ink-muted bg-mat/80 sticky top-0">
                      {meta.metric_groups[sec] ?? sec}
                    </p>
                    {items.map(({ key, label }) => (
                      <button
                        key={key}
                        type="button"
                        className="w-full text-left px-3 py-1.5 text-[12px] text-ink-dim hover:bg-electric/10 hover:text-ink"
                        onClick={() => {
                          onAdd(key)
                          setOpen(false)
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )
              })
            )}
          </div>
        )}
      </div>
      <p className="text-[10px] text-ink-muted leading-relaxed">
        Axes persist for this browser tab (session). Minimum {PIZZA_SLICE_MIN} slices; add up to your
        tolerance (we warn past {PIZZA_SLICE_SOFT_MAX}).
      </p>
    </div>
  )
}
