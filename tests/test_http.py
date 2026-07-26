"""Offline tests for the HTTP client's redirect handling (mocked urllib)."""

import unittest
import urllib.error
from unittest import mock

from collectors.http import HttpError, get_bytes


def _http_error(url: str, code: int, location: str | None = None):
    headers = {"Location": location} if location else {}
    return urllib.error.HTTPError(url, code, "err", headers, None)


def _ok_response(body: bytes):
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


class TestRedirects(unittest.TestCase):
    @mock.patch("collectors.http.urllib.request.urlopen")
    def test_follows_308(self, mock_open):
        mock_open.side_effect = [
            _http_error("https://a.example/feed/", 308, "https://a.example/feed"),
            _ok_response(b"<rss/>"),
        ]
        out = get_bytes("https://a.example/feed/")
        self.assertEqual(out, b"<rss/>")
        # Second request went to the redirect target.
        followed = mock_open.call_args_list[1][0][0].full_url
        self.assertEqual(followed, "https://a.example/feed")

    @mock.patch("collectors.http.urllib.request.urlopen")
    def test_relative_location(self, mock_open):
        mock_open.side_effect = [
            _http_error("https://a.example/old", 301, "/new"),
            _ok_response(b"ok"),
        ]
        get_bytes("https://a.example/old")
        followed = mock_open.call_args_list[1][0][0].full_url
        self.assertEqual(followed, "https://a.example/new")

    @mock.patch("collectors.http.urllib.request.urlopen")
    def test_redirect_loop_raises(self, mock_open):
        mock_open.side_effect = lambda *a, **k: (_ for _ in ()).throw(
            _http_error("https://a.example/x", 308, "https://a.example/x")
        )
        with self.assertRaises(HttpError):
            get_bytes("https://a.example/x")

    @mock.patch("collectors.http.urllib.request.urlopen")
    def test_non_retryable_4xx_raises_immediately(self, mock_open):
        mock_open.side_effect = [_http_error("https://a.example/gone", 451)]
        with self.assertRaises(HttpError) as ctx:
            get_bytes("https://a.example/gone")
        self.assertEqual(ctx.exception.status, 451)
        self.assertEqual(mock_open.call_count, 1)  # no pointless retries


if __name__ == "__main__":
    unittest.main()
