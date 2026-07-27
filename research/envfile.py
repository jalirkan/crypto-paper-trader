"""Minimal .env.local loader so Python CLIs share the Next.js secrets file.

Only fills variables that aren't already set — real environment always wins.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env_local(path: str | Path | None = None) -> None:
    p = Path(path) if path else ROOT / ".env.local"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and "PASTE_" not in value:
            os.environ.setdefault(key, value)
