import type { StateLensMetadata } from './eventMaps'

export type TransitionDirection = 'attacking' | 'concession'
export type TransitionOutcomeKey =
  | 'territorial_entry'
  | 'box_entry'
  | 'shot'
  | 'big_chance'
  | 'goal'

export interface TransitionLadderRow {
  key: TransitionOutcomeKey
  label: string
  count: number
  ratePerOpportunity: number | null
}

export interface TransitionDirectionStats {
  opportunities: number
  outcomeLadder: TransitionLadderRow[]
}

export interface TransitionLeverageScope {
  attacking: TransitionDirectionStats
  concession: TransitionDirectionStats
  coverage: {
    matchesIncluded: number
    matchesExcluded: number
    possessionCount: number
    ambiguousPossessionCount: number
    sparse: boolean
    sparseThreshold: number
  }
}

export interface TransitionLeveragePayload {
  stateLens: StateLensMetadata
  selected: TransitionLeverageScope
  comparison: {
    baseline: TransitionLeverageScope | null
    delta: Record<TransitionDirection, Record<TransitionOutcomeKey, number | null>> | null
  }
}
