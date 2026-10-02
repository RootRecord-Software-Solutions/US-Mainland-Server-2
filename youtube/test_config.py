import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from youtube.auth import redact
from youtube.config import load_settings, render_template


class ConfigTests(unittest.TestCase):
    def test_title_uses_hawaii_date(self):
        when = datetime(2026, 10, 1, 12, 0, tzinfo=ZoneInfo("Pacific/Honolulu"))
        settings = load_settings()
        self.assertEqual(
            render_template(settings["title_template"], when),
            "RootRecord Live — 2026-10-01",
        )

    def test_redact_hides_access_tokens(self):
        self.assertNotIn("ya29.", redact("token ya29.abc_def failed"))


if __name__ == "__main__":
    unittest.main()
