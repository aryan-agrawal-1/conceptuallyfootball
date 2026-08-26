import type { EventMatchLookup, StateLensMetadata } from './eventMaps'

export type ResponseHalfLifeReliability = 'verified' | 'partial' | 'sparse' | 'unavailable'
export type ResponseMetricGroup = 'attacking' | 'structural'

export interface ResponseHalfLifeComponent {
  observed: number | null
  expected: number | null
  absoluteDeviation: number | null
  normalisedDeviation: number | null
  scale: number
}

export interface ResponseHalfLifeSignal {
  signal: number | null
  supportedComponents: number
  components: Record<string, ResponseHalfLifeComponent>
  formula: string
}

export interface ResponseHalfLifeSnapshot {
  exposureSeconds: number
  exposureMinutes: number
  attacking: Record<string, number | null>
  structural: Record<string, number | null>
  counts: Record<string, number | Record<string, number>>
}

export interface ResponseHalfLifeWindow {
  index: number
  offsetSeconds: number
  startSecond: number
  endSecond: number
  durationSeconds: number
  phase: string
  isAddedTime: boolean
  complete: boolean
  censored: boolean
  censorReason: string | null
  snapshot: ResponseHalfLifeSnapshot
  attacking: ResponseHalfLifeSignal | null
  structural: ResponseHalfLifeSignal | null
}

export interface ResponseHalfLifeDestination {
  available: boolean
  reliability: ResponseHalfLifeReliability
  matchBasis: string | null
  state: string | null
  phase: string | null
  goalDifference: number | null
  exposureSeconds: number
  exposureMinutes: number
  matchCount: number
  eventCount: number
  passCount: number
  attacking: Record<string, number | null>
  structural: Record<string, number | null>
  counts: Record<string, number>
  unavailableReason: string | null
}

export interface ResponseHalfLifeEpisodeScore {
  focalGoalDifference: number | null
  focalScore: number | null
  opponentScore: number | null
}

export interface ResponseHalfLifeEpisode {
  matchRef: number | null
  providerMatchId: number
  eventIndex: number
  concessionSecond: number
  period: number
  phase: string | null
  score: {
    before: ResponseHalfLifeEpisodeScore
    after: ResponseHalfLifeEpisodeScore
  }
  state: {
    before: string | null
    after: string | null
    drawProvenance: string | null
  }
  destination: ResponseHalfLifeDestination
  firstFiveMinuteResponse: {
    available: boolean
    censorReason: string | null
    snapshot: ResponseHalfLifeSnapshot | null
    attacking: ResponseHalfLifeSignal | null
    structural: ResponseHalfLifeSignal | null
  }
  qualifies: boolean
  censored: boolean
  censorReason: string | null
  attacking: ResponseHalfLifeAggregate
  structural: ResponseHalfLifeAggregate
  windows: ResponseHalfLifeWindow[]
}

export interface ResponseHalfLifeAggregate {
  initialDeviation: number | null
  halfThreshold: number | null
  halfLifeSeconds: number | null
  recovered: boolean
  supportedWindowCount: number
  status: 'recovered' | 'no_recovery' | 'unavailable'
}

export interface ResponseHalfLifeSummary {
  sampleSize: number
  meanSeconds: number | null
  medianSeconds: number | null
  valuesSeconds: number[]
}

export interface ResponseHalfLifeCohort {
  available: boolean
  reliability: ResponseHalfLifeReliability
  reliabilityNote: string | null
  qualifyingConcessions: number
  qualifyingWindows: number
  qualifyingMatches: number
  destinationAvailableConcessions: number
  censoredEpisodes: number
  uncertainConcessionEvents: number
  censorReasons: Record<string, number>
  episodeCount: number
  traceLimit: number
  traceTruncated: boolean
  attacking: {
    halfLifeSeconds: ResponseHalfLifeSummary
    recoveredConcessions: number
    formula: string
  }
  structural: {
    halfLifeSeconds: ResponseHalfLifeSummary
    recoveredConcessions: number
    formula: string
  }
  episodes: ResponseHalfLifeEpisode[]
}

export interface ResponseHalfLifeDefinitions {
  formulaVersion: string
  windowSeconds: number
  stepSeconds: number
  overlapSeconds: number
  horizonSeconds: number
  intervalBoundary: string
  periodBoundary: string
  addedTime: string
  extraTime: string
  subsequentGoal: string
  rapidSubsequentGoalSeconds: number
  redCard: string
  participationUncertainty: string
  destination: {
    stableAgeSeconds: number
    minimumExposureSeconds: number
    minimumEvents: number
    minimumPasses: number
    priority: string
  }
  attackingComponents: string[]
  structuralComponents: string[]
  attackingScales: Record<string, number>
  structuralScales: Record<string, number>
  halfLife: string
  censorReasons: string[]
}

export interface ResponseHalfLifePayload {
  contractVersion: string
  formulaVersion: string
  canonicalTeamId: number
  canonicalTeamName: string
  competitionSeason: number
  competitionCode: string
  seasonLabel: string
  selectedMatchRef: number | null
  matches: EventMatchLookup
  definitions: ResponseHalfLifeDefinitions
  stateLens: StateLensMetadata
  selected: ResponseHalfLifeCohort
  baseline: ResponseHalfLifeCohort | null
  comparison: {
    enabled: boolean
    baseline: ResponseHalfLifeCohort | null
    note: string
  }
  notes: string[]
}
