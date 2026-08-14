import {
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from 'react'
import { scaleLinear } from 'd3-scale'
import type { RegressionLabPredictionRow } from '../../types/api'
import { shortPlayerName } from '../../lib/entityLabels'
import { cn } from '../../lib/utils'
import {
  buildRegressionScatterDomain,
  REGRESSION_SCATTER_ASPECT_RATIO,
  REGRESSION_SCATTER_MAX_HEIGHT,
  REGRESSION_SCATTER_MIN_HEIGHT,
} from './RegressionScatterPlot.utils'

const MIN_RENDER_WIDTH = 180
const TOOLTIP_MAX_WIDTH = 224
const TOOLTIP_GUTTER = 8
const TOOLTIP_ESTIMATED_HEIGHT = 84

interface RegressionScatterPlotProps {
  rows: RegressionLabPredictionRow[]
  targetLabel: string
  className?: string
}

interface PlotLayout {
  padBottom: number
  padLeft: number
  padRight: number
  padTop: number
  tickCount: number
}

interface MappedPoint {
  actual: number
  id: number
  index: number
  name: string
  predicted: number
  residual: number
  x: number
  y: number
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function chartHeight(width: number) {
  return Math.round(
    clamp(
      width / REGRESSION_SCATTER_ASPECT_RATIO,
      REGRESSION_SCATTER_MIN_HEIGHT,
      REGRESSION_SCATTER_MAX_HEIGHT,
    ),
  )
}

function plotLayout(width: number): PlotLayout {
  if (width < 360) {
    return {
      padBottom: 48,
      padLeft: 42,
      padRight: 12,
      padTop: 34,
      tickCount: 4,
    }
  }
  if (width < 720) {
    return {
      padBottom: 52,
      padLeft: 50,
      padRight: 18,
      padTop: 36,
      tickCount: 5,
    }
  }
  return {
    padBottom: 58,
    padLeft: 58,
    padRight: 24,
    padTop: 40,
    tickCount: 7,
  }
}

function metricPrecision(domain: [number, number]) {
  const span = Math.abs(domain[1] - domain[0])
  if (!Number.isFinite(span) || span === 0) return 2
  if (span >= 100) return 0
  if (span >= 10) return 1
  if (span >= 1) return 2
  return clamp(Math.ceil(-Math.log10(span)) + 2, 3, 8)
}

function formatMetric(value: number, precision: number) {
  if (!Number.isFinite(value)) return '-'
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: precision,
    minimumFractionDigits: 0,
  }).format(value)
}

function useContainerWidth(containerRef: RefObject<HTMLDivElement | null>) {
  const [width, setWidth] = useState(0)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return

    function measure() {
      const nextWidth = Math.max(0, Math.round(container?.getBoundingClientRect().width ?? 0))
      setWidth(current => (current === nextWidth ? current : nextWidth))
    }

    measure()
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(container)
    window.addEventListener('resize', measure)

    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [containerRef])

  return width
}

