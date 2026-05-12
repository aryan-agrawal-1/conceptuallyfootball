from __future__ import annotations

from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    MatchMethod,
    MetadataAuthority,
    MergedPlayerSeason,
    PlayerDataMode,
    Provider,
    ProviderPlayerMapping,
    ProviderTeamMapping,
    ReepPlayerRow,
    ReepTeamRow,
    Season,
    SofascorePlayerSeasonSource,
    UnderstatPlayerSeasonSource,
    UnmatchedProviderPlayer,
)
from ingestion.services.identity import reattach_slice_identities, resolve_canonical_player, resolve_canonical_team
from ingestion.services.ingest import run_merge_job
from ingestion.services.merge import execute_merge_for_slice
from ingestion.position import normalize_position_group
from ingestion.services.validation import ValidationResult


def _slice():
    comp = Competition.objects.create(name="Premier League", short_code="EPL", country="England")
    season = Season.objects.create(label="2025-26", sort_order=2026)
    return CompetitionSeason.objects.create(
        competition=comp,
        season=season,
        understat_league="EPL",
        understat_season_year="2025",
        sofascore_unique_tournament_id=17,
        sofascore_season_id=76986,
    )


class IdentityQuarantineTests(TestCase):
    def test_provider_native_canonical_when_no_reep_row(self):
        cs = _slice()
        p = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="999",
            display_name="Ghost",
            run=None,
        )
        self.assertIsNotNone(p)
        assert p is not None
        self.assertIsNone(p.reep_id)
        self.assertEqual(p.display_name, "Ghost")
        mapping = ProviderPlayerMapping.objects.get(
            provider=Provider.UNDERSTAT,
            provider_player_id="999",
        )
        self.assertEqual(mapping.canonical_player, p)
        self.assertFalse(
            UnmatchedProviderPlayer.objects.filter(
                competition_season=cs,
                provider=Provider.UNDERSTAT,
                provider_player_id="999",
            ).exists()
        )

    def test_auto_match_creates_canonical_and_mapping(self):
        cs = _slice()
        ReepPlayerRow.objects.create(
            reep_id="r1",
            full_name="Test Player",
            understat_player_id="42",
            sofascore_player_id="99",
        )
        p = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="42",
            display_name="Test Player",
            run=None,
        )
        self.assertIsNotNone(p)
        self.assertEqual(p.reep_id, "r1")
        m = ProviderPlayerMapping.objects.get(provider=Provider.UNDERSTAT, provider_player_id="42")
        self.assertEqual(m.match_method, MatchMethod.AUTO)

    def test_unique_cross_provider_name_match_creates_canonical_without_reep(self):
        cs = _slice()
        us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        us_src = UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=us_run,
            provider_player_id="u-1",
            provider_team_id="",
            player_name="Ben Example",
            team_name="Alpha FC",
            position_raw="M",
        )
        unresolved = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="u-1",
            display_name="Ben Example",
            run=us_run,
        )
        self.assertIsNotNone(unresolved)
        assert unresolved is not None
        self.assertIsNone(unresolved.reep_id)
        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.UNDERSTAT,
                provider_player_id="u-1",
            ).canonical_player,
            unresolved,
        )

        ss_src = SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=ss_run,
            provider_player_id="s-1",
            provider_team_id="",
            player_name="Ben Example",
            team_name="Alpha FC",
            position_raw="M",
        )
        resolved = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.SOFASCORE,
            provider_player_id="s-1",
            display_name="Ben Example",
            run=ss_run,
        )

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertIsNone(resolved.reep_id)
        self.assertEqual(resolved, unresolved)
        ss_src.canonical_player = resolved
        ss_src.save(update_fields=["canonical_player"])

        us_src.refresh_from_db()
        ss_src.refresh_from_db()
        self.assertEqual(us_src.canonical_player, resolved)
        self.assertEqual(ss_src.canonical_player, resolved)

        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.UNDERSTAT,
                provider_player_id="u-1",
            ).canonical_player,
            resolved,
        )
        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.SOFASCORE,
                provider_player_id="s-1",
            ).canonical_player,
            resolved,
        )

        self.assertFalse(
            UnmatchedProviderPlayer.objects.filter(
                competition_season=cs,
                provider__in=[Provider.UNDERSTAT, Provider.SOFASCORE],
            ).exists()
        )

    def test_reep_backed_row_absorbs_existing_provider_native_counterpart(self):
        cs = _slice()
        us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        us_src = UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=us_run,
            provider_player_id="u-1",
            provider_team_id="",
            player_name="Lamine Yamal",
            team_name="Barcelona",
            position_raw="F",
        )
        native = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="u-1",
            display_name="Lamine Yamal",
            run=us_run,
        )
        assert native is not None
        us_src.canonical_player = native
        us_src.save(update_fields=["canonical_player"])

        ReepPlayerRow.objects.create(
            reep_id="reep_lamine",
            full_name="Lamine Yamal",
            sofascore_player_id="s-1",
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=ss_run,
            provider_player_id="s-1",
            provider_team_id="",
            player_name="Lamine Yamal",
            team_name="FC Barcelona",
            position_raw="F",
        )

        resolved = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.SOFASCORE,
            provider_player_id="s-1",
            display_name="Lamine Yamal",
            run=ss_run,
        )

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.reep_id, "reep_lamine")
        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.UNDERSTAT,
                provider_player_id="u-1",
            ).canonical_player,
            resolved,
        )
        us_src.refresh_from_db()
        self.assertEqual(us_src.canonical_player, resolved)

    def test_reep_full_name_absorbs_provider_native_counterpart_when_source_name_differs(self):
        cs = _slice()
        us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        us_src = UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=us_run,
            provider_player_id="13051",
            provider_team_id="",
            player_name="Matias Fernandez-Pardo",
            team_name="Lille",
            position_raw="F",
        )
        native = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="13051",
            display_name="Matias Fernandez-Pardo",
            run=us_run,
        )
        assert native is not None
        us_src.canonical_player = native
        us_src.save(update_fields=["canonical_player"])

        ReepPlayerRow.objects.create(
            reep_id="reep_matias",
            full_name="Matias Fernandez-Pardo",
            sofascore_player_id="1149144",
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=ss_run,
            provider_player_id="1149144",
            provider_team_id="",
            player_name="Matías Fernández",
            team_name="Lille",
            position_raw="F",
        )

        resolved = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.SOFASCORE,
            provider_player_id="1149144",
            display_name="Matías Fernández",
            run=ss_run,
        )

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.reep_id, "reep_matias")
        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.UNDERSTAT,
                provider_player_id="13051",
            ).canonical_player,
            resolved,
        )
        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.SOFASCORE,
                provider_player_id="1149144",
            ).canonical_player,
            resolved,
        )
        us_src.refresh_from_db()
        self.assertEqual(us_src.canonical_player, resolved)

    def test_cross_provider_name_match_refuses_ambiguous_name(self):
        cs = _slice()
        us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=us_run,
            provider_player_id="u-1",
            provider_team_id="",
            player_name="Alex Example",
            team_name="Alpha FC",
            position_raw="M",
        )
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=us_run,
            provider_player_id="u-2",
            provider_team_id="",
            player_name="Alex Example",
            team_name="Beta FC",
            position_raw="D",
        )
        resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="u-1",
            display_name="Alex Example",
            run=us_run,
        )
        resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="u-2",
            display_name="Alex Example",
            run=us_run,
        )

        SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=ss_run,
            provider_player_id="s-1",
            provider_team_id="",
            player_name="Alex Example",
            team_name="Alpha FC",
            position_raw="M",
        )
        resolved = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.SOFASCORE,
            provider_player_id="s-1",
            display_name="Alex Example",
            run=ss_run,
        )

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertIsNone(resolved.reep_id)
        self.assertEqual(resolved.display_name, "Alex Example")
        self.assertEqual(
            ProviderPlayerMapping.objects.get(
                provider=Provider.SOFASCORE,
                provider_player_id="s-1",
            ).canonical_player,
            resolved,
        )
        self.assertNotIn(
            resolved,
            [
                ProviderPlayerMapping.objects.get(
                    provider=Provider.UNDERSTAT,
                    provider_player_id="u-1",
                ).canonical_player,
                ProviderPlayerMapping.objects.get(
                    provider=Provider.UNDERSTAT,
                    provider_player_id="u-2",
                ).canonical_player,
            ],
        )
        self.assertFalse(
            UnmatchedProviderPlayer.objects.filter(
                competition_season=cs,
                provider=Provider.SOFASCORE,
                provider_player_id="s-1",
            ).exists()
        )

    def test_team_auto_mapping_heals_after_reep_correction(self):
        cs = _slice()
        wrong_team = CanonicalTeam.objects.create(name="SC Freiburg", reep_id="reef_wrong")
        right_team = CanonicalTeam.objects.create(name="Brighton & Hove Albion F.C.", reep_id="reef_right")
        ProviderTeamMapping.objects.create(
            canonical_team=wrong_team,
            provider=Provider.UNDERSTAT,
            provider_team_id="220",
            match_method=MatchMethod.AUTO,
        )
        ReepTeamRow.objects.create(
            reep_id="reef_right",
            name="Brighton & Hove Albion F.C.",
            understat_team_id="220",
        )

        resolved = resolve_canonical_team(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_team_id="220",
            team_name="Brighton",
            run=None,
        )

        self.assertEqual(resolved, right_team)
        mapping = ProviderTeamMapping.objects.get(provider=Provider.UNDERSTAT, provider_team_id="220")
        self.assertEqual(mapping.canonical_team, right_team)


