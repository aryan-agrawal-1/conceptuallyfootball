from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_api import _resolve_competition_scope
from ingestion.models import PlayerSeasonEmbedding, PlayerSeasonSimilarity

ARCHETYPE_COLORS = [
    "#4A9EF5",
    "#1FD17C",
    "#F0A832",
    "#A855F7",
    "#EF4444",
    "#22D3EE",
    "#F472B6",
    "#C0FF4D",
]


class GalaxyApi(APIView):
    def get(self, request):
        try:
            competition_code, season_label, competition_seasons = _resolve_competition_scope(request)
            queryset = (
                PlayerSeasonEmbedding.objects.filter(
                    competition_season__in=competition_seasons,
                    is_current=True,
                )
                .select_related("canonical_player", "canonical_display_team")
                .order_by("canonical_player__display_name")
            )

            position_group = request.query_params.get("position_group")
            if position_group:
                queryset = queryset.filter(position_group__iexact=position_group)

            team_id = request.query_params.get("team")
            if team_id:
                if team_id.isdigit():
                    queryset = queryset.filter(canonical_display_team_id=int(team_id))
                else:
                    queryset = queryset.filter(canonical_display_team__name__iexact=team_id)

            min_minutes = request.query_params.get("min_minutes")
            if min_minutes:
                try:
                    queryset = queryset.filter(minutes__gte=int(min_minutes))
                except ValueError as exc:
                    raise DjangoValidationError("min_minutes must be an integer.") from exc
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        rows = list(queryset)

        # Each cluster's label is stored per-row on the embedding. We pick any
        # row's label to represent the cluster (all rows in the same cluster
        # share a label) and fall back to "Archetype N" if the label is empty
        # (e.g. data materialized before we started storing labels).
        labels_by_cluster: dict[int, str] = {}
        for row in rows:
            if row.cluster_id in labels_by_cluster:
                continue
            labels_by_cluster[row.cluster_id] = (
                row.cluster_label or f"Archetype {row.cluster_id + 1}"
            )

        cluster_ids = sorted(labels_by_cluster.keys())
        archetypes = [
            {
                "cluster_id": cluster_id,
                "label": labels_by_cluster[cluster_id],
                "color": ARCHETYPE_COLORS[cluster_id % len(ARCHETYPE_COLORS)],
            }
            for cluster_id in cluster_ids
        ]
        color_map = {item["cluster_id"]: item["color"] for item in archetypes}
        points = [
            {
                "canonical_player_id": row.canonical_player_id,
                "canonical_player_name": row.canonical_player.display_name,
                "canonical_team_id": row.canonical_display_team_id,
                "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
                "position_group": row.position_group,
                "minutes": row.minutes or 0,
                "cluster_id": row.cluster_id,
                "cluster_label": labels_by_cluster[row.cluster_id],
                "cluster_color": color_map[row.cluster_id],
                "x": row.umap_x,
                "y": row.umap_y,
                "z": row.umap_z,
            }
            for row in rows
        ]
        players = [
            {
                "canonical_player_id": row.canonical_player_id,
                "canonical_player_name": row.canonical_player.display_name,
            }
            for row in rows
        ]

        selected_player_id = request.query_params.get("selected_player")
        selected = None
        edges = []
        if selected_player_id:
            try:
                selected_id = int(selected_player_id)
            except ValueError:
                selected_id = None
            if selected_id:
                selected = next((point for point in points if point["canonical_player_id"] == selected_id), None)
                if selected:
                    similar_rows = (
                        PlayerSeasonSimilarity.objects.filter(
                            competition_season__in=competition_seasons,
                            canonical_player_id=selected_id,
                            is_current=True,
                        )
                        .select_related("similar_player")
                        .order_by("rank")
                    )
                    edges = [
                        {
                            "from_player_id": selected_id,
                            "to_player_id": row.similar_player_id,
                            "to_player_name": row.similar_player.display_name,
                            "similarity": row.similarity,
                            "rank": row.rank,
                        }
                        for row in similar_rows
                    ]

        return Response(
            {
                "competition_season": competition_seasons[0].id if len(competition_seasons) == 1 else 0,
                "competition_code": competition_code,
                "season_label": season_label,
                "count": len(points),
                "archetypes": archetypes,
                "points": points,
                "players": players,
                "selected_player": selected,
                "edges": edges,
            }
        )


class GalaxySimilarApi(APIView):
    def get(self, request):
        try:
            _competition_code, _season_label, competition_seasons = _resolve_competition_scope(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        player_param = request.query_params.get("player")
        if not player_param or not player_param.isdigit():
            return Response(
                {"detail": "player query param required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        player_id = int(player_param)

        embedding = (
            PlayerSeasonEmbedding.objects.filter(
                competition_season__in=competition_seasons,
                canonical_player_id=player_id,
                is_current=True,
            )
            .select_related("canonical_player", "canonical_display_team")
            .first()
        )
        if embedding is None:
            return Response(
                {"detail": "Player not found in this galaxy snapshot."},
                status=status.HTTP_404_NOT_FOUND,
            )

        similar_rows = (
            PlayerSeasonSimilarity.objects.filter(
                competition_season=embedding.competition_season,
                canonical_player_id=player_id,
                is_current=True,
            )
            .select_related("similar_player")
            .order_by("rank")
        )

        color = ARCHETYPE_COLORS[embedding.cluster_id % len(ARCHETYPE_COLORS)]
        label = embedding.cluster_label or f"Archetype {embedding.cluster_id + 1}"
        return Response(
            {
                "selected_player": {
                    "canonical_player_id": embedding.canonical_player_id,
                    "canonical_player_name": embedding.canonical_player.display_name,
                    "canonical_team_id": embedding.canonical_display_team_id,
                    "canonical_team_name": embedding.canonical_display_team.name
                    if embedding.canonical_display_team
                    else None,
                    "position_group": embedding.position_group,
                    "minutes": embedding.minutes or 0,
                    "cluster_id": embedding.cluster_id,
                    "cluster_label": label,
                    "cluster_color": color,
                    "x": embedding.umap_x,
                    "y": embedding.umap_y,
                    "z": embedding.umap_z,
                },
                "edges": [
                    {
                        "from_player_id": player_id,
                        "to_player_id": row.similar_player_id,
                        "to_player_name": row.similar_player.display_name,
                        "similarity": row.similarity,
                        "rank": row.rank,
                    }
                    for row in similar_rows
                ],
            }
        )
