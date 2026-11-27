"""A/B one actor with the identical reference; preserve all other source takes."""
import argparse,json,pathlib,hashlib,shutil
out=pathlib.Path("out");prior=pathlib.Path("prior");review=pathlib.Path("review")
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def registry():
    p=pathlib.Path("preferred-voices.json");r=read(p)
    entry=next(x for x in r["voices"] if x["key"]=="UK-T-F-02-pocket")
    candidates=read(review/"candidates.json")
    row=next(x for x in candidates if x["id"]=="UK-T-F-02")
    assert any(e["engine"]=="chatterbox" and e["eligible"] for e in row["engines"])
    assert sha(review/entry["reference_file"])==entry["reference_sha256"]==row["reference_sha256"]
    r["voices"].append({**entry,"key":"UK-T-F-02-chatterbox","engine":"chatterbox","selection_status":"experimental_same_reference_engine_comparison","reviewed":False})
    write(p,r)
def stage():
    plan=read(out/"plan.json");old=read(prior/"plan.json")
    a,b=plan["tracks"][0]["lines"],old["tracks"][0]["lines"]
    assert len(a)==len(b)==5
    changed=[i for i,(x,y) in enumerate(zip(a,b)) if x["voice_key"]!=y["voice_key"]]
    assert changed==[1,3]
    for i in range(5):
        for k in ("text","speaker","pause_after_ms","synthesis_text","qa_text","emotion","emphasis"):
            assert a[i].get(k)==b[i].get(k),(i,k)
    tasks=read(out/"tasks.json")
    assert len(tasks["chatterbox"])==12 and len(tasks["kitten"])==3 and not tasks["pocket"]
    old_pocket=read(prior/"synth-pocket.json")
    for t in tasks["chatterbox"]:
        if t["index"] in changed:
            prior_t=next(r for r in old_pocket if r["id"]==t["id"])
            assert t["voice"]["reference_sha256"]==prior_t["voice"]["reference_sha256"]
    (out/"takes").mkdir(exist_ok=True)
    for e in ("chatterbox","kitten"):
        keep={t["id"]:t for t in tasks[e] if t["index"] not in changed}
        records=read(prior/f"synth-{e}.json")
        assert set(keep)=={r["id"] for r in records}
        for r in records:
            t=keep[r["id"]]
            assert t["line"]==r["line"] and t["seed"]==r["seed"]
            assert t["voice"].get("reference_sha256")==r["voice"].get("reference_sha256")
            r["voice"]=t["voice"]
            if r["status"]=="generated":
                src=prior/"takes"/r["file"]
                assert sha(src)==r["sha256"]
                shutil.copyfile(src,out/"takes"/r["file"])
        write(out/f"reuse-{e}.json",records)
    write(out/"full-tasks.json",tasks)
    write(out/"tasks.json",{"chatterbox":[t for t in tasks["chatterbox"] if t["index"] in changed],"kitten":[],"pocket":[]})
def merge():
    new=read(out/"synth-chatterbox.json");old=read(out/"reuse-chatterbox.json")
    assert len(new)==6 and len(old)==6
    assert not {x["id"] for x in new}&{x["id"] for x in old}
    write(out/"synth-chatterbox.json",old+new)
    shutil.copyfile(out/"reuse-kitten.json",out/"synth-kitten.json")
    shutil.copyfile(out/"full-tasks.json",out/"tasks.json")
def package():
    target=out/"comparison";target.mkdir(exist_ok=True)
    import sys
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"postprocess"))
    from mastering import ff,measure
    oldqa=read(prior/"qa-report.json")["tracks"][0];newqa=read(out/"qa-report.json")["tracks"][0]
    assert newqa["status"]=="technical_pass_pending_listening"
    names=[]
    for label,src,qa in (("A-pocket",prior,oldqa),("B-chatterbox",out,newqa)):
        path=src/"audio"/(qa["id"]+".wav")
        m=measure(path)
        names.append((label,path,m))
    level=min(x[2]["input_i"] for x in names)
    for label,path,m in names:
        gain=min(level-m["input_i"],-2.5-m["input_tp"])
        ff("-i",path,"-af",f"volume={gain}dB","-c:a","libmp3lame","-b:a","128k",target/(label+".mp3"))
    for label,src,qa in (("A-pocket",prior,oldqa),("B-chatterbox",out,newqa)):
        for i in (1,3):
            l=qa["lines"][i]
            c=next(t for t in l["takes"] if t["seed"]==l["selected_seed"])
            raw=src/"takes"/c["file"];assert sha(raw)==c["sha256"]
            m=measure(raw)
            gain=min(-22-m["input_i"],-3-m["input_tp"]) if m["input_i"] is not None else 0
            ff("-i",raw,"-af",f"volume={gain}dB","-c:a","pcm_s24le",target/f"{label}-line-{i+1}-raw.wav")
    write(target/"comparison.json",{"status":"listening_required","reference":"identical UK-T-F-02 source for both engines","publication_allowed":False,"full_dialogue_loudness":{label:measure(target/(label+".mp3")) for label,_,_ in names}})
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("mode",choices=["registry","stage","merge","package"]);globals()[a.parse_args().mode]()
