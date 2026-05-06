export type PositionGroup = 'FWD' | 'MID' | 'DEF' | 'GK' | 'UNK'

export interface ScoreAvailabilityDetail {
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

export interface SearchScopeMembership {
  competition: string
  season: string
  competition_season_id: number
}

export interface SearchPlayerMembership extends SearchScopeMembership {
  canonical_team_id: number | null
  canonical_team_name: string | null
  position_group: PositionGroup
  minutes: number
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

export interface Eligibility {
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
  scores: Record<string, number | null>
  score_raw: Record<string, number | null>
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

export interface ScoreDefinition {
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
}

/** `GET /player-seasons/derived-stats/:id` — player row + optional grouped sections + meta. */
export interface PlayerDetailResponse extends PlayerRow {
  meta?: StatMeta
  sections?: ProfileSectionsPayload
}

export interface ProfileSectionsPayload {
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

export interface GalaxyArchetype {
  cluster_id: number
  label: string
  color: string
}

export interface GalaxyPoint {
  canonical_player_id: number
  canonical_player_name: string
  canonical_team_id: number | null
  canonical_team_name: string | null
  position_group: PositionGroup
  minutes: number
  cluster_id: number
  cluster_label: string
  cluster_color: string
  x: number
  y: number
  z: number
}

export interface GalaxyEdge {
  from_player_id: number
  to_player_id: number
  to_player_name: string
  similarity: number
  rank: number
}

export interface GalaxyResponse {
  competition_season: number
  competition_code: string
  season_label: string
  count: number
  archetypes: GalaxyArchetype[]
  points: GalaxyPoint[]
  players: Array<{
    canonical_player_id: number
    canonical_player_name: string
  }>
  selected_player: GalaxyPoint | null
  edges: GalaxyEdge[]
}

export interface GalaxySimilarResponse {
  selected_player: GalaxyPoint
  edges: GalaxyEdge[]
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

export interface RegressionLabSample {
  cohort_rows: number
  usable_rows: number
  dropped_rows: number
}

export interface RegressionLabFitMetrics {
  r2_cv: number
  mae_cv: number
  rmse_cv: number
  r2_train: number
}

export interface RegressionLabCoefficient {
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
