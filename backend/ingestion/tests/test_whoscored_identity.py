from __future__ import annotations

from datetime import datetime, timezone

from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    MatchEventType,
    MatchMethod,
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    Season,
    UnmatchedProviderPlayer,
    UnmatchedProviderTeam,
)
from ingestion.services.identity import (
    EventIdentityPublicationError,
    apply_manual_player_resolution,
    apply_manual_team_resolution,
    attach_provider_match_identities,
    build_event_identity_report,
    reattach_event_identities,
    record_event_identity_diagnostics,
    resolve_canonical_player,
    resolve_canonical_team,
    validate_event_identity_publication,
)


def create_slice() -> CompetitionSeason:
    competition = Competition.objects.create(
        name="Premier League",
        short_code="ENG1",
        country="England",
    )
    season = Season.objects.create(label="2025-26", sort_order=2026)
    return CompetitionSeason.objects.create(
        competition=competition,
        season=season,
        has_whoscored=True,
        whoscored_league="ENG-Premier League",
        whoscored_season="2526",
        whoscored_expected_match_count=380,
    )


class WhoScoredIdentityResolutionTests(TestCase):
    def setUp(self):
        self.competition_season = create_slice()
        self.run = IngestionRun.objects.create(
            kind=IngestionKind.WHOSCORED_FETCH,
            competition_season=self.competition_season,
        )
        self.provider_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id="match-1",
            competition_season=self.competition_season,
            kickoff_at=datetime(2025, 8, 16, 14, tzinfo=timezone.utc),
            home_provider_team_id="team-1",
            away_provider_team_id="team-2",
        )

    def test_unknown_whoscored_ids_remain_unresolved_without_creating_canonicals(self):
        player = resolve_canonical_player(
            competition_season=self.competition_season,
            provider=Provider.WHOSCORED,
            provider_player_id="player-1",
            display_name="Alex Example",
            run=self.run,
        )
        team = resolve_canonical_team(
            competition_season=self.competition_season,
            provider=Provider.WHOSCORED,
            provider_team_id="team-1",
            team_name="Example FC",
            run=self.run,
        )

        self.assertIsNone(player)
        self.assertIsNone(team)
        self.assertFalse(CanonicalPlayer.objects.exists())
        self.assertFalse(CanonicalTeam.objects.exists())
        unmatched_player = UnmatchedProviderPlayer.objects.get()
        unmatched_team = UnmatchedProviderTeam.objects.get()
        self.assertEqual(unmatched_player.player_name, "Alex Example")
        self.assertEqual(unmatched_player.first_seen_run, self.run)
        self.assertEqual(unmatched_team.team_name, "Example FC")
        self.assertEqual(unmatched_team.first_seen_run, self.run)

        later_run = IngestionRun.objects.create(
            kind=IngestionKind.WHOSCORED_FETCH,
            competition_season=self.competition_season,
        )
        resolve_canonical_player(
            competition_season=self.competition_season,
            provider=Provider.WHOSCORED,
            provider_player_id="player-1",
            display_name="Updated source name",
            run=later_run,
        )
        unmatched_player.refresh_from_db()
        self.assertEqual(unmatched_player.player_name, "Updated source name")
        self.assertEqual(unmatched_player.first_seen_run, self.run)

    def test_known_mappings_attach_without_overwriting_canonical_metadata(self):
        player = CanonicalPlayer.objects.create(
            reep_id="reep-player",
            display_name="Authoritative Player Name",
        )
        team = CanonicalTeam.objects.create(
            reep_id="reep-team",
            name="Authoritative Team Name",
        )
        ProviderPlayerMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_player_id="player-1",
            canonical_player=player,
            match_method=MatchMethod.MANUAL,
        )
        ProviderTeamMapping.objects.create(
            provider=Provider.WHOSCORED,
            provider_team_id="team-1",
            canonical_team=team,
            match_method=MatchMethod.MANUAL,
        )
        ProviderMatchEvent.objects.bulk_create(
            [
                ProviderMatchEvent(
                    provider_match=self.provider_match,
                    event_index=0,
                    provider_team_id="team-1",
                    provider_player_id="player-1",
                    minute=1,
                    second=0,
                    event_type=MatchEventType.PASS,
                ),
                ProviderMatchEvent(
                    provider_match=self.provider_match,
                    event_index=1,
                    provider_team_id="team-2",
                    provider_player_id="player-2",
                    minute=2,
                    second=0,
                    event_type=MatchEventType.PASS,
                ),
            ]
        )

        report = attach_provider_match_identities(
            self.provider_match,
            run=self.run,
            team_names={"team-1": "Source Team", "team-2": "Unknown Team"},
            player_names={"player-1": "Source Player", "player-2": "Unknown Player"},
        )

        first_event, second_event = self.provider_match.events.order_by("event_index")
        self.provider_match.refresh_from_db()
        player.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual(first_event.player, player)
        self.assertEqual(first_event.team, team)
        self.assertIsNone(second_event.player)
        self.assertIsNone(second_event.team)
        self.assertEqual(self.provider_match.home_team, team)
        self.assertIsNone(self.provider_match.away_team)
        self.assertEqual(player.display_name, "Authoritative Player Name")
        self.assertEqual(team.name, "Authoritative Team Name")
        self.assertEqual(report.volume.total_events, 2)
        self.assertEqual(report.volume.unmapped_player_events, 1)
        self.assertTrue(
            UnmatchedProviderPlayer.objects.filter(
                provider_player_id="player-2",
                player_name="Unknown Player",
                first_seen_run=self.run,
            ).exists()
        )
        self.assertTrue(
            UnmatchedProviderTeam.objects.filter(
                provider_team_id="team-2",
                team_name="Unknown Team",
                first_seen_run=self.run,
            ).exists()
        )

    def test_manual_resolution_reattaches_matches_and_events_idempotently(self):
        ProviderMatchEvent.objects.create(
            provider_match=self.provider_match,
            event_index=0,
            provider_team_id="team-1",
            provider_player_id="player-1",
            minute=1,
            second=0,
            event_type=MatchEventType.PASS,
        )
        attach_provider_match_identities(self.provider_match, run=self.run)
        unmatched_player = UnmatchedProviderPlayer.objects.get(provider_player_id="player-1")
        unmatched_team = UnmatchedProviderTeam.objects.get(provider_team_id="team-1")
        player = CanonicalPlayer.objects.create(display_name="Resolved Player")
        team = CanonicalTeam.objects.create(name="Resolved Team")

        apply_manual_player_resolution(unmatched_player, player)
        apply_manual_team_resolution(unmatched_team, team)
        first_counts = reattach_event_identities(self.competition_season)
        second_counts = reattach_event_identities(self.competition_season)

        event = self.provider_match.events.get()
        self.provider_match.refresh_from_db()
        self.assertEqual(event.player, player)
        self.assertEqual(event.team, team)
        self.assertEqual(self.provider_match.home_team, team)
        self.assertEqual(first_counts, (1, 1))
        self.assertEqual(second_counts, first_counts)
        self.assertEqual(
            ProviderPlayerMapping.objects.get(provider_player_id="player-1").canonical_player,
            player,
        )
        self.assertEqual(
            ProviderTeamMapping.objects.get(provider_team_id="team-1").canonical_team,
            team,
        )


