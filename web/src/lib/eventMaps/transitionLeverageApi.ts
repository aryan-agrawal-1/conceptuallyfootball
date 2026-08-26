import type {
  TransitionAction,
  TransitionActionFlags,
  TransitionDirectionStats,
  TransitionLeverageCoverage,
  TransitionLeveragePayload,
  TransitionLeverageScope,
  TransitionObservation,
  TransitionPlayerEvidence,
  TransitionPlayerRow,
  TransitionRapidTransition,
  TransitionSequenceRole,
  TransitionScore,
  TransitionState,
  TransitionStateChange,
} from '../../types/transitionLeverage'
import { appendStateLens, mapStateLens, type ApiStateLens, type StateLensRequest } from './stateLensApi'
import { BASE, readJson } from './api'

type ApiAction = {
  sequence: number
  event_index: number | null
  match_seconds: number | null
  minute: number | null
  second: number | null
  period: number | null
  event_type: string
  team_id: number | null
  team_name: string | null
  team_perspective: 'for' | 'against'
  player_id: number | null
  player_name: string | null
  location: { x: number | null; y: number | null }
  destination: { x: number | null; y: number | null }
  completed: boolean | null
  is_control_action: boolean
  is_settled_defensive_action: boolean
  stage: string
  stage_label: string
  role: TransitionAction['role']
  role_label: string
  role_evidence: string[]
  is_terminal: boolean
  flags: {
    progressive: boolean
    final_third_entry: boolean
    box_entry: boolean
    key_pass: boolean
    shot_assist: boolean
    intentional_assist: boolean
    big_chance: boolean
    penalty: boolean
    restart: boolean
    contested: boolean
  }
  game_state: ApiState
}

type ApiState = {
  state: TransitionState['state']
  goal_difference: number | null
  phase: string | null
  draw_provenance: string | null
  state_age_seconds: number | null
  episode_index: number | null
}

type ApiStateChange = {
  actual: boolean
  classification: string
  before: string | null
  after: string | null
  before_goal_difference: number | null
  after_goal_difference: number | null
  perspective: 'for' | 'against' | null
  directional_classification?: string
}

type ApiScore = {
  is_goal: boolean
  goal_type: 'goal' | 'own_goal' | null
  scoring_team_id: number | null
  perspective: 'for' | 'against' | null
  before_goal_difference: number | null
  after_goal_difference: number | null
  situation: 'penalty' | null
}

type ApiRapidTransition = {
  is_counter_launch: boolean
  qualifies_forward_progress: boolean
  elapsed_seconds: number | null
  forward_metres: number | null
  speed_mps: number | null
  outcome: string | null
}

type ApiOutcomeLadder = Record<string, { reached: boolean; first_event_index: number | null }>

type ApiObservation = {
  possession_id: string
  match_ref: number
  team_id: number | null
  team_name: string | null
  direction: 'for' | 'against'
  period: number | null
  start_second: number | null
  end_second: number | null
  duration_seconds: number | null
  start: { x: number | null; y: number | null }
  end: { x: number | null; y: number | null }
  launch_type: string
  termination_reason: string
  is_ambiguous: boolean
  rapid_transition: ApiRapidTransition
  outcome_tier: TransitionObservation['outcomeTier']
  outcome_ladder: ApiOutcomeLadder
  direction_ladder: TransitionObservation['directionLadder']
  score: ApiScore
  state: ApiState
  state_transition: ApiStateChange
  actual_state_transition?: boolean
  transition_classification?: string
  possession_trace: ApiAction[]
  action_evidence: ApiAction[]
}

type ApiLadderRow = {
  key: TransitionLeverageScope['attacking']['outcomeLadder'][number]['key']
  label: string
  count: number
  rate_per_opportunity: number | null
}

type ApiThresholds = {
  outcome_ladder: TransitionLeveragePayload['thresholds']['outcomeLadder']
  sequence_roles: TransitionLeveragePayload['thresholds']['sequenceRoles']
  possession_calculation_version: string
  transition_calculation_version: string
  state_boundary: string
  player_opportunity_denominator: string
}

type ApiPlayerOutcome = {
  opportunities: number
  involved_possessions: number
  involvement_rate: number | null
}

type ApiPlayerConcession = {
  opportunities: number
  defensive_action_possessions: number
  defensive_action_rate: number | null
}

type ApiDirectionStats = {
  opportunities: number
  opportunity_basis: string
  outcome_ladder: ApiLadderRow[]
  state_transitions: {
    count: number
    by_classification: Record<string, number>
    rate_per_opportunity: number | null
  }
  scores: { goals: number; normal_goals: number; own_goals: number }
}

