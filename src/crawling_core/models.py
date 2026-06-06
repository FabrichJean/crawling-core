"""Generic content models shared by every platform adapter.

Each platform exposes data with different field names (``playUrl`` vs
``play_url`` vs ``video_url``...). Rather than hard-coding one platform's
shape, these models keep a small set of normalized fields that the pipeline
and storage layer rely on, plus a ``raw`` dict that always preserves the
original payload so nothing is lost and adapters can stash extra fields.

Adapters are expected to build these via :meth:`from_raw`, passing a
``mapping`` of normalized-field -> list of possible source keys (checked in
order, first match wins). This keeps the per-platform "which key holds the
title" knowledge in the adapter/config, not in the core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Default key candidates per normalized field. Adapters can override/extend
# these via the `mapping` argument of `from_raw` without subclassing anything.
_DEFAULT_CREATOR_MAPPING: dict[str, tuple[str, ...]] = {
    "id": ("uuid", "id", "user_id", "creator_id"),
    "name": ("nickname", "name", "username", "display_name"),
    "avatar": ("thumb", "avatar", "avatarUrl", "cover"),
    "fans_count": ("fans_count", "followers", "followerCount"),
    "media_count": ("video_count", "media_count", "post_count"),
}

_DEFAULT_MEDIA_MAPPING: dict[str, tuple[str, ...]] = {
    "id": ("id", "vid", "uuid", "video_id"),
    "title": ("title", "name"),
    "description": ("description", "content", "desc"),
    "play_url": ("playUrl", "play_url", "previewUrl", "sourceUrl", "source_url", "url"),
    "cover": ("cover", "cover_thumb", "thumb", "thumbImg", "poster"),
    "duration": ("playTime", "play_time", "duration"),
    "created_at": ("createdAt", "created_at", "publishedAt"),
    "play_count": ("playCount", "play_count", "views"),
    "like_count": ("likeCount", "like_count", "like", "likes"),
    "comment_count": ("commentCount", "comment_count", "comment", "comments"),
}

_DEFAULT_POST_MAPPING: dict[str, tuple[str, ...]] = {
    "id": ("id", "post_id", "uuid"),
    "title": ("title", "subject"),
    "content": ("content", "body", "text"),
    "created_at": ("createdAt", "created_at", "publishedAt"),
    "reply_count": ("replyCount", "reply_count", "comments"),
}


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


@dataclass(frozen=True, slots=True)
class Creator:
    """A channel/author/uploader on a platform."""

    id: str
    name: str | None = None
    avatar: str | None = None
    fans_count: str | None = None
    media_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        data: dict[str, Any],
        *,
        fallback_id: str = "",
        mapping: dict[str, tuple[str, ...]] | None = None,
    ) -> Creator:
        keys = {**_DEFAULT_CREATOR_MAPPING, **(mapping or {})}
        return cls(
            id=str(_first_present(data, keys["id"]) or fallback_id),
            name=_as_optional_str(_first_present(data, keys["name"])),
            avatar=_as_optional_str(_first_present(data, keys["avatar"])),
            fans_count=_as_optional_str(_first_present(data, keys["fans_count"])),
            media_count=_as_optional_int(_first_present(data, keys["media_count"])),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class Media:
    """A single piece of content: short video, long video, image set, ...

    ``kind`` is a free-form label the adapter chooses (e.g. "short",
    "long", "vlog", "photo") so the same model serves every content shape
    without subclassing per platform.
    """

    id: str
    creator_id: str | None = None
    kind: str = "video"
    title: str | None = None
    description: str | None = None
    play_url: str | None = None
    cover: str | None = None
    duration: int | None = None
    created_at: str | None = None
    play_count: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        data: dict[str, Any],
        *,
        creator_id: str | None = None,
        kind: str = "video",
        fallback_id: str = "",
        mapping: dict[str, tuple[str, ...]] | None = None,
    ) -> Media:
        keys = {**_DEFAULT_MEDIA_MAPPING, **(mapping or {})}
        return cls(
            id=str(_first_present(data, keys["id"]) or fallback_id),
            creator_id=creator_id,
            kind=kind,
            title=_as_optional_str(_first_present(data, keys["title"])),
            description=_as_optional_str(_first_present(data, keys["description"])),
            play_url=_as_optional_str(_first_present(data, keys["play_url"])),
            cover=_as_optional_str(_first_present(data, keys["cover"])),
            duration=_as_optional_int(_first_present(data, keys["duration"])),
            created_at=_as_optional_str(_first_present(data, keys["created_at"])),
            play_count=_as_optional_str(_first_present(data, keys["play_count"])),
            like_count=_as_optional_int(_first_present(data, keys["like_count"])),
            comment_count=_as_optional_int(_first_present(data, keys["comment_count"])),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class ForumPost:
    """A forum/community post attached to a creator or a board."""

    id: str
    creator_id: str | None = None
    title: str | None = None
    content: str | None = None
    created_at: str | None = None
    reply_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        data: dict[str, Any],
        *,
        creator_id: str | None = None,
        fallback_id: str = "",
        mapping: dict[str, tuple[str, ...]] | None = None,
    ) -> ForumPost:
        keys = {**_DEFAULT_POST_MAPPING, **(mapping or {})}
        return cls(
            id=str(_first_present(data, keys["id"]) or fallback_id),
            creator_id=creator_id,
            title=_as_optional_str(_first_present(data, keys["title"])),
            content=_as_optional_str(_first_present(data, keys["content"])),
            created_at=_as_optional_str(_first_present(data, keys["created_at"])),
            reply_count=_as_optional_int(_first_present(data, keys["reply_count"])),
            raw=data,
        )
