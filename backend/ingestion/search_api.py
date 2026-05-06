from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.models import (
    MergedTeamSeason,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
)


class SearchEntitiesApi(APIView):
    """
    Canonical player/team search index across every active slice.

    This keeps the global nav search canonical (one Man City, one player) while
    still giving the frontend enough memberships to open the current scope when
    possible, or a nearby valid slice when not.
    """

    def get(self, request):
        players: dict[int, dict] = {}
        player_membership_seen: set[tuple[int, str, str]] = set()

        player_qs = (
            PlayerSeasonDerivedStats.objects.filter(
                is_current=True,
                competition_season__is_active=True,
            )
            .values(
                "canonical_player_id",
                "canonical_player__display_name",
                "canonical_display_team_id",
                "canonical_display_team__name",
                "position_group",
                "minutes",
                "competition_season_id",
                "competition_season__competition__short_code",
                "competition_season__season__label",
            )
        )
        gk_qs = (
            PlayerSeasonGkDerivedStats.objects.filter(
                is_current=True,
                competition_season__is_active=True,
            )
            .values(
                "canonical_player_id",
                "canonical_player__display_name",
                "canonical_display_team_id",
                "canonical_display_team__name",
                "minutes",
                "competition_season_id",
                "competition_season__competition__short_code",
                "competition_season__season__label",
            )
        )

        for row in player_qs.iterator(chunk_size=2000):
            player_id = row["canonical_player_id"]
            scope = {
                "competition": row["competition_season__competition__short_code"],
                "season": row["competition_season__season__label"],
                "competition_season_id": row["competition_season_id"],
            }
            seen_key = (player_id, scope["competition"], scope["season"])
            entry = players.setdefault(
                player_id,
                {
                    "kind": "player",
                    "canonical_player_id": player_id,
                    "canonical_player_name": row["canonical_player__display_name"],
                    "memberships": [],
                    "total_minutes": 0,
                },
            )
            entry["total_minutes"] += row["minutes"] or 0
            if seen_key in player_membership_seen:
                continue
            player_membership_seen.add(seen_key)
            entry["memberships"].append(
                {
                    **scope,
                    "canonical_team_id": row["canonical_display_team_id"],
                    "canonical_team_name": row["canonical_display_team__name"],
                    "position_group": row["position_group"],
                    "minutes": row["minutes"],
                }
            )

        for row in gk_qs.iterator(chunk_size=2000):
            player_id = row["canonical_player_id"]
            scope = {
                "competition": row["competition_season__competition__short_code"],
                "season": row["competition_season__season__label"],
                "competition_season_id": row["competition_season_id"],
            }
            seen_key = (player_id, scope["competition"], scope["season"])
            entry = players.setdefault(
                player_id,
                {
                    "kind": "player",
                    "canonical_player_id": player_id,
                    "canonical_player_name": row["canonical_player__display_name"],
                    "memberships": [],
                    "total_minutes": 0,
                },
            )
            entry["total_minutes"] += row["minutes"] or 0
            if seen_key in player_membership_seen:
                continue
            player_membership_seen.add(seen_key)
            entry["memberships"].append(
                {
                    **scope,
                    "canonical_team_id": row["canonical_display_team_id"],
                    "canonical_team_name": row["canonical_display_team__name"],
                    "position_group": "GK",
                    "minutes": row["minutes"],
                }
            )

        teams: dict[int, dict] = {}
        team_membership_seen: set[tuple[int, str, str]] = set()
        team_qs = (
            MergedTeamSeason.objects.filter(
                is_current=True,
                competition_season__is_active=True,
            )
            .values(
                "canonical_team_id",
                "canonical_team__name",
                "rank",
                "matches",
                "competition_season_id",
                "competition_season__competition__short_code",
                "competition_season__season__label",
            )
        )
        for row in team_qs.iterator(chunk_size=1000):
            team_id = row["canonical_team_id"]
            scope = {
                "competition": row["competition_season__competition__short_code"],
                "season": row["competition_season__season__label"],
                "competition_season_id": row["competition_season_id"],
            }
            seen_key = (team_id, scope["competition"], scope["season"])
            entry = teams.setdefault(
                team_id,
                {
                    "kind": "team",
                    "canonical_team_id": team_id,
                    "canonical_team_name": row["canonical_team__name"],
                    "memberships": [],
                    "total_matches": 0,
                },
            )
            entry["total_matches"] += row["matches"] or 0
            if seen_key in team_membership_seen:
                continue
            team_membership_seen.add(seen_key)
            entry["memberships"].append(
                {
                    **scope,
                    "rank": row["rank"],
                    "matches": row["matches"],
                }
            )

        for collection in (players.values(), teams.values()):
            for entry in collection:
                entry["memberships"].sort(
                    key=lambda m: (m["season"], m["competition"]),
                    reverse=True,
                )

        return Response(
            {
                "players": sorted(
                    players.values(),
                    key=lambda p: (-p["total_minutes"], p["canonical_player_name"]),
                ),
                "teams": sorted(
                    teams.values(),
                    key=lambda t: (t["canonical_team_name"], -t["total_matches"]),
                ),
            }
        )
