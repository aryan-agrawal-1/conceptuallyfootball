import django_filters

from ingestion.models import MergedPlayerSeason, MergedTeamSeason


class MergedPlayerSeasonFilter(django_filters.FilterSet):
    season = django_filters.CharFilter(
        field_name="competition_season__season__label",
        lookup_expr="iexact",
    )
    competition = django_filters.CharFilter(
        field_name="competition_season__competition__short_code",
        lookup_expr="iexact",
    )
    team = django_filters.NumberFilter(field_name="canonical_display_team_id")
    position_group = django_filters.CharFilter(field_name="position_group", lookup_expr="iexact")

    class Meta:
        model = MergedPlayerSeason
        fields = ["competition_season", "season", "competition", "team", "position_group"]


class MergedTeamSeasonFilter(django_filters.FilterSet):
    season = django_filters.CharFilter(
        field_name="competition_season__season__label",
        lookup_expr="iexact",
    )
    competition = django_filters.CharFilter(
        field_name="competition_season__competition__short_code",
        lookup_expr="iexact",
    )
    team = django_filters.NumberFilter(field_name="canonical_team_id")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = MergedTeamSeason
        fields = ["competition_season", "season", "competition", "team", "search"]

    def filter_search(self, queryset, name, value):  # noqa: ARG002
        if not value:
            return queryset
        return queryset.filter(canonical_team__name__icontains=value)
