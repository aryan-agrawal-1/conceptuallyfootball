import type { PitchCoordinate } from '../../types/eventMaps'

/**
 * Versioned, provider-neutral input for a comparison pitch.
 *
 * The renderer deliberately receives already-normalised values.  In
 * particular, it never derives an exposure denominator from event rows.  A
 * player consumer can therefore pass verified on-pitch minutes from #118,
 * while a team consumer can pass canonical State Lens minutes, without the
 * two surfaces accidentally sharing a denominator.
 */
export const STATE_DELTA_MAP_CONTRACT_VERSION = 'state-delta-map/v1'

export type DeltaMapSubjectType = 'team' | 'player'

export type DeltaMapMode =
  | 'absolute-rate'
  | 'distribution'
  | 'within-team-relative'

export type DeltaMapSmoothing = 'none' | 'supplied'

export type DeltaMapReliability =
  | 'verified'
  | 'partial'
  | 'sparse'
  | 'unsupported'
  | 'unavailable'

export type DeltaMapCellStatus =
  | 'positive'
  | 'negative'
  | 'unchanged'
  | 'absent'
  | 'sparse'
  | 'unsupported'

export type DeltaMapCohortEvidence = {
  /** Human-readable State Lens scope, for example "Losing" or "Drawing". */
  label: string
  /** Exposure supplied by the evidence producer; never inferred by the map. */
  exposureMinutes: number | null
  matchCount: number | null
  episodeCount: number | null
  eventCount: number | null
  locatedEventCount?: number | null
  excludedEventCount: number | null
  excludedMatchCount?: number | null
  exclusions: Record<string, number>
  reliability: DeltaMapReliability
}

export type DeltaMapSubject = {
  type: DeltaMapSubjectType
  id?: number | string
  name: string
}

export type DeltaMapCell = {
  column: number
  row: number
  /** Values are already normalised to the metric's declared unit. */
  selectedValue: number | null
  baselineValue: number | null
  /** Selected minus baseline. Null means that the comparison is unsupported. */
  delta: number | null
  selectedRawCount?: number | null
  baselineRawCount?: number | null
  selectedSupported?: boolean
  baselineSupported?: boolean
  selectedSparse?: boolean
  baselineSparse?: boolean
  selectedVector?: DeltaMapVector
  baselineVector?: DeltaMapVector
}

export type DeltaMapVector = {
  origin: PitchCoordinate
  destination: PitchCoordinate
  /** Kept for disclosure; vector geometry remains the supplied coordinates. */
  meanLengthMetres?: number | null
  eventCount?: number | null
}

export type DeltaMapAverageMarker = {
  id: string
  label: string
  coordinate: PitchCoordinate
  sampleSize: number | null
  tone: 'selected' | 'baseline' | 'reference'
  description?: string
}

export type DeltaMapMovementArrow = {
  from: PitchCoordinate
  to: PitchCoordinate
  label?: string
  /** Distance in pitch percentage points, supplied by the evidence producer. */
  distance?: number | null
}

export type DeltaMapGrid = {
  columns: number
  rows: number
  cells: DeltaMapCell[]
}

export type StateDeltaMapContract = {
  contractVersion?: string
  subject: DeltaMapSubject
  metric: {
    label: string
    unit: string
    mode: DeltaMapMode
    description?: string
    /** Rendering never invents smoothing; `supplied` means the producer did. */
    smoothing?: DeltaMapSmoothing
    /** A shared domain keeps separate maps visually comparable. */
    domain?: number | null
    /** Values within this epsilon are a stable zero, not a sign change. */
    zeroEpsilon?: number
  }
  selected: DeltaMapCohortEvidence
  baseline: DeltaMapCohortEvidence
  grid: DeltaMapGrid
  markers?: {
    selected?: DeltaMapAverageMarker | null
    baseline?: DeltaMapAverageMarker | null
    teamReference?: DeltaMapAverageMarker | null
  }
  movement?: DeltaMapMovementArrow | null
  /** Optional matched-team movement, kept visually secondary to `movement`. */
  teamReferenceMovement?: DeltaMapMovementArrow | null
  notes?: string[]
}

export type DeltaMapCellInput = {
  column: number
  row: number
  selectedValue: number | null
  baselineValue: number | null
  /** Optional server-computed value; omitted values are safely subtracted here. */
  delta?: number | null
  selectedRawCount?: number | null
  baselineRawCount?: number | null
  selectedSupported?: boolean
  baselineSupported?: boolean
  selectedSparse?: boolean
  baselineSparse?: boolean
  selectedVector?: DeltaMapVector
  baselineVector?: DeltaMapVector
}

export type DeltaMapPresentation = {
  status: DeltaMapCellStatus
  intensity: number
  clipped: boolean
}

const DEFAULT_ZERO_EPSILON = 0.000001
export const DELTA_MAP_ZERO_EPSILON = DEFAULT_ZERO_EPSILON

function finiteOrNull(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? null : value
}

/**
 * Build one comparison cell from two values in the same declared unit.
 * This function intentionally does not accept raw exposure or event arrays.
 */
