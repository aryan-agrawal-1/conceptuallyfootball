import { useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import {
  actionGridCellBounds,
  createPitchTransform,
  PITCH_VIEWBOX_HEIGHT,
  PITCH_VIEWBOX_WIDTH,
} from '../../lib/eventMaps/pitchGeometry'
import {
  classifyDeltaCell,
  deltaModeDescription,
  deltaModeLabel,
  deltaReliabilityLabel,
  formatDeltaValue,
  presentDeltaCell,
  resolveDeltaDomain,
  STATE_DELTA_MAP_CONTRACT_VERSION,
  type DeltaMapAverageMarker,
  type DeltaMapCell,
  type DeltaMapCellStatus,
  type DeltaMapCohortEvidence,
  type DeltaMapMovementArrow,
  type DeltaMapVector,
  type StateDeltaMapContract,
} from '../../lib/eventMaps/deltaMap'
import { cn } from '../../lib/utils'
import { PitchMarkings } from './PitchMarkings'

const pitchTransform = createPitchTransform(PITCH_VIEWBOX_WIDTH, PITCH_VIEWBOX_HEIGHT)

const STATUS_COLOURS: Record<DeltaMapCellStatus, string> = {
  positive: '#1FD17C',
  negative: '#EF5C66',
  unchanged: '#8A95B8',
  absent: '#4E5878',
  sparse: '#F0A832',
  unsupported: '#65759E',
}

const STATUS_LABELS: Record<DeltaMapCellStatus, string> = {
  positive: 'increased',
  negative: 'decreased',
  unchanged: 'unchanged',
  absent: 'absent in both cohorts',
  sparse: 'sparse and interpret cautiously',
  unsupported: 'unsupported in one or both cohorts',
}

function safeId(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]/g, '') || 'map'
}

function countLabel(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString()
}

