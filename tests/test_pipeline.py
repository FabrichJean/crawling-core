from crawling_core.models import Creator, Media
from crawling_core.pipeline import run_creator_media, run_main_listing, run_paginated


def test_run_paginated_yields_in_order_and_respects_max_pages():
    pages = {1: ["a", "b"], 2: ["c"], 3: ["d", "e"]}
    seen_pages = []

    def fetch(page):
        return pages[page]

    items = list(
        run_paginated(
            total_pages=3,
            fetch_page=fetch,
            on_page=lambda p, items: seen_pages.append((p, items)),
            max_pages=2,
        )
    )
    assert items == ["a", "b", "c"]
    assert seen_pages == [(1, ["a", "b"]), (2, ["c"])]


class _FakeAdapter:
    def __init__(self):
        self.pages = {1: [Media(id="v1"), Media(id="v2")], 2: [Media(id="v3")]}

    def get_total_pages(self) -> int:
        return 2

    def fetch_page(self, page: int):
        return self.pages[page]

    def build_media_url(self, media: Media) -> str:
        return f"https://x/{media.id}.m3u8"


def test_run_main_listing_single_threaded():
    adapter = _FakeAdapter()
    handled = []
    run_main_listing(adapter, handled.append)
    assert [m.id for m in handled] == ["v1", "v2", "v3"]


def test_run_main_listing_with_workers():
    adapter = _FakeAdapter()
    handled = []
    run_main_listing(adapter, handled.append, workers=4)
    assert sorted(m.id for m in handled) == ["v1", "v2", "v3"]


class _FakeCreatorMediaAdapter:
    def __init__(self):
        self.pages = {1: [Media(id="v1"), Media(id="v2")], 2: [Media(id="v3")], 3: []}

    def fetch_creator_media_page(self, creator, page, *, kind=None):
        return self.pages.get(page, [])

    def has_more_creator_media(self, creator, page, fetched):
        return len(fetched) > 0


def test_run_creator_media_stops_on_empty_page():
    adapter = _FakeCreatorMediaAdapter()
    creator = Creator(id="u1")
    handled = []

    count = run_creator_media(adapter, creator, handled.append)

    assert count == 3
    assert [m.id for m in handled] == ["v1", "v2", "v3"]


def test_run_creator_media_respects_max_pages():
    adapter = _FakeCreatorMediaAdapter()
    creator = Creator(id="u1")
    handled = []

    count = run_creator_media(adapter, creator, handled.append, max_pages=1)

    assert count == 2
    assert [m.id for m in handled] == ["v1", "v2"]
