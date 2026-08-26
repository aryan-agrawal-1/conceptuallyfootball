import type {
  ActionGridCell,
  EventCarry,
  EventMatchLookup,
  EventPass,
  EventShot,
  GkShotZonesPayload,
  PitchCoordinate,
  PlayerEventProfilePayload,
  PlayerStateComparisonPayload,
  PlayerStateCohort,
  PlayerTransitionLeverage,
  PlayerTransitionEvidence,
  PlayerTransitionAction,
  PlayerPassFilter,
  PlayerPassOutcome,
  PlayerPassMapPayload,
  PlayerShotZonesPayload,
  ShotBodyPart,
  ShotOutcome,
  ShotSituation,
  ShotZoneVariant,
  TeamEventProfilePayload,
  TeamPassFlow,
} from '../../types/eventMaps'
import { appendStateLens, mapStateLens, mapStateLensEvidence, type ApiStateLens, type ApiStateLensEvidence, type StateLensRequest } from './stateLensApi'

export const BASE = '/api/v1'
export const FLOW_GRID_ROWS = 4

export async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? `API error ${response.status}`)
  }
  return response.json()
}

export function requestParams(competition: string, season: string, teamId?: number | null, matchRef?: string | null) {
  const params = new URLSearchParams({ competition, season })
  if (teamId != null) params.set('team', String(teamId))
  if (matchRef != null) params.set('match', matchRef)
  return params
}

export function toDisplay(coordinate: PitchCoordinate): PitchCoordinate {
  return { x: coordinate.x, y: 100 - coordinate.y }
}

export function invertRow(row: number, rowCount: number) {
  return rowCount - 1 - row
}

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
  state_lens?: ApiStateLens
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
  state_lens?: ApiStateLens
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
  state_lens?: ApiStateLens
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
  state_lens?: ApiStateLens
}

type ApiPlayerStateMetric = {
  count: number
  per_state_minute: number | null
  per_90: number | null
}

type ApiPlayerStateGridCell = {
  column: number
  row: number
  raw_count: number
  per_state_minute: number | null
  per_90?: number | null
  share: number
}

type ApiPlayerTransitionState = {
  state: string | null
  goal_difference: number | null
  phase: string | null
  draw_provenance: string | null
  state_age_seconds: number | null
  episode_index: number | null
}

type ApiPlayerTransitionStateChange = {
  actual: boolean
  classification: string
  before: string | null
  after: string | null
  perspective: string | null
}

type ApiPlayerTransitionAction = {
  sequence: number
  event_type: string
  match_seconds: number | null
  player_id: number | null
  player_name: string | null
  role: string
  role_label: string
}

type ApiPlayerTransitionEvidence = {
  match_ref: number
  possession_id: string
  team_id: number | null
  state: ApiPlayerTransitionState
  state_transition: ApiPlayerTransitionStateChange
  outcome_tier: string
  rapid_transition: {
    is_counter_launch: boolean
    qualifies_forward_progress: boolean
    elapsed_seconds: number | null
    forward_metres: number | null
    speed_mps: number | null
    outcome: string | null
  }
  action_stages: string[]
  action_event_indexes: number[]
  verified_player_action_sequences: number[]
  possession_trace: ApiPlayerTransitionAction[]
}

type ApiPlayerTransitionLeverage = {
  available: boolean
  verified: boolean
  contract_version: string
  formula_version: string
  opportunities: number
  involved_possessions: number
  counter_possessions: number
  shot_producing_possessions: number
  box_entry_possessions: number
  final_third_possessions: number
  big_chance_possessions: number
  goal_possessions: number
  state_changing_possessions: number
  sequence_stages: Record<string, {
    actions: number
    possessions: number
    rate_per_opportunity: number | null
  }>
  sequence_evidence: ApiPlayerTransitionEvidence[]
  evidence_truncated: boolean
  ambiguous_excluded: number
  exclusions: Record<string, number>
  matching: Record<string, boolean | string>
}

