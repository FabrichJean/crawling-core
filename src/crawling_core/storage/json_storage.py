"""JSON-file storage backend — one directory per entity type, one file per item.

Compared to SqliteStorage:
  + Zero DB dependency, human-readable output
  + Easy to inspect / edit individual records in any editor or with jq
  + Each write is an atomic file-replace rather than a locked transaction
  - No SQL queries; cross-item filtering happens in Python (fine for scraper scale)

Layout::

    <root>/
      creators/   <creator_id>.json
      media/      <media_id>.json
      posts/      <post_id>.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawling_core.models import Creator, ForumPost, Media


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_stem(item_id: str) -> str:
    """Map an item ID to a filesystem-safe filename stem (no path separators)."""
    cleaned = re.sub(r'[/\\:\x00-\x1f<>|*?"]', "_", item_id).strip(". ")
    return cleaned or "_empty"


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class JsonStorage:
    """Stores each entity as an individual JSON file under *root*.

    Call :meth:`initialize` once before use to create the subdirectories.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def initialize(self) -> None:
        for d in (self._creators_dir, self._media_dir, self._posts_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- directory properties -----------------------------------------------

    @property
    def _creators_dir(self) -> Path:
        return self.root / "creators"

    @property
    def _media_dir(self) -> Path:
        return self.root / "media"

    @property
    def _posts_dir(self) -> Path:
        return self.root / "posts"

    def _dir_for_table(self, table: str) -> Path:
        return {
            "creators": self._creators_dir,
            "media": self._media_dir,
            "posts": self._posts_dir,
        }.get(table, self.root / table)

    def _path(self, directory: Path, item_id: str) -> Path:
        return directory / f"{_safe_stem(item_id)}.json"

    # -- creators -----------------------------------------------------------

    def upsert_creator(self, creator: Creator, **extra: Any) -> None:
        path = self._path(self._creators_dir, creator.id)
        existing = _load(path)
        merged_extra = existing.get("extra", {}) | extra
        _save(path, {
            "id": creator.id,
            "name": creator.name,
            "avatar": creator.avatar,
            "fans_count": creator.fans_count,
            "media_count": creator.media_count,
            "raw": creator.raw,
            "extra": merged_extra,
            "updated_at": _now(),
        })

    def get_creator(self, creator_id: str) -> Creator | None:
        data = _load(self._path(self._creators_dir, creator_id))
        if not data.get("id"):
            return None
        return Creator(
            id=data["id"],
            name=data.get("name"),
            avatar=data.get("avatar"),
            fans_count=data.get("fans_count"),
            media_count=data.get("media_count"),
            raw=data.get("raw", {}),
        )

    def get_creator_extra(self, creator_id: str) -> dict[str, Any]:
        return _load(self._path(self._creators_dir, creator_id)).get("extra", {})

    def list_creator_ids(self) -> list[str]:
        """Return all stored creator IDs (reads each file to retrieve original ID)."""
        ids = []
        for p in sorted(self._creators_dir.glob("*.json")):
            data = _load(p)
            if data.get("id"):
                ids.append(data["id"])
        return ids

    # -- media --------------------------------------------------------------

    def upsert_media(self, media: Media, **extra: Any) -> None:
        path = self._path(self._media_dir, media.id)
        existing = _load(path)
        merged_extra = existing.get("extra", {}) | extra
        _save(path, {
            "id": media.id,
            "creator_id": media.creator_id,
            "kind": media.kind,
            "title": media.title,
            "description": media.description,
            "play_url": media.play_url,
            "cover": media.cover,
            "duration": media.duration,
            "created_at": media.created_at,
            "play_count": media.play_count,
            "like_count": media.like_count,
            "comment_count": media.comment_count,
            "raw": media.raw,
            "extra": merged_extra,
            "updated_at": _now(),
        })

    def get_media(self, media_id: str) -> Media | None:
        data = _load(self._path(self._media_dir, media_id))
        if not data.get("id"):
            return None
        return Media(
            id=data["id"],
            creator_id=data.get("creator_id"),
            kind=data.get("kind") or "video",
            title=data.get("title"),
            description=data.get("description"),
            play_url=data.get("play_url"),
            cover=data.get("cover"),
            duration=data.get("duration"),
            created_at=data.get("created_at"),
            play_count=data.get("play_count"),
            like_count=data.get("like_count"),
            comment_count=data.get("comment_count"),
            raw=data.get("raw", {}),
        )

    def get_media_extra(self, media_id: str) -> dict[str, Any]:
        return _load(self._path(self._media_dir, media_id)).get("extra", {})

    def list_creator_media(self, creator_id: str, *, kind: str | None = None) -> list[Media]:
        result = []
        for p in self._media_dir.glob("*.json"):
            data = _load(p)
            if data.get("creator_id") != creator_id:
                continue
            if kind is not None and data.get("kind") != kind:
                continue
            m = self.get_media(data["id"])
            if m:
                result.append(m)
        return result

    # -- forum posts --------------------------------------------------------

    def upsert_post(self, post: ForumPost, **extra: Any) -> None:
        path = self._path(self._posts_dir, post.id)
        existing = _load(path)
        merged_extra = existing.get("extra", {}) | extra
        _save(path, {
            "id": post.id,
            "creator_id": post.creator_id,
            "title": post.title,
            "content": post.content,
            "created_at": post.created_at,
            "reply_count": post.reply_count,
            "raw": post.raw,
            "extra": merged_extra,
            "updated_at": _now(),
        })

    # -- generic status updates ---------------------------------------------

    def mark_status(self, table: str, item_id: str, **fields: Any) -> None:
        path = self._path(self._dir_for_table(table), item_id)
        data = _load(path)
        if not data:
            return
        data["extra"] = data.get("extra", {}) | fields
        data["updated_at"] = _now()
        _save(path, data)
