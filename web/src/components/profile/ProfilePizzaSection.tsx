import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { arc as d3Arc } from 'd3-shape'
import { scaleLinear } from 'd3-scale'
import { ArrowLeft, ArrowRight, ChevronDown, SlidersHorizontal, X } from 'lucide-react'
import { HudCornerMarks, HudFrame } from '../hud/Hud'
import { formatValue } from '../../lib/format'
import type {
  PlayerRow,
  ProfileDistributionPayload,
  StatMeta,
} from '../../types/api'
import {
  PIZZA_SLICE_MIN,
  PIZZA_SLICE_SOFT_MAX,
  barKindForMetricKey,
  canonicalProfileMetricKey,
  defaultPizzaMetricKeys,
  dedupeCanonicalMetricKeys,
  groupMetricsForPizzaPicker,
  moveMetricKey,
  radarLabelLines,
  radarGroupForMetric,
  radarTemplateGroups,
  resolveRadarMetricKeys,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { loadPizzaMetricKeys, savePizzaMetricKeys } from '../../lib/profilePizzaStorage'
import { BRAND_LOGO_URL } from '../../lib/brand'
import {
  getPercentileTextColor,
  metricSemanticColor,
} from '../../lib/heatmap'
import { shortPlayerName } from '../../lib/entityLabels'
import { cn } from '../../lib/utils'
import { ChartShareCard } from '../visualizer/ChartShareCard'
import { ProfileDistributionPanel } from './ProfileDistributionPanel'

interface ProfilePizzaSectionProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  percentileMap?: Record<string, number | null>
  distributions?: ProfileDistributionPayload
}

export function ProfilePizzaSection({ player, rateMode, meta, percentileMap, distributions }: ProfilePizzaSectionProps) {
  return (
    <ProfilePizzaSectionInner
      key={`${player.canonical_player_id}:${player.position_group}`}
      player={player}
      rateMode={rateMode}
      meta={meta}
      percentileMap={percentileMap}
      distributions={distributions}
    />
  )
}

