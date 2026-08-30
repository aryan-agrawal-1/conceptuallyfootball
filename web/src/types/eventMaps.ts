import type { SeasonRole } from './api'

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
  color?: string
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
  color?: string
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
  gameState?: 'winning' | 'drawing' | 'losing'
  color?: string
  comparisonLane?: number
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
  reliability?: Record<string, boolean | string | number>
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
  stateLens?: StateLensMetadata
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
  stateLens?: StateLensMetadata
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
  stateLens?: StateLensMetadata
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
  stateLens?: StateLensMetadata
}

export type PlayerStateMetric = {
  count: number
  perStateMinute: number | null
  per90: number | null
}

export type PlayerStateLocation = {
  x: number | null
  y: number | null
  sampleSize: number
}

export type PlayerDefensiveFamily = {
  count: number
  locatedCount: number
  ratePerStateMinute: number | null
  height: {
    sampleSize: number
    mean: number | null
    median: number | null
  }
  grid: ActionGridCell[]
}

export type PlayerTransitionAction = {
  sequence: number
  eventType: string
  matchSeconds: number | null
  playerId: number | null
  playerName: string | null
  role: string
  roleLabel: string
}

export type PlayerTransitionEvidence = {
  matchRef: number
  possessionId: string
  teamId: number | null
  state: {
    state: string | null
    goalDifference: number | null
    phase: string | null
    drawProvenance: string | null
    stateAgeSeconds: number | null
    episodeIndex: number | null
  }
  stateTransition: {
    actual: boolean
    classification: string
    before: string | null
    after: string | null
    perspective: string | null
  }
  outcomeTier: string
  rapidTransition: {
    isCounterLaunch: boolean
    qualifiesForwardProgress: boolean
    elapsedSeconds: number | null
    forwardMetres: number | null
    speedMps: number | null
    outcome: string | null
  }
  actionStages: string[]
  actionEventIndexes: number[]
  verifiedPlayerActionSequences: number[]
  possessionTrace: PlayerTransitionAction[]
}

export type PlayerTransitionLeverage = {
  available: boolean
  verified: boolean
  contractVersion: string
  formulaVersion: string
  opportunities: number
  involvedPossessions: number
  counterPossessions: number
  shotProducingPossessions: number
  boxEntryPossessions: number
  finalThirdPossessions: number
  bigChancePossessions: number
  goalPossessions: number
  stateChangingPossessions: number
  sequenceStages: Record<string, {
    actions: number
    possessions: number
    ratePerOpportunity: number | null
  }>
  sequenceEvidence: PlayerTransitionEvidence[]
  evidenceTruncated: boolean
  ambiguousExcluded: number
  exclusions: Record<string, number>
  matching: Record<string, boolean | string>
}

export type PlayerStateCohort = {
  exposureSeconds: number
  exposureMinutes: number
  summary: Record<string, number>
  rates: Record<string, PlayerStateMetric>
  passing: {
    attempts: number
    completed: number
    completionRate: number | null
    progressive: number
    keyPasses: number
    finalThirdEntries: number
    boxEntries: number
    crosses: number
    longBalls: number
    meanLengthMetres: number | null
    meanForwardMetres: number | null
    forwardShare: number | null
  }
  carrying: {
    attempts: number
    progressive: number
    finalThirdEntries: number
    boxEntries: number
    meanLengthMetres: number | null
    meanForwardMetres: number | null
    forwardShare: number | null
  }
  touchLocation: PlayerStateLocation
  actionLocation: PlayerStateLocation
  defensiveLocation: PlayerStateLocation
  touchGrid: ActionGridCell[]
  defensiveGrid: ActionGridCell[]
  defensiveByFamily: Partial<Record<DefensiveActionFamily, PlayerDefensiveFamily>>
  defensiveHeight: {
    sampleSize: number
    mean: number | null
    median: number | null
  }
  teamActionShares: Record<string, {
    playerCount: number
    teamCount: number
    share: number | null
    unit: string
  }>
  possession: {
    available: boolean
    verified: boolean
    involvedPossessions: number
    counterPossessions: number
    shotProducingPossessions: number
    boxEntryPossessions: number
    finalThirdPossessions: number
    ambiguousExcluded: number
    bigChancePossessions: number
    goalPossessions: number
    stateChangingPossessions: number
    transitionLeverage: PlayerTransitionLeverage
  }
  evidence: StateLensEvidence
}

