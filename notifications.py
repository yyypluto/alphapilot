"""Notification helpers (Feishu/Lark).

This module is intentionally dependency-light and uses `requests` which is
already in `requirements.txt`.

Environment variables:
- FEISHU_WEBHOOK: Feishu bot webhook URL.

Design:
- Never raise to crash the Streamlit app.
- Small timeout to avoid blocking UI.
"""

from __future__ import annotations

import os
from typing import Optional

import requests


def get_feishu_webhook() -> Optional[str]:
    return os.getenv("FEISHU_WEBHOOK")


def send_feishu_alert(
    title: str,
    content: str,
    *,
    webhook: Optional[str] = None,
    timeout: float = 6.0,
) -> bool:
    """Send a Feishu bot message.

    Returns True if request was sent successfully (2xx), else False.
    """

    url = webhook or get_feishu_webhook()
    if not url:
        return False

    payload = {
        "msg_type": "text",
        "content": {"text": f"【AlphaPilot 监控报警】\n{title}\n\n{content}"},
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        return 200 <= resp.status_code < 300
    except Exception:
        return False
