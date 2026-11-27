import copy, pathlib,tempfile,unittest,hashlib
from line_cache import *
class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.cache=self.root/"cache";self.out=self.root/"first"
        (self.out/"takes").mkdir(parents=True);(self.out/"cleaned").mkdir()
        self.ref=self.root/"ref.wav";self.ref.write_bytes(b"synthetic ref")
        self.track={"options":{"takes":2},"profile":"school_dialogue","director":{"scene":"school"}}
        self.tasks=[]
        for n in (101,303):
            name=f"line-{n}.wav"
            self.tasks.append({"id":name[:-4],"file":name,"track":"test","index":0,"seed":n,"line":{"text":"Hello.","engine":"pocket","speaker":"A","voice_key":"A","pause_after_ms":300},"voice":{"key":"A","reference_file":str(self.ref),"reference_sha256":file_hash(self.ref)}})
        self.i=identity(self.tasks,self.track,"a"*64)
        self.rows=[]
        for t in self.tasks:
            f=self.out/"takes"/t["file"];f.write_bytes(t["id"].encode())
            self.rows.append({**t,"status":"generated","sha256":file_hash(f),"signal":{"passed":True}})
        self.w=self.rows[1]
        f=self.out/"cleaned"/self.w["file"];f.write_bytes(b"clean")
        q={"passed":True,"lexical":{"errors":0}}
        self.w.update(qa=q,postprocess={"qa":q,"sha256":file_hash(f)})
    def test_cold_restore_and_edit(self):
        self.assertTrue(save(self.cache,self.i,self.rows,self.w,self.out))
        fresh=self.root/"fresh";tasks=copy.deepcopy(self.tasks)
        for t in tasks:t.update(track="another",index=4,id="new-"+t["id"],file="new-"+t["file"])
        self.assertEqual(identity(tasks,self.track,"a"*64),self.i)
        got=restore(self.cache,self.i,tasks,fresh)
        self.assertEqual([r["sha256"] for r in got],[r["sha256"] for r in self.rows])
        self.assertTrue(all(r["cache_hit"] and r["cached_preferred_seed"]==303 for r in got))
        for t in tasks:t["line"]["text"]="Good morning."
        self.assertIsNone(restore(self.cache,identity(tasks,self.track,"a"*64),tasks,fresh))
    def test_corrupt(self):
        save(self.cache,self.i,self.rows,self.w,self.out)
        obj(self.cache,self.w["sha256"]).write_bytes(b"damaged")
        with self.assertRaises(ValueError):restore(self.cache,self.i,self.tasks,self.root/"fresh")
    def test_fingerprint_and_context(self):
        save(self.cache,self.i,self.rows,self.w,self.out)
        self.assertIsNone(restore(self.cache,identity(self.tasks,self.track,"b"*64),self.tasks,self.root/"fresh"))
        self.assertIsNone(restore(self.cache,identity(self.tasks,{**self.track,"director":{"scene":"station"}},"a"*64),self.tasks,self.root/"fresh"))
        self.ref.write_bytes(b"changed")
        with self.assertRaises(ValueError):identity(self.tasks,self.track,"a"*64)
    def test_failed_qa_not_saved(self):
        self.w["postprocess"]["qa"]["lexical"]["errors"]=1
        self.assertFalse(save(self.cache,self.i,self.rows,self.w,self.out))
        self.assertIsNone(restore(self.cache,self.i,self.tasks,self.root/"fresh"))
    def test_retry_group_not_yet_eligible(self):
        extra=copy.deepcopy(self.tasks[0]);extra.update(seed=505,retry=True)
        self.assertIsNone(identity(self.tasks+[extra],self.track,"a"*64))
if __name__=="__main__":unittest.main()