function minutesLabel(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '—' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} min`
}

function evidenceState(contract: StateDeltaMapContract) {
  const selectedMinutes = contract.selected.exposureMinutes
  const baselineMinutes = contract.baseline.exposureMinutes
  const hasExposure = selectedMinutes != null && baselineMinutes != null && selectedMinutes > 0 && baselineMinutes > 0
  const supportedCells = contract.grid.cells.some(cell => (
    classifyDeltaCell(cell, contract.metric.zeroEpsilon) !== 'unsupported'
  ))
  const hasNoEvents = contract.selected.eventCount === 0 && contract.baseline.eventCount === 0
  if (!hasExposure || !supportedCells || hasNoEvents) return 'unavailable' as const
  if (contract.selected.reliability === 'unavailable' || contract.baseline.reliability === 'unavailable') return 'unavailable' as const
  if (contract.selected.reliability === 'unsupported' || contract.baseline.reliability === 'unsupported') return 'unsupported' as const
  const ratio = Math.min(selectedMinutes / baselineMinutes, baselineMinutes / selectedMinutes)
  if (ratio < 0.25) return 'imbalanced' as const
  if (
    contract.selected.reliability === 'sparse' ||
    contract.baseline.reliability === 'sparse' ||
    contract.selected.reliability === 'partial' ||
    contract.baseline.reliability === 'partial' ||
    contract.grid.cells.some(cell => cell.selectedSparse || cell.baselineSparse)
  ) return 'cautious' as const
  return 'ready' as const
}

function evidenceStateLabel(state: ReturnType<typeof evidenceState>) {
  if (state === 'unavailable') return 'Comparison evidence unavailable'
  if (state === 'unsupported') return 'Comparison not supported'
  if (state === 'imbalanced') return 'Cohorts are highly imbalanced'
  if (state === 'cautious') return 'Interpret sparse evidence cautiously'
  return 'Comparison evidence'
}

function evidenceStateDescription(state: ReturnType<typeof evidenceState>) {
  if (state === 'unavailable') return 'The map is suppressed until both cohorts have verified exposure and at least one supported cell.'
  if (state === 'unsupported') return 'This subject or metric does not have a comparable evidence contract for both cohorts.'
  if (state === 'imbalanced') return 'The smaller cohort has less than one quarter of the other cohort’s supplied exposure. Treat spatial changes as directional evidence, not a stable pattern.'
  if (state === 'cautious') return 'One or more cohorts or cells are sparse or partial. Positive and negative colours remain visible, but interpretation should stay qualified.'
  return 'Positive and negative cells use the same supplied unit and explicit selected-minus-baseline comparison.'
}

function cellKey(cell: Pick<DeltaMapCell, 'column' | 'row'>) {
  return `${cell.column}:${cell.row}`
}

function cellValueLabel(value: number | null, unit: string, rawCount: number | null | undefined) {
  const normalized = formatDeltaValue(value, unit)
  return rawCount == null ? normalized : `${normalized}; ${countLabel(rawCount)} raw events`
}

function cellAriaLabel(
  cell: DeltaMapCell,
  contract: StateDeltaMapContract,
  status: DeltaMapCellStatus,
) {
  const selected = cellValueLabel(cell.selectedValue, contract.metric.unit, cell.selectedRawCount)
  const baseline = cellValueLabel(cell.baselineValue, contract.metric.unit, cell.baselineRawCount)
  const delta = formatDeltaValue(cell.delta, contract.metric.unit)
  return `Grid cell ${cell.column + 1}, row ${cell.row + 1}: ${STATUS_LABELS[status]}. ${contract.selected.label} ${selected}; ${contract.baseline.label} ${baseline}; change ${delta}.`
}

function vectorLabel(vector: DeltaMapVector | undefined, label: string) {
  if (!vector) return null
  const length = vector.meanLengthMetres == null ? null : `${vector.meanLengthMetres.toFixed(1)} metres mean`
  return `${label} vector${length ? `, ${length}` : ''}`
}

function CellTooltip({ cell, contract, status }: {
  cell: DeltaMapCell
  contract: StateDeltaMapContract
  status: DeltaMapCellStatus
}) {
  return (
    <div className="space-y-1.5">
      <p className="font-bold uppercase tracking-[0.1em] text-ink">Cell {cell.column + 1} · row {cell.row + 1}</p>
      <p><span className="text-ink-dim">{contract.selected.label}:</span> {cellValueLabel(cell.selectedValue, contract.metric.unit, cell.selectedRawCount)}</p>
      <p><span className="text-ink-dim">{contract.baseline.label}:</span> {cellValueLabel(cell.baselineValue, contract.metric.unit, cell.baselineRawCount)}</p>
      <p className={status === 'positive' ? 'text-mint' : status === 'negative' ? 'text-ember' : 'text-ink'}><span className="text-ink-dim">Change:</span> {formatDeltaValue(cell.delta, contract.metric.unit)} · {STATUS_LABELS[status]}</p>
      {vectorLabel(cell.selectedVector, contract.selected.label) ? <p className="text-electric">{vectorLabel(cell.selectedVector, contract.selected.label)}</p> : null}
      {vectorLabel(cell.baselineVector, contract.baseline.label) ? <p className="text-ember">{vectorLabel(cell.baselineVector, contract.baseline.label)}</p> : null}
      {status === 'sparse' || status === 'unsupported' ? <p className="text-gold">This cell is not reliable enough for a confident spatial claim.</p> : null}
    </div>
  )
}

function CohortEvidence({ cohort }: { cohort: DeltaMapCohortEvidence }) {
  const exclusions = Object.entries(cohort.exclusions)
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => `${reason.replaceAll('_', ' ')} ${countLabel(count)}`)
  return (
    <div className="border border-line/70 bg-panel/50 px-2.5 py-2" data-delta-cohort={cohort.label}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-ink">{cohort.label}</p>
        <p className="text-[9px] font-bold uppercase tracking-[0.08em] text-electric">{deltaReliabilityLabel(cohort.reliability)}</p>
      </div>
      <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] text-ink-dim">
        <div><dt className="sr-only">Exposure</dt><dd>{minutesLabel(cohort.exposureMinutes)}</dd></div>
        <div><dt className="sr-only">Matches</dt><dd>{countLabel(cohort.matchCount)} matches</dd></div>
        <div><dt className="sr-only">Episodes</dt><dd>{countLabel(cohort.episodeCount)} episodes</dd></div>
        <div><dt className="sr-only">Events</dt><dd>{countLabel(cohort.eventCount)} events</dd></div>
        <div className="col-span-2"><dt className="sr-only">Excluded</dt><dd className={cohort.excludedEventCount ? 'text-gold' : ''}>{countLabel(cohort.excludedEventCount)} excluded</dd></div>
        {cohort.excludedMatchCount != null ? <div className="col-span-2"><dt className="sr-only">Excluded matches</dt><dd className={cohort.excludedMatchCount ? 'text-gold' : ''}>{countLabel(cohort.excludedMatchCount)} excluded matches</dd></div> : null}
      </dl>
      {cohort.locatedEventCount != null ? <p className="mt-1 text-[9px] text-ink-muted">{countLabel(cohort.locatedEventCount)} located events</p> : null}
      <p className="mt-1 text-[9px] leading-relaxed text-ink-muted">{exclusions.length ? exclusions.join(' · ') : 'No exclusions recorded'}</p>
    </div>
  )
}

export function DeltaMapEvidenceDisclosure({ contract }: { contract: StateDeltaMapContract }) {
  return (
    <section className="space-y-2" aria-label="State Delta Map evidence samples">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-[10px] font-bold uppercase tracking-[0.12em] text-ink-dim">Evidence samples</h4>
        <span className="font-mono text-[9px] text-ink-muted">{contract.subject.type} · {contractVersion(contract)}</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
        <CohortEvidence cohort={contract.selected} />
        <CohortEvidence cohort={contract.baseline} />
      </div>
    </section>
  )
}

function contractVersion(contract: StateDeltaMapContract) {
  return contract.contractVersion ?? STATE_DELTA_MAP_CONTRACT_VERSION
}

function markerColour(marker: DeltaMapAverageMarker) {
  if (marker.tone === 'selected') return '#4A9EF5'
  if (marker.tone === 'baseline') return '#EF5C66'
  return '#F0A832'
}

function DeltaAverageMarker({ marker }: { marker: DeltaMapAverageMarker }) {
  const point = pitchTransform.toScreen(marker.coordinate)
  const colour = markerColour(marker)
  const shape = marker.tone === 'reference' ? (
    <circle cx={point.x} cy={point.y} r={8} fill="none" stroke={colour} strokeWidth={2} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
  ) : marker.tone === 'baseline' ? (
    <rect x={point.x - 8} y={point.y - 8} width={16} height={16} fill={colour} fillOpacity={0.2} stroke={colour} strokeWidth={2} transform={`rotate(45 ${point.x} ${point.y})`} vectorEffect="non-scaling-stroke" />
  ) : (
    <circle cx={point.x} cy={point.y} r={8} fill={colour} fillOpacity={0.22} stroke={colour} strokeWidth={2} vectorEffect="non-scaling-stroke" />
  )
  return (
    <g role="img" aria-label={`${marker.label}, ${marker.sampleSize == null ? 'sample size unavailable' : `${countLabel(marker.sampleSize)} events`}${marker.description ? `. ${marker.description}` : ''}`} pointerEvents="none">
      {shape}
      <text x={point.x} y={Math.max(14, point.y - 15)} textAnchor="middle" fill={colour} className="text-[10px] font-bold uppercase tracking-[0.1em]">{marker.label}</text>
    </g>
  )
}

function movementArrow(
  movement: DeltaMapMovementArrow,
  arrowId: string,
  secondary = false,
) {
  const from = pitchTransform.toScreen(movement.from)
  const to = pitchTransform.toScreen(movement.to)
  return (
    <g aria-label={movement.label ?? (secondary ? 'Matched team movement reference' : 'Average-position movement')} role="img" opacity={secondary ? 0.7 : 1} pointerEvents="none">
      <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={secondary ? '#8A95B8' : '#F0A832'} strokeWidth={secondary ? 1.8 : 2.5} strokeDasharray={secondary ? '6 6' : '10 6'} markerEnd={`url(#${arrowId})`} vectorEffect="non-scaling-stroke" pointerEvents="none" />
    </g>
  )
}

