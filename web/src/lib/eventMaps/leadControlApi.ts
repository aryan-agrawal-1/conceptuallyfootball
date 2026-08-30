import type { EventMatchLookup, StateLensMetadata } from '../../types/eventMaps'
import type {
  LeadControlAxis,
  LeadControlEpisode,
  LeadControlMetric,
  LeadControlPayload,
  LeadControlSurface,
} from '../../types/leadControl'
import { appendStateLens, mapStateLens, type ApiStateLens, type StateLensRequest } from './stateLensApi'
import { BASE, readJson } from './api'

type ApiMetric = {
  key: string
  label: string
  kind: LeadControlMetric['kind']
  value: number | null
  count: number
  sample_size: number
  denominator?: number
  unit: string
  exposure_seconds: number
  per_state_minute: number | null
  per_90: number | null
  mean?: number | null
  episodes_with_attack?: number
  episodes_without_attack?: number
  baseline_value: number | null
  baseline_count: number | null
  baseline_sample_size: number | null
  baseline_per_state_minute: number | null
  baseline_per_90: number | null
  delta: number | null
  delta_per_state_minute: number | null
  delta_per_90: number | null
  reliability: string
  baseline_reliability: string
  raw: Record<string, unknown>
  baseline_raw: Record<string, unknown> | null
}

type ApiComponents = Record<string, ApiMetric | Record<string, ApiMetric>>

type ApiSurface = {
  exposure_seconds: number
  exposure_minutes: number
  episode_count: number
  match_count: number
  window_count: number
  event_count: number
  gravity: {
    components: ApiComponents
    raw_components: ApiComponents
    axis: ApiAxis
  }
  ownership: {
    components: ApiComponents
    raw_components: ApiComponents
    axis: ApiAxis
  }
  axes: {
    behavioral_retreat: ApiAxis
    process_control: ApiAxis
  }
  reliability: ApiReliability
  raw_counts: Record<string, number>
}

type ApiAxis = {
  value: number | null
  available_components: number
  higher_means: string
  unit: string
}

type ApiReliability = {
  status: string
  label_eligible: boolean
  lead_episode_count: number
  minimum_lead_episodes: number
  exposure_seconds: number
  minimum_exposure_seconds: number
  matched_baseline_available: boolean
  note: string
}

type ApiEpisode = {
  episode_id: string
  match_ref: number | null
  phase: string | null
  lead_band: 'one_goal' | 'multi_goal' | null
  goal_difference: number | null
  start_second: number
  end_second: number
  state_entry_second: number
  duration_seconds: number
  clock_buckets: number[]
  matched_baseline_windows: number
  matched_baseline_exposure_seconds: number
  time_to_first_meaningful_opponent_attack_seconds: number | null
  behavior: Pick<ApiSurface['gravity'], 'components' | 'axis'>
  ownership: Pick<ApiSurface['ownership'], 'components' | 'axis'>
  coverage: {
    exposure_seconds: number
    matched_baseline: boolean
    reliability: ApiReliability
  }
  secondary_outcomes: {
    lead_survived_to_match_end: boolean | null
    final_result: 'win' | 'draw' | 'loss' | null
    note: string
  }
}

type ApiPayload = {
  contract_version: string
  formula_version: string
  team: { id: number; name: string | null }
  competition_season: { id: number; competition: string; season: string }
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
  state_lens: ApiStateLens
  selected: ApiSurface & {
    lead_band_breakdown: { one_goal: ApiSurface; multi_goal: ApiSurface }
    phase_breakdown: Record<string, ApiSurface>
    episodes: ApiEpisode[]
  }
  baseline: ApiSurface | null
  comparison: {
    enabled: boolean
    baseline_type: string
    lead_state: string
    baseline_state: string
    baseline_goal_difference: number
    phase_matching: string
    clock_matching: {
      bucket_seconds: number
      tolerance_seconds: number
      rule: string
    }
    baseline: ApiSurface | null
    matched_windows: number
    delta_note: string
  }
  quadrant: {
    behavioral_retreat: ApiAxis
    process_control: ApiAxis
    placement: {
      label: string | null
      short_label: string
      available: boolean
      note: string
    }
  }
  coverage: {
    lead_episode_count: number
    one_goal_episode_count: number
    multi_goal_episode_count: number
    match_count: number
    exposure_seconds: number
    matched_baseline_window_count: number
    matched_baseline_episode_count: number
    matched_baseline_exposure_seconds: number
    episode_evidence_limit: number
    episode_evidence_truncated: boolean
    reliability: ApiReliability
  }
  thresholds: {
    clock_bucket_seconds: number
    clock_match_tolerance_seconds: number
    minimum_lead_episodes: number
    minimum_lead_exposure_seconds: number
    minimum_component_events: number
    episode_evidence_limit: number
    axis_scales: Record<string, number>
    possession_calculation_version: string
    territory: { final_third_x: number; box_x: number }
  }
  limitations: string[]
  opponent_strength: LeadControlPayload['opponentStrength']
}

