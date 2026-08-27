import type { EventMatchLookup, StateLensMetadata, StateLensScope } from './eventMaps'

export type TeamStyleAxisCategory =
  | 'build_up'
  | 'progression_attack'
  | 'defence'
  | 'transitions'

export type TeamStyleReliability = 'verified' | 'partial' | 'sparse' | 'unavailable'
export type TeamStyleGameState = 'winning' | 'drawing' | 'losing'

export interface TeamStyleAxisDefinition {
  key: string
  category: TeamStyleAxisCategory
  label: string
  description: string
  formula: string
  unit: string
  higherMeans: string
  evidenceType: string
  minimumEvidence: {
    exposureSeconds: number
    events: number
  }
  direction: 'prevalence'
  percentileVersion: string
}

export interface TeamStyleAxis {
  key: string
  category: TeamStyleAxisCategory
  label: string
  description: string
  formula: string
  formulaVersion: string
  value: number | null
  rawValue: number | null
  unit: string
  direction: 'prevalence'
  raw: Record<string, unknown>
  evidence: {
    count: number
    exposureSeconds: number
    minimum: {
      exposureSeconds: number
      events: number
    }
  }
  reliability: TeamStyleReliability
  percentileEligible: boolean
  percentile: number | null
  ineligibilityReason: string | null
  distribution?: TeamStyleDistribution
}

export interface TeamStyleExposure {
  seconds: number
  minutes: number
  episodeCount: number
  matchCount: number
  matchesExcluded: number
}

export interface TeamStyleCohort {
  teamId: number
  teamName: string
  scope: StateLensScope
  formulaVersion: string
  percentileVersion: string
  exposure: TeamStyleExposure
  axes: Record<string, TeamStyleAxis>
  evidence: {
    eventCount: number
    passAttempts: number
    locatedPassAttempts: number
    carryAttempts: number
    shotCount: number
    defensiveActionCount: number
    settledBlockCount: number
    counterLaunchCount: number
    sourceEventLimit: number | null
    truncated: boolean
  }
  reliability: {
    stateExposureVerified: boolean
    matchesExcluded: number
    sparseAxes: string[]
    unavailableAxes: string[]
  }
}

export interface TeamStyleDistribution {
  axis: string
  sampleSize: number
  percentileVersion: string
  higherMeans: 'prevalence'
  distribution: {
    sampleSize: number
    min: number | null
    p10: number | null
    p25: number | null
    p50: number | null
    p75: number | null
    p90: number | null
    max: number | null
    iqr: number | null
    values: number[]
  }
  members: Array<{
    teamId: number
    teamName: string | null
    value: number | null
    reliability: TeamStyleReliability
    percentileEligible: boolean
    target?: boolean
  }>
}

export interface TeamStyleSignedShift {
  selectedValue: number | null
  baselineValue: number | null
  rawDelta: number | null
  unit: string | null
  normalisedDelta: number | null
  normalisation: string
  scale: number | null
  direction: 'prevalence'
  eligible: boolean
  reliability: TeamStyleReliability
}

export interface TeamStyleShapePayload {
  contractVersion: string
  formulaVersion: string
  percentileVersion: string
  canonicalTeamId: number
  canonicalTeamName: string
  competitionSeason: number
  competitionCode: string
  seasonLabel: string
  selectedMatchRef: number | null
  matches: EventMatchLookup
  axisKeys: string[]
  axisDefinitions: TeamStyleAxisDefinition[]
  cohort: {
    type: 'competition_season'
    competitionSeasonId: number
    competitionCode: string
    seasonLabel: string
    teamCount: number
    teams: Array<{ teamId: number; teamName: string | null }>
    percentilesAvailable: boolean
    percentileNote: string
  }
  stateLens: StateLensMetadata
  overall: TeamStyleCohort
  selected: TeamStyleCohort
  baseline: TeamStyleCohort | null
  distributions: {
    overall: Record<string, TeamStyleDistribution>
    selected: Record<string, TeamStyleDistribution>
    baseline: Record<string, TeamStyleDistribution> | null
  }
  /** Optional target-team state series, loaded only for the state chart view. */
  gameStates?: Partial<Record<TeamStyleGameState, TeamStyleCohort | null>> | null
  comparison: {
    enabled: boolean
    baseline: TeamStyleCohort | null
    selectedMinusBaseline: Record<string, TeamStyleSignedShift> | null
    normalisationNote: string
  }
  notes: string[]
}
