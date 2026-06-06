from pathlib import Path

import pytest

from crawling_core.models import Creator, ForumPost, Media
from crawling_core.storage.sqlite import SqliteStorage


@pytest.fixture
def storage(tmp_path: Path) -> SqliteStorage:
    db = SqliteStorage(tmp_path / "test.db")
    db.initialize()
    return db


def test_creator_upsert_and_get(storage: SqliteStorage):
    creator = Creator.from_raw({"uuid": "u1", "nickname": "Alice"})
    storage.upsert_creator(creator, mirrored=True)

    fetched = storage.get_creator("u1")
    assert fetched is not None
    assert fetched.name == "Alice"
    assert storage.get_creator_extra("u1") == {"mirrored": True}


def test_creator_extra_merges_across_upserts(storage: SqliteStorage):
    creator = Creator.from_raw({"uuid": "u1", "nickname": "Alice"})
    storage.upsert_creator(creator, mirrored=True)
    storage.upsert_creator(creator, cdn_url="https://cdn/x.png")

    assert storage.get_creator_extra("u1") == {"mirrored": True, "cdn_url": "https://cdn/x.png"}


def test_media_upsert_get_and_list_by_creator(storage: SqliteStorage):
    media = Media.from_raw(
        {"id": "v1", "title": "Hello", "playUrl": "http://x/v1.m3u8"},
        creator_id="u1",
        kind="short",
    )
    storage.upsert_media(media)

    fetched = storage.get_media("v1")
    assert fetched is not None
    assert fetched.title == "Hello"
    assert fetched.kind == "short"

    same_creator = storage.list_creator_media("u1")
    assert [m.id for m in same_creator] == ["v1"]
    assert storage.list_creator_media("u1", kind="long") == []


def test_mark_status_merges_into_extra(storage: SqliteStorage):
    media = Media.from_raw({"id": "v1", "title": "Hello"}, creator_id="u1")
    storage.upsert_media(media)

    storage.mark_status("media", "v1", downloaded=True, local_m3u8_path="/tmp/v1.m3u8")
    storage.mark_status("media", "v1", transcoded=True)

    with storage.connect() as conn:
        row = conn.execute("SELECT extra_json FROM media WHERE id = 'v1'").fetchone()
    import json
    assert json.loads(row["extra_json"]) == {
        "downloaded": True,
        "local_m3u8_path": "/tmp/v1.m3u8",
        "transcoded": True,
    }


def test_mark_status_noop_for_missing_row(storage: SqliteStorage):
    storage.mark_status("media", "missing", downloaded=True)  # should not raise


def test_forum_post_upsert(storage: SqliteStorage):
    post = ForumPost.from_raw({"id": "p1", "title": "Hi"}, creator_id="u1")
    storage.upsert_post(post)

    with storage.connect() as conn:
        row = conn.execute("SELECT * FROM forum_posts WHERE id = 'p1'").fetchone()
    assert row["title"] == "Hi"
    assert row["creator_id"] == "u1"
