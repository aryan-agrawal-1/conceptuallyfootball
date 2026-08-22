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
  TeamPassFlow,
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
  return {
    id: `carry-${row.match_ref}-${row.start_event_index}`,
    matchRef: String(row.match_ref),
    teamId: row.team_id,
    minute: eventMinute(row.match_seconds),
    start: toDisplay({ x: row.x, y: row.y }),
    end: toDisplay({ x: row.end_x, y: row.end_y }),
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
): Promise<TeamEventProfilePayload> {
  const params = requestParams(competition, season, null, matchRef)
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
  }
}
