import type { MatrixFilters } from '../types/api'
import { DEFAULT_FILTERS } from '../hooks/useStatMatrix'
import type { LabPosition } from './regressionLabConfig'
import { isLabPosition } from './regressionLabConfig'

export interface RegressionLabUrlState {
  competition: string
  season: string
  position_group?: LabPosition
  teams?: string[]
  min_minutes: number
  target?: string
  predictors?: string[]
  /** When true, auto-run once after data load (shared links). */
  autoRun?: boolean
}

export function buildRegressionLabHandoff(filters: MatrixFilters): string {
  const p = new URLSearchParams()
  p.set('competition', filters.competition)
  p.set('season', filters.season)
  if (filters.position_group && isLabPosition(filters.position_group)) {
    p.set('position', filters.position_group)
  }
  p.set('min_minutes', String(filters.min_minutes ?? DEFAULT_FILTERS.min_minutes))
  if (filters.teams?.length) p.set('teams', filters.teams.join('|'))
  return `/regression-lab?${p.toString()}`
}

export function parseRegressionLabParams(search: URLSearchParams): RegressionLabUrlState {
  const competition = search.get('competition')?.trim() || DEFAULT_FILTERS.competition
  const season = search.get('season')?.trim() || DEFAULT_FILTERS.season
  const posRaw = search.get('position')?.trim().toUpperCase()
  const position_group = isLabPosition(posRaw) ? posRaw : undefined
  const minRaw = search.get('min_minutes')
  const min_minutes = minRaw != null && minRaw !== '' ? Number(minRaw) : DEFAULT_FILTERS.min_minutes
  const teamsRaw = search.get('teams')
  const teams =
    teamsRaw && teamsRaw.length
      ? teamsRaw.split('|').flatMap(s => {
          const team = s.trim()
          return team ? [team] : []
        })
      : undefined
  const target = search.get('target')?.trim() || undefined
  const predRaw = search.get('predictors')
  const predictors =
    predRaw && predRaw.length
      ? predRaw.split(',').flatMap(s => {
          const predictor = s.trim()
          return predictor ? [predictor] : []
        })
      : undefined
  const autoRun = search.get('run') === '1'

  return {
    competition,
    season,
    position_group,
    teams,
    min_minutes: Number.isFinite(min_minutes) ? min_minutes : DEFAULT_FILTERS.min_minutes,
    target,
    predictors,
    autoRun,
  }
}

export function writeRegressionLabParams(
  state: RegressionLabUrlState,
  opts?: { includeRunFlag?: boolean },
): URLSearchParams {
  const p = new URLSearchParams()
  p.set('competition', state.competition)
  p.set('season', state.season)
  if (state.position_group) p.set('position', state.position_group)
  p.set('min_minutes', String(state.min_minutes))
  if (state.teams?.length) p.set('teams', state.teams.join('|'))
  if (state.target) p.set('target', state.target)
  if (state.predictors?.length) p.set('predictors', state.predictors.join(','))
  if (opts?.includeRunFlag) p.set('run', '1')
  return p
}
