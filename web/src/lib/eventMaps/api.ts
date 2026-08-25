import type {
  ActionGridCell,
  EventCarry,
  EventMatchLookup,
  EventPass,
  EventShot,
  GkShotZonesPayload,
  PitchCoordinate,
  PlayerEventProfilePayload,
  PlayerPassFilter,
  PlayerPassOutcome,
  PlayerPassMapPayload,
  PlayerShotZonesPayload,
  ShotBodyPart,
  ShotOutcome,
  ShotSituation,
  ShotZoneVariant,
  TeamEventProfilePayload,
  TeamDefensiveTerritoryPayload,
  DefensiveTerritoryEvidence,
  DefensiveActionFamily,
  DefensiveTerritoryGroup,
  TeamPassFlow,
  StateLensMetadata,
  TeamPassStateEvidence,
  TeamPassStatePayload,
  ShotPressureCohort,
  ShotPressurePenaltyMode,
  TeamShotPressurePayload,
} from '../../types/eventMaps'

const BASE = '/api/v1'

type ApiMatch = {
  ref: number
  kickoff_at: string
  home_team_id: number | null
  home_team_name: string | null
  away_team_id: number | null
  away_team_name: string | null
  subject_team_id: number | null
}

type ApiShot = {
  match_ref: number
  team_id: number | null
  player_id: number | null
  player_name: string | null
  event_index: number
  match_seconds: number | null
  x: number
  y: number
  outcome: string
  body_part: string
  situation: string
  big_chance: boolean
  assisted: boolean
  goal_mouth_y: number | null
  goal_mouth_z: number | null
  blocked_x: number | null
  blocked_y: number | null
}

type ApiPass = {
  match_ref: number
  team_id: number | null
  event_index: number
  match_seconds: number | null
  x: number
  y: number
  end_x: number
  end_y: number
  completed: boolean
  progressive: boolean
  final_third_entry: boolean
  box_entry: boolean
  key_pass: boolean
  cross: boolean
  long_ball: boolean
}

type ApiCarry = {
  match_ref: number
  team_id: number | null
  start_event_index: number
  end_event_index: number
  match_seconds: number | null
  x: number
  y: number
  end_x: number
  end_y: number
  progressive: boolean
  final_third_entry: boolean
  box_entry: boolean
  low_confidence: boolean
}

type ApiShotZoneCell = {
  column: number
  row: number
  shots: number
  goals: number
  conversion?: number | null
  save_rate?: number | null
}

type ApiShotZoneVariant = {
  cells: ApiShotZoneCell[]
  totals: Record<string, number>
}

export type ApiShotZoneVariants = {
  all: ApiShotZoneVariant
  open_play: ApiShotZoneVariant
  penalties_only: ApiShotZoneVariant
}

type ApiPlayerShotZones = {
  canonical_player_id: number
  canonical_team_id: number | null
  canonical_team_name: string | null
  competition_code: string
  season_label: string
  grid: PlayerShotZonesPayload['grid']
  shot_count: number
  variants: ApiShotZoneVariants
  matches: ApiMatch[]
}

type ApiGkShotZones = {
  canonical_player_id: number
  competition_code: string
  season_label: string
  grid: GkShotZonesPayload['grid']
  matches_included: number
  matches_excluded: number
  attribution_note: string
  selected_match_included: boolean
  shots_faced: number
  variants: ApiShotZoneVariants
  matches: ApiMatch[]
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
      location: Record<'for' | 'against', Array<{
        column: number
        row: number
        shots_per_90_delta: number | null
        location_share_delta: number | null
        observed_conversion_delta: number | null
      }>>
    }
  }
}

type ApiGridCell = {
  column: number
  row: number
  raw_count: number
  per90_count: number | null
  share: number
}

type ApiMaterialization = {
  formula_version: string
  materialization_run_id: number
  profile_version: number
  materialized_at: string
}

type ApiAvailability = Record<
  'pass_map' | 'shot_map' | 'action_grid',
  { available: boolean; sparse: boolean }
>

