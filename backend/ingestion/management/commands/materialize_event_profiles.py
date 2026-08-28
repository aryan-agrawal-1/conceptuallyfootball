from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from ingestion.competition_scope import resolve_active_competition_season
from ingestion.models import CompetitionSeason, IngestionKind, IngestionRun, IngestionRunStatus, Provider, ProviderMatch
from ingestion.services.event_profiles import materialize_event_profiles
from ingestion.services.player_season_roles import materialize_player_season_roles


class Command(BaseCommand):
    help = "Rebuild WhoScored event profiles from normalized database events."

    def add_arguments(self, parser) -> None:
        parser.add_argument("competition_season_id", type=int, nargs="?", help="CompetitionSeason primary key.")
        parser.add_argument("--competition", help="Competition code, e.g. ENG1.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")
        parser.add_argument("--affected-player-id", action="append", type=int, default=[])
        parser.add_argument("--affected-team-id", action="append", type=int, default=[])
        parser.add_argument("--affected-match-id", action="append", default=[], help="WhoScored provider match id to recompute.")
        parser.add_argument(
            "--internal-pilot",
            action="store_true",
            help="Materialize an incomplete pilot on an isolated delivery branch.",
        )

    def handle(self, *args, **options) -> None:
        cid = options["competition_season_id"]
        competition, season = (options.get("competition") or "").strip(), (options.get("season") or "").strip()
        if cid and (competition or season):
            raise CommandError("Use either competition_season_id or --competition/--season, not both.")
        if not cid and not (competition and season):
            raise CommandError("Provide competition_season_id or both --competition/--season.")
        if competition.upper() in {"BIG5", "ALL"}:
            raise CommandError("Event profiles require one concrete competition season.")
        try:
            competition_season = (CompetitionSeason.objects.select_related("competition", "season").get(pk=cid)
                                  if cid else resolve_active_competition_season(competition, season))
        except (CompetitionSeason.DoesNotExist, DjangoValidationError) as exc:
            raise CommandError("Unknown competition-season.") from exc
        if not competition_season.supports_whoscored:
            raise CommandError("WhoScored is not configured for this competition-season.")
        players, teams, match_ids = options["affected_player_id"], options["affected_team_id"], options["affected_match_id"]
        if match_ids and (players or teams):
            raise CommandError("Use --affected-match-id or explicit affected entity ids, not both.")
        if match_ids:
            matches = list(ProviderMatch.objects.filter(competition_season=competition_season, provider=Provider.WHOSCORED,
                                                        provider_match_id__in=match_ids))
            if len(matches) != len(set(match_ids)):
                raise CommandError("Unknown affected WhoScored match id.")
            # The current event set cannot reveal identities removed by a
            # corrected payload. Fall back to a full deterministic rebuild;
            # lifecycle callers can still pass its explicit old-union-new IDs
            # directly to the service for a narrow affected rebuild.
            players, teams = [], []
        if bool(players) != bool(teams):
            raise CommandError("Affected rebuild requires both --affected-player-id and --affected-team-id.")
        run = IngestionRun.objects.create(kind=IngestionKind.EVENT_PROFILES, competition_season=competition_season,
                                          status=IngestionRunStatus.PENDING)
        materialize_event_profiles(competition_season, run=run,
                                   affected_player_ids=players or None, affected_team_ids=teams or None,
                                   internal_pilot=options["internal_pilot"])
        run.refresh_from_db()
        if run.status != IngestionRunStatus.SUCCESS:
            raise CommandError(run.error_detail or "Event profile materialization failed")
        role_result = materialize_player_season_roles(
            competition_season,
            affected_player_ids=players or None,
            affected_team_ids=teams or None,
        )
        run.stats = run.stats | {"player_season_roles": role_result}
        run.save(update_fields=["stats"])
        self.stdout.write(self.style.SUCCESS(f"Event profiles run {run.id} succeeded ({run.stats})"))
