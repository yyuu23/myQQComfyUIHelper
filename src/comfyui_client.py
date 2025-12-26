from __future__ import annotations

import io
import json
import logging
import mimetypes
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config_loader import ComfyUIConfig
from .utils import ensure_directory, load_json_file

LOGGER = logging.getLogger("comfy_helper.comfyui")


class ComfyUIClient:
    def __init__(self, config: ComfyUIConfig, output_dir: str):
        self.config = config
        self.base_url = config.api_base.rstrip("/") + "/"
        self.workflow_path = Path(config.workflow_path)
        self.client_id = uuid.uuid4().hex
        self.output_dir = ensure_directory(output_dir)

    def generate_video(self, image_path: Path, prompt: str, resolution: Tuple[int, int], job_id: str) -> Path:
        workflow = self._load_workflow()
        image_name = self._upload_image(image_path, job_id)
        self._apply_image(workflow, image_name)
        self._apply_prompt(workflow, prompt)
        self._apply_resolution(workflow, resolution)
        payload = {"prompt": workflow, "client_id": self.client_id}
        response = self._post_json("prompt", payload)
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return prompt_id")
        LOGGER.info("Submitted job %s to ComfyUI prompt %s", job_id, prompt_id)
        history = self._wait_for_completion(prompt_id)
        descriptor = self._pick_video_descriptor(history)
        if not descriptor:
            raise RuntimeError("No video output returned by ComfyUI")
        return self._download_output(descriptor, job_id)

    def _load_workflow(self) -> Dict:
        return load_json_file(self.workflow_path)

    def _apply_image(self, workflow: Dict, image_name: str) -> None:
        for item in self.config.workflow_overrides.image:
            node = self._find_node(workflow, item.node_id)
            if node:
                node.setdefault("inputs", {})[item.field] = image_name

    def _apply_prompt(self, workflow: Dict, prompt: str) -> None:
        for item in self.config.workflow_overrides.prompt:
            node = self._find_node(workflow, item.node_id)
            if node:
                node.setdefault("inputs", {})[item.field] = prompt or ""

    def _apply_resolution(self, workflow: Dict, resolution: Tuple[int, int]) -> None:
        width, height = resolution
        for item in self.config.workflow_overrides.resolution:
            node = self._find_node(workflow, item.node_id)
            if node:
                inputs = node.setdefault("inputs", {})
                inputs[item.width_field] = width
                inputs[item.height_field] = height

    def _find_node(self, workflow: Dict, node_id: int) -> Optional[Dict]:
        for node in workflow.get("nodes", []):
            if node.get("id") == node_id:
                return node
        return None

    def _upload_image(self, image_path: Path, job_id: str) -> str:
        file_name = f"{job_id}_{image_path.name}"
        file_bytes = image_path.read_bytes()
        mime_type = mimetypes.guess_type(file_name)[0] or "image/png"
        fields = {
            "subfolder": "bot_inputs",
            "type": "input",
            "overwrite": "true",
        }
        files = {"image": (file_name, file_bytes, mime_type)}
        body, content_type = self._encode_multipart(fields, files)
        url = urllib.parse.urljoin(self.base_url, "upload/image")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
        return file_name

    def _post_json(self, endpoint: str, payload: Dict) -> Dict:
        url = urllib.parse.urljoin(self.base_url, endpoint.lstrip("/"))
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
        return json.loads(body.decode("utf-8"))

    def _wait_for_completion(self, prompt_id: str) -> Dict:
        deadline = time.time() + self.config.timeout_seconds
        while time.time() < deadline:
            history_raw = self._get_json(f"history/{prompt_id}")
            history = history_raw.get(prompt_id, history_raw)
            status = history.get("status") or {}
            status_value = status.get("status")
            if status_value == "completed":
                return history
            if status_value == "error":
                raise RuntimeError(f"ComfyUI error: {status.get('detail')}")
            time.sleep(self.config.poll_interval_seconds)
        raise TimeoutError("ComfyUI processing timed out")

    def _get_json(self, endpoint: str) -> Dict:
        url = urllib.parse.urljoin(self.base_url, endpoint.lstrip("/"))
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
        return json.loads(body.decode("utf-8"))

    def _pick_video_descriptor(self, history: Dict) -> Optional[Dict]:
        outputs = history.get("outputs") or {}
        for node in outputs.values():
            videos = node.get("videos") or []
            if videos:
                return videos[0]
            images = node.get("images") or []
            if images:
                LOGGER.warning("Workflow returned image instead of video; using first image output.")
                return images[0]
        return None

    def _download_output(self, descriptor: Dict, job_id: str) -> Path:
        params = urllib.parse.urlencode(
            {
                "filename": descriptor.get("filename"),
                "subfolder": descriptor.get("subfolder", ""),
                "type": descriptor.get("type", "output"),
            }
        )
        url = urllib.parse.urljoin(self.base_url, f"view?{params}")
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        output_name = descriptor.get("filename") or f"{job_id}.{self.config.video_extension}"
        output_path = self.output_dir / output_name
        output_path.write_bytes(data)
        return output_path

    @staticmethod
    def _encode_multipart(fields: Dict[str, str], files: Dict[str, tuple]) -> tuple[bytes, str]:
        boundary = "----ComfyUploadBoundary"
        buffer = io.BytesIO()
        for name, value in fields.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            buffer.write(str(value).encode("utf-8"))
            buffer.write(b"\r\n")
        for name, (filename, content, mime_type) in files.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
            )
            buffer.write(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
            buffer.write(content)
            buffer.write(b"\r\n")
        buffer.write(f"--{boundary}--\r\n".encode("utf-8"))
        return buffer.getvalue(), f"multipart/form-data; boundary={boundary}"
