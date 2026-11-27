"""Cross-engine regressions discovered during source review."""
import json
import unittest
from .memory import Memory
from .context import build
from .curriculum import plan
from . import resources, drafting, proofreading, search, test_adapters, test_audio, test_resources
from .transport import EngineError

class CompatibilityTests(unittest.TestCase):
    def test_nested_course_resources_and_draft_context(self):
        m=Memory(":memory:")
        self.addCleanup(m.close)
        for scope,kind,key in [("shared","standard","classroom"),("teacher-a","course","demo"),("teacher-a","course","demo.extra"),("teacher-a","decision","demo.extra.decision")]:
            m.put(scope,kind,key,"Fixture","Synthetic content",status="approved",expected_revision=0)
        for key,course in [("base","demo"),("nested","demo.extra")]:
            d=test_resources.fixture(key)
            d["course_key"]=course
            resources.register(m,"teacher-a",d,expected_revision=0,status="approved")
        ctx=build(m,"teacher-a",required_standards=["classroom"],course_key="demo")
        self.assertEqual([r["key"] for r in ctx["included"]],["classroom","demo","demo.res.base"])
        rows=resources.candidates(m,"teacher-a",allowed_licenses=["CC0-1.0"],course_key="demo")
        self.assertEqual(search.lexical("bedroom",rows)["matches"][0]["resource"]["resource_id"],"base")
        t=test_adapters.AdapterTests("test_bounds")
        t.setUp()
        try:
            t.respond({"done":True,"message":{"content":json.dumps({"title":"Demo","rationale":"Practice","markdown":"# Lesson"})}})
            draft=drafting.draft("Prepare course",ctx["context"],model="local:test",port=t.port)
            self.assertFalse(draft["publication_allowed"])
            sent=json.loads(t.server.request_data[1])
            self.assertEqual(json.loads(sent["messages"][1]["content"])["context"],ctx["context"])
        finally: t.doCleanups()

    def test_cycle_cannot_be_bypassed_by_mastery(self):
        units=[{"id":"a","title":"A","lessons":1,"prerequisites":["b"]},
               {"id":"b","title":"B","lessons":1,"prerequisites":["a"]}]
        with self.assertRaises(ValueError):
            plan("demo",units,lesson_minutes=40,max_lessons=2,mastered=["a","b"])

    def test_ambiguous_resource_id(self):
        m=Memory(":memory:")
        self.addCleanup(m.close)
        with self.assertRaises(ValueError):
            resources.register(m,"shared",test_resources.fixture("x.res.y"),expected_revision=0)

    def test_duplicate_json_keys(self):
        t=test_adapters.AdapterTests("test_bounds")
        t.setUp()
        try:
            t.server.payload=b'{"matches":[],"matches":[]}'
            with self.assertRaises(EngineError):
                proofreading.check("Test",port=t.port)
            t.respond({"done":True,"message":{"content":'{"title":"A","title":"B","rationale":"R","markdown":"M"}'}})
            with self.assertRaises(EngineError):
                drafting.draft("Test","",model="local:test",port=t.port)
        finally: t.doCleanups()

    def test_audio_qa_disagreement_even_with_updated_hash(self):
        t=test_audio.AudioTests("test_valid_review_no_publication")
        t.setUp()
        try:
            report=json.loads((t.root/"qa-report.json").read_text())
            report["tracks"][0]["status"]="failed"
            t.write("qa-report.json",report)
            t.manifest["qa_sha256"]=test_audio.sha(t.root/"qa-report.json")
            t.refresh()
            with self.assertRaises(ValueError): t.inspect()
        finally: t.doCleanups()
