import logging
import os
import threading
from typing import Optional

import requests

from .logging_config import LogEntry


class ExternalLogForwardHandler(logging.Handler):
    """将日志记录通过HTTP转发到主应用的日志接收端点"""

    def __init__(
        self,
        endpoint: str,
        buffer_name: str = "task_crawl_sources",
        timeout: float = 2.0,
        token: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.endpoint = endpoint.rstrip("/")
        self.buffer_name = buffer_name
        self.timeout = timeout
        self.token = token
        self.session = requests.Session()
        self.lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            entry = LogEntry.from_record(record).to_dict()

            payload = {
                "buffer_name": self.buffer_name,
                "entries": [entry],
            }

            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            with self.lock:
                self.session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
        except Exception:
            self.handleError(record)


def build_forward_handler_from_env() -> Optional[ExternalLogForwardHandler]:
    """根据环境变量配置日志转发处理器"""

    endpoint = os.getenv("LOG_FORWARD_ENDPOINT")
    if not endpoint:
        return None

    buffer_name = os.getenv("LOG_FORWARD_BUFFER", "task_crawl_sources")
    timeout = float(os.getenv("LOG_FORWARD_TIMEOUT", "2.0"))
    token = os.getenv("LOG_FORWARD_TOKEN")

    return ExternalLogForwardHandler(endpoint, buffer_name, timeout, token)
