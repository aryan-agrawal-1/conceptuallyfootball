import { useMemo, useState } from 'react'
import { scaleLinear } from 'd3-scale'
import { cn } from '../../lib/utils'

function quantile(values: number[], q: number): number {
  if (!values.length) return 0
  const sorted = [...values].sort((left, right) => left - right)
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
  highlighted?: boolean
}

interface VisualiserScatterPlotProps {
  points: VisualiserScatterDatum[]
  xLabel: string
  yLabel: string
  exportMode?: boolean
  showLabels?: boolean
  labelIds?: number[]
  onSelect?: (id: number) => void
}

export function VisualiserScatterPlot({
  points,
  xLabel,
  yLabel,
  exportMode = false,
  showLabels = false,
  labelIds,
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

  const { xScale, yScale, mapped, diagonal } = useMemo(() => {
    if (!points.length) {
      const emptyX = scaleLinear().domain([0, 1]).range([padLeft, width - padRight]).clamp(true)
      const emptyY = scaleLinear().domain([0, 1]).range([height - padBottom, padTop]).clamp(true)
      return {
        xScale: emptyX,
        yScale: emptyY,
        mapped: [] as Array<VisualiserScatterDatum & { cx: number; cy: number }>,
        diagonal: '',
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
    const [dx0, dx1] = nextX.domain() as [number, number]
    const [dy0, dy1] = nextY.domain() as [number, number]
    const d0 = Math.min(dx0, dy0)
    const d1 = Math.max(dx1, dy1)
    return {
      xScale: nextX,
      yScale: nextY,
      mapped: nextMapped,
      diagonal: `M ${nextX(d0)} ${nextY(d0)} L ${nextX(d1)} ${nextY(d1)}`,
    }
  }, [height, padBottom, padLeft, padRight, padTop, points, width])

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
        <path d={diagonal} fill="none" stroke="rgba(74,158,245,0.28)" strokeWidth={1} strokeDasharray="4 4" />

        {mapped.map(point => {
          const active = point.highlighted || hoverId === point.id
          const showPointLabel = showLabels && (labelSet.size === 0 || labelSet.has(point.id))
          const labelOffset = exportMode ? 10 : 8
          const nearRightEdge = point.cx > width - padRight - (exportMode ? 96 : 72)
          const nearTopEdge = point.cy < padTop + (exportMode ? 16 : 12)
          return (
            <g key={point.id}>
              {showPointLabel && (
                <text
                  x={nearRightEdge ? point.cx - labelOffset : point.cx + labelOffset}
                  y={nearTopEdge ? point.cy + labelOffset + 2 : point.cy - labelOffset}
                  textAnchor={nearRightEdge ? 'end' : 'start'}
                  fill="rgba(138,149,184,0.92)"
                  fontSize={exportMode ? 13 : 10}
                  fontFamily="ui-monospace, SFMono-Regular, monospace"
                  style={{ pointerEvents: 'none' }}
                >
                  {point.label}
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
