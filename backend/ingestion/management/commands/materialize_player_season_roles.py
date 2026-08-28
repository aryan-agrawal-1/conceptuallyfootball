from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from ingestion.competition_scope import resolve_active_competition_season
from ingestion.models import CompetitionSeason
from ingestion.services.player_season_roles import materialize_player_season_roles


class Command(BaseCommand):
    help = "Extract player-team role features and score the complete competition-season cohort."

    def add_arguments(self, parser) -> None:
        parser.add_argument("competition_season_id", type=int, nargs="?", help="CompetitionSeason primary key.")
        parser.add_argument("--competition", help="Competition code, e.g. ENG1.")
        parser.add_argument("--season", help="Season label, e.g. 2025-26.")
        parser.add_argument("--affected-player-id", action="append", type=int, default=[])
        parser.add_argument("--affected-team-id", action="append", type=int, default=[])
        parser.add_argument(
            "--score-only",
            action="store_true",
            help="Reuse current versioned feature snapshots and only rerun cheap cohort scoring.",
        )
        parser.add_argument(
            "--score-events-only",
            action="store_true",
            help="Refresh direct goal-assist evidence in snapshots, then rerun cohort scoring.",
        )

    def handle(self, *args, **options) -> None:
        competition_season_id = options["competition_season_id"]
        competition = (options.get("competition") or "").strip()
        season = (options.get("season") or "").strip()
        if competition_season_id and (competition or season):
            raise CommandError("Use either competition_season_id or --competition/--season, not both.")
        if not competition_season_id and not (competition and season):
            raise CommandError("Provide competition_season_id or both --competition/--season.")
        if competition.upper() in {"BIG5", "ALL"}:
            raise CommandError("Player roles require one concrete competition season.")
        try:
            competition_season = (
                CompetitionSeason.objects.select_related("competition", "season").get(pk=competition_season_id)
                if competition_season_id
                else resolve_active_competition_season(competition, season)
            )
        except (CompetitionSeason.DoesNotExist, DjangoValidationError) as exc:
            raise CommandError("Unknown competition-season.") from exc
        players = options["affected_player_id"] or None
        teams = options["affected_team_id"] or None
        if options["score_only"] and options["score_events_only"]:
            raise CommandError("--score-only and --score-events-only are mutually exclusive.")
        result = materialize_player_season_roles(
            competition_season,
            affected_player_ids=players,
            affected_team_ids=teams,
            score_only=options["score_only"],
            score_events_only=options["score_events_only"],
        )
        self.stdout.write(self.style.SUCCESS(f"Player-season roles succeeded ({result})"))
