from crawling_core.models import Creator, ForumPost, Media


def test_media_from_raw_uses_default_mapping():
    media = Media.from_raw(
        {"id": "v1", "title": "Hello", "playUrl": "http://x/v1.m3u8", "playCount": 42},
        kind="short",
    )
    assert media.id == "v1"
    assert media.title == "Hello"
    assert media.play_url == "http://x/v1.m3u8"
    assert media.play_count == "42"
    assert media.kind == "short"
    assert media.raw["playCount"] == 42


def test_media_from_raw_custom_mapping_overrides_lookup_order():
    media = Media.from_raw(
        {"video_url": "http://x/custom.m3u8", "playUrl": "http://x/ignored.m3u8"},
        fallback_id="fallback",
        mapping={"play_url": ("video_url",)},
    )
    assert media.id == "fallback"
    assert media.play_url == "http://x/custom.m3u8"


def test_creator_from_raw_picks_first_present_key():
    creator = Creator.from_raw({"uuid": "u1", "nickname": "Alice", "video_count": "5"})
    assert creator.id == "u1"
    assert creator.name == "Alice"
    assert creator.media_count == 5


def test_forum_post_from_raw():
    post = ForumPost.from_raw({"id": "p1", "title": "Hi", "replyCount": 3}, creator_id="u1")
    assert post.id == "p1"
    assert post.creator_id == "u1"
    assert post.reply_count == 3