class MergeTests(TestCase):
    def setUp(self):
        self.cs = _slice()
        ReepPlayerRow.objects.create(
            reep_id="rp1",
            full_name="Alice",
            understat_player_id="1",
            sofascore_player_id="10",
        )
        ReepTeamRow.objects.create(
            reep_id="rt1",
            name="Alpha FC",
            understat_team_id="100",
            sofascore_team_id="200",
        )
        self.cp = CanonicalPlayer.objects.create(display_name="Alice", reep_id="rp1")
        self.ct = CanonicalTeam.objects.create(name="Alpha FC", reep_id="rt1")
        self.us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=self.cs,
            status=IngestionRunStatus.SUCCESS,
        )
        self.ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=self.cs,
            status=IngestionRunStatus.SUCCESS,
        )
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.us_run,
            provider_player_id="1",
            provider_team_id="100",
            player_name="Alice",
            team_name="Alpha FC",
            position_raw="F",
            games=10,
            minutes=900,
            goals=5,
            xg=4.2,
            canonical_player=self.cp,
            canonical_team=self.ct,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.ss_run,
            provider_player_id="10",
            provider_team_id="200",
            player_name="Alice",
            team_name="Alpha FC",
            position_raw="F",
            tackles=20,
            interceptions=3,
            canonical_player=self.cp,
            canonical_team=self.ct,
        )

    def test_merge_field_ownership_and_null_partial(self):
        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=self.cs,
            status=IngestionRunStatus.PENDING,
        )
        execute_merge_for_slice(self.cs, merge_run=merge_run)
        row = MergedPlayerSeason.objects.get(
            competition_season=self.cs,
            canonical_player=self.cp,
            is_current=True,
        )
        self.assertEqual(row.us_goals, 5)
        self.assertEqual(row.us_xg, 4.2)
        self.assertEqual(row.ss_tackles, 20)
        self.assertIsNone(row.ss_saves)
        self.assertEqual(row.metadata_authority, MetadataAuthority.UNDERSTAT)

    def test_merge_soft_retires_previous(self):
        execute_merge_for_slice(self.cs, merge_run=None)
        self.assertEqual(
            MergedPlayerSeason.objects.filter(competition_season=self.cs, is_current=True).count(),
            1,
        )
        execute_merge_for_slice(self.cs, merge_run=None)
        self.assertEqual(
            MergedPlayerSeason.objects.filter(competition_season=self.cs, is_current=True).count(),
            1,
        )
        self.assertEqual(
            MergedPlayerSeason.objects.filter(competition_season=self.cs, is_current=False).count(),
            1,
        )

    def test_merge_prefers_reep_detail_over_understat_goalkeeper_substitute_position(self):
        self.cp.provider_mappings.all().delete()
        self.cp.delete()
        ReepPlayerRow.objects.create(
            reep_id="rp_gk",
            full_name="Keeper",
            understat_player_id="3",
            sofascore_player_id="30",
            position="goalkeeper",
            position_detail="Goalkeeper",
        )
        cp = CanonicalPlayer.objects.create(display_name="Keeper", reep_id="rp_gk")
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.us_run,
            provider_player_id="3",
            provider_team_id="100",
            player_name="Keeper",
            team_name="Alpha FC",
            position_raw="GK S",
            canonical_player=cp,
            canonical_team=self.ct,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.ss_run,
            provider_player_id="30",
            provider_team_id="200",
            player_name="Keeper",
            team_name="Alpha FC",
            position_raw="",
            canonical_player=cp,
            canonical_team=self.ct,
        )

        execute_merge_for_slice(self.cs, merge_run=None)
        row = MergedPlayerSeason.objects.get(
            competition_season=self.cs,
            canonical_player=cp,
            is_current=True,
        )
        self.assertEqual(row.position_group, "GK")
        self.assertEqual(row.native_position, "Goalkeeper")

    def test_merge_falls_back_to_reep_position_when_understat_only_has_substitute_flag(self):
        self.cp.provider_mappings.all().delete()
        self.cp.delete()
        ReepPlayerRow.objects.create(
            reep_id="rp_mid",
            full_name="Mid Example",
            understat_player_id="4",
            sofascore_player_id="40",
            position="midfielder",
            position_detail="Defensive Midfield",
        )
        cp = CanonicalPlayer.objects.create(display_name="Mid Example", reep_id="rp_mid")
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.us_run,
            provider_player_id="4",
            provider_team_id="100",
            player_name="Mid Example",
            team_name="Alpha FC",
            position_raw="S",
            canonical_player=cp,
            canonical_team=self.ct,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.ss_run,
            provider_player_id="40",
            provider_team_id="200",
            player_name="Mid Example",
            team_name="Alpha FC",
            position_raw="",
            canonical_player=cp,
            canonical_team=self.ct,
        )

        execute_merge_for_slice(self.cs, merge_run=None)
        row = MergedPlayerSeason.objects.get(
            competition_season=self.cs,
            canonical_player=cp,
            is_current=True,
        )
        self.assertEqual(row.position_group, "MID")
        self.assertEqual(row.native_position, "Defensive Midfield")

    def test_merge_prefers_sofascore_position_over_reep_and_understat(self):
        self.cp.provider_mappings.all().delete()
        self.cp.delete()
        ReepPlayerRow.objects.create(
            reep_id="rp_wide",
            full_name="Wide Example",
            understat_player_id="5",
            sofascore_player_id="50",
            position="midfielder",
            position_detail="Central Midfield",
        )
        cp = CanonicalPlayer.objects.create(display_name="Wide Example", reep_id="rp_wide")
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.us_run,
            provider_player_id="5",
            provider_team_id="100",
            player_name="Wide Example",
            team_name="Alpha FC",
            position_raw="F M",
            canonical_player=cp,
            canonical_team=self.ct,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.ss_run,
            provider_player_id="50",
            provider_team_id="200",
            player_name="Wide Example",
            team_name="Alpha FC",
            position_raw="RW",
            canonical_player=cp,
            canonical_team=self.ct,
        )

        execute_merge_for_slice(self.cs, merge_run=None)
        row = MergedPlayerSeason.objects.get(
            competition_season=self.cs,
            canonical_player=cp,
            is_current=True,
        )
        self.assertEqual(row.position_group, "FWD")
        self.assertEqual(row.native_position, "Right Winger")

    def test_merge_canonicalizes_native_position_labels(self):
        self.cp.provider_mappings.all().delete()
        self.cp.delete()
        ReepPlayerRow.objects.create(
            reep_id="rp_cb",
            full_name="Centre Back Example",
            understat_player_id="6",
            sofascore_player_id="60",
            position="defender",
            position_detail="centre-back",
        )
        cp = CanonicalPlayer.objects.create(display_name="Centre Back Example", reep_id="rp_cb")
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.us_run,
            provider_player_id="6",
            provider_team_id="100",
            player_name="Centre Back Example",
            team_name="Alpha FC",
            position_raw="D",
            canonical_player=cp,
            canonical_team=self.ct,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=self.cs,
            ingestion_run=self.ss_run,
            provider_player_id="60",
            provider_team_id="200",
            player_name="Centre Back Example",
            team_name="Alpha FC",
            position_raw="",
            canonical_player=cp,
            canonical_team=self.ct,
        )

        execute_merge_for_slice(self.cs, merge_run=None)
        row = MergedPlayerSeason.objects.get(
            competition_season=self.cs,
            canonical_player=cp,
            is_current=True,
        )
        self.assertEqual(row.position_group, "DEF")
        self.assertEqual(row.native_position, "Centre-Back")

    def test_merge_sofascore_primary_team_and_secondary_from_understat(self):
        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=self.cs,
            status=IngestionRunStatus.PENDING,
        )
        ct_bournemouth = CanonicalTeam.objects.create(name="Bournemouth", reep_id="reep_bou")
        ct_city = CanonicalTeam.objects.create(name="Manchester City", reep_id="reep_mci")
        ProviderTeamMapping.objects.create(
            canonical_team=ct_bournemouth,
            provider=Provider.UNDERSTAT,
            provider_team_id="60",
            match_method=MatchMethod.AUTO,
        )
        ProviderTeamMapping.objects.create(
            canonical_team=ct_city,
            provider=Provider.UNDERSTAT,
            provider_team_id="17",
            match_method=MatchMethod.AUTO,
        )
        ReepTeamRow.objects.create(
            reep_id="reep_bou",
            name="Bournemouth",
            understat_team_id="60",
            sofascore_team_id="60",
        )
        ReepTeamRow.objects.create(
            reep_id="reep_mci",
            name="Manchester City",
            understat_team_id="17",
            sofascore_team_id="17",
        )

        UnderstatPlayerSeasonSource.objects.filter(competition_season=self.cs).update(
            team_name="Bournemouth,Manchester City",
            provider_team_id="60",
            provider_team_ids=["60", "17"],
            canonical_team=ct_bournemouth,
        )
        SofascorePlayerSeasonSource.objects.filter(competition_season=self.cs).update(
            provider_team_id="17",
            team_name="Manchester City",
            canonical_team=ct_city,
        )

        execute_merge_for_slice(self.cs, merge_run=merge_run)
        row = MergedPlayerSeason.objects.get(
            competition_season=self.cs,
            canonical_player=self.cp,
            is_current=True,
        )
        self.assertEqual(row.canonical_display_team_id, ct_city.pk)
        self.assertEqual(row.secondary_display_team_ids, [ct_bournemouth.pk])


