import {
  memo,
  useCallback,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type RefObject,
} from 'react'
import type {
  ActionGridCell,
  EventPass,
  EventShot,
  PitchCoordinate,
  TeamPassFlow,
} from '../../types/eventMaps'
import {
  configureHiDPICanvas,
  drawDensePitchLayers,
  type CanvasViewport,
  type DenseLayerOptions,
} from '../../lib/eventMaps/canvasRendering'
import {
  clientPointToViewport,
  createPitchTransform,
  PITCH_VIEWBOX_HEIGHT,
  PITCH_VIEWBOX_WIDTH,
} from '../../lib/eventMaps/pitchGeometry'
import {
  findDirectionalPitchEvent,
  findNearestPitchEvent,
  type DirectionKey,
  type SelectablePitchEvent,
} from '../../lib/eventMaps/selection'
import { PitchMarkings } from './PitchMarkings'

export type PitchLabel = {
  id: string
  coordinate: PitchCoordinate
  text: string
  tone?: 'neutral' | 'accent' | 'warning'
}

export type PitchMarker = {
  id: string
  coordinate: PitchCoordinate
  kind: 'jersey'
  ariaLabel: string
  label?: string
  tone?: 'neutral' | 'accent' | 'warning'
}

type PortraitPitchProps = {
  passes?: EventPass[]
  shots?: EventShot[]
  densityCells?: ActionGridCell[]
  flows?: TeamPassFlow[]
  labels?: PitchLabel[]
  markers?: PitchMarker[]
  selectedEventId?: string | null
  onSelectedEventChange?: (event: SelectablePitchEvent | null) => void
  ariaLabel?: string
  className?: string
  layerOptions?: DenseLayerOptions
}

const logicalTransform = createPitchTransform(PITCH_VIEWBOX_WIDTH, PITCH_VIEWBOX_HEIGHT)
const directionKeys = new Set<DirectionKey>([
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
])

function useCanvasViewport(containerRef: RefObject<HTMLDivElement | null>) {
  const [viewport, setViewport] = useState<CanvasViewport>({
    width: 0,
    height: 0,
    devicePixelRatio: 1,
  })

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return
    const activeContainer = container

    function measure() {
      const bounds = activeContainer.getBoundingClientRect()
      const nextViewport = {
        width: bounds.width,
        height: bounds.height,
        devicePixelRatio: window.devicePixelRatio || 1,
      }
      setViewport((current) =>
        current.width === nextViewport.width &&
        current.height === nextViewport.height &&
        current.devicePixelRatio === nextViewport.devicePixelRatio
          ? current
          : nextViewport,
      )
    }

    measure()
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => measure())
    observer?.observe(activeContainer)
    window.addEventListener('resize', measure)

    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [containerRef])

  return viewport
}

function passAriaLabel(pass: EventPass) {
  const outcome = pass.outcome === 'successful' ? 'completed' : 'incomplete'
  return `${outcome} pass, minute ${pass.minute}, from ${pass.start.x.toFixed(0)} to ${pass.end.x.toFixed(0)} percent upfield`
}

function shotAriaLabel(shot: EventShot) {
  return `${shot.perspective === 'against' ? 'opponent ' : ''}${shot.outcome.replace('_', ' ')} shot, minute ${shot.minute}`
}

function createSelectableEvents(passes: EventPass[], shots: EventShot[]) {
  const events: SelectablePitchEvent[] = []
  for (const pass of passes) {
    events.push({
      id: pass.id,
      kind: 'pass',
      start: pass.start,
      end: pass.end,
      ariaLabel: passAriaLabel(pass),
      event: pass,
    })
  }
  for (const shot of shots) {
    events.push({
      id: shot.id,
      kind: 'shot',
      point: shot.location,
      ariaLabel: shotAriaLabel(shot),
      event: shot,
    })
  }
  return events
}

function toLogicalSelectionEvent(event: SelectablePitchEvent): SelectablePitchEvent {
  if (event.kind === 'shot') {
    return { ...event, point: logicalTransform.toScreen(event.point) }
  }
  return {
    ...event,
    start: logicalTransform.toScreen(event.start),
    end: logicalTransform.toScreen(event.end),
  }
}

function shotMarkerStyle(shot: EventShot, selected: boolean, hasSelection: boolean) {
  let fill = '#8A95B8'
  let radius = 6
  if (shot.outcome === 'goal') {
    fill = '#1FD17C'
    radius = 8
  } else if (shot.perspective === 'against') {
    fill = '#EF4444'
    radius = 7
  } else if (shot.outcome === 'blocked') {
    fill = '#F0A832'
  }
  return {
    fill,
    stroke: selected ? '#E4EAF8' : 'none',
    radius,
    opacity: selected ? 1 : hasSelection ? 0.4 : 1,
  }
}

