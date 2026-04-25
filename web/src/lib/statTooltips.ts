/**
 * Header hover copy for the stat matrix. Wording is aligned with backend
 * `derived_definitions.py` (metrics + score composites).
 */

export interface StatHeaderTooltip {
  /** Plain-English title shown at the top of the tooltip */
  fullName: string
  /** One or two short sentences */
  description: string
  /**
   * For composite scores only: underlying metrics (union across FWD/MID/DEF;
   * weights differ by position).
   */
  scoreComponents?: readonly string[]
}

/** Metric id → display name for score composition lists (matches backend labels). */
const METRIC_LABEL: Record<string, string> = {
  assists_per_90: 'Assists',
  big_chances_created_per_90: 'Big chances created',
  blocks_per_90: 'Blocks',
  buildup_share: 'Buildup share',
  chance_involvement_per_90: 'Chance involvement',
  clearances_per_90: 'Clearances',
  completed_passes_per_90: 'Completed passes',
  defensive_action_density: 'Defensive action density',
  goals_minus_npxg: 'Non-penalty goals minus NPxG',
  finishing_shrunk_delta_per_shot: 'Finishing Δ/shot (shrunk)',
  sot_rate: 'Shots on target rate',
  goals_per_90: 'Goals',
  interceptions_per_90: 'Interceptions',
  key_passes_per_90: 'Key passes',
  npxg_per_90: 'NPxG',
  npxg_per_shot: 'NPxG per shot',
  pass_accuracy: 'Pass accuracy',
  shots_per_90: 'Shots',
  successful_dribbles_per_90: 'Successful dribbles',
  successful_dribbles_percentage: 'Successful dribbles %',
  tackles_won: 'Tackles won',
  tackles_won_percentage: 'Tackles won %',
  shots_on_target: 'Shots on target',
  shots_off_target: 'Shots off target',
  aerial_duels_won: 'Aerial duels won',
  ground_duels_won: 'Ground duels won',
  ball_recoveries: 'Ball recoveries',
  fouls: 'Fouls committed',
  offsides: 'Offsides',
  tackles_per_90: 'Tackles',
  xa_per_90: 'xA',
  xa_per_key_pass: 'xA per key pass',
  xgbuildup_per_90: 'xGBuildup',
  xgchain_per_90: 'xGChain',
}

function metricLabels(ids: readonly string[]): string[] {
  return [...new Set(ids.map(id => METRIC_LABEL[id] ?? id))].sort((a, b) =>
    a.localeCompare(b),
  )
}

const SCORE_METRICS: Record<string, readonly string[]> = {
  finishing_score: [
    'finishing_shrunk_delta_per_shot',
    'sot_rate',
    'npxg_per_shot',
    'shots_per_90',
  ],
  creation_score: [
    'xa_per_90',
    'xa_per_key_pass',
    'key_passes_per_90',
    'successful_dribbles_per_90',
    'xgbuildup_per_90',
    'completed_passes_per_90',
    'pass_accuracy',
  ],
  buildup_score: [
    'xgbuildup_per_90',
    'buildup_share',
    'completed_passes_per_90',
    'successful_dribbles_per_90',
    'pass_accuracy',
  ],
  ball_winning_score: [
    'tackles_per_90',
    'interceptions_per_90',
    'blocks_per_90',
    'clearances_per_90',
  ],
  involvement_score: [
    'chance_involvement_per_90',
    'xgchain_per_90',
    'key_passes_per_90',
    'successful_dribbles_per_90',
    'completed_passes_per_90',
    'defensive_action_density',
    'xgbuildup_per_90',
  ],
}

