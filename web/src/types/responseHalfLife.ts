export type ResponseHalfLifeReliability = 'verified' | 'partial' | 'sparse' | 'unavailable'

export interface ResponseHalfLifeSummary {
  sampleSize: number
  meanSeconds: number | null
  medianSeconds: number | null
}

export interface ResponseHalfLifeCohort {
  reliability: ResponseHalfLifeReliability
  qualifyingConcessions: number
  qualifyingWindows: number
  qualifyingMatches: number
  censoredEpisodes: number
  attacking: {
    halfLifeSeconds: ResponseHalfLifeSummary
    recoveredConcessions: number
  }
  structural: {
    halfLifeSeconds: ResponseHalfLifeSummary
    recoveredConcessions: number
  }
}

export interface ResponseHalfLifePayload {
  definitions: { windowSeconds: number }
  selected: ResponseHalfLifeCohort
}
