import type {
  DefensiveActionFamily,
  DefensiveTerritoryEvidence,
  ShotPressureCohort,
  ShotPressurePenaltyMode,
  TeamDefensiveTerritoryPayload,
  TeamPassStateEvidence,
  TeamPassStatePayload,
  TeamShotPressurePayload,
} from '../../types/eventMaps'
import { BASE, FLOW_GRID_ROWS, invertRow, readJson, requestParams, toDisplay } from './api'
import {
  appendStateLens,
  mapStateLens,
  mapStateLensEvidence,
  type ApiStateLens,
  type ApiStateLensEvidence,
  type StateLensRequest,
} from './stateLensApi'

type ApiPassStateCategory = {
  category: string
  attempts: number
  completions: number
  incompletions: number
  attempt_share: number | null
  completion_rate: number | null
}

type ApiPassStateEvidence = {
  exposure_seconds: number
  exposure_minutes: number
  summary: {
    attempts: number
    completions: number
    incompletions: number
    attempts_per_state_minute: number | null
    completions_per_state_minute: number | null
    completion_rate: number | null
    progressive_attempt_rate: number | null
    mean_length_metres: number | null
    mean_forward_metres: number | null
    mean_origin_height: number | null
    mean_destination_height: number | null
  }
  directions: ApiPassStateCategory[]
  length_bands: ApiPassStateCategory[]
  flow: Array<{
    column: number
    row: number
    attempts: number
    completions: number
    incompletions: number
    attempts_per_state_minute: number | null
    completion_rate: number | null
    attempt_share: number | null
    mean_origin_x: number
    mean_origin_y: number
    mean_destination_x: number
    mean_destination_y: number
    mean_length_metres: number
  }>
  evidence: {
    source_pass_events: number
    excluded_missing_coordinates: number
    truncated: boolean
    sparse: boolean
    empty: boolean
  }
}

type ApiTeamPassState = {
  canonical_team_id: number
  canonical_team_name: string
  selected: ApiPassStateEvidence
  comparison: null | {
    baseline: ApiPassStateEvidence
    delta: Record<string, number | null>
  }
}

type ApiDefensiveHeight = {
  sample_size: number
  median: number | null
  mean: number | null
  spread: {
    p10: number | null
    p90: number | null
    p10_p90: number | null
    standard_deviation: number | null
  }
}

type ApiDefensiveGridValue = {
  count: number
  share: number
  per_state_minute: number | null
}

type ApiDefensiveTerritory = {
  contract_version: string
  disclaimer: string
  counts: {
    included: number
    with_location: number
    without_location: number
    non_clearance: number
    clearance: number
    recovery: number
  }
  family_composition: Array<{
    family: DefensiveActionFamily
    count: number
    with_location: number
    without_location: number
    share: number
  }>
  family_evidence: Record<DefensiveActionFamily, {
    height: ApiDefensiveHeight
    rate_per_state_minute: number | null
  }>
  heights: {
    recovery: ApiDefensiveHeight
    non_clearance_action: ApiDefensiveHeight
    clearance: ApiDefensiveHeight
    all: ApiDefensiveHeight
  }
  distribution: Array<{ band: string; count: number; share: number }>
  rates_per_state_minute: {
    all: number | null
    non_clearance: number | null
    clearance: number | null
    recovery: number | null
  }
  grid: {
    columns: number
    rows: number
    cells: Array<{
      column: number
      row: number
      all: ApiDefensiveGridValue
      non_clearance: ApiDefensiveGridValue
      clearance: ApiDefensiveGridValue
      families: Record<DefensiveActionFamily, ApiDefensiveGridValue>
    }>
  }
  evidence: {
    located_sample_size: number
    sparse: boolean
    sparse_threshold: number
    exclusions: Record<string, number>
  }
}

type ApiTeamDefensiveTerritory = {
  canonical_team_id: number
  canonical_team_name: string
  competition_code: string
  season_label: string
  state_lens: ApiStateLens
  selected: ApiDefensiveTerritory
  baseline: ApiDefensiveTerritory | null
}

type ApiShotPressureMetric = { count: number; per_minute: number | null; per_90: number | null }