function mapAxis(value: ApiAxis): LeadControlAxis {
  return {
    value: value.value,
    availableComponents: value.available_components,
    higherMeans: value.higher_means,
    unit: value.unit,
  }
}

function mapMetric(value: ApiMetric): LeadControlMetric {
  return {
    key: value.key,
    label: value.label,
    kind: value.kind,
    value: value.value,
    count: value.count,
    sampleSize: value.sample_size,
    denominator: value.denominator,
    unit: value.unit,
    exposureSeconds: value.exposure_seconds,
    perStateMinute: value.per_state_minute,
    per90: value.per_90,
    mean: value.mean,
    episodesWithAttack: value.episodes_with_attack,
    episodesWithoutAttack: value.episodes_without_attack,
    baselineValue: value.baseline_value,
    baselineCount: value.baseline_count,
    baselineSampleSize: value.baseline_sample_size,
    baselinePerStateMinute: value.baseline_per_state_minute,
    baselinePer90: value.baseline_per_90,
    delta: value.delta,
    deltaPerStateMinute: value.delta_per_state_minute,
    deltaPer90: value.delta_per_90,
    reliability: value.reliability,
    baselineReliability: value.baseline_reliability,
    raw: value.raw,
    baselineRaw: value.baseline_raw,
  }
}

function mapComponents(value: ApiComponents): Record<string, LeadControlMetric | Record<string, LeadControlMetric>> {
  return Object.fromEntries(
    Object.entries(value).map(([key, component]) => [
      key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()),
      'value' in component
        ? mapMetric(component as ApiMetric)
        : Object.fromEntries(
            Object.entries(component as Record<string, ApiMetric>).map(([nestedKey, nestedValue]) => [nestedKey, mapMetric(nestedValue)]),
          ),
    ]),
  ) as Record<string, LeadControlMetric | Record<string, LeadControlMetric>>
}

function mapReliability(value: ApiReliability) {
  return {
    status: value.status,
    labelEligible: value.label_eligible,
    leadEpisodeCount: value.lead_episode_count,
    minimumLeadEpisodes: value.minimum_lead_episodes,
    exposureSeconds: value.exposure_seconds,
    minimumExposureSeconds: value.minimum_exposure_seconds,
    matchedBaselineAvailable: value.matched_baseline_available,
    note: value.note,
  }
}

