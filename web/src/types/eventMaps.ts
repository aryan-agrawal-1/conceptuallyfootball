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

export type EventCarry = {
  id: string
  matchRef: string
  teamId?: number | null
  minute: number
  second?: number
  start: PitchCoordinate
  end: PitchCoordinate
  length: number
  progressive: boolean
  finalThirdEntry: boolean
  boxEntry: boolean
  lowConfidence: boolean
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
  playerId?: number | null
  playerName?: string | null
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
  attemptedCount?: number
  incompleteCount?: number
  attemptsPerStateMinute?: number | null
  completionRate?: number | null
}

export type PassStateCategory = {
  category: string
  attempts: number
  completions: number
  incompletions: number
  attemptShare: number | null
  completionRate: number | null
}

export type TeamPassStateEvidence = {
  exposureSeconds: number
  exposureMinutes: number
  summary: {
    attempts: number
    completions: number
    incompletions: number
    attemptsPerStateMinute: number | null
    completionsPerStateMinute: number | null
    completionRate: number | null
    progressiveAttemptRate: number | null
    meanLengthMetres: number | null
    meanForwardMetres: number | null
    meanOriginHeight: number | null
    meanDestinationHeight: number | null
  }
  directions: PassStateCategory[]
  lengthBands: PassStateCategory[]
  flows: TeamPassFlow[]
  evidence: {
    sourcePassEvents: number
    excludedMissingCoordinates: number
    truncated: boolean
    sparse: boolean
    empty: boolean
  }
}

export type TeamPassStatePayload = {
  teamId: number
  teamName: string
  selected: TeamPassStateEvidence
  baseline: TeamPassStateEvidence | null
  delta: Record<string, number | null> | null
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

export type StateLensState = 'all' | 'drawing' | 'winning' | 'losing'
export type StateLensPhase = 'first_half' | 'second_half' | 'first_extra_time' | 'second_extra_time'
export type StateLensProvenance = 'none' | 'neutral' | 'restored' | 'surrendered'

export type StateLensScope = {
  state: StateLensState
  goalDifference: number | null
  phase: StateLensPhase | null
  drawProvenance: StateLensProvenance | null
  minimumStateAgeSeconds: number | null
  maximumStateAgeSeconds: number | null
}

export type StateLensEvidence = {
  exposureSeconds: number
  exposureMinutes: number
  episodeCount: number
  matchCount: number
  matchesIncluded: number
  matchesExcluded: number
  exclusionReasons: Record<string, number>
  formulaVersion: string
  empty: boolean
}

export type StateLensMetadata = {
  contractVersion: string
  selected: StateLensScope
  evidence: StateLensEvidence
  eligibleRefinements: {
    states: Exclude<StateLensState, 'all'>[]
    goalDifferences: number[]
    phases: StateLensPhase[]
    drawProvenances: StateLensProvenance[]
    stateAgeSeconds: { minimum: number | null; maximum: number | null }
  }
  comparison: {
    enabled: boolean
    baseline: StateLensScope | null
    baselineEvidence: StateLensEvidence | null
    comparison: StateLensScope
    comparisonEvidence: StateLensEvidence
  }
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
  carriesTruncated: boolean
  totalCarries: number
  totalAllCarries: number
  passes: EventPass[]
  carries: EventCarry[]
  matches: EventMatchLookup
}

export type ShotZoneCell = {
  column: number
  row: number
  shots: number
  goals: number
  rate: number | null
}

export type ShotZoneTotals = Record<string, number>

export type ShotZoneVariant = {
  cells: ShotZoneCell[]
  totals: ShotZoneTotals
}

export type ShotZoneGrid = {
  columns: number
  rows: number
  y_min: number
  y_max: number
  z_low_max: number
}

export type ShotZoneMatchLookup = Record<
  string,
  {
    matchId: string
    opponent: string
    matchDate: string
    venue: 'home' | 'away' | 'neutral'
  }
>

export type ShotZoneVariantKey = 'all' | 'open_play' | 'penalties_only'

export type PlayerShotZonesPayload = {
  playerId: number
  teamId: number | null
  teamName: string | null
  competition: string
  season: string
  grid: ShotZoneGrid
  shotCount: number
  variants: Record<ShotZoneVariantKey, ShotZoneVariant>
  matches: EventMatchLookup
}

export type GkShotZonesPayload = {
  playerId: number
  competition: string
  season: string
  grid: ShotZoneGrid
  matchesIncluded: number
  matchesExcluded: number
  attributionNote: string
  selectedMatchIncluded: boolean
  shotsFaced: number
  variants: Record<ShotZoneVariantKey, ShotZoneVariant>
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
  stateLens: StateLensMetadata
}