function ProfilePizzaSectionInner({
  player,
  rateMode,
  meta,
  percentileMap = player.percentiles,
  distributions,
}: ProfilePizzaSectionProps) {
  const [keys, setKeys] = useState<string[]>(() => loadPizzaMetricKeys(player.position_group))
  const [showDistributions, setShowDistributions] = useState(false)
  const warnMax = keys.length > PIZZA_SLICE_SOFT_MAX
  const rawOnly = !player.eligibility.percentiles_eligible

  useEffect(() => {
    savePizzaMetricKeys(player.position_group, keys)
  }, [keys, player.position_group])

  const validKeys = useMemo(
    () =>
      keys.filter(
        k => {
          if (!(k in meta.metrics) || (player.position_group === 'GK' && k === 'rating')) {
            return false
          }
          const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(k), meta, percentileMap)
          return resolved.value != null
        },
      ),
    [keys, meta, percentileMap, player, rateMode],
  )

  const usableKeySet = useMemo(() => {
    const out = new Set<string>()
    for (const key of Object.keys(meta.metrics)) {
      if (player.position_group === 'GK' && key === 'rating') continue
      const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(key), meta, percentileMap)
      if (resolved.value != null) out.add(key)
    }
    return out
  }, [meta, percentileMap, player, rateMode])

  const sectionOrder = useMemo(() => Object.keys(meta.metric_groups), [meta.metric_groups])

  const chartKeys = useMemo(
    () =>
      resolveRadarMetricKeys({
        position: player.position_group,
        current: validKeys,
        available: [...usableKeySet],
        targetCount: Math.max(
          PIZZA_SLICE_MIN,
          Math.min(keys.length || defaultPizzaMetricKeys(player.position_group).length, PIZZA_SLICE_SOFT_MAX),
        ),
      }),
    [keys.length, player.position_group, usableKeySet, validKeys],
  )

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
    setKeys(prev => dedupeCanonicalMetricKeys([...prev, k]))
  }

  function moveKey(k: string, direction: -1 | 1) {
    setKeys(prev => moveMetricKey(prev, k, direction))
  }

  const groupLegend = radarTemplateGroups(player.position_group)

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
      <div className="flex flex-col gap-5 p-3 sm:p-4">
        <div className="flex flex-col gap-3 border-b border-electric/10 pb-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {groupLegend.map(group => {
              const count = chartKeys.filter(key =>
                radarGroupForMetric(player.position_group, key, meta.metrics[key]?.group).id === group.id
              ).length
              return (
                <div
                  key={group.id}
                  className="flex items-center justify-between gap-4 border px-3 py-2"
                  style={{ borderColor: `${group.color}44`, background: `${group.color}0D` }}
                >
                  <span className="text-[9px] font-bold uppercase tracking-[0.18em]" style={{ color: group.color }}>
                    {group.label}
                  </span>
                  <span className="font-mono text-[10px] text-ink-muted">{count}</span>
                </div>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              aria-expanded={showDistributions}
              onClick={() => setShowDistributions(current => !current)}
              className="flex items-center gap-1.5 border border-control-border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10"
            >
              <SlidersHorizontal size={13} />
              {showDistributions ? 'Hide distributions' : 'Inspect distributions'}
            </button>
            <ChartShareCard
              title={`${shortPlayerName(player.canonical_player_name)} · Polar profile`}
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
                  percentileMap={percentileMap}
                  exportMode={exportMode}
                />
              )}
            />
          </div>
        </div>
        <div className="flex flex-col items-start gap-5 lg:flex-row lg:gap-8">
          <div className="flex w-full min-w-0 flex-1 flex-col justify-center gap-4">
            <div className="flex w-full min-w-0 justify-center">
              <ProfilePizzaSvg
                player={player}
                rateMode={rateMode}
                meta={meta}
                metricKeys={chartKeys}
                percentileMap={percentileMap}
              />
            </div>
          </div>
          <PizzaAxisPicker
            position={player.position_group}
            meta={meta}
            sectionOrder={sectionOrder}
            excludeMetricKeys={player.position_group === 'GK' ? ['rating'] : undefined}
            usableKeys={usableKeySet}
            selectedKeys={chartKeys}
            onRemove={removeKey}
            onAdd={addKey}
            onMove={moveKey}
            canRemove={chartKeys.length > PIZZA_SLICE_MIN}
          />
        </div>
        {showDistributions && (
          <div className="border-t border-electric/10 pt-5">
            <ProfileDistributionPanel
              player={player}
              rateMode={rateMode}
              meta={meta}
              metricKeys={chartKeys}
              distributions={distributions}
              percentileMap={percentileMap}
            />
          </div>
        )}
      </div>
    </HudFrame>
  )
}

interface ProfilePizzaSvgProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  metricKeys: string[]
  percentileMap?: Record<string, number | null>
  exportMode?: boolean
}

/** Polar helpers — d3-arc convention (angle 0 = 12 o'clock, clockwise). */
function polar(angle: number, radius: number): { x: number; y: number } {
  return { x: Math.sin(angle) * radius, y: -Math.cos(angle) * radius }
}

const CHART_SIZE = 460
const INNER_R = 48
const BAND = 140

function formatSliceValue(raw: number | null, percentile: number | null, formatUnit: Parameters<typeof formatValue>[1]): string {
  return percentile != null ? String(Math.round(percentile)) : formatValue(raw, formatUnit)
}

