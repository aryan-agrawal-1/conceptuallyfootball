import type { EventMatchLookup, StateLensMetadata } from './eventMaps'

export type LeadControlMetricKind = 'height' | 'rate' | 'share' | 'time'

export interface LeadControlMetric {
  key: string
  label: string
  kind: LeadControlMetricKind
  value: number | null
  count: number
  sampleSize: number
  denominator?: number
  unit: string
  exposureSeconds: number
  perStateMinute: number | null
  per90: number | null
  mean?: number | null
  episodesWithAttack?: number
  episodesWithoutAttack?: number
  baselineValue: number | null
  baselineCount: number | null
  baselineSampleSize: number | null
  baselinePerStateMinute: number | null
  baselinePer90: number | null
  delta: number | null
  deltaPerStateMinute: number | null
  deltaPer90: number | null
  reliability: string
  baselineReliability: string
  raw: Record<string, unknown>
  baselineRaw: Record<string, unknown> | null
}

export type LeadControlPassDirection = Record<'forward' | 'lateral' | 'backward', LeadControlMetric>

export interface LeadGravityComponents {
  touchOriginHeight: LeadControlMetric
  passOriginHeight: LeadControlMetric
  defensiveActionHeight: LeadControlMetric
  passDirection: LeadControlPassDirection
  boxEntries: LeadControlMetric
  shots: LeadControlMetric
  clearances: LeadControlMetric
  opponentTerritoryHeight: LeadControlMetric
  opponentFinalThirdShare: LeadControlMetric
}

export interface LeadOwnershipComponents {
  opponentBoxEntries: LeadControlMetric
  opponentShots: LeadControlMetric
  opponentBigChances: LeadControlMetric
  ownTerritorialExits: LeadControlMetric
  ownCounters: LeadControlMetric
  ownShots: LeadControlMetric
  timeToFirstMeaningfulOpponentAttack: LeadControlMetric
}

export interface LeadControlAxis {
  value: number | null
  availableComponents: number
  higherMeans: string
  unit: string
}

export interface LeadControlSurface {
  exposureSeconds: number
  exposureMinutes: number
  episodeCount: number
  matchCount: number
  windowCount: number
  eventCount: number
  gravity: {
    components: LeadGravityComponents
    rawComponents: LeadGravityComponents
    axis: LeadControlAxis
  }
  ownership: {
    components: LeadOwnershipComponents
    rawComponents: LeadOwnershipComponents
    axis: LeadControlAxis
  }
  axes: {
    behavioralRetreat: LeadControlAxis
    processControl: LeadControlAxis
  }
  reliability: LeadControlReliability
  rawCounts: Record<string, number>
}

export interface LeadControlReliability {
  status: 'verified' | 'partial' | 'sparse' | 'unavailable' | string
  labelEligible: boolean
  leadEpisodeCount: number
  minimumLeadEpisodes: number
  exposureSeconds: number
  minimumExposureSeconds: number
  matchedBaselineAvailable: boolean
  note: string
}

export interface LeadControlEpisode {
  episodeId: string
  matchRef: number | null
  phase: string | null
  leadBand: 'one_goal' | 'multi_goal' | null
  goalDifference: number | null
  startSecond: number
  endSecond: number
  stateEntrySecond: number
  durationSeconds: number
  clockBuckets: number[]
  matchedBaselineWindows: number
  matchedBaselineExposureSeconds: number
  timeToFirstMeaningfulOpponentAttackSeconds: number | null
  behavior: LeadControlSurface['gravity']
  ownership: LeadControlSurface['ownership']
  coverage: {
    exposureSeconds: number
    matchedBaseline: boolean
    reliability: LeadControlReliability
  }
  secondaryOutcomes: {
    leadSurvivedToMatchEnd: boolean | null
    finalResult: 'win' | 'draw' | 'loss' | null
    note: string
  }
}

export interface LeadControlCoverage {
  leadEpisodeCount: number
  oneGoalEpisodeCount: number
  multiGoalEpisodeCount: number
  matchCount: number
  exposureSeconds: number
  matchedBaselineWindowCount: number
  matchedBaselineEpisodeCount: number
  matchedBaselineExposureSeconds: number
  episodeEvidenceLimit: number
  episodeEvidenceTruncated: boolean
  reliability: LeadControlReliability
}

export interface LeadControlPayload {
  contractVersion: string
  formulaVersion: string
  team: { id: number; name: string | null }
  competitionSeason: { id: number; competition: string; season: string }
  selectedMatchRef: number | null
  matches: EventMatchLookup
  stateLens: StateLensMetadata
  selected: LeadControlSurface & {
    leadBandBreakdown: Record<'oneGoal' | 'multiGoal', LeadControlSurface>
    phaseBreakdown: Record<string, LeadControlSurface>
    episodes: LeadControlEpisode[]
  }
  baseline: LeadControlSurface | null
  comparison: {
    enabled: boolean
    baselineType: string
    leadState: string
    baselineState: string
    baselineGoalDifference: number
    phaseMatching: string
    clockMatching: {
      bucketSeconds: number
      toleranceSeconds: number
      rule: string
    }
    baseline: LeadControlSurface | null
    matchedWindows: number
    deltaNote: string
  }
  quadrant: {
    behavioralRetreat: LeadControlAxis
    processControl: LeadControlAxis
    placement: {
      label: string | null
      shortLabel: string
      available: boolean
      note: string
    }
  }
  episodes: LeadControlEpisode[]
  coverage: LeadControlCoverage
  thresholds: {
    clockBucketSeconds: number
    clockMatchToleranceSeconds: number
    minimumLeadEpisodes: number
    minimumLeadExposureSeconds: number
    minimumComponentEvents: number
    episodeEvidenceLimit: number
    axisScales: Record<string, number>
    possessionCalculationVersion: string
    territory: { finalThirdX: number; boxX: number }
  }
  limitations: string[]
  opponentStrength: {
    controlled: boolean
    available: boolean
    note: string
  }
}
