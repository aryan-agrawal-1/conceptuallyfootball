from rest_framework import viewsets

from ingestion.filters import MergedPlayerSeasonFilter, MergedTeamSeasonFilter
from ingestion.models import MergedPlayerSeason, MergedTeamSeason
from ingestion.serializers import MergedPlayerSeasonSerializer, MergedTeamSeasonSerializer


class MergedPlayerSeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Internal bootstrap API: current merged player-season rows only.
    """

    serializer_class = MergedPlayerSeasonSerializer
    filterset_class = MergedPlayerSeasonFilter
    pagination_class = None
    queryset = MergedPlayerSeason.objects.none()

    def get_queryset(self):
        return (
            MergedPlayerSeason.objects.filter(is_current=True)
            .select_related(
                "canonical_player",
                "canonical_display_team",
                "competition_season",
                "competition_season__competition",
                "competition_season__season",
            )
            .order_by("canonical_player__display_name")
        )


class MergedTeamSeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Internal bootstrap API: current merged team-season rows only.
    """

    serializer_class = MergedTeamSeasonSerializer
    filterset_class = MergedTeamSeasonFilter
    pagination_class = None
    queryset = MergedTeamSeason.objects.none()

    def get_queryset(self):
        return (
            MergedTeamSeason.objects.filter(is_current=True)
            .select_related(
                "canonical_team",
                "competition_season",
                "competition_season__competition",
                "competition_season__season",
            )
            .order_by("rank", "canonical_team__name")
        )
