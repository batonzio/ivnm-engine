import pathlib,tempfile,unittest,copy,sys
from retry import plan,merge,write,read,sha,ENGINES
class RetryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=pathlib.Path(self.tmp.name);(self.out/"takes").mkdir()
        self.lines=[{"speaker":"A","text":"Hello.","voice_key":"voice-a","engine":"pocket"},{"speaker":"B","text":"Hi.","voice_key":"voice-b","engine":"chatterbox"}]
        self.tasks={e:[] for e in ENGINES}
        for i,l in enumerate(self.lines):
            for k in range(3):
                uid=f"demo-{i:03d}-{k:02d}"
                self.tasks[l["engine"]].append({"id":uid,"track":"demo","index":i,"seed":101+202*k,"line":l,"voice":{"key":l["voice_key"]},"file":uid+".wav"})
        write(self.out/"plan.json",{"tracks":[{"id":"demo","lines":self.lines,"options":{"takes":3}}]})
        write(self.out/"tasks.json",self.tasks)
        for e in ENGINES:
            if self.tasks[e]:
                rows=[]
                for t in self.tasks[e]:
                    p=self.out/"takes"/t["file"];p.write_bytes(t["id"].encode());rows.append({**t,"status":"generated","sha256":sha(p)})
                write(self.out/f"synth-{e}.json",rows)
        self.report()
    def report(self):
        t=read(self.out/"tasks.json")
        write(self.out/"qa-report.json",{"tracks":[{"id":"demo","lines":[{"text":l["text"],"voice_key":l["voice_key"],"selected_seed":None if i==0 else 101,"takes":t[l["engine"]]} for i,l in enumerate(self.lines)]}]})
        write(self.out/"manifest.json",{"qa_sha256":sha(self.out/"qa-report.json"),"status":"blocked","publication_allowed":False})
    def simulate(self):
        pending=read(self.out/"retry-tasks.json")
        write(self.out/"retry-synth-pocket.json",[{**t,"status":"failed"} for t in pending["pocket"]])
        merge(self.out);self.report()
    def test_target_and_limit(self):
        hashes={p:sha(p) for p in (self.out/"takes").glob("*")}
        self.assertEqual(plan(self.out)["new_takes"],2)
        p=read(self.out/"retry-tasks.json")
        self.assertEqual([t["seed"] for t in p["pocket"]],[707,909]);self.assertFalse(p["chatterbox"])
        self.simulate();self.assertEqual(plan(self.out)["new_takes"],2);self.simulate()
        self.assertEqual(plan(self.out)["new_takes"],0);self.assertEqual(plan(self.out)["status"],"blocked")
        self.assertEqual(hashes,{p:sha(p) for p in hashes})
    def test_stale(self):
        plan(self.out);(self.out/"qa-report.json").write_text("{}")
        with self.assertRaises(ValueError):merge(self.out)
    def test_tampered_voice(self):
        plan(self.out);pending=read(self.out/"retry-tasks.json");rows=[{**t,"status":"failed"} for t in pending["pocket"]];rows[0]["voice"]={"key":"other"}
        write(self.out/"retry-synth-pocket.json",rows)
        with self.assertRaises(ValueError):merge(self.out)
if __name__=="__main__":unittest.main()
