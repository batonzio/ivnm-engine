"""Reuse untouched takes from the director audition; replace only Lucy."""
import json,pathlib,hashlib,shutil
out=pathlib.Path("out");prior=pathlib.Path("prior")
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2))
plan=read(out/"plan.json");old=read(prior/"plan.json")
tasks=read(out/"tasks.json");old_tasks=read(prior/"tasks.json")
assert len(plan["tracks"])==len(old["tracks"])==1
a,b=plan["tracks"][0]["lines"],old["tracks"][0]["lines"]
assert len(a)==len(b)==5
changed=[i for i,(x,y) in enumerate(zip(a,b)) if x["voice_key"]!=y["voice_key"]]
assert changed==[1,3],changed
for i in range(5):
    for key in ("text","speaker","engine","pause_after_ms","synthesis_text","qa_text","emotion","emphasis"):
        assert a[i].get(key)==b[i].get(key),(i,key)
assert all(a[i]["voice_key"]=="UK-T-F-02-pocket" for i in changed)
(out/"takes").mkdir(exist_ok=True)
for e in ("chatterbox","kitten"):
    records=read(prior/f"synth-{e}.json")
    new={t["id"]:t for t in tasks[e]}
    assert set(new)=={r["id"] for r in records}
    for r in records:
        t=new[r["id"]]
        assert r["seed"]==t["seed"] and r["line"]==t["line"]
        assert r["voice"].get("reference_sha256")==t["voice"].get("reference_sha256")
        r["voice"]=t["voice"]
        if r["status"]=="generated":
            p=prior/"takes"/r["file"]
            assert hashlib.sha256(p.read_bytes()).hexdigest()==r["sha256"]
            shutil.copyfile(p,out/"takes"/r["file"])
    write(out/f"synth-{e}.json",records)
print("Only Lucy's six takes will be synthesized; all other source recordings reused.")
