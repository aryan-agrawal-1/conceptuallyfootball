import { useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { cn } from '../../lib/utils'

export interface VisualiserRadarSeries {
  id: number
  label: string
  sublabel?: string
  stroke: string
  fill: string
  values: Array<{
    pct: number
    text: string
  }>
}

interface VisualiserRadarChartProps {
  axisLabels: string[]
  series: VisualiserRadarSeries[]
  exportMode?: boolean
}

function polar(theta: number, radius: number): { x: number; y: number } {
  return { x: Math.sin(theta) * radius, y: -Math.cos(theta) * radius }
}

function buildPath(points: { x: number; y: number }[]): string {
  if (!points.length) return ''
  const [first, ...rest] = points
  return `M ${first.x} ${first.y} ${rest.map(point => `L ${point.x} ${point.y}`).join(' ')} Z`
}

export function VisualiserRadarChart({
  axisLabels,
  series,
  exportMode = false,
}: VisualiserRadarChartProps) {
  const [hover, setHover] = useState<{ axisIndex: number; seriesId: number; x: number; y: number } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const size = exportMode ? 760 : 520
  const padding = exportMode ? 76 : 44
  const center = size / 2
  const inner = exportMode ? 82 : 58
  const band = exportMode ? 206 : 140
  const outer = inner + band
  const labelR = outer + (exportMode ? 28 : 20)

  const { axis, polygons } = useMemo(() => {
    const count = Math.max(axisLabels.length, 1)
    const span = (Math.PI * 2) / count
    const nextAxis = axisLabels.map((label, index) => {
      const theta = -Math.PI / 2 + index * span
      return {
        label,
        theta,
        labelPoint: polar(theta, labelR),
      }
    })
    const nextPolygons = series.map(item => {
      const points = item.values.map((value, index) => {
        const theta = nextAxis[index]?.theta ?? -Math.PI / 2
        const radius = inner + (Math.max(0, Math.min(100, value.pct)) / 100) * band
        return polar(theta, radius)
      })
      return {
        ...item,
        points,
        path: buildPath(points),
      }
    })
    return { axis: nextAxis, polygons: nextPolygons }
  }, [axisLabels, band, inner, labelR, series])

  if (!axisLabels.length || !series.length) {
    return <p className="py-12 text-center text-[12px] text-ink-muted">Select entities and axes to render the radar.</p>
  }

  const hoveredSeries = hover ? polygons.find(item => item.id === hover.seriesId) : null
  const hoveredValue =
    hover && hoveredSeries ? hoveredSeries.values[hover.axisIndex] : null

  function updateHoverPosition(
    event: ReactMouseEvent<SVGCircleElement, MouseEvent>,
    axisIndex: number,
    seriesId: number,
  ) {
    const bounds = containerRef.current?.getBoundingClientRect()
    if (!bounds) {
      setHover({ axisIndex, seriesId, x: event.clientX, y: event.clientY })
      return
    }
    setHover({
      axisIndex,
      seriesId,
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    })
  }

  return (
    <div ref={containerRef} className="relative flex flex-col items-center gap-4">
      <svg
        width={size}
        height={size}
        viewBox={`${-padding} ${-padding} ${size + padding * 2} ${size + padding * 2}`}
        className="max-w-full overflow-visible text-electric/25"
        role="img"
        aria-label="Radar comparison chart"
      >
        <g transform={`translate(${center}, ${center})`}>
          {[0.25, 0.5, 0.75, 1].map((step, index) => (
            <circle
              key={step}
              r={inner + step * band}
              fill="none"
              stroke="currentColor"
              strokeWidth={1}
              strokeDasharray={index === 3 ? undefined : '2 4'}
            />
          ))}

          {axis.map(item => {
            const point = polar(item.theta, outer)
            return (
              <line
                key={item.label}
                x1={0}
                y1={0}
                x2={point.x}
                y2={point.y}
                stroke="currentColor"
                strokeWidth={1}
              />
            )
          })}

          {polygons.map(item => (
            <path
              key={item.id}
              d={item.path}
              fill={item.fill}
              stroke={item.stroke}
              strokeWidth={1.8}
            />
          ))}

          {polygons.flatMap(item =>
            item.points.map((point, axisIndex) => (
              <g key={`${item.id}-${axisIndex}`}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={4.25}
                  fill={item.stroke}
                  stroke="rgba(7,8,16,0.95)"
                  strokeWidth={1}
                />
                {!exportMode && (
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={14}
                    fill="transparent"
                    className="cursor-crosshair"
                    onMouseEnter={event => updateHoverPosition(event, axisIndex, item.id)}
                    onMouseMove={event => updateHoverPosition(event, axisIndex, item.id)}
                    onMouseLeave={() => setHover(null)}
                  />
                )}
              </g>
            )),
          )}

          {axis.map(item => (
            <text
              key={`label-${item.label}`}
              x={item.labelPoint.x}
              y={item.labelPoint.y}
              textAnchor={item.labelPoint.x > 20 ? 'start' : item.labelPoint.x < -20 ? 'end' : 'middle'}
              dominantBaseline="middle"
              fill="rgba(138,149,184,0.92)"
              fontSize={exportMode ? 13 : 10}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
              style={{ letterSpacing: '0.08em', textTransform: 'uppercase' }}
            >
              {item.label}
            </text>
          ))}
        </g>
      </svg>

      <div className={cn('flex flex-wrap justify-center', exportMode ? 'gap-3' : 'gap-2')}>
        {polygons.map(item => (
          <div
            key={`legend-${item.id}`}
            className={cn('border border-electric/20 bg-panel/55', exportMode ? 'px-4 py-3' : 'px-3 py-2')}
          >
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full" style={{ background: item.stroke }} />
              <span className={cn('font-medium text-ink', exportMode ? 'text-[15px]' : 'text-[12px]')}>
                {item.label}
              </span>
            </div>
            {item.sublabel && (
              <div className={cn('mt-1 text-ink-muted', exportMode ? 'text-[12px]' : 'text-[10px]')}>
                {item.sublabel}
              </div>
            )}
          </div>
        ))}
      </div>

      {!exportMode && hover && hoveredSeries && hoveredValue && (
        <div
          className="pointer-events-none absolute z-[120] min-w-[190px] border border-electric/35 bg-panel/95 px-2.5 py-2 text-[11px] shadow-xl"
          style={{
            left: hover.x,
            top: hover.y,
            transform: 'translate(-50%, calc(-100% - 10px))',
          }}
        >
          <div className="text-[10px] font-semibold text-ink">{hoveredSeries.label}</div>
          <div className="mt-0.5 text-[10px] text-ink-muted">{axis[hover.axisIndex]?.label}</div>
          <div className="mt-1 font-mono text-electric/90">{hoveredValue.text}</div>
        </div>
      )}
    </div>
  )
}
