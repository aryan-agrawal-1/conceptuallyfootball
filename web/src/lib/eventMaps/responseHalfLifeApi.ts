import type { EventMatchLookup, StateLensMetadata } from '../../types/eventMaps'
import type {
  ResponseHalfLifeAggregate,
  ResponseHalfLifeCohort,
  ResponseHalfLifeComponent,
  ResponseHalfLifeDefinitions,
  ResponseHalfLifeDestination,
  ResponseHalfLifeEpisode,
  ResponseHalfLifePayload,
  ResponseHalfLifeSignal,
  ResponseHalfLifeSnapshot,
  ResponseHalfLifeWindow,
} from '../../types/responseHalfLife'
import { appendStateLens, mapStateLens, type ApiStateLens, type StateLensRequest } from './stateLensApi'
import { BASE, readJson } from './api'

type ApiComponent = {
  observed: number | null
  expected: number | null
  absolute_deviation: number | null
  normalised_deviation: number | null
  scale: number
}

type ApiSignal = {
  signal: number | null
  supported_components: number
  components: Record<string, ApiComponent>
  formula: string
}

type ApiSnapshot = {
  exposure_seconds: number
  exposure_minutes: number
  attacking: Record<string, number | null>
  structural: Record<string, number | null>
  counts: Record<string, number | Record<string, number>>
}

type ApiWindow = {
  index: number
  offset_seconds: number
  start_second: number
  end_second: number
  duration_seconds: number
  phase: string
  is_added_time: boolean
  complete: boolean
  censored: boolean
  censor_reason: string | null
  snapshot: ApiSnapshot
  attacking: ApiSignal | null
  structural: ApiSignal | null
}

type ApiDestination = {
  available: boolean
  reliability: ResponseHalfLifeDestination['reliability']
  match_basis: string | null
  state: string | null
  phase: string | null
  goal_difference: number | null
  exposure_seconds: number
  exposure_minutes: number
  match_count: number
  event_count: number
  pass_count: number
  attacking: Record<string, number | null>
  structural: Record<string, number | null>
  counts: Record<string, number>
  unavailable_reason: string | null
}

type ApiAggregate = {
  initial_deviation: number | null
  half_threshold: number | null
  half_life_seconds: number | null
  recovered: boolean
  supported_window_count: number
  status: ResponseHalfLifeAggregate['status']
}

type ApiEpisode = {
  match_ref: number | null
  provider_match_id: number
  event_index: number
  concession_second: number
  period: number
  phase: string | null
  score: {
    before: {
      focal_goal_difference: number | null
      focal_score: number | null
      opponent_score: number | null
    }
    after: {
      focal_goal_difference: number | null
      focal_score: number | null
      opponent_score: number | null
    }
  }
  state: {
    before: string | null
    after: string | null
    draw_provenance: string | null
  }
  destination: ApiDestination
  first_five_minute_response: {
    available: boolean
    censor_reason: string | null
    snapshot: ApiSnapshot | null
    attacking: ApiSignal | null
    structural: ApiSignal | null
  }
  qualifies: boolean
  censored: boolean
  censor_reason: string | null
  attacking: ApiAggregate
  structural: ApiAggregate
  windows: ApiWindow[]
}

type ApiCohort = {
  available: boolean
  reliability: ResponseHalfLifeCohort['reliability']
  reliability_note: string | null
  qualifying_concessions: number
  qualifying_windows: number
  qualifying_matches: number
  destination_available_concessions: number
  censored_episodes: number
  uncertain_concession_events: number
  censor_reasons: Record<string, number>
  episode_count: number
  trace_limit: number
  trace_truncated: boolean
  attacking: {
    half_life_seconds: {
      sample_size: number
      mean_seconds: number | null
      median_seconds: number | null
      values_seconds: number[]
    }
    recovered_concessions: number
    formula: string
  }
  structural: {
    half_life_seconds: {
      sample_size: number
      mean_seconds: number | null
      median_seconds: number | null
      values_seconds: number[]
    }
    recovered_concessions: number
    formula: string
  }
  episodes: ApiEpisode[]
}

type ApiDefinitions = {
  formula_version: string
  window_seconds: number
  step_seconds: number
  overlap_seconds: number
  horizon_seconds: number
  interval_boundary: string
  period_boundary: string
  added_time: string
  extra_time: string
  subsequent_goal: string
  rapid_subsequent_goal_seconds: number
  red_card: string
  participation_uncertainty: string
  destination: {
    stable_age_seconds: number
    minimum_exposure_seconds: number
    minimum_events: number
    minimum_passes: number
    priority: string
  }
  attacking_components: string[]
  structural_components: string[]
  attacking_scales: Record<string, number>
  structural_scales: Record<string, number>
  half_life: string
  censor_reasons: string[]
}

