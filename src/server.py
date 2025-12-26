from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict

from .config_loader import AppConfig
from .qq_client import QQClient
from .qq_events import build_job_from_event
from .task_runner import TaskRunner
from .utils import verify_signature

LOGGER = logging.getLogger("comfy_helper.server")


class BotApplication:
    def __init__(self, config: AppConfig, task_runner: TaskRunner, qq_client: QQClient):
        self.config = config
        self.task_runner = task_runner
        self.qq_client = qq_client

    def process_event(self, event: Dict) -> Dict:
        job = build_job_from_event(event, self.config)
        if not job:
            return {"accepted": False, "reason": "ignored"}
        if self.task_runner.enqueue(job):
            return {"accepted": True, "job_id": job.job_id}
        busy_msg = f"当前还有任务在排队，请稍后再试。"
        self.qq_client.send_group_message(job.group_id, busy_msg)
        return {"accepted": False, "reason": "queue_full"}


def make_handler(app: BotApplication):
    class QQWebhookHandler(BaseHTTPRequestHandler):
        server_version = "ComfyUIHelper/1.0"

        def do_GET(self):
            if self.path.startswith("/health"):
                self._write_json(200, {"ok": True})
            else:
                self._write_json(404, {"error": "not_found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length)
            if not verify_signature(app.config.server.event_secret, body, self.headers.get("X-Signature")):
                LOGGER.warning("Signature mismatch")
                self._write_json(403, {"error": "invalid_signature"})
                return
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                LOGGER.exception("Invalid JSON payload")
                self._write_json(400, {"error": "invalid_json"})
                return
            result = app.process_event(payload)
            self._write_json(200, result)

        def log_message(self, format: str, *args):
            if app.config.server.request_log:
                LOGGER.info("%s - %s", self.address_string(), format % args)

        def _write_json(self, status: int, payload: Dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return QQWebhookHandler


def serve_forever(app: BotApplication) -> None:
    handler = make_handler(app)
    server = ThreadingHTTPServer((app.config.server.host, app.config.server.port), handler)
    LOGGER.info("Server listening on %s:%s", app.config.server.host, app.config.server.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping server...")
    finally:
        server.shutdown()
        server.server_close()