class PositionNormalizationTests(TestCase):
    def test_normalize_position_group_handles_goalkeeper_substitute_token(self):
        self.assertEqual(normalize_position_group("GK S"), "GK")

    def test_normalize_position_group_handles_hyphenated_fullback_role(self):
        self.assertEqual(normalize_position_group("Right-Back"), "DEF")

    def test_normalize_position_group_handles_sofascore_detailed_codes(self):
        self.assertEqual(normalize_position_group("DL"), "DEF")
        self.assertEqual(normalize_position_group("DC"), "DEF")
        self.assertEqual(normalize_position_group("MC"), "MID")
        self.assertEqual(normalize_position_group("AML"), "FWD")

    def test_normalize_position_group_leaves_plain_substitute_unknown(self):
        self.assertEqual(normalize_position_group("S"), "UNK")


class ManualOverrideTests(TestCase):
    def test_manual_mapping_allows_merge(self):
        cs = _slice()
        ReepPlayerRow.objects.create(
            reep_id="rp2",
            full_name="Bob",
            understat_player_id="2",
            sofascore_player_id=None,
        )
        cp = resolve_canonical_player(
            competition_season=cs,
            provider=Provider.UNDERSTAT,
            provider_player_id="2",
            display_name="Bob",
            run=None,
        )
        self.assertIsNotNone(cp)
        ProviderPlayerMapping.objects.create(
            canonical_player=cp,
            provider=Provider.SOFASCORE,
            provider_player_id="77",
            match_method=MatchMethod.MANUAL,
        )
        us_run = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=us_run,
            provider_player_id="2",
            provider_team_id="",
            player_name="Bob",
            team_name="Beta",
            position_raw="M",
            minutes=800,
            goals=1,
            canonical_player=cp,
            canonical_team=None,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=ss_run,
            provider_player_id="77",
            provider_team_id="",
            player_name="Bob",
            team_name="Beta",
            position_raw="M",
            minutes=800,
            tackles=5,
            canonical_player=cp,
            canonical_team=None,
        )
        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        execute_merge_for_slice(cs, merge_run=merge_run)
        row = MergedPlayerSeason.objects.get(
            competition_season=cs,
            canonical_player=cp,
            is_current=True,
        )
        self.assertEqual(row.us_goals, 1)
        self.assertEqual(row.ss_tackles, 5)


