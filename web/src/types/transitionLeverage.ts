import type { StateLensMetadata } from './eventMaps'

export type TransitionDirection = 'attacking' | 'concession'
export type TransitionOutcomeKey =
  | 'territorial_entry'
  | 'box_entry'
  | 'shot'
  | 'big_chance'
  | 'goal'
export type TransitionSequenceRole =
  | 'origin_recovery'
  | 'escape'
  | 'advancement'
  | 'destabilisation'
  | 'creation'
  | 'contest'
  | 'terminal'
  | 'support'

export interface TransitionLeverageMatch {
  ref: number
  kickoffAt: string
  homeTeamId: number | null
  homeTeamName: string | null
  awayTeamId: number | null
  awayTeamName: string | null
  subjectTeamId: number | null
  homeScore: number | null
  awayScore: number | null
}

export interface TransitionState {
  state: 'drawing' | 'winning' | 'losing' | null
  goalDifference: number | null
  phase: string | null
  drawProvenance: string | null
  stateAgeSeconds: number | null
  episodeIndex: number | null
}

export interface TransitionStateChange {
  actual: boolean
  classification: string
  before: string | null
  after: string | null
  beforeGoalDifference: number | null
  afterGoalDifference: number | null
  perspective: 'for' | 'against' | null
  directionalClassification?: string
}

export interface TransitionActionFlags {
  progressive: boolean
  finalThirdEntry: boolean
  boxEntry: boolean
  keyPass: boolean
  shotAssist: boolean
  intentionalAssist: boolean
  bigChance: boolean
  penalty: boolean
  restart: boolean
  contested: boolean
}

export interface TransitionAction {
  sequence: number
  eventIndex: number | null
  matchSeconds: number | null
  minute: number | null
  second: number | null
  period: number | null
  eventType: string
  teamId: number | null
  teamName: string | null
  teamPerspective: 'for' | 'against'
  playerId: number | null
  playerName: string | null
  location: { x: number | null; y: number | null }
  destination: { x: number | null; y: number | null }
  completed: boolean | null
  isControlAction: boolean
  isSettledDefensiveAction: boolean
  stage: string
  stageLabel: string
  role: TransitionSequenceRole
  roleLabel: string
  roleEvidence: string[]
  isTerminal: boolean
  flags: TransitionActionFlags
  gameState: TransitionState
}

export interface TransitionScore {
  isGoal: boolean
  goalType: 'goal' | 'own_goal' | null
  scoringTeamId: number | null
  perspective: 'for' | 'against' | null
  beforeGoalDifference: number | null
  afterGoalDifference: number | null
  situation: 'penalty' | null
}

export interface TransitionRapidTransition {
  isCounterLaunch: boolean
  qualifiesForwardProgress: boolean
  elapsedSeconds: number | null
  forwardMetres: number | null
  speedMps: number | null
  outcome: string | null
}

export interface TransitionLadderRow {
  key: TransitionOutcomeKey
  label: string
  count: number
  ratePerOpportunity: number | null
}

export interface TransitionObservation {
  possessionId: string
  matchRef: number
  observationRef: string
  teamId: number | null
  teamName: string | null
  direction: 'for' | 'against'
  period: number | null
  startSecond: number | null
  endSecond: number | null
  durationSeconds: number | null
  start: { x: number | null; y: number | null }
  end: { x: number | null; y: number | null }
  launchType: string
  terminationReason: string
  isAmbiguous: boolean
  rapidTransition: TransitionRapidTransition
  outcomeTier: TransitionOutcomeKey | 'possession'
  outcomeLadder: Record<TransitionOutcomeKey, { reached: boolean; firstEventIndex: number | null }>
  directionLadder: Record<TransitionOutcomeKey, boolean>
  score: TransitionScore
  state: TransitionState
  stateTransition: TransitionStateChange
  actualStateTransition?: boolean
  transitionClassification?: string
  possessionTrace: TransitionAction[]
  actionEvidence: TransitionAction[]
}

