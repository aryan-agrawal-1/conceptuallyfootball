from __future__ import annotations

FORMULA_VERSION = "v3"
MIN_ELIGIBLE_MINUTES = 450
CORE_METRIC_MIN_COVERAGE = 0.8
STYLE_METRIC_MIN_COVERAGE = 0.7
SCORE_COMPONENT_MIN_COVERAGE = 0.9
ELIGIBLE_OUTFIELD_POSITIONS = ("DEF", "MID", "FWD")
WINSORIZE_LOWER = 0.05
WINSORIZE_UPPER = 0.95

METRIC_GROUPS = {
    "attack": "Attack",
    "volume": "Volume",
    "efficiency_style": "Efficiency & Style",
    "defending": "Defending",
}

METRIC_DEFINITIONS: dict[str, dict] = {
    "npxg": {
        "label": "NPxG",
        "group": "attack",
        "unit": "total",
        "sources_used": ["understat"],
        "description": "Non-penalty expected goals. Higher values mean the player accumulated more non-penalty shot value over the season.",
        "caveat": "Excludes penalties and does not measure finishing by itself.",
    },
    "npxg_per_90": {
        "label": "NPxG/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Non-penalty expected goals per 90 minutes. Useful for comparing shot threat independent of playing time.",
        "caveat": "Sensitive to small samples below the minutes threshold.",
    },
    "xa": {
        "label": "xA",
        "group": "attack",
        "unit": "total",
        "sources_used": ["understat"],
        "description": "Expected assists. Measures the total value of chances a player created for teammates.",
        "caveat": "Depends on shot quality after the pass, not whether teammates finished the chance.",
    },
    "xa_per_90": {
        "label": "xA/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Expected assists per 90 minutes. A strong baseline measure of creative output.",
        "caveat": "More stable over larger minute totals.",
    },
    "xgchain": {
        "label": "xGChain",
        "group": "attack",
        "unit": "total",
        "sources_used": ["understat"],
        "description": "Total xG from possessions the player was involved in. Highlights overall attacking involvement.",
        "caveat": "Credits every player in the move, so it should not be read as a final-third-only stat.",
    },
    "xgchain_per_90": {
        "label": "xGChain/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Attacking involvement in chance-ending possessions per 90 minutes.",
        "caveat": "Can reward supportive involvement as well as direct chance creation.",
    },
    "xgbuildup": {
        "label": "xGBuildup",
        "group": "attack",
        "unit": "total",
        "sources_used": ["understat"],
        "description": "Total buildup contribution excluding the shot and key pass actions in the possession.",
        "caveat": "Designed to surface earlier-phase contributors rather than final action takers.",
    },
    "xgbuildup_per_90": {
        "label": "xGBuildup/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Earlier-phase attacking contribution per 90 minutes.",
        "caveat": "Best interpreted alongside xGChain and buildup share.",
    },
    "shots_per_90": {
        "label": "Shots/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Shot volume per 90 minutes.",
        "caveat": "Shot count is less informative than shot quality on its own.",
    },
    "goals_per_90": {
        "label": "Goals/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Goals scored per 90 minutes in the sample.",
        "caveat": "Includes all goal types recorded in the underlying feed.",
    },
    "assists_per_90": {
        "label": "Assists/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Assists per 90 minutes in the sample.",
        "caveat": "Uses provider assist definitions, which can differ across sources.",
    },
    "key_passes_per_90": {
        "label": "Key Passes/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["understat"],
        "description": "Passes leading directly to a shot per 90 minutes.",
        "caveat": "Does not capture the quality of the resulting shot.",
    },
    "big_chances_created_per_90": {
        "label": "Big Chances Created/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "High-value chance creation rate per 90 minutes.",
        "caveat": "Uses provider-defined big chance labels rather than a custom model.",
    },
    "successful_dribbles_per_90": {
        "label": "Successful Dribbles/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Successful take-ons per 90 minutes.",
        "caveat": "Measures beat-your-man activity, not downstream chance value.",
    },
    "completed_passes_per_90": {
        "label": "Completed Passes/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Completed passes per 90 minutes. A clean proxy for circulation involvement.",
        "caveat": "Does not represent total attempts or passing risk on its own.",
    },
    "goals_minus_xg": {
        "label": "Goals - xG",
        "group": "efficiency_style",
        "unit": "delta",
        "sources_used": ["understat"],
        "description": "Goals minus expected goals. Positive values suggest finishing overperformance across all goals.",
        "caveat": "This can swing with luck and often regresses over time.",
    },
    "goals_minus_npxg": {
        "label": "NPG - NPxG",
        "group": "efficiency_style",
        "unit": "delta",
        "sources_used": ["understat"],
        "description": "Non-penalty goals minus non-penalty xG. A cleaner finishing delta than goals minus xG.",
        "caveat": "Still noisy over smaller samples.",
    },
    "finishing_shrunk_delta_per_shot": {
        "label": "Finishing Δ/shot (shrunk)",
        "group": "efficiency_style",
        "unit": "ratio",
        "sources_used": ["understat"],
        "description": "(NPG − NPxG) per shot, multiplied by shot-count reliability (shots / (shots + 35)). Core input to finishing score.",
        "caveat": "Null without shots. Shrinkage dampens small-sample noise.",
        "availability_note": "Null when the player has no recorded shots.",
    },
    "sot_rate": {
        "label": "Shots on target rate",
        "group": "efficiency_style",
        "unit": "ratio",
        "sources_used": ["sofascore", "understat"],
        "description": "Share of recorded attempts that were on target: on-target ÷ (on-target + off-target).",
        "caveat": "Provider definitions; when on/off split is missing but on-target and total shots exist, falls back to on-target ÷ total shots.",
        "availability_note": "Null when neither the split nor a fallback can be computed.",
    },
    "npxg_per_shot": {
        "label": "NPxG/Shot",
        "group": "efficiency_style",
        "unit": "ratio",
        "sources_used": ["understat"],
        "description": "Average non-penalty shot quality. Higher means the player tends to shoot from better positions.",
        "caveat": "Requires at least one shot and does not measure finishing skill on its own.",
        "availability_note": "Null when the player has no recorded shots.",
    },
    "xa_per_key_pass": {
        "label": "xA/Key Pass",
        "group": "efficiency_style",
        "unit": "ratio",
        "sources_used": ["understat"],
        "description": "Average chance quality generated per key pass.",
        "caveat": "Rewards creators whose passes lead to better shots, not just more shots.",
        "availability_note": "Null when the player has no recorded key passes.",
    },
    "buildup_share": {
        "label": "Buildup Share",
        "group": "efficiency_style",
        "unit": "share",
        "sources_used": ["understat"],
        "description": "Share of xGChain that comes from xGBuildup. Higher values suggest earlier-phase involvement.",
        "caveat": "This is a style proxy, not a full possession-value model.",
        "availability_note": "Null when xGChain is zero.",
    },
    "chance_involvement_per_90": {
        "label": "Chance Involvement/90",
        "group": "efficiency_style",
        "unit": "per90",
        "sources_used": ["understat", "sofascore"],
        "description": "Direct scoring action volume per 90, built from shots, key passes, and big chances created.",
        "caveat": "A descriptive involvement count, not a value-based expected-goal model.",
    },
    "pass_accuracy": {
        "label": "Pass Accuracy",
        "group": "efficiency_style",
        "unit": "percentage",
        "sources_used": ["sofascore"],
        "description": "Pass completion percentage.",
        "caveat": "Safer passing can inflate accuracy, so it should be read alongside completed passes per 90.",
    },
    "tackles_per_90": {
        "label": "Tackles/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Tackles per 90 minutes.",
        "caveat": "Not possession-adjusted, so team context still matters.",
    },
    "interceptions_per_90": {
        "label": "Interceptions/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Interceptions per 90 minutes.",
        "caveat": "Not possession-adjusted, so team context still matters.",
    },
    "clearances_per_90": {
        "label": "Clearances/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Clearances per 90 minutes.",
        "caveat": "Often reflects team defensive environment as much as individual quality.",
    },
    "blocks_per_90": {
        "label": "Blocks/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Outfielder blocks per 90 minutes.",
        "caveat": "Depends heavily on opponent shot and cross volume.",
    },
    "defensive_action_density": {
        "label": "Defensive Action Density",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Combined tackles, interceptions, clearances, and blocks per 90.",
        "caveat": "A broad activity proxy, not a possession-adjusted defending model.",
    },
    "tackles_won": {
        "label": "Tackles Won",
        "group": "defending",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total successful tackles.",
        "caveat": "More context-rich when paired with tackles won percentage.",
    },
    "tackles_won_percentage": {
        "label": "Tackles Won %",
        "group": "defending",
        "unit": "percentage",
        "sources_used": ["sofascore"],
        "description": "Share of tackle attempts that were won.",
        "caveat": "Can vary with role and tackle difficulty.",
    },
    "aerial_duels_won": {
        "label": "Aerial Duels Won",
        "group": "defending",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total aerial duels won.",
        "caveat": "Volume depends on role and team style.",
    },
    "ground_duels_won": {
        "label": "Ground Duels Won",
        "group": "defending",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total ground duels won.",
        "caveat": "Includes different duel contexts, so compare within positions.",
    },
    "ball_recoveries": {
        "label": "Ball Recoveries",
        "group": "defending",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Number of times the player recovered possession.",
        "caveat": "Team shape and pressing behavior affect totals.",
    },
    "shots_on_target": {
        "label": "Shots On Target",
        "group": "volume",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total shots that hit the target.",
        "caveat": "Should be read alongside shot volume and shot quality metrics.",
    },
    "shots_off_target": {
        "label": "Shots Off Target",
        "group": "volume",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total shots that missed the target.",
        "caveat": "Higher values can come from both high volume and poor accuracy.",
    },
    "successful_dribbles_percentage": {
        "label": "Dribble Success %",
        "group": "efficiency_style",
        "unit": "percentage",
        "sources_used": ["sofascore"],
        "description": "Share of attempted dribbles completed successfully.",
        "caveat": "More stable when interpreted with dribble attempt volume.",
    },
    "fouls": {
        "label": "Fouls",
        "group": "defending",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total fouls committed.",
        "caveat": "Can reflect role/tactical fouling as much as individual discipline.",
    },
    "offsides": {
        "label": "Offsides",
        "group": "attack",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total offside calls.",
        "caveat": "Contextual and role-dependent; best used as a style indicator.",
    },
    "accurate_crosses_per_90": {
        "label": "Accurate Crosses/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Accurate crosses completed per 90 minutes.",
        "caveat": "Role-sensitive and generally higher for wide players.",
    },
    "accurate_long_balls_per_90": {
        "label": "Accurate Long Balls/90",
        "group": "volume",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Accurate long balls completed per 90 minutes.",
        "caveat": "Can reflect both individual skill and team directness.",
    },
    "ball_recoveries_per_90": {
        "label": "Ball Recoveries/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Possession recoveries per 90 minutes.",
        "caveat": "Influenced by team pressing behavior and match state.",
    },
    "ground_duels_won_per_90": {
        "label": "Ground Duels Won/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Ground duels won per 90 minutes.",
        "caveat": "Role and duel context affect opportunity volume.",
    },
    "aerial_duels_won_per_90": {
        "label": "Aerial Duels Won/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Aerial duels won per 90 minutes.",
        "caveat": "Naturally favors players involved in aerial contests.",
    },
    "fouls_per_90": {
        "label": "Fouls/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Fouls committed per 90 minutes.",
        "caveat": "Can include tactical fouls and role-dependent behaviors.",
    },
    "errors_lead_to_goal_per_90": {
        "label": "Errors Leading to Goal/90",
        "group": "defending",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Errors directly leading to goals per 90 minutes.",
        "caveat": "Rare-event metric that can be noisy in smaller samples.",
    },
    "offsides_per_90": {
        "label": "Offsides/90",
        "group": "attack",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Offside calls per 90 minutes.",
        "caveat": "Style and role dependent; often highest for high-line forwards.",
    },
    "kp_share_per90": {
        "label": "Key Pass Share",
        "group": "efficiency_style",
        "unit": "ratio",
        "sources_used": ["sofascore"],
        "description": "Share of total pass volume represented by key passes.",
        "caveat": "Can be volatile for very low pass-volume players.",
        "availability_note": "Null when total passes is zero or missing.",
    },
    "inaccurate_pass_rate": {
        "label": "Inaccurate Pass Rate",
        "group": "efficiency_style",
        "unit": "ratio",
        "sources_used": ["sofascore"],
        "description": "Share of passes that were inaccurate.",
        "caveat": "Riskier pass profiles can raise this despite positive progression value.",
        "availability_note": "Null when total passes is zero or missing.",
    },
}

