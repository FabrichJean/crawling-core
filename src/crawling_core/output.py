"""Generic local "drop folder" delivery: move the transcoded file into place
and write a JSON sidecar with media + creator metadata next to it.

This is the platform-agnostic core of what the original project's
``VmsSender`` did — moving the MP4 and exporting JSON — minus anything
platform-specific (R2 mirroring, VMS-specific upload protocols, ...),
which belongs in the platform project.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from crawling_core.models import Creator, Media
from crawling_core.storage.base import Storage
from crawling_core.utils import dump_json, export_json, safe_filename, write_text


def _media_payload(media: Media, **extra: Any) -> dict[str, Any]:
    return {
        "id": media.id,
        "creator_id": media.creator_id,
        "kind": media.kind,
        "title": media.title,
        "description": media.description,
        "cover": media.cover,
        "play_url": media.play_url,
        "duration": media.duration,
        "created_at": media.created_at,
        "play_count": media.play_count,
        "like_count": media.like_count,
        "comment_count": media.comment_count,
        **extra,
    }


def _creator_payload(creator: Creator) -> dict[str, Any]:
    return {
        "id": creator.id,
        "name": creator.name,
        "avatar": creator.avatar,
        "fans_count": creator.fans_count,
        "media_count": creator.media_count,
    }


class LocalOutput:
    """Moves a transcoded file into ``final_dir`` and exports JSON metadata
    (sidecar next to the file, plus an optional combined export with
    creator info in ``export_dir``)."""

    def __init__(
        self,
        *,
        final_dir: Path,
        export_dir: Path | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.final_dir = Path(final_dir)
        self.export_dir = Path(export_dir) if export_dir else None
        self.storage = storage

    def deliver(self, media: Media, source_path: Path, *, creator: Creator | None = None) -> bool:
        if not source_path.exists():
            print(f"[output] Source not found: {source_path}")
            return False

        final_path = self.final_dir / f"{safe_filename(media.id, 80)}.mp4"
        try:
            self.final_dir.mkdir(parents=True, exist_ok=True)
            if source_path.resolve() != final_path.resolve():
                if final_path.exists():
                    final_path.unlink()
                shutil.move(str(source_path), str(final_path))

            sidecar = {
                "media_id": media.id,
                "file_path": str(final_path.resolve()),
                "file_size_mb": final_path.stat().st_size / 1024 / 1024,
                "delivered_at": datetime.now().isoformat(timespec="seconds"),
                "media": _media_payload(media),
            }
            write_text(
                self.final_dir / f"{safe_filename(media.id, 80)}.json",
                dump_json(sidecar),
            )

            if self.export_dir is not None:
                export_json(
                    self.export_dir,
                    f"{safe_filename(media.id, 40)}_{safe_filename(media.title or media.id, 80)}",
                    {
                        "media": _media_payload(media, transcoded_mp4=str(final_path.resolve())),
                        "creator": _creator_payload(creator) if creator else {},
                    },
                )

            if self.storage is not None:
                self.storage.mark_status(
                    "media", media.id, delivered=True, final_path=str(final_path.resolve())
                )
            print(f"[output] Delivered: {(media.title or media.id)[:70]}")
            return True
        except Exception as exc:
            print(f"[output] Delivery failed for {media.id}: {exc}")
            return False
