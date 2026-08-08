import type {
  ActionGridCell,
  EventMatchLookup,
  EventPass,
  EventShot,
  PlayerEventProfilePayload,
  PlayerPassFilter,
  PlayerPassMapPayload,
  ShotBodyPart,
  ShotOutcome,
  ShotSituation,
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
    observed_event_minutes: number
    competition_complete: boolean
  }
  availability: ApiAvailability
  materialization: ApiMaterialization
  summary: Record<string, number>
  average_touch_location: { x: number | null; y: number | null; sample_size: number }
  action_grid: ApiGridCell[]
  shots: ApiShot[]
  matches: ApiMatch[]
}

type ApiPlayerPasses = {
  canonical_player_id: number
  competition_code: string
  season_label: string
  filter: PlayerPassFilter
  total_matching_count: number
  truncated: boolean
  passes: ApiPass[]
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
    origin_zone: number
    destination_zone: number
    attempts: number
    completions: number
    completion_rate: number | null
  }>
  action_grid: ApiGridCell[]
  opponent_action_grid: ApiGridCell[]
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

function requestParams(competition: string, season: string, teamId?: number | null) {
  const params = new URLSearchParams({ competition, season })
  if (teamId != null) params.set('team', String(teamId))
  return params
}

function eventMinute(matchSeconds: number | null) {
  return matchSeconds == null ? 0 : Math.floor(matchSeconds / 60)
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
      const teamId = viewedTeamId ?? eventTeamIds.get(match.ref)
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
    row: cell.row,
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
    location: { x: row.x, y: row.y },
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
        ? { x: row.blocked_x, y: row.blocked_y }
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
    start: { x: row.x, y: row.y },
    end: { x: row.end_x, y: row.end_y },
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
): Promise<PlayerEventProfilePayload> {
  const params = requestParams(competition, season, teamId)
  const raw = await readJson<ApiPlayerProfile>(
    `${BASE}/player-seasons/event-profile/${playerId}?${params}`,
  )
  const shots = raw.shots.map(row => mapShot(row, 'for'))
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
      matchesExpected:
        raw.coverage.competition_expected_matches ?? raw.coverage.observed_matches,
      minutes: raw.coverage.observed_event_minutes,
      complete: raw.coverage.competition_complete,
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
            x: raw.average_touch_location.x,
            y: raw.average_touch_location.y,
            sampleSize: raw.average_touch_location.sample_size,
          }
        : null,
    actionGrid: mapGrid(raw.action_grid),
    shots,
    matches: mapMatches(raw.matches, matchTeamIds(raw.shots)),
  }
}

export async function fetchPlayerPassMap(
  playerId: number,
  competition: string,
  season: string,
  filter: PlayerPassFilter,
  teamId?: number | null,
): Promise<PlayerPassMapPayload> {
  const params = requestParams(competition, season, teamId)
  params.set('filter', filter)
  const raw = await readJson<ApiPlayerPasses>(
    `${BASE}/player-seasons/event-profile/${playerId}/passes?${params}`,
  )
  return {
    playerId: raw.canonical_player_id,
    competition: raw.competition_code,
    season: raw.season_label,
    filter: raw.filter,
    truncated: raw.truncated,
    totalMatching: raw.total_matching_count,
    passes: raw.passes.map(mapPass),
    matches: mapMatches(raw.matches, matchTeamIds(raw.passes)),
  }
}

function flowZone(index: number) {
  return { column: Math.floor(index / 3), row: index % 3 }
}

function mapFlow(
  row: ApiTeamProfile['pass_flow'][number],
  totalCompletions: number,
): TeamPassFlow {
  return {
    id: `flow-${row.origin_zone}-${row.destination_zone}`,
    startZone: flowZone(row.origin_zone),
    endZone: flowZone(row.destination_zone),
    completedCount: row.completions,
    attemptedCount: row.attempts,
    share: totalCompletions ? row.completions / totalCompletions : 0,
  }
}

export async function fetchTeamEventProfile(
  teamId: number,
  competition: string,
  season: string,
): Promise<TeamEventProfilePayload> {
  const params = requestParams(competition, season)
  const raw = await readJson<ApiTeamProfile>(
    `${BASE}/team-seasons/event-profile/${teamId}?${params}`,
  )
  const allShots = [...raw.shots_for, ...raw.shots_against]
  const totalCompletions = raw.pass_flow.reduce((total, row) => total + row.completions, 0)
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
    passFlows: raw.pass_flow.map(row => mapFlow(row, totalCompletions)),
    shots: [
      ...raw.shots_for.map(row => mapShot(row, 'for')),
      ...raw.shots_against.map(row => mapShot(row, 'against')),
    ],
    actionTerritory: mapGrid(raw.action_grid),
    opponentActionTerritory: mapGrid(raw.opponent_action_grid),
    matches: mapMatches(raw.matches, matchTeamIds(allShots), raw.canonical_team_id),
  }
}
