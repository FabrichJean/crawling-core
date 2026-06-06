"""Generic FFmpeg transcoder: M3U8/source URL -> MP4, fanned out on a thread pool."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from crawling_core.models import Media
from crawling_core.storage.base import Storage
from crawling_core.utils import safe_filename


class FfmpegTranscoder:
    def __init__(
        self,
        *,
        output_dir: Path,
        build_url: Callable[[Media], str],
        workers: int = 2,
        ffmpeg_timeout: int = 1800,
        storage: Storage | None = None,
        on_done: Callable[[Media, Path], None] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.build_url = build_url
        self.ffmpeg_timeout = ffmpeg_timeout
        self.storage = storage
        self.on_done = on_done
        self.executor = ThreadPoolExecutor(max_workers=workers)

    def submit(self, media: Media) -> Future[Path | None]:
        print(f"[transcode] Queued: {(media.title or media.id)[:70]} ({media.id})")
        return self.executor.submit(self.transcode, media)

    def shutdown(self, *, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait)

    def transcode(self, media: Media) -> Path | None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("[transcode] FFmpeg not found on PATH.")
            return None

        output_path = self.output_dir / f"{safe_filename(media.id, 80)}.mp4"
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"[transcode] Existing MP4: {output_path.name}")
            self._finish(media, output_path)
            return output_path

        url = self.build_url(media)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg, "-y",
            "-i", url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            str(output_path),
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=self.ffmpeg_timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"[transcode] Timed out: {(media.title or media.id)[:70]}")
            self._mark(media.id, transcoded=False, transcode_error="timeout")
            return None
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", "ignore")[-500:] if exc.stderr else ""
            print(f"[transcode] FFmpeg failed: {(media.title or media.id)[:70]}: {stderr}")
            self._mark(media.id, transcoded=False, transcode_error=stderr)
            return None

        self._finish(media, output_path)
        return output_path

    def _finish(self, media: Media, output_path: Path) -> None:
        self._mark(media.id, transcoded=True, local_mp4_path=str(output_path.resolve()))
        if self.on_done:
            self.on_done(media, output_path)

    def _mark(self, media_id: str, **fields: object) -> None:
        if self.storage is not None:
            self.storage.mark_status("media", media_id, **fields)