type ApiPlayerProfile = {
  canonical_player_id: number
  canonical_player_name: string
  canonical_team_id: number | null
  canonical_team_name: string | null
  split_type: 'season_total' | 'team'
  competition_code: string
  season_label: string
  coverage: {
    observed_matches: number
    competition_expected_matches: number | null
    expected_matches: number | null
    observed_event_minutes: number
    competition_complete: boolean
  }
  availability: ApiAvailability
  materialization: ApiMaterialization
  summary: Record<string, number>
  average_touch_location: { x: number | null; y: number | null; sample_size: number }
  action_grid: ApiGridCell[]
  touch_grid?: ApiGridCell[]
  shots: ApiShot[]
  matches: ApiMatch[]
}

type ApiPlayerPasses = {
  canonical_player_id: number
  competition_code: string
  season_label: string
  filter: PlayerPassFilter
  outcome: PlayerPassOutcome
  total_matching_count: number
  truncated: boolean
  total_carry_count?: number
  total_all_carry_count?: number
  carries_truncated?: boolean
  passes: ApiPass[]
  carries?: ApiCarry[]
  matches: ApiMatch[]
}

type ApiTeamProfile = {
  canonical_team_id: number
  canonical_team_name: string
  competition_code: string
  season_label: string
  coverage: { observed_matches: number; expected_matches: number; ratio: number | null }
  materialization: ApiMaterialization
  summary: Record<string, number>
  pass_flow: Array<{
    column: number
    row: number
    completed_count: number
    share: number
    mean_origin_x: number
    mean_origin_y: number
    mean_destination_x: number
    mean_destination_y: number
    mean_length_metres: number
  }>
  action_grid: ApiGridCell[]
  opponent_action_grid: ApiGridCell[]
  touch_grid?: ApiGridCell[]
  opponent_touch_grid?: ApiGridCell[]
  shots_for: ApiShot[]
  shots_against: ApiShot[]
  matches: ApiMatch[]
  state_lens: ApiStateLens
}

type ApiStateLensScope = {
  state: StateLensMetadata['selected']['state']
  goal_difference: number | null
  phase: StateLensMetadata['selected']['phase']
  draw_provenance: StateLensMetadata['selected']['drawProvenance']
  minimum_state_age_seconds: number | null
  maximum_state_age_seconds: number | null
}

type ApiStateLensEvidence = {
  exposure_seconds: number
  exposure_minutes: number
  episode_count: number
  match_count: number
  matches_included: number
  matches_excluded: number
  exclusion_reasons: Record<string, number>
  formula_version: string
  empty: boolean
}