export const STAT_HEADER_TOOLTIPS: Record<string, StatHeaderTooltip> = {
  canonical_player_name: {
    fullName: 'Player',
    description:
      'Display name for the row. The subtitle shows primary position group and club.',
  },
  canonical_team_name: {
    fullName: 'Club',
    description: 'Club badge for the player’s side in the selected competition.',
  },
  minutes: {
    fullName: 'Minutes played',
    description: 'Total minutes played. Drives rate denominators and heatmap eligibility.',
  },
  finishing_score: {
    fullName: 'Finishing score',
    description:
      'Shrunk per-shot NPG−NPxG vs peers, on-target rate, NPxG per shot (guardrail), and a small shot-volume term. Percentile within position.',
    scoreComponents: metricLabels(SCORE_METRICS.finishing_score),
  },
  creation_score: {
    fullName: 'Creation score',
    description:
      'Chance creation from xA, xA per key pass, and key-pass volume; dribbling carries; defenders add xGBuildup and passing volume.',
    scoreComponents: metricLabels(SCORE_METRICS.creation_score),
  },
  buildup_score: {
    fullName: 'Buildup score',
    description:
      'Earlier-phase work via xGBuildup rate and buildup share of chain credit, plus passes and dribbles (forwards) or pass accuracy.',
    scoreComponents: metricLabels(SCORE_METRICS.buildup_score),
  },
  ball_winning_score: {
    fullName: 'Ball winning score',
    description:
      'Defensive activity from tackles, interceptions, blocks, and clearances (raw counts, not possession-adjusted).',
    scoreComponents: metricLabels(SCORE_METRICS.ball_winning_score),
  },
  involvement_score: {
    fullName: 'Involvement score',
    description:
      'Presence in chance-ending actions and xGChain; forwards omit shots as a separate column because they are inside chance involvement.',
    scoreComponents: metricLabels(SCORE_METRICS.involvement_score),
  },
  tackles_per_90: {
    fullName: 'Tackles',
    description: 'Tackle attempts won or counted. Not possession-adjusted, so team context still matters.',
  },
  interceptions_per_90: {
    fullName: 'Interceptions',
    description: 'Passes or touches intercepted. Reflects reading of the game and defensive workload.',
  },
  clearances_per_90: {
    fullName: 'Clearances',
    description: 'Defensive clearances. Often reflects team defensive pressure as much as individual style.',
  },
  blocks_per_90: {
    fullName: 'Blocks',
    description: 'Outfield blocks (e.g. shots or crosses). Tied to how often opponents fire attempts.',
  },
  defensive_action_density: {
    fullName: 'Defensive action density',
    description:
      'Combined tackles, interceptions, clearances, and blocks. A broad activity proxy, not a possession model.',
  },
  completed_passes_per_90: {
    fullName: 'Completed passes',
    description: 'Completed passes as a simple proxy for on-ball circulation volume.',
  },
  key_passes_per_90: {
    fullName: 'Key passes',
    description: 'Passes that directly lead to a shot. Does not, by itself, value the resulting shot.',
  },
  big_chances_created_per_90: {
    fullName: 'Big chances created',
    description: 'High-value chances created for teammates, using provider “big chance” labels.',
  },
  pass_accuracy: {
    fullName: 'Pass accuracy',
    description: 'Share of passes completed. Safer roles can inflate this, so read it with pass volume.',
  },
  xa_per_key_pass: {
    fullName: 'Expected assists per key pass',
    description: 'Average chance quality generated each time the player records a key pass.',
  },
  buildup_share: {
    fullName: 'Buildup share',
    description: 'Share of xGChain that comes from xGBuildup—how much involvement is earlier-phase vs chance-ending.',
  },
  successful_dribbles_per_90: {
    fullName: 'Successful dribbles',
    description: 'Successful take-ons. Measures progressive carrying, not end-product on its own.',
  },
  successful_dribbles_percentage: {
    fullName: 'Successful dribbles %',
    description: 'Share of attempted dribbles completed successfully.',
  },
  tackles_won: {
    fullName: 'Tackles won',
    description: 'Total successful tackles won.',
  },
  tackles_won_per90: {
    fullName: 'Tackles won',
    description: 'Successful tackles won, with /90 and Season views available for comparison.',
  },
  tackles_won_percentage: {
    fullName: 'Tackles won %',
    description: 'Share of tackle attempts won.',
  },
  shots_on_target: {
    fullName: 'Shots on target',
    description: 'Shots that hit the target.',
  },
  shots_on_target_per90: {
    fullName: 'Shots on target',
    description: 'Shots that hit the target, with /90 and Season views available for comparison.',
  },
  shots_off_target: {
    fullName: 'Shots off target',
    description: 'Shots that missed the target.',
  },
  shots_off_target_per90: {
    fullName: 'Shots off target',
    description: 'Shots that missed the target, with /90 and Season views available for comparison.',
  },
  aerial_duels_won: {
    fullName: 'Aerial duels won',
    description: 'Total aerial duels won.',
  },
  aerial_duels_won_per90: {
    fullName: 'Aerial duels won',
    description: 'Aerial duels won, with /90 and Season views available for comparison.',
  },
  ground_duels_won: {
    fullName: 'Ground duels won',
    description: 'Total ground duels won.',
  },
  ground_duels_won_per90: {
    fullName: 'Ground duels won',
    description: 'Ground duels won, with /90 and Season views available for comparison.',
  },
  ball_recoveries: {
    fullName: 'Ball recoveries',
    description: 'Total possession recoveries.',
  },
  ball_recoveries_per90: {
    fullName: 'Ball recoveries',
    description: 'Possession recoveries, with /90 and Season views available for comparison.',
  },
  fouls: {
    fullName: 'Fouls committed',
    description: 'Total fouls committed.',
  },
  fouls_per90: {
    fullName: 'Fouls committed',
    description: 'Fouls committed, with /90 and Season views available for comparison.',
  },
  offsides: {
    fullName: 'Offsides',
    description: 'Total offside calls.',
  },
  offsides_per90: {
    fullName: 'Offsides',
    description: 'Offside calls, with /90 and Season views available for comparison.',
  },
  xgbuildup: {
    fullName: 'xGBuildup',
    description:
      'Buildup-phase xG contribution excluding the shot and final key pass in the possession chain.',
  },
  xgbuildup_per_90: {
    fullName: 'xGBuildup',
    description: 'Earlier-phase attacking contribution from possessions excluding the final shot or key pass.',
  },
  xgchain: {
    fullName: 'xGChain',
    description: 'Total xG from possessions the player was involved in, including indirect involvement.',
  },
  xgchain_per_90: {
    fullName: 'xGChain',
    description: 'Involvement in chance-ending possessions, including supportive links in the move.',
  },
  goals_per_90: {
    fullName: 'Goals',
    description: 'Goals scored (provider definition).',
  },
  assists_per_90: {
    fullName: 'Assists',
    description: 'Assists (provider definition).',
  },
  npxg: {
    fullName: 'Non-penalty expected goals',
    description:
      'Non-penalty expected goals accumulated. Excludes penalties; not a finishing skill label by itself.',
  },
  npxg_per_90: {
    fullName: 'Non-penalty expected goals (NPxG)',
    description: 'Shot threat excluding penalties. Useful for comparing profiles independent of minutes played.',
  },
  xa: {
    fullName: 'Expected assists',
    description: 'Expected assists from chances created for teammates.',
  },
  xa_per_90: {
    fullName: 'Expected assists (xA)',
    description: 'Creative output based on the quality of chances created for teammates.',
  },
  shots_per_90: {
    fullName: 'Shots',
    description: 'Shot volume. Best read together with shot quality (e.g. NPxG per shot).',
  },
  npxg_per_shot: {
    fullName: 'NPxG per shot',
    description: 'Average non-penalty shot quality per attempt. Null when the player has no shots in the sample.',
  },
  goals_minus_xg: {
    fullName: 'Goals minus expected goals',
    description: 'Finishing delta including penalties in goals and xG. Can swing with variance year to year.',
  },
  goals_minus_npxg: {
    fullName: 'Non-penalty goals minus NPxG',
    description: 'Finishing delta on non-penalty goals vs non-penalty xG. Cleaner than goals minus xG for outfielders.',
  },
  chance_involvement_per_90: {
    fullName: 'Chance involvement',
    description:
      'Descriptive involvement from shots, key passes, and big chances created—not a full xG model.',
  },

  // ── Goalkeepers ────────────────────────────────────────────────────────────
  appearances: {
    fullName: 'Appearances',
    description: 'Matches the goalkeeper appeared in, as recorded by SofaScore.',
  },
  rating: {
    fullName: 'Rating',
    description:
      'SofaScore season rating. Percentiles are ranked within goalkeepers only, not across outfielders.',
  },
  saves_per_90: {
    fullName: 'Saves',
    description:
      'Saves made. Volume depends heavily on how often the goalkeeper is tested, so read with team defensive context.',
  },
  saves: {
    fullName: 'Saves (total)',
    description: 'Total saves recorded in the sample.',
  },
  clean_sheet_rate: {
    fullName: 'Clean sheet rate',
    description:
      'Clean sheets as a share of goalkeeper appearances. Heavily team-dependent; short samples swing.',
  },
  clean_sheets: {
    fullName: 'Clean sheets',
    description: 'Matches the goalkeeper completed without conceding, using SofaScore’s definition.',
  },
  clean_sheets_per90: {
    fullName: 'Clean sheets',
    description: 'Clean sheet volume per 90 minutes. Useful alongside Clean sheet rate.',
  },
  penalty_saves: {
    fullName: 'Penalty saves',
    description: 'Penalties saved in the sample. Counts are low for most goalkeepers.',
  },
  penalty_saves_per90: {
    fullName: 'Penalty saves per 90',
    description: 'Penalty saves per 90 minutes. Sample sizes are tiny — treat with caution.',
  },
  saved_shots_inside_box_per_90: {
    fullName: 'Saves from inside the box',
    description:
      'Saves from shots taken inside the penalty area. Reflects the shot locations faced more than the quality of the save.',
  },
  saved_shots_inside_box: {
    fullName: 'Saves from inside the box (total)',
    description: 'Total saves from shots taken inside the penalty area.',
  },
  runs_out_per_90: {
    fullName: 'Runs out',
    description:
      'Defensive runs off the line per 90. Sweeper-keeper style and team line height both drive volume.',
  },
  runs_out: {
    fullName: 'Runs out (total)',
    description: 'Total defensive runs out recorded in the sample.',
  },
  accurate_long_balls_per_90: {
    fullName: 'Accurate long balls',
    description:
      'Accurate long balls per 90 minutes. A distribution style marker for goalkeepers who launch.',
  },
}

