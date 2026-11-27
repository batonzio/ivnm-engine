"""Opt-in local preview cache for independently generated Pocket/Chatterbox lines.
Store complete accepted take groups, including bounded repaired takes, after raw+cleaned selected-take QA.
No credentials, publication grants, remote writes, or context-stitching claim.
"""
import hashlib,json,pathlib,re,os,tempfile,time
HEX=re.compile(r"[0-9a-f]{64}\Z")
ROOT=pathlib.Path(__file__).resolve().parents[1]
def require(ok,msg):
    if not ok:raise ValueError(msg)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def digest(b):return hashlib.sha256(b).hexdigest()
def file_hash(p):return digest(p.read_bytes())
def checked(p,h):
    require(HEX.fullmatch(h or "") and p.is_file() and not p.is_symlink(),"Missing/unsafe cached object")
    b=p.read_bytes();require(digest(b)==h,"Cached object hash mismatch");return b
def once(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as f:
        f.write(b);tmp=pathlib.Path(f.name)
    try:
        try:os.link(tmp,p)
        except FileExistsError:require(p.is_file() and not p.is_symlink() and p.read_bytes()==b,"Immutable line cache conflict")
    finally:tmp.unlink()
def group(tasks):
    result={}
    for t in tasks:result.setdefault((t["track"],t["index"]),[]).append(t)
    return result
def identity(tasks,track,fingerprint):
    require(HEX.fullmatch(fingerprint or ""),"Explicit pinned model/runtime/QA fingerprint required")
    if not tasks:return None
    t=tasks[0];line=t["line"];voice=dict(t["voice"])
    if line["engine"] not in ("pocket","chatterbox") or not voice.get("reference_file"):return None
    ref=pathlib.Path(voice.pop("reference_file"))
    require(HEX.fullmatch(voice.get("reference_sha256","")) and file_hash(ref)==voice["reference_sha256"],"Voice reference changed")
    require(all(x["line"]==line and x["voice"]==t["voice"] for x in tasks),"Mixed line tasks")
    initial=[x for x in tasks if not x.get("retry")]
    if len(initial)!=track["options"]["takes"]:return None
    seeds=sorted(x["seed"] for x in initial)
    require(seeds==[101+202*k for k in range(len(initial))],"Unexpected initial seeds")
    validate_seeds(tasks,seeds)
    return {"schema":"ivnm-preview-line-v1","fingerprint":fingerprint,"pipeline":{f:file_hash(ROOT/f) for f in ("production/pipeline.py","production/line_cache.py","md-first/render.py","audio-qa/quality.py","postprocess/mastering.py","speech-director/director.py")},"line":line,"voice":voice,"profile":track.get("profile"),"director":track.get("director"),"options":track["options"],"seeds":seeds,"publication_allowed":False}
def validate_seeds(rows,initial):
    seeds=sorted(r["seed"] for r in rows)
    require(len(initial)<=len(seeds)<=len(initial)+4 and seeds==[101+202*k for k in range(len(seeds))],"Invalid cached retry history")
    require(sorted(r["seed"] for r in rows if not r.get("retry"))==initial,"Initial seeds mismatch")
    return seeds
def record(root,i):return root/"requests"/(digest(canonical(i))+".json")
def obj(root,h):return root/"objects"/(h+".wav")
def passed(t):return t.get("status")=="generated" and t.get("qa",{}).get("passed") is True and t["qa"].get("lexical",{}).get("errors")==0 and t.get("postprocess",{}).get("qa",{}).get("passed") is True and t["postprocess"]["qa"].get("lexical",{}).get("errors")==0
def save(root,i,rows,winner,out):
    if i is None or not passed(winner):return False
    validate_seeds(rows,i["seeds"])
    p=record(root,i)
    if p.exists():
        # An already restored record is immutable, even if fresh diagnostics differ.
        return False
    data=[]
    for r in rows:
        require(r["status"] in ("generated","failed"),"Invalid synthesis status")
        entry={"seed":r["seed"],"status":r["status"]}
        if r.get("retry"):entry["retry"]=True
        for k in ("signal","error","sha256"):
            if k in r:entry[k]=r[k]
        if r["status"]=="generated":
            b=checked(out/"takes"/r["file"],r["sha256"]);once(obj(root,r["sha256"]),b)
        data.append(entry)
    proof={"qa":winner["qa"],"postprocess":winner["postprocess"],"seed":winner["seed"],"status":"generated","raw_sha256":winner["sha256"]}
    clean=checked(out/"cleaned"/winner["file"],winner["postprocess"]["sha256"])
    once(obj(root,winner["postprocess"]["sha256"]),clean)
    once(p,canonical({"identity":i,"rows":data,"winner":proof,"publication_allowed":False}))
    return True
def restore(root,i,tasks,out):
    if i is None:return None
    p=record(root,i)
    if not p.exists():return None
    require(p.is_file() and not p.is_symlink(),"Unsafe cache manifest")
    m=json.loads(p.read_bytes());require(m["identity"]==i and m["publication_allowed"] is False and passed(m["winner"]),"Invalid cache proof")
    rows={x["seed"]:x for x in m["rows"]}
    require(len(rows)==len(m["rows"]),"Duplicate cache seed")
    validate_seeds(m["rows"],i["seeds"])
    w=m["winner"];require(rows[w["seed"]]["sha256"]==w["raw_sha256"],"Winner binding mismatch")
    clean=checked(obj(root,w["postprocess"]["sha256"]),w["postprocess"]["sha256"])
    byseed={t["seed"]:t for t in tasks}
    require(len(byseed)==len(tasks) and set(byseed)<=set(rows),"Unexpected task seed")
    initial=next(t for t in tasks if not t.get("retry"))
    prepared=[]
    for seed in sorted(rows):
        t=byseed.get(seed)
        if t is None:
            serial=(seed-101)//202
            uid=f'{initial["track"]}-{initial["index"]:03d}-r{serial:02d}'
            t={**initial,"id":uid,"file":uid+".wav","seed":seed,"retry":True}
        r=rows[t["seed"]];require(r["status"] in ("generated","failed"),"Invalid cached status")
        b=checked(obj(root,r["sha256"]),r["sha256"]) if r["status"]=="generated" else None
        prepared.append((t,r,b))
    result=[]
    for t,r,b in prepared:
        dest=out/"takes"/t["file"]
        if b is not None:once(dest,b)
        row={**t,**r,"cache_hit":True,"cached_preferred_seed":w["seed"]}
        if t["seed"]==w["seed"]:
            once(out/"cleaned"/t["file"],clean)
            row["cached_postprocess"]=w["postprocess"]
        result.append(row)
    return result
