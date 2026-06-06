from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - requests is a hard dependency, but stay defensive
    requests = None  # type: ignore

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
EXTINF_PATTERN = re.compile(r"#EXTINF:\s*([\d.]+)")


def safe_filename(value: str, max_length: int = 120) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", value).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length]


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def extract_m3u8_duration(m3u8_url: str, timeout: float = 10.0) -> int | None:
    """Sum the ``#EXTINF`` values of an M3U8 playlist to estimate its duration in seconds."""
    if not requests:
        return None
    try:
        response = requests.get(m3u8_url, timeout=timeout)
        response.raise_for_status()
        values = EXTINF_PATTERN.findall(response.text)
        if not values:
            return None
        return int(sum(float(v) for v in values))
    except Exception:
        return None


def export_json(output_dir: Path, filename_stem: str, payload: dict[str, Any]) -> Path | None:
    """Write ``payload`` as pretty JSON to ``output_dir/<safe filename_stem>.json``."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{safe_filename(filename_stem, 120)}.json"
        write_text(json_path, dump_json(payload))
        return json_path
    except Exception:
        return None
