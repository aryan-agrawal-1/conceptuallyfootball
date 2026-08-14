from __future__ import annotations

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

from accounts.models import WriterProfile


SOCIAL_LINK_DOMAINS = {
    "x": {"x.com", "www.x.com", "twitter.com", "www.twitter.com"},
    "instagram": {"instagram.com", "www.instagram.com"},
    "discord": {"discord.com", "www.discord.com", "discord.gg", "www.discord.gg"},
    "bluesky": {"bsky.app", "www.bsky.app"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be"},
}
SOCIAL_LINK_KEYS = (*SOCIAL_LINK_DOMAINS.keys(), "website")


def writer_profile_for(user) -> WriterProfile | None:
    try:
        return user.writer_profile
    except WriterProfile.DoesNotExist:
        return None


def display_name_for(user) -> str:
    profile = writer_profile_for(user)
    return (
        profile.display_name.strip()
        if profile and profile.display_name.strip()
        else user.get_full_name() or user.email or user.username
    )


def social_links_for(user) -> dict:
    profile = writer_profile_for(user)
    if not profile or not isinstance(profile.social_links, dict):
        return {}
    return {
        key: value
        for key, value in profile.social_links.items()
        if key in SOCIAL_LINK_KEYS and isinstance(value, str) and value
    }


def needs_writer_onboarding(user, *, can_access_editorial: bool | None = None) -> bool:
    if can_access_editorial is None:
        can_access_editorial = user.is_superuser or user.has_perm("accounts.access_editorial_workspace")
    if not can_access_editorial:
        return False
    profile = writer_profile_for(user)
    return not profile or not profile.is_complete


def validate_display_name(value) -> str:
    if not isinstance(value, str):
        raise ValidationError("Your public name is required.")
    value = " ".join(value.split())
    if len(value) < 2:
        raise ValidationError("Enter the name readers should see on your articles.")
    if len(value) > 100:
        raise ValidationError("Your public name must be 100 characters or fewer.")
    return value


def validate_social_links(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError("Social links must be an object.")

    normalized = {}
    for key in SOCIAL_LINK_KEYS:
        raw_url = value.get(key, "")
        if not isinstance(raw_url, str):
            raise ValidationError(f"The {key} link must be a URL.")
        url = raw_url.strip()
        if not url:
            continue
        if len(url) > 500:
            raise ValidationError(f"The {key} link is too long.")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValidationError(f"The {key} link must be a complete HTTPS URL.")
        hostname = (parsed.hostname or "").lower()
        allowed_domains = SOCIAL_LINK_DOMAINS.get(key)
        if allowed_domains and hostname not in allowed_domains:
            raise ValidationError(f"Use a valid {key} profile URL.")
        normalized[key] = url
    return normalized