type ApiPlayerStateCohort = {
  exposure_seconds: number
  exposure_minutes: number
  summary: Record<string, number>
  rates: Record<string, ApiPlayerStateMetric>
  passing: {
    attempts: number
    completed: number
    completion_rate: number | null
    progressive: number
    key_passes: number
    final_third_entries: number
    box_entries: number
    crosses: number
    long_balls: number
    mean_length_metres: number | null
    mean_forward_metres: number | null
    forward_share: number | null
  }
  carrying: {
    attempts: number
    progressive: number
    final_third_entries: number
    box_entries: number
    mean_length_metres: number | null
    mean_forward_metres: number | null
    forward_share: number | null
  }
  touch_location: { x: number | null; y: number | null; sample_size: number }
  action_location: { x: number | null; y: number | null; sample_size: number }
  defensive_location: { x: number | null; y: number | null; sample_size: number }
  touch_grid: ApiPlayerStateGridCell[]
  defensive_grid: ApiPlayerStateGridCell[]
  defensive_height: { sample_size: number; mean: number | null; median: number | null }
  team_action_shares?: Record<string, {
    player_count: number
    team_count: number
    share: number | null
    unit: string
  }>
  possession?: {
    available: boolean
    verified: boolean
    involved_possessions: number
    counter_possessions: number
    shot_producing_possessions: number
    box_entry_possessions: number
    final_third_possessions: number
    ambiguous_excluded: number
    big_chance_possessions?: number
    goal_possessions?: number
    state_changing_possessions?: number
    transition_leverage?: ApiPlayerTransitionLeverage
  }
  evidence?: ApiStateLensEvidence
}

