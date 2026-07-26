"""Validate configured Telegram bot access without printing secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.config import config  # noqa: E402


def main() -> int:
    problems = config.validate_telegram_startup()
    if problems:
        print(json.dumps({"status": "failed", "problems": problems}, ensure_ascii=True))
        return 1
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print(json.dumps({"status": "failed", "problems": ["TELEGRAM_BOT_TOKEN is missing"]}, ensure_ascii=True))
        return 1

    base = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=20) as client:
        me = _json_ok(client.get(f"{base}/getMe"), "getMe")
        webhook = _json_ok(client.get(f"{base}/getWebhookInfo"), "getWebhookInfo")

    bot = me.get("result") or {}
    webhook_info = webhook.get("result") or {}
    print(
        json.dumps(
            {
                "status": "ok",
                "username": bot.get("username"),
                "can_join_groups": bot.get("can_join_groups"),
                "can_read_all_group_messages": bot.get("can_read_all_group_messages"),
                "supports_inline_queries": bot.get("supports_inline_queries"),
                "webhook_url_configured": bool(webhook_info.get("url")),
                "pending_update_count": webhook_info.get("pending_update_count"),
                "last_error_date": webhook_info.get("last_error_date"),
                "telegram_test_mode": config.TELEGRAM_TEST_MODE,
            },
            ensure_ascii=True,
        )
    )
    print("Telegram API smoke passed.")
    return 0


def _json_ok(response: httpx.Response, name: str) -> dict:
    if response.status_code != 200:
        raise RuntimeError(f"{name} returned HTTP {response.status_code}")
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"{name} returned ok=false")
    return body


if __name__ == "__main__":
    raise SystemExit(main())
