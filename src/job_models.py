from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class VideoJob:
    job_id: str
    group_id: int
    user_id: int
    sender_name: str
    prompt: str
    image_url: str
    resolution: Tuple[int, int]
    message_id: Optional[int]
    raw_event: Dict