type ApiPlayerStateComparison = {
  contract_version: string
  canonical_player_id: number
  canonical_player_name: string
  canonical_team_id: number | null
  canonical_team_name: string | null
  position_group: string
  state_lens: ApiStateLens
  selected: ApiPlayerStateCohort
  baseline: ApiPlayerStateCohort | null
  comparison: {
    enabled: boolean
    selected_minus_baseline: Record<string, { absolute: number | null; relative: number | null; unit: string }>
    movement: {
      player: { x: number | null; y: number | null }
      matched_team: { x: number | null; y: number | null } | null
    }
    action_share_change: Record<string, number | null>
  } | null
  response_roles: Array<{
    label: string
    confidence: string
    formula: string
    observations: Record<string, unknown>
    reliability: Record<string, boolean | string | number>
  }>
  role_formulae: Array<Record<string, unknown>>
  team_context: {
    available: boolean
    selection_required?: boolean
    selection_note?: string | null
    matching: string
    selected: ApiPlayerStateCohort | null
    baseline: ApiPlayerStateCohort | null
  }
  exclusions: Record<string, boolean>
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

function eventMinute(matchSeconds: number | null) {
  return matchSeconds == null ? 0 : Math.floor(matchSeconds / 60)
}

const ACTION_GRID_ROWS = 16

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

function mapPlayerStateGrid(cells: ApiPlayerStateGridCell[]): ActionGridCell[] {
  return cells.map(cell => ({
    column: cell.column,
    row: invertRow(cell.row, ACTION_GRID_ROWS),
    rawCount: cell.raw_count,
    per90Count: cell.per_90 ?? (cell.per_state_minute == null ? 0 : cell.per_state_minute * 90),
    share: cell.share,
  }))
}

function mapPlayerTransitionAction(value: ApiPlayerTransitionAction): PlayerTransitionAction {
  return {
    sequence: value.sequence,
    eventType: value.event_type,
    matchSeconds: value.match_seconds,
    playerId: value.player_id,
    playerName: value.player_name,
    role: value.role,
    roleLabel: value.role_label,
  }
}

function mapPlayerTransitionEvidence(value: ApiPlayerTransitionEvidence): PlayerTransitionEvidence {
  return {
    matchRef: value.match_ref,
    possessionId: value.possession_id,
    teamId: value.team_id,
    state: {
      state: value.state.state,
      goalDifference: value.state.goal_difference,
      phase: value.state.phase,
      drawProvenance: value.state.draw_provenance,
      stateAgeSeconds: value.state.state_age_seconds,
      episodeIndex: value.state.episode_index,
    },
    stateTransition: {
      actual: value.state_transition.actual,
      classification: value.state_transition.classification,
      before: value.state_transition.before,
      after: value.state_transition.after,
      perspective: value.state_transition.perspective,
    },
    outcomeTier: value.outcome_tier,
    rapidTransition: {
      isCounterLaunch: value.rapid_transition.is_counter_launch,
      qualifiesForwardProgress: value.rapid_transition.qualifies_forward_progress,
      elapsedSeconds: value.rapid_transition.elapsed_seconds,
      forwardMetres: value.rapid_transition.forward_metres,
      speedMps: value.rapid_transition.speed_mps,
      outcome: value.rapid_transition.outcome,
    },
    actionStages: value.action_stages,
    actionEventIndexes: value.action_event_indexes,
    verifiedPlayerActionSequences: value.verified_player_action_sequences,
    possessionTrace: value.possession_trace.map(mapPlayerTransitionAction),
  }
}

function mapPlayerTransitionLeverage(value?: ApiPlayerTransitionLeverage): PlayerTransitionLeverage {
  if (!value) {
    return {
      available: false,
      verified: true,
      contractVersion: 'transition_leverage_unavailable',
      formulaVersion: 'unavailable',
      opportunities: 0,
      involvedPossessions: 0,
      counterPossessions: 0,
      shotProducingPossessions: 0,
      boxEntryPossessions: 0,
      finalThirdPossessions: 0,
      bigChancePossessions: 0,
      goalPossessions: 0,
      stateChangingPossessions: 0,
      sequenceStages: {},
      sequenceEvidence: [],
      evidenceTruncated: false,
      ambiguousExcluded: 0,
      exclusions: {},
      matching: {},
    }
  }
  return {
    available: value.available,
    verified: value.verified,
    contractVersion: value.contract_version,
    formulaVersion: value.formula_version,
    opportunities: value.opportunities,
    involvedPossessions: value.involved_possessions,
    counterPossessions: value.counter_possessions,
    shotProducingPossessions: value.shot_producing_possessions,
    boxEntryPossessions: value.box_entry_possessions,
    finalThirdPossessions: value.final_third_possessions,
    bigChancePossessions: value.big_chance_possessions,
    goalPossessions: value.goal_possessions,
    stateChangingPossessions: value.state_changing_possessions,
    sequenceStages: Object.fromEntries(Object.entries(value.sequence_stages).map(([key, stage]) => [key, {
      actions: stage.actions,
      possessions: stage.possessions,
      ratePerOpportunity: stage.rate_per_opportunity,
    }])),
    sequenceEvidence: value.sequence_evidence.map(mapPlayerTransitionEvidence),
    evidenceTruncated: value.evidence_truncated,
    ambiguousExcluded: value.ambiguous_excluded,
    exclusions: value.exclusions,
    matching: value.matching,
  }
}

function mapPlayerStateCohort(value: ApiPlayerStateCohort): PlayerStateCohort {
  const mapLocation = (location: ApiPlayerStateCohort['touch_location']) => ({
    x: location.x,
    y: location.y == null ? null : 100 - location.y,
    sampleSize: location.sample_size,
  })
  return {
    exposureSeconds: value.exposure_seconds,
    exposureMinutes: value.exposure_minutes,
    summary: value.summary,
    rates: Object.fromEntries(Object.entries(value.rates).map(([key, metric]) => [key, {
      count: metric.count,
      perStateMinute: metric.per_state_minute,
      per90: metric.per_90,
    }])),
    passing: {
      attempts: value.passing.attempts,
      completed: value.passing.completed,
      completionRate: value.passing.completion_rate,
      progressive: value.passing.progressive,
      keyPasses: value.passing.key_passes,
      finalThirdEntries: value.passing.final_third_entries,
      boxEntries: value.passing.box_entries,
      crosses: value.passing.crosses,
      longBalls: value.passing.long_balls,
      meanLengthMetres: value.passing.mean_length_metres,
      meanForwardMetres: value.passing.mean_forward_metres,
      forwardShare: value.passing.forward_share,
    },
    carrying: {
      attempts: value.carrying.attempts,
      progressive: value.carrying.progressive,
      finalThirdEntries: value.carrying.final_third_entries,
      boxEntries: value.carrying.box_entries,
      meanLengthMetres: value.carrying.mean_length_metres,
      meanForwardMetres: value.carrying.mean_forward_metres,
      forwardShare: value.carrying.forward_share,
    },
    touchLocation: mapLocation(value.touch_location),
    actionLocation: mapLocation(value.action_location),
    defensiveLocation: mapLocation(value.defensive_location),
    touchGrid: mapPlayerStateGrid(value.touch_grid),
    defensiveGrid: mapPlayerStateGrid(value.defensive_grid),
    defensiveHeight: {
      sampleSize: value.defensive_height.sample_size,
      mean: value.defensive_height.mean,
      median: value.defensive_height.median,
    },
    teamActionShares: Object.fromEntries(Object.entries(value.team_action_shares ?? {}).map(([key, share]) => [key, {
      playerCount: share.player_count,
      teamCount: share.team_count,
      share: share.share,
      unit: share.unit,
    }])),
    possession: {
      available: value.possession?.available ?? false,
      verified: value.possession?.verified ?? false,
      involvedPossessions: value.possession?.involved_possessions ?? 0,
      counterPossessions: value.possession?.counter_possessions ?? 0,
      shotProducingPossessions: value.possession?.shot_producing_possessions ?? 0,
      boxEntryPossessions: value.possession?.box_entry_possessions ?? 0,
      finalThirdPossessions: value.possession?.final_third_possessions ?? 0,
      ambiguousExcluded: value.possession?.ambiguous_excluded ?? 0,
      bigChancePossessions: value.possession?.big_chance_possessions ?? 0,
      goalPossessions: value.possession?.goal_possessions ?? 0,
      stateChangingPossessions: value.possession?.state_changing_possessions ?? 0,
      transitionLeverage: mapPlayerTransitionLeverage(value.possession?.transition_leverage),
    },
    evidence: value.evidence ? mapStateLensEvidence(value.evidence) : {
      exposureSeconds: value.exposure_seconds,
      exposureMinutes: value.exposure_minutes,
      episodeCount: 0,
      matchCount: 0,
      matchesIncluded: 0,
      matchesExcluded: 0,
      exclusionReasons: {},
      formulaVersion: 'matched-player-intervals',
      empty: value.exposure_seconds <= 0,
    },
  }
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
  stateLens?: StateLensRequest,
): Promise<PlayerEventProfilePayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  appendStateLens(params, stateLens)
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
    stateLens: raw.state_lens ? mapStateLens(raw.state_lens) : undefined,
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
  stateLens?: StateLensRequest,
): Promise<PlayerPassMapPayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  appendStateLens(params, stateLens)
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
    stateLens: raw.state_lens ? mapStateLens(raw.state_lens) : undefined,
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
  stateLens?: StateLensRequest,
): Promise<PlayerShotZonesPayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPlayerShotZones>(
    `${BASE}/player-seasons/event-profile/${playerId}/shot-zones?${params}`,
  )
  return {
    ...mapZoneCommon(raw),
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    shotCount: raw.shot_count,
    stateLens: raw.state_lens ? mapStateLens(raw.state_lens) : undefined,
  }
}