export type PlayerStateComparisonPayload = {
  contractVersion: string
  playerId: number
  playerName: string
  teamId: number | null
  teamName: string | null
  positionGroup: string
  seasonRole: SeasonRole
  stateEvidence: {
    selected: Record<string, { count: number; per_state_minute: number | null; per_90: number | null }>
    baseline: Record<string, { count: number; per_state_minute: number | null; per_90: number | null }> | null
    selectedScope: Record<string, unknown>
    baselineScope: Record<string, unknown> | null
  }
  stateLens: StateLensMetadata
  selected: PlayerStateCohort
  baseline: PlayerStateCohort | null
  comparison: {
    enabled: boolean
    selectedMinusBaseline: {
      [key: string]: {
        absolute: number | null
        relative: number | null
        unit: string
      }
    }
    movement: {
      player: { x: number | null; y: number | null }
      matchedTeam: { x: number | null; y: number | null } | null
    }
    actionShareChange: Record<string, number | null>
  } | null
  responseRoles: Array<{
    label: string
    confidence: string
    formula: string
    observations: Record<string, unknown>
    reliability: Record<string, boolean | string | number>
  }>
  roleFormulae: Array<Record<string, unknown>>
  teamContext: {
    available: boolean
    selectionRequired?: boolean
    selectionNote?: string | null
    matching: string
    selected: PlayerStateCohort | null
    baseline: PlayerStateCohort | null
  }
  exclusions: Record<string, boolean>
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

export type DefensiveTerritoryGroup = 'all' | 'nonClearance' | 'clearance'
export type DefensiveActionFamily =
  | 'recovery'
  | 'tackle'
  | 'interception'
  | 'blocked_pass'
  | 'defensive_aerial'
  | 'defensive_challenge'
  | 'clearance'

export type DefensiveHeightEvidence = {
  sampleSize: number
  median: number | null
  mean: number | null
  spread: {
    p10: number | null
    p90: number | null
    p10P90: number | null
    standardDeviation: number | null
  }
}

export type DefensiveTerritoryEvidence = {
  contractVersion: string
  disclaimer: string
  counts: {
    included: number
    withLocation: number
    withoutLocation: number
    nonClearance: number
    clearance: number
    recovery: number
  }
  familyComposition: Array<{
    family: DefensiveActionFamily
    count: number
    withLocation: number
    withoutLocation: number
    share: number
  }>
  familyEvidence: Record<DefensiveActionFamily, {
    height: DefensiveHeightEvidence
    ratePerStateMinute: number | null
  }>
  heights: {
    recovery: DefensiveHeightEvidence
    nonClearanceAction: DefensiveHeightEvidence
    clearance: DefensiveHeightEvidence
    all: DefensiveHeightEvidence
  }
  distribution: Array<{ band: string; count: number; share: number }>
  ratesPerStateMinute: {
    all: number | null
    nonClearance: number | null
    clearance: number | null
    recovery: number | null
  }
  grids: Record<DefensiveTerritoryGroup, ActionGridCell[]>
  gridsByFamily: Record<DefensiveActionFamily, ActionGridCell[]>
  evidence: {
    locatedSampleSize: number
    sparse: boolean
    sparseThreshold: number
    exclusions: Record<string, number>
  }
}

export type TeamDefensiveTerritoryPayload = {
  teamId: number
  teamName: string
  competition: string
  season: string
  stateLens: StateLensMetadata
  selected: DefensiveTerritoryEvidence
  baseline: DefensiveTerritoryEvidence | null
}

export type ShotPressurePenaltyMode = 'exclude' | 'include' | 'only'

export type ShotPressureMetric = {
  count: number
  perMinute: number | null
  per90: number | null
}

export type ShotPressureSurfaceCell = {
  column: number
  row: number
  shotCount: number
  shotsPer90: number | null
  locationShare: number | null
  observedConversion: number | null
}

export type ShotPressureCohort = {
  evidence: StateLensEvidence & {
    zeroShotEpisodesFor: number
    zeroShotEpisodesAgainst: number
  }
  frequency: {
    for: Record<string, ShotPressureMetric>
    against: Record<string, ShotPressureMetric>
    openness: { shotCount: number; shotsPerMinute: number | null; shotsPer90: number | null }
  }
  outcomes: {
    for: Record<string, ShotPressureMetric>
    against: Record<string, ShotPressureMetric>
    observedConversionFor: number | null
    observedConversionAgainst: number | null
  }
  firstShot: Record<'for' | 'against', {
    episodeCount: number
    episodesWithShot: number
    zeroShotEpisodes: number
    meanSecondsFromStateEntry: number | null
    medianSecondsFromStateEntry: number | null
  }>
  location: Record<'for' | 'against', {
    columns: number
    rows: number
    locatedShots: number
    unlocatedShots: number
    cells: ShotPressureSurfaceCell[]
  }>
}

export type ShotPressureDeltaCell = {
  column: number
  row: number
  shotsPer90Delta: number | null
  locationShareDelta: number | null
  observedConversionDelta: number | null
}

export type TeamShotPressurePayload = {
  teamId: number
  teamName: string
  competition: string
  season: string
  stateLens: StateLensMetadata
  formulaVersion: string
  penaltyMode: ShotPressurePenaltyMode
  penaltyNote: string
  fastBreakNote: string
  measurementNote: string
  selected: ShotPressureCohort
  comparison: {
    enabled: boolean
    baseline: ShotPressureCohort | null
    locationDelta: Record<'for' | 'against', ShotPressureDeltaCell[]> | null
  }
}