type ApiPayload = {
  contract_version: string
  formula_version: string
  canonical_team_id: number
  canonical_team_name: string
  competition_season: number
  competition_code: string
  season_label: string
  selected_match_ref: number | null
  matches: Array<{
    ref: number
    kickoff_at: string
    home_team_id: number | null
    home_team_name: string | null
    away_team_id: number | null
    away_team_name: string | null
    subject_team_id: number | null
  }>
  definitions: ApiDefinitions
  state_lens: ApiStateLens
  selected: ApiCohort
  baseline: ApiCohort | null
  comparison: {
    enabled: boolean
    baseline: ApiCohort | null
    note: string
  }
  notes: string[]
}

function mapComponent(value: ApiComponent): ResponseHalfLifeComponent {
  return {
    observed: value.observed,
    expected: value.expected,
    absoluteDeviation: value.absolute_deviation,
    normalisedDeviation: value.normalised_deviation,
    scale: value.scale,
  }
}

function mapSignal(value: ApiSignal | null): ResponseHalfLifeSignal | null {
  if (!value) return null
  return {
    signal: value.signal,
    supportedComponents: value.supported_components,
    components: Object.fromEntries(
      Object.entries(value.components).map(([key, component]) => [key, mapComponent(component)]),
    ),
    formula: value.formula,
  }
}

function mapSnapshot(value: ApiSnapshot): ResponseHalfLifeSnapshot {
  return {
    exposureSeconds: value.exposure_seconds,
    exposureMinutes: value.exposure_minutes,
    attacking: value.attacking,
    structural: value.structural,
    counts: value.counts,
  }
}

function mapWindow(value: ApiWindow): ResponseHalfLifeWindow {
  return {
    index: value.index,
    offsetSeconds: value.offset_seconds,
    startSecond: value.start_second,
    endSecond: value.end_second,
    durationSeconds: value.duration_seconds,
    phase: value.phase,
    isAddedTime: value.is_added_time,
    complete: value.complete,
    censored: value.censored,
    censorReason: value.censor_reason,
    snapshot: mapSnapshot(value.snapshot),
    attacking: mapSignal(value.attacking),
    structural: mapSignal(value.structural),
  }
}

function mapDestination(value: ApiDestination): ResponseHalfLifeDestination {
  return {
    available: value.available,
    reliability: value.reliability,
    matchBasis: value.match_basis,
    state: value.state,
    phase: value.phase,
    goalDifference: value.goal_difference,
    exposureSeconds: value.exposure_seconds,
    exposureMinutes: value.exposure_minutes,
    matchCount: value.match_count,
    eventCount: value.event_count,
    passCount: value.pass_count,
    attacking: value.attacking,
    structural: value.structural,
    counts: value.counts,
    unavailableReason: value.unavailable_reason,
  }
}

function mapAggregate(value: ApiAggregate): ResponseHalfLifeAggregate {
  return {
    initialDeviation: value.initial_deviation,
    halfThreshold: value.half_threshold,
    halfLifeSeconds: value.half_life_seconds,
    recovered: value.recovered,
    supportedWindowCount: value.supported_window_count,
    status: value.status,
  }
}

function mapEpisode(value: ApiEpisode): ResponseHalfLifeEpisode {
  return {
    matchRef: value.match_ref,
    providerMatchId: value.provider_match_id,
    eventIndex: value.event_index,
    concessionSecond: value.concession_second,
    period: value.period,
    phase: value.phase,
    score: {
      before: {
        focalGoalDifference: value.score.before.focal_goal_difference,
        focalScore: value.score.before.focal_score,
        opponentScore: value.score.before.opponent_score,
      },
      after: {
        focalGoalDifference: value.score.after.focal_goal_difference,
        focalScore: value.score.after.focal_score,
        opponentScore: value.score.after.opponent_score,
      },
    },
    state: {
      before: value.state.before,
      after: value.state.after,
      drawProvenance: value.state.draw_provenance,
    },
    destination: mapDestination(value.destination),
    firstFiveMinuteResponse: {
      available: value.first_five_minute_response.available,
      censorReason: value.first_five_minute_response.censor_reason,
      snapshot: value.first_five_minute_response.snapshot
        ? mapSnapshot(value.first_five_minute_response.snapshot)
        : null,
      attacking: mapSignal(value.first_five_minute_response.attacking),
      structural: mapSignal(value.first_five_minute_response.structural),
    },
    qualifies: value.qualifies,
    censored: value.censored,
    censorReason: value.censor_reason,
    attacking: mapAggregate(value.attacking),
    structural: mapAggregate(value.structural),
    windows: value.windows.map(mapWindow),
  }
}

