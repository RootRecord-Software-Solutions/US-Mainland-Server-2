"""Mixer rules that do not need FFmpeg or YouTube."""

import array
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from program import DUCK, FRAME, chime_slot, mix_pcm, slot_key


HAWAII = ZoneInfo("Pacific/Honolulu")


class MixTests(unittest.TestCase):
    def test_duck_adds_under_voice(self):
        voice = array.array("h", [1000, 0])
        bed = array.array("h", [1000, 1000])
        mixed = array.array("h")
        mixed.frombytes(mix_pcm([(voice.tobytes(), 1.0), (bed.tobytes(), DUCK)]))
        self.assertEqual(mixed[0], 1250)
        self.assertEqual(mixed[1], 250)

    def test_silence_when_empty(self):
        self.assertEqual(len(mix_pcm([])), FRAME)

    def test_chime_only_on_the_half_hour(self):
        ten = datetime(2026, 10, 1, 10, 0, tzinfo=HAWAII)
        ten_oh_one = datetime(2026, 10, 1, 10, 1, tzinfo=HAWAII)
        self.assertEqual(chime_slot(ten), "hour-10-00")
        self.assertEqual(chime_slot(ten_oh_one), "")
        self.assertEqual(slot_key(ten), "2026-10-01-hour-10-00")


if __name__ == "__main__":
    unittest.main()
