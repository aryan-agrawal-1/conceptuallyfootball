import { useMemo, useState } from 'react'
import { scaleLinear } from 'd3-scale'
import type { RegressionLabPredictionRow } from '../../types/api'
import { cn } from '../../lib/utils'

const W = 420
const H = 280
const PAD = 36

interface RegressionScatterPlotProps {
  rows: RegressionLabPredictionRow[]
  targetLabel: string
  className?: string
}

export function RegressionScatterPlot({
  rows,
  targetLabel,
  className,
}: RegressionScatterPlotProps) {
  const [hover, setHover] = useState<{ name: string; x: number; y: number } | null>(null)

  const { xScale, yScale, pts } = useMemo(() => {
    if (!rows.length) {
      return {
        xScale: scaleLinear().domain([0, 1]).range([PAD, W - PAD]),
        yScale: scaleLinear().domain([0, 1]).range([H - PAD, PAD]),
        pts: [] as { x: number; y: number; id: number; name: string }[],
      }
    }
    const xs = rows.map(r => r.predicted_oof)
    const ys = rows.map(r => r.actual)
    const xmin = Math.min(...xs)
    const xmax = Math.max(...xs)
    const ymin = Math.min(...ys)
    const ymax = Math.max(...ys)
    const padX = (xmax - xmin) * 0.06 || 0.5
    const padY = (ymax - ymin) * 0.06 || 0.5
    const xScale = scaleLinear()
      .domain([xmin - padX, xmax + padX])
      .range([PAD, W - PAD])
    const yScale = scaleLinear()
      .domain([ymin - padY, ymax + padY])
      .range([H - PAD, PAD])
    const pts = rows.map(r => ({
      x: xScale(r.predicted_oof),
      y: yScale(r.actual),
      id: r.canonical_player_id,
      name: r.canonical_player_name,
    }))
    return { xScale, yScale, pts }
  }, [rows])

  const diag = useMemo(() => {
    if (!rows.length) return null
    const [x0, x1] = xScale.domain() as [number, number]
    const [y0, y1] = yScale.domain() as [number, number]
    const t0 = Math.min(x0, y0)
    const t1 = Math.max(x1, y1)
    return `M ${xScale(t0)} ${yScale(t0)} L ${xScale(t1)} ${yScale(t1)}`
  }, [rows, xScale, yScale])

  if (!rows.length) {
    return (
      <p className="text-[11px] text-ink-muted text-center py-8">No points to plot.</p>
    )
  }

  return (
    <div className={cn('w-full flex justify-center', className)}>
      <div className="relative" style={{ width: W, height: H }}>
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          className="text-electric/30 block"
          role="img"
          aria-label="Predicted versus actual scatter"
          onMouseLeave={() => setHover(null)}
        >
        <text
          x={W / 2}
          y={14}
          textAnchor="middle"
          className="fill-ink-muted text-[9px] uppercase tracking-[0.2em]"
        >
          OOF predicted vs actual · {targetLabel}
        </text>
        <line
          x1={PAD}
          y1={H - PAD}
          x2={W - PAD}
          y2={H - PAD}
          stroke="currentColor"
          strokeWidth={1}
        />
        <line
          x1={PAD}
          y1={PAD}
          x2={PAD}
          y2={H - PAD}
          stroke="currentColor"
          strokeWidth={1}
        />
        {diag && (
          <path
            d={diag}
            fill="none"
            stroke="rgba(74,158,245,0.45)"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        )}
        {pts.map(p => (
          <g key={p.id}>
            <circle
              cx={p.x}
              cy={p.y}
              r={14}
              fill="transparent"
              className="cursor-default"
              onMouseEnter={() => setHover({ name: p.name, x: p.x, y: p.y })}
              onMouseLeave={() => setHover(null)}
            />
            <circle
              cx={p.x}
              cy={p.y}
              r={3.5}
              className="pointer-events-none fill-electric/80 stroke-mat stroke"
              strokeWidth={1}
            />
          </g>
        ))}
        <text
          x={W / 2}
          y={H - 8}
          textAnchor="middle"
          className="fill-ink-muted text-[9px] font-mono"
        >
          Predicted (out-of-fold)
        </text>
        <text
          x={12}
          y={H / 2}
          textAnchor="middle"
          transform={`rotate(-90 12 ${H / 2})`}
          className="fill-ink-muted text-[9px] font-mono"
        >
          Actual
        </text>
      </svg>
        {hover && (
          <div
            className="pointer-events-none absolute z-10 max-w-[min(220px,calc(100vw-48px))]"
            style={{
              left: hover.x,
              top: hover.y,
              transform: 'translate(-50%, calc(-100% - 10px))',
            }}
          >
            <span className="block truncate rounded border border-electric/35 bg-mat/95 px-2 py-0.5 text-center text-[10px] font-medium text-ink shadow-md">
              {hover.name}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