function mapCohort(value: ApiCohort): ResponseHalfLifeCohort {
  return {
    available: value.available,
    reliability: value.reliability,
    reliabilityNote: value.reliability_note,
    qualifyingConcessions: value.qualifying_concessions,
    qualifyingWindows: value.qualifying_windows,
    qualifyingMatches: value.qualifying_matches,
    destinationAvailableConcessions: value.destination_available_concessions,
    censoredEpisodes: value.censored_episodes,
    uncertainConcessionEvents: value.uncertain_concession_events,
    censorReasons: value.censor_reasons,
    episodeCount: value.episode_count,
    traceLimit: value.trace_limit,
    traceTruncated: value.trace_truncated,
    attacking: {
      halfLifeSeconds: {
        sampleSize: value.attacking.half_life_seconds.sample_size,
        meanSeconds: value.attacking.half_life_seconds.mean_seconds,
        medianSeconds: value.attacking.half_life_seconds.median_seconds,
        valuesSeconds: value.attacking.half_life_seconds.values_seconds,
      },
      recoveredConcessions: value.attacking.recovered_concessions,
      formula: value.attacking.formula,
    },
    structural: {
      halfLifeSeconds: {
        sampleSize: value.structural.half_life_seconds.sample_size,
        meanSeconds: value.structural.half_life_seconds.mean_seconds,
        medianSeconds: value.structural.half_life_seconds.median_seconds,
        valuesSeconds: value.structural.half_life_seconds.values_seconds,
      },
      recoveredConcessions: value.structural.recovered_concessions,
      formula: value.structural.formula,
    },
    episodes: value.episodes.map(mapEpisode),
  }
}

function mapDefinitions(value: ApiDefinitions): ResponseHalfLifeDefinitions {
  return {
    formulaVersion: value.formula_version,
    windowSeconds: value.window_seconds,
    stepSeconds: value.step_seconds,
    overlapSeconds: value.overlap_seconds,
    horizonSeconds: value.horizon_seconds,
    intervalBoundary: value.interval_boundary,
    periodBoundary: value.period_boundary,
    addedTime: value.added_time,
    extraTime: value.extra_time,
    subsequentGoal: value.subsequent_goal,
    rapidSubsequentGoalSeconds: value.rapid_subsequent_goal_seconds,
    redCard: value.red_card,
    participationUncertainty: value.participation_uncertainty,
    destination: {
      stableAgeSeconds: value.destination.stable_age_seconds,
      minimumExposureSeconds: value.destination.minimum_exposure_seconds,
      minimumEvents: value.destination.minimum_events,
      minimumPasses: value.destination.minimum_passes,
      priority: value.destination.priority,
    },
    attackingComponents: value.attacking_components,
    structuralComponents: value.structural_components,
    attackingScales: value.attacking_scales,
    structuralScales: value.structural_scales,
    halfLife: value.half_life,
    censorReasons: value.censor_reasons,
  }
}

function mapMatches(value: ApiPayload['matches']): EventMatchLookup {
  const output: EventMatchLookup = {}
  for (const match of value) {
    const home = match.home_team_id === match.subject_team_id
    output[String(match.ref)] = {
      matchId: String(match.ref),
      opponent: home ? (match.away_team_name ?? 'Unknown opponent') : (match.home_team_name ?? 'Unknown opponent'),
      matchDate: match.kickoff_at,
      venue: home ? 'home' : match.away_team_id === match.subject_team_id ? 'away' : 'neutral',
    }
  }
  return output
}

export async function fetchTeamResponseHalfLife(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
): Promise<ResponseHalfLifePayload> {
  const params = new URLSearchParams({ competition, season })
  if (matchRef != null) params.set('match', matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPayload>(
    `${BASE}/team-seasons/response-half-life/${teamId}?${params}`,
  )
  return {
    contractVersion: raw.contract_version,
    formulaVersion: raw.formula_version,
    canonicalTeamId: raw.canonical_team_id,
    canonicalTeamName: raw.canonical_team_name,
    competitionSeason: raw.competition_season,
    competitionCode: raw.competition_code,
    seasonLabel: raw.season_label,
    selectedMatchRef: raw.selected_match_ref,
    matches: mapMatches(raw.matches),
    definitions: mapDefinitions(raw.definitions),
    stateLens: mapStateLens(raw.state_lens) as StateLensMetadata,
    selected: mapCohort(raw.selected),
    baseline: raw.baseline ? mapCohort(raw.baseline) : null,
    comparison: {
      enabled: raw.comparison.enabled,
      baseline: raw.comparison.baseline ? mapCohort(raw.comparison.baseline) : null,
      note: raw.comparison.note,
    },
    notes: raw.notes,
  }
}
