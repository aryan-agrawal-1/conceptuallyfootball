import type {
  EventMatchLookup,
  StateLensScope,
} from '../../types/eventMaps'
import type {
  TeamStyleAxis,
  TeamStyleAxisDefinition,
  TeamStyleCohort,
  TeamStyleDistribution,
  TeamStyleShapePayload,
  TeamStyleSignedShift,
} from '../../types/teamStyleShape'
import { appendStateLens, mapStateLens, type ApiStateLens, type StateLensRequest } from './stateLensApi'
import { BASE, readJson } from './api'

type ApiAxis = {
  key: string
  category: TeamStyleAxis['category']
  label: string
  description: string
  formula: string
  formula_version: string
  value: number | null
  raw_value: number | null
  unit: string
  direction: 'prevalence'
  raw: Record<string, unknown>
  evidence: {
    count: number
    exposure_seconds: number
    minimum: { exposure_seconds: number; events: number }
  }
  reliability: TeamStyleAxis['reliability']
  percentile_eligible: boolean
  percentile: number | null
  ineligibility_reason: string | null
  distribution?: ApiDistribution
}

type ApiCohort = {
  team_id: number
  team_name: string
  scope: {
    state: StateLensScope['state']
    goal_difference: number | null
    phase: StateLensScope['phase']
    draw_provenance: StateLensScope['drawProvenance']
    minimum_state_age_seconds: number | null
    maximum_state_age_seconds: number | null
  }
  formula_version: string
  percentile_version: string
  exposure: {
    seconds: number
    minutes: number
    episode_count: number
    match_count: number
    matches_excluded: number
  }
  axes: Record<string, ApiAxis>
  evidence: TeamStyleCohort['evidence']
  reliability: TeamStyleCohort['reliability']
}

type ApiDistribution = {
  axis: string
  sample_size: number
  percentile_version: string
  higher_means: 'prevalence'
  distribution: {
    sample_size: number
    min: number | null
    p10: number | null
    p25: number | null
    p50: number | null
    p75: number | null
    p90: number | null
    max: number | null
    iqr: number | null
    values: number[]
    raw_values: number[]
  }
  members: Array<{
    team_id: number
    team_name: string | null
    value: number | null
    reliability: TeamStyleDistribution['members'][number]['reliability']
    percentile_eligible: boolean
    target?: boolean
  }>
}

type ApiSignedShift = {
  selected_value: number | null
  baseline_value: number | null
  raw_delta: number | null
  unit: string | null
  normalised_delta: number | null
  normalized_delta?: number | null
  normalisation: string
  normalization?: string
  scale: number | null
  direction: 'prevalence'
  eligible: boolean
  reliability: TeamStyleSignedShift['reliability']
}

type ApiPayload = {
  contract_version: string
  formula_version: string
  percentile_version: string
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
  axis_keys: string[]
  axis_definitions: Array<{
    key: string
    category: TeamStyleAxisDefinition['category']
    label: string
    description: string
    formula: string
    unit: string
    higher_means: string
    evidence_type: string
    minimum_evidence: { exposure_seconds: number; events: number }
    direction: 'prevalence'
    percentile_version: string
  }>
  cohort: {
    type: 'competition_season'
    competition_season_id: number
    competition_code: string
    season_label: string
    team_count: number
    teams: Array<{ team_id: number; team_name: string | null }>
    percentiles_available: boolean
    percentile_note: string
  }
  state_lens: ApiStateLens
  overall: ApiCohort
  selected: ApiCohort
  baseline: ApiCohort | null
  distributions: {
    overall: Record<string, ApiDistribution>
    selected: Record<string, ApiDistribution>
    baseline: Record<string, ApiDistribution> | null
  }
  comparison: {
    enabled: boolean
    baseline: ApiCohort | null
    selected_minus_baseline: Record<string, ApiSignedShift> | null
    normalisation_note: string
  }
  notes: string[]
}

function mapScope(value: ApiCohort['scope']): StateLensScope {
  return {
    state: value.state,
    goalDifference: value.goal_difference,
    phase: value.phase,
    drawProvenance: value.draw_provenance,
    minimumStateAgeSeconds: value.minimum_state_age_seconds,
    maximumStateAgeSeconds: value.maximum_state_age_seconds,
  }
}

function mapAxis(value: ApiAxis): TeamStyleAxis {
  return {
    key: value.key,
    category: value.category,
    label: value.label,
    description: value.description,
    formula: value.formula,
    formulaVersion: value.formula_version,
    value: value.value,
    rawValue: value.raw_value,
    unit: value.unit,
    direction: value.direction,
    raw: value.raw,
    evidence: {
      count: value.evidence.count,
      exposureSeconds: value.evidence.exposure_seconds,
      minimum: {
        exposureSeconds: value.evidence.minimum.exposure_seconds,
        events: value.evidence.minimum.events,
      },
    },
    reliability: value.reliability,
    percentileEligible: value.percentile_eligible,
    percentile: value.percentile,
    ineligibilityReason: value.ineligibility_reason,
    distribution: value.distribution ? mapDistribution(value.distribution) : undefined,
  }
}

