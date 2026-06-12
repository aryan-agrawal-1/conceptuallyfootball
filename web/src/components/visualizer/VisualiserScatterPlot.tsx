import { useMemo, useState } from 'react'
import { scaleLinear } from 'd3-scale'
import { cn } from '../../lib/utils'
import { shortPlayerName } from '../../lib/entityLabels'

function quantile(values: number[], q: number): number {
  if (!values.length) return 0
  const sorted = values.toSorted((left, right) => left - right)
  const pos = (sorted.length - 1) * q
  const base = Math.floor(pos)
  const rest = pos - base
  const next = sorted[Math.min(base + 1, sorted.length - 1)] ?? sorted[base]
  return sorted[base] + rest * (next - sorted[base])
}

function robustExtent(values: number[]): [number, number] {
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) return [min - 1, max + 1]
  const qLow = quantile(values, 0.03)
  const qHigh = quantile(values, 0.97)
  const span = qHigh - qLow || max - min || 1
  const pad = span * 0.14
  return [qLow - pad, qHigh + pad]
}

export interface VisualiserScatterDatum {
  id: number
  label: string
  sublabel?: string
  x: number
  y: number
  xText: string
  yText: string
  tieBreak?: number
  highlighted?: boolean
}

interface VisualiserScatterPlotProps {
  points: VisualiserScatterDatum[]
  xLabel: string
  yLabel: string
  exportMode?: boolean
  showLabels?: boolean
  labelIds?: number[]
  shortenLabels?: boolean
  showTrendline?: boolean
  onSelect?: (id: number) => void
}

type LabelAnchor = 'start' | 'middle' | 'end'
type LabelRect = { left: number; right: number; top: number; bottom: number }
type LabelPlacement = { x: number; y: number; anchor: LabelAnchor; rect: LabelRect }

