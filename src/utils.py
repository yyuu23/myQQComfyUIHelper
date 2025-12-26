from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

LOGGER = logging.getLogger("comfy_helper")

CQ_PATTERN = re.compile(r"\[CQ:(?P<type>\w+)(?P<data>[^\]]*)\]")
RESOLUTION_HINT = re.compile(r"(?P<w>\d{2,4})\s*[xX\*]\s*(?P<h>\d{2,4})")


def ensure_directory(path: str | Path) -> Path:
    """Create the directory if missing and return it as Path."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_json_file(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_cq_text(message: str) -> List[Dict]:
    """Parse CQ code text into a list of segments."""
    segments: List[Dict] = []
    idx = 0
    for match in CQ_PATTERN.finditer(message):
        start, end = match.span()
        if start > idx:
            segments.append({"type": "text", "data": {"text": message[idx:start]}})
        segment_type = match.group("type")
        raw_data = match.group("data").lstrip(",")
        data_dict: Dict[str, str] = {}
        if raw_data:
            for part in raw_data.split(","):
                if "=" not in part:
                    continue
                key, value = part.split("=", 1)
                data_dict[key] = value.replace("&amp;", "&").replace("&#44;", ",")
        segments.append({"type": segment_type, "data": data_dict})
        idx = end
    if idx < len(message):
        segments.append({"type": "text", "data": {"text": message[idx:]}})
    return segments


def normalize_segments(message: object) -> List[Dict]:
    """Normalize message data into segment dicts."""
    if isinstance(message, list):
        return message
    if isinstance(message, str):
        return parse_cq_text(message)
    return []


def extract_plain_text(segments: Sequence[Dict], skip_mentions: bool = True) -> str:
    """Concatenate text segments, optionally skipping @ mentions."""
    texts: List[str] = []
    for seg in segments:
        seg_type = seg.get("type")
        if seg_type == "text":
            texts.append(seg.get("data", {}).get("text", ""))
        elif seg_type == "at" and skip_mentions:
            continue
    return " ".join(part.strip() for part in texts if part.strip())


def find_first_image_url(segments: Sequence[Dict]) -> Optional[str]:
    for seg in segments:
        if seg.get("type") == "image":
            data = seg.get("data") or {}
            return data.get("url") or data.get("file") or data.get("path")
    return None


def contains_at_me(segments: Sequence[Dict], bot_qq: int | str) -> bool:
    target = str(bot_qq)
    for seg in segments:
        if seg.get("type") != "at":
            continue
        data = seg.get("data") or {}
        qq = data.get("qq")
        if qq == target or qq == "all":
            return True
    return False


def parse_resolution_from_text(text: str, default: Tuple[int, int]) -> Tuple[int, int]:
    match = RESOLUTION_HINT.search(text)
    if not match:
        return default
    width = int(match.group("w"))
    height = int(match.group("h"))
    if width < 64 or height < 64:
        return default
    return width, height


def slugify_filename(name: str, default: str = "file") -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return slug or default


def human_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def unique_task_id(prefix: str = "task") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    expected = "sha1=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, signature)