export function ProfilePizzaSvg({
  player,
  rateMode,
  meta,
  metricKeys,
  percentileMap = player.percentiles,
  exportMode = false,
}: ProfilePizzaSvgProps) {
  const reactId = useId()
  const chartSize = exportMode ? 760 : CHART_SIZE
  const chartCenter = chartSize / 2
  const innerR = exportMode ? 82 : INNER_R
  const band = exportMode ? 220 : BAND
  const outerR = innerR + band
  const labelRingR = outerR + (exportMode ? 36 : 20)
  const logoClipId = `pizza-logo-clip-${reactId.replace(/:/g, '')}`
  const logoSize = innerR * 1.45

  const slices = useMemo(() => {
    const n = Math.max(metricKeys.length, 1)
    const pad = 0.02
    const total = Math.PI * 2
    const span = total / n
    const rScale = scaleLinear().domain([0, 100]).range([0, band])

    return metricKeys.map((key, i) => {
      const kind = barKindForMetricKey(key)
      const resolved = resolveProfileMetric(player, rateMode, kind, meta, percentileMap)
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
      const group = radarGroupForMetric(
        player.position_group,
        key,
        meta.metrics[resolved.metricKey]?.group,
      )
      const groupArc = d3Arc<unknown>()
        .innerRadius(outerR + (exportMode ? 8 : 4))
        .outerRadius(outerR + (exportMode ? 18 : 10))
        .startAngle(start)
        .endAngle(end)

      const inner = polar(mid, (innerR + outer) / 2)
      const outerLabel = polar(mid, labelRingR)

      return {
        key,
        d: dPath,
        groupD: groupArc(null as unknown as Record<string, never>) ?? '',
        group,
        fill: pctEligible
          ? getPercentileTextColor(
              pct,
              metricSemanticColor(meta.metrics[resolved.metricKey]),
            )
          : 'rgba(74, 158, 245, 0.28)',
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
  }, [band, exportMode, innerR, labelRingR, metricKeys, outerR, player, rateMode, meta, percentileMap])

  if (metricKeys.length === 0) {
    return (
      <p className="text-[12px] text-ink-muted text-center py-12">
        Select at least {PIZZA_SLICE_MIN} metrics below.
      </p>
    )
  }

  return (
    <div className="relative inline-block max-w-full">
      <svg
        width={chartSize}
        height={chartSize}
        viewBox={`0 0 ${chartSize} ${chartSize}`}
        className="h-auto max-w-full overflow-visible text-electric/25"
        role="img"
        aria-label={player.eligibility.percentiles_eligible ? 'Player percentile pizza chart' : 'Player raw metric polar chart'}
      >
        <defs>
          <clipPath id={logoClipId}>
            <circle r={innerR - 8} />
          </clipPath>
        </defs>
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
            />
          ))}

          {slices.map(s => (
            <path
              key={`group-${s.key}`}
              d={s.groupD}
              fill={s.group.color}
              fillOpacity={0.92}
              pointerEvents="none"
            />
          ))}

          {slices.map(s => (
            <text
              key={`v-${s.key}`}
              x={s.inner.x}
              y={s.inner.y}
              fill={s.valueFill}
              fontSize={exportMode ? 18 : 11}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
              textAnchor="middle"
              dominantBaseline="middle"
              pointerEvents="none"
            >
              {formatSliceValue(s.raw, s.percentile, s.formatUnit)}
            </text>
          ))}

          {slices.map(s => (
            <OuterLabel
              key={`l-${s.key}`}
              x={s.outerLabel.x}
              y={s.outerLabel.y}
              midDeg={s.midDeg}
              text={s.label}
              color={s.group.color}
              exportMode={exportMode}
            />
          ))}

          <circle r={innerR - 2} fill="#070810" stroke="#1F2438" strokeWidth={1} />
          <image
            href={BRAND_LOGO_URL}
            x={-logoSize / 2}
            y={-logoSize / 2}
            width={logoSize}
            height={logoSize}
            preserveAspectRatio="xMidYMid meet"
            clipPath={`url(#${logoClipId})`}
            pointerEvents="none"
          />
        </g>
      </svg>
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
  color,
  exportMode,
}: {
  x: number
  y: number
  midDeg: number
  text: string
  color: string
  exportMode: boolean
}) {
  const normalized = ((midDeg % 360) + 360) % 360
  const flip = normalized > 90 && normalized < 270
  const rotation = flip ? midDeg + 180 : midDeg
  const lines = radarLabelLines(text)
  return (
    <text
      x={x}
      y={y}
      fill={color}
      fontSize={exportMode ? 15 : 9}
      fontWeight={600}
      fontFamily="ui-monospace, SFMono-Regular, monospace"
      textAnchor="middle"
      dominantBaseline="middle"
      transform={`rotate(${rotation} ${x} ${y})`}
      style={{ letterSpacing: '0.08em', textTransform: 'uppercase' }}
      pointerEvents="none"
    >
      {lines.map((line, index) => (
        <tspan
          key={line}
          x={x}
          dy={lines.length === 1 ? 0 : index === 0 ? '-0.55em' : '1.1em'}
        >
          {line}
        </tspan>
      ))}
    </text>
  )
}

