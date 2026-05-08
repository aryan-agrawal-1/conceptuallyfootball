from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.models import GalaxyPlayerEmbedding, GalaxySimilarity
from ingestion.services.galaxy import latest_galaxy_snapshot


def _snapshot_or_404(request):
    competition_code = (request.query_params.get("competition") or "").strip().upper()
    season_label = (request.query_params.get("season") or "").strip()
    if not competition_code or not season_label:
        raise DjangoValidationError(
            "Provide both competition and season for the Galaxy snapshot."
        )
    snapshot = latest_galaxy_snapshot(competition_code, season_label)
    if snapshot is None:
        raise GalaxyPlayerEmbedding.DoesNotExist(
            f"Galaxy snapshot not materialized for {competition_code} {season_label}."
        )
    return snapshot


def _model_meta(snapshot) -> dict:
    return {
        "snapshot_id": snapshot.id,
        "model_version": snapshot.model_version,
        "scope_code": snapshot.scope_code,
        "season_label": snapshot.season_label,
        "feature_profile": snapshot.feature_profile,
        "min_minutes": snapshot.min_minutes,
        "default_min_minutes": snapshot.default_min_minutes,
        "top_k": snapshot.top_k,
        "feature_names": snapshot.feature_names,
        "feature_weights": snapshot.feature_weights,
        "feature_groups": snapshot.feature_groups,
        "included_competition_season_ids": snapshot.included_competition_season_ids,
        "excluded_competitions": snapshot.excluded_competitions,
        "diagnostics": snapshot.diagnostics,
    }


def _point_payload(row: GalaxyPlayerEmbedding) -> dict:
    archetype = row.primary_archetype
    color = archetype.color if archetype else "#4A9EF5"
    label = row.primary_archetype_label or (archetype.label if archetype else "Outfielder")
    return {
        "galaxy_player_id": row.galaxy_player_id,
        "canonical_player_id": row.canonical_player_id,
        "canonical_player_name": row.canonical_player.display_name,
        "canonical_team_id": row.canonical_display_team_id,
        "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
        "competition_season_id": row.competition_season_id,
        "competition_code": row.competition_season.competition.short_code,
        "season_label": row.competition_season.season.label,
        "position_group": row.position_group,
        "native_position": row.native_position,
        "minutes": row.minutes or 0,
        "archetype_key": archetype.archetype_key if archetype else "",
        "archetype_label": label,
        "archetype_color": color,
        "primary_archetype_key": archetype.archetype_key if archetype else "",
        "primary_archetype_label": label,
        "primary_archetype_confidence": row.primary_archetype_confidence,
        "secondary_archetype_key": row.secondary_archetype.archetype_key if row.secondary_archetype else "",
        "secondary_archetype_label": row.secondary_archetype_label,
        "secondary_archetype_confidence": row.secondary_archetype_confidence,
        "archetype_margin": row.archetype_margin,
        "archetype_diagnostics": row.archetype_diagnostics,
        # Backward-compatible aliases while the frontend migrates.
        "cluster_id": archetype.cluster_id if archetype else 0,
        "cluster_label": label,
        "cluster_color": color,
        "x": row.umap_x,
        "y": row.umap_y,
        "z": row.umap_z,
    }


def _edge_payload(row: GalaxySimilarity) -> dict:
    target = row.similar_embedding
    return {
        "from_galaxy_player_id": row.source_embedding.galaxy_player_id,
        "to_galaxy_player_id": target.galaxy_player_id,
        "from_player_id": row.source_embedding.canonical_player_id,
        "to_player_id": target.canonical_player_id,
        "to_player_name": target.canonical_player.display_name,
        "to_team_name": target.canonical_display_team.name if target.canonical_display_team else None,
        "to_competition_code": target.competition_season.competition.short_code,
        "distance": row.distance,
        "base_distance": row.base_distance,
        "position_multiplier": row.position_multiplier,
        "candidate_percentile_score": row.candidate_percentile_score,
        "absolute_fit_score": row.absolute_fit_score,
        "profile_match_score": row.profile_match_score,
        # Backward-compatible 0-1-ish field for old UI while migrated.
        "similarity": row.profile_match_score / 100.0,
        "weak_absolute_fit": row.weak_absolute_fit,
        "match_context": row.match_context,
        "explanation": row.explanation,
        "rank": row.rank,
    }


