from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from ingestion.models import (
    CompetitionSeason,
    CompetitionType,
    MergedTeamSeason,
    Provider,
    ProviderTeamMapping,
    SofascoreTeamSeasonSource,
    UnmatchedProviderTeam,
)


@dataclass(frozen=True)
class TeamEntry:
    provider_team_id: str
    team_name: str
    canonical_team_id: int | None


@dataclass(frozen=True)
class RolloverAnomaly:
    code: str
    severity: str
    message: str
    details: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RolloverDiagnosticReport:
    competition_season_id: int
    competition_code: str
    season_label: str
    previous_competition_season_id: int | None
    expected_team_count: int
    observed_team_count: int
    candidate_data: bool
    anomalies: tuple[RolloverAnomaly, ...]

    @property
    def ready_for_publication(self) -> bool:
        return not self.anomalies

    def as_dict(self) -> dict[str, object]:
        return {
            "competition_season_id": self.competition_season_id,
            "competition_code": self.competition_code,
            "season_label": self.season_label,
            "previous_competition_season_id": self.previous_competition_season_id,
            "expected_team_count": self.expected_team_count,
            "observed_team_count": self.observed_team_count,
            "candidate_data": self.candidate_data,
            "ready_for_publication": self.ready_for_publication,
            "anomalies": [anomaly.as_dict() for anomaly in self.anomalies],
        }


def normalize_team_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def team_entries_from_candidate(rows: Sequence[Mapping[str, object]]) -> list[TeamEntry]:
    provider_ids = {
        str(row.get("provider_team_id") or "")
        for row in rows
        if row.get("provider_team_id")
    }
    mapped_team_ids = dict(
        ProviderTeamMapping.objects.filter(
            provider=Provider.SOFASCORE,
            provider_team_id__in=provider_ids,
        ).values_list("provider_team_id", "canonical_team_id")
    )
    return [
        TeamEntry(
            provider_team_id=str(row.get("provider_team_id") or ""),
            team_name=str(row.get("team_name") or ""),
            canonical_team_id=mapped_team_ids.get(str(row.get("provider_team_id") or "")),
        )
        for row in rows
    ]


def team_entries_from_source(competition_season: CompetitionSeason) -> list[TeamEntry]:
    return [
        TeamEntry(
            provider_team_id=row.provider_team_id,
            team_name=row.team_name,
            canonical_team_id=row.canonical_team_id,
        )
        for row in SofascoreTeamSeasonSource.objects.filter(
            competition_season=competition_season,
        ).only("provider_team_id", "team_name", "canonical_team_id")
    ]


def add_anomaly(
    anomalies: list[RolloverAnomaly],
    *,
    code: str,
    severity: str,
    message: str,
    **details: object,
) -> None:
    anomalies.append(
        RolloverAnomaly(
            code=code,
            severity=severity,
            message=message,
            details=details,
        )
    )


def diagnose_expected_count(
    competition_season: CompetitionSeason,
    entries: Sequence[TeamEntry],
    anomalies: list[RolloverAnomaly],
) -> None:
    observed = len(entries)
    expected = competition_season.expected_team_count
    if observed != expected:
        add_anomaly(
            anomalies,
            code="expected_team_count_mismatch",
            severity="error",
            message=f"Observed {observed} teams; expected exactly {expected}.",
            expected=expected,
            observed=observed,
        )