function mapCohort(value: ApiCohort): TeamStyleCohort {
  return {
    teamId: value.team_id,
    teamName: value.team_name,
    scope: mapScope(value.scope),
    formulaVersion: value.formula_version,
    percentileVersion: value.percentile_version,
    exposure: {
      seconds: value.exposure.seconds,
      minutes: value.exposure.minutes,
      episodeCount: value.exposure.episode_count,
      matchCount: value.exposure.match_count,
      matchesExcluded: value.exposure.matches_excluded,
    },
    axes: Object.fromEntries(
      Object.entries(value.axes).map(([key, axis]) => [key, mapAxis(axis)]),
    ),
    evidence: value.evidence,
    reliability: value.reliability,
  }
}

function mapDistribution(value: ApiDistribution): TeamStyleDistribution {
  return {
    axis: value.axis,
    sampleSize: value.sample_size,
    percentileVersion: value.percentile_version,
    higherMeans: value.higher_means,
    distribution: {
      sampleSize: value.distribution.sample_size,
      min: value.distribution.min,
      p10: value.distribution.p10,
      p25: value.distribution.p25,
      p50: value.distribution.p50,
      p75: value.distribution.p75,
      p90: value.distribution.p90,
      max: value.distribution.max,
      iqr: value.distribution.iqr,
      values: value.distribution.values,
      rawValues: value.distribution.raw_values,
    },
    members: value.members.map(member => ({
      teamId: member.team_id,
      teamName: member.team_name,
      value: member.value,
      reliability: member.reliability,
      percentileEligible: member.percentile_eligible,
      target: member.target,
    })),
  }
}

function mapSignedShift(value: ApiSignedShift): TeamStyleSignedShift {
  return {
    selectedValue: value.selected_value,
    baselineValue: value.baseline_value,
    rawDelta: value.raw_delta,
    unit: value.unit,
    normalisedDelta: value.normalised_delta ?? value.normalized_delta ?? null,
    normalisation: value.normalisation ?? value.normalization ?? '',
    scale: value.scale,
    direction: value.direction,
    eligible: value.eligible,
    reliability: value.reliability,
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

export async function fetchTeamStyleShape(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
  axisKeys?: string[],
): Promise<TeamStyleShapePayload> {
  const params = new URLSearchParams({ competition, season })
  if (matchRef != null) params.set('match', matchRef)
  appendStateLens(params, stateLens)
  if (axisKeys?.length) params.set('axes', axisKeys.join(','))
  const raw = await readJson<ApiPayload>(
    `${BASE}/team-seasons/style-shape/${teamId}?${params}`,
  )
  const mapDistributionRecord = (record: Record<string, ApiDistribution>) => (
    Object.fromEntries(
      Object.entries(record).map(([key, value]) => [key, mapDistribution(value)]),
    )
  )
  return {
    contractVersion: raw.contract_version,
    formulaVersion: raw.formula_version,
    percentileVersion: raw.percentile_version,
    canonicalTeamId: raw.canonical_team_id,
    canonicalTeamName: raw.canonical_team_name,
    competitionSeason: raw.competition_season,
    competitionCode: raw.competition_code,
    seasonLabel: raw.season_label,
    selectedMatchRef: raw.selected_match_ref,
    matches: mapMatches(raw.matches),
    axisKeys: raw.axis_keys,
    axisDefinitions: raw.axis_definitions.map(value => ({
      key: value.key,
      category: value.category,
      label: value.label,
      description: value.description,
      formula: value.formula,
      unit: value.unit,
      higherMeans: value.higher_means,
      evidenceType: value.evidence_type,
      minimumEvidence: {
        exposureSeconds: value.minimum_evidence.exposure_seconds,
        events: value.minimum_evidence.events,
      },
      direction: value.direction,
      percentileVersion: value.percentile_version,
    })),
    cohort: {
      type: raw.cohort.type,
      competitionSeasonId: raw.cohort.competition_season_id,
      competitionCode: raw.cohort.competition_code,
      seasonLabel: raw.cohort.season_label,
      teamCount: raw.cohort.team_count,
      teams: raw.cohort.teams.map(team => ({ teamId: team.team_id, teamName: team.team_name })),
      percentilesAvailable: raw.cohort.percentiles_available,
      percentileNote: raw.cohort.percentile_note,
    },
    stateLens: mapStateLens(raw.state_lens),
    overall: mapCohort(raw.overall),
    selected: mapCohort(raw.selected),
    baseline: raw.baseline ? mapCohort(raw.baseline) : null,
    distributions: {
      overall: mapDistributionRecord(raw.distributions.overall),
      selected: mapDistributionRecord(raw.distributions.selected),
      baseline: raw.distributions.baseline ? mapDistributionRecord(raw.distributions.baseline) : null,
    },
    comparison: {
      enabled: raw.comparison.enabled,
      baseline: raw.comparison.baseline ? mapCohort(raw.comparison.baseline) : null,
      selectedMinusBaseline: raw.comparison.selected_minus_baseline
        ? Object.fromEntries(
            Object.entries(raw.comparison.selected_minus_baseline).map(([key, value]) => [key, mapSignedShift(value)]),
          )
        : null,
      normalisationNote: raw.comparison.normalisation_note,
    },
    notes: raw.notes,
  }
}