function vectorLine(vector: DeltaMapVector | undefined, tone: 'selected' | 'baseline', arrowId: string, index: number) {
  if (!vector) return null
  const origin = pitchTransform.toScreen(vector.origin)
  const destination = pitchTransform.toScreen(vector.destination)
  const deltaX = destination.x - origin.x
  const deltaY = destination.y - origin.y
  const distance = Math.hypot(deltaX, deltaY)
  if (distance < 1) return null
  const offset = tone === 'selected' ? -5 : 5
  const offsetX = (-deltaY / distance) * offset
  const offsetY = (deltaX / distance) * offset
  return (
    <line
      key={`${tone}-vector-${index}`}
      x1={origin.x + offsetX}
      y1={origin.y + offsetY}
      x2={destination.x + offsetX}
      y2={destination.y + offsetY}
      stroke={tone === 'selected' ? '#4A9EF5' : '#EF5C66'}
      strokeWidth={tone === 'selected' ? 2.4 : 2}
      strokeDasharray={tone === 'selected' ? undefined : '7 5'}
      markerEnd={`url(#${arrowId})`}
      vectorEffect="non-scaling-stroke"
      opacity={0.95}
      pointerEvents="none"
    />
  )
}

export function DeltaMapLegend({ contract, domain }: { contract: StateDeltaMapContract; domain?: number }) {
  const resolvedDomain = domain ?? resolveDeltaDomain(contract.grid.cells, contract.metric.domain)
  return (
    <div className="space-y-2" role="group" aria-label="State Delta Map legend">
      <div className="flex items-center justify-between gap-3 text-[9px] font-bold uppercase tracking-[0.1em] text-ink-dim">
        <span className="text-ember">Decrease −{formatDeltaValue(resolvedDomain, contract.metric.unit).replace('+', '')}</span>
        <span>Zero</span>
        <span className="text-mint">Increase +{formatDeltaValue(resolvedDomain, contract.metric.unit).replace('+', '')}</span>
      </div>
      <div className="h-2 border border-line-bright bg-[linear-gradient(90deg,#EF5C66,#4E5878_48%,#4E5878_52%,#1FD17C)]" aria-hidden="true" />
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-ink-dim">
        <span><i className="mr-1 inline-block size-2 bg-mint align-middle" aria-hidden="true" />Increase</span>
        <span><i className="mr-1 inline-block size-2 bg-ember align-middle" aria-hidden="true" />Decrease</span>
        <span><i className="mr-1 inline-block size-2 bg-ink-muted align-middle" aria-hidden="true" />Absent</span>
        <span><i className="mr-1 inline-block size-2 border border-gold align-middle" aria-hidden="true" />Sparse</span>
        <span><i className="mr-1 inline-block size-2 border border-ink-muted align-middle" aria-hidden="true" />Unsupported</span>
      </div>
      <p className="text-[10px] leading-relaxed text-ink-dim">Domain is symmetric around zero; values beyond ±{formatDeltaValue(resolvedDomain, contract.metric.unit).replace('+', '')} are clipped for display. {contract.metric.smoothing === 'supplied' ? 'The evidence producer supplied smoothing.' : 'Cells are rendered without client-side smoothing.'}</p>
    </div>
  )
}