export const GROUP_HEADER_TOOLTIPS: Record<string, StatHeaderTooltip> = {
  meta: {
    fullName: 'Player metadata',
    description: 'Name, club, and minutes for each row. Minutes drive rate denominators and heatmap eligibility.',
  },
  scores: {
    fullName: 'Composite scores',
    description:
      'Single-number summaries (percentile-style within position) built from the underlying metrics in each column’s tooltip.',
  },
  defending: {
    fullName: 'Defending',
    description: 'Out-of-possession volume and density stats, mostly from defensive action counts.',
  },
  passing_creative: {
    fullName: 'Passing and creativity',
    description: 'Chance creation, passing volume and accuracy, buildup style, and progressive carrying.',
  },
  attacking: {
    fullName: 'Attacking output',
    description:
      'Shot threat, creation, goals and assists, and finishing deltas. Use /90 | Season to switch rate vs season totals.',
  },
  shot_stopping: {
    fullName: 'Shot stopping',
    description:
      'Saves, clean sheets, penalty stops, and save location. Values switch between /90 and season totals with the rate toggle; percentiles are within the goalkeeper cohort.',
  },
  sweeper: {
    fullName: 'Sweeper',
    description: 'Defensive activity off the goal line. Volume is shaped by team line height and style.',
  },
  distribution: {
    fullName: 'Distribution',
    description: 'Passing volume, completion rate, and long-ball output from the goalkeeper.',
  },
}

export function getStatHeaderTooltip(columnId: string): StatHeaderTooltip | undefined {
  return STAT_HEADER_TOOLTIPS[columnId]
}

export function getGroupHeaderTooltip(groupColumnId: string): StatHeaderTooltip | undefined {
  if (!groupColumnId.startsWith('group_')) return undefined
  return GROUP_HEADER_TOOLTIPS[groupColumnId.slice('group_'.length)]
}