type ApiPlayerStage = {
  actions: number
  possessions: number
  rate_per_opportunity: number | null
}

type ApiPlayer = {
  canonical_player_id: number | null
  canonical_player_name: string | null
  canonical_team_id: number
  canonical_team_name: string
  roster_role: string
  verified_on_pitch_seconds: number
  verified_on_pitch_minutes: number
  opportunities: number
  involved_possessions: number
  involvement_rate: number | null
  outcome_ladder: Record<string, ApiPlayerOutcome>
  sequence_stages: Record<TransitionSequenceRole, ApiPlayerStage>
  concession: ApiPlayerConcession
  coverage: {
    included_match_count: number
    excluded_match_count: number
    excluded_reasons: Record<string, number>
    selected_verified_seconds: number
    selected_verified_minutes: number
    confidence: string
  }
  evidence: Array<{
    match_ref: number
    possession_id: string
    state: ApiState
    state_transition: ApiStateChange
    outcome_tier: TransitionObservation['outcomeTier']
    action_stages: string[]
    action_event_indexes: number[]
    possession_trace: ApiAction[]
  }>
  evidence_truncated: boolean
}

type ApiScope = {
  scope: {
    state: string
    goal_difference: number | null
    phase: string | null
    draw_provenance: string | null
    minimum_state_age_seconds: number | null
    maximum_state_age_seconds: number | null
  }
  attacking: ApiDirectionStats
  concession: ApiDirectionStats
  concession_vulnerability?: ApiDirectionStats
  players: ApiPlayer[]
  player_involvement: ApiPlayer[]
  observations: ApiObservation[]
  coverage: {
    matches_available: number
    matches_eligible: number
    matches_included: number
    matches_excluded: number
    exclusion_reasons: Record<string, number>
    possession_count: number
    ambiguous_possession_count: number
    evidence_limit: number
    evidence_truncated: boolean
    sparse: boolean
    sparse_threshold: number
    player_participation?: {
      candidate_count: number
      verified_count: number
      excluded_count: number
      unused_count: number
      verified_seconds: number
      exclusion_reasons: Record<string, number>
    }
    reliability: TransitionLeverageCoverage['reliability']
  }
}

type ApiPayload = {
  contract_version: string
  formula_version: string
  team: { id: number; name: string }
  competition_season: { id: number; competition: string; season: string }
  selected_match_ref: number | null
  matches: Array<{
    ref: number
    kickoff_at: string
    home_team_id: number | null
    home_team_name: string | null
    away_team_id: number | null
    away_team_name: string | null
    subject_team_id: number | null
    home_score: number | null
    away_score: number | null
  }>
  state_lens: ApiStateLens
  thresholds: ApiThresholds
  selected: ApiScope
  comparison: {
    enabled: boolean
    baseline: ApiScope | null
    delta: TransitionLeveragePayload['comparison']['delta']
  }
}

function mapState(value: ApiState): TransitionState {
  return {
    state: value.state,
    goalDifference: value.goal_difference,
    phase: value.phase,
    drawProvenance: value.draw_provenance,
    stateAgeSeconds: value.state_age_seconds,
    episodeIndex: value.episode_index,
  }
}

function mapStateChange(value: ApiStateChange): TransitionStateChange {
  return {
    actual: value.actual,
    classification: value.classification,
    before: value.before,
    after: value.after,
    beforeGoalDifference: value.before_goal_difference,
    afterGoalDifference: value.after_goal_difference,
    perspective: value.perspective,
    directionalClassification: value.directional_classification,
  }
}

function mapAction(value: ApiAction): TransitionAction {
  const flags: TransitionActionFlags = {
    progressive: value.flags.progressive,
    finalThirdEntry: value.flags.final_third_entry,
    boxEntry: value.flags.box_entry,
    keyPass: value.flags.key_pass,
    shotAssist: value.flags.shot_assist,
    intentionalAssist: value.flags.intentional_assist,
    bigChance: value.flags.big_chance,
    penalty: value.flags.penalty,
    restart: value.flags.restart,
    contested: value.flags.contested,
  }
  return {
    sequence: value.sequence,
    eventIndex: value.event_index,
    matchSeconds: value.match_seconds,
    minute: value.minute,
    second: value.second,
    period: value.period,
    eventType: value.event_type,
    teamId: value.team_id,
    teamName: value.team_name,
    teamPerspective: value.team_perspective,
    playerId: value.player_id,
    playerName: value.player_name,
    location: value.location,
    destination: value.destination,
    completed: value.completed,
    isControlAction: value.is_control_action,
    isSettledDefensiveAction: value.is_settled_defensive_action,
    stage: value.stage,
    stageLabel: value.stage_label,
    role: value.role,
    roleLabel: value.role_label,
    roleEvidence: value.role_evidence,
    isTerminal: value.is_terminal,
    flags,
    gameState: mapState(value.game_state),
  }
}