METRIC_FIELDS = list(METRIC_DEFINITIONS.keys())
PERCENTILE_FIELDS = [f"{metric}_percentile" for metric in METRIC_FIELDS]
STYLE_PROXY_METRICS = {
    "npxg_per_shot",
    "xa_per_key_pass",
    "buildup_share",
    "chance_involvement_per_90",
    "defensive_action_density",
    "kp_share_per90",
    "inaccurate_pass_rate",
    "finishing_shrunk_delta_per_shot",
    "sot_rate",
}

SCORE_DEFINITIONS: dict[str, dict] = {
    "finishing_score": {
        "label": "Finishing Score",
        "description": "Per-shot finishing vs NPxG (shrunk), on-target rate, shot quality per attempt, and a small shot-volume stabiliser; percentile within position.",
        "group": "scores",
        "sources_used": ["understat", "sofascore"],
        "positions": {
            "FWD": [
                {"metric": "finishing_shrunk_delta_per_shot", "weight": 0.65},
                {"metric": "sot_rate", "weight": 0.20},
                {"metric": "npxg_per_shot", "weight": 0.10},
                {"metric": "shots_per_90", "weight": 0.05},
            ],
            "MID": [
                {"metric": "finishing_shrunk_delta_per_shot", "weight": 0.65},
                {"metric": "sot_rate", "weight": 0.20},
                {"metric": "npxg_per_shot", "weight": 0.10},
                {"metric": "shots_per_90", "weight": 0.05},
            ],
            "DEF": [
                {"metric": "finishing_shrunk_delta_per_shot", "weight": 0.65},
                {"metric": "sot_rate", "weight": 0.20},
                {"metric": "npxg_per_shot", "weight": 0.10},
                {"metric": "shots_per_90", "weight": 0.05},
            ],
        },
    },
    "creation_score": {
        "label": "Creation Score",
        "description": "Chance creation from xA level, efficiency per key pass, key-pass volume, and dribbling; defenders add buildup and circulation.",
        "group": "scores",
        "sources_used": ["understat", "sofascore"],
        "positions": {
            "FWD": [
                {"metric": "xa_per_90", "weight": 0.34},
                {"metric": "big_chances_created_per_90", "weight": 0.26},
                {"metric": "key_passes_per_90", "weight": 0.16},
                {"metric": "accurate_crosses_per_90", "weight": 0.08},
                {"metric": "successful_dribbles_per_90", "weight": 0.12},
                {"metric": "kp_share_per90", "weight": 0.04},
            ],
            "MID": [
                {"metric": "xa_per_90", "weight": 0.36},
                {"metric": "big_chances_created_per_90", "weight": 0.24},
                {"metric": "key_passes_per_90", "weight": 0.16},
                {"metric": "accurate_crosses_per_90", "weight": 0.08},
                {"metric": "successful_dribbles_per_90", "weight": 0.12},
                {"metric": "kp_share_per90", "weight": 0.04},
            ],
            "DEF": [
                {"metric": "xgbuildup_per_90", "weight": 0.3},
                {"metric": "xa_per_90", "weight": 0.22},
                {"metric": "big_chances_created_per_90", "weight": 0.16},
                {"metric": "accurate_long_balls_per_90", "weight": 0.18},
                {"metric": "accurate_crosses_per_90", "weight": 0.06},
                {"metric": "kp_share_per90", "weight": 0.08},
            ],
        },
    },
    "buildup_score": {
        "label": "Buildup Score",
        "description": "Earlier-phase contribution via xGBuildup rate and buildup share of chain credit, plus circulation and carrying.",
        "group": "scores",
        "sources_used": ["understat", "sofascore"],
        "positions": {
            "FWD": [
                {"metric": "xgbuildup_per_90", "weight": 0.3},
                {"metric": "buildup_share", "weight": 0.24},
                {"metric": "completed_passes_per_90", "weight": 0.18},
                {"metric": "accurate_long_balls_per_90", "weight": 0.1},
                {"metric": "successful_dribbles_per_90", "weight": 0.18},
            ],
            "MID": [
                {"metric": "xgbuildup_per_90", "weight": 0.3},
                {"metric": "buildup_share", "weight": 0.22},
                {"metric": "completed_passes_per_90", "weight": 0.22},
                {"metric": "accurate_long_balls_per_90", "weight": 0.12},
                {"metric": "successful_dribbles_per_90", "weight": 0.14},
            ],
            "DEF": [
                {"metric": "xgbuildup_per_90", "weight": 0.28},
                {"metric": "buildup_share", "weight": 0.2},
                {"metric": "completed_passes_per_90", "weight": 0.2},
                {"metric": "accurate_long_balls_per_90", "weight": 0.22},
                {"metric": "successful_dribbles_per_90", "weight": 0.1},
            ],
        },
        "penalties": {
            "FWD": [{"metric": "inaccurate_pass_rate", "weight": 0.1}],
            "MID": [{"metric": "inaccurate_pass_rate", "weight": 0.1}],
            "DEF": [{"metric": "inaccurate_pass_rate", "weight": 0.1}],
        },
    },
    "ball_winning_score": {
        "label": "Ball Winning Score",
        "description": "Defensive activity from tackles, interceptions, blocks, and clearances (no aggregate density to avoid double counting).",
        "group": "scores",
        "sources_used": ["sofascore"],
        "positions": {
            "FWD": [
                {"metric": "tackles_per_90", "weight": 0.18},
                {"metric": "interceptions_per_90", "weight": 0.18},
                {"metric": "ball_recoveries_per_90", "weight": 0.24},
                {"metric": "tackles_won_percentage", "weight": 0.14},
                {"metric": "ground_duels_won_per_90", "weight": 0.16},
                {"metric": "aerial_duels_won_per_90", "weight": 0.1},
            ],
            "MID": [
                {"metric": "tackles_per_90", "weight": 0.19},
                {"metric": "interceptions_per_90", "weight": 0.19},
                {"metric": "ball_recoveries_per_90", "weight": 0.24},
                {"metric": "tackles_won_percentage", "weight": 0.14},
                {"metric": "ground_duels_won_per_90", "weight": 0.14},
                {"metric": "aerial_duels_won_per_90", "weight": 0.1},
            ],
            "DEF": [
                {"metric": "tackles_per_90", "weight": 0.16},
                {"metric": "interceptions_per_90", "weight": 0.18},
                {"metric": "ball_recoveries_per_90", "weight": 0.22},
                {"metric": "tackles_won_percentage", "weight": 0.14},
                {"metric": "ground_duels_won_per_90", "weight": 0.14},
                {"metric": "aerial_duels_won_per_90", "weight": 0.16},
            ],
        },
        "penalties": {
            "FWD": [
                {"metric": "fouls_per_90", "weight": 0.06},
                {"metric": "errors_lead_to_goal_per_90", "weight": 0.14},
            ],
            "MID": [
                {"metric": "fouls_per_90", "weight": 0.06},
                {"metric": "errors_lead_to_goal_per_90", "weight": 0.14},
            ],
            "DEF": [
                {"metric": "fouls_per_90", "weight": 0.06},
                {"metric": "errors_lead_to_goal_per_90", "weight": 0.14},
            ],
        },
    },
    "involvement_score": {
        "label": "Involvement Score",
        "description": "How often a player appears in chance-ending actions and chains; forwards exclude separate shot volume where it duplicates chance involvement.",
        "group": "scores",
        "sources_used": ["understat", "sofascore"],
        "positions": {
            "FWD": [
                {"metric": "xgchain_per_90", "weight": 0.42},
                {"metric": "chance_involvement_per_90", "weight": 0.34},
                {"metric": "shots_per_90", "weight": 0.12},
                {"metric": "key_passes_per_90", "weight": 0.06},
                {"metric": "successful_dribbles_per_90", "weight": 0.06},
            ],
            "MID": [
                {"metric": "xgchain_per_90", "weight": 0.46},
                {"metric": "chance_involvement_per_90", "weight": 0.34},
                {"metric": "shots_per_90", "weight": 0.04},
                {"metric": "key_passes_per_90", "weight": 0.06},
                {"metric": "successful_dribbles_per_90", "weight": 0.1},
            ],
            "DEF": [
                {"metric": "xgchain_per_90", "weight": 0.56},
                {"metric": "chance_involvement_per_90", "weight": 0.34},
                {"metric": "key_passes_per_90", "weight": 0.03},
                {"metric": "successful_dribbles_per_90", "weight": 0.07},
            ],
        },
        "penalties": {"FWD": [{"metric": "offsides_per_90", "weight": 0.04}]},
    },
}

SCORE_FIELDS = list(SCORE_DEFINITIONS.keys())
SCORE_RAW_FIELDS = [f"{field}_raw" for field in SCORE_FIELDS]
SCORE_COMPONENT_METRICS = sorted(
    {
        component["metric"]
        for score_def in SCORE_DEFINITIONS.values()
        for components in score_def["positions"].values()
        for component in components
    }
)
SCORE_PENALTY_METRICS = sorted(
    {
        component["metric"]
        for score_def in SCORE_DEFINITIONS.values()
        for penalties in score_def.get("penalties", {}).values()
        for component in penalties
    }
)

LIST_SORT_FIELDS = {
    "canonical_player_name": "canonical_player__display_name",
    "canonical_team_name": "canonical_display_team__name",
    "position_group": "position_group",
    "minutes": "minutes",
}
for field_name in METRIC_FIELDS + PERCENTILE_FIELDS + SCORE_FIELDS + SCORE_RAW_FIELDS:
    LIST_SORT_FIELDS[field_name] = field_name
