"""Offline regression tests; synthetic fixtures only."""
import json
from pathlib import Path
import tempfile
import unittest
from .memory import Memory
from .context import build
from .curriculum import plan

class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"memory.sqlite"
        self.m=Memory(self.path)
        self.addCleanup(self.m.close)

    def put(self,scope,kind,key,content="Synthetic content",status="approved",rev=0):
        return self.m.put(scope,kind,key,"Fixture",content,status=status,expected_revision=rev)

    def seed(self):
        self.put("shared","standard","classroom")
        self.put("teacher-a","course","demo")

    def test_persistence_and_isolation(self):
        self.seed()
        self.put("teacher-b","decision","demo.private","OTHER_SCOPE_SENTINEL")
        other=Memory(self.path)
        try:
            data=build(other,"teacher-a",required_standards=["classroom"],course_key="demo")
            self.assertNotIn("OTHER_SCOPE_SENTINEL",data["context"])
            self.assertEqual(len(data["included"]),2)
        finally: other.close()

    def test_revision_conflict_and_retired(self):
        self.seed()
        self.assertEqual(self.put("shared","standard","classroom",rev=1),1)
        self.assertEqual(self.put("shared","standard","classroom",status="retired",rev=1),2)
        with self.assertRaises(ValueError):
            self.put("shared","standard","classroom",rev=1)
        with self.assertRaises(ValueError):
            build(self.m,"teacher-a",required_standards=["classroom"],course_key="demo")

    def test_draft_not_used(self):
        self.seed()
        self.put("teacher-a","decision","demo.draft",status="draft")
        self.assertEqual(len(build(self.m,"teacher-a",required_standards=["classroom"],course_key="demo")["included"]),2)

    def test_ambiguous_standard_blocks(self):
        self.seed()
        self.put("teacher-a","standard","classroom")
        with self.assertRaises(ValueError):
            build(self.m,"teacher-a",required_standards=["classroom"],course_key="demo")

    def test_budget_and_course_filter(self):
        self.seed()
        self.put("teacher-a","resource","demo.large","x"*10000)
        self.put("teacher-a","resource","other.small")
        r=build(self.m,"teacher-a",required_standards=["classroom"],course_key="demo",budget=1000)
        self.assertEqual([x["key"] for x in r["omitted"]],["demo.large"])
        self.assertNotIn("other.small",r["context"])
        self.assertFalse(r["progress_known"])

    def test_progress_reference(self):
        self.seed()
        self.put("teacher-a","progress","demo","Lesson 1 actually taught.")
        r=build(self.m,"teacher-a",required_standards=["classroom"],course_key="demo")
        self.assertTrue(r["progress_known"])
        self.assertEqual(json.loads(r["context"])["records"][-1]["kind"],"progress")

    def test_required_context_never_truncated(self):
        self.seed()
        self.put("shared","standard","classroom","x"*5000,rev=1)
        with self.assertRaises(ValueError):
            build(self.m,"teacher-a",required_standards=["classroom"],course_key="demo",budget=1000)

class CurriculumTests(unittest.TestCase):
    def unit(self,key,prerequisites=(),lessons=2):
        return {"id":key,"title":key,"lessons":lessons,"prerequisites":list(prerequisites)}

    def test_order_review_and_capacity(self):
        r=plan("demo",[self.unit("b",["a"]),self.unit("a")],lesson_minutes=40,max_lessons=5)
        self.assertEqual([x["unit"] for x in r["lessons"]],["a","a","b","b"])
        self.assertEqual(r["lessons"][2]["review_units"],["a"])
        self.assertEqual(r["unused_slots"],1)
        self.assertFalse(r["publication_allowed"])
        self.assertTrue(all(x["status"]=="planned" for x in r["lessons"]))

    def test_unknown_cycle_and_overflow(self):
        for units in ([self.unit("a",["missing"])],[self.unit("a",["b"]),self.unit("b",["a"])],
                      [self.unit("a",lessons=6)],[self.unit("a"),self.unit("a")]):
            with self.assertRaises(ValueError):
                plan("demo",units,lesson_minutes=40,max_lessons=5)

    def test_explicit_prior_mastery(self):
        r=plan("demo",[self.unit("a",["prior"])],lesson_minutes=35,max_lessons=2,mastered=["prior"])
        self.assertEqual(r["lessons"][0]["review_units"],["prior"])