function mapScore(value: ApiScore): TransitionScore {
  return {
    isGoal: value.is_goal,
    goalType: value.goal_type,
    scoringTeamId: value.scoring_team_id,
    perspective: value.perspective,
    beforeGoalDifference: value.before_goal_difference,
    afterGoalDifference: value.after_goal_difference,
    situation: value.situation,
  }
}

function mapRapidTransition(value: ApiRapidTransition): TransitionRapidTransition {
  return {
    isCounterLaunch: value.is_counter_launch,
    qualifiesForwardProgress: value.qualifies_forward_progress,
    elapsedSeconds: value.elapsed_seconds,
    forwardMetres: value.forward_metres,
    speedMps: value.speed_mps,
    outcome: value.outcome,
  }
}

function mapObservation(value: ApiObservation): TransitionObservation {
  const outcomeLadder = Object.fromEntries(
    Object.entries(value.outcome_ladder).map(([key, tier]) => [key, {
      reached: tier.reached,
      firstEventIndex: tier.first_event_index,
    }]),
  ) as TransitionObservation['outcomeLadder']
  return {
    possessionId: value.possession_id,
    matchRef: value.match_ref,
    teamId: value.team_id,
    teamName: value.team_name,
    direction: value.direction,
    period: value.period,
    startSecond: value.start_second,
    endSecond: value.end_second,
    durationSeconds: value.duration_seconds,
    start: value.start,
    end: value.end,
    launchType: value.launch_type,
    terminationReason: value.termination_reason,
    isAmbiguous: value.is_ambiguous,
    rapidTransition: mapRapidTransition(value.rapid_transition),
    outcomeTier: value.outcome_tier,
    outcomeLadder,
    directionLadder: value.direction_ladder,
    score: mapScore(value.score),
    state: mapState(value.state),
    stateTransition: mapStateChange(value.state_transition),
    actualStateTransition: value.actual_state_transition,
    transitionClassification: value.transition_classification,
    possessionTrace: value.possession_trace.map(mapAction),
    actionEvidence: value.action_evidence.map(mapAction),
  }
}

function mapPlayerEvidence(value: ApiPlayer['evidence'][number]): TransitionPlayerEvidence {
  return {
    matchRef: value.match_ref,
    possessionId: value.possession_id,
    state: mapState(value.state),
    stateTransition: mapStateChange(value.state_transition),
    outcomeTier: value.outcome_tier,
    actionStages: value.action_stages,
    actionEventIndexes: value.action_event_indexes,
    possessionTrace: value.possession_trace.map(mapAction),
  }
}

function mapPlayer(value: ApiPlayer): TransitionPlayerRow {
  const stages = Object.fromEntries(
    Object.entries(value.sequence_stages).map(([key, stage]) => [key, {
      actions: stage.actions,
      possessions: stage.possessions,
      ratePerOpportunity: stage.rate_per_opportunity,
    }]),
  ) as TransitionPlayerRow['sequenceStages']
  const outcomeLadder = Object.fromEntries(
    Object.entries(value.outcome_ladder).map(([key, outcome]) => [key, {
      opportunities: outcome.opportunities,
      involvedPossessions: outcome.involved_possessions,
      involvementRate: outcome.involvement_rate,
    }]),
  ) as TransitionPlayerRow['outcomeLadder']
  return {
    canonicalPlayerId: value.canonical_player_id,
    canonicalPlayerName: value.canonical_player_name,
    canonicalTeamId: value.canonical_team_id,
    canonicalTeamName: value.canonical_team_name,
    rosterRole: value.roster_role,
    verifiedOnPitchSeconds: value.verified_on_pitch_seconds,
    verifiedOnPitchMinutes: value.verified_on_pitch_minutes,
    opportunities: value.opportunities,
    involvedPossessions: value.involved_possessions,
    involvementRate: value.involvement_rate,
    outcomeLadder,
    sequenceStages: stages,
    concession: {
      opportunities: value.concession.opportunities,
      defensiveActionPossessions: value.concession.defensive_action_possessions,
      defensiveActionRate: value.concession.defensive_action_rate,
    },
    coverage: {
      includedMatchCount: value.coverage.included_match_count,
      excludedMatchCount: value.coverage.excluded_match_count,
      excludedReasons: value.coverage.excluded_reasons,
      selectedVerifiedSeconds: value.coverage.selected_verified_seconds,
      selectedVerifiedMinutes: value.coverage.selected_verified_minutes,
      confidence: value.coverage.confidence,
    },
    evidence: value.evidence.map(mapPlayerEvidence),
    evidenceTruncated: value.evidence_truncated,
  }
}

