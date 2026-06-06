"""The contract every platform adapter must satisfy.

A platform adapter is the *only* thing that should know about a given
site's API shape, pagination quirks, and encoding. Everything downstream
(pipeline, storage, downloader, transcoder, exporter) works purely against
these Protocols and the generic models in :mod:`crawling_core.models`.

Implement only the methods your scraping strategy actually needs — e.g. a
forum-only platform may implement ``PlatformAdapter`` plus
``ForumListing`` and skip ``CreatorMediaListing`` entirely. The pipeline
helpers check ``hasattr`` / ``isinstance`` before calling optional pieces.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from crawling_core.models import Creator, ForumPost, Media


@runtime_checkable
class PlatformAdapter(Protocol):
    """Minimal capability every adapter has: paginated content discovery."""

    def get_total_pages(self) -> int:
        """Total number of pages in the main listing (e.g. the home/featured feed)."""

    def fetch_page(self, page: int) -> list[Media]:
        """Fetch and normalize one page of the main listing."""

    def build_media_url(self, media: Media) -> str:
        """Resolve a playable/downloadable URL for a piece of media."""


@runtime_checkable
class CreatorListing(Protocol):
    """Optional: platforms that expose a browsable creator/author directory."""

    def get_creator_total_pages(self) -> int:
        ...

    def fetch_creator_page(self, page: int) -> list[Creator]:
        ...


@runtime_checkable
class CreatorMediaListing(Protocol):
    """Optional: platforms where you can list a given creator's media."""

    def fetch_creator_media_page(
        self, creator: Creator, page: int, *, kind: str | None = None
    ) -> list[Media]:
        """Fetch one page of a creator's media. ``kind`` lets callers ask for
        a specific bucket (e.g. "short" vs "long") on platforms that split
        them into separate endpoints; adapters that don't split can ignore it.
        """

    def has_more_creator_media(self, creator: Creator, page: int, fetched: list[Media]) -> bool:
        """Whether to keep paginating a creator's media. Default heuristic
        callers may use: ``len(fetched) > 0``, but platforms with known page
        sizes/totals should override via this hook for accuracy.
        """


@runtime_checkable
class ForumListing(Protocol):
    """Optional: platforms with a forum/community board per creator or globally."""

    def fetch_forum_page(self, page: int, *, creator: Creator | None = None) -> list[ForumPost]:
        ...
