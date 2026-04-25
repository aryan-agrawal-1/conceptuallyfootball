from __future__ import annotations

FORMULA_VERSION_GK = "gk_v1"

GK_METRIC_GROUPS = {
    "shot_stopping": "Shot stopping",
    "sweeper": "Sweeper",
    "distribution": "Distribution",
}

GK_METRIC_DEFINITIONS: dict[str, dict] = {
    "rating": {
        "label": "Rating",
        "group": "shot_stopping",
        "unit": "ratio",
        "sources_used": ["sofascore"],
        "description": "Sofascore season rating for goalkeepers.",
        "caveat": "Provider summary; cohort percentiles are within goalkeepers only.",
    },
    "saves_per_90": {
        "label": "Saves/90",
        "group": "shot_stopping",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Saves per 90 minutes.",
        "caveat": "Volume depends on how often the goalkeeper is tested.",
    },
    "saves": {
        "label": "Saves",
        "group": "shot_stopping",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total saves in the sample.",
        "caveat": "Season total from SofaScore.",
    },
    "clean_sheet_rate": {
        "label": "CS%",
        "group": "shot_stopping",
        "unit": "percentage",
        "sources_used": ["sofascore"],
        "description": "Clean sheets divided by goalkeeper appearances.",
        "caveat": "Team-dependent; short samples swing.",
    },
    "clean_sheets": {
        "label": "CS",
        "group": "shot_stopping",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total clean sheets.",
        "caveat": "Provider definition of clean sheet.",
    },
    "penalty_saves": {
        "label": "Pen saves",
        "group": "shot_stopping",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Penalty saves in the sample.",
        "caveat": "Low counts for most keepers.",
    },
    "saved_shots_inside_box_per_90": {
        "label": "Box saves/90",
        "group": "shot_stopping",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Saves from shots inside the penalty area per 90.",
        "caveat": "Reflects shot location faced, not quality of save.",
    },
    "saved_shots_inside_box": {
        "label": "Box saves",
        "group": "shot_stopping",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total saves from shots inside the box.",
        "caveat": "",
    },
    "runs_out_per_90": {
        "label": "Runs out/90",
        "group": "sweeper",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Defensive runs out per 90 minutes.",
        "caveat": "Style and team line height affect volume.",
    },
    "runs_out": {
        "label": "Runs out",
        "group": "sweeper",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Total defensive runs out.",
        "caveat": "",
    },
    "pass_accuracy": {
        "label": "Pass%",
        "group": "distribution",
        "unit": "percentage",
        "sources_used": ["sofascore"],
        "description": "Share of passes completed.",
        "caveat": "Mix of pass difficulty varies by system.",
    },
    "completed_passes_per_90": {
        "label": "Passes/90",
        "group": "distribution",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Completed passes per 90 minutes.",
        "caveat": "",
    },
    "accurate_long_balls_per_90": {
        "label": "Long balls/90",
        "group": "distribution",
        "unit": "per90",
        "sources_used": ["sofascore"],
        "description": "Accurate long balls per 90 minutes.",
        "caveat": "",
    },
    "appearances": {
        "label": "Apps",
        "group": "shot_stopping",
        "unit": "total",
        "sources_used": ["sofascore"],
        "description": "Goalkeeper appearances recorded by SofaScore.",
        "caveat": "",
    },
}

GK_METRIC_FIELDS = list(GK_METRIC_DEFINITIONS.keys())

# Appearances has no percentile column in the model.
GK_METRICS_WITH_PERCENTILE = [m for m in GK_METRIC_FIELDS if m != "appearances"]

GK_METRIC_PERCENTILE_FIELDS = [f"{m}_percentile" for m in GK_METRICS_WITH_PERCENTILE]

LIST_SORT_FIELDS_GK: dict[str, str] = {
    "canonical_player_name": "canonical_player__display_name",
    "canonical_team_name": "canonical_display_team__name",
    "minutes": "minutes",
    "appearances": "appearances",
}
for _m in GK_METRIC_FIELDS:
    LIST_SORT_FIELDS_GK[_m] = _m