function DeltaPitch({
  contract,
  domain,
  mapId,
  activeCell,
  selectedCell,
  setActiveCell,
  setSelectedCell,
  onCellSelect,
  exportMode,
}: {
  contract: StateDeltaMapContract
  domain: number
  mapId: string
  activeCell: DeltaMapCell | null
  selectedCell: DeltaMapCell | null
  setActiveCell: (cell: DeltaMapCell | null) => void
  setSelectedCell: (cell: DeltaMapCell | null) => void
  onCellSelect?: (cell: DeltaMapCell | null) => void
  exportMode: boolean
}) {
  const cellRefs = useRef<Record<string, SVGRectElement | null>>({})
  const activeId = activeCell ? cellKey(activeCell) : null
  const selectedId = selectedCell ? cellKey(selectedCell) : null
  const zeroEpsilon = contract.metric.zeroEpsilon
  const mapDescriptionId = `${mapId}-description`
  const activeDescriptionId = `${mapId}-active`
  const arrowSelectedId = `${mapId}-selected-arrow`
  const arrowBaselineId = `${mapId}-baseline-arrow`
  const arrowMovementId = `${mapId}-movement-arrow`
  const arrowTeamReferenceId = `${mapId}-team-reference-arrow`

  const focusCell = (cell: DeltaMapCell) => {
    cellRefs.current[cellKey(cell)]?.focus()
  }

  const moveCell = (cell: DeltaMapCell, direction: 'up' | 'down' | 'left' | 'right') => {
    const rowDelta = direction === 'up' ? -1 : direction === 'down' ? 1 : 0
    const columnDelta = direction === 'left' ? -1 : direction === 'right' ? 1 : 0
    const targetRow = cell.row + rowDelta
    const targetColumn = cell.column + columnDelta
    const exact = contract.grid.cells.find(candidate => candidate.row === targetRow && candidate.column === targetColumn)
    if (exact) {
      focusCell(exact)
      return
    }
    const candidates = contract.grid.cells.filter(candidate => (
      direction === 'up' || direction === 'down'
        ? candidate.column === cell.column
        : candidate.row === cell.row
    ))
    const next = candidates
      .filter(candidate => direction === 'up' ? candidate.row < cell.row : direction === 'down' ? candidate.row > cell.row : direction === 'left' ? candidate.column < cell.column : candidate.column > cell.column)
      .sort((first, second) => direction === 'up' || direction === 'left'
        ? (direction === 'up' ? second.row - first.row : second.column - first.column)
        : (direction === 'down' ? first.row - second.row : first.column - second.column))[0]
    if (next) focusCell(next)
  }

  const onCellKeyDown = (event: KeyboardEvent<SVGRectElement | SVGSVGElement>, cell: DeltaMapCell) => {
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown' || event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault()
      moveCell(cell, event.key === 'ArrowUp' ? 'up' : event.key === 'ArrowDown' ? 'down' : event.key === 'ArrowLeft' ? 'left' : 'right')
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      const next = selectedId === cellKey(cell) ? null : cell
      setSelectedCell(next)
      onCellSelect?.(next)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      setSelectedCell(null)
      onCellSelect?.(null)
    }
  }

  const onMapKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    if (event.target !== event.currentTarget) return
    const cell = activeCell ?? selectedCell ?? contract.grid.cells[0]
    if (cell) onCellKeyDown(event, cell)
  }

  return (
    <div className={cn('relative w-full overflow-hidden border border-line-bright bg-panel shadow-[0_18px_48px_rgba(0,0,0,0.30)]', exportMode && 'print-color-exact')} style={{ backgroundImage: 'radial-gradient(circle at 72% 44%, rgba(74,158,245,0.10), transparent 42%)' }} data-delta-map-pitch={contract.metric.mode}>
      <svg
        viewBox={`0 0 ${PITCH_VIEWBOX_WIDTH} ${PITCH_VIEWBOX_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        className="block aspect-[105/68] size-full touch-none text-ink outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-electric"
        role="application"
        tabIndex={0}
        aria-roledescription="State Delta Map"
        aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight Enter Space Escape"
        aria-label={`${contract.subject.name} ${contract.metric.label} State Delta Map. ${deltaModeLabel(contract.metric.mode)}.`}
        aria-describedby={`${mapDescriptionId} ${activeDescriptionId}`}
        onKeyDown={onMapKeyDown}
      >
        <defs>
          <marker id={arrowSelectedId} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#4A9EF5" />
          </marker>
          <marker id={arrowBaselineId} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#EF5C66" />
          </marker>
          <marker id={arrowMovementId} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#F0A832" />
          </marker>
          <marker id={arrowTeamReferenceId} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#8A95B8" />
          </marker>
          <pattern id={`${mapId}-sparse-pattern`} width="12" height="12" patternUnits="userSpaceOnUse">
            <rect width="12" height="12" fill="#F0A832" fillOpacity="0.10" />
            <path d="M -3 3 L 3 -3 M 0 12 L 12 0 M 9 15 L 15 9" stroke="#F0A832" strokeOpacity="0.75" strokeWidth="2" />
          </pattern>
          <pattern id={`${mapId}-unsupported-pattern`} width="10" height="10" patternUnits="userSpaceOnUse">
            <rect width="10" height="10" fill="#65759E" fillOpacity="0.08" />
            <path d="M 0 0 L 10 10 M 10 0 L 0 10" stroke="#65759E" strokeOpacity="0.42" strokeWidth="1.5" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={PITCH_VIEWBOX_WIDTH} height={PITCH_VIEWBOX_HEIGHT} fill="var(--color-panel)" />
        <PitchMarkings />
        {contract.grid.cells.map(cell => {
          const bounds = actionGridCellBounds(cell.column, cell.row, contract.grid.columns, contract.grid.rows)
          const topLeft = pitchTransform.toScreen({ x: bounds.xMin, y: bounds.yMin })
          const bottomRight = pitchTransform.toScreen({ x: bounds.xMax, y: bounds.yMax })
          const presentation = presentDeltaCell(cell, domain, zeroEpsilon)
          const status = presentation.status
          const fill = status === 'sparse'
            ? `url(#${mapId}-sparse-pattern)`
            : status === 'unsupported'
              ? `url(#${mapId}-unsupported-pattern)`
              : STATUS_COLOURS[status]
          const fillOpacity = status === 'positive' || status === 'negative'
            ? 0.14 + presentation.intensity * 0.62
            : status === 'unchanged' ? 0.18 : status === 'absent' ? 0.10 : 1
          const isActive = activeId === cellKey(cell)
          const isSelected = selectedId === cellKey(cell)
          return (
            <rect
              key={cellKey(cell)}
              ref={node => { cellRefs.current[cellKey(cell)] = node }}
              x={topLeft.x + 1}
              y={topLeft.y + 1}
              width={Math.max(0, bottomRight.x - topLeft.x - 2)}
              height={Math.max(0, bottomRight.y - topLeft.y - 2)}
              fill={fill}
              fillOpacity={fillOpacity}
              stroke={isActive || isSelected ? '#E4EAF8' : STATUS_COLOURS[status]}
              strokeOpacity={isActive || isSelected ? 0.95 : 0.18}
              strokeWidth={isActive || isSelected ? 2.4 : 0.8}
              vectorEffect="non-scaling-stroke"
              role="button"
              tabIndex={0}
              aria-label={cellAriaLabel(cell, contract, status)}
              onPointerEnter={(event: PointerEvent<SVGRectElement>) => {
                if (event.pointerType !== 'touch') setActiveCell(cell)
              }}
              onFocus={() => setActiveCell(cell)}
              onBlur={() => setActiveCell(null)}
              onPointerLeave={(event: PointerEvent<SVGRectElement>) => {
                if (event.pointerType !== 'touch' && selectedId !== cellKey(cell)) setActiveCell(null)
              }}
              onClick={() => {
                const next = selectedId === cellKey(cell) ? null : cell
                setSelectedCell(next)
                onCellSelect?.(next)
              }}
              onKeyDown={event => onCellKeyDown(event, cell)}
            />
          )
        })}
        {contract.grid.cells.flatMap((cell, index) => [
          vectorLine(cell.selectedVector, 'selected', arrowSelectedId, index),
          vectorLine(cell.baselineVector, 'baseline', arrowBaselineId, index),
        ])}
        {contract.movement ? movementArrow(contract.movement, arrowMovementId) : null}
        {contract.teamReferenceMovement ? movementArrow(contract.teamReferenceMovement, arrowTeamReferenceId, true) : null}
        {contract.markers?.baseline ? <DeltaAverageMarker marker={contract.markers.baseline} /> : null}
        {contract.markers?.selected ? <DeltaAverageMarker marker={contract.markers.selected} /> : null}
        {contract.markers?.teamReference ? <DeltaAverageMarker marker={contract.markers.teamReference} /> : null}
      </svg>
      <div className="pointer-events-none absolute inset-x-2 bottom-2 flex justify-between gap-2 text-[8px] font-bold uppercase tracking-[0.14em] text-ink/75" aria-hidden="true">
        <span>Own goal</span><span>Opponent goal</span>
      </div>
    </div>
  )
}