export function buildStateDeltaCell(input: DeltaMapCellInput): DeltaMapCell {
  const selectedValue = finiteOrNull(input.selectedValue)
  const baselineValue = finiteOrNull(input.baselineValue)
  const delta = input.delta !== undefined
    ? finiteOrNull(input.delta)
    : selectedValue == null || baselineValue == null
      ? null
      : selectedValue - baselineValue
  return {
    column: input.column,
    row: input.row,
    selectedValue,
    baselineValue,
    delta,
    selectedRawCount: input.selectedRawCount ?? null,
    baselineRawCount: input.baselineRawCount ?? null,
    selectedSupported: input.selectedSupported ?? selectedValue != null,
    baselineSupported: input.baselineSupported ?? baselineValue != null,
    selectedSparse: input.selectedSparse ?? false,
    baselineSparse: input.baselineSparse ?? false,
    selectedVector: input.selectedVector,
    baselineVector: input.baselineVector,
  }
}

/** Alias kept short for consumers assembling several grid cells. */
export const createDeltaCell = buildStateDeltaCell
export const buildDeltaCell = buildStateDeltaCell

export function buildStateDeltaGrid({
  columns,
  rows,
  cells,
}: {
  columns: number
  rows: number
  cells: DeltaMapCellInput[]
}): DeltaMapGrid {
  const safeColumns = Math.max(1, Math.floor(columns))
  const safeRows = Math.max(1, Math.floor(rows))
  const byCoordinate = new Map(cells.map(cell => [`${cell.column}:${cell.row}`, cell]))
  const normalized: DeltaMapCell[] = []
  for (let row = 0; row < safeRows; row += 1) {
    for (let column = 0; column < safeColumns; column += 1) {
      const cell = byCoordinate.get(`${column}:${row}`)
      normalized.push(buildStateDeltaCell(cell ?? {
        column,
        row,
        selectedValue: null,
        baselineValue: null,
        selectedSupported: false,
        baselineSupported: false,
      }))
    }
  }
  return { columns: safeColumns, rows: safeRows, cells: normalized }
}

export const buildDeltaGrid = buildStateDeltaGrid

export function resolveDeltaDomain(
  cells: readonly DeltaMapCell[],
  configuredDomain?: number | null,
) {
  const configured = finiteOrNull(configuredDomain)
  if (configured != null && configured > DEFAULT_ZERO_EPSILON) return configured
  const maximum = cells.reduce((current, cell) => {
    const value = finiteOrNull(cell.delta)
    return value == null ? current : Math.max(current, Math.abs(value))
  }, 0)
  return Math.max(DEFAULT_ZERO_EPSILON, maximum)
}

export function classifyDeltaCell(
  cell: DeltaMapCell,
  zeroEpsilon = DEFAULT_ZERO_EPSILON,
): DeltaMapCellStatus {
  if (cell.selectedSupported === false || cell.baselineSupported === false) return 'unsupported'
  if (cell.selectedValue == null || cell.baselineValue == null || cell.delta == null) return 'unsupported'
  if (
    Math.abs(cell.selectedValue) <= zeroEpsilon &&
    Math.abs(cell.baselineValue) <= zeroEpsilon
  ) return 'absent'
  if (cell.selectedSparse || cell.baselineSparse) return 'sparse'
  if (Math.abs(cell.delta) <= zeroEpsilon) return 'unchanged'
  return cell.delta > 0 ? 'positive' : 'negative'
}

export function presentDeltaCell(
  cell: DeltaMapCell,
  domain: number,
  zeroEpsilon = DEFAULT_ZERO_EPSILON,
): DeltaMapPresentation {
  const status = classifyDeltaCell(cell, zeroEpsilon)
  if (status === 'unsupported' || status === 'sparse' || status === 'absent' || status === 'unchanged') {
    return { status, intensity: 0, clipped: false }
  }
  const magnitude = Math.abs(cell.delta ?? 0)
  return {
    status,
    intensity: Math.min(1, magnitude / Math.max(DEFAULT_ZERO_EPSILON, domain)),
    clipped: magnitude > domain,
  }
}

export function formatDeltaValue(value: number | null | undefined, unit: string) {
  if (value == null || !Number.isFinite(value)) return 'Not supported'
  const precision = Math.abs(value) >= 10 ? 1 : Math.abs(value) >= 1 ? 2 : 3
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(precision)} ${unit}`
}

export function deltaModeLabel(mode: DeltaMapMode) {
  if (mode === 'absolute-rate') return 'Absolute action-rate change'
  if (mode === 'within-team-relative') return 'Within-team relative change'
  return 'Within-subject spatial distribution change'
}

export function deltaModeDescription(mode: DeltaMapMode) {
  if (mode === 'absolute-rate') {
    return 'Selected-minus-baseline values use the supplied exposure-normalised rate.'
  }
  if (mode === 'within-team-relative') {
    return 'Selected-minus-baseline values use the supplied team-relative action share.'
  }
  return 'Selected-minus-baseline values compare each subject’s supplied spatial distribution.'
}

export function deltaReliabilityLabel(reliability: DeltaMapReliability) {
  return reliability === 'verified'
    ? 'Verified'
    : reliability === 'partial'
      ? 'Partial'
      : reliability === 'sparse'
        ? 'Sparse'
        : reliability === 'unsupported'
          ? 'Unsupported'
          : 'Unavailable'
}
