"""Real artifact cache seed and cold restore. Fingerprint deliberately scoped
to the original immutable audition artifact, not claimed as current model identity.
"""
import argparse,pathlib,hashlib,json,sys,time,copy
from line_cache import identity,save,restore,group,file_hash,require,passed
import pipeline

def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2))
def seed(prior,refs,bundle,artifact):
    start=time.perf_counter()
    manifest=read(prior/"manifest.json")
    require(manifest["demo"] is True and manifest["publication_allowed"] is False and manifest["status"]=="technical_pass_pending_listening" and manifest["qa_sha256"]==file_hash(prior/"qa-report.json"),"Not a technical preview")
    plan=read(prior/"plan.json");qa=read(prior/"qa-report.json");tasks=read(prior/"tasks.json")
    fingerprint=hashlib.sha256(("legacy-audition-preview-only:"+artifact+":"+manifest["qa_sha256"]).encode()).hexdigest()
    tracks={t["id"]:t for t in plan["tracks"]};reports={t["id"]:t for t in qa["tracks"]}
    selected=[];filtered={e:[] for e in tasks}
    for engine,items in tasks.items():
        for (tid,idx),rows in group(items).items():
            if engine not in ("pocket","chatterbox") or not rows[0]["voice"].get("reference_file"):continue
            q=reports[tid]["lines"][idx]
            takes=copy.deepcopy(q["takes"]);winner=next(t for t in takes if t["seed"]==q["selected_seed"])
            require(passed(winner),"Selected take not accepted")
            byid={t["id"]:t for t in rows}
            require(set(byid)=={t["id"] for t in takes},"Missing take evidence")
            for t in takes:
                expected=byid[t["id"]]
                require(all(t[k]==v for k,v in expected.items()),"Task evidence mismatch")
                ref=refs/"refs"/pathlib.Path(t["voice"]["reference_file"]).name
                require(file_hash(ref)==t["voice"]["reference_sha256"],"Reference changed")
                t["voice"]["reference_file"]=str(ref)
                expected["voice"]["reference_file"]=str(ref)
            i=identity(rows,tracks[tid],fingerprint)
            require(i is not None and save(bundle/"cache",i,takes,winner,prior),"Cache seed refused")
            filtered[engine].extend(rows)
            selected.append({"track":tid,"index":idx,"engine":engine,"seed":winner["seed"],"raw":winner["sha256"],"clean":winner["postprocess"]["sha256"]})
    require(len(selected)>=2,"Not enough real eligible lines")
    bundle.mkdir(exist_ok=True)
    write(bundle/"plan.json",plan);write(bundle/"tasks.json",filtered);write(bundle/"manifest.json",{"demo":True,"publication_allowed":False})
    write(bundle/"seed-report.json",{"artifact":artifact,"fingerprint":fingerprint,"selected":selected,"wall_seconds":time.perf_counter()-start,"publication_allowed":False})
    print(json.dumps(read(bundle/"seed-report.json")))
def replay(bundle,refs,fresh):
    start=time.perf_counter()
    evidence=read(bundle/"seed-report.json");fp=evidence["fingerprint"]
    tasks=read(bundle/"tasks.json");plan=read(bundle/"plan.json")
    tracks={t["id"]:t for t in plan["tracks"]}
    fresh.mkdir(parents=True)
    for rows in tasks.values():
        for t in rows:
            ref=refs/"refs"/pathlib.Path(t["voice"]["reference_file"]).name
            require(file_hash(ref)==t["voice"]["reference_sha256"],"Reference mismatch")
            t["voice"]["reference_file"]=str(ref)
    write(fresh/"plan.json",plan);write(fresh/"tasks.json",tasks);write(fresh/"manifest.json",{"demo":True,"publication_allowed":False})
    timings=[]
    from types import SimpleNamespace
    from unittest.mock import patch
    for engine,rows in tasks.items():
        if not rows:continue
        with patch.object(pipeline,"load_module",side_effect=AssertionError("TTS renderer must not load")):
            pipeline.synth(SimpleNamespace(out=fresh,engine=engine,retry=False,line_cache=bundle/"cache",cache_fingerprint=fp))
        t=read(fresh/f"synth-timing-{engine}.json");require(t["synthesis_calls"]==0 and t["model_load_seconds"]==0,"Warm path synthesized")
        timings.append(t)
    for e in evidence["selected"]:
        rows=read(fresh/f'synth-{e["engine"]}.json')
        w=next(t for t in rows if t["track"]==e["track"] and t["index"]==e["index"] and t["seed"]==e["seed"])
        require(file_hash(fresh/"takes"/w["file"])==e["raw"] and file_hash(fresh/"cleaned"/w["file"])==e["clean"],"Real replay hash mismatch")
    # Change one utterance only; all other keys must still hit.
    all_groups=[(group(rows),engine) for engine,rows in tasks.items() if rows]
    target=next(iter(all_groups[0][0]))
    misses=0;hits=0
    for groups,engine in all_groups:
        for (tid,idx),rows in groups.items():
            changed=copy.deepcopy(rows)
            if (tid,idx)==target:
                for t in changed:t["line"]["text"]+=" Again.";t["line"]["qa_text"]=t["line"]["text"];t["line"]["synthesis_text"]=t["line"]["text"]
            i=identity(changed,tracks[tid],fp)
            if restore(bundle/"cache",i,changed,fresh/"edit-check") is None:misses+=1
            else:hits+=1
    require(misses==1 and hits==len(evidence["selected"])-1,"Unexpected invalidation")
    report={"real_cached_lines":len(evidence["selected"]),"raw_and_clean_hashes_verified":True,"changed_line_cache_misses":misses,"unchanged_line_cache_hits":hits,"timings":timings,"wall_seconds":time.perf_counter()-start,"publication_allowed":False,"scope":"legacy artifact replay only; edited line inference not performed"}
    write(fresh/"replay-report.json",report);print(json.dumps(report))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["seed","replay"]);p.add_argument("--prior",type=pathlib.Path);p.add_argument("--refs",type=pathlib.Path,required=True);p.add_argument("--bundle",type=pathlib.Path,required=True);p.add_argument("--artifact");p.add_argument("--fresh",type=pathlib.Path);a=p.parse_args()
    if a.mode=="seed":seed(a.prior,a.refs,a.bundle,a.artifact)
    else:replay(a.bundle,a.refs,a.fresh)
