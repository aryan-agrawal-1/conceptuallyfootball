"""Verified player projection of transition-leverage possession evidence."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Prefetch

from ingestion.models import (
    Provider,
    ProviderMatch,
    ProviderMatchPossession,
    ProviderMatchPossessionEvent,
    ProviderMatchPossessionParticipant,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.player_state_scope import (
    PlayerExposureSegment,
    event_in_segments,
)
from ingestion.services.possession_context import POSSESSION_CALCULATION_VERSION
from ingestion.state_lens import StateLensScope


PLAYER_TRANSITION_EVIDENCE_LIMIT = 25
TRANSITION_STAGES = (
    "origin_recovery",
    "escape",
    "advancement",
    "destabilisation",
    "creation",
    "contest",
    "terminal",
    "support",
)


def _scope_matches(context: dict, scope: StateLensScope) -> bool:
    if scope.state != "all" and context.get("state") != scope.state:
        return False
    if scope.goal_difference is not None and context.get("goal_difference") != scope.goal_difference:
        return False
    if scope.phase is not None and context.get("phase") != scope.phase:
        return False
    if scope.draw_provenance is not None and context.get("draw_provenance") != scope.draw_provenance:
        return False
    age = context.get("state_age_seconds")
    if scope.minimum_state_age_seconds is not None and (
        age is None or age < scope.minimum_state_age_seconds
    ):
        return False
    if scope.maximum_state_age_seconds is not None and (
        age is None or age >= scope.maximum_state_age_seconds
    ):
        return False
    return True


def _empty_evidence(contract_version: str, formula_version: str) -> dict:
    return {
        "available": False,
        "verified": True,
        "contract_version": contract_version,
        "formula_version": formula_version,
        "opportunities": 0,
        "involved_possessions": 0,
        "counter_possessions": 0,
        "shot_producing_possessions": 0,
        "box_entry_possessions": 0,
        "final_third_possessions": 0,
        "big_chance_possessions": 0,
        "goal_possessions": 0,
        "state_changing_possessions": 0,
        "sequence_stages": {
            stage: {"actions": 0, "possessions": 0, "rate_per_opportunity": None}
            for stage in TRANSITION_STAGES
        },
        "sequence_evidence": [],
        "evidence_truncated": False,
        "ambiguous_excluded": 0,
        "exclusions": {
            "ambiguous_possessions": 0,
            "outside_verified_player_interval": 0,
            "state_or_team_mismatch": 0,
        },
        "matching": {
            "same_matches": True,
            "same_team": True,
            "same_state_cohort": True,
            "verified_player_on_pitch_intervals": True,
            "timeline": "half_open_played_seconds",
        },
    }


def _transition_player_evidence(
    profile,
    segments: list[PlayerExposureSegment],
    scope: StateLensScope,
) -> dict:
    from ingestion.services.transition_leverage import (
        TRANSITION_LEVERAGE_API_VERSION,
        TRANSITION_LEVERAGE_FORMULA_VERSION,
        possession_observation,
    )

    evidence = _empty_evidence(
        TRANSITION_LEVERAGE_API_VERSION,
        TRANSITION_LEVERAGE_FORMULA_VERSION,
    )
    match_ids = {segment.match_id for segment in segments}
    team_ids = {segment.team_id for segment in segments if segment.team_id is not None}
    if not match_ids or not team_ids:
        return evidence

    matches = list(
        ProviderMatch.objects.filter(pk__in=match_ids, provider=Provider.WHOSCORED)
        .select_related("home_team", "away_team")
        .order_by("kickoff_at", "id")
    )
    match_by_id = {match.id: match for match in matches}
    match_refs = {match.id: index for index, match in enumerate(matches)}
    episodes_by_match_team: dict[tuple[int, int], list] = defaultdict(list)
    for episode in ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match_id__in=match_ids,
        focal_team_id__in=team_ids,
    ).order_by("provider_match_id", "focal_team_id", "episode_index"):
        episodes_by_match_team[
            int(episode.provider_match_id),
            int(episode.focal_team_id),
        ].append(episode)

    link_queryset = ProviderMatchPossessionEvent.objects.select_related(
        "event",
        "event__player",
        "event__team",
    ).order_by("sequence")
    possessions = list(
        ProviderMatchPossession.objects.filter(
            provider_match_id__in=match_ids,
            team_id__in=team_ids,
            build__calculation_version=POSSESSION_CALCULATION_VERSION,
        )
        .distinct()
        .select_related("provider_match", "team", "build")
        .prefetch_related(
            Prefetch("event_links", queryset=link_queryset),
            Prefetch(
                "participants",
                queryset=ProviderMatchPossessionParticipant.objects.filter(
                    player_id=profile.player_id
                ),
                to_attr="player_participants",
            ),
        )
        .order_by("provider_match_id", "possession_index")
    )
    candidate_possessions = [
        possession
        for possession in possessions
        if getattr(possession, "player_participants", ())
    ]
    candidate_count = len(candidate_possessions)
    ambiguous_count = sum(possession.is_ambiguous for possession in candidate_possessions)
    stages = {
        stage: values.copy()
        for stage, values in evidence["sequence_stages"].items()
    }
    observations: list[dict] = []
    outside_interval_count = 0
    mismatch_count = 0
    opportunities = 0
    for possession in possessions:
        if possession.is_ambiguous:
            continue
        match = match_by_id.get(int(possession.provider_match_id))
        team_id = getattr(possession, "team_id", None)
        if match is None or team_id is None:
            mismatch_count += 1
            continue
        matching_segments = [
            segment
            for segment in segments
            if segment.match_id == possession.provider_match_id
            and segment.team_id == team_id
        ]
        if not matching_segments:
            mismatch_count += bool(getattr(possession, "player_participants", ()))
            continue
        links = sorted(
            possession.event_links.all(),
            key=lambda link: (int(link.sequence), int(link.event.event_index)),
        )
        team_sequences = [
            sequence
            for sequence, link in enumerate(links)
            if link.event.team_id == team_id
            and event_in_segments(link.event, matching_segments, link.event.team_id)
        ]
        focal_team = getattr(possession, "team", None) or (
            match.home_team
            if match.home_team_id == team_id
            else match.away_team
            if match.away_team_id == team_id
            else None
        )
        if focal_team is None:
            mismatch_count += bool(getattr(possession, "player_participants", ()))
            continue
        observation_args = {
            "match": match,
            "focal_team": focal_team,
            "match_ref": match_refs.get(match.id, 0),
            "episodes": episodes_by_match_team.get((match.id, int(team_id)), ()),
        }
        opportunity = None
        if team_sequences:
            opportunity = possession_observation(possession, **observation_args)
            opportunities += _scope_matches(opportunity["state"], scope)
        player_sequences = [
            sequence
            for sequence, link in enumerate(links)
            if link.event.player_id == profile.player_id
            and link.event.team_id == team_id
            and event_in_segments(link.event, matching_segments, link.event.team_id)
        ]
        if not player_sequences:
            outside_interval_count += bool(getattr(possession, "player_participants", ()))
            continue
        observation = opportunity or possession_observation(possession, **observation_args)
        if not _scope_matches(observation["state"], scope):
            mismatch_count += 1
            continue
        observation["_counter_evidence"] = {
            "final_third_arrival": bool(possession.counter_final_third_arrival),
            "box_arrival": bool(possession.counter_box_arrival),
            "shot": bool(possession.counter_shot),
        }
        observation["verified_player_action_sequences"] = player_sequences
        observation["verified_player_action_event_indexes"] = [
            links[sequence].event.event_index for sequence in player_sequences
        ]
        observations.append(observation)

    role_possessions: dict[str, set[str]] = defaultdict(set)
    for observation in observations:
        for sequence in observation["verified_player_action_sequences"]:
            role = observation["possession_trace"][sequence]["role"]
            stages[role]["actions"] += 1
            role_possessions[role].add(observation["possession_id"])
        if observation["rapid_transition"]["is_counter_launch"]:
            evidence["counter_possessions"] += 1
            outcome = observation["rapid_transition"].get("outcome")
            ladder = observation["direction_ladder"]
            counter = observation["_counter_evidence"]
            evidence["shot_producing_possessions"] += bool(
                counter["shot"]
                or ladder.get("shot")
                or outcome in {"saved", "goal", "missed", "blocked", "woodwork"}
            )
            evidence["box_entry_possessions"] += bool(
                counter["box_arrival"]
                or ladder.get("box_entry")
                or outcome == "box_arrival"
            )
            evidence["final_third_possessions"] += bool(
                counter["final_third_arrival"]
                or ladder.get("territorial_entry")
                or outcome == "final_third_arrival"
            )
        evidence["big_chance_possessions"] += bool(
            observation["direction_ladder"].get("big_chance")
        )
        evidence["goal_possessions"] += observation["score"]["perspective"] == "for"
        evidence["state_changing_possessions"] += bool(
            observation["state_transition"]["actual"]
        )

    for role, possession_ids in role_possessions.items():
        stages[role]["possessions"] = len(possession_ids)
        stages[role]["rate_per_opportunity"] = (
            round(len(possession_ids) / opportunities, 4) if opportunities else None
        )
    sequence_evidence = [
        {
            "match_ref": observation["match_ref"],
            "possession_id": observation["possession_id"],
            "team_id": observation["team_id"],
            "state": observation["state"],
            "state_transition": observation["state_transition"],
            "outcome_tier": observation["outcome_tier"],
            "rapid_transition": observation["rapid_transition"],
            "action_stages": sorted({
                observation["possession_trace"][sequence]["stage"]
                for sequence in observation["verified_player_action_sequences"]
            }),
            "action_event_indexes": observation["verified_player_action_event_indexes"],
            "verified_player_action_sequences": observation["verified_player_action_sequences"],
            "possession_trace": observation["possession_trace"],
        }
        for observation in observations[:PLAYER_TRANSITION_EVIDENCE_LIMIT]
    ]
    evidence.update({
        "available": candidate_count > 0,
        "opportunities": opportunities,
        "involved_possessions": len(observations),
        "sequence_stages": stages,
        "sequence_evidence": sequence_evidence,
        "evidence_truncated": len(observations) > PLAYER_TRANSITION_EVIDENCE_LIMIT,
        "ambiguous_excluded": ambiguous_count,
        "exclusions": {
            "ambiguous_possessions": ambiguous_count,
            "outside_verified_player_interval": outside_interval_count,
            "state_or_team_mismatch": mismatch_count,
        },
    })
    return evidence


def possession_context(
    profile,
    segments: list[PlayerExposureSegment],
    scope: StateLensScope = StateLensScope(),
) -> dict:
    """Return legacy counters plus the inspectable transition projection."""

    transition = _transition_player_evidence(profile, segments, scope)
    keys = (
        "available",
        "verified",
        "involved_possessions",
        "counter_possessions",
        "shot_producing_possessions",
        "box_entry_possessions",
        "final_third_possessions",
        "ambiguous_excluded",
        "big_chance_possessions",
        "goal_possessions",
        "state_changing_possessions",
    )
    return {
        **{key: transition[key] for key in keys},
        "transition_leverage": transition,
    }
