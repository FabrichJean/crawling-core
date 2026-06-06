"""Storage contract. The SQLite implementation in :mod:`crawling_core.storage.sqlite`
satisfies this; swap in another backend by implementing the same Protocol."""

from __future__ import annotations

from typing import Any, Protocol

from crawling_core.models import Creator, ForumPost, Media


class Storage(Protocol):
    def upsert_creator(self, creator: Creator, **extra: Any) -> None:
        ...

    def get_creator(self, creator_id: str) -> Creator | None:
        ...

    def upsert_media(self, media: Media, **extra: Any) -> None:
        ...

    def get_media(self, media_id: str) -> Media | None:
        ...

    def upsert_post(self, post: ForumPost, **extra: Any) -> None:
        ...

    def mark_status(self, table: str, item_id: str, **fields: Any) -> None:
        """Generic status-field updater, e.g. ``mark_status("media", id, downloaded=True)``."""
