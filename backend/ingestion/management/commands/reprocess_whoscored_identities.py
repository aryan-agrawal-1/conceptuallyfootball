from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ingestion.competition_scope import resolve_active_competition_season
from ingestion.models import (
    MatchMethod,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderTeamMapping,
    UnmatchedProviderTeam,
)
from ingestion.services.identity import (
    _candidate_player_evidence,
    attach_provider_match_identities,
    build_event_identity_report,
)
from ingestion.whoscored_identity_manifest import WHOSCORED_TEAM_MAPPINGS


class Command(BaseCommand):
    help = "Apply checked-in WhoScored team mappings and reprocess event identities."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--competition", required=True)
        parser.add_argument("--season", required=True)

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        try:
            competition_season = resolve_active_competition_season(
                options["competition"], options["season"]
            )
        except DjangoValidationError as error:
            raise CommandError("Unknown active competition-season.") from error
        scope = (
            competition_season.competition.short_code,
            competition_season.season.label,
        )
        configured = WHOSCORED_TEAM_MAPPINGS.get(scope)
        if not configured:
            raise CommandError("No checked-in WhoScored team mappings exist for this scope.")

        schedule_team_ids = set(
            ProviderMatch.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
            ).values_list("home_provider_team_id", flat=True)
        )
        schedule_team_ids.update(
            ProviderMatch.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
            ).values_list("away_provider_team_id", flat=True)
        )
        missing = sorted(schedule_team_ids - set(configured))
        if missing:
            raise CommandError(f"WhoScored schedule contains unmapped team IDs: {missing}")

        for whoscored_team_id, sofascore_team_id in configured.items():
            try:
                canonical_team = ProviderTeamMapping.objects.get(
                    provider=Provider.SOFASCORE,
                    provider_team_id=sofascore_team_id,
                ).canonical_team
            except ProviderTeamMapping.DoesNotExist as error:
                raise CommandError(
                    f"SofaScore team {sofascore_team_id} has no canonical mapping."
                ) from error
            ProviderTeamMapping.objects.update_or_create(
                provider=Provider.WHOSCORED,
                provider_team_id=whoscored_team_id,
                defaults={
                    "canonical_team": canonical_team,
                    "match_method": MatchMethod.MANUAL,
                },
            )
            UnmatchedProviderTeam.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
                provider_team_id=whoscored_team_id,
            ).update(resolved_team=canonical_team)
            UnmatchedProviderTeam.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
                provider_team_id=whoscored_team_id,
            ).update(resolved_at=timezone.now())
            ProviderMatchEvent.objects.filter(
                provider_match__competition_season=competition_season,
                provider_match__provider=Provider.WHOSCORED,
                provider_team_id=whoscored_team_id,
            ).update(team=canonical_team)
            ProviderMatch.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
                home_provider_team_id=whoscored_team_id,
            ).update(home_team=canonical_team)
            ProviderMatch.objects.filter(
                competition_season=competition_season,
                provider=Provider.WHOSCORED,
                away_provider_team_id=whoscored_team_id,
            ).update(away_team=canonical_team)

        candidate_evidence = _candidate_player_evidence(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
        )
        matches = ProviderMatch.objects.filter(
            competition_season=competition_season,
            provider=Provider.WHOSCORED,
            payload__isnull=False,
        ).order_by("provider_match_id")
        reprocessed = 0
        for provider_match in matches.iterator():
            attach_provider_match_identities(
                provider_match,
                include_report=False,
                candidate_evidence=candidate_evidence,
            )
            reprocessed += 1

        report = build_event_identity_report(competition_season)
        self.stdout.write(
            self.style.SUCCESS(
                f"Reprocessed {reprocessed} matches with {len(configured)} team mappings: "
                f"{report.volume.mapped_team_events}/{report.volume.total_events} team events, "
                f"{report.volume.mapped_player_events}/{report.volume.player_events} player events."
            )
        )
