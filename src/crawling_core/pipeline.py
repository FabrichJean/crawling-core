"""Generic orchestration loops shared by every platform pipeline.

These functions stay deliberately dumb: they walk pages, call the adapter,
hand items to a callback, and stop on the conditions the adapter reports.
All platform-specific knowledge (how to paginate, how to detect "no more
pages", how to map a page to items) lives in the adapter; all
storage/download/transcode decisions live in the callback the caller passes
in. This keeps the loop reusable across wildly different platforms and
content shapes (videos, forum posts, photo sets, ...).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from crawling_core.adapters.base import CreatorMediaListing, PlatformAdapter
from crawling_core.models import Creator, Media

T = TypeVar("T")


def run_paginated(
    *,
    total_pages: int,
    fetch_page: Callable[[int], list[T]],
    on_page: Callable[[int, list[T]], None] | None = None,
    start_page: int = 1,
    max_pages: int | None = None,
) -> Iterable[T]:
    """Walk pages ``start_page..end`` yielding every item, in order.

    ``end`` is ``min(total_pages, start_page + max_pages - 1)`` when
    ``max_pages`` is given, else ``total_pages``. ``on_page`` is an optional
    progress hook invoked with ``(page_number, items)`` after each fetch.
    """
    end_page = total_pages
    if max_pages is not None:
        end_page = min(total_pages, start_page + max_pages - 1)

    for page in range(start_page, end_page + 1):
        items = fetch_page(page)
        if on_page:
            on_page(page, items)
        yield from items


def run_main_listing(
    adapter: PlatformAdapter,
    handle_media: Callable[[Media], object],
    *,
    start_page: int = 1,
    max_pages: int | None = None,
    workers: int = 1,
    on_page: Callable[[int, list[Media]], None] | None = None,
) -> None:
    """Scrape the adapter's main paginated listing, handing each item to
    ``handle_media``. When ``workers > 1`` items from a page are dispatched
    to a thread pool (mirrors the download/transcode fan-out pattern).
    """
    total_pages = adapter.get_total_pages()

    def fetch(page: int) -> list[Media]:
        return adapter.fetch_page(page)

    if workers <= 1:
        for media in run_paginated(
            total_pages=total_pages,
            fetch_page=fetch,
            on_page=on_page,
            start_page=start_page,
            max_pages=max_pages,
        ):
            handle_media(media)
        return

    end_page = total_pages if max_pages is None else min(total_pages, start_page + max_pages - 1)
    for page in range(start_page, end_page + 1):
        items = fetch(page)
        if on_page:
            on_page(page, items)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(handle_media, item) for item in items]
            for future in as_completed(futures):
                future.result()


def run_creator_media(
    adapter: CreatorMediaListing,
    creator: Creator,
    handle_media: Callable[[Media], object],
    *,
    kind: str | None = None,
    start_page: int = 1,
    max_pages: int | None = None,
) -> int:
    """Page through one creator's media until the adapter says to stop.

    Returns the number of items handled. Stopping is delegated to
    :meth:`CreatorMediaListing.has_more_creator_media` so platforms that
    know their true page count can stop precisely, while platforms that
    only know "empty page = end" can implement that heuristic instead.
    """
    handled = 0
    page = start_page
    while True:
        if max_pages is not None and page > start_page + max_pages - 1:
            break

        items = adapter.fetch_creator_media_page(creator, page, kind=kind)
        for media in items:
            handle_media(media)
            handled += 1

        if not adapter.has_more_creator_media(creator, page, items):
            break
        page += 1

    return handled