class ManagementCommandSharedLogicTests(TestCase):
    @override_settings(STATBALLER_INGEST_MIN_ROWS=1)
    @patch("ingestion.services.ingest.validate_understat_slice", return_value=ValidationResult(True, ""))
    @patch("ingestion.services.ingest.validate_sofascore_slice", return_value=ValidationResult(True, ""))
    @patch(
        "ingestion.services.ingest.fetch_league_players",
        return_value=[
            {
                "id": "1",
                "player_name": "A",
                "team_title": "T",
                "team_id": "",
                "provider_team_ids": [],
                "games": "38",
                "time": "3000",
            }
        ],
    )
    @patch(
        "ingestion.services.ingest.fetch_full_season_statistics",
        return_value={
            10: {
                "_player": {"id": 10, "name": "A", "position": "M"},
                "_team": {"id": 1, "name": "T"},
                "summary:rating": 6.8,
                "defence:tackles": 10,
            }
        },
    )
    def test_merge_command_requires_both_providers(
        self,
        _mock_fetch_full,
        _mock_fetch_league,
        _mock_validate_ss,
        _mock_validate_us,
    ):
        cs = _slice()
        ReepPlayerRow.objects.create(
            reep_id="x",
            full_name="A",
            understat_player_id="1",
            sofascore_player_id="10",
        )
        ReepTeamRow.objects.create(
            reep_id="y",
            name="T",
            understat_team_id="",
            sofascore_team_id="1",
        )
        from ingestion.services.ingest import ingest_sofascore_slice, ingest_understat_slice

        ur = IngestionRun.objects.create(
            kind=IngestionKind.UNDERSTAT,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        sr = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        ingest_understat_slice(cs, run=ur)
        ingest_sofascore_slice(cs, run=sr)
        mr = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )
        run_merge_job(cs, run=mr)
        mr.refresh_from_db()
        self.assertEqual(mr.status, IngestionRunStatus.SUCCESS)

    def test_seed_command_upserts_epl_to_eng1(self):
        comp = Competition.objects.create(name="Premier League", short_code="EPL", country="England")
        season = Season.objects.create(label="2025-26", sort_order=1)
        CompetitionSeason.objects.create(
            competition=comp,
            season=season,
            understat_league="EPL",
            understat_season_year="2025",
            sofascore_unique_tournament_id=17,
            sofascore_season_id=1,
        )

        call_command("seed_competition_slices")

        comp.refresh_from_db()
        self.assertEqual(comp.short_code, "ENG1")
        cs = CompetitionSeason.objects.get(competition=comp, season__label="2025-26")
        self.assertEqual(cs.player_data_mode, PlayerDataMode.FULL_MERGE)
        self.assertEqual(cs.sofascore_season_id, 76986)

    def test_run_merge_job_allows_sofascore_only_slices(self):
        comp = Competition.objects.create(name="Championship", short_code="ENG2", country="England")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        cs = CompetitionSeason.objects.create(
            competition=comp,
            season=season,
            player_data_mode=PlayerDataMode.SOFASCORE_ONLY,
            has_understat=False,
            has_sofascore=True,
            understat_league=None,
            understat_season_year=None,
            sofascore_unique_tournament_id=18,
            sofascore_season_id=77347,
        )
        team = CanonicalTeam.objects.create(name="Leeds United", reep_id="team-leeds")
        player = CanonicalPlayer.objects.create(display_name="Sofa Only", reep_id="player-sofa-only")
        ss_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=cs,
            status=IngestionRunStatus.SUCCESS,
        )
        SofascorePlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=ss_run,
            provider_player_id="ss-1",
            provider_team_id="team-1",
            player_name="Sofa Only",
            team_name=team.name,
            position_raw="M",
            minutes=900,
            summary_goals=4,
            summary_assists=6,
            summary_successful_dribbles=20,
            tackles=18,
            interceptions=11,
            clearances=6,
            outfielder_blocks=2,
            big_chances_created=9,
            accurate_passes=410,
            accurate_passes_percentage=84.0,
            key_passes=30,
            shots_on_target=14,
            shots_off_target=10,
            canonical_player=player,
            canonical_team=team,
        )
        merge_run = IngestionRun.objects.create(
            kind=IngestionKind.MERGE,
            competition_season=cs,
            status=IngestionRunStatus.PENDING,
        )

        run_merge_job(cs, run=merge_run)

        merge_run.refresh_from_db()
        self.assertEqual(merge_run.status, IngestionRunStatus.SUCCESS)
        row = MergedPlayerSeason.objects.get(
            competition_season=cs,
            canonical_player=player,
            is_current=True,
        )
        self.assertEqual(row.metadata_authority, MetadataAuthority.SOFASCORE)
        self.assertIsNone(row.us_xg)
        self.assertEqual(row.ss_key_passes, 30)