export interface TransitionStateTransitionSummary {
  count: number
  byClassification: Record<string, number>
  ratePerOpportunity: number | null
}

export interface TransitionDirectionStats {
  opportunities: number
  opportunityBasis: string
  outcomeLadder: TransitionLadderRow[]
  stateTransitions: TransitionStateTransitionSummary
  scores: { goals: number; normalGoals: number; ownGoals: number }
}

export interface TransitionPlayerStage {
  actions: number
  possessions: number
  ratePerOpportunity: number | null
}

export interface TransitionPlayerOutcome {
  opportunities: number
  involvedPossessions: number
  involvementRate: number | null
}

export interface TransitionPlayerEvidence {
  matchRef: number
  possessionId: string
  observationRef: string
  state: TransitionState
  stateTransition: TransitionStateChange
  outcomeTier: TransitionOutcomeKey | 'possession'
  actionStages: string[]
  actionEventIndexes: number[]
}

export interface TransitionPlayerRow {
  canonicalPlayerId: number | null
  canonicalPlayerName: string | null
  canonicalTeamId: number
  canonicalTeamName: string
  rosterRole: string
  verifiedOnPitchSeconds: number
  verifiedOnPitchMinutes: number
  opportunities: number
  involvedPossessions: number
  involvementRate: number | null
  outcomeLadder: Record<TransitionOutcomeKey, TransitionPlayerOutcome>
  sequenceStages: Record<TransitionSequenceRole, TransitionPlayerStage>
  concession: {
    opportunities: number
    defensiveActionPossessions: number
    defensiveActionRate: number | null
  }
  coverage: {
    includedMatchCount: number
    excludedMatchCount: number
    excludedReasons: Record<string, number>
    selectedVerifiedSeconds: number
    selectedVerifiedMinutes: number
    confidence: 'verified' | 'partial' | 'unavailable' | string
  }
  evidence: TransitionPlayerEvidence[]
  evidenceTruncated: boolean
}

export interface TransitionLeverageCoverage {
  matchesAvailable: number
  matchesEligible: number
  matchesIncluded: number
  matchesExcluded: number
  exclusionReasons: Record<string, number>
  possessionCount: number
  ambiguousPossessionCount: number
  evidenceLimit: number
  evidenceTruncated: boolean
  sparse: boolean
  sparseThreshold: number
  playerParticipation?: {
    candidateCount: number
    verifiedCount: number
    excludedCount: number
    unusedCount: number
    verifiedSeconds: number
    exclusionReasons: Record<string, number>
  }
  reliability: {
    eligibleGameStateOnly: boolean
    verifiedPossessionOnly: boolean
    timeline: string
    causalClaims: boolean
  }
}

export interface TransitionLeverageScope {
  scope: {
    state: string
    goalDifference: number | null
    phase: string | null
    drawProvenance: string | null
    minimumStateAgeSeconds: number | null
    maximumStateAgeSeconds: number | null
  }
  attacking: TransitionDirectionStats
  concession: TransitionDirectionStats
  concessionVulnerability?: TransitionDirectionStats
  players: TransitionPlayerRow[]
  playerInvolvement: TransitionPlayerRow[]
  observations: TransitionObservation[]
  coverage: TransitionLeverageCoverage
}

export interface TransitionLeveragePayload {
  contractVersion: string
  formulaVersion: string
  team: { id: number; name: string }
  competitionSeason: { id: number; competition: string; season: string }
  selectedMatchRef: number | null
  matches: TransitionLeverageMatch[]
  stateLens: StateLensMetadata
  thresholds: {
    outcomeLadder: Array<{ key: TransitionOutcomeKey; label: string }>
    sequenceRoles: Array<{ key: TransitionSequenceRole; label: string }>
    possessionCalculationVersion: string
    transitionCalculationVersion: string
    stateBoundary: string
    playerOpportunityDenominator: string
  }
  selected: TransitionLeverageScope
  comparison: {
    enabled: boolean
    baseline: TransitionLeverageScope | null
    delta: Record<TransitionDirection, Record<TransitionOutcomeKey, number | null>> | null
  }
}
