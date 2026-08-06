"""Tests for the coverage server: ignore mutation and HTTP handling."""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import coverage_ignore
import coverage_server


class ApplyChangeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, ".coverage-ignore.txt")

    def test_add_then_remove(self):
        coverage_server.apply_ignore_change(self.path, "Some Mod", True)
        self.assertTrue(coverage_ignore.load_ignore(self.path).contains_name("Some Mod"))
        coverage_server.apply_ignore_change(self.path, "Some Mod", False)
        self.assertFalse(coverage_ignore.load_ignore(self.path).contains_name("Some Mod"))

    def test_add_idempotent(self):
        coverage_server.apply_ignore_change(self.path, "Dup", True)
        coverage_server.apply_ignore_change(self.path, "Dup", True)
        self.assertEqual(len(coverage_ignore.load_ignore(self.path)), 1)


class ServerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ignore_path = os.path.join(self.dir, ".coverage-ignore.txt")
        self.source = os.path.join(self.dir, "Source.json")
        self.target = os.path.join(self.dir, "Target.json")
        with open(self.source, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"type": "separator", "separatorName": "S", "order": 0},
                    {"type": "mod", "modName": "ClickMe", "separatorName": "S",
                     "order": 1, "id": 42, "general": {"version": "1.0"}},
                ],
                f,
            )
        with open(self.target, "w", encoding="utf-8") as f:
            json.dump([], f)
        handler = coverage_server.make_handler(self.source, self.target, 0.80, self.ignore_path)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _conn(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def test_get_root_returns_html(self):
        c = self._conn()
        c.request("GET", "/")
        resp = c.getresponse()
        body = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        self.assertTrue(body.startswith("<!DOCTYPE html>"))
        self.assertIn("ClickMe", body)
        self.assertIn("/api/ignore", body)  # serve-mode JS present

    def test_unknown_get_404(self):
        c = self._conn()
        c.request("GET", "/nope")
        self.assertEqual(c.getresponse().status, 404)

    def test_post_ignore_mutates_file(self):
        c = self._conn()
        payload = json.dumps({"name": "ClickMe", "ignored": True})
        c.request("POST", "/api/ignore", payload, {"Content-Type": "application/json"})
        resp = c.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertTrue(json.loads(resp.read())["ok"])
        self.assertTrue(coverage_ignore.load_ignore(self.ignore_path).contains_name("ClickMe"))

    def test_post_bad_body_400(self):
        c = self._conn()
        c.request("POST", "/api/ignore", "{not json", {"Content-Type": "application/json"})
        self.assertEqual(c.getresponse().status, 400)

    def test_post_unknown_path_404(self):
        c = self._conn()
        c.request("POST", "/api/other", "{}", {"Content-Type": "application/json"})
        self.assertEqual(c.getresponse().status, 404)

    def test_post_remove_mutates_file(self):
        # First add, then remove over HTTP — the un-ignore path.
        coverage_ignore.add(self.ignore_path, "ClickMe")
        self.assertTrue(coverage_ignore.load_ignore(self.ignore_path).contains_name("ClickMe"))
        c = self._conn()
        payload = json.dumps({"name": "ClickMe", "ignored": False})
        c.request("POST", "/api/ignore", payload, {"Content-Type": "application/json"})
        resp = c.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertTrue(json.loads(resp.read())["ok"])
        self.assertFalse(coverage_ignore.load_ignore(self.ignore_path).contains_name("ClickMe"))


class ServerBaseModeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ignore_path = os.path.join(self.dir, ".coverage-ignore.txt")

        def write(name, items):
            path = os.path.join(self.dir, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f)
            return path

        def m(name, version, mod_id):
            return {"type": "mod", "modName": name, "separatorName": "S",
                    "order": 1, "id": mod_id, "general": {"version": version}}

        s = {"type": "separator", "separatorName": "S", "order": 0}
        self.base = write("Base.json", [s, m("ChangedMod", "1.0", 1),
                                        m("StableMod", "1.0", 2),
                                        m("GoneMod", "1.0", 3)])
        self.source = write("Source.json", [s, m("ChangedMod", "2.0", 1),
                                            m("StableMod", "1.0", 2)])
        self.target = write("Target.json", [s, m("GoneMod", "1.0", 3)])

        handler = coverage_server.make_handler(
            self.source, self.target, 0.80, self.ignore_path, self.base
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_get_renders_base_update_view(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/")
        body = c.getresponse().read().decode("utf-8")
        self.assertIn("Base Update Coverage", body)
        self.assertIn("ChangedMod", body)           # changed in base -> kept
        self.assertNotIn("StableMod", body)          # unchanged -> filtered out
        self.assertIn("Removed in base update", body)
        self.assertIn("GoneMod", body)               # removed in base, target has it


if __name__ == "__main__":
    unittest.main()