export async function fetchGkShotZones(
  playerId: number,
  competition: string,
  season: string,
  matchRef?: string | null,
  stateLens?: StateLensRequest,
): Promise<GkShotZonesPayload> {
  const params = requestParams(competition, season, null, matchRef)
  appendStateLens(params, stateLens)
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
    stateLens: raw.state_lens ? mapStateLens(raw.state_lens) : undefined,
  }
}

export async function fetchPlayerStateComparison(
  playerId: number,
  competition: string,
  season: string,
  teamId?: number | null,
  matchRef?: string | null,
  stateLens?: StateLensRequest,
): Promise<PlayerStateComparisonPayload> {
  const params = requestParams(competition, season, teamId, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPlayerStateComparison>(
    `${BASE}/player-seasons/event-profile/${playerId}/state-comparison?${params}`,
  )
  const mapComparison = raw.comparison
    ? {
        enabled: raw.comparison.enabled,
        selectedMinusBaseline: raw.comparison.selected_minus_baseline,
        movement: {
          player: raw.comparison.movement.player,
          matchedTeam: raw.comparison.movement.matched_team,
        },
        actionShareChange: raw.comparison.action_share_change,
      }
    : null
  return {
    contractVersion: raw.contract_version,
    playerId: raw.canonical_player_id,
    playerName: raw.canonical_player_name,
    teamId: raw.canonical_team_id,
    teamName: raw.canonical_team_name,
    positionGroup: raw.position_group,
    stateLens: mapStateLens(raw.state_lens),
    selected: mapPlayerStateCohort(raw.selected),
    baseline: raw.baseline ? mapPlayerStateCohort(raw.baseline) : null,
    comparison: mapComparison,
    responseRoles: raw.response_roles,
    roleFormulae: raw.role_formulae,
    teamContext: {
      available: raw.team_context.available,
      selectionRequired: raw.team_context.selection_required,
      selectionNote: raw.team_context.selection_note,
      matching: raw.team_context.matching,
      selected: raw.team_context.selected ? mapPlayerStateCohort(raw.team_context.selected) : null,
      baseline: raw.team_context.baseline ? mapPlayerStateCohort(raw.team_context.baseline) : null,
    },
    exclusions: raw.exclusions,
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
