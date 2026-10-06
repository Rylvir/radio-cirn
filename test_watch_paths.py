"""Which recordings the transcriber picks up. No audio, no model."""

import unittest
from pathlib import Path

import watch_transcribe as wt


class ChannelTests(unittest.TestCase):
    def test_both_pircs_sites(self):
        for root in ("cirn", "cirn80"):
            p = Path(f"/home/scribe/trunk-build/{root}/2026/10/6/"
                     "2001-1791304146.715_152037500.0-call_1944.wav")
            with self.subTest(root=root):
                self.assertEqual(wt.channel_of(p), ("cirn", 2001, "PCSO West"))

    def test_untranscribed_talkgroup_is_skipped(self):
        p = Path("/home/scribe/trunk-build/cirn80/2026/10/6/1911-1791304146.7_161875000.0-call_1.wav")
        self.assertIsNone(wt.channel_of(p))

    def test_fire_by_frequency(self):
        p = Path("/home/scribe/trunk-build/fire/2026/10/6/1-1791304146.7_151325000.0-call_9.wav")
        self.assertEqual(wt.channel_of(p), ("fire", 151325, "NEU West"))


if __name__ == "__main__":
    unittest.main()