def diagnose_current_identities(
    competition_season: CompetitionSeason,
    entries: Sequence[TeamEntry],
    anomalies: list[RolloverAnomaly],
) -> None:
    entries_by_provider_id: dict[str, list[TeamEntry]] = {}
    entries_by_canonical_id: dict[int, list[TeamEntry]] = {}
    canonical_ids_by_name: dict[str, set[int]] = {}

    audited_provider_ids = set(
        UnmatchedProviderTeam.objects.filter(
            competition_season=competition_season,
            provider=Provider.SOFASCORE,
        ).values_list("provider_team_id", flat=True)
    )

    for entry in entries:
        entries_by_provider_id.setdefault(entry.provider_team_id, []).append(entry)
        if entry.canonical_team_id is None:
            add_anomaly(
                anomalies,
                code="unmatched_canonical_team",
                severity="error",
                message=(
                    f"Sofascore team {entry.provider_team_id or '<blank>'} "
                    "has no canonical-team mapping."
                ),
                provider_team_id=entry.provider_team_id,
                team_name=entry.team_name,
            )
        else:
            entries_by_canonical_id.setdefault(entry.canonical_team_id, []).append(entry)
            normalized_name = normalize_team_name(entry.team_name)
            if normalized_name:
                canonical_ids_by_name.setdefault(normalized_name, set()).add(
                    entry.canonical_team_id
                )

        if entry.provider_team_id in audited_provider_ids:
            add_anomaly(
                anomalies,
                code="provider_identity_requires_review",
                severity="review",
                message=(
                    f"Sofascore team {entry.provider_team_id} has an unmatched-provider "
                    "audit row and requires identity review."
                ),
                provider_team_id=entry.provider_team_id,
                team_name=entry.team_name,
                canonical_team_id=entry.canonical_team_id,
            )

    for provider_team_id, duplicate_entries in sorted(entries_by_provider_id.items()):
        if provider_team_id and len(duplicate_entries) > 1:
            add_anomaly(
                anomalies,
                code="duplicate_provider_team_id",
                severity="error",
                message=f"Sofascore team ID {provider_team_id} occurs more than once.",
                provider_team_id=provider_team_id,
                occurrences=len(duplicate_entries),
            )

    for canonical_team_id, duplicate_entries in sorted(entries_by_canonical_id.items()):
        provider_ids = sorted({entry.provider_team_id for entry in duplicate_entries})
        if len(provider_ids) > 1:
            add_anomaly(
                anomalies,
                code="duplicate_canonical_team",
                severity="error",
                message=(
                    f"Canonical team {canonical_team_id} is represented by multiple "
                    "Sofascore team IDs in the same slice."
                ),
                canonical_team_id=canonical_team_id,
                provider_team_ids=provider_ids,
            )

    for normalized_name, canonical_team_ids in sorted(canonical_ids_by_name.items()):
        if len(canonical_team_ids) > 1:
            add_anomaly(
                anomalies,
                code="duplicate_canonical_team_name",
                severity="error",
                message="One normalized team name resolves to multiple canonical teams.",
                normalized_team_name=normalized_name,
                canonical_team_ids=sorted(canonical_team_ids),
            )


def diagnose_provider_changes(
    entries: Sequence[TeamEntry],
    previous_entries: Sequence[TeamEntry],
    anomalies: list[RolloverAnomaly],
) -> None:
    previous_by_provider_id = {
        entry.provider_team_id: entry
        for entry in previous_entries
        if entry.provider_team_id
    }
    previous_by_canonical_id = {
        entry.canonical_team_id: entry
        for entry in previous_entries
        if entry.canonical_team_id is not None
    }
    previous_by_name = {
        normalize_team_name(entry.team_name): entry
        for entry in previous_entries
        if normalize_team_name(entry.team_name)
    }

    mapped_provider_ids = set(
        ProviderTeamMapping.objects.filter(
            provider=Provider.SOFASCORE,
            provider_team_id__in=[entry.provider_team_id for entry in entries],
        ).values_list("provider_team_id", flat=True)
    )

    for entry in entries:
        if entry.provider_team_id and entry.provider_team_id not in mapped_provider_ids:
            add_anomaly(
                anomalies,
                code="unknown_provider_team_id",
                severity="review",
                message=(
                    f"Sofascore team ID {entry.provider_team_id} has no existing provider mapping."
                ),
                provider_team_id=entry.provider_team_id,
                team_name=entry.team_name,
            )

        previous_same_provider = previous_by_provider_id.get(entry.provider_team_id)
        if previous_same_provider is not None:
            previous_name = normalize_team_name(previous_same_provider.team_name)
            current_name = normalize_team_name(entry.team_name)
            if previous_name and current_name and previous_name != current_name:
                add_anomaly(
                    anomalies,
                    code="provider_name_change",
                    severity="review",
                    message=(
                        f"Sofascore team {entry.provider_team_id} changed name from "
                        f"'{previous_same_provider.team_name}' to '{entry.team_name}'."
                    ),
                    provider_team_id=entry.provider_team_id,
                    previous_name=previous_same_provider.team_name,
                    current_name=entry.team_name,
                    canonical_team_id=entry.canonical_team_id,
                )
            continue

        previous_match = None
        if entry.canonical_team_id is not None:
            previous_match = previous_by_canonical_id.get(entry.canonical_team_id)
        if previous_match is None:
            previous_match = previous_by_name.get(normalize_team_name(entry.team_name))
        if previous_match is not None and previous_match.provider_team_id != entry.provider_team_id:
            add_anomaly(
                anomalies,
                code="provider_id_change",
                severity="review",
                message=(
                    f"Team '{entry.team_name}' changed Sofascore ID from "
                    f"{previous_match.provider_team_id} to {entry.provider_team_id}."
                ),
                previous_provider_team_id=previous_match.provider_team_id,
                current_provider_team_id=entry.provider_team_id,
                previous_canonical_team_id=previous_match.canonical_team_id,
                current_canonical_team_id=entry.canonical_team_id,
            )


