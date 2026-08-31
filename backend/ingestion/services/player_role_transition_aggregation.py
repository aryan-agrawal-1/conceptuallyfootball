"""Bounded possession and transition aggregation for player role evidence."""

from __future__ import annotations

from collections import defaultdict
from itertools import islice
from types import SimpleNamespace
from typing import Mapping

from ingestion.models import (
    Provider,
    ProviderMatch,
    ProviderMatchEvent,
    ProviderMatchPlayerStateExposure,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.player_role_aggregation import (
    DEFAULT_MATCH_BATCH_SIZE,
    EVENT_COLUMNS,
    EXPOSURE_COLUMNS,
    MATCH_COLUMNS,
    POSSESSION_COLUMNS,
    POSSESSION_EVENT_COLUMNS,
    POSSESSION_PARTICIPANT_COLUMNS,
    TEAM_EPISODE_COLUMNS,
    CompactMatchBatch,
    PlayerRoleFeatureAccumulator,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.services.transition_leverage import possession_observation


class ScalarRelation(list):
    def all(self):
        return self


def scalar_object(row: Mapping, **extra):
    return SimpleNamespace(**dict(row), **extra)


def batch_objects(batch: CompactMatchBatch):
    """Adapt compact rows to the shared formatter without ORM hydration."""

    teams = {}
    for match in batch.matches:
        for team_id in (match.get("home_team_id"), match.get("away_team_id")):
            if team_id is not None:
                teams.setdefault(int(team_id), SimpleNamespace(id=int(team_id), name=""))
    matches = {
        int(row["id"]): scalar_object(
            row,
            home_team=teams.get(row.get("home_team_id")),
            away_team=teams.get(row.get("away_team_id")),
        )
        for row in batch.matches
    }
    events = {}
    for row in batch.events:
        team_id, player_id = row.get("team_id"), row.get("player_id")
        events[int(row["id"])] = scalar_object(
            row,
            team=teams.get(int(team_id)) if team_id is not None else None,
            player=(SimpleNamespace(id=int(player_id), display_name="") if player_id is not None else None),
        )
    links = defaultdict(ScalarRelation)
    for row in batch.possession_events:
        event = events.get(int(row["event_id"]))
        if event is not None:
            links[int(row["possession_id"])].append(scalar_object(row, event=event))
    possessions = {}
    for row in batch.possessions:
        team_id = row.get("team_id")
        possessions[int(row["id"])] = scalar_object(
            row,
            team=teams.get(int(team_id)) if team_id is not None else None,
            event_links=links[int(row["id"])],
        )
    episodes = defaultdict(list)
    for row in batch.team_episodes:
        episodes[(int(row["provider_match_id"]), int(row["focal_team_id"]))].append(
            scalar_object(row)
        )
    return matches, teams, events, possessions, episodes


def exposure_rows(batch: CompactMatchBatch, accumulators):
    rows = defaultdict(lambda: defaultdict(list))
    for row in batch.exposures:
        match_id = int(row["player_interval__participation__provider_match_id"])
        team_id = int(row["player_interval__participation__team_id"])
        player_id = int(row["player_interval__participation__player_id"])
        if (player_id, team_id) in accumulators:
            rows[(match_id, team_id)][player_id].append(
                (int(row["start_second"]), int(row["end_second"]))
            )
    return rows


def inside(intervals, second) -> bool:
    return second is not None and any(start <= int(second) < end for start, end in intervals)


def transition_evidence_payload(observation: dict, player_sequences: list[int]) -> dict:
    return {
        "match_ref": observation["match_ref"],
        "possession_id": observation["possession_id"],
        "team_id": observation["team_id"],
        "state": observation["state"],
        "state_transition": observation["state_transition"],
        "outcome_tier": observation["outcome_tier"],
        "rapid_transition": observation["rapid_transition"],
        "action_stages": sorted({
            observation["possession_trace"][sequence]["stage"] for sequence in player_sequences
        }),
        "action_event_indexes": [
            observation["possession_trace"][sequence]["event_index"] for sequence in player_sequences
        ],
        "verified_player_action_sequences": player_sequences,
        "possession_trace": observation["possession_trace"],
    }


def aggregate_transition_batch(
    batch: CompactMatchBatch,
    accumulators: dict[tuple[int, int], PlayerRoleFeatureAccumulator],
    *,
    match_refs: Mapping[int, int] | None = None,
) -> None:
    """Format each team possession once and project only involved players."""

    matches, teams, _events, possessions, episodes = batch_objects(batch)
    exposures = exposure_rows(batch, accumulators)
    refs = match_refs or {match_id: index for index, match_id in enumerate(batch.match_ids)}
    participants = defaultdict(set)
    for row in batch.possession_participants:
        if row.get("player_id") is not None:
            participants[int(row["possession_id"])].add(int(row["player_id"]))

    for possession_row in batch.possessions:
        possession_id = int(possession_row["id"])
        possession = possessions[possession_id]
        match_id = int(possession.provider_match_id)
        team_id = possession.team_id
        if team_id is None or match_id not in matches:
            continue
        team_id = int(team_id)
        scoped = exposures.get((match_id, team_id), {})
        candidate_players = {
            player_id for player_id in participants.get(possession_id, set())
            if (player_id, team_id) in accumulators
        }
        for player_id in candidate_players:
            target = accumulators[(player_id, team_id)].transition
            target.counters["candidate_possessions"] += 1
            target.counters["ambiguous_excluded"] += bool(possession.is_ambiguous)
        if possession.is_ambiguous:
            continue
        if not scoped:
            for player_id in candidate_players:
                accumulators[(player_id, team_id)].transition.counters["state_or_team_mismatch"] += 1
            continue

        links = list(possession.event_links.all())
        links.sort(key=lambda link: (int(link.sequence), int(link.event.event_index)))
        # Participant rows are the cheap primary gate. Older possession builds
        # can omit a participant that is still present in their already-loaded
        # team opportunity links, so retain that compact fallback to preserve
        # the accepted transition evidence exactly.
        involved_players = candidate_players | {
            int(link.event.player_id)
            for link in links
            if link.event.player_id is not None
            and link.event.team_id == team_id
            and (int(link.event.player_id), team_id) in accumulators
        }
        team_sequences_by_player = {player_id: [] for player_id in scoped}
        player_sequences_by_player = defaultdict(list)
        for sequence, link in enumerate(links):
            event = link.event
            if event.team_id != team_id:
                continue
            for player_id, intervals in scoped.items():
                if not inside(intervals, event.timeline_seconds):
                    continue
                team_sequences_by_player[player_id].append(sequence)
                if event.player_id == player_id:
                    player_sequences_by_player[player_id].append(sequence)
        relevant_players = involved_players | {
            player_id for player_id, sequences in team_sequences_by_player.items() if sequences
        }
        if not relevant_players:
            continue
        focal_team = teams.get(team_id) or SimpleNamespace(id=team_id, name="")
        observation = possession_observation(
            possession,
            match=matches[match_id],
            focal_team=focal_team,
            match_ref=refs.get(match_id, 0),
            episodes=episodes.get((match_id, team_id), ()),
        )
        for player_id, sequences in team_sequences_by_player.items():
            if sequences:
                accumulators[(player_id, team_id)].transition.counters["opportunities"] += 1
        for player_id in involved_players:
            target = accumulators[(player_id, team_id)].transition
            intervals = scoped.get(player_id)
            if not intervals:
                if player_id in candidate_players:
                    target.counters["state_or_team_mismatch"] += 1
                continue
            player_sequences = player_sequences_by_player.get(player_id, [])
            if not player_sequences:
                if player_id in candidate_players:
                    target.counters["outside_verified_player_interval"] += 1
                continue
            target.counters["involved_possessions"] += 1
            seen_stages = set()
            for sequence in player_sequences:
                role = observation["possession_trace"][sequence]["role"]
                target.stage_actions[role] += 1
                seen_stages.add(role)
            for role in seen_stages:
                target.stage_possessions[role] += 1
            if observation["rapid_transition"]["is_counter_launch"]:
                target.counters["counter_possessions"] += 1
                outcome = observation["rapid_transition"].get("outcome")
                ladder = observation["direction_ladder"]
                if possession.counter_shot or ladder.get("shot") or outcome in {"saved", "goal", "missed", "blocked", "woodwork"}:
                    target.counters["shot_producing_possessions"] += 1
                if possession.counter_box_arrival or ladder.get("box_entry") or outcome == "box_arrival":
                    target.counters["box_entry_possessions"] += 1
                if possession.counter_final_third_arrival or ladder.get("territorial_entry") or outcome == "final_third_arrival":
                    target.counters["final_third_possessions"] += 1
            target.counters["big_chance_possessions"] += bool(observation["direction_ladder"].get("big_chance"))
            target.counters["goal_possessions"] += observation["score"]["perspective"] == "for"
            target.counters["state_changing_possessions"] += bool(observation["state_transition"]["actual"])
            payload = transition_evidence_payload(observation, player_sequences)
            target.evidence.add(
                (refs.get(match_id, 0), int(possession.possession_index), possession_id, str(possession.identity)),
                payload,
            )


def iter_transition_batches(
    competition_season,
    batch_size: int = DEFAULT_MATCH_BATCH_SIZE,
    *,
    match_ids=None,
):
    """Yield only a fixed match batch of compact possession graph rows."""

    if not 1 <= batch_size <= DEFAULT_MATCH_BATCH_SIZE:
        raise ValueError(f"match batch size must be between 1 and {DEFAULT_MATCH_BATCH_SIZE}")
    matches_query = ProviderMatch.objects.filter(
        competition_season=competition_season, provider=Provider.WHOSCORED,
    )
    if match_ids is not None:
        matches_query = matches_query.filter(id__in=tuple(int(match_id) for match_id in match_ids))
    matches = matches_query.values(*MATCH_COLUMNS).order_by("kickoff_at", "id").iterator(chunk_size=batch_size)
    while rows := tuple(islice(matches, batch_size)):
        match_ids = tuple(int(row["id"]) for row in rows)
        possessions = tuple(ProviderMatchPossession.objects.filter(
            provider_match_id__in=match_ids,
            build__calculation_version=POSSESSION_CALCULATION_VERSION,
        ).values(*POSSESSION_COLUMNS).order_by("provider_match_id", "possession_index", "id"))
        possession_ids = tuple(int(row["id"]) for row in possessions)
        possession_events = tuple(ProviderMatchPossessionEvent.objects.filter(
            possession_id__in=possession_ids,
        ).values(*POSSESSION_EVENT_COLUMNS).order_by("possession_id", "sequence", "event_id", "id"))
        event_ids = tuple(int(row["event_id"]) for row in possession_events)
        events = tuple(ProviderMatchEvent.objects.filter(
            id__in=event_ids,
        ).values(*EVENT_COLUMNS).order_by("provider_match_id", "event_index", "id"))
        participants = tuple(ProviderMatchPossessionParticipant.objects.filter(
            possession_id__in=possession_ids,
        ).values(*POSSESSION_PARTICIPANT_COLUMNS).order_by(
            "possession_id", "first_event_index", "player_id", "id"
        ))
        exposures = tuple(ProviderMatchPlayerStateExposure.objects.filter(
            player_interval__participation__provider_match_id__in=match_ids,
            player_interval__participation__status="verified",
            player_interval__participation__confidence="verified",
            player_interval__confidence="verified",
        ).values(*EXPOSURE_COLUMNS).order_by(
            "player_interval__participation__provider_match_id",
            "player_interval__participation__team_id",
            "player_interval__participation__player_id", "start_second", "end_second", "id",
        ))
        episodes = tuple(ProviderMatchTeamGameStateEpisode.objects.filter(
            provider_match_id__in=match_ids,
        ).values(*TEAM_EPISODE_COLUMNS).order_by(
            "provider_match_id", "focal_team_id", "episode_index", "id"
        ))
        yield CompactMatchBatch(
            matches=rows, events=events, exposures=exposures, team_episodes=episodes,
            possessions=possessions, possession_events=possession_events,
            possession_participants=participants,
        )
