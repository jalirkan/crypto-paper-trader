"""Env-file loader tests."""

import os
import tempfile
import unittest
from pathlib import Path

from research.envfile import load_env_local


class TestEnvFile(unittest.TestCase):
    def setUp(self):
        for k in ("CPT_TEST_KEY", "CPT_TEST_KEEP"):
            os.environ.pop(k, None)

    def test_loads_and_skips_placeholders_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env.local"
            p.write_text(
                "# comment\n"
                "CPT_TEST_KEY=sk-test-123\n"
                "CPT_TEST_PLACEHOLDER=PASTE_YOUR_KEY_HERE\n"
                'CPT_TEST_QUOTED="quoted-value"\n'
                "malformed line\n",
                encoding="utf-8",
            )
            load_env_local(p)
            self.assertEqual(os.environ.get("CPT_TEST_KEY"), "sk-test-123")
            self.assertIsNone(os.environ.get("CPT_TEST_PLACEHOLDER"))
            self.assertEqual(os.environ.get("CPT_TEST_QUOTED"), "quoted-value")

    def test_real_env_wins(self):
        os.environ["CPT_TEST_KEEP"] = "original"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env.local"
            p.write_text("CPT_TEST_KEEP=overridden\n", encoding="utf-8")
            load_env_local(p)
            self.assertEqual(os.environ["CPT_TEST_KEEP"], "original")

    def test_missing_file_is_fine(self):
        load_env_local("/nonexistent/.env.local")  # no raise


if __name__ == "__main__":
    unittest.main()
