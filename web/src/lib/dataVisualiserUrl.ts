import { DEFAULT_FILTERS } from '../hooks/useStatMatrix'
import type { ProfileRateMode } from './profileMetrics'

export type VisualiserTab = 'players' | 'teams'
export type VisualiserChartType = 'scatter' | 'bar' | 'radar'
export type VisualiserPlayerPosition = 'ALL' | 'FWD' | 'MID' | 'DEF' | 'GK'
export type VisualiserBarWindow = 'top' | 'bottom' | 'all'
export const MIN_BAR_COUNT = 5
export const MAX_BAR_COUNT = 20

export interface DataVisualiserUrlState {
  tab: VisualiserTab
  chart: VisualiserChartType
  competition: string
  season: string
  position: VisualiserPlayerPosition
  playerTeams: string[]
  minMinutes: number
  mode: ProfileRateMode
  xMetric?: string
  yMetric?: string
  metric?: string
  radarMetrics: string[]
  compareIds: number[]
  pinnedIds: number[]
  barWindow: VisualiserBarWindow
  barCount: number
  labels: boolean
}

export const DEFAULT_BAR_COUNT = 12

function parseCsv(value: string | null): string[] {
  return value?.split(',').map(part => part.trim()).filter(Boolean) ?? []
}

function parsePipe(value: string | null): string[] {
  return value?.split('|').map(part => part.trim()).filter(Boolean) ?? []
}

function parseIds(value: string | null): number[] {
  return parseCsv(value)
    .map(part => Number(part))
    .filter(id => Number.isFinite(id) && id > 0)
}

function parsePosition(value: string | null): VisualiserPlayerPosition {
  const upper = value?.trim().toUpperCase()
  if (upper === 'FWD' || upper === 'MID' || upper === 'DEF' || upper === 'GK') return upper
  return 'ALL'
}

function parseChart(value: string | null): VisualiserChartType {
  if (value === 'bar' || value === 'radar') return value
  return 'scatter'
}

function parseTab(value: string | null): VisualiserTab {
  return value === 'teams' ? 'teams' : 'players'
}

function parseBarWindow(value: string | null): VisualiserBarWindow {
  if (value === 'bottom' || value === 'all') return value
  return 'top'
}

export function parseDataVisualiserParams(search: URLSearchParams): DataVisualiserUrlState {
  const minRaw = Number(search.get('min_minutes') ?? DEFAULT_FILTERS.min_minutes)
  const barCountRaw = Number(search.get('bar_count') ?? DEFAULT_BAR_COUNT)
  const mode = search.get('mode') === 'full' ? 'full' : 'per90'

  return {
    tab: parseTab(search.get('tab')),
    chart: parseChart(search.get('chart')),
    competition: search.get('competition')?.trim() || DEFAULT_FILTERS.competition,
    season: search.get('season')?.trim() || DEFAULT_FILTERS.season,
    position: parsePosition(search.get('position')),
    playerTeams: parsePipe(search.get('teams')),
    minMinutes: Number.isFinite(minRaw) ? minRaw : DEFAULT_FILTERS.min_minutes,
    mode,
    xMetric: search.get('x')?.trim() || undefined,
    yMetric: search.get('y')?.trim() || undefined,
    metric: search.get('metric')?.trim() || undefined,
    radarMetrics: parseCsv(search.get('radar')),
    compareIds: parseIds(search.get('compare')),
    pinnedIds: parseIds(search.get('pins')),
    barWindow: parseBarWindow(search.get('bar_window')),
    barCount:
      Number.isFinite(barCountRaw) && barCountRaw > 0
        ? Math.min(Math.max(Math.round(barCountRaw), MIN_BAR_COUNT), MAX_BAR_COUNT)
        : DEFAULT_BAR_COUNT,
    labels: search.get('labels') === '1',
  }
}

export function writeDataVisualiserParams(state: DataVisualiserUrlState): URLSearchParams {
  const p = new URLSearchParams()
  p.set('tab', state.tab)
  p.set('chart', state.chart)
  p.set('competition', state.competition)
  p.set('season', state.season)
  p.set('mode', state.mode)

  if (state.tab === 'players') {
    if (state.position !== 'ALL') p.set('position', state.position)
    if (state.playerTeams.length) p.set('teams', state.playerTeams.join('|'))
    if (state.minMinutes !== DEFAULT_FILTERS.min_minutes) {
      p.set('min_minutes', String(state.minMinutes))
    }
  }

  if (state.xMetric) p.set('x', state.xMetric)
  if (state.yMetric) p.set('y', state.yMetric)
  if (state.metric) p.set('metric', state.metric)
  if (state.radarMetrics.length) p.set('radar', state.radarMetrics.join(','))
  if (state.compareIds.length) p.set('compare', state.compareIds.join(','))
  if (state.pinnedIds.length) p.set('pins', state.pinnedIds.join(','))
  if (state.barWindow !== 'top') p.set('bar_window', state.barWindow)
  if (state.barCount !== DEFAULT_BAR_COUNT) p.set('bar_count', String(state.barCount))
  if (state.labels) p.set('labels', '1')

  return p
}