export function RegressionScatterPlot({
  rows,
  targetLabel,
  className,
}: RegressionScatterPlotProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const descriptionId = useId()
  const width = useContainerWidth(containerRef)
  const height = chartHeight(width)
  const layout = useMemo(() => plotLayout(width), [width])
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)
  const activeIndex = focusedIndex ?? hoveredIndex

  const plot = useMemo(() => {
    const finiteRows = rows.filter(
      row => Number.isFinite(row.predicted_oof) && Number.isFinite(row.actual),
    )
    const paddedDomain = buildRegressionScatterDomain(finiteRows)
    const niceDomain = scaleLinear()
      .domain(paddedDomain)
      .nice(layout.tickCount)
      .domain() as [number, number]
    const xScale = scaleLinear()
      .domain(niceDomain)
      .range([layout.padLeft, width - layout.padRight])
    const yScale = scaleLinear()
      .domain(niceDomain)
      .range([height - layout.padBottom, layout.padTop])
    const points: MappedPoint[] = finiteRows.map((row, index) => ({
      actual: row.actual,
      id: row.canonical_player_id,
      index,
      name: row.canonical_player_name,
      predicted: row.predicted_oof,
      residual: row.actual - row.predicted_oof,
      x: xScale(row.predicted_oof),
      y: yScale(row.actual),
    }))

    return {
      domain: niceDomain,
      points,
      tickFormatter: xScale.tickFormat(layout.tickCount),
      ticks: xScale.ticks(layout.tickCount),
      xScale,
      yScale,
    }
  }, [height, layout, rows, width])

  if (!rows.length) {
    return (
      <p className={cn('py-8 text-center text-[11px] text-ink-muted', className)}>
        No points to plot.
      </p>
    )
  }

  const activePoint = activeIndex === null ? null : (plot.points[activeIndex] ?? null)
  const precision = metricPrecision(plot.domain)
  const tooltipWidth = Math.max(
    0,
    Math.min(TOOLTIP_MAX_WIDTH, width - TOOLTIP_GUTTER * 2),
  )
  const tooltipLeft = activePoint
    ? clamp(
        activePoint.x,
        TOOLTIP_GUTTER + tooltipWidth / 2,
        width - TOOLTIP_GUTTER - tooltipWidth / 2,
      )
    : 0
  const tooltipBelow =
    activePoint !== null &&
    activePoint.y - TOOLTIP_ESTIMATED_HEIGHT < TOOLTIP_GUTTER

  function handlePointKeyDown(event: KeyboardEvent<SVGCircleElement>) {
    if (event.key === 'Escape') {
      setFocusedIndex(null)
      event.currentTarget.blur()
    }
  }

  return (
    <div
      ref={containerRef}
      className={cn('relative min-w-0 w-full overflow-hidden', className)}
      style={{ minHeight: REGRESSION_SCATTER_MIN_HEIGHT }}
    >
      <p id={descriptionId} className="sr-only">
        Each point compares a player's out-of-fold prediction with their actual value.
        The dashed identity line marks an exact prediction; distance from it is the
        prediction error.
      </p>
      {width >= MIN_RENDER_WIDTH ? (
        <>
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            className="block max-w-full text-electric/30"
            role="group"
            aria-label={`Out-of-fold predicted versus actual ${targetLabel} scatter plot`}
            aria-describedby={descriptionId}
            onPointerLeave={() => setHoveredIndex(null)}
          >
            <rect
              x={layout.padLeft}
              y={layout.padTop}
              width={width - layout.padLeft - layout.padRight}
              height={height - layout.padTop - layout.padBottom}
              fill="rgba(7,8,16,0.32)"
              stroke="rgba(74,158,245,0.1)"
            />

            {plot.ticks.map(tick => (
              <g key={`grid-${tick}`}>
                <line
                  x1={plot.xScale(tick)}
                  y1={layout.padTop}
                  x2={plot.xScale(tick)}
                  y2={height - layout.padBottom}
                  stroke="rgba(74,158,245,0.08)"
                  strokeWidth={1}
                />
                <line
                  x1={layout.padLeft}
                  y1={plot.yScale(tick)}
                  x2={width - layout.padRight}
                  y2={plot.yScale(tick)}
                  stroke="rgba(74,158,245,0.08)"
                  strokeWidth={1}
                />
                <text
                  x={plot.xScale(tick)}
                  y={height - layout.padBottom + 18}
                  textAnchor="middle"
                  className="fill-ink-muted text-[9px] font-mono"
                >
                  {plot.tickFormatter(tick)}
                </text>
                <text
                  x={layout.padLeft - 8}
                  y={plot.yScale(tick)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="fill-ink-muted text-[9px] font-mono"
                >
                  {plot.tickFormatter(tick)}
                </text>
              </g>
            ))}

            <line
              x1={layout.padLeft}
              y1={height - layout.padBottom}
              x2={width - layout.padRight}
              y2={height - layout.padBottom}
              stroke="currentColor"
              strokeWidth={1}
            />
            <line
              x1={layout.padLeft}
              y1={layout.padTop}
              x2={layout.padLeft}
              y2={height - layout.padBottom}
              stroke="currentColor"
              strokeWidth={1}
            />
            <line
              x1={plot.xScale(plot.domain[0])}
              y1={plot.yScale(plot.domain[0])}
              x2={plot.xScale(plot.domain[1])}
              y2={plot.yScale(plot.domain[1])}
              fill="none"
              stroke="rgba(74,158,245,0.52)"
              strokeWidth={1.25}
              strokeDasharray="5 5"
              aria-hidden="true"
            />

            {plot.points.map(point => {
              const active = point.index === activeIndex
              const pointLabel = `${point.name}. Predicted ${formatMetric(point.predicted, precision)}. Actual ${formatMetric(point.actual, precision)}. Residual ${formatMetric(point.residual, precision)}.`

              return (
                <g key={`${point.id}-${point.index}`}>
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={active ? 5 : 3.75}
                    className="pointer-events-none fill-electric/85 stroke-mat"
                    strokeWidth={active ? 1.75 : 1}
                    aria-hidden="true"
                  />
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={14}
                    fill="transparent"
                    className="cursor-default outline-none focus-visible:stroke-ink focus-visible:stroke-1"
                    role="button"
                    tabIndex={0}
                    aria-label={pointLabel}
                    onPointerEnter={() => setHoveredIndex(point.index)}
                    onPointerLeave={() => setHoveredIndex(null)}
                    onFocus={() => setFocusedIndex(point.index)}
                    onBlur={() => setFocusedIndex(null)}
                    onKeyDown={handlePointKeyDown}
                  />
                </g>
              )
            })}

            <text
              x={width / 2}
              y={18}
              textAnchor="middle"
              className="fill-ink-muted text-[9px] uppercase tracking-[0.2em]"
            >
              OOF predicted vs actual · {targetLabel}
            </text>
            <text
              x={(layout.padLeft + width - layout.padRight) / 2}
              y={height - 9}
              textAnchor="middle"
              className="fill-ink-muted text-[9px] font-mono"
            >
              Predicted (out-of-fold)
            </text>
            <text
              x={12}
              y={(layout.padTop + height - layout.padBottom) / 2}
              textAnchor="middle"
              transform={`rotate(-90 12 ${(layout.padTop + height - layout.padBottom) / 2})`}
              className="fill-ink-muted text-[9px] font-mono"
            >
              Actual
            </text>
          </svg>

          {activePoint ? (
            <div
              className="pointer-events-none absolute z-10 border border-electric/35 bg-mat/95 px-2.5 py-2 text-[10px] shadow-md"
              role="status"
              aria-live="polite"
              style={{
                left: tooltipLeft,
                top: activePoint.y,
                transform: tooltipBelow
                  ? 'translate(-50%, 10px)'
                  : 'translate(-50%, calc(-100% - 10px))',
                width: tooltipWidth,
              }}
            >
              <p className="truncate font-medium text-ink">
                {shortPlayerName(activePoint.name)}
              </p>
              <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 font-mono text-ink-muted">
                <dt>Predicted (OOF)</dt>
                <dd className="text-right text-electric">
                  {formatMetric(activePoint.predicted, precision)}
                </dd>
                <dt>Actual</dt>
                <dd className="text-right text-ink">
                  {formatMetric(activePoint.actual, precision)}
                </dd>
                <dt>Residual</dt>
                <dd className="text-right text-ink">
                  {formatMetric(activePoint.residual, precision)}
                </dd>
              </dl>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}
