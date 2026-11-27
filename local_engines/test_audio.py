"""Synthetic audio contract tests; no synthesis, no real voice or external calls."""
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from .audio import inspect_package, request_key, sha, PASS

class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"audio").mkdir()
        self.audio=self.root/"audio/t1.mp3"
        self.audio.write_bytes(b"synthetic bytes: not actual MP3")
        self.write("qa-report.json",{"publication_allowed":False})
        self.manifest={"schema":1,"demo":False,"status":PASS,"publication_allowed":False,
                       "qa_sha256":sha(self.root/"qa-report.json"),
                       "tracks":[{"id":"t1","lesson":"l1","slide":"s1","file":"audio/t1.mp3","status":PASS,
                                  "seconds":35.0,"sha256":sha(self.audio)}]}
        self.refresh()

    def write(self,name,data):
        (self.root/name).write_text(json.dumps(data),encoding="utf-8")

    def refresh(self):
        self.write("manifest.json",self.manifest)
        self.write("release-review.json",{"manifest_sha256":sha(self.root/"manifest.json"),
                   "listening_approved":True,"reviewer":"fixture","tracks":{"t1":sha(self.audio)}})

    def inspect(self,**kw):
        return inspect_package(self.root,**({"expected_bindings":{"t1":("l1","s1")},
                                              "minimum_seconds":{"t1":30}}|kw))

    def test_valid_review_no_publication(self):
        r=self.inspect()
        self.assertEqual(r["tracks"][0]["sha256"],sha(self.audio))
        self.assertFalse(r["publication_allowed"])

    def test_tampering_rejected(self):
        self.audio.write_bytes(b"changed")
        with self.assertRaises(ValueError): self.inspect()

    def test_stale_review_rejected(self):
        self.manifest["tracks"][0]["seconds"]=36
        self.write("manifest.json",self.manifest)
        with self.assertRaises(ValueError): self.inspect()

    def test_demo_and_unapproved_rejected(self):
        for field,value in (("demo",True),("publication_allowed",True),("status","blocked")):
            original=self.manifest[field]; self.manifest[field]=value; self.refresh()
            with self.assertRaises(ValueError): self.inspect()
            self.manifest[field]=original

    def test_binding_and_duration(self):
        with self.assertRaises(ValueError): self.inspect(expected_bindings={"t1":("l2","s1")})
        with self.assertRaises(ValueError): self.inspect(minimum_seconds={"t1":50})

    def test_qa_checksum(self):
        self.write("qa-report.json",{"publication_allowed":False,"changed":True})
        with self.assertRaises(ValueError): self.inspect()

    def test_symlink(self):
        target=self.root/"replacement"
        target.write_bytes(self.audio.read_bytes())
        self.audio.unlink(); self.audio.symlink_to(target)
        with self.assertRaises(ValueError): self.inspect()

class AudioKeyTests(unittest.TestCase):
    def test_key_reuse_and_invalidation(self):
        track={"status":"ready","id":"t1","lesson":"l1","slide":"s1","options":{"speed":1,"takes":3},
               "lines":[{"engine":"pocket","voice_key":"voice-a","voice_status":"approved","text":"Hello."}]}
        cfg={"runtime_fingerprints":{"pocket":"a"*64},"reference_fingerprints":{"voice-a":"b"*64},
             "processing_fingerprint":"c"*64}
        k=request_key(track,**cfg)
        other=deepcopy(track);other["lesson"]="l2";other["id"]="t2"
        self.assertEqual(k,request_key(other,**cfg))
        other["lines"][0]["text"]="Good morning."
        self.assertNotEqual(k,request_key(other,**cfg))
        self.assertNotEqual(k,request_key(track,**(cfg|{"processing_fingerprint":"d"*64})))
        other["lines"][0]["voice_status"]="candidate"
        with self.assertRaises(ValueError): request_key(other,**cfg)
        with self.assertRaises(ValueError): request_key(track,**(cfg|{"runtime_fingerprints":{}}))
