"""Tests for the funding-rate mirror parser — synthetic zips, no network."""

import io
import unittest
import zipfile
from datetime import date

from collectors.sources.binance_vision import (
    fetch_funding_month,
    month_url,
    months_between,
    parse_funding_csv,
)


def make_zip(csv_text: str, name: str = "BTCUSDT-fundingRate-2024-01.csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, csv_text)
    return buf.getvalue()


class TestParse(unittest.TestCase):
    def test_parses_with_header(self):
        raw = make_zip(
            "calc_time,funding_interval_hours,last_funding_rate\n"
            "1704067200000,8,0.00010000\n"
            "1704096000000,8,-0.00005000\n"
        )
        rows = parse_funding_csv(raw, "BTCUSDT")
        self.assertEqual(len(rows), 2)  # header skipped, not counted
        self.assertEqual(rows[0], ("BTCUSDT", 1704067200000, 0.0001, "binance-vision"))
        self.assertEqual(rows[1][2], -0.00005)  # negatives preserved

    def test_parses_without_header(self):
        raw = make_zip("1704067200000,8,0.0001\n")
        self.assertEqual(len(parse_funding_csv(raw, "ETHUSDT")), 1)

    def test_microsecond_timestamps_normalised(self):
        raw = make_zip("1704067200000000,8,0.0001\n")  # microseconds
        rows = parse_funding_csv(raw, "BTCUSDT")
        self.assertEqual(rows[0][1], 1704067200000)  # → milliseconds

    def test_malformed_lines_skipped_not_fatal(self):
        raw = make_zip(
            "1704067200000,8,0.0001\n"
            "garbage,row,here\n"
            ",,\n"
            "short,row\n"
            "1704096000000,8,0.0002\n"
        )
        rows = parse_funding_csv(raw, "BTCUSDT")
        self.assertEqual(len(rows), 2)  # the two good rows survive

    def test_schema_matches_funding_table(self):
        """Rows must be insertable by db.upsert_funding: (symbol, ts, rate, source)."""
        import sqlite3

        from collectors import db as cdb

        conn = sqlite3.connect(":memory:")
        conn.executescript(cdb.SCHEMA)
        rows = parse_funding_csv(make_zip("1704067200000,8,0.0001\n"), "BTCUSDT")
        cdb.upsert_funding(conn, rows)
        stored = conn.execute("SELECT symbol, ts, rate, source FROM funding").fetchone()
        self.assertEqual(stored, ("BTCUSDT", 1704067200000, 0.0001, "binance-vision"))


class TestUrlAndMonths(unittest.TestCase):
    def test_url_shape(self):
        self.assertEqual(
            month_url("BTCUSDT", 2024, 1),
            "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
            "BTCUSDT/BTCUSDT-fundingRate-2024-01.zip",
        )

    def test_months_between_spans_year_boundary(self):
        got = months_between(date(2023, 11, 15), date(2024, 2, 3))
        self.assertEqual(got, [(2023, 11), (2023, 12), (2024, 1), (2024, 2)])

    def test_single_month(self):
        self.assertEqual(months_between(date(2024, 5, 1), date(2024, 5, 28)), [(2024, 5)])

    def test_three_years_is_37_requests_per_symbol(self):
        n = len(months_between(date(2023, 7, 1), date(2026, 7, 31)))
        self.assertEqual(n, 37)  # vs thousands of paginated API calls


class TestMissingMonth(unittest.TestCase):
    def test_404_returns_empty_not_raise(self):
        from unittest import mock

        from collectors.http import HttpError

        with mock.patch(
            "collectors.sources.binance_vision.get_bytes",
            side_effect=HttpError("u", 404, "not found"),
        ):
            self.assertEqual(fetch_funding_month("BTCUSDT", 2019, 1), [])

    def test_other_errors_propagate(self):
        from unittest import mock

        from collectors.http import HttpError

        with mock.patch(
            "collectors.sources.binance_vision.get_bytes",
            side_effect=HttpError("u", 500, "server error"),
        ):
            with self.assertRaises(HttpError):
                fetch_funding_month("BTCUSDT", 2024, 1)


if __name__ == "__main__":
    unittest.main()
