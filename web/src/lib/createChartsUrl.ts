import { DEFAULT_FILTERS } from '../hooks/useStatMatrix'
import type {
  GalaxyEdge,
  GalaxyPoint,
  MatrixFilters,
  PlayerRow,
  PositionGroup,
  TeamDetailResponse,
} from '../types/api'
import {
  DEFAULT_BAR_COUNT,
  writeDataVisualiserParams,
  type DataVisualiserUrlState,
  type VisualiserBarWindow,
  type VisualiserPlayerPosition,
} from './dataVisualiserUrl'
import type { ProfileRateMode } from './profileMetrics'

export const CREATE_CHARTS_PATH = '/create-charts'
export const LEGACY_DATA_VISUALISER_PATH = '/data-visualiser'

const DEFAULT_CHART_STATE: DataVisualiserUrlState = {
  tab: 'players',
  chart: 'scatter',
  competition: DEFAULT_FILTERS.competition,
  season: DEFAULT_FILTERS.season,
  position: 'ALL',
  playerTeams: [],
  minMinutes: DEFAULT_FILTERS.min_minutes,
  mode: 'per90',
  radarMetrics: [],
  compareIds: [],
  pinnedIds: [],
  barWindow: 'top',
  barCount: DEFAULT_BAR_COUNT,
  labels: false,
}

function playerPosition(position: PositionGroup | string | undefined): VisualiserPlayerPosition {
  if (position === 'FWD' || position === 'MID' || position === 'DEF' || position === 'GK') return position
  return 'ALL'
}

export function buildCreateChartsPath(next: Partial<DataVisualiserUrlState> = {}): string {
  const state: DataVisualiserUrlState = {
    ...DEFAULT_CHART_STATE,
    ...next,
    playerTeams: next.playerTeams ?? DEFAULT_CHART_STATE.playerTeams,
    radarMetrics: next.radarMetrics ?? DEFAULT_CHART_STATE.radarMetrics,
    compareIds: next.compareIds ?? DEFAULT_CHART_STATE.compareIds,
    pinnedIds: next.pinnedIds ?? DEFAULT_CHART_STATE.pinnedIds,
  }
  const p = writeDataVisualiserParams(state)
  return `${CREATE_CHARTS_PATH}?${p.toString()}`
}

export function buildMatrixCreateChartsPath(
  filters: MatrixFilters,
  mode: ProfileRateMode,
): string {
  return buildCreateChartsPath({
    tab: 'players',
    chart: 'scatter',
    competition: filters.competition,
    season: filters.season,
    position: playerPosition(filters.position_group),
    playerTeams: filters.teams ?? [],
    minMinutes: filters.min_minutes,
    mode,
    labels: true,
  })
}

export function buildMatrixMetricCreateChartsPath({
  filters,
  mode,
  metric,
  barWindow,
}: {
  filters: MatrixFilters
  mode: ProfileRateMode
  metric: string
  barWindow: Extract<VisualiserBarWindow, 'top' | 'bottom'>
}): string {
  const path = buildCreateChartsPath({
    tab: 'players',
    chart: 'bar',
    competition: filters.competition,
    season: filters.season,
    position: playerPosition(filters.position_group),
    playerTeams: filters.teams ?? [],
    minMinutes: filters.min_minutes,
    mode,
    metric,
    barWindow,
    barCount: 12,
  })
  const [pathname, query] = path.split('?')
  const params = new URLSearchParams(query)
  params.set('bar_window', barWindow)
  params.set('bar_count', '12')
  return `${pathname}?${params.toString()}`
}

export function buildPlayerCreateChartsPath(
  player: PlayerRow,
  mode: ProfileRateMode = 'per90',
): string {
  return buildCreateChartsPath({
    tab: 'players',
    chart: 'scatter',
    competition: player.competition_code,
    season: player.season_label,
    position: playerPosition(player.position_group),
    mode,
    pinnedIds: [player.canonical_player_id],
    labels: true,
  })
}

export function buildTeamCreateChartsPath(
  team: TeamDetailResponse,
  mode: ProfileRateMode = 'full',
): string {
  return buildCreateChartsPath({
    tab: 'teams',
    chart: 'bar',
    competition: team.competition_code,
    season: team.season_label,
    mode,
    pinnedIds: [team.canonical_team_id],
  })
}

export function buildComparisonCreateChartsPath({
  competition,
  season,
  playerIds,
  metricKeys,
  mode,
}: {
  competition: string
  season: string
  playerIds: number[]
  metricKeys: string[]
  mode: ProfileRateMode
}): string {
  return buildCreateChartsPath({
    tab: 'players',
    chart: 'radar',
    competition,
    season,
    mode,
    radarMetrics: metricKeys,
    compareIds: playerIds.slice(0, 3),
    pinnedIds: playerIds.slice(0, 5),
  })
}

export function buildGalaxyCreateChartsPath({
  competition,
  season,
  selectedPoint,
  edges,
}: {
  competition: string
  season: string
  selectedPoint?: GalaxyPoint | null
  edges?: GalaxyEdge[]
}): string {
  if (!selectedPoint) {
    return buildCreateChartsPath({
      tab: 'players',
      chart: 'scatter',
      competition,
      season,
      labels: true,
    })
  }
  const seen = new Set<number>()
  const playerIds = [selectedPoint.canonical_player_id, ...(edges ?? []).map(edge => edge.to_player_id)]
    .filter(id => {
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
  return buildCreateChartsPath({
    tab: 'players',
    chart: 'radar',
    competition,
    season,
    position: playerPosition(selectedPoint.position_group),
    compareIds: playerIds.slice(0, 3),
    pinnedIds: playerIds.slice(0, 5),
    labels: true,
  })
}
