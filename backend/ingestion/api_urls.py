from django.urls import path

from ingestion.competition_seasons_api import CompetitionSeasonsCatalogApi
from ingestion.derived_api import DerivedPlayerSeasonDetailApi, DerivedPlayerSeasonListApi
from ingestion.galaxy_api import GalaxyApi, GalaxySimilarApi
from ingestion.gk_api import GkDerivedPlayerSeasonDetailApi, GkDerivedPlayerSeasonListApi
from ingestion.team_api import TeamSeasonDetailApi, TeamSeasonListApi, TeamSquadApi
from ingestion.regression_api import RegressionLabFitApi
from ingestion.search_api import SearchEntitiesApi


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
    path("galaxy", GalaxyApi.as_view()),
    path("galaxy/similar", GalaxySimilarApi.as_view()),
    path("team-seasons/stats", TeamSeasonListApi.as_view()),
    path("team-seasons/stats/<int:canonical_team_id>", TeamSeasonDetailApi.as_view()),
    path("team-seasons/squad/<int:canonical_team_id>", TeamSquadApi.as_view()),
    path("labs/regression/fit", RegressionLabFitApi.as_view()),
]
