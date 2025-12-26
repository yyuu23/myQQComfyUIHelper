from __future__ import annotations

import logging
import mimetypes
import queue
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from .config_loader import ProcessingConfig, QQConfig
from .comfyui_client import ComfyUIClient
from .job_models import VideoJob
from .qq_client import QQClient
from .utils import human_ts

LOGGER = logging.getLogger("comfy_helper.task_runner")


class TaskRunner:
    def __init__(
        self,
        processing: ProcessingConfig,
        qq_config: QQConfig,
        qq_client: QQClient,
        comfy_client: ComfyUIClient,
    ):
        self.processing = processing
        self.qq_config = qq_config
        self.qq_client = qq_client
        self.comfy_client = comfy_client
        self.queue: queue.Queue[Optional[VideoJob]] = queue.Queue(maxsize=processing.queue_size)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def enqueue(self, job: VideoJob) -> bool:
        try:
            self.queue.put_nowait(job)
            LOGGER.info("Enqueued job %s for group %s", job.job_id, job.group_id)
            return True
        except queue.Full:
            LOGGER.warning("Queue is full, rejecting job %s", job.job_id)
            return False

    def shutdown(self) -> None:
        self._stop_event.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=2)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            if job is None:
                break
            try:
                self._process_job(job)
            except Exception:
                LOGGER.exception("Unexpected error when processing job %s", job.job_id)
            finally:
                self.queue.task_done()

    def _process_job(self, job: VideoJob) -> None:
        if self.qq_config.processing_ack:
            ack = f"{job.sender_name}，{self.qq_config.processing_ack}"
            self.qq_client.send_group_message(job.group_id, ack)
        retries = self.processing.max_retries + 1
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                image_path = self._download_image(job)
                try:
                    video_path = self.comfy_client.generate_video(
                        image_path=image_path,
                        prompt=job.prompt,
                        resolution=job.resolution,
                        job_id=job.job_id,
                    )
                finally:
                    image_path.unlink(missing_ok=True)
                self.qq_client.upload_group_file(job.group_id, video_path)
                if self.qq_config.completion_message:
                    msg = f"{job.sender_name}，{self.qq_config.completion_message}"
                    self.qq_client.send_group_message(job.group_id, msg)
                LOGGER.info("Job %s finished successfully", job.job_id)
                return
            except Exception as exc:
                last_error = exc
                LOGGER.exception("Job %s failed on attempt %s/%s", job.job_id, attempt, retries)
                time.sleep(2)
        if self.qq_config.failure_message:
            self.qq_client.send_group_message(job.group_id, self.qq_config.failure_message)
        if last_error:
            raise last_error

    def _download_image(self, job: VideoJob) -> Path:
        url = job.image_url
        request = urllib.request.Request(url)
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "")
        suffix = self._choose_suffix(url, content_type)
        file_name = f"{job.job_id}_{human_ts()}{suffix}"
        path = Path(self.processing.download_dir) / file_name
        path.write_bytes(data)
        LOGGER.debug("Downloaded image for job %s to %s", job.job_id, path)
        return path

    @staticmethod
    def _choose_suffix(url: str, content_type: str) -> str:
        mime_suffix = mimetypes.guess_extension(content_type or "") or ""
        if mime_suffix:
            return mime_suffix
        parsed = urllib.parse.urlparse(url)
        name = Path(parsed.path or "")
        return Path(name).suffix or ".png"