type ApiShotPressureCohort = {
  evidence: ApiStateLensEvidence & {
    zero_shot_episodes_for: number
    zero_shot_episodes_against: number
  }
  frequency: {
    for: Record<string, ApiShotPressureMetric>
    against: Record<string, ApiShotPressureMetric>
    openness: { shot_count: number; shots_per_minute: number | null; shots_per_90: number | null }
  }
  outcomes: {
    for: Record<string, ApiShotPressureMetric>
    against: Record<string, ApiShotPressureMetric>
    observed_conversion_for: number | null
    observed_conversion_against: number | null
  }
  first_shot: Record<'for' | 'against', {
    episode_count: number
    episodes_with_shot: number
    zero_shot_episodes: number
    mean_seconds_from_state_entry: number | null
    median_seconds_from_state_entry: number | null
  }>
  location: Record<'for' | 'against', {
    columns: number
    rows: number
    located_shots: number
    unlocated_shots: number
    cells: Array<{
      column: number
      row: number
      shot_count: number
      shots_per_90: number | null
      location_share: number | null
      observed_conversion: number | null
    }>
  }>
}

type ApiShotLocationDelta = {
  column: number
  row: number
  shots_per_90_delta: number | null
  location_share_delta: number | null
  observed_conversion_delta: number | null
}

type ApiTeamShotPressure = {
  formula_version: string
  canonical_team_id: number
  canonical_team_name: string
  competition_code: string
  season_label: string
  penalty_mode: ShotPressurePenaltyMode
  penalty_note: string
  fast_break_note: string
  measurement_note: string
  state_lens: ApiStateLens
  selected: ApiShotPressureCohort
  comparison: {
    enabled: boolean
    baseline: ApiShotPressureCohort | null
    selected_minus_baseline: null | {
      location: Record<'for' | 'against', ApiShotLocationDelta[]>
    }
  }
}

function mapPassStateCategory(row: ApiPassStateCategory) {
  return {
    category: row.category,
    attempts: row.attempts,
    completions: row.completions,
    incompletions: row.incompletions,
    attemptShare: row.attempt_share,
    completionRate: row.completion_rate,
  }
}

function mapPassStateEvidence(raw: ApiPassStateEvidence): TeamPassStateEvidence {
  return {
    exposureSeconds: raw.exposure_seconds,
    exposureMinutes: raw.exposure_minutes,
    summary: {
      attempts: raw.summary.attempts,
      completions: raw.summary.completions,
      incompletions: raw.summary.incompletions,
      attemptsPerStateMinute: raw.summary.attempts_per_state_minute,
      completionsPerStateMinute: raw.summary.completions_per_state_minute,
      completionRate: raw.summary.completion_rate,
      progressiveAttemptRate: raw.summary.progressive_attempt_rate,
      meanLengthMetres: raw.summary.mean_length_metres,
      meanForwardMetres: raw.summary.mean_forward_metres,
      meanOriginHeight: raw.summary.mean_origin_height,
      meanDestinationHeight: raw.summary.mean_destination_height,
    },
    directions: raw.directions.map(mapPassStateCategory),
    lengthBands: raw.length_bands.map(mapPassStateCategory),
    flows: raw.flow.map(row => ({
      id: `state-flow-${row.column}-${row.row}`,
      bin: { column: row.column, row: invertRow(row.row, FLOW_GRID_ROWS) },
      origin: toDisplay({ x: row.mean_origin_x, y: row.mean_origin_y }),
      destination: toDisplay({ x: row.mean_destination_x, y: row.mean_destination_y }),
      attemptedCount: row.attempts,
      completedCount: row.completions,
      incompleteCount: row.incompletions,
      attemptsPerStateMinute: row.attempts_per_state_minute,
      completionRate: row.completion_rate,
      share: row.attempt_share ?? 0,
      meanLength: row.mean_length_metres,
    })),
    evidence: {
      sourcePassEvents: raw.evidence.source_pass_events,
      excludedMissingCoordinates: raw.evidence.excluded_missing_coordinates,
      truncated: raw.evidence.truncated,
      sparse: raw.evidence.sparse,
      empty: raw.evidence.empty,
    },
  }
}

function mapDefensiveHeight(value: ApiDefensiveHeight) {
  return {
    sampleSize: value.sample_size,
    median: value.median,
    mean: value.mean,
    spread: {
      p10: value.spread.p10,
      p90: value.spread.p90,
      p10P90: value.spread.p10_p90,
      standardDeviation: value.spread.standard_deviation,
    },
  }
}

