"""Verify the configured Anthropic key works — without ever printing it.

    python -m research.check_key

Reports only: whether a key is present, its shape (prefix + last 4), and
whether a minimal API call succeeds. Never echoes the secret, so the output
is safe to paste into a chat or an issue.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from .envfile import load_env_local


def masked(key: str) -> str:
    return f"{key[:11]}…{key[-4:]}  ({len(key)} chars)" if len(key) > 20 else "(too short)"


def main() -> int:
    load_env_local()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if not key:
        print("✗ no ANTHROPIC_API_KEY found (.env.local or environment)")
        return 1
    if "PASTE_" in key:
        print("✗ .env.local still has the placeholder — paste your real key over it")
        return 1
    if not key.startswith("sk-ant-"):
        print(f"✗ key doesn't look like an Anthropic key: {masked(key)}")
        return 1

    print(f"key found: {masked(key)}")
    model = os.environ.get("EVENT_MODEL", "claude-haiku-4-5-20251001")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(
            {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
        ).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            json.loads(res.read().decode())
        print(f"✓ key works — {model} responded. Credits available.")
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        kind = json.loads(body).get("error", {}).get("type", "") if body.startswith("{") else ""
        if e.code == 401:
            print("✗ 401 unauthorized — key is invalid, revoked, or expired")
        elif e.code == 400 and "credit" in body.lower():
            print("✗ out of credits — buy more at platform.claude.com → Billing")
        elif e.code == 429:
            print("✗ 429 rate limited — key is valid, just throttled right now")
            return 0
        else:
            print(f"✗ HTTP {e.code} {kind}: {body[:160]}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"✗ could not reach the API: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
