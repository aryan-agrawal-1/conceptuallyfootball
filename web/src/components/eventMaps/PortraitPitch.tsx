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

type PortraitPitchProps = {
  passes?: EventPass[]
  shots?: EventShot[]
  densityCells?: ActionGridCell[]
  flows?: TeamPassFlow[]
  labels?: PitchLabel[]
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

function shotMarkerStyle(shot: EventShot, selected: boolean) {
  if (selected) return { fill: '#E4EAF8', stroke: '#4A9EF5', radius: 10 }
  if (shot.outcome === 'goal') return { fill: '#1FD17C', stroke: '#07150E', radius: 8 }
  if (shot.perspective === 'against') return { fill: '#EF4444', stroke: '#270909', radius: 7 }
  if (shot.outcome === 'blocked') return { fill: '#F0A832', stroke: '#231806', radius: 6 }
  return { fill: '#8A95B8', stroke: '#0D0F1A', radius: 6 }
}

function labelClasses(tone: PitchLabel['tone']) {
  if (tone === 'accent') return 'fill-electric'
  if (tone === 'warning') return 'fill-gold'
  return 'fill-ink-dim'
}

export const PortraitPitch = memo(function PortraitPitch({
  passes = [],
  shots = [],
  densityCells = [],
  flows = [],
  labels = [],
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
      if (!nearest) return
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
      <div
        ref={containerRef}
        className="relative isolate aspect-[68/105] w-full min-w-0 overflow-hidden border border-line-bright bg-[radial-gradient(circle_at_50%_24%,rgba(74,158,245,0.10),transparent_38%),repeating-linear-gradient(0deg,rgba(255,255,255,0.018)_0,rgba(255,255,255,0.018)_1px,transparent_1px,transparent_52.5px),linear-gradient(180deg,#11192a_0%,#0a101b_100%)] shadow-[0_24px_70px_rgba(0,0,0,0.42),inset_0_0_42px_rgba(74,158,245,0.05)]"
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
          onKeyDown={handleKeyDown}
        >
          <PitchMarkings />

          {shots.map((shot) => {
            const point = logicalTransform.toScreen(shot.location)
            const selected = shot.id === selectedEventId
            const style = shotMarkerStyle(shot, selected)
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
                  strokeWidth={selected ? 4 : 2}
                  vectorEffect="non-scaling-stroke"
                />
                {shot.outcome === 'goal' ? (
                  <circle cx={point.x} cy={point.y} r={2.2} fill="#07150E" aria-hidden="true" />
                ) : null}
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

          {selectedEvent?.kind === 'pass' ? (
            <g aria-hidden="true" pointerEvents="none">
              <line
                x1={logicalTransform.toScreen(selectedEvent.start).x}
                y1={logicalTransform.toScreen(selectedEvent.start).y}
                x2={logicalTransform.toScreen(selectedEvent.end).x}
                y2={logicalTransform.toScreen(selectedEvent.end).y}
                stroke="#E4EAF8"
                strokeWidth={2.4}
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={logicalTransform.toScreen(selectedEvent.end).x}
                cy={logicalTransform.toScreen(selectedEvent.end).y}
                r={4}
                fill="#E4EAF8"
              />
            </g>
          ) : null}

          <g aria-hidden="true" className="fill-electric">
            <path d="M 326 18 L 340 5 L 354 18 L 348 18 L 348 29 L 332 29 L 332 18 Z" />
            <text
              x={340}
              y={45}
              textAnchor="middle"
              className="text-[10px] font-bold uppercase tracking-[0.18em]"
            >
              Attack
            </text>
          </g>
        </svg>
        <span className="absolute left-2 top-2 size-2 border-l border-t border-electric/70" aria-hidden />
        <span className="absolute right-2 top-2 size-2 border-r border-t border-electric/70" aria-hidden />
        <span className="absolute bottom-2 left-2 size-2 border-b border-l border-electric/35" aria-hidden />
        <span className="absolute bottom-2 right-2 size-2 border-b border-r border-electric/35" aria-hidden />
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
