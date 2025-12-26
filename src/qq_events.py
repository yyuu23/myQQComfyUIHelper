from __future__ import annotations

import logging
import re
from typing import Dict, Optional, Sequence

from .config_loader import AppConfig
from .job_models import VideoJob
from .utils import (
    contains_at_me,
    extract_plain_text,
    find_first_image_url,
    normalize_segments,
    parse_resolution_from_text,
    unique_task_id,
)

LOGGER = logging.getLogger("comfy_helper.qq_events")
RESOLUTION_HINT = re.compile(r"\d{2,4}\s*[xX\*]\s*\d{2,4}")


def _allowed_group(group_id: int, allowed: Sequence[int]) -> bool:
    if not allowed:
        return True
    return group_id in allowed


def _clean_prompt_text(text: str) -> str:
    if not text:
        return ""
    return RESOLUTION_HINT.sub("", text).strip()


def build_job_from_event(event: Dict, config: AppConfig) -> Optional[VideoJob]:
    if event.get("message_type") != "group":
        return None
    group_id = event.get("group_id")
    if group_id is None or not _allowed_group(group_id, config.qq.allowed_groups):
        return None
    message = event.get("message")
    segments = normalize_segments(message)
    if not segments and "raw_message" in event:
        segments = normalize_segments(event.get("raw_message"))
    if not segments:
        return None
    if not contains_at_me(segments, config.qq.bot_qq):
        return None
    image_url = find_first_image_url(segments)
    if not image_url:
        LOGGER.debug("No image in message %s", event.get("message_id"))
        return None
    text = extract_plain_text(segments, skip_mentions=True)
    resolution = parse_resolution_from_text(text, (config.comfyui.default_width, config.comfyui.default_height))
    prompt = _clean_prompt_text(text)
    sender = event.get("sender") or {}
    sender_name = sender.get("card") or sender.get("nickname") or str(event.get("user_id", "user"))
    job = VideoJob(
        job_id=unique_task_id("video"),
        group_id=int(group_id),
        user_id=int(event.get("user_id", 0)),
        sender_name=sender_name,
        prompt=prompt,
        image_url=image_url,
        resolution=resolution,
        message_id=event.get("message_id"),
        raw_event=event,
    )
    return job
