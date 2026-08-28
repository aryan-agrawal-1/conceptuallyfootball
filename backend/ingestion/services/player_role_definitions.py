"""Versioned, inspectable definitions for player-season archetypes and traits."""

from __future__ import annotations


ROLE_FEATURE_VERSION = "player_role_features_v4"
ROLE_SCORING_VERSION = "player_role_scoring_v4"
PROVISIONAL_EXPOSURE_SECONDS = 450 * 60
ESTABLISHED_EXPOSURE_SECONDS = 900 * 60
MINIMUM_PRIMARY_FIT = 0.58
MINIMUM_SECONDARY_FIT = 0.56
HYBRID_MARGIN = 0.07


ARCHETYPE_DEFINITIONS = {
    "Connector": {
        "meaning": "A central link player who repeatedly keeps possessions moving between teammates and zones.",
        "pool": "outfield",
        "positions": ["MID", "FWD", "UNK"],
        "plausibility": "Broadly central midfield or attacking touch territory; only defender-labelled players operating unusually high can enter.",
        "minimum_evidence": "80 open-play pass attempts and 40 central touches.",
        "components": {
            "pass_involvement": 0.30,
            "central_touch_share": 0.25,
            "completion": 0.20,
            "zone_connectivity": 0.25,
        },
    },
    "Deep-Lying Playmaker": {
        "meaning": "A central, deeper distributor who advances play through repeatable progressive passing.",
        "pool": "outfield",
        "positions": ["MID", "FWD", "UNK"],
        "plausibility": "Central/interior midfield territory with an average touch height no higher than the middle third; ordinary centre-backs belong in the Ball-Playing Defender pool.",
        "minimum_evidence": "60 passes from the defensive or middle third and 12 progressive passes, with progression demonstrably originating in first/second-phase build-up.",
        "components": {
            "deep_pass_volume": 0.20,
            "build_up_origin_share": 0.20,
            "build_up_progression": 0.25,
            "build_up_progression_share": 0.20,
            "progressive_pass_share": 0.15,
        },
    },
    "Line-Breaking Playmaker": {
        "meaning": "A central playmaker whose successful passes repeatedly cross an opposition line or enter a more dangerous zone.",
        "pool": "outfield",
        "positions": ["MID", "FWD", "UNK"],
        "plausibility": "Broadly central or half-space midfield/attacking territory; ordinary centre-backs remain Ball-Playing Defender candidates.",
        "minimum_evidence": "10 successful line-breaking passes and 60 open-play pass attempts.",
        "components": {
            "line_break_volume": 0.35,
            "line_break_frequency": 0.25,
            "central_progression": 0.20,
            "dangerous_entries": 0.20,
        },
    },
    "Ball-Playing Defender": {
        "meaning": "A first-line defender who combines genuine defensive work with repeatable progression from the build-up line.",
        "pool": "outfield",
        "positions": ["DEF", "MID", "UNK"],
        "plausibility": "Defender or build-up player operating predominantly in the defensive half; includes build-up full-backs.",
        "minimum_evidence": "50 build-up passes, 10 progressive build-up passes, and 20 defensive actions.",
        "components": {
            "build_up_progression": 0.35,
            "build_up_pass_volume": 0.20,
            "defensive_work": 0.20,
            "progressive_share": 0.25,
        },
    },
    "Ball-Carrying Progressor": {
        "meaning": "Moves the team forward primarily through repeatable progressive carries and territory gained on the ball.",
        "pool": "outfield",
        "positions": ["DEF", "MID", "FWD", "UNK"],
        "plausibility": "Any outfield role with meaningful carry evidence.",
        "minimum_evidence": "12 progressive carries and 30 recorded carries.",
        "components": {
            "progressive_carry_volume": 0.35,
            "progressive_carry_share": 0.30,
            "forward_carry_distance": 0.20,
            "carry_entries": 0.15,
        },
    },
    "Advanced Creator": {
        "meaning": "Creates shots and dangerous entries from advanced open-play positions.",
        "pool": "outfield",
        "positions": ["MID", "FWD", "UNK"],
        "plausibility": "Advanced midfield, half-space, wide or attacking territory.",
        "minimum_evidence": "8 open-play key passes or shot assists, plus 20 final-third actions.",
        "components": {
            "key_pass_volume": 0.35,
            "shot_assist_share": 0.20,
            "box_entry_creation": 0.25,
            "advanced_involvement": 0.20,
        },
    },
    "Transition Outlet": {
        "meaning": "Provides a repeatable forward release point and carries threat when play turns over, across all score states.",
        "pool": "outfield",
        "positions": ["MID", "FWD", "DEF", "UNK"],
        "plausibility": "Usually advanced or wide, but role evidence can admit an attacking wing-back.",
        "minimum_evidence": "30 advanced touches and involvement in 10 verified transition possessions.",
        "components": {
            "transition_involvement": 0.35,
            "advanced_touch_share": 0.20,
            "transition_advancement": 0.25,
            "direct_carry_threat": 0.20,
        },
    },
    "Box Threat": {
        "meaning": "Consistently occupies and attacks scoring territory through open-play box touches and shots.",
        "pool": "outfield",
        "positions": ["FWD", "MID", "UNK"],
        "plausibility": "Advanced central or wide attacking territory; touch evidence can override a broad midfield label.",
        "minimum_evidence": "20 open-play box touches and 12 open-play shots.",
        "components": {
            "box_touch_volume": 0.30,
            "shot_volume": 0.30,
            "box_touch_share": 0.20,
            "shot_share": 0.20,
        },
    },
    "Ball Winner": {
        "meaning": "Actively regains possession through tackles, interceptions, recoveries and defensive pressure away from the last line.",
        "pool": "outfield",
        "positions": ["MID", "DEF", "FWD", "UNK"],
        "plausibility": "Any outfield player with meaningful defensive evidence outside a purely deep protective profile.",
        "minimum_evidence": "35 ball-winning actions, including at least 10 tackles or interceptions.",
        "components": {
            "ball_win_volume": 0.35,
            "ball_win_share": 0.25,
            "active_defensive_height": 0.20,
            "tackle_interception_mix": 0.20,
        },
    },
    "Deep Protector": {
        "meaning": "Protects deep territory through last-line interventions, clearances, blocks and aerial defending.",
        "pool": "outfield",
        "positions": ["DEF", "MID", "UNK"],
        "plausibility": "Predominantly defensive-half territory, guided by both assigned position and touch/action height.",
        "minimum_evidence": "30 deep defensive actions, including 12 clearances, blocks or defensive aerials.",
        "components": {
            "deep_defensive_volume": 0.35,
            "protective_interventions": 0.30,
            "defensive_share": 0.20,
            "deep_action_share": 0.15,
        },
    },
    "Sweeper Keeper": {
        "meaning": "A goalkeeper who repeatedly intervenes outside the immediate goalmouth and supports a higher defensive line.",
        "pool": "goalkeeper",
        "positions": ["GK"],
        "plausibility": "Goalkeepers only.",
        "minimum_evidence": "8 open-play recoveries, clearances or passes outside the penalty-area build-up zone.",
        "components": {
            "sweeper_actions": 0.45,
            "sweeper_height": 0.25,
            "outside_box_share": 0.30,
        },
    },
    "Goalkeeper Distributor": {
        "meaning": "A goalkeeper whose repeatable contribution is initiating possession through volume and progressive distribution.",
        "pool": "goalkeeper",
        "positions": ["GK"],
        "plausibility": "Goalkeepers only.",
        "minimum_evidence": "80 open-play pass attempts and 10 progressive or long distributions.",
        "components": {
            "distribution_volume": 0.30,
            "progressive_distribution": 0.30,
            "long_distribution": 0.20,
            "distribution_completion": 0.20,
        },
    },
    "Shot Stopper": {
        "meaning": "A goalkeeper whose season role is defined by a high volume of direct shot-stopping interventions, not inferred saving ability.",
        "pool": "goalkeeper",
        "positions": ["GK"],
        "plausibility": "Goalkeepers only.",
        "minimum_evidence": "20 recorded saves.",
        "components": {
            "save_volume": 0.55,
            "save_workload_share": 0.25,
            "close_range_interventions": 0.20,
        },
    },
}


