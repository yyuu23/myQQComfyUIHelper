from __future__ import annotations

import io
import json
import logging
import mimetypes
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional

from .config_loader import QQConfig

LOGGER = logging.getLogger("comfy_helper.qq_client")


class QQClient:
    def __init__(self, config: QQConfig, timeout: int = 30):
        self.config = config
        self.base_url = config.api_base.rstrip("/") + "/"
        self.timeout = timeout

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = extra.copy() if extra else {}
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        return headers

    def _request(self, endpoint: str, payload: Optional[Dict] = None, method: str = "POST") -> Dict:
        url = urllib.parse.urljoin(self.base_url, endpoint.lstrip("/"))
        data = None
        headers = self._headers({"Content-Type": "application/json"})
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def send_group_message(self, group_id: int, message: str) -> None:
        payload = {"group_id": group_id, "message": message}
        try:
            self._request("send_group_msg", payload)
        except Exception:
            LOGGER.exception("Failed to send group message")

    def upload_group_file(self, group_id: int, file_path: Path, file_name: Optional[str] = None) -> None:
        file_name = file_name or file_path.name
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        fields = {"group_id": str(group_id)}
        files = {"file": (file_name, file_path.read_bytes(), mime_type)}
        body, content_type = self._encode_multipart(fields, files)
        url = urllib.parse.urljoin(self.base_url, "upload_group_file")
        headers = self._headers({"Content-Type": content_type})
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read()
        except Exception:
            LOGGER.exception("Failed to upload file to group")

    @staticmethod
    def _encode_multipart(fields: Dict[str, str], files: Dict[str, tuple]) -> tuple[bytes, str]:
        boundary = "----ComfyHelperBoundary"
        buffer = io.BytesIO()
        for name, value in fields.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            buffer.write(str(value).encode("utf-8"))
            buffer.write(b"\r\n")
        for name, (filename, file_bytes, content_type) in files.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
            )
            buffer.write(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
            buffer.write(file_bytes)
            buffer.write(b"\r\n")
        buffer.write(f"--{boundary}--\r\n".encode("utf-8"))
        return buffer.getvalue(), f"multipart/form-data; boundary={boundary}"