class ApiTests(TestCase):
    def setUp(self):
        MergeTests.setUp(self)

    def test_internal_bootstrap_api_is_not_publicly_routed(self):
        execute_merge_for_slice(self.cs, merge_run=None)
        c = APIClient()
        r = c.get("/internal/api/merged-player-seasons/")
        self.assertEqual(r.status_code, 404)
        r2 = c.get(
            "/internal/api/merged-player-seasons/",
            {"competition": "EPL", "season": "2025-26"},
        )
        self.assertEqual(r2.status_code, 404)


class ReattachTests(TestCase):
    def test_reattach_updates_source_fks(self):
        cs = _slice()
        ReepPlayerRow.objects.create(
            reep_id="r99",
            full_name="Later",
            understat_player_id="5",
            sofascore_player_id=None,
        )
        src = UnderstatPlayerSeasonSource.objects.create(
            competition_season=cs,
            ingestion_run=IngestionRun.objects.create(
                kind=IngestionKind.UNDERSTAT,
                competition_season=cs,
                status=IngestionRunStatus.SUCCESS,
            ),
            provider_player_id="5",
            player_name="Later",
            team_name="",
            position_raw="D",
        )
        self.assertIsNone(src.canonical_player_id)
        reattach_slice_identities(cs)
        src.refresh_from_db()
        self.assertIsNotNone(src.canonical_player_id)
