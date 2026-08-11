from __future__ import annotations

from django.core.exceptions import ValidationError

from editorial.content import normalize_entity_context
from editorial.models import (
    Article,
    ArticlePlayerReference,
    ArticlePlayerSubject,
    ArticleTeamReference,
    ArticleTeamSubject,
)
from ingestion.models import CanonicalPlayer, CanonicalTeam, CompetitionSeason


MAX_SUBJECTS_PER_KIND = 2


def normalize_subjects(value) -> dict:
    if value is None:
        value = {"players": [], "teams": []}
    if not isinstance(value, dict):
        raise ValidationError("Article subjects are invalid.")
    players = normalize_subject_list(value.get("players", []), kind="player")
    teams = normalize_subject_list(value.get("teams", []), kind="team")
    validate_context_ids([*players, *teams])
    return {"players": players, "teams": teams}


def normalize_subject_list(value, *, kind: str) -> list[dict]:
    label = "player" if kind == "player" else "team"
    if not isinstance(value, list) or len(value) > MAX_SUBJECTS_PER_KIND:
        raise ValidationError(f"An article can have at most 2 {label} subjects.")
    ids = []
    contexts = {}
    for item in value:
        if not isinstance(item, dict) or item.get("kind") != kind:
            raise ValidationError(f"Article {label} subjects are invalid.")
        try:
            entity_id = int(item.get("id"))
        except (TypeError, ValueError):
            raise ValidationError(f"Article {label} subject ID is invalid.") from None
        if entity_id < 1 or entity_id in ids:
            raise ValidationError(f"Article {label} subjects must be unique canonical entities.")
        ids.append(entity_id)
        contexts[entity_id] = normalize_entity_context(item.get("context"))

    model = CanonicalPlayer if kind == "player" else CanonicalTeam
    name_field = "display_name" if kind == "player" else "name"
    entities = model.objects.in_bulk(ids)
    if len(entities) != len(ids):
        raise ValidationError(f"One or more article {label} subjects do not exist.")
    return [
        {
            "kind": kind,
            "id": entity_id,
            "name": getattr(entities[entity_id], name_field),
            **({"context": contexts[entity_id]} if contexts[entity_id] else {}),
        }
        for entity_id in ids
    ]


def validate_context_ids(entities: list[dict]) -> None:
    competition_season_ids = {
        entity.get("context", {}).get("competition_season_id")
        for entity in entities
        if entity.get("context", {}).get("competition_season_id")
    }
    team_ids = {
        entity.get("context", {}).get("team", {}).get("id")
        for entity in entities
        if entity.get("context", {}).get("team", {}).get("id")
    }
    if competition_season_ids and CompetitionSeason.objects.filter(
        id__in=competition_season_ids
    ).count() != len(competition_season_ids):
        raise ValidationError("One or more article subject competition contexts do not exist.")
    if team_ids and CanonicalTeam.objects.filter(id__in=team_ids).count() != len(team_ids):
        raise ValidationError("One or more article subject club contexts do not exist.")


def save_subjects(article: Article, subjects: dict) -> None:
    article.player_subject_links.all().delete()
    article.team_subject_links.all().delete()
    ArticlePlayerSubject.objects.bulk_create(
        [
            ArticlePlayerSubject(
                article=article,
                player_id=subject["id"],
                position=position,
                context=subject.get("context", {}),
            )
            for position, subject in enumerate(subjects["players"])
        ]
    )
    ArticleTeamSubject.objects.bulk_create(
        [
            ArticleTeamSubject(
                article=article,
                team_id=subject["id"],
                position=position,
                context=subject.get("context", {}),
            )
            for position, subject in enumerate(subjects["teams"])
        ]
    )


def subjects_payload(article: Article) -> dict:
    return {
        "players": [
            entity_payload("player", link.player_id, link.player.display_name, link.context)
            for link in article.player_subject_links.select_related("player").all()
        ],
        "teams": [
            entity_payload("team", link.team_id, link.team.name, link.context)
            for link in article.team_subject_links.select_related("team").all()
        ],
    }


def sync_references(article: Article, document: dict) -> None:
    player_ids = set()
    team_ids = set()
    supplied_names = {}
    for reference in document_references(document):
        entity_id = reference["id"]
        key = (reference["kind"], entity_id)
        supplied_names[key] = reference["name"]
        if reference["kind"] == "player":
            player_ids.add(entity_id)
        else:
            team_ids.add(entity_id)

    players = CanonicalPlayer.objects.in_bulk(player_ids)
    teams = CanonicalTeam.objects.in_bulk(team_ids)
    if len(players) != len(player_ids) or len(teams) != len(team_ids):
        raise ValidationError("One or more article references no longer exist.")
    for player_id, player in players.items():
        if supplied_names[("player", player_id)] != player.display_name:
            raise ValidationError("An article player reference label does not match its canonical entity.")
    for team_id, team in teams.items():
        if supplied_names[("team", team_id)] != team.name:
            raise ValidationError("An article team reference label does not match its canonical entity.")

    article.player_reference_links.exclude(player_id__in=player_ids).delete()
    article.team_reference_links.exclude(team_id__in=team_ids).delete()
    ArticlePlayerReference.objects.bulk_create(
        [ArticlePlayerReference(article=article, player_id=player_id) for player_id in player_ids],
        ignore_conflicts=True,
    )
    ArticleTeamReference.objects.bulk_create(
        [ArticleTeamReference(article=article, team_id=team_id) for team_id in team_ids],
        ignore_conflicts=True,
    )


def references_payload(article: Article) -> dict:
    return {
        "players": [
            entity_payload("player", link.player_id, link.player.display_name)
            for link in article.player_reference_links.select_related("player").order_by(
                "player__display_name"
            )
        ],
        "teams": [
            entity_payload("team", link.team_id, link.team.name)
            for link in article.team_reference_links.select_related("team").order_by("team__name")
        ],
    }


def entity_payload(kind: str, entity_id: int, name: str, context: dict | None = None) -> dict:
    return {
        "kind": kind,
        "id": entity_id,
        "name": name,
        **({"context": context} if context else {}),
    }


def document_references(document: dict):
    for block in document.get("blocks", []):
        content_lists = []
        if isinstance(block.get("content"), list):
            content_lists.append(block["content"])
        if isinstance(block.get("items"), list):
            content_lists.extend(item for item in block["items"] if isinstance(item, list))
        for content in content_lists:
            for run in content:
                reference = run.get("reference") if isinstance(run, dict) else None
                if reference:
                    yield reference