class GalaxyApi(APIView):
    def get(self, request):
        try:
            snapshot = _snapshot_or_404(request)
            queryset = (
                GalaxyPlayerEmbedding.objects.filter(snapshot=snapshot)
                .select_related(
                    "canonical_player",
                    "canonical_display_team",
                    "competition_season",
                    "competition_season__competition",
                    "competition_season__season",
                    "primary_archetype",
                    "secondary_archetype",
                )
                .order_by("canonical_player__display_name", "competition_season__competition__short_code")
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
            requested_min_minutes = snapshot.default_min_minutes
            if min_minutes:
                try:
                    requested_min_minutes = int(min_minutes)
                except ValueError as exc:
                    raise DjangoValidationError("min_minutes must be an integer.") from exc
            effective_min_minutes = max(requested_min_minutes, snapshot.min_minutes)
            queryset = queryset.filter(minutes__gte=effective_min_minutes)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except GalaxyPlayerEmbedding.DoesNotExist as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        rows = list(queryset)
        archetype_ids = {row.primary_archetype_id for row in rows if row.primary_archetype_id}
        archetypes = [
            {
                "archetype_key": archetype.archetype_key,
                "cluster_id": archetype.cluster_id,
                "position_group": archetype.position_group,
                "label": archetype.label,
                "color": archetype.color,
                "size": archetype.size,
                "feature_signature": archetype.feature_signature,
                "representative_players": archetype.representative_players,
            }
            for archetype in snapshot.archetypes.filter(id__in=archetype_ids).order_by("position_group", "cluster_id")
        ]
        points = [_point_payload(row) for row in rows]
        players = [
            {
                "galaxy_player_id": row.galaxy_player_id,
                "canonical_player_id": row.canonical_player_id,
                "canonical_player_name": row.canonical_player.display_name,
                "canonical_team_name": row.canonical_display_team.name if row.canonical_display_team else None,
                "competition_code": row.competition_season.competition.short_code,
                "position_group": row.position_group,
                "minutes": row.minutes or 0,
            }
            for row in rows
        ]

        return Response(
            {
                "competition_season": 0 if len(snapshot.included_competition_season_ids) != 1 else snapshot.included_competition_season_ids[0],
                "competition_code": snapshot.scope_code,
                "season_label": snapshot.season_label,
                "count": len(points),
                "model_meta": {
                    **_model_meta(snapshot),
                    "requested_min_minutes": requested_min_minutes,
                    "effective_min_minutes": effective_min_minutes,
                },
                "archetypes": archetypes,
                "points": points,
                "players": players,
                "selected_player": None,
                "edges": [],
            }
        )


class GalaxySimilarApi(APIView):
    def get(self, request):
        try:
            snapshot = _snapshot_or_404(request)
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except GalaxyPlayerEmbedding.DoesNotExist as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        galaxy_player_id = request.query_params.get("galaxy_player_id")
        player_param = request.query_params.get("player")

        embedding_qs = (
            GalaxyPlayerEmbedding.objects.filter(snapshot=snapshot)
            .select_related(
                "canonical_player",
                "canonical_display_team",
                "competition_season",
                "competition_season__competition",
                "competition_season__season",
                "primary_archetype",
                "secondary_archetype",
            )
        )
        if galaxy_player_id:
            embedding = embedding_qs.filter(galaxy_player_id=galaxy_player_id).first()
        elif player_param and player_param.isdigit():
            matches = list(embedding_qs.filter(canonical_player_id=int(player_param))[:2])
            if len(matches) > 1:
                return Response(
                    {"detail": "player is ambiguous for this Galaxy scope; use galaxy_player_id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            embedding = matches[0] if matches else None
        else:
            return Response(
                {"detail": "galaxy_player_id query param required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if embedding is None:
            return Response(
                {"detail": "Player not found in this Galaxy snapshot."},
                status=status.HTTP_404_NOT_FOUND,
            )

        similar_rows = (
            GalaxySimilarity.objects.filter(
                snapshot=snapshot,
                source_embedding=embedding,
            )
            .select_related(
                "source_embedding",
                "similar_embedding",
                "similar_embedding__canonical_player",
                "similar_embedding__canonical_display_team",
                "similar_embedding__competition_season",
                "similar_embedding__competition_season__competition",
            )
            .order_by("rank")[:5]
        )

        return Response(
            {
                "selected_player": _point_payload(embedding),
                "edges": [_edge_payload(row) for row in similar_rows],
                "model_meta": _model_meta(snapshot),
            }
        )
