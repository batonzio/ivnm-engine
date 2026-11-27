"""Synthetic reuse and search fixtures; no external services."""
import unittest
from .memory import Memory
from . import resources, search
from . import test_adapters

LICENSES=["CC0-1.0","CC-BY-4.0"]
def fixture(key, title="A room", license="CC0-1.0"):
    return {"schema_version":1,"resource_id":key,"course_key":"demo","kind":"image",
            "title":title,"description":"A bedroom with furniture","tags":["house","bed"],
            "levels":["A2"],"sha256":"a"*64,"license":license,"attribution":"Synthetic fixture",
            "source":"fixture-only"}

class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.m=Memory(":memory:")
        self.addCleanup(self.m.close)

    def add(self,scope,key,**kwargs):
        return resources.register(self.m,scope,fixture(key,**kwargs),expected_revision=0,status="approved")

    def rows(self):
        return resources.candidates(self.m,"teacher-a",allowed_licenses=LICENSES)

    def test_scope_and_license(self):
        self.add("shared","shared")
        self.add("teacher-a","private")
        self.add("teacher-b","other")
        self.add("teacher-a","restricted",license="restricted")
        resources.register(self.m,"teacher-a",fixture("draft"),expected_revision=0)
        self.assertEqual({r["resource_id"] for r in self.rows()},{"shared","private"})

    def test_approval_and_revision(self):
        self.add("teacher-a","private")
        resources.register(self.m,"teacher-a",fixture("private"),expected_revision=1,status="retired")
        self.assertEqual(self.rows(),[])
        with self.assertRaises(ValueError):
            resources.register(self.m,"teacher-a",fixture("private"),expected_revision=1,status="approved")

    def test_filters_and_no_policy(self):
        self.add("shared","shared")
        self.assertEqual(resources.candidates(self.m,"teacher-a",allowed_licenses=LICENSES,level="B1"),[])
        self.assertEqual(resources.candidates(self.m,"teacher-a",allowed_licenses=LICENSES,kind="audio"),[])
        with self.assertRaises(ValueError): resources.candidates(self.m,"teacher-a",allowed_licenses=[])

    def test_same_bytes_keep_attribution(self):
        self.add("shared","one")
        self.add("teacher-a","two",license="CC-BY-4.0")
        group=resources.reusable_bytes(self.rows())["a"*64]
        self.assertEqual(len(group),2)
        self.assertEqual({r["license"] for r in group},set(LICENSES))

    def test_bad_metadata(self):
        d=fixture("bad"); d["sha256"]="invalid"
        with self.assertRaises(ValueError): resources.register(self.m,"shared",d,expected_revision=0)

    def test_lexical_rank(self):
        self.add("shared","one",title="Bedroom")
        self.add("shared","two",title="Garden")
        r=search.lexical("bedroom",self.rows())
        self.assertEqual(r["matches"][0]["resource"]["resource_id"],"one")
        self.assertEqual(search.lexical("unrelated",self.rows())["matches"],[])

    def test_semantic_and_missing(self):
        self.add("shared","one"); self.add("shared","two")
        rows=self.rows()
        q={"model":"local:test","fingerprint":"b"*64,"vector":[1,0]}
        index={rows[0]["metadata_digest"]:{**q,"vector":[1,0.1]},
               rows[1]["metadata_digest"]:{**q,"vector":[0,1]}}
        r=search.semantic(q,rows,index)
        self.assertTrue(r["complete"])
        self.assertEqual(r["matches"][0]["resource"]["resource_id"],rows[0]["resource_id"])
        index[rows[1]["metadata_digest"]]["fingerprint"]="c"*64
        r=search.semantic(q,rows,index)
        self.assertFalse(r["complete"])
        self.assertEqual(len(r["unindexed"]),1)
        index[rows[0]["metadata_digest"]]["vector"]=[0,0]
        with self.assertRaises(ValueError): search.semantic(q,rows,index)

class EmbeddingTests(unittest.TestCase):
    def test_loopback_embedding_contract(self):
        t=test_adapters.AdapterTests("test_bounds")
        t.setUp()
        try:
            t.respond({"embeddings":[[3,4]]})
            r=search.embed("bedroom",model="local:test",fingerprint="b"*64,port=t.port)
            self.assertAlmostEqual(r["vector"][0],.6)
            self.assertEqual(t.server.request_data[0],"/api/embed")
            t.respond({"embeddings":[[0,0]]})
            from .transport import EngineError
            with self.assertRaises(EngineError):
                search.embed("bedroom",model="local:test",fingerprint="b"*64,port=t.port)
        finally: t.doCleanups()
