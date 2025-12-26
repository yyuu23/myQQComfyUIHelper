from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import ensure_directory, load_json_file


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8088
    event_secret: str = ""
    request_log: bool = False


@dataclass
class QQConfig:
    bot_qq: int = 0
    api_base: str = "http://127.0.0.1:5700/"
    access_token: str = ""
    allowed_groups: List[int] = field(default_factory=list)
    processing_ack: str = ""
    completion_message: str = ""
    failure_message: str = ""


@dataclass
class ProcessingConfig:
    queue_size: int = 4
    download_dir: str = "data/data_in"
    output_dir: str = "data/data_out"
    cooldown_seconds: int = 5
    max_retries: int = 1
    debug: bool = False


@dataclass
class WorkflowImageOverride:
    node_id: int
    field: str


@dataclass
class WorkflowPromptOverride:
    node_id: int
    field: str


@dataclass
class WorkflowResolutionOverride:
    node_id: int
    width_field: str
    height_field: str


@dataclass
class WorkflowOverrides:
    image: List[WorkflowImageOverride] = field(default_factory=list)
    prompt: List[WorkflowPromptOverride] = field(default_factory=list)
    resolution: List[WorkflowResolutionOverride] = field(default_factory=list)


@dataclass
class ComfyUIConfig:
    api_base: str = "http://127.0.0.1:8188"
    workflow_path: str = "workflows/image_to_video.json"
    default_width: int = 768
    default_height: int = 1024
    timeout_seconds: int = 1800
    poll_interval_seconds: int = 5
    video_extension: str = "mp4"
    workflow_overrides: WorkflowOverrides = field(default_factory=WorkflowOverrides)


@dataclass
class AppConfig:
    server: ServerConfig
    qq: QQConfig
    processing: ProcessingConfig
    comfyui: ComfyUIConfig
    raw_path: Path


def _parse_workflow_overrides(raw: Dict) -> WorkflowOverrides:
    overrides = WorkflowOverrides()
    for item in raw.get("image", []):
        overrides.image.append(WorkflowImageOverride(node_id=item["node_id"], field=item["field"]))
    for item in raw.get("prompt", []):
        overrides.prompt.append(WorkflowPromptOverride(node_id=item["node_id"], field=item["field"]))
    for item in raw.get("resolution", []):
        overrides.resolution.append(
            WorkflowResolutionOverride(
                node_id=item["node_id"],
                width_field=item["width_field"],
                height_field=item["height_field"],
            )
        )
    return overrides


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    raw = load_json_file(config_path)
    server = ServerConfig(**raw.get("server", {}))
    qq = QQConfig(**raw.get("qq", {}))
    processing = ProcessingConfig(**raw.get("processing", {}))
    comfy_raw = raw.get("comfyui", {})
    overrides = _parse_workflow_overrides(comfy_raw.get("workflow_overrides", {}))
    comfy = ComfyUIConfig(
        api_base=comfy_raw.get("api_base", "http://127.0.0.1:8188"),
        workflow_path=comfy_raw.get("workflow_path", "workflows/image_to_video.json"),
        default_width=comfy_raw.get("default_width", 768),
        default_height=comfy_raw.get("default_height", 1024),
        timeout_seconds=comfy_raw.get("timeout_seconds", 1800),
        poll_interval_seconds=comfy_raw.get("poll_interval_seconds", 5),
        video_extension=comfy_raw.get("video_extension", "mp4"),
        workflow_overrides=overrides,
    )
    ensure_directory(processing.download_dir)
    ensure_directory(processing.output_dir)
    return AppConfig(server=server, qq=qq, processing=processing, comfyui=comfy, raw_path=config_path)
