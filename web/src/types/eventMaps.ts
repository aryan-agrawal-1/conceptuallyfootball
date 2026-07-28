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
export type ShotSituation = 'open_play' | 'set_piece' | 'corner' | 'penalty' | 'fast_break'

export type EventShot = {
  id: string
  matchRef: string
  minute: number
  second?: number
  location: PitchCoordinate
  outcome: ShotOutcome
  bodyPart: ShotBodyPart
  situation: ShotSituation
  bigChance: boolean
  assisted: boolean
  perspective: 'for' | 'against'
  goalMouth?: PitchCoordinate
  blockedAt?: PitchCoordinate
}

export type ActionGridCell = {
  column: number
  row: number
  rawCount: number
  per90Count: number
  share: number
}

export type TeamFlowZone = {
  column: number
  row: number
}

export type TeamPassFlow = {
  id: string
  startZone: TeamFlowZone
  endZone: TeamFlowZone
  completedCount: number
  attemptedCount: number
  share: number
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

export type PlayerEventProfilePayload = {
  playerId: number
  playerName: string
  competition: string
  season: string
  teamId: number | null
  coverage: EventProfileCoverage
  metadata: EventProfileMetadata
  modules: {
    passMap: EventModuleState
    shotMap: EventModuleState
    actionGrid: EventModuleState
  }
  averageTouchLocation: (PitchCoordinate & { sampleSize: number }) | null
  actionGrid: ActionGridCell[]
  shots: EventShot[]
  matches: EventMatchLookup
}

export type PlayerPassMapPayload = {
  playerId: number
  competition: string
  season: string
  filter:
    | 'completed'
    | 'progressive'
    | 'final_third_entries'
    | 'box_entries'
    | 'key_passes'
    | 'crosses'
    | 'long_balls'
    | 'failed'
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
  passFlows: TeamPassFlow[]
  shots: EventShot[]
  actionTerritory: ActionGridCell[]
  matches: EventMatchLookup
}
