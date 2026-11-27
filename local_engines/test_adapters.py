"""Synthetic local HTTP contract tests; no real model, internet or personal data."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from . import proofreading, drafting
from .transport import EngineError

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        self.server.request_data = (self.path, self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(self.server.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.server.payload)

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.status = 200
        self.server.payload = b"{}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.shutdown)

    def respond(self, data):
        self.server.payload = json.dumps(data).encode()

    def test_proofreading_contract(self):
        self.respond({"matches": [{"rule":{"id":"TEST_RULE"}, "offset":0, "length":3,
                                   "message":"Review", "replacements":[{"value":"The"}]}]})
        r = proofreading.check("Teh book.", port=self.port)
        self.assertEqual(r["findings"][0]["suggestions"], ["The"])
        self.assertTrue(r["advisory_only"])
        self.assertIsNone(r["grade"])
        self.assertFalse(r["publication_allowed"])
        path, body = self.server.request_data
        self.assertEqual(path, "/v2/check")
        self.assertEqual(parse_qs(body.decode())["language"], ["en-GB"])

    def test_invalid_match_rejected(self):
        self.respond({"matches":[{"offset":-1}]})
        with self.assertRaises(EngineError):
            proofreading.check("Test.", port=self.port)

    def test_no_findings_is_valid(self):
        self.respond({"matches":[]})
        self.assertEqual(proofreading.check("Test.", port=self.port)["findings"], [])

    def test_draft_contract(self):
        self.respond({"done":True, "done_reason":"stop", "message":{"content":json.dumps(
            {"title":"Demo", "rationale":"Practise a form.", "markdown":"# Demo"})}})
        r = drafting.draft("Write a lesson", "Synthetic context", model="local:test", port=self.port)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertFalse(r["publication_allowed"])
        path, body = self.server.request_data
        request = json.loads(body)
        self.assertEqual(path, "/api/chat")
        self.assertFalse(request["stream"])
        self.assertEqual(request["format"], drafting.DRAFT_SCHEMA)

    def test_incomplete_and_invalid_draft_rejected(self):
        for raw in [{"done":False}, {"done":True,"done_reason":"length"},
                    {"done":True,"message":{"content":"not JSON"}},
                    {"done":True,"message":{"content":"{}"}}]:
            self.respond(raw)
            with self.assertRaises(EngineError):
                drafting.draft("Test", "", model="local:test", port=self.port)

    def test_cloud_model_rejected(self):
        with self.assertRaises(ValueError):
            drafting.draft("Test", "", model="example:cloud", port=self.port)

    def test_http_redirect_and_invalid_json(self):
        self.server.status = 302
        with self.assertRaises(EngineError):
            proofreading.check("Test", port=self.port)
        self.server.status = 200
        self.server.payload = b"broken"
        with self.assertRaises(EngineError):
            proofreading.check("Test", port=self.port)

    def test_bounds(self):
        for text in ("", "x"*20001):
            with self.assertRaises(ValueError):
                proofreading.check(text, port=self.port)
        with self.assertRaises(ValueError):
            proofreading.check("Test", port=0)

if __name__ == "__main__":
    unittest.main()