function mapDirection(value: ApiDirectionStats): TransitionDirectionStats {
  return {
    opportunities: value.opportunities,
    opportunityBasis: value.opportunity_basis,
    outcomeLadder: value.outcome_ladder.map(row => ({
      key: row.key,
      label: row.label,
      count: row.count,
      ratePerOpportunity: row.rate_per_opportunity,
    })),
    stateTransitions: {
      count: value.state_transitions.count,
      byClassification: value.state_transitions.by_classification,
      ratePerOpportunity: value.state_transitions.rate_per_opportunity,
    },
    scores: {
      goals: value.scores.goals,
      normalGoals: value.scores.normal_goals,
      ownGoals: value.scores.own_goals,
    },
  }
}

function mapScope(value: ApiScope): TransitionLeverageScope {
  return {
    scope: {
      state: value.scope.state,
      goalDifference: value.scope.goal_difference,
      phase: value.scope.phase,
      drawProvenance: value.scope.draw_provenance,
      minimumStateAgeSeconds: value.scope.minimum_state_age_seconds,
      maximumStateAgeSeconds: value.scope.maximum_state_age_seconds,
    },
    attacking: mapDirection(value.attacking),
    concession: mapDirection(value.concession),
    concessionVulnerability: value.concession_vulnerability ? mapDirection(value.concession_vulnerability) : undefined,
    players: value.players.map(mapPlayer),
    playerInvolvement: value.player_involvement.map(mapPlayer),
    observations: value.observations.map(mapObservation),
    coverage: {
      matchesAvailable: value.coverage.matches_available,
      matchesEligible: value.coverage.matches_eligible,
      matchesIncluded: value.coverage.matches_included,
      matchesExcluded: value.coverage.matches_excluded,
      exclusionReasons: value.coverage.exclusion_reasons,
      possessionCount: value.coverage.possession_count,
      ambiguousPossessionCount: value.coverage.ambiguous_possession_count,
      evidenceLimit: value.coverage.evidence_limit,
      evidenceTruncated: value.coverage.evidence_truncated,
      sparse: value.coverage.sparse,
      sparseThreshold: value.coverage.sparse_threshold,
      playerParticipation: value.coverage.player_participation ? {
        candidateCount: value.coverage.player_participation.candidate_count,
        verifiedCount: value.coverage.player_participation.verified_count,
        excludedCount: value.coverage.player_participation.excluded_count,
        unusedCount: value.coverage.player_participation.unused_count,
        verifiedSeconds: value.coverage.player_participation.verified_seconds,
        exclusionReasons: value.coverage.player_participation.exclusion_reasons,
      } : undefined,
      reliability: value.coverage.reliability,
    },
  }
}

export async function fetchTeamTransitionLeverage(
  teamId: number,
  competition: string,
  season: string,
  matchRef?: string | null,
  stateLens?: StateLensRequest,
): Promise<TransitionLeveragePayload> {
  const params = new URLSearchParams({ competition, season })
  if (matchRef != null) params.set('match', matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPayload>(
    `${BASE}/team-seasons/transition-leverage/${teamId}?${params.toString()}`,
  )
  return {
    contractVersion: raw.contract_version,
    formulaVersion: raw.formula_version,
    team: raw.team,
    competitionSeason: raw.competition_season,
    selectedMatchRef: raw.selected_match_ref,
    matches: raw.matches.map(match => ({
      ref: match.ref,
      kickoffAt: match.kickoff_at,
      homeTeamId: match.home_team_id,
      homeTeamName: match.home_team_name,
      awayTeamId: match.away_team_id,
      awayTeamName: match.away_team_name,
      subjectTeamId: match.subject_team_id,
      homeScore: match.home_score,
      awayScore: match.away_score,
    })),
    stateLens: mapStateLens(raw.state_lens),
    thresholds: {
      outcomeLadder: raw.thresholds.outcome_ladder,
      sequenceRoles: raw.thresholds.sequence_roles,
      possessionCalculationVersion: raw.thresholds.possession_calculation_version,
      transitionCalculationVersion: raw.thresholds.transition_calculation_version,
      stateBoundary: raw.thresholds.state_boundary,
      playerOpportunityDenominator: raw.thresholds.player_opportunity_denominator,
    },
    selected: mapScope(raw.selected),
    comparison: {
      enabled: raw.comparison.enabled,
      baseline: raw.comparison.baseline ? mapScope(raw.comparison.baseline) : null,
      delta: raw.comparison.delta,
    },
  }
}