def diagnose_multiple_domestic_memberships(
    competition_season: CompetitionSeason,
    anomalies: list[RolloverAnomaly],
) -> None:
    memberships: dict[tuple[int, str], list[tuple[int, str]]] = {}
    rows = (
        MergedTeamSeason.objects.filter(
            competition_season__season=competition_season.season,
            competition_season__competition__competition_type=CompetitionType.DOMESTIC_LEAGUE,
            competition_season__competition__country__gt="",
            is_current=True,
        )
        .values_list(
            "canonical_team_id",
            "competition_season__competition__country",
            "competition_season_id",
            "competition_season__competition__short_code",
        )
    )
    for canonical_team_id, country, competition_season_id, competition_code in rows:
        memberships.setdefault((canonical_team_id, country.casefold()), []).append(
            (competition_season_id, competition_code)
        )

    for (canonical_team_id, country), domestic_memberships in sorted(memberships.items()):
        competition_ids = {membership[0] for membership in domestic_memberships}
        if len(competition_ids) > 1:
            add_anomaly(
                anomalies,
                code="multiple_domestic_competitions",
                severity="error",
                message=(
                    f"Canonical team {canonical_team_id} appears in multiple {country.title()} "
                    f"domestic competitions in {competition_season.season.label}."
                ),
                canonical_team_id=canonical_team_id,
                country=country,
                competition_seasons=[
                    {
                        "competition_season_id": competition_id,
                        "competition_code": competition_code,
                    }
                    for competition_id, competition_code in sorted(domestic_memberships)
                ],
            )


def diagnose_season_rollover(
    competition_season: CompetitionSeason,
    *,
    previous_competition_season: CompetitionSeason | None = None,
    candidate_rows: Sequence[Mapping[str, object]] | None = None,
) -> RolloverDiagnosticReport:
    """Derive a read-only publication report from source, mapping, and merged rows."""

    entries = (
        team_entries_from_candidate(candidate_rows)
        if candidate_rows is not None
        else team_entries_from_source(competition_season)
    )
    previous_entries = (
        team_entries_from_source(previous_competition_season)
        if previous_competition_season is not None
        else []
    )
    anomalies: list[RolloverAnomaly] = []

    diagnose_expected_count(competition_season, entries, anomalies)
    diagnose_current_identities(competition_season, entries, anomalies)
    diagnose_provider_changes(entries, previous_entries, anomalies)
    diagnose_multiple_domestic_memberships(competition_season, anomalies)

    return RolloverDiagnosticReport(
        competition_season_id=competition_season.id,
        competition_code=competition_season.competition.short_code,
        season_label=competition_season.season.label,
        previous_competition_season_id=(
            previous_competition_season.id
            if previous_competition_season is not None
            else None
        ),
        expected_team_count=competition_season.expected_team_count,
        observed_team_count=len(entries),
        candidate_data=candidate_rows is not None,
        anomalies=tuple(anomalies),
    )
