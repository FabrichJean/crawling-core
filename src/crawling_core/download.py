"""Generic M3U8/file downloader.

Deliberately config-shape-agnostic: it takes plain values (output dir,
headers, timeout, optional key-URI rewrite) rather than a platform's
``Settings`` object, and an optional ``storage`` + ``build_url`` so it can
record progress without knowing how the platform models its DB rows.
"""

from __future__ import annotations

import re
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
        stem = f"{safe_filename(media.id, 40)}_{safe_filename(media.title or media.id)}"
        output_path = self.output_dir / f"{stem}.m3u8"
        segments_dir = self.output_dir / stem

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            if response.status_code != 200:
                status = response.status_code
                print(f"[download] Failed {status}: {(media.title or media.id)[:70]}")
                self._mark(media.id, downloaded=False, download_error=f"http_{status}")
                return None

            content = response.content

            # Only localise proper HLS playlists (text starting with #EXTM3U)
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = None

            if text and text.lstrip().startswith("#EXTM3U"):
                text = self._localise(text, segments_dir, url)
                write_text(output_path, text)
            else:
                # Binary or non-HLS content — save raw, FFmpeg will use CDN URL
                output_path.write_bytes(content)
                print(f"[download] Non-HLS content, saved raw: {output_path.name}")

            self._mark(media.id, downloaded=True, local_m3u8_path=str(output_path.resolve()))
            print(f"[download] Saved: {output_path.name}")
            return DownloadResult(media=media, path=output_path)
        except Exception as exc:
            print(f"[download] Error for {(media.title or media.id)[:70]}: {exc}")
            self._mark(media.id, downloaded=False, download_error=str(exc))
            return None

    # ── segment + key localisation ────────────────────────────────────────────

    @staticmethod
    def _ffmpeg_safe(path: str) -> str:
        """Escape characters that FFmpeg's HLS parser treats as special ([ ] are glob/IPv6)."""
        return path.replace("[", "%5B").replace("]", "%5D")

    def _localise(self, playlist: str, segments_dir: Path, playlist_url: str) -> str:
        """Download every .ts segment and AES key; rewrite the playlist to use local paths."""
        lines = playlist.splitlines()
        rewritten: list[str] = []
        segment_index = 0

        for line in lines:
            # AES-128 key URI
            key_match = re.match(
                r'(#EXT-X-KEY:[^"]*URI=")([^"]+)(".*)', line
            )
            if key_match:
                key_url = self._resolve(key_match.group(2), playlist_url)
                key_path = self._fetch_file(key_url, segments_dir, "crypt.key")
                if key_path:
                    # Absolute file:// URI so FFmpeg reads the key locally regardless of
                    # Chinese/special characters in the relative path
                    local_uri = key_path.resolve().as_uri()
                    line = key_match.group(1) + local_uri + key_match.group(3)
                elif self.key_uri_rewrite:
                    old, new = self.key_uri_rewrite
                    line = line.replace(old, new)
                rewritten.append(line)
                continue

            # .ts segment line (any non-comment non-empty line after #EXTINF)
            if line and not line.startswith("#"):
                seg_url = self._resolve(line.strip(), playlist_url)
                seg_path = self._fetch_file(
                    seg_url, segments_dir, f"seg{segment_index:05d}.ts"
                )
                if seg_path:
                    # Absolute file:// URI so FFmpeg resolves correctly regardless of
                    # special characters (Chinese, brackets, spaces) in the path
                    rewritten.append(seg_path.resolve().as_uri())
                else:
                    rewritten.append(line)
                segment_index += 1
                continue

            rewritten.append(line)

        return "\n".join(rewritten)

    def _resolve(self, url: str, base: str) -> str:
        """Make relative URLs absolute using the playlist base URL."""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        from urllib.parse import urljoin
        return urljoin(base, url)

    def _fetch_file(self, url: str, dest_dir: Path, filename: str) -> Path | None:
        """Download a single file to dest_dir/filename; return the path or None on error."""
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename
            if dest.exists():
                return dest
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
        except Exception as exc:
            print(f"[download] Segment error {filename}: {exc}")
            return None

    # ── storage helper ────────────────────────────────────────────────────────

    def _mark(self, media_id: str, **fields: object) -> None:
        if self.storage is not None:
            self.storage.mark_status("media", media_id, **fields)
