from __future__ import annotations

import argparse
import logging
import sys

from .comfyui_client import ComfyUIClient
from .config_loader import load_config
from .qq_client import QQClient
from .server import BotApplication, serve_forever
from .task_runner import TaskRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQ to ComfyUI helper service")
    parser.add_argument(
        "-c", "--config", default="config.json", help="Path to config file (default: %(default)s)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    logging.basicConfig(
        level=logging.DEBUG if config.processing.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    qq_client = QQClient(config.qq)
    comfy_client = ComfyUIClient(config.comfyui, config.processing.output_dir)
    task_runner = TaskRunner(config.processing, config.qq, qq_client, comfy_client)
    app = BotApplication(config, task_runner, qq_client)
    try:
        serve_forever(app)
    finally:
        task_runner.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
