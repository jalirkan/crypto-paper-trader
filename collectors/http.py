"""Minimal HTTP client on urllib — retries, backoff, JSON helpers. Stdlib only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import USER_AGENT


class HttpError(Exception):
    def __init__(self, url: str, status: int | None, message: str):
        super().__init__(f"{message} [{status}] {url}")
        self.url = url
        self.status = status


def get_bytes(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 20.0,
    retries: int = 3,
) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)

    last_err: Exception | None = None
    hops = 0
    attempt = 0
    while attempt < retries:
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except urllib.error.HTTPError as e:
            # Follow redirects urllib doesn't handle itself (e.g. 308 on py<3.11).
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location")
                if location and hops < 5:
                    url = urllib.parse.urljoin(url, location)
                    hops += 1
                    continue  # redirect hop doesn't consume a retry
                raise HttpError(url, e.code, "redirect loop or missing Location") from e
            # Retry only on rate limits and server errors.
            if e.code == 429 or e.code >= 500:
                last_err = HttpError(url, e.code, "retryable HTTP error")
            else:
                raise HttpError(url, e.code, "HTTP error") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = HttpError(url, None, f"network error: {e}")
        time.sleep(2**attempt)  # 1s, 2s, 4s
        attempt += 1

    assert last_err is not None
    raise last_err


def get_json(url: str, params: dict | None = None, **kwargs):
    return json.loads(get_bytes(url, params, **kwargs).decode("utf-8"))


def get_text(url: str, params: dict | None = None, **kwargs) -> str:
    return get_bytes(url, params, **kwargs).decode("utf-8", errors="replace")
