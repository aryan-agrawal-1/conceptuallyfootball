export type PitchCoordinate = {
  x: number
  y: number
}

export type EventMatchLookup = Record<
  string,
  {
    matchId: string
    opponent: string
    matchDate: string
    venue: 'home' | 'away' | 'neutral'
  }
>

export type PassOutcome = 'successful' | 'unsuccessful'

export type EventPass = {
  id: string
  matchRef: string
  teamId?: number | null
  minute: number
  second?: number
  start: PitchCoordinate
  end: PitchCoordinate
  outcome: PassOutcome
  length: number
  progressive: boolean
  finalThirdEntry: boolean
  boxEntry: boolean
  keyPass: boolean
  cross: boolean
  longBall: boolean
}

export type ShotOutcome = 'goal' | 'saved' | 'blocked' | 'off_target' | 'woodwork'
export type ShotBodyPart = 'left_foot' | 'right_foot' | 'head' | 'other'
export type ShotSituation =
  | 'open_play'
  | 'set_piece'
  | 'corner'
  | 'direct_free_kick'
  | 'penalty'
  | 'fast_break'
  | 'unknown'

export type GoalMouthCoordinate = {
  y: number
  z: number
}

export type EventShot = {
  id: string
  matchRef: string
  teamId?: number | null
  minute: number
  second?: number
  location: PitchCoordinate
  outcome: ShotOutcome
  bodyPart: ShotBodyPart
  situation: ShotSituation
  bigChance: boolean
  assisted: boolean
  perspective: 'for' | 'against'
  goalMouth?: GoalMouthCoordinate
  blockedAt?: PitchCoordinate
}

export type ActionGridCell = {
  column: number
  row: number
  rawCount: number
  per90Count: number
  share: number
}

export type TeamFlowBin = {
  column: number
  row: number
}

export type TeamPassFlow = {
  id: string
  bin: TeamFlowBin
  origin: PitchCoordinate
  destination: PitchCoordinate
  completedCount: number
  share: number
  meanLength: number
}

export type EventProfileCoverage = {
  matchesIncluded: number
  matchesExpected: number
  minutes: number
  complete: boolean
}

export type EventModuleState = {
  available: boolean
  sparse: boolean
}

export type EventProfileMetadata = {
  formulaVersion: string
  materialisationVersion: string
  updatedAt: string
}

export type PlayerPassFilter =
  | 'all'
  | 'progressive'
  | 'final_third_entry'
  | 'box_entry'
  | 'key_pass'
  | 'cross'
  | 'long_ball'

export type PlayerPassOutcome = 'all' | 'completed' | 'incomplete'

export type PlayerEventProfilePayload = {
  playerId: number
  playerName: string
  competition: string
  season: string
  teamId: number | null
  teamName: string | null
  splitType: 'season_total' | 'team'
  coverage: EventProfileCoverage
  metadata: EventProfileMetadata
  summary: Record<string, number>
  modules: {
    passMap: EventModuleState
    shotMap: EventModuleState
    actionGrid: EventModuleState
  }
  averageTouchLocation: (PitchCoordinate & { sampleSize: number }) | null
  touchGrid: ActionGridCell[]
  shots: EventShot[]
  matches: EventMatchLookup
}

export type PlayerPassMapPayload = {
  playerId: number
  competition: string
  season: string
  filter: PlayerPassFilter
  outcome: PlayerPassOutcome
  truncated: boolean
  totalMatching: number
  passes: EventPass[]
  matches: EventMatchLookup
}

export type TeamEventProfilePayload = {
  teamId: number
  teamName: string
  competition: string
  season: string
  coverage: EventProfileCoverage
  metadata: EventProfileMetadata
  summary: Record<string, number>
  passFlows: TeamPassFlow[]
  shots: EventShot[]
  actionTerritory: ActionGridCell[]
  opponentActionTerritory: ActionGridCell[]
  matches: EventMatchLookup
}
