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
  EventCarry,
  EventPass,
  EventShot,
  PitchCoordinate,
  ShotOutcome,
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
  carries?: EventCarry[]
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
  pitchView?: 'full' | 'attacking-half'
  densityStyle?: 'cells' | 'smooth'
  selectedFlowId?: string | null
  onSelectedFlowChange?: (flow: TeamPassFlow | null) => void
  eventSelectionMode?: 'hover' | 'click'
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

function carryAriaLabel(carry: EventCarry) {
  const classifications = [
    carry.progressive ? 'progressive' : null,
    carry.finalThirdEntry ? 'final third entry' : null,
    carry.boxEntry ? 'box entry' : null,
    carry.lowConfidence ? 'low confidence' : null,
  ].filter(Boolean).join(', ')
  return `derived carry, minute ${carry.minute}, ${carry.length.toFixed(1)} metres${classifications ? `, ${classifications}` : ''}`
}

function shotAriaLabel(shot: EventShot) {
  const shooter = shot.playerName ? `${shot.playerName}, ` : ''
  return `${shooter}${shot.perspective === 'against' ? 'opponent ' : ''}${shot.outcome.replace('_', ' ')} shot, minute ${shot.minute}`
}

function flowAriaLabel(flow: TeamPassFlow) {
  const attempts = flow.attemptedCount
  return attempts == null
    ? `${flow.completedCount} completed passes from this area, mean length ${flow.meanLength.toFixed(1)} metres`
    : `${attempts} attempted passes from this area, ${flow.completedCount} completed, mean length ${flow.meanLength.toFixed(1)} metres`
}

