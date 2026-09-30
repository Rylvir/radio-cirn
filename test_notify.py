"""ntfy formatting and send rules. Posts only to a local test server."""

import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path

import incident_classify as ic
import notify


class NotifyRuleTests(unittest.TestCase):
    def _record(self, when, tg, name, system, text, path):
        return ic.record_alert(
            ic.classify(text), talkgroup=tg, talkgroup_name=name,
            system=system, when_iso=when, rel="", text=text, alerts_path=path)

    def test_new_then_same_channel_then_new_channel(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            first = self._record("2026-09-28T12:00:00", 151325, "NEU West", "fire",
                                 "High level TC, Highway 49 at Dry Creek", path)
            again = self._record("2026-09-28T12:02:00", 151325, "NEU West", "fire",
                                 "high level TC, engine 20 on scene, highway 49", path)
            law = self._record("2026-09-28T12:04:00", 2001, "PCSO West", "cirn",
                               "major vehicle accident, 49 and Dry Creek", path)
            self.assertTrue(notify.should_send(first))
            self.assertFalse(notify.should_send(again))
            self.assertTrue(notify.should_send(law))
            self.assertEqual(law["channels"], ["NEU West", "PCSO West"])
            title, body, headers = notify.build(law)
            self.assertEqual(title, "MVA - NEU West + PCSO West (now 3 calls)")
            self.assertEqual(body, "major vehicle accident, 49 and Dry Creek")
            self.assertEqual(headers["Priority"], "4")
            self.assertEqual(len(json.loads(path.read_text())["alerts"]), 1)

    def test_foresthill_every_call_notifies(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            a = self._record("2026-09-28T12:00:00", 2001, "PCSO West", "cirn",
                             "vehicle accident, Foresthill Road", path)
            b = self._record("2026-09-28T12:01:00", 2001, "PCSO West", "cirn",
                             "brush fire reported, Foresthill", path)
            self.assertTrue(notify.should_send(a) and notify.should_send(b))
            self.assertEqual(notify.build(a)[2]["Priority"], "3")

    def test_major_incident_in_foresthill_says_so(self):
        title = notify.build({"label": "Structure Fire", "category": "structure_fire",
                              "place": "foresthill", "channels": ["Placer"]})[0]
        self.assertEqual(title, "Structure Fire - Placer - Foresthill")

    def test_long_transcript_is_trimmed(self):
        body = notify.build({"label": "MVA", "text": "x" * 5000})[1]
        self.assertLessEqual(len(body.encode()), 4096)


class _Capture(http.server.BaseHTTPRequestHandler):
    got = []

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        _Capture.got.append((dict(self.headers), self.rfile.read(n).decode()))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


class NotifySendTests(unittest.TestCase):
    def test_posts_transcript_to_topic(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Capture)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        old = notify.NTFY_URL
        notify.NTFY_URL = f"http://127.0.0.1:{srv.server_port}/topic"
        try:
            notify.send({"category": "shooting", "label": "Shooting",
                         "channels": ["PCSO West"],
                         "text": "Shots fired, 200 block of Main Street — caller hiding"},
                        wait=True)
        finally:
            notify.NTFY_URL = old
            srv.server_close()
        headers, body = _Capture.got[-1]
        self.assertEqual(headers["Title"], "Shooting - PCSO West")
        self.assertEqual(headers["Priority"], "5")
        self.assertIn("caller hiding", body)

    def test_off_without_url(self):
        old = notify.NTFY_URL
        notify.NTFY_URL = ""
        try:
            notify.send({"label": "x"}, wait=True)  # must not raise
        finally:
            notify.NTFY_URL = old


if __name__ == "__main__":
    unittest.main()