function mapDefensiveTerritory(value: ApiDefensiveTerritory): DefensiveTerritoryEvidence {
  const mapGrid = (select: (cell: ApiDefensiveTerritory['grid']['cells'][number]) => ApiDefensiveGridValue) =>
    value.grid.cells.map(cell => {
      const selected = select(cell)
      return {
        column: cell.column,
        row: invertRow(cell.row, value.grid.rows),
        rawCount: selected.count,
        per90Count: selected.per_state_minute ?? 0,
        share: selected.share,
      }
    })
  const mapFamilyEvidence = (family: DefensiveActionFamily) => ({
    height: mapDefensiveHeight(value.family_evidence[family].height),
    ratePerStateMinute: value.family_evidence[family].rate_per_state_minute,
  })

  return {
    contractVersion: value.contract_version,
    disclaimer: value.disclaimer,
    counts: {
      included: value.counts.included,
      withLocation: value.counts.with_location,
      withoutLocation: value.counts.without_location,
      nonClearance: value.counts.non_clearance,
      clearance: value.counts.clearance,
      recovery: value.counts.recovery,
    },
    familyComposition: value.family_composition.map(row => ({
      family: row.family,
      count: row.count,
      withLocation: row.with_location,
      withoutLocation: row.without_location,
      share: row.share,
    })),
    familyEvidence: {
      recovery: mapFamilyEvidence('recovery'),
      tackle: mapFamilyEvidence('tackle'),
      interception: mapFamilyEvidence('interception'),
      blocked_pass: mapFamilyEvidence('blocked_pass'),
      defensive_aerial: mapFamilyEvidence('defensive_aerial'),
      defensive_challenge: mapFamilyEvidence('defensive_challenge'),
      clearance: mapFamilyEvidence('clearance'),
    },
    heights: {
      recovery: mapDefensiveHeight(value.heights.recovery),
      nonClearanceAction: mapDefensiveHeight(value.heights.non_clearance_action),
      clearance: mapDefensiveHeight(value.heights.clearance),
      all: mapDefensiveHeight(value.heights.all),
    },
    distribution: value.distribution,
    ratesPerStateMinute: {
      all: value.rates_per_state_minute.all,
      nonClearance: value.rates_per_state_minute.non_clearance,
      clearance: value.rates_per_state_minute.clearance,
      recovery: value.rates_per_state_minute.recovery,
    },
    grids: {
      all: mapGrid(cell => cell.all),
      nonClearance: mapGrid(cell => cell.non_clearance),
      clearance: mapGrid(cell => cell.clearance),
    },
    gridsByFamily: {
      recovery: mapGrid(cell => cell.families.recovery),
      tackle: mapGrid(cell => cell.families.tackle),
      interception: mapGrid(cell => cell.families.interception),
      blocked_pass: mapGrid(cell => cell.families.blocked_pass),
      defensive_aerial: mapGrid(cell => cell.families.defensive_aerial),
      defensive_challenge: mapGrid(cell => cell.families.defensive_challenge),
      clearance: mapGrid(cell => cell.families.clearance),
    },
    evidence: {
      locatedSampleSize: value.evidence.located_sample_size,
      sparse: value.evidence.sparse,
      sparseThreshold: value.evidence.sparse_threshold,
      exclusions: value.evidence.exclusions,
    },
  }
}

function mapShotPressureMetric(value: ApiShotPressureMetric) {
  return { count: value.count, perMinute: value.per_minute, per90: value.per_90 }
}