function createSelectableEvents(passes: EventPass[], carries: EventCarry[], shots: EventShot[]) {
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
  for (const carry of carries) {
    events.push({
      id: carry.id,
      kind: 'carry',
      start: carry.start,
      end: carry.end,
      ariaLabel: carryAriaLabel(carry),
      event: carry,
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
  const radius = shot.bigChance ? 8 : 5.5
  if (shot.outcome === 'goal') {
    fill = '#1FD17C'
  } else if (shot.outcome === 'saved') {
    fill = '#4A9EF5'
  } else if (shot.outcome === 'blocked') {
    fill = '#F0A832'
  } else if (shot.outcome === 'woodwork') {
    fill = '#EF5C66'
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

const ON_TARGET_OUTCOMES: ReadonlySet<ShotOutcome> = new Set(['goal', 'saved', 'woodwork'])

// GoalMouthZ crossbar height — see lib/eventMaps/goalMouth.ts.
const GOAL_CROSSBAR_Z = 38

function targetHeightRadius(z: number) {
  return 2 + (Math.min(GOAL_CROSSBAR_Z, Math.max(0, z)) / GOAL_CROSSBAR_Z) * 3.5
}

function shotTargetArrow(shot: EventShot): {
  from: PitchCoordinate
  to: PitchCoordinate
  break?: PitchCoordinate
  heightRadius: number
} | null {
  const onTarget = ON_TARGET_OUTCOMES.has(shot.outcome)
  if (shot.outcome === 'blocked' && shot.blockedAt) {
    // Blocked shots show a broken arrow; a faint continuation to the projected
    // target keeps the intended destination readable.
    return shot.goalMouth
      ? {
          from: shot.location,
          to: { x: 100, y: shot.goalMouth.y },
          break: shot.blockedAt,
          heightRadius: targetHeightRadius(shot.goalMouth.z),
        }
      : null
  }
  if (!onTarget || !shot.goalMouth) return null
  return {
    from: shot.location,
    to: { x: 100, y: shot.goalMouth.y },
    heightRadius: targetHeightRadius(shot.goalMouth.z),
  }
}

function ShotTargetArrow({ shot }: { shot: EventShot }) {
  const arrow = shotTargetArrow(shot)
  if (!arrow) return null
  // goalMouth stays in native Opta space (zone labels depend on it); flip the
  // y here so the rendered arrow matches the display orientation.
  const displayTo = { x: arrow.to.x, y: 100 - arrow.to.y }
  const from = logicalTransform.toScreen(arrow.from)
  const to = logicalTransform.toScreen(displayTo)
  const mid = arrow.break ? logicalTransform.toScreen(arrow.break) : null
  const deltaX = to.x - from.x
  const deltaY = to.y - from.y
  const distance = Math.hypot(deltaX, deltaY)
  if (distance < 1) return null
  const unitX = deltaX / distance
  const unitY = deltaY / distance
  const headSize = 7
  const shaftEndX = to.x - unitX * headSize * 0.8
  const shaftEndY = to.y - unitY * headSize * 0.8
  const color = shot.outcome === 'goal' ? '#1FD17C' : '#E4EAF8'
  return (
    <g aria-hidden="true" className="pointer-events-none">
      {mid ? (
        <>
          <line x1={from.x} y1={from.y} x2={mid.x} y2={mid.y} stroke={color} strokeWidth={2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
          <rect x={mid.x - 3.5} y={mid.y - 3.5} width={7} height={7} fill="#F0A832" stroke="#07101B" strokeWidth={1} transform={`rotate(45 ${mid.x} ${mid.y})`} />
          <line x1={mid.x} y1={mid.y} x2={shaftEndX} y2={shaftEndY} stroke={color} strokeWidth={1.5} strokeDasharray="4 4" opacity={0.55} vectorEffect="non-scaling-stroke" />
        </>
      ) : (
        <line x1={from.x} y1={from.y} x2={shaftEndX} y2={shaftEndY} stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      )}
      <path
        d={`M ${to.x} ${to.y} L ${to.x - unitX * headSize - unitY * headSize * 0.55} ${to.y - unitY * headSize + unitX * headSize * 0.55} L ${to.x - unitX * headSize + unitY * headSize * 0.55} ${to.y - unitY * headSize - unitX * headSize * 0.55} Z`}
        fill={color}
      />
      <circle cx={to.x} cy={to.y} r={arrow.heightRadius + 2.5} fill={color} opacity={0.28} />
    </g>
  )
}

function markerClasses(tone: PitchMarker['tone']) {
  if (tone === 'warning') return 'fill-gold stroke-gold text-gold'
  if (tone === 'neutral') return 'fill-ink-dim stroke-ink-dim text-ink-dim'
  return 'fill-electric stroke-electric text-electric'
}

export const PortraitPitch = memo(function PortraitPitch({
  passes = [],
  carries = [],
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
  pitchView = 'full',
  densityStyle = 'cells',
  selectedFlowId,
  onSelectedFlowChange,
  eventSelectionMode = 'hover',
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
  const selectableEvents = useMemo(
    () => createSelectableEvents(passes, carries, shots),
    [carries, passes, shots],
  )
  const logicalSelectionEvents = useMemo(
    () => selectableEvents.map(toLogicalSelectionEvent),
    [selectableEvents],
  )
  const selectedEvent =
    selectableEvents.find((event) => event.id === selectedEventId) ?? null
  const selectedFlow = flows.find(flow => flow.id === selectedFlowId) ?? null
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
      { passes, carries, densityCells, flows },
      { ...layerOptions, densityStyle, selectedEventId, selectedFlowId },
      pitchView,
    )
  }, [carries, densityCells, densityStyle, flows, layerOptions, passes, pitchView, selectedEventId, selectedFlowId, viewport])

  const selectNearest = useCallback(
    (event: PointerEvent<SVGSVGElement>) => {
      const bounds = event.currentTarget.getBoundingClientRect()
      const point = clientPointToViewport(
        event.clientX,
        event.clientY,
        bounds,
        pitchView === 'attacking-half' ? PITCH_VIEWBOX_WIDTH / 2 : PITCH_VIEWBOX_WIDTH,
        PITCH_VIEWBOX_HEIGHT,
      )
      if (pitchView === 'attacking-half') point.x += PITCH_VIEWBOX_WIDTH / 2
      const nearest = findNearestPitchEvent(logicalSelectionEvents, point, 26)
      if (!nearest) {
        selectEvent(null)
        return
      }
      selectEvent(selectableEvents.find((candidate) => candidate.id === nearest.id) ?? null)
    },
    [logicalSelectionEvents, pitchView, selectEvent, selectableEvents],
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
      <div
          ref={containerRef}
          className={`relative isolate w-full overflow-hidden border border-line-bright bg-[radial-gradient(circle_at_72%_44%,rgba(74,158,245,0.10),transparent_42%),repeating-linear-gradient(90deg,rgba(255,255,255,0.018)_0,rgba(255,255,255,0.018)_1px,transparent_1px,transparent_52.5px),linear-gradient(90deg,#0a101b_0%,#11192a_100%)] shadow-[0_18px_48px_rgba(0,0,0,0.30),inset_0_0_42px_rgba(74,158,245,0.05)] ${pitchView === 'attacking-half' ? 'aspect-[105/136]' : 'aspect-[105/68]'}`}
        >
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 size-full"
          aria-hidden="true"
        />
        {selectedFlow ? (
          <div
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-1/2 border border-gold/60 bg-panel/95 px-2.5 py-2 font-mono text-[8px] leading-relaxed text-ink-dim shadow-[0_10px_28px_rgba(0,0,0,0.45)] backdrop-blur-sm"
            style={{
              left: `${Math.min(82, Math.max(18, selectedFlow.origin.x))}%`,
              top: `${Math.min(80, Math.max(20, selectedFlow.origin.y))}%`,
            }}
            role="status"
          >
            <span className="font-bold text-ink">
              {selectedFlow.attemptedCount == null
                ? `${selectedFlow.completedCount.toLocaleString()} completed`
                : `${selectedFlow.attemptedCount.toLocaleString()} attempted · ${selectedFlow.completedCount.toLocaleString()} completed`}
            </span>
            <span className="mx-1.5 text-gold/70">·</span>
            {selectedFlow.meanLength.toFixed(1)}m mean
            <span className="mx-1.5 text-gold/70">·</span>
            {(selectedFlow.share * 100).toFixed(1)}%
          </div>
        ) : null}
        <svg
          viewBox={`${pitchView === 'attacking-half' ? PITCH_VIEWBOX_WIDTH / 2 : 0} 0 ${pitchView === 'attacking-half' ? PITCH_VIEWBOX_WIDTH / 2 : PITCH_VIEWBOX_WIDTH} ${PITCH_VIEWBOX_HEIGHT}`}
          preserveAspectRatio="xMidYMid meet"
          className="absolute inset-0 size-full touch-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-electric"
          role="application"
          tabIndex={0}
          aria-label={ariaLabel}
          aria-describedby={`${accessibleDescriptionId} ${accessibleSelectionId}`}
          onPointerMove={eventSelectionMode === 'hover' ? handlePointerMove : undefined}
          onPointerDown={selectNearest}
          onPointerLeave={eventSelectionMode === 'hover' ? handlePointerLeave : undefined}
          onKeyDown={handleKeyDown}
        >
          <PitchMarkings />

          {flows.map(flow => {
            const topLeft = logicalTransform.toScreen({
              x: (flow.bin.column / 6) * 100,
              y: (flow.bin.row / 4) * 100,
            })
            const bottomRight = logicalTransform.toScreen({
              x: ((flow.bin.column + 1) / 6) * 100,
              y: ((flow.bin.row + 1) / 4) * 100,
            })
            return (
              <g
                key={flow.id}
                role="button"
                tabIndex={0}
                aria-label={flowAriaLabel(flow)}
                className="cursor-crosshair outline-none"
                onFocus={() => onSelectedFlowChange?.(flow)}
                onBlur={() => onSelectedFlowChange?.(null)}
                onPointerEnter={event => { event.stopPropagation(); onSelectedFlowChange?.(flow) }}
                onPointerLeave={event => {
                  if (event.pointerType !== 'touch') onSelectedFlowChange?.(null)
                }}
                onPointerDown={event => {
                  event.stopPropagation()
                  onSelectedFlowChange?.(selectedFlowId === flow.id ? null : flow)
                }}
              >
                <rect
                  x={topLeft.x}
                  y={topLeft.y}
                  width={bottomRight.x - topLeft.x}
                  height={bottomRight.y - topLeft.y}
                  fill="transparent"
                  stroke="transparent"
                />
              </g>
            )
          })}

          {selectedEvent?.kind === 'shot' ? (
            <ShotTargetArrow shot={selectedEvent.event as EventShot} />
          ) : null}

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
      <figcaption className="sr-only">
        <span id={accessibleDescriptionId}>
          Use the arrow keys to inspect nearby events. Press Escape to clear the selection.
        </span>
        <span id={accessibleSelectionId} aria-live="polite">
          {selectedEvent?.ariaLabel ?? (selectedFlow ? flowAriaLabel(selectedFlow) : 'No event selected.')}
        </span>
      </figcaption>
    </figure>
  )
})