class WhoScoredIdentityDiagnosticTests(TestCase):
    def setUp(self):
        self.competition_season = create_slice()
        self.team = CanonicalTeam.objects.create(name="Mapped Team")
        self.player = CanonicalPlayer.objects.create(display_name="Mapped Player")

    def create_events(self, *, unmapped_count: int, total: int = 100) -> None:
        provider_match = ProviderMatch.objects.create(
            provider=Provider.WHOSCORED,
            provider_match_id=f"match-{ProviderMatch.objects.count()}",
            competition_season=self.competition_season,
            kickoff_at=datetime(2025, 8, 16, 14, tzinfo=timezone.utc),
            home_provider_team_id="team-1",
            away_provider_team_id="team-2",
        )
        ProviderMatchEvent.objects.bulk_create(
            [
                ProviderMatchEvent(
                    provider_match=provider_match,
                    event_index=index,
                    provider_team_id="team-1" if index % 2 == 0 else "team-2",
                    provider_player_id=f"player-{index}",
                    team=self.team,
                    player=None if index < unmapped_count else self.player,
                    minute=index,
                    second=0,
                    event_type=MatchEventType.PASS,
                )
                for index in range(total)
            ]
        )

    def test_warning_and_publication_boundaries_are_strict(self):
        cases = (
            (0, False, False),
            (1, False, False),
            (2, True, False),
            (5, True, False),
            (6, True, True),
        )
        for unmapped_count, warning, publication_failure in cases:
            with self.subTest(unmapped_count=unmapped_count):
                ProviderMatch.objects.all().delete()
                self.create_events(unmapped_count=unmapped_count)
                report = build_event_identity_report(self.competition_season)
                self.assertEqual(report.warning, warning)
                self.assertEqual(report.publication_failure, publication_failure)
                if publication_failure:
                    with self.assertRaises(EventIdentityPublicationError):
                        validate_event_identity_publication(report)
                else:
                    validate_event_identity_publication(report)

    def test_report_reconciles_by_match_team_and_slice_and_records_on_run(self):
        self.create_events(unmapped_count=2, total=40)
        self.create_events(unmapped_count=3, total=60)
        ProviderMatchEvent.objects.create(
            provider_match=ProviderMatch.objects.first(),
            event_index=100,
            provider_team_id="team-1",
            provider_player_id=None,
            team=self.team,
            player=None,
            minute=90,
            second=0,
            event_type=MatchEventType.ADMINISTRATIVE,
        )

        report = build_event_identity_report(self.competition_season)

        self.assertEqual(report.volume.total_events, 101)
        self.assertEqual(report.volume.player_events, 100)
        self.assertEqual(report.volume.mapped_player_events, 95)
        self.assertEqual(report.volume.unmapped_player_events, 5)
        self.assertEqual(report.volume.playerless_events, 1)
        self.assertEqual(
            sum(group["total_events"] for group in report.by_match),
            report.volume.total_events,
        )
        self.assertEqual(
            sum(group["total_events"] for group in report.by_team),
            report.volume.total_events,
        )
        self.assertEqual(
            sum(group["unmapped_player_events"] for group in report.by_match),
            report.volume.unmapped_player_events,
        )
        self.assertEqual(
            sum(group["unmapped_player_events"] for group in report.by_team),
            report.volume.unmapped_player_events,
        )

        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        record_event_identity_diagnostics(run, report)
        run.refresh_from_db()
        self.assertEqual(run.stats["event_identity"], report.as_dict())