function mapShotPressureCohort(value: ApiShotPressureCohort): ShotPressureCohort {
  const mapMetrics = (metrics: Record<string, ApiShotPressureMetric>) =>
    Object.fromEntries(Object.entries(metrics).map(([key, metric]) => [key, mapShotPressureMetric(metric)]))
  const mapFirst = (perspective: 'for' | 'against') => ({
    episodeCount: value.first_shot[perspective].episode_count,
    episodesWithShot: value.first_shot[perspective].episodes_with_shot,
    zeroShotEpisodes: value.first_shot[perspective].zero_shot_episodes,
    meanSecondsFromStateEntry: value.first_shot[perspective].mean_seconds_from_state_entry,
    medianSecondsFromStateEntry: value.first_shot[perspective].median_seconds_from_state_entry,
  })
  const mapLocation = (perspective: 'for' | 'against') => ({
    columns: value.location[perspective].columns,
    rows: value.location[perspective].rows,
    locatedShots: value.location[perspective].located_shots,
    unlocatedShots: value.location[perspective].unlocated_shots,
    cells: value.location[perspective].cells.map(cell => ({
      column: cell.column,
      row: cell.row,
      shotCount: cell.shot_count,
      shotsPer90: cell.shots_per_90,
      locationShare: cell.location_share,
      observedConversion: cell.observed_conversion,
    })),
  })
  return {
    evidence: {
      ...mapStateLensEvidence(value.evidence),
      zeroShotEpisodesFor: value.evidence.zero_shot_episodes_for,
      zeroShotEpisodesAgainst: value.evidence.zero_shot_episodes_against,
    },
    frequency: {
      for: mapMetrics(value.frequency.for),
      against: mapMetrics(value.frequency.against),
      openness: {
        shotCount: value.frequency.openness.shot_count,
        shotsPerMinute: value.frequency.openness.shots_per_minute,
        shotsPer90: value.frequency.openness.shots_per_90,
      },
    },
    outcomes: {
      for: mapMetrics(value.outcomes.for),
      against: mapMetrics(value.outcomes.against),
      observedConversionFor: value.outcomes.observed_conversion_for,
      observedConversionAgainst: value.outcomes.observed_conversion_against,
    },
    firstShot: { for: mapFirst('for'), against: mapFirst('against') },
    location: { for: mapLocation('for'), against: mapLocation('against') },
  }
}

function mapShotLocationDelta(cell: ApiShotLocationDelta) {
  return {
    column: cell.column,
    row: cell.row,
    shotsPer90Delta: cell.shots_per_90_delta,
    locationShareDelta: cell.location_share_delta,
    observedConversionDelta: cell.observed_conversion_delta,
  }
}

export async function fetchTeamPassState(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
): Promise<TeamPassStatePayload> {
  const params = requestParams(competition, season, null, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiTeamPassState>(
    `${BASE}/team-seasons/event-profile/${teamId}/pass-state?${params}`,
  )
  return {
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    selected: mapPassStateEvidence(raw.selected),
    baseline: raw.comparison ? mapPassStateEvidence(raw.comparison.baseline) : null,
    delta: raw.comparison?.delta ?? null,
  }
}

export async function fetchTeamDefensiveTerritory(
  teamId: number,
  competition: string,
  season: string,
  matchRef?: string | null,
  stateLens?: StateLensRequest,
): Promise<TeamDefensiveTerritoryPayload> {
  const params = requestParams(competition, season, null, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiTeamDefensiveTerritory>(
    `${BASE}/team-seasons/event-profile/${teamId}/defensive-territory?${params}`,
  )
  return {
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    competition: raw.competition_code,
    season: raw.season_label,
    stateLens: mapStateLens(raw.state_lens),
    selected: mapDefensiveTerritory(raw.selected),
    baseline: raw.baseline ? mapDefensiveTerritory(raw.baseline) : null,
  }
}

export async function fetchTeamShotPressure(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
  penaltyMode: ShotPressurePenaltyMode,
): Promise<TeamShotPressurePayload> {
  const params = requestParams(competition, season, null, matchRef)
  appendStateLens(params, stateLens)
  params.set('penalty_mode', penaltyMode)
  const raw = await readJson<ApiTeamShotPressure>(
    `${BASE}/team-seasons/shot-pressure/${teamId}?${params}`,
  )
  const delta = raw.comparison.selected_minus_baseline?.location
  return {
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    competition: raw.competition_code,
    season: raw.season_label,
    stateLens: mapStateLens(raw.state_lens),
    formulaVersion: raw.formula_version,
    penaltyMode: raw.penalty_mode,
    penaltyNote: raw.penalty_note,
    fastBreakNote: raw.fast_break_note,
    measurementNote: raw.measurement_note,
    selected: mapShotPressureCohort(raw.selected),
    comparison: {
      enabled: raw.comparison.enabled,
      baseline: raw.comparison.baseline ? mapShotPressureCohort(raw.comparison.baseline) : null,
      locationDelta: delta ? {
        for: delta.for.map(mapShotLocationDelta),
        against: delta.against.map(mapShotLocationDelta),
      } : null,
    },
  }
}