export type StateDeltaMapProps = {
  contract: StateDeltaMapContract
  className?: string
  compact?: boolean
  /** Keep true when a share/export surface captures the component. */
  exportMode?: boolean
  onCellSelect?: (cell: DeltaMapCell | null) => void
}

export function StateDeltaMap({
  contract,
  className,
  compact = false,
  exportMode = false,
  onCellSelect,
}: StateDeltaMapProps) {
  const id = safeId(useId())
  const [activeCell, setActiveCell] = useState<DeltaMapCell | null>(null)
  const [selectedCell, setSelectedCell] = useState<DeltaMapCell | null>(null)
  const domain = useMemo(
    () => resolveDeltaDomain(contract.grid.cells, contract.metric.domain),
    [contract.grid.cells, contract.metric.domain],
  )
  const state = evidenceState(contract)
  const shownCell = selectedCell ?? activeCell
  const mapId = `state-delta-${id}`
  const mapDescriptionId = `${mapId}-description`
  const activeDescriptionId = `${mapId}-active`

  return (
    <section className={cn('min-w-0 space-y-3', className)} aria-label={`${contract.subject.name} State Delta Map`} data-delta-map-mode={contract.metric.mode} data-delta-map-subject={contract.subject.type} data-delta-map-version={contractVersion(contract)}>
      <header className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
        <div className="min-w-0">
          <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">{contract.metric.label}</h3>
          <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">{deltaModeLabel(contract.metric.mode)} · {contract.metric.description ?? deltaModeDescription(contract.metric.mode)}</p>
        </div>
        <p className="shrink-0 text-[9px] font-bold uppercase tracking-[0.1em] text-electric">{contract.selected.label} − {contract.baseline.label}</p>
      </header>

      <div className={cn('grid min-w-0 items-start gap-4', compact ? 'lg:grid-cols-[minmax(0,1.35fr)_minmax(220px,0.65fr)]' : 'lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]')}>
        <div className="min-w-0 space-y-2">
          <div id={mapDescriptionId} className="sr-only">{evidenceStateDescription(state)} Use Tab to enter a cell and the arrow keys to move between cells. Enter or Space selects a cell; Escape clears it.</div>
          {state !== 'ready' ? (
            <div className={cn('border px-3 py-2 text-[10px] leading-relaxed', state === 'unavailable' || state === 'unsupported' ? 'border-ember/45 bg-ember/8 text-ember' : 'border-gold/45 bg-gold/8 text-gold')} role="status" data-delta-evidence-state={state}>
              <p className="font-bold uppercase tracking-[0.1em]">{evidenceStateLabel(state)}</p>
              <p className="mt-1 text-ink-dim">{evidenceStateDescription(state)}</p>
            </div>
          ) : null}
          <div className={state === 'unavailable' || state === 'unsupported' ? 'opacity-45' : undefined}>
            <DeltaPitch
              contract={contract}
              domain={domain}
              mapId={mapId}
              activeCell={activeCell}
              selectedCell={selectedCell}
              setActiveCell={setActiveCell}
              setSelectedCell={setSelectedCell}
              onCellSelect={onCellSelect}
              exportMode={exportMode}
            />
          </div>
          <div id={activeDescriptionId} className="min-h-7 border border-line-bright bg-raised/45 px-2.5 py-2 text-[10px] leading-relaxed text-ink-dim" role="status" aria-live="polite">
            {shownCell ? <CellTooltip cell={shownCell} contract={contract} status={classifyDeltaCell(shownCell, contract.metric.zeroEpsilon)} /> : 'Focus or select a cell to inspect the supplied baseline value, selected value, raw event counts, and delta.'}
          </div>
          <DeltaMapLegend contract={contract} domain={domain} />
          {contract.notes?.length ? <div className="space-y-1 text-[10px] leading-relaxed text-ink-dim">{contract.notes.map(note => <p key={note}>· {note}</p>)}</div> : null}
        </div>

        <aside className="min-w-0 space-y-3 border-t border-line-bright pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0" aria-label="State Delta Map details">
          <DeltaMapEvidenceDisclosure contract={contract} />
          <div className="space-y-1 text-[10px] leading-relaxed text-ink-dim">
            <p><span className="font-bold uppercase tracking-[0.08em] text-ink-dim">Subject:</span> {contract.subject.name} ({contract.subject.type})</p>
            <p><span className="font-bold uppercase tracking-[0.08em] text-ink-dim">Unit:</span> {contract.metric.unit}</p>
            <p><span className="font-bold uppercase tracking-[0.08em] text-ink-dim">Smoothing:</span> {contract.metric.smoothing === 'supplied' ? 'Supplied by evidence producer' : 'None; fixed grid cells'}</p>
            <p><span className="font-bold uppercase tracking-[0.08em] text-ink-dim">Cells:</span> {contract.grid.columns} × {contract.grid.rows}; zero is stable and absent cells are not raw-total subtraction.</p>
            {contract.movement ? <p className="text-gold"><span className="font-bold uppercase tracking-[0.08em]">Movement:</span> {contract.movement.label ?? 'Average-position shift'}{contract.movement.distance == null ? '' : ` · ${contract.movement.distance.toFixed(1)} pitch points`}</p> : null}
            {contract.teamReferenceMovement ? <p className="text-ink-dim"><span className="font-bold uppercase tracking-[0.08em]">Team reference:</span> {contract.teamReferenceMovement.label ?? 'Matched team movement'}{contract.teamReferenceMovement.distance == null ? '' : ` · ${contract.teamReferenceMovement.distance.toFixed(1)} pitch points`}</p> : null}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] font-bold uppercase tracking-[0.08em] text-ink-dim" aria-label="State Delta Map vector legend">
            {contract.markers?.selected ? <span className="text-electric"><i className="mr-1 inline-block size-2 rounded-full border border-electric align-middle" aria-hidden="true" />{contract.markers.selected.label}</span> : null}
            {contract.markers?.baseline ? <span className="text-ember"><i className="mr-1 inline-block size-2 rotate-45 border border-ember align-middle" aria-hidden="true" />{contract.markers.baseline.label}</span> : null}
            {contract.grid.cells.some(cell => cell.selectedVector) ? <span className="text-electric"><i className="mr-1 inline-block h-px w-4 bg-electric align-middle" aria-hidden="true" />{contract.selected.label} vector</span> : null}
            {contract.grid.cells.some(cell => cell.baselineVector) ? <span className="text-ember"><i className="mr-1 inline-block h-px w-4 border-t border-dashed border-ember align-middle" aria-hidden="true" />{contract.baseline.label} vector</span> : null}
            {contract.markers?.teamReference ? <span className="text-gold"><i className="mr-1 inline-block size-2 rounded-full border border-dashed border-gold align-middle" aria-hidden="true" />Matched team reference</span> : null}
            {contract.teamReferenceMovement ? <span className="text-ink-dim"><i className="mr-1 inline-block h-px w-4 border-t border-dashed border-ink-dim align-middle" aria-hidden="true" />Team movement reference</span> : null}
          </div>
        </aside>
      </div>
    </section>
  )
}

/** Short alias for consumers that call the primitive simply DeltaMap. */
export const DeltaMap = StateDeltaMap
