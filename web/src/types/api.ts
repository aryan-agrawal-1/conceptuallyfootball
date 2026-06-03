export type PositionGroup = 'FWD' | 'MID' | 'DEF' | 'GK' | 'UNK'

interface ScoreAvailabilityDetail {
  available?: boolean
  positions?: Partial<Record<PositionGroup, boolean>>
  missing_components?: Partial<Record<PositionGroup, string[]>>
  low_coverage_components?: Partial<Record<PositionGroup, Record<string, number>>>
}

export interface MetricAvailability {
  available_metrics?: string[]
  unavailable_metrics?: string[]
  ui_available_metrics?: string[]
  default_metrics?: string[]
  low_coverage_metrics?: string[]
  scores?: Record<string, ScoreAvailabilityDetail>
  available_scores?: string[]
  unavailable_scores?: string[]
  coverage_by_position?: Partial<Record<PositionGroup, Record<string, number>>>
  metric_thresholds?: Record<string, number>
}

export interface CompetitionSeasonOption {
  label: string
  competition_season_id: number
  player_data_mode?: string
  has_understat?: boolean
  has_sofascore?: boolean
  metric_availability?: MetricAvailability
}

export interface CompetitionCatalogEntry {
  code: string
  name: string
  seasons: CompetitionSeasonOption[]
}

export interface CompetitionSeasonsCatalogResponse {
  competitions: CompetitionCatalogEntry[]
}

interface SearchScopeMembership {
  competition: string
  season: string
  competition_season_id: number
}

export interface SearchPlayerMembership extends SearchScopeMembership {
  canonical_team_id: number | null
  canonical_team_name: string | null
  position_group: PositionGroup
  minutes: number | null
}

export interface SearchTeamMembership extends SearchScopeMembership {
  rank: number | null
  matches: number | null
}

export interface SearchPlayerEntity {
  kind: 'player'
  canonical_player_id: number
  canonical_player_name: string
  total_minutes: number
  memberships: SearchPlayerMembership[]
}

export interface SearchTeamEntity {
  kind: 'team'
  canonical_team_id: number
  canonical_team_name: string
  total_matches: number
  memberships: SearchTeamMembership[]
}

export interface SearchEntitiesResponse {
  players: SearchPlayerEntity[]
  teams: SearchTeamEntity[]
}

interface Eligibility {
  percentiles_eligible: boolean
  percentiles_ineligibility_reason: string | null
  scores_eligible: boolean
  scores_ineligibility_reason: string | null
}

/** Additional clubs from the same league-season aggregate (multi-club Understat row). */
export interface SecondaryTeamBadge {
  canonical_team_id: number
  canonical_team_name: string
}

export interface PlayerRow {
  canonical_player_id: number
  canonical_player_name: string
  canonical_team_id: number | null
  canonical_team_name: string | null
  /** Present when the player appeared for more than one club in this competition season. */
  secondary_teams?: SecondaryTeamBadge[]
  competition_season: number
  competition_code: string
  season_label: string
  position_group: PositionGroup
  native_position: string | null
  minutes: number
  /** Goalkeeper matrix only (Sofascore appearances). */
  appearances?: number | null
  formula_version: string
  derived_run_id: number | null
  eligibility: Eligibility
  metrics: Record<string, number | null>
  percentiles: Record<string, number | null>
  scope_percentiles?: Record<string, number | null>
  scope_percentile_context?: ScopePercentileContext
  scores: Record<string, number | null>
  score_raw: Record<string, number | null>
}

interface ScopePercentileContext {
  competition_code: string
  season_label: string
  competition_season_ids?: number[]
}

export interface MetricDefinition {
  label: string
  group: string
  unit: 'total' | 'per90' | 'delta' | 'ratio' | 'percentage' | 'share'
  sources_used: string[]
  description: string
  caveat: string
  availability_note?: string
}

interface ScoreDefinition {
  label: string
  description: string
  group: string
  sources_used: string[]
}

export interface StatMeta {
  formula_version: string
  minimum_eligible_minutes: number
  metric_groups: Record<string, string>
  metrics: Record<string, MetricDefinition>
  scores?: Record<string, ScoreDefinition>
}

export interface MatrixResponse {
  competition_season: number
  competition_code: string
  season_label: string
  /** Present on goalkeeper matrix responses. */
  matrix_kind?: 'gk' | 'outfield'
  count: number
  results: PlayerRow[]
  meta?: StatMeta
  scope_percentile_context?: ScopePercentileContext
}

/** `GET /player-seasons/derived-stats/:id` — player row + optional grouped sections + meta. */
export interface PlayerDetailResponse extends PlayerRow {
  meta?: StatMeta
  sections?: ProfileSectionsPayload
}

interface ProfileSectionsPayload {
  [groupKey: string]: {
    label: string
    metrics: Array<{
      key: string
      label: string
      value: number | null
      percentile: number | null
    }>
  }
}

export interface MatrixFilters {
  competition: string
  season: string
  teams?: string[]
  position_group?: string
  min_minutes: number
}

interface GalaxyArchetype {
  archetype_key: string
  cluster_id: number
  position_group?: PositionGroup
  label: string
  color: string
  size?: number
  feature_signature?: Record<string, unknown>
  representative_players?: Array<Record<string, unknown>>
}

