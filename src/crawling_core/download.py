"""Generic M3U8/file downloader.

Deliberately config-shape-agnostic: it takes plain values (output dir,
headers, timeout, optional key-URI rewrite) rather than a platform's
``Settings`` object, and an optional ``storage`` + ``build_url`` so it can
record progress without knowing how the platform models its DB rows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from crawling_core.models import Media
from crawling_core.storage.base import Storage
from crawling_core.utils import safe_filename, write_text


@dataclass(frozen=True, slots=True)
class DownloadResult:
    media: Media
    path: Path


class M3U8Downloader:
    def __init__(
        self,
        *,
        output_dir: Path,
        build_url: Callable[[Media], str],
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        key_uri_rewrite: tuple[str, str] | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.build_url = build_url
        self.headers = headers or {}
        self.timeout = timeout
        self.key_uri_rewrite = key_uri_rewrite
        self.storage = storage

    def download(self, media: Media) -> DownloadResult | None:
        if not media.play_url:
            print(f"[download] Missing play_url for {media.title or media.id}")
            self._mark(media.id, downloaded=False)
            return None

        url = self.build_url(media)
        filename = f"{safe_filename(media.id, 40)}_{safe_filename(media.title or media.id)}.m3u8"
        output_path = self.output_dir / filename

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            if response.status_code != 200:
                status = response.status_code
                print(f"[download] Failed {status}: {(media.title or media.id)[:70]}")
                self._mark(media.id, downloaded=False, download_error=f"http_{status}")
                return None

            content = self._rewrite_playlist(response.text)
            write_text(output_path, content)
            self._mark(media.id, downloaded=True, local_m3u8_path=str(output_path.resolve()))
            print(f"[download] Saved: {output_path.name}")
            return DownloadResult(media=media, path=output_path)
        except Exception as exc:
            print(f"[download] Error for {(media.title or media.id)[:70]}: {exc}")
            self._mark(media.id, downloaded=False, download_error=str(exc))
            return None

    def _rewrite_playlist(self, content: str) -> str:
        if self.key_uri_rewrite:
            old, new = self.key_uri_rewrite
            return content.replace(old, new)
        return content

    def _mark(self, media_id: str, **fields: object) -> None:
        if self.storage is not None:
            self.storage.mark_status("media", media_id, **fields)