type ApiStateLens = {
  contract_version: string
  selected: ApiStateLensScope
  evidence: ApiStateLensEvidence
  eligible_refinements: {
    states: StateLensMetadata['eligibleRefinements']['states']
    goal_differences: number[]
    phases: StateLensMetadata['eligibleRefinements']['phases']
    draw_provenances: StateLensMetadata['eligibleRefinements']['drawProvenances']
    state_age_seconds: { minimum: number | null; maximum: number | null }
  }
  comparison: {
    enabled: boolean
    baseline: ApiStateLensScope | null
    baseline_evidence: ApiStateLensEvidence | null
    comparison: ApiStateLensScope
    comparison_evidence: ApiStateLensEvidence
  }
}

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
      all: { count: number; share: number; per_state_minute: number | null }
      non_clearance: { count: number; share: number; per_state_minute: number | null }
      clearance: { count: number; share: number; per_state_minute: number | null }
      families: Record<DefensiveActionFamily, {
        count: number
        share: number
        per_state_minute: number | null
      }>
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

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${response.status}`)
  }
  return response.json()
}

function requestParams(
  competition: string,
  season: string,
  teamId?: number | null,
  matchRef?: string | null,
) {
  const params = new URLSearchParams({ competition, season })
  if (teamId != null) params.set('team', String(teamId))
  if (matchRef != null) params.set('match', matchRef)
  return params
}

export type StateLensRequest = Record<string, string>

function appendStateLens(params: URLSearchParams, stateLens?: StateLensRequest) {
  if (!stateLens) return
  Object.entries(stateLens).forEach(([key, value]) => {
    if (value !== '') params.set(key, value)
  })
}

function mapStateLensScope(value: ApiStateLensScope): StateLensMetadata['selected'] {
  return {
    state: value.state,
    goalDifference: value.goal_difference,
    phase: value.phase,
    drawProvenance: value.draw_provenance,
    minimumStateAgeSeconds: value.minimum_state_age_seconds,
    maximumStateAgeSeconds: value.maximum_state_age_seconds,
  }
}

function mapStateLensEvidence(value: ApiStateLensEvidence): StateLensMetadata['evidence'] {
  return {
    exposureSeconds: value.exposure_seconds,
    exposureMinutes: value.exposure_minutes,
    episodeCount: value.episode_count,
    matchCount: value.match_count,
    matchesIncluded: value.matches_included,
    matchesExcluded: value.matches_excluded,
    exclusionReasons: value.exclusion_reasons,
    formulaVersion: value.formula_version,
    empty: value.empty,
  }
}

function mapStateLens(value: ApiStateLens): StateLensMetadata {
  return {
    contractVersion: value.contract_version,
    selected: mapStateLensScope(value.selected),
    evidence: mapStateLensEvidence(value.evidence),
    eligibleRefinements: {
      states: value.eligible_refinements.states,
      goalDifferences: value.eligible_refinements.goal_differences,
      phases: value.eligible_refinements.phases,
      drawProvenances: value.eligible_refinements.draw_provenances,
      stateAgeSeconds: value.eligible_refinements.state_age_seconds,
    },
    comparison: {
      enabled: value.comparison.enabled,
      baseline: value.comparison.baseline ? mapStateLensScope(value.comparison.baseline) : null,
      baselineEvidence: value.comparison.baseline_evidence ? mapStateLensEvidence(value.comparison.baseline_evidence) : null,
      comparison: mapStateLensScope(value.comparison.comparison),
      comparisonEvidence: mapStateLensEvidence(value.comparison.comparison_evidence),
    },
  }
}

function eventMinute(matchSeconds: number | null) {
  return matchSeconds == null ? 0 : Math.floor(matchSeconds / 60)
}

/**
 * Opta coordinates have their origin at the BOTTOM-left corner (y increases
 * toward the far touchline), but our components render y top-down. Flip once
 * here so every event-map consumer works in display space; grid row indices
 * are inverted to match.
 */
function toDisplay(coordinate: PitchCoordinate): PitchCoordinate {
  return { x: coordinate.x, y: 100 - coordinate.y }
}

/** Action grids are 24x16, flow bins 6x4 — row 0 sits at the bottom in Opta space. */
const ACTION_GRID_ROWS = 16
const FLOW_GRID_ROWS = 4

function invertRow(row: number, rowCount: number) {
  return rowCount - 1 - row
}

function slug(value: string) {
  return value.trim().toLowerCase().replaceAll(' ', '_').replaceAll('-', '_')
}

function shotOutcome(value: string): ShotOutcome {
  const normalized = slug(value)
  if (normalized === 'goal' || normalized === 'saved' || normalized === 'blocked' || normalized === 'woodwork') {
    return normalized
  }
  return 'off_target'
}

function shotBodyPart(value: string): ShotBodyPart {
  const normalized = slug(value)
  if (normalized === 'left_foot' || normalized === 'right_foot' || normalized === 'head') {
    return normalized
  }
  return 'other'
}

function shotSituation(value: string): ShotSituation {
  const normalized = slug(value) as ShotSituation
  const supported: ShotSituation[] = [
    'open_play',
    'set_piece',
    'corner',
    'direct_free_kick',
    'penalty',
    'fast_break',
    'unknown',
  ]
  return supported.includes(normalized) ? normalized : 'unknown'
}

function mapMatches(
  matches: ApiMatch[],
  eventTeamIds: Map<number, number | null>,
  viewedTeamId?: number,
): EventMatchLookup {
  return Object.fromEntries(
    matches.map(match => {
      const teamId = viewedTeamId ?? match.subject_team_id ?? eventTeamIds.get(match.ref)
      const isHome = teamId != null && teamId === match.home_team_id
      const isAway = teamId != null && teamId === match.away_team_id
      return [
        String(match.ref),
        {
          matchId: String(match.ref),
          opponent: isHome
            ? match.away_team_name ?? 'Unknown opponent'
            : isAway
              ? match.home_team_name ?? 'Unknown opponent'
              : `${match.home_team_name ?? 'Home'} v ${match.away_team_name ?? 'Away'}`,
          matchDate: match.kickoff_at.slice(0, 10),
          venue: isHome ? 'home' : isAway ? 'away' : 'neutral',
        },
      ]
    }),
  )
}

function mapGrid(cells: ApiGridCell[]): ActionGridCell[] {
  return cells.map(cell => ({
    column: cell.column,
    row: invertRow(cell.row, ACTION_GRID_ROWS),
    rawCount: cell.raw_count,
    per90Count: cell.per90_count ?? 0,
    share: cell.share,
  }))
}

function matchTeamIds(events: Array<{ match_ref: number; team_id: number | null }>) {
  const values = new Map<number, number | null>()
  for (const event of events) values.set(event.match_ref, event.team_id)
  return values
}

function mapShot(row: ApiShot, perspective: 'for' | 'against'): EventShot {
  return {
    id: `shot-${row.match_ref}-${row.event_index}-${perspective}`,
    matchRef: String(row.match_ref),
    teamId: row.team_id,
    playerId: row.player_id,
    playerName: row.player_name,
    minute: eventMinute(row.match_seconds),
    location: toDisplay({ x: row.x, y: row.y }),
    outcome: shotOutcome(row.outcome),
    bodyPart: shotBodyPart(row.body_part),
    situation: shotSituation(row.situation),
    bigChance: row.big_chance,
    assisted: row.assisted,
    perspective,
    goalMouth:
      row.goal_mouth_y != null && row.goal_mouth_z != null
        ? { y: row.goal_mouth_y, z: row.goal_mouth_z }
        : undefined,
    blockedAt:
      row.blocked_x != null && row.blocked_y != null
        ? toDisplay({ x: row.blocked_x, y: row.blocked_y })
        : undefined,
  }
}

function mapPass(row: ApiPass): EventPass {
  const deltaX = (row.end_x - row.x) * 1.05
  const deltaY = (row.end_y - row.y) * 0.68
  return {
    id: `pass-${row.match_ref}-${row.event_index}`,
    matchRef: String(row.match_ref),
    teamId: row.team_id,
    minute: eventMinute(row.match_seconds),
    start: toDisplay({ x: row.x, y: row.y }),
    end: toDisplay({ x: row.end_x, y: row.end_y }),
    outcome: row.completed ? 'successful' : 'unsuccessful',
    length: Math.sqrt(deltaX * deltaX + deltaY * deltaY),
    progressive: row.progressive,
    finalThirdEntry: row.final_third_entry,
    boxEntry: row.box_entry,
    keyPass: row.key_pass,
    cross: row.cross,
    longBall: row.long_ball,
  }
}

function mapCarry(row: ApiCarry): EventCarry {
  const deltaX = (row.end_x - row.x) * 1.05
  const deltaY = (row.end_y - row.y) * 0.68
  return {
    id: `carry-${row.match_ref}-${row.start_event_index}`,
    matchRef: String(row.match_ref),
    teamId: row.team_id,
    minute: eventMinute(row.match_seconds),
    start: toDisplay({ x: row.x, y: row.y }),
    end: toDisplay({ x: row.end_x, y: row.end_y }),
    length: Math.sqrt(deltaX * deltaX + deltaY * deltaY),
    progressive: row.progressive,
    finalThirdEntry: row.final_third_entry,
    boxEntry: row.box_entry,
    lowConfidence: row.low_confidence,
  }
}

function metadata(value: ApiMaterialization) {
  return {
    formulaVersion: value.formula_version,
    materialisationVersion: `${value.materialization_run_id}:${value.profile_version}`,
    updatedAt: value.materialized_at,
  }
}

export async function fetchPlayerEventProfile(
  playerId: number,
  competition: string,
  season: string,
  teamId?: number | null,
  matchRef?: string | null,
): Promise<PlayerEventProfilePayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  const raw = await readJson<ApiPlayerProfile>(
    `${BASE}/player-seasons/event-profile/${playerId}?${params}`,
  )
  const shots = raw.shots.map(row => mapShot(row, 'for'))
  const expectedMatches = raw.coverage.expected_matches ?? raw.coverage.observed_matches
  return {
    playerId: raw.canonical_player_id,
    playerName: raw.canonical_player_name,
    competition: raw.competition_code,
    season: raw.season_label,
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    splitType: raw.split_type,
    coverage: {
      matchesIncluded: raw.coverage.observed_matches,
      matchesExpected: expectedMatches,
      minutes: raw.coverage.observed_event_minutes,
      complete: expectedMatches > 0 && raw.coverage.observed_matches >= expectedMatches,
    },
    metadata: metadata(raw.materialization),
    summary: raw.summary,
    modules: {
      passMap: raw.availability.pass_map,
      shotMap: raw.availability.shot_map,
      actionGrid: raw.availability.action_grid,
    },
    averageTouchLocation:
      raw.average_touch_location.x != null && raw.average_touch_location.y != null
        ? {
            ...toDisplay({
              x: raw.average_touch_location.x,
              y: raw.average_touch_location.y,
            }),
            sampleSize: raw.average_touch_location.sample_size,
          }
        : null,
    touchGrid: mapGrid(raw.touch_grid ?? []),
    shots,
    matches: mapMatches(raw.matches, matchTeamIds(raw.shots)),
  }
}

export async function fetchPlayerPassMap(
  playerId: number,
  competition: string,
  season: string,
  filter: PlayerPassFilter,
  outcome: PlayerPassOutcome,
  teamId?: number | null,
  matchRef?: string | null,
): Promise<PlayerPassMapPayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  params.set('filter', filter)
  params.set('outcome', outcome)
  const raw = await readJson<ApiPlayerPasses>(
    `${BASE}/player-seasons/event-profile/${playerId}/passes?${params}`,
  )
  return {
    playerId: raw.canonical_player_id,
    competition: raw.competition_code,
    season: raw.season_label,
    filter: raw.filter,
    outcome: raw.outcome,
    truncated: raw.truncated,
    totalMatching: raw.total_matching_count,
    carriesTruncated: raw.carries_truncated ?? false,
    totalCarries: raw.total_carry_count ?? raw.carries?.length ?? 0,
    totalAllCarries: raw.total_all_carry_count ?? raw.total_carry_count ?? raw.carries?.length ?? 0,
    passes: raw.passes.map(mapPass),
    carries: (raw.carries ?? []).map(mapCarry),
    matches: mapMatches(raw.matches, matchTeamIds(raw.passes)),
  }
}

function mapZoneVariant(variant: ApiShotZoneVariant): ShotZoneVariant {
  return {
    cells: variant.cells.map(cell => ({
      column: cell.column,
      row: cell.row,
      shots: cell.shots,
      goals: cell.goals,
      rate: cell.conversion ?? cell.save_rate ?? null,
    })),
    totals: variant.totals,
  }
}

function emptyZoneVariant(): ShotZoneVariant {
  return { cells: [], totals: {} }
}

type ApiZonePayloadBase = {
  canonical_player_id: number
  competition_code: string
  season_label: string
  grid: PlayerShotZonesPayload['grid']
  variants: ApiShotZoneVariants
  matches: ApiMatch[]
}

function mapZoneCommon(raw: ApiZonePayloadBase) {
  return {
    playerId: raw.canonical_player_id,
    competition: raw.competition_code,
    season: raw.season_label,
    grid: raw.grid,
    variants: {
      all: raw.variants.all ? mapZoneVariant(raw.variants.all) : emptyZoneVariant(),
      open_play: raw.variants.open_play
        ? mapZoneVariant(raw.variants.open_play)
        : emptyZoneVariant(),
      penalties_only: raw.variants.penalties_only
        ? mapZoneVariant(raw.variants.penalties_only)
        : emptyZoneVariant(),
    },
    matches: mapMatches(raw.matches, new Map()),
  }
}

export async function fetchPlayerShotZones(
  playerId: number,
  competition: string,
  season: string,
  teamId?: number | null,
  matchRef?: string | null,
): Promise<PlayerShotZonesPayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  const raw = await readJson<ApiPlayerShotZones>(
    `${BASE}/player-seasons/event-profile/${playerId}/shot-zones?${params}`,
  )
  return {
    ...mapZoneCommon(raw),
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    shotCount: raw.shot_count,
  }
}

export async function fetchGkShotZones(
  playerId: number,
  competition: string,
  season: string,
  matchRef?: string | null,
): Promise<GkShotZonesPayload> {
  const params = requestParams(competition, season, null, matchRef)
  const raw = await readJson<ApiGkShotZones>(
    `${BASE}/player-seasons/event-profile/${playerId}/gk-shot-zones?${params}`,
  )
  return {
    ...mapZoneCommon(raw),
    matchesIncluded: raw.matches_included,
    matchesExcluded: raw.matches_excluded,
    attributionNote: raw.attribution_note,
    selectedMatchIncluded: raw.selected_match_included,
    shotsFaced: raw.shots_faced,
  }
}

function mapFlow(row: ApiTeamProfile['pass_flow'][number]): TeamPassFlow {
  return {
    id: `flow-${row.column}-${row.row}`,
    bin: { column: row.column, row: invertRow(row.row, FLOW_GRID_ROWS) },
    origin: toDisplay({ x: row.mean_origin_x, y: row.mean_origin_y }),
    destination: toDisplay({ x: row.mean_destination_x, y: row.mean_destination_y }),
    completedCount: row.completed_count,
    share: row.share,
    meanLength: row.mean_length_metres,
  }
}

export async function fetchTeamEventProfile(
  teamId: number,
  competition: string,
  season: string,
  matchRef?: string | null,
  stateLens?: StateLensRequest,
): Promise<TeamEventProfilePayload> {
  const params = requestParams(competition, season, null, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiTeamProfile>(
    `${BASE}/team-seasons/event-profile/${teamId}?${params}`,
  )
  const allShots = [...raw.shots_for, ...raw.shots_against]
  return {
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    competition: raw.competition_code,
    season: raw.season_label,
    coverage: {
      matchesIncluded: raw.coverage.observed_matches,
      matchesExpected: raw.coverage.expected_matches,
      minutes: raw.coverage.observed_matches * 90,
      complete:
        raw.coverage.expected_matches > 0 &&
        raw.coverage.observed_matches >= raw.coverage.expected_matches,
    },
    metadata: metadata(raw.materialization),
    summary: raw.summary,
    passFlows: raw.pass_flow.map(mapFlow),
    shots: [
      ...raw.shots_for.map(row => mapShot(row, 'for')),
      ...raw.shots_against.map(row => mapShot(row, 'against')),
    ],
    actionTerritory: mapGrid(raw.touch_grid ?? []),
    opponentActionTerritory: mapGrid(raw.opponent_touch_grid ?? []),
    matches: mapMatches(raw.matches, matchTeamIds(allShots), raw.canonical_team_id),
    stateLens: mapStateLens(raw.state_lens),
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
  const groups: Array<[DefensiveTerritoryGroup, 'all' | 'non_clearance' | 'clearance']> = [
    ['all', 'all'],
    ['nonClearance', 'non_clearance'],
    ['clearance', 'clearance'],
  ]
  const grids = Object.fromEntries(groups.map(([target, source]) => [
    target,
    value.grid.cells.map(cell => ({
      column: cell.column,
      row: invertRow(cell.row, value.grid.rows),
      rawCount: cell[source].count,
      per90Count: cell[source].per_state_minute ?? 0,
      share: cell[source].share,
    })),
  ])) as Record<DefensiveTerritoryGroup, ActionGridCell[]>
  const families = Object.keys(value.family_evidence) as DefensiveActionFamily[]
  const gridsByFamily = Object.fromEntries(families.map(family => [
    family,
    value.grid.cells.map(cell => ({
      column: cell.column,
      row: invertRow(cell.row, value.grid.rows),
      rawCount: cell.families[family].count,
      per90Count: cell.families[family].per_state_minute ?? 0,
      share: cell.families[family].share,
    })),
  ])) as Record<DefensiveActionFamily, ActionGridCell[]>
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
    familyEvidence: Object.fromEntries(families.map(family => [family, {
      height: mapDefensiveHeight(value.family_evidence[family].height),
      ratePerStateMinute: value.family_evidence[family].rate_per_state_minute,
    }])) as DefensiveTerritoryEvidence['familyEvidence'],
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
    grids,
    gridsByFamily,
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

export async function fetchTeamPassState(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
): Promise<TeamPassStatePayload> {
  const params = requestParams(competition, season, null, matchRef)
  for (const [key, value] of Object.entries(stateLens)) params.set(key, value)
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
        for: delta.for.map(cell => ({
          column: cell.column,
          row: cell.row,
          shotsPer90Delta: cell.shots_per_90_delta,
          locationShareDelta: cell.location_share_delta,
          observedConversionDelta: cell.observed_conversion_delta,
        })),
        against: delta.against.map(cell => ({
          column: cell.column,
          row: cell.row,
          shotsPer90Delta: cell.shots_per_90_delta,
          locationShareDelta: cell.location_share_delta,
          observedConversionDelta: cell.observed_conversion_delta,
        })),
      } : null,
    },
  }
}
