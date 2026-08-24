import gzip
import json
from time import perf_counter

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ingestion.competition_scope import resolve_active_competition_season
from ingestion.models import (
    Provider,
    ProviderMatch,
    ProviderMatchPayload,
    ProviderMatchPlayerStateExposure,
    ProviderPayloadStorage,
)
from ingestion.services.whoscored_normalization import (
    parse_match_payload,
    replace_match_events,
)


class Command(BaseCommand):
    help = (
        "Rebuild game-state episodes, exposure, player intersections, and "
        "possession context from stored WhoScored payloads."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", required=True)
        parser.add_argument("--season", required=True)
        parser.add_argument("--match-id", action="append", default=[])

    def handle(self, *args, **options) -> None:
        try:
            competition_season = resolve_active_competition_season(
                options["competition"], options["season"]
            )
        except DjangoValidationError as error:
            raise CommandError("Unknown active competition-season.") from error

        matches = (
            ProviderMatch.objects.filter(
                provider=Provider.WHOSCORED,
                competition_season=competition_season,
            )
            .select_related("payload")
            .order_by("provider_match_id")
        )
        match_ids = options["match_id"]
        if match_ids:
            matches = matches.filter(provider_match_id__in=match_ids)
            if matches.count() != len(set(match_ids)):
                raise CommandError("Unknown affected WhoScored match id.")

        started = perf_counter()
        rebuilt = eligible = episodes = possessions = player_exposures = 0
        for provider_match in matches.iterator():
            try:
                stored = provider_match.payload
            except ProviderMatchPayload.DoesNotExist as error:
                raise CommandError(
                    f"Match {provider_match.provider_match_id} has no stored payload."
                ) from error
            if stored.storage_backend != ProviderPayloadStorage.DATABASE:
                raise CommandError(
                    f"Match {provider_match.provider_match_id} uses unsupported "
                    f"payload storage {stored.storage_backend!r}."
                )
            if stored.payload_gzip is None:
                raise CommandError(
                    f"Match {provider_match.provider_match_id} has no database payload."
                )
            try:
                wrapped = json.loads(gzip.decompress(bytes(stored.payload_gzip)))
                normalized = parse_match_payload(wrapped)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise CommandError(
                    f"Stored payload for match {provider_match.provider_match_id} "
                    "cannot be normalized."
                ) from error

            with transaction.atomic():
                replace_match_events(provider_match, normalized)
                provider_match.refresh_from_db()
                audit = provider_match.game_state
                match_player_exposures = ProviderMatchPlayerStateExposure.objects.filter(
                    player_interval__participation__provider_match=provider_match
                ).count()
                match_possessions = provider_match.possessions.count()
            player_exposures += match_player_exposures
            possessions += match_possessions
            rebuilt += 1
            eligible += int(audit.eligible)
            episodes += audit.episode_count

        elapsed = perf_counter() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Rebuilt game-state foundations for {rebuilt} matches "
                f"({eligible} eligible, {episodes} episodes, "
                f"{player_exposures} player exposures, {possessions} possessions) "
                f"in {elapsed:.3f}s."
            )
        )
