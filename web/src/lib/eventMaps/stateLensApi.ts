import type { StateLensMetadata } from '../../types/eventMaps'

export type StateLensRequest = Record<string, string>

type ApiStateLensScope = {
  state: StateLensMetadata['selected']['state']
  goal_difference: number | null
  phase: StateLensMetadata['selected']['phase']
  draw_provenance: StateLensMetadata['selected']['drawProvenance']
  minimum_state_age_seconds: number | null
  maximum_state_age_seconds: number | null
}

export type ApiStateLensEvidence = {
  exposure_seconds: number
  exposure_minutes: number
  episode_count: number
  match_count: number
  matches_included: number
  matches_excluded: number
  exclusion_reasons: Record<string, number>
  formula_version: string
  empty: boolean
}

export type ApiStateLens = {
  contract_version: string
  selected: ApiStateLensScope
  evidence: ApiStateLensEvidence
  eligible_refinements: {
    states: StateLensMetadata['eligibleRefinements']['states']
    goal_differences: number[]
    phases: StateLensMetadata['eligibleRefinements']['phases']
    draw_provenances: StateLensMetadata['eligibleRefinements']['drawProvenances']
    state_age_seconds: { minimum: number | null; maximum: number | null }
  }
  comparison: {
    enabled: boolean
    baseline: ApiStateLensScope | null
    baseline_evidence: ApiStateLensEvidence | null
    comparison: ApiStateLensScope
    comparison_evidence: ApiStateLensEvidence
  }
}

export function appendStateLens(params: URLSearchParams, stateLens?: StateLensRequest) {
  if (!stateLens) return
  for (const [key, value] of Object.entries(stateLens)) {
    if (value !== '') params.set(key, value)
  }
}

function mapStateLensScope(value: ApiStateLensScope): StateLensMetadata['selected'] {
  return {
    state: value.state,
    goalDifference: value.goal_difference,
    phase: value.phase,
    drawProvenance: value.draw_provenance,
    minimumStateAgeSeconds: value.minimum_state_age_seconds,
    maximumStateAgeSeconds: value.maximum_state_age_seconds,
  }
}

export function mapStateLensEvidence(value: ApiStateLensEvidence): StateLensMetadata['evidence'] {
  return {
    exposureSeconds: value.exposure_seconds,
    exposureMinutes: value.exposure_minutes,
    episodeCount: value.episode_count,
    matchCount: value.match_count,
    matchesIncluded: value.matches_included,
    matchesExcluded: value.matches_excluded,
    exclusionReasons: value.exclusion_reasons,
    formulaVersion: value.formula_version,
    empty: value.empty,
  }
}

export function mapStateLens(value: ApiStateLens): StateLensMetadata {
  return {
    contractVersion: value.contract_version,
    selected: mapStateLensScope(value.selected),
    evidence: mapStateLensEvidence(value.evidence),
    eligibleRefinements: {
      states: value.eligible_refinements.states,
      goalDifferences: value.eligible_refinements.goal_differences,
      phases: value.eligible_refinements.phases,
      drawProvenances: value.eligible_refinements.draw_provenances,
      stateAgeSeconds: value.eligible_refinements.state_age_seconds,
    },
    comparison: {
      enabled: value.comparison.enabled,
      baseline: value.comparison.baseline ? mapStateLensScope(value.comparison.baseline) : null,
      baselineEvidence: value.comparison.baseline_evidence
        ? mapStateLensEvidence(value.comparison.baseline_evidence)
        : null,
      comparison: mapStateLensScope(value.comparison.comparison),
      comparisonEvidence: mapStateLensEvidence(value.comparison.comparison_evidence),
    },
  }
}
