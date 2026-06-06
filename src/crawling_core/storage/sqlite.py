"""Generic SQLite storage for creators / media / forum posts.

Rather than a fixed schema per platform (which forces a migration every
time a new platform needs one more status column), each table keeps:

- a handful of normalized columns shared by every platform (id, name/title,
  timestamps, ...) used for lookups and basic queries;
- ``raw_json``: the untouched payload from the API, for anything the
  normalized columns don't capture;
- ``extra_json``: a free-form bag of platform/pipeline status fields
  (``downloaded``, ``local_path``, ``cdn_url``, ``transcoded``, ...) that
  accumulates via :meth:`mark_status` without any DDL changes.

This trades a bit of query-ability (you can't `WHERE downloaded = 1` in
SQL — you'd filter in Python or add a generated column later) for zero
migrations when bootstrapping a new platform. If a platform's pipeline
grows enough to need indexed status queries, promote that one field to a
real column in a thin per-platform subclass/migration.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawling_core.models import Creator, ForumPost, Media

_SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
    id TEXT PRIMARY KEY,
    name TEXT,
    avatar TEXT,
    fans_count TEXT,
    media_count INTEGER,
    raw_json TEXT,
    extra_json TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    creator_id TEXT,
    kind TEXT,
    title TEXT,
    description TEXT,
    play_url TEXT,
    cover TEXT,
    duration INTEGER,
    created_at TEXT,
    play_count TEXT,
    like_count INTEGER,
    comment_count INTEGER,
    raw_json TEXT,
    extra_json TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_creator ON media (creator_id);

CREATE TABLE IF NOT EXISTS forum_posts (
    id TEXT PRIMARY KEY,
    creator_id TEXT,
    title TEXT,
    content TEXT,
    created_at TEXT,
    reply_count INTEGER,
    raw_json TEXT,
    extra_json TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_creator ON forum_posts (creator_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class SqliteStorage:
    """Thread-safe-enough storage: opens a short-lived connection per call,
    matching the pattern used by the original per-platform databases."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(_SCHEMA)

    # -- creators ---------------------------------------------------------

    def upsert_creator(self, creator: Creator, **extra: Any) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT extra_json FROM creators WHERE id = ?", (creator.id,)
            ).fetchone()
            merged_extra = _load(existing["extra_json"] if existing else None) | extra
            conn.execute(
                """
                INSERT INTO creators
                    (id, name, avatar, fans_count, media_count, raw_json, extra_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    avatar=excluded.avatar,
                    fans_count=excluded.fans_count,
                    media_count=excluded.media_count,
                    raw_json=excluded.raw_json,
                    extra_json=excluded.extra_json,
                    updated_at=excluded.updated_at
                """,
                (
                    creator.id,
                    creator.name,
                    creator.avatar,
                    creator.fans_count,
                    creator.media_count,
                    _dump(creator.raw),
                    _dump(merged_extra),
                    _now(),
                ),
            )

    def get_creator(self, creator_id: str) -> Creator | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM creators WHERE id = ?", (creator_id,)).fetchone()
        if row is None:
            return None
        return Creator(
            id=row["id"],
            name=row["name"],
            avatar=row["avatar"],
            fans_count=row["fans_count"],
            media_count=row["media_count"],
            raw=_load(row["raw_json"]),
        )

    def get_creator_extra(self, creator_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT extra_json FROM creators WHERE id = ?", (creator_id,)
            ).fetchone()
        return _load(row["extra_json"]) if row else {}

    # -- media -------------------------------------------------------------

    def upsert_media(self, media: Media, **extra: Any) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT extra_json FROM media WHERE id = ?", (media.id,)
            ).fetchone()
            merged_extra = _load(existing["extra_json"] if existing else None) | extra
            conn.execute(
                """
                INSERT INTO media (
                    id, creator_id, kind, title, description, play_url, cover,
                    duration, created_at, play_count, like_count, comment_count,
                    raw_json, extra_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    creator_id=excluded.creator_id,
                    kind=excluded.kind,
                    title=excluded.title,
                    description=excluded.description,
                    play_url=excluded.play_url,
                    cover=excluded.cover,
                    duration=excluded.duration,
                    created_at=excluded.created_at,
                    play_count=excluded.play_count,
                    like_count=excluded.like_count,
                    comment_count=excluded.comment_count,
                    raw_json=excluded.raw_json,
                    extra_json=excluded.extra_json,
                    updated_at=excluded.updated_at
                """,
                (
                    media.id,
                    media.creator_id,
                    media.kind,
                    media.title,
                    media.description,
                    media.play_url,
                    media.cover,
                    media.duration,
                    media.created_at,
                    media.play_count,
                    media.like_count,
                    media.comment_count,
                    _dump(media.raw),
                    _dump(merged_extra),
                    _now(),
                ),
            )

    def get_media(self, media_id: str) -> Media | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        if row is None:
            return None
        return Media(
            id=row["id"],
            creator_id=row["creator_id"],
            kind=row["kind"] or "video",
            title=row["title"],
            description=row["description"],
            play_url=row["play_url"],
            cover=row["cover"],
            duration=row["duration"],
            created_at=row["created_at"],
            play_count=row["play_count"],
            like_count=row["like_count"],
            comment_count=row["comment_count"],
            raw=_load(row["raw_json"]),
        )

    def list_creator_media(self, creator_id: str, *, kind: str | None = None) -> list[Media]:
        query = "SELECT * FROM media WHERE creator_id = ?"
        params: list[Any] = [creator_id]
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            Media(
                id=row["id"],
                creator_id=row["creator_id"],
                kind=row["kind"] or "video",
                title=row["title"],
                description=row["description"],
                play_url=row["play_url"],
                cover=row["cover"],
                duration=row["duration"],
                created_at=row["created_at"],
                play_count=row["play_count"],
                like_count=row["like_count"],
                comment_count=row["comment_count"],
                raw=_load(row["raw_json"]),
            )
            for row in rows
        ]

    # -- forum posts --------------------------------------------------------

    def upsert_post(self, post: ForumPost, **extra: Any) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT extra_json FROM forum_posts WHERE id = ?", (post.id,)
            ).fetchone()
            merged_extra = _load(existing["extra_json"] if existing else None) | extra
            conn.execute(
                """
                INSERT INTO forum_posts
                    (id, creator_id, title, content, created_at, reply_count,
                     raw_json, extra_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    creator_id=excluded.creator_id,
                    title=excluded.title,
                    content=excluded.content,
                    created_at=excluded.created_at,
                    reply_count=excluded.reply_count,
                    raw_json=excluded.raw_json,
                    extra_json=excluded.extra_json,
                    updated_at=excluded.updated_at
                """,
                (
                    post.id,
                    post.creator_id,
                    post.title,
                    post.content,
                    post.created_at,
                    post.reply_count,
                    _dump(post.raw),
                    _dump(merged_extra),
                    _now(),
                ),
            )

    # -- generic status updates ---------------------------------------------

    _TABLES = {"creators": "creators", "media": "media", "posts": "forum_posts"}

    def mark_status(self, table: str, item_id: str, **fields: Any) -> None:
        """Merge ``fields`` into ``extra_json`` for the row ``item_id`` in
        ``table`` (one of ``"creators"``, ``"media"``, ``"posts"``). Useful
        for pipeline bookkeeping like ``downloaded=True, local_path=...``
        without touching the schema.
        """
        table_name = self._TABLES.get(table, table)
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT extra_json FROM {table_name} WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return
            merged = _load(row["extra_json"]) | fields
            conn.execute(
                f"UPDATE {table_name} SET extra_json = ?, updated_at = ? WHERE id = ?",
                (_dump(merged), _now(), item_id),
            )
