from django.urls import path

from ingestion.competition_seasons_api import CompetitionSeasonsCatalogApi
from ingestion.derived_api import (
    DerivedPlayerSeasonDetailApi,
    DerivedPlayerSeasonListApi,
)
from ingestion.defensive_territory_api import TeamDefensiveTerritoryApi
from ingestion.event_profile_api import (
    PlayerEventProfileApi,
    PlayerEventProfilePassesApi,
    TeamEventProfileApi,
)
from ingestion.galaxy_api import GalaxyApi, GalaxySimilarApi
from ingestion.gk_api import (
    GkDerivedPlayerSeasonDetailApi,
    GkDerivedPlayerSeasonListApi,
)
from ingestion.player_state_api import PlayerStateExposureApi
from ingestion.player_state_comparison_api import PlayerStateComparisonApi
from ingestion.possession_context_api import TeamPossessionContextApi
from ingestion.pass_state_api import TeamPassStateApi
from ingestion.team_api import TeamSeasonDetailApi, TeamSeasonListApi, TeamSquadApi
from ingestion.regression_api import RegressionLabFitApi
from ingestion.search_api import SearchEntitiesApi
from ingestion.shot_zones_api import PlayerGkShotZonesApi, PlayerShotZonesApi
from ingestion.shot_pressure_api import TeamShotPressureApi


urlpatterns = [
    path("competition-seasons", CompetitionSeasonsCatalogApi.as_view()),
    path("search/entities", SearchEntitiesApi.as_view()),
    path("player-seasons/gk-derived-stats", GkDerivedPlayerSeasonListApi.as_view()),
    path(
        "player-seasons/gk-derived-stats/<int:canonical_player_id>",
        GkDerivedPlayerSeasonDetailApi.as_view(),
    ),
    path("player-seasons/derived-stats", DerivedPlayerSeasonListApi.as_view()),
    path(
        "player-seasons/derived-stats/<int:canonical_player_id>",
        DerivedPlayerSeasonDetailApi.as_view(),
    ),
    path(
        "player-seasons/event-profile/<int:canonical_player_id>",
        PlayerEventProfileApi.as_view(),
    ),
    path(
        "player-seasons/event-profile/<int:canonical_player_id>/passes",
        PlayerEventProfilePassesApi.as_view(),
    ),
    path(
        "player-seasons/event-profile/<int:canonical_player_id>/shot-zones",
        PlayerShotZonesApi.as_view(),
    ),
    path(
        "player-seasons/event-profile/<int:canonical_player_id>/gk-shot-zones",
        PlayerGkShotZonesApi.as_view(),
    ),
    path(
        "player-seasons/state-exposure/<int:canonical_player_id>",
        PlayerStateExposureApi.as_view(),
    ),
    path(
        "player-seasons/event-profile/<int:canonical_player_id>/state-comparison",
        PlayerStateComparisonApi.as_view(),
    ),
    path("galaxy", GalaxyApi.as_view()),
    path("galaxy/similar", GalaxySimilarApi.as_view()),
    path("team-seasons/stats", TeamSeasonListApi.as_view()),
    path("team-seasons/stats/<int:canonical_team_id>", TeamSeasonDetailApi.as_view()),
    path(
        "team-seasons/event-profile/<int:canonical_team_id>",
        TeamEventProfileApi.as_view(),
    ),
    path(
        "team-seasons/event-profile/<int:canonical_team_id>/pass-state",
        TeamPassStateApi.as_view(),
    ),
    path(
        "team-seasons/event-profile/<int:canonical_team_id>/defensive-territory",
        TeamDefensiveTerritoryApi.as_view(),
    ),
    path(
        "team-seasons/shot-pressure/<int:canonical_team_id>",
        TeamShotPressureApi.as_view(),
    ),
    path("team-seasons/squad/<int:canonical_team_id>", TeamSquadApi.as_view()),
    path(
        "team-seasons/possession-context/<int:canonical_team_id>",
        TeamPossessionContextApi.as_view(),
    ),
    path("labs/regression/fit", RegressionLabFitApi.as_view()),
]