function mapSurface(value: ApiSurface): LeadControlSurface {
  return {
    exposureSeconds: value.exposure_seconds,
    exposureMinutes: value.exposure_minutes,
    episodeCount: value.episode_count,
    matchCount: value.match_count,
    windowCount: value.window_count,
    eventCount: value.event_count,
    gravity: {
      components: mapComponents(value.gravity.components) as unknown as LeadControlSurface['gravity']['components'],
      rawComponents: mapComponents(value.gravity.raw_components) as unknown as LeadControlSurface['gravity']['rawComponents'],
      axis: mapAxis(value.gravity.axis),
    },
    ownership: {
      components: mapComponents(value.ownership.components) as unknown as LeadControlSurface['ownership']['components'],
      rawComponents: mapComponents(value.ownership.raw_components) as unknown as LeadControlSurface['ownership']['rawComponents'],
      axis: mapAxis(value.ownership.axis),
    },
    axes: {
      behavioralRetreat: mapAxis(value.axes.behavioral_retreat),
      processControl: mapAxis(value.axes.process_control),
    },
    reliability: mapReliability(value.reliability),
    rawCounts: value.raw_counts,
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

function mapEpisode(value: ApiEpisode): LeadControlEpisode {
  return {
    episodeId: value.episode_id,
    matchRef: value.match_ref,
    phase: value.phase,
    leadBand: value.lead_band,
    goalDifference: value.goal_difference,
    startSecond: value.start_second,
    endSecond: value.end_second,
    stateEntrySecond: value.state_entry_second,
    durationSeconds: value.duration_seconds,
    clockBuckets: value.clock_buckets,
    matchedBaselineWindows: value.matched_baseline_windows,
    matchedBaselineExposureSeconds: value.matched_baseline_exposure_seconds,
    timeToFirstMeaningfulOpponentAttackSeconds: value.time_to_first_meaningful_opponent_attack_seconds,
    behavior: {
      components: mapComponents(value.behavior.components) as unknown as LeadControlSurface['gravity']['components'],
      rawComponents: mapComponents(value.behavior.components) as unknown as LeadControlSurface['gravity']['rawComponents'],
      axis: mapAxis(value.behavior.axis),
    },
    ownership: {
      components: mapComponents(value.ownership.components) as unknown as LeadControlSurface['ownership']['components'],
      rawComponents: mapComponents(value.ownership.components) as unknown as LeadControlSurface['ownership']['rawComponents'],
      axis: mapAxis(value.ownership.axis),
    },
    coverage: {
      exposureSeconds: value.coverage.exposure_seconds,
      matchedBaseline: value.coverage.matched_baseline,
      reliability: mapReliability(value.coverage.reliability),
    },
    secondaryOutcomes: {
      leadSurvivedToMatchEnd: value.secondary_outcomes.lead_survived_to_match_end,
      finalResult: value.secondary_outcomes.final_result,
      note: value.secondary_outcomes.note,
    },
  }
}

export async function fetchTeamLeadControl(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
): Promise<LeadControlPayload> {
  const params = new URLSearchParams({ competition, season })
  if (matchRef != null) params.set('match', matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPayload>(
    `${BASE}/team-seasons/lead-control/${teamId}?${params.toString()}`,
  )
  const selected = mapSurface(raw.selected)
  const leadBandBreakdown = {
    oneGoal: mapSurface(raw.selected.lead_band_breakdown.one_goal),
    multiGoal: mapSurface(raw.selected.lead_band_breakdown.multi_goal),
  }
  const phaseBreakdown = Object.fromEntries(
    Object.entries(raw.selected.phase_breakdown).map(([key, value]) => [key, mapSurface(value)]),
  )
  return {
    contractVersion: raw.contract_version,
    formulaVersion: raw.formula_version,
    team: raw.team,
    competitionSeason: raw.competition_season,
    selectedMatchRef: raw.selected_match_ref,
    matches: mapMatches(raw.matches),
    stateLens: mapStateLens(raw.state_lens) as StateLensMetadata,
    selected: {
      ...selected,
      leadBandBreakdown,
      phaseBreakdown,
      episodes: raw.selected.episodes.map(mapEpisode),
    },
    baseline: raw.baseline ? mapSurface(raw.baseline) : null,
    comparison: {
      enabled: raw.comparison.enabled,
      baselineType: raw.comparison.baseline_type,
      leadState: raw.comparison.lead_state,
      baselineState: raw.comparison.baseline_state,
      baselineGoalDifference: raw.comparison.baseline_goal_difference,
      phaseMatching: raw.comparison.phase_matching,
      clockMatching: {
        bucketSeconds: raw.comparison.clock_matching.bucket_seconds,
        toleranceSeconds: raw.comparison.clock_matching.tolerance_seconds,
        rule: raw.comparison.clock_matching.rule,
      },
      baseline: raw.comparison.baseline ? mapSurface(raw.comparison.baseline) : null,
      matchedWindows: raw.comparison.matched_windows,
      deltaNote: raw.comparison.delta_note,
    },
    quadrant: {
      behavioralRetreat: mapAxis(raw.quadrant.behavioral_retreat),
      processControl: mapAxis(raw.quadrant.process_control),
      placement: {
        label: raw.quadrant.placement.label,
        shortLabel: raw.quadrant.placement.short_label,
        available: raw.quadrant.placement.available,
        note: raw.quadrant.placement.note,
      },
    },
    episodes: raw.selected.episodes.map(mapEpisode),
    coverage: {
      leadEpisodeCount: raw.coverage.lead_episode_count,
      oneGoalEpisodeCount: raw.coverage.one_goal_episode_count,
      multiGoalEpisodeCount: raw.coverage.multi_goal_episode_count,
      matchCount: raw.coverage.match_count,
      exposureSeconds: raw.coverage.exposure_seconds,
      matchedBaselineWindowCount: raw.coverage.matched_baseline_window_count,
      matchedBaselineEpisodeCount: raw.coverage.matched_baseline_episode_count,
      matchedBaselineExposureSeconds: raw.coverage.matched_baseline_exposure_seconds,
      episodeEvidenceLimit: raw.coverage.episode_evidence_limit,
      episodeEvidenceTruncated: raw.coverage.episode_evidence_truncated,
      reliability: mapReliability(raw.coverage.reliability),
    },
    thresholds: {
      clockBucketSeconds: raw.thresholds.clock_bucket_seconds,
      clockMatchToleranceSeconds: raw.thresholds.clock_match_tolerance_seconds,
      minimumLeadEpisodes: raw.thresholds.minimum_lead_episodes,
      minimumLeadExposureSeconds: raw.thresholds.minimum_lead_exposure_seconds,
      minimumComponentEvents: raw.thresholds.minimum_component_events,
      episodeEvidenceLimit: raw.thresholds.episode_evidence_limit,
      axisScales: raw.thresholds.axis_scales,
      possessionCalculationVersion: raw.thresholds.possession_calculation_version,
      territory: {
        finalThirdX: raw.thresholds.territory.final_third_x,
        boxX: raw.thresholds.territory.box_x,
      },
    },
    limitations: raw.limitations,
    opponentStrength: raw.opponent_strength,
  }
}