TRAIT_DEFINITIONS = {
    "Clutch": "Repeatedly changes the score state with at least four direct contributions and strong goal-weighted evidence.",
    "Lead Extender": "Repeatedly adds goals or direct assists while already winning, with at least three direct contributions.",
    "State-resilient": "Maintains a recognisably similar rate, share and territory across sufficiently observed game states.",
    "Adaptive": "Meaningfully changes territory or contribution relative to the team as game state changes.",
    "High-volume": "Handles an unusually large share of the team's repeatable actions.",
    "Direct": "Moves play forward quickly through progressive, long or transition actions.",
    "Ball secure": "Combines reliable retention with a low turnover burden at meaningful volume.",
    "Aerial specialist": "Takes an unusually large, repeatable share of aerial contests.",
    "Set-piece specialist": "Provides a meaningful share of a team's corners, free-kicks or set-piece creation.",
}


def public_role_definitions() -> dict:
    return {
        "feature_version": ROLE_FEATURE_VERSION,
        "scoring_version": ROLE_SCORING_VERSION,
        "archetypes": ARCHETYPE_DEFINITIONS,
        "traits": TRAIT_DEFINITIONS,
        "exposure": {
            "provisional_minutes": PROVISIONAL_EXPOSURE_SECONDS // 60,
            "established_minutes": ESTABLISHED_EXPOSURE_SECONDS // 60,
        },
    }
