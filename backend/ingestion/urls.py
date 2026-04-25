from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ingestion.views import MergedPlayerSeasonViewSet, MergedTeamSeasonViewSet

router = DefaultRouter()
router.register(r"merged-player-seasons", MergedPlayerSeasonViewSet, basename="merged-player-season")
router.register(r"merged-team-seasons", MergedTeamSeasonViewSet, basename="merged-team-season")

urlpatterns = [
    path("api/", include(router.urls)),
]