function labelClasses(tone: PitchLabel['tone']) {
  if (tone === 'accent') return 'fill-electric'
  if (tone === 'warning') return 'fill-gold'
  return 'fill-ink-dim'
}

function markerClasses(tone: PitchMarker['tone']) {
  if (tone === 'warning') return 'fill-gold stroke-gold text-gold'
  if (tone === 'neutral') return 'fill-ink-dim stroke-ink-dim text-ink-dim'
  return 'fill-electric stroke-electric text-electric'
}

export const PortraitPitch = memo(function PortraitPitch({
  passes = [],
  shots = [],
  densityCells = [],
  flows = [],
  labels = [],
  markers = [],
  selectedEventId: controlledSelectedEventId,
  onSelectedEventChange,
  ariaLabel = 'Portrait football pitch. The acting team attacks toward the top.',
  className = '',
  layerOptions,
}: PortraitPitchProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const accessibleDescriptionId = useId()
  const accessibleSelectionId = useId()
  const viewport = useCanvasViewport(containerRef)
  const [internalSelectedEventId, setInternalSelectedEventId] = useState<string | null>(null)
  const selectedEventId =
    controlledSelectedEventId === undefined
      ? internalSelectedEventId
      : controlledSelectedEventId
  const selectableEvents = useMemo(() => createSelectableEvents(passes, shots), [passes, shots])
  const logicalSelectionEvents = useMemo(
    () => selectableEvents.map(toLogicalSelectionEvent),
    [selectableEvents],
  )
  const selectedEvent =
    selectableEvents.find((event) => event.id === selectedEventId) ?? null
  const hasSelection = selectedEvent !== null

  const selectEvent = useCallback(
    (event: SelectablePitchEvent | null) => {
      if (controlledSelectedEventId === undefined) {
        setInternalSelectedEventId(event?.id ?? null)
      }
      onSelectedEventChange?.(event)
    },
    [controlledSelectedEventId, onSelectedEventChange],
  )

  useLayoutEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || viewport.width === 0 || viewport.height === 0) return
    const context = configureHiDPICanvas(canvas, viewport)
    if (!context) return

    drawDensePitchLayers(
      context,
      viewport,
      { passes, densityCells, flows },
      { ...layerOptions, selectedEventId },
    )
  }, [densityCells, flows, layerOptions, passes, selectedEventId, viewport])

  const selectNearest = useCallback(
    (event: PointerEvent<SVGSVGElement>) => {
      const bounds = event.currentTarget.getBoundingClientRect()
      const point = clientPointToViewport(event.clientX, event.clientY, bounds)
      const nearest = findNearestPitchEvent(logicalSelectionEvents, point, 26)
      if (!nearest) {
        selectEvent(null)
        return
      }
      selectEvent(selectableEvents.find((candidate) => candidate.id === nearest.id) ?? null)
    },
    [logicalSelectionEvents, selectEvent, selectableEvents],
  )

  const handlePointerMove = useCallback(
    (event: PointerEvent<SVGSVGElement>) => {
      if (event.pointerType !== 'touch') selectNearest(event)
    },
    [selectNearest],
  )

  const handlePointerLeave = useCallback(
    (event: PointerEvent<SVGSVGElement>) => {
      if (event.pointerType !== 'touch') selectEvent(null)
    },
    [selectEvent],
  )

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<SVGSVGElement>) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        selectEvent(null)
        return
      }
      if (!directionKeys.has(event.key as DirectionKey)) return

      event.preventDefault()
      const next = findDirectionalPitchEvent(
        selectableEvents,
        selectedEventId,
        event.key as DirectionKey,
      )
      if (next) selectEvent(next)
    },
    [selectEvent, selectableEvents, selectedEventId],
  )

  return (
    <figure className={`m-0 w-full ${className}`}>
      <div className="flex w-full items-stretch gap-2">
        <div className="relative w-[52px] shrink-0" aria-hidden="true">
          <svg
            viewBox={`0 0 64 ${PITCH_VIEWBOX_HEIGHT}`}
            preserveAspectRatio="none"
            className="absolute inset-0 size-full overflow-visible"
          >
            <line
              x1={48}
              y1={930}
              x2={48}
              y2={126}
              stroke="#4A9EF5"
              strokeWidth={3}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
            <path d="M 48 82 L 34 128 L 62 128 Z" fill="#4A9EF5" />
            <text
              transform="translate(18 530) rotate(-90)"
              textAnchor="middle"
              dominantBaseline="central"
              fill="#E4EAF8"
              className="text-[14px] font-bold uppercase tracking-[0.16em]"
            >
              Direction of attack
            </text>
          </svg>
        </div>
        <div
          ref={containerRef}
          className="relative isolate aspect-[68/105] min-w-0 flex-1 overflow-hidden border border-line-bright bg-[radial-gradient(circle_at_50%_24%,rgba(74,158,245,0.10),transparent_38%),repeating-linear-gradient(0deg,rgba(255,255,255,0.018)_0,rgba(255,255,255,0.018)_1px,transparent_1px,transparent_52.5px),linear-gradient(180deg,#11192a_0%,#0a101b_100%)] shadow-[0_24px_70px_rgba(0,0,0,0.42),inset_0_0_42px_rgba(74,158,245,0.05)]"
        >
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 size-full"
          aria-hidden="true"
        />
        <svg
          viewBox={`0 0 ${PITCH_VIEWBOX_WIDTH} ${PITCH_VIEWBOX_HEIGHT}`}
          preserveAspectRatio="xMidYMid meet"
          className="absolute inset-0 size-full touch-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-electric"
          role="application"
          tabIndex={0}
          aria-label={ariaLabel}
          aria-describedby={`${accessibleDescriptionId} ${accessibleSelectionId}`}
          onPointerMove={handlePointerMove}
          onPointerDown={selectNearest}
          onPointerLeave={handlePointerLeave}
          onKeyDown={handleKeyDown}
        >
          <PitchMarkings />

          {shots.map((shot) => {
            const point = logicalTransform.toScreen(shot.location)
            const selected = shot.id === selectedEventId
            const style = shotMarkerStyle(shot, selected, hasSelection)
            return (
              <g
                key={shot.id}
                role="button"
                tabIndex={0}
                aria-label={shotAriaLabel(shot)}
                className="cursor-pointer outline-none"
                onFocus={() =>
                  selectEvent(selectableEvents.find((event) => event.id === shot.id) ?? null)
                }
                onPointerDown={(event) => {
                  event.stopPropagation()
                  selectEvent(selectableEvents.find((candidate) => candidate.id === shot.id) ?? null)
                }}
              >
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={style.radius + 9}
                  fill="transparent"
                  stroke="transparent"
                />
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={style.radius}
                  fill={style.fill}
                  stroke={style.stroke}
                  strokeWidth={selected ? 3 : 0}
                  opacity={style.opacity}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          })}

          {labels.map((label) => {
            const point = logicalTransform.toScreen(label.coordinate)
            return (
              <text
                key={label.id}
                x={point.x}
                y={point.y}
                textAnchor="middle"
                dominantBaseline="central"
                className={`${labelClasses(label.tone)} pointer-events-none text-[11px] font-bold uppercase tracking-[0.14em]`}
              >
                {label.text}
              </text>
            )
          })}

          {markers.map((marker) => {
            const point = logicalTransform.toScreen(marker.coordinate)
            return (
              <g
                key={marker.id}
                role="img"
                aria-label={marker.ariaLabel}
                transform={`translate(${point.x - 18} ${point.y - 17})`}
                className={`${markerClasses(marker.tone)} pointer-events-none`}
              >
                {marker.label ? (
                  <text
                    x={18}
                    y={-6}
                    textAnchor="middle"
                    fill="currentColor"
                    stroke="none"
                    className="text-[10px] font-bold uppercase tracking-[0.12em]"
                  >
                    {marker.label}
                  </text>
                ) : null}
                <path
                  d="M 5 7 L 12 2 L 17 5 L 19 5 L 24 2 L 31 7 L 27 16 L 23 14 L 23 32 L 13 32 L 13 14 L 9 16 Z"
                  strokeWidth={2}
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d="M 12 2 Q 18 11 24 2"
                  fill="none"
                  stroke="#07101B"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          })}

        </svg>
        <span className="absolute left-2 top-2 size-2 border-l border-t border-electric/70" aria-hidden />
        <span className="absolute right-2 top-2 size-2 border-r border-t border-electric/70" aria-hidden />
        <span className="absolute bottom-2 left-2 size-2 border-b border-l border-electric/35" aria-hidden />
        <span className="absolute bottom-2 right-2 size-2 border-b border-r border-electric/35" aria-hidden />
        </div>
      </div>
      <figcaption className="sr-only">
        <span id={accessibleDescriptionId}>
          Use the arrow keys to inspect nearby events. Press Escape to clear the selection.
        </span>
        <span id={accessibleSelectionId} aria-live="polite">
          {selectedEvent?.ariaLabel ?? 'No event selected.'}
        </span>
      </figcaption>
    </figure>
  )
})