export function VisualiserScatterPlot({
  points,
  xLabel,
  yLabel,
  exportMode = false,
  showLabels = false,
  labelIds,
  shortenLabels = false,
  showTrendline = false,
  onSelect,
}: VisualiserScatterPlotProps) {
  const [hoverId, setHoverId] = useState<number | null>(null)
  const width = exportMode ? 980 : 720
  const height = exportMode ? 620 : 440
  const padLeft = exportMode ? 84 : 62
  const padRight = exportMode ? 36 : 28
  const padTop = exportMode ? 36 : 30
  const padBottom = exportMode ? 78 : 56

  const labelSet = useMemo(() => new Set(labelIds ?? []), [labelIds])

  const { xScale, yScale, mapped } = useMemo(() => {
    if (!points.length) {
      const emptyX = scaleLinear().domain([0, 1]).range([padLeft, width - padRight]).clamp(true)
      const emptyY = scaleLinear().domain([0, 1]).range([height - padBottom, padTop]).clamp(true)
      return {
        xScale: emptyX,
        yScale: emptyY,
        mapped: [] as Array<VisualiserScatterDatum & { cx: number; cy: number }>,
      }
    }

    const xs = points.map(point => point.x)
    const ys = points.map(point => point.y)
    const [xMin, xMax] = robustExtent(xs)
    const [yMin, yMax] = robustExtent(ys)
    const nextX = scaleLinear()
      .domain([xMin, xMax])
      .range([padLeft, width - padRight])
      .clamp(true)
    const nextY = scaleLinear()
      .domain([yMin, yMax])
      .range([height - padBottom, padTop])
      .clamp(true)
    const nextMapped = points.map(point => ({
      ...point,
      cx: nextX(point.x),
      cy: nextY(point.y),
    }))
    return {
      xScale: nextX,
      yScale: nextY,
      mapped: nextMapped,
    }
  }, [height, padBottom, padLeft, padRight, padTop, points, width])

  const xTicks = useMemo(() => xScale.ticks(6), [xScale])
  const yTicks = useMemo(() => yScale.ticks(6), [yScale])
  const trendline = useMemo(
    () => (showTrendline ? buildTrendline(points, xScale, yScale) : null),
    [points, showTrendline, xScale, yScale],
  )
  const placedLabels = useMemo(
    () =>
      placeScatterLabels({
        mapped,
        showLabels,
        labelSet,
        exportMode,
        width,
        height,
        padTop,
        padBottom,
        padLeft,
        padRight,
        shortenLabels,
      }),
    [exportMode, height, labelSet, mapped, padBottom, padLeft, padRight, padTop, shortenLabels, showLabels, width],
  )

  if (!points.length) {
    return <p className="py-12 text-center text-[12px] text-ink-muted">No points to plot for this cohort.</p>
  }

  const hovered = mapped.find(point => point.id === hoverId) ?? null

  return (
    <div className="relative flex justify-center">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto max-w-full text-electric/30"
        role="img"
        aria-label={`${xLabel} vs ${yLabel} scatter`}
        onMouseLeave={() => setHoverId(null)}
      >
        <rect
          x={padLeft}
          y={padTop}
          width={width - padLeft - padRight}
          height={height - padTop - padBottom}
          fill="rgba(7,8,16,0.45)"
          stroke="rgba(74,158,245,0.12)"
        />
        <line x1={padLeft} y1={height - padBottom} x2={width - padRight} y2={height - padBottom} stroke="currentColor" strokeWidth={1} />
        <line x1={padLeft} y1={padTop} x2={padLeft} y2={height - padBottom} stroke="currentColor" strokeWidth={1} />

        {xTicks.map(tick => (
          <g key={`x-${tick}`}>
            <line
              x1={xScale(tick)}
              y1={padTop}
              x2={xScale(tick)}
              y2={height - padBottom}
              stroke="rgba(74,158,245,0.08)"
              strokeWidth={1}
            />
            <text
              x={xScale(tick)}
              y={height - padBottom + (exportMode ? 28 : 20)}
              textAnchor="middle"
              fill="rgba(138,149,184,0.72)"
              fontSize={exportMode ? 12 : 9}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
            >
              {formatTick(tick)}
            </text>
          </g>
        ))}

        {yTicks.map(tick => (
          <g key={`y-${tick}`}>
            <line
              x1={padLeft}
              y1={yScale(tick)}
              x2={width - padRight}
              y2={yScale(tick)}
              stroke="rgba(74,158,245,0.08)"
              strokeWidth={1}
            />
            <text
              x={padLeft - (exportMode ? 14 : 10)}
              y={yScale(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fill="rgba(138,149,184,0.72)"
              fontSize={exportMode ? 12 : 9}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
            >
              {formatTick(tick)}
            </text>
          </g>
        ))}

        {trendline && (
          <g>
            <path
              d={trendline.path}
              fill="none"
              stroke="rgba(255,190,92,0.74)"
              strokeWidth={exportMode ? 2.2 : 1.6}
              strokeDasharray="6 5"
            />
            <text
              x={width - padRight}
              y={padTop - (exportMode ? 12 : 9)}
              textAnchor="end"
              fill="rgba(255,190,92,0.88)"
              fontSize={exportMode ? 13 : 10}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
            >
              r = {trendline.r.toFixed(2)} · R² = {trendline.r2.toFixed(2)}
            </text>
          </g>
        )}

        {mapped.map(point => {
          const active = point.highlighted || hoverId === point.id
          const placedLabel = placedLabels.get(point.id)
          return (
            <g key={point.id}>
              {placedLabel && (
                <text
                  x={placedLabel.x}
                  y={placedLabel.y}
                  textAnchor={placedLabel.anchor}
                  fill="rgba(138,149,184,0.92)"
                  fontSize={exportMode ? 13 : 10}
                  fontFamily="ui-monospace, SFMono-Regular, monospace"
                  style={{ pointerEvents: 'none' }}
                >
                  {shortenLabels ? shortPlayerName(point.label) : point.label}
                </text>
              )}
              <circle
                cx={point.cx}
                cy={point.cy}
                r={active ? 6.75 : 4.75}
                fill={point.highlighted ? 'rgba(255,190,92,0.95)' : 'rgba(74,158,245,0.82)'}
                stroke={active ? 'rgba(255,255,255,0.8)' : 'rgba(7,8,16,0.95)'}
                strokeWidth={active ? 1.4 : 1}
                className={cn(!exportMode && 'transition-[r,stroke-width]')}
              />
              {!exportMode && (
                <circle
                  cx={point.cx}
                  cy={point.cy}
                  r={14}
                  fill="transparent"
                  className={cn(onSelect && 'cursor-pointer')}
                  onMouseEnter={() => setHoverId(point.id)}
                  onClick={() => onSelect?.(point.id)}
                />
              )}
            </g>
          )
        })}

        <text
          x={width / 2}
          y={height - (exportMode ? 20 : 12)}
          textAnchor="middle"
          fill="rgba(138,149,184,0.92)"
          fontSize={exportMode ? 15 : 11}
          fontFamily="ui-monospace, SFMono-Regular, monospace"
        >
          {xLabel}
        </text>
        <text
          x={exportMode ? 24 : 16}
          y={height / 2}
          textAnchor="middle"
          transform={`rotate(-90 ${exportMode ? 24 : 16} ${height / 2})`}
          fill="rgba(138,149,184,0.92)"
          fontSize={exportMode ? 15 : 11}
          fontFamily="ui-monospace, SFMono-Regular, monospace"
        >
          {yLabel}
        </text>
      </svg>

      {!exportMode && hovered && (
        <div
          className="pointer-events-none absolute z-10 min-w-[180px] border border-electric/35 bg-panel/95 px-2.5 py-2 text-[11px] shadow-xl"
          style={{
            left: xScale(hovered.x),
            top: yScale(hovered.y),
            transform: 'translate(-50%, calc(-100% - 10px))',
          }}
        >
          <div className="text-[10px] font-semibold text-ink">{hovered.label}</div>
          {hovered.sublabel && <div className="mt-0.5 text-[10px] text-ink-muted">{hovered.sublabel}</div>}
          <div className="mt-1 font-mono text-electric/90">
            {xLabel}: {hovered.xText}
          </div>
          <div className="font-mono text-electric/90">
            {yLabel}: {hovered.yText}
          </div>
        </div>
      )}
    </div>
  )
}

function formatTick(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1000) {
    return new Intl.NumberFormat(undefined, {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  }
  if (abs >= 100) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(1).replace(/\.0$/, '')
  if (abs >= 1) return value.toFixed(2).replace(/0$/, '').replace(/\.0$/, '')
  return value.toFixed(2).replace(/0$/, '').replace(/\.0$/, '')
}

function buildTrendline(
  points: VisualiserScatterDatum[],
  xScale: ReturnType<typeof scaleLinear>,
  yScale: ReturnType<typeof scaleLinear>,
): { path: string; r: number; r2: number } | null {
  if (points.length < 2) return null
  const n = points.length
  const meanX = points.reduce((sum, point) => sum + point.x, 0) / n
  const meanY = points.reduce((sum, point) => sum + point.y, 0) / n
  let sxx = 0
  let syy = 0
  let sxy = 0
  for (const point of points) {
    const dx = point.x - meanX
    const dy = point.y - meanY
    sxx += dx * dx
    syy += dy * dy
    sxy += dx * dy
  }
  if (sxx === 0 || syy === 0) return null
  const slope = sxy / sxx
  const intercept = meanY - slope * meanX
  const [x0, x1] = xScale.domain() as [number, number]
  const y0 = slope * x0 + intercept
  const y1 = slope * x1 + intercept
  const r = sxy / Math.sqrt(sxx * syy)
  return {
    path: `M ${xScale(x0)} ${yScale(y0)} L ${xScale(x1)} ${yScale(y1)}`,
    r,
    r2: r * r,
  }
}

function placeScatterLabels({
  mapped,
  showLabels,
  labelSet,
  exportMode,
  width,
  height,
  padTop,
  padBottom,
  padLeft,
  padRight,
  shortenLabels,
}: {
  mapped: Array<VisualiserScatterDatum & { cx: number; cy: number }>
  showLabels: boolean
  labelSet: Set<number>
  exportMode: boolean
  width: number
  height: number
  padTop: number
  padBottom: number
  padLeft: number
  padRight: number
  shortenLabels: boolean
}): Map<number, { x: number; y: number; anchor: LabelAnchor }> {
  const placed = new Map<number, { x: number; y: number; anchor: LabelAnchor }>()
  if (!showLabels) return placed

  const fontSize = exportMode ? 13 : 10
  const labelPad = exportMode ? 9 : 7
  const candidates = [
    { dx: labelPad, dy: -labelPad, anchor: 'start' as const },
    { dx: labelPad, dy: labelPad + fontSize, anchor: 'start' as const },
    { dx: -labelPad, dy: -labelPad, anchor: 'end' as const },
    { dx: -labelPad, dy: labelPad + fontSize, anchor: 'end' as const },
    { dx: 0, dy: -(labelPad + fontSize), anchor: 'middle' as const },
    { dx: 0, dy: labelPad + fontSize * 1.3, anchor: 'middle' as const },
  ]
  const occupied: LabelRect[] = []
  const labeled = mapped
    .filter(point => labelSet.size === 0 || labelSet.has(point.id))
    .toSorted((left, right) => Number(Boolean(right.highlighted)) - Number(Boolean(left.highlighted)))

  for (const point of labeled) {
    const label = shortenLabels ? shortPlayerName(point.label) : point.label
    const approxWidth = Math.min(label.length * fontSize * 0.62 + 8, exportMode ? 220 : 160)
    const approxHeight = fontSize + 6
    let fallback: LabelPlacement | null = null
    for (const option of candidates) {
      const x = point.cx + option.dx
      const y = point.cy + option.dy
      const left = option.anchor === 'end' ? x - approxWidth : option.anchor === 'middle' ? x - approxWidth / 2 : x
      const right = left + approxWidth
      const top = y - approxHeight
      const bottom = y + 3
      const rect = { left, right, top, bottom }
      const inBounds =
        left >= Math.max(4, padLeft - 54) &&
        right <= width - Math.max(4, padRight - 16) &&
        top >= Math.max(4, padTop - 22) &&
        bottom <= height - Math.max(4, padBottom - 24)
      if (inBounds && !fallback) fallback = { x, y, anchor: option.anchor, rect }
      if (!inBounds) continue
      const collides = occupied.some(rect =>
        left < rect.right &&
        right > rect.left &&
        top < rect.bottom &&
        bottom > rect.top,
      )
      if (collides) continue
      occupied.push(rect)
      placed.set(point.id, { x, y, anchor: option.anchor })
      break
    }
    if (!placed.has(point.id)) {
      const option = fallback ?? {
        x: point.cx + candidates[0].dx,
        y: point.cy + candidates[0].dy,
        anchor: candidates[0].anchor,
        rect: {
          left: point.cx + candidates[0].dx,
          right: point.cx + candidates[0].dx + approxWidth,
          top: point.cy + candidates[0].dy - approxHeight,
          bottom: point.cy + candidates[0].dy + 3,
        },
      }
      occupied.push(option.rect)
      placed.set(point.id, { x: option.x, y: option.y, anchor: option.anchor })
    }
  }
  return placed
}