export interface GalaxyPoint {
  galaxy_player_id: string
  canonical_player_id: number
  canonical_player_name: string
  canonical_team_id: number | null
  canonical_team_name: string | null
  competition_season_id: number
  competition_code: string
  season_label: string
  position_group: PositionGroup
  native_position?: string | null
  minutes: number
  archetype_key: string
  archetype_label: string
  archetype_color: string
  primary_archetype_key: string
  primary_archetype_label: string
  primary_archetype_confidence: number | null
  secondary_archetype_key: string
  secondary_archetype_label: string
  secondary_archetype_confidence: number | null
  archetype_margin: number | null
  archetype_diagnostics?: Record<string, unknown>
  cluster_id: number
  cluster_label: string
  cluster_color: string
  x: number
  y: number
  z: number
}

export interface GalaxyEdge {
  from_galaxy_player_id: string
  to_galaxy_player_id: string
  from_player_id: number
  to_player_id: number
  to_player_name: string
  to_team_name?: string | null
  to_competition_code?: string
  distance?: number
  base_distance?: number
  position_multiplier?: number
  candidate_percentile_score?: number
  absolute_fit_score?: number
  profile_match_score: number
  weak_absolute_fit?: boolean
  match_context?: string
  explanation?: {
    shared_traits?: string[]
    differences?: string[]
    top_feature_deltas?: Array<Record<string, unknown>>
  }
  similarity: number
  rank: number
}

interface GalaxyModelMeta {
  snapshot_id: number
  model_version: string
  scope_code: string
  season_label: string
  feature_profile: string
  min_minutes: number
  default_min_minutes: number
  requested_min_minutes?: number
  effective_min_minutes?: number
  top_k: number
  feature_names: string[]
  feature_weights: Record<string, number>
  feature_groups: Record<string, string>
  included_competition_season_ids: number[]
  excluded_competitions: Array<Record<string, unknown>>
  diagnostics?: Record<string, unknown>
}

export interface GalaxyResponse {
  competition_season: number
  competition_code: string
  season_label: string
  count: number
  model_meta: GalaxyModelMeta
  archetypes: GalaxyArchetype[]
  points: GalaxyPoint[]
  players: Array<{
    galaxy_player_id: string
    canonical_player_id: number
    canonical_player_name: string
    canonical_team_name?: string | null
    competition_code?: string
    position_group?: PositionGroup
    minutes?: number
  }>
  selected_player: GalaxyPoint | null
  edges: GalaxyEdge[]
}

export interface GalaxySimilarResponse {
  selected_player: GalaxyPoint
  edges: GalaxyEdge[]
  model_meta: GalaxyModelMeta
}

/** Team stat definitions from `include=meta` on team detail. */
export interface TeamStatMeta {
  stat_groups: Record<string, string>
  stats: Record<string, { label: string; group: string }>
  ranked_keys: string[]
}

export interface TeamDetailResponse {
  canonical_team_id: number
  canonical_team_name: string
  competition_season: number
  competition_code: string
  season_label: string
  stats: Record<string, number | null>
  /** League rank on season totals (same ordering as raw `stats`). */
  ranks: Record<string, number | null>
  /** League rank on per-match rates (volume ÷ matches; % stats unchanged). */
  ranks_per_match: Record<string, number | null>
  sections: Record<
    string,
    {
      label: string
      metrics: Array<{
        key: string
        label: string
        value: number | null
        rank: number | null
        rank_per_match: number | null
      }>
    }
  >
  meta?: TeamStatMeta
}

export interface TeamSeasonRow {
  canonical_team_id: number
  canonical_team_name: string
  competition_season: number
  competition_code: string
  season_label: string
  stats: Record<string, number | null>
  /** League rank on season totals (same ordering as raw `stats`). */
  ranks: Record<string, number | null>
  /** League rank on per-match rates (volume ÷ matches; % stats unchanged). */
  ranks_per_match: Record<string, number | null>
}

export interface TeamMatrixResponse {
  competition_season: number
  competition_code: string
  season_label: string
  count: number
  results: TeamSeasonRow[]
  meta?: TeamStatMeta
}

export interface TeamSquadPlayer {
  canonical_player_id: number
  canonical_player_name: string
  position_group: PositionGroup
  native_position: string | null
  minutes: number | null
  appearances: number | null
}

export interface TeamSquadResponse {
  competition_season: number
  competition_code: string
  season_label: string
  canonical_team_id: number
  results: TeamSquadPlayer[]
}

interface RegressionLabSample {
  cohort_rows: number
  usable_rows: number
  dropped_rows: number
}

interface RegressionLabFitMetrics {
  r2_cv: number
  mae_cv: number
  rmse_cv: number
  r2_train: number
}

interface RegressionLabCoefficient {
  key: string
  label: string
  coefficient_std: number
}

export interface RegressionLabPredictionRow {
  canonical_player_id: number
  canonical_player_name: string
  canonical_team_name: string | null
  actual: number
  predicted_oof: number
  residual: number
}

export interface RegressionLabFitResponse {
  model: string
  alpha: number
  position_group: string
  competition_code: string
  season_label: string
  sample: RegressionLabSample
  fit: RegressionLabFitMetrics
  coefficients: RegressionLabCoefficient[]
  intercept: number
  predictions: RegressionLabPredictionRow[]
  warnings: string[]
}