interface PizzaAxisPickerProps {
  position: PlayerRow['position_group']
  meta: StatMeta
  sectionOrder: string[]
  /** Metrics omitted from the add-stat list (e.g. GK `rating`). */
  excludeMetricKeys?: readonly string[]
  selectedKeys: string[]
  usableKeys: Set<string>
  canRemove: boolean
  onRemove: (k: string) => void
  onAdd: (k: string) => void
  onMove: (k: string, direction: -1 | 1) => void
}

function PizzaAxisPicker({
  position,
  meta,
  sectionOrder,
  excludeMetricKeys,
  selectedKeys,
  usableKeys,
  canRemove,
  onRemove,
  onAdd,
  onMove,
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
    if (selectedKeys.length >= PIZZA_SLICE_SOFT_MAX) return []
    const selectedCanonical = new Set(selectedKeys.map(canonicalProfileMetricKey))
    return sectionOrder.flatMap(sec =>
      (grouped[sec] ?? []).flatMap(item =>
        !selectedCanonical.has(canonicalProfileMetricKey(item.key)) && usableKeys.has(item.key)
          ? [{ ...item, section: sec }]
          : [],
      ),
    )
  }, [grouped, sectionOrder, selectedKeys, usableKeys])

  return (
    <div className="w-full max-w-sm flex flex-col gap-3" ref={ref}>
      <p className="text-[10px] uppercase tracking-[0.2em] text-electric/80">Active axes</p>
      <div className="flex flex-wrap gap-1.5">
        {selectedKeys.map((k, index) => {
          const label = stripPer90Suffix(meta.metrics[k]?.label ?? k)
          const group = radarGroupForMetric(
            position,
            k,
            meta.metrics[k]?.group,
          )
          return (
            <div
              key={k}
              className="relative flex items-center border bg-electric/5 text-[10px] uppercase tracking-wide text-control-fg"
              style={{ borderColor: `${group.color}55` }}
            >
              <HudCornerMarks size="size-1" />
              <span className="max-w-[120px] truncate py-1 pl-2 pr-1">{label}</span>
              <button
                type="button"
                disabled={index === 0}
                onClick={() => onMove(k, -1)}
                className="grid size-6 place-items-center text-control-fg transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={`Move ${label} earlier`}
              >
                <ArrowLeft size={10} />
              </button>
              <button
                type="button"
                disabled={index === selectedKeys.length - 1}
                onClick={() => onMove(k, 1)}
                className="grid size-6 place-items-center text-control-fg transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={`Move ${label} later`}
              >
                <ArrowRight size={10} />
              </button>
              <button
                type="button"
                disabled={!canRemove}
                onClick={() => onRemove(k)}
                className="grid size-6 place-items-center text-control-fg transition-colors hover:text-ember disabled:cursor-not-allowed disabled:opacity-30"
                aria-label={`Remove ${label}`}
              >
                <X size={10} />
              </button>
            </div>
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
              <p className="p-3 text-[11px] text-ink-muted">
                {selectedKeys.length >= PIZZA_SLICE_SOFT_MAX
                  ? `Maximum ${PIZZA_SLICE_SOFT_MAX} axes selected.`
                  : 'All metrics selected.'}
              </p>
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
        Axes persist by position for this browser tab. Minimum {PIZZA_SLICE_MIN}; maximum{' '}
        {PIZZA_SLICE_SOFT_MAX}. Use the arrow controls to keep the shape order stable.
      </p>
    </div>
  )
}
