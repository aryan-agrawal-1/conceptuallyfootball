import type {
  TransitionDirectionStats,
  TransitionLeveragePayload,
  TransitionLeverageScope,
} from '../../types/transitionLeverage'
import { BASE, readJson, requestParams } from './api'
import { appendStateLens, mapStateLens, type ApiStateLens, type StateLensRequest } from './stateLensApi'

type ApiDirection = {
  opportunities: number
  outcome_ladder: Array<{
    key: TransitionLeverageScope['attacking']['outcomeLadder'][number]['key']
    label: string
    count: number
    rate_per_opportunity: number | null
  }>
}

type ApiScope = {
  attacking: ApiDirection
  concession: ApiDirection
  coverage: {
    matches_included: number
    matches_excluded: number
    possession_count: number
    ambiguous_possession_count: number
    sparse: boolean
    sparse_threshold: number
  }
}

type ApiPayload = {
  state_lens: ApiStateLens
  selected: ApiScope
  comparison: {
    baseline: ApiScope | null
    delta: TransitionLeveragePayload['comparison']['delta']
  }
}

function mapDirection(value: ApiDirection): TransitionDirectionStats {
  return {
    opportunities: value.opportunities,
    outcomeLadder: value.outcome_ladder.map(row => ({
      key: row.key,
      label: row.label,
      count: row.count,
      ratePerOpportunity: row.rate_per_opportunity,
    })),
  }
}

function mapScope(value: ApiScope): TransitionLeverageScope {
  return {
    attacking: mapDirection(value.attacking),
    concession: mapDirection(value.concession),
    coverage: {
      matchesIncluded: value.coverage.matches_included,
      matchesExcluded: value.coverage.matches_excluded,
      possessionCount: value.coverage.possession_count,
      ambiguousPossessionCount: value.coverage.ambiguous_possession_count,
      sparse: value.coverage.sparse,
      sparseThreshold: value.coverage.sparse_threshold,
    },
  }
}

export async function fetchTeamTransitionLeverage(
  teamId: number,
  competition: string,
  season: string,
  matchRef?: string | null,
  stateLens?: StateLensRequest,
): Promise<TransitionLeveragePayload> {
  const params = requestParams(competition, season, undefined, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPayload>(
    `${BASE}/team-seasons/transition-leverage/${teamId}?${params}`,
  )
  return {
    stateLens: mapStateLens(raw.state_lens),
    selected: mapScope(raw.selected),
    comparison: {
      baseline: raw.comparison.baseline ? mapScope(raw.comparison.baseline) : null,
      delta: raw.comparison.delta,
    },
  }
}
