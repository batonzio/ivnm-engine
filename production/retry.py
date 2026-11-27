"""Bounded repair of failed lines only. Never rewrite prior takes or change voices."""
import argparse,hashlib,json,pathlib,re,copy
ENGINES=("pocket","chatterbox","kitten")
MAX_EXTRA_PER_LINE=4
BATCH=2
def read(p):return json.loads(p.read_text())
def write(p,x):
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False));tmp.replace(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def group(tasks):
    result={}
    ids=set()
    for e in ENGINES:
        for t in tasks[e]:
            if t["id"] in ids or t["line"]["engine"]!=e or t["file"]!=t["id"]+".wav" or not re.fullmatch(r"[A-Za-z0-9_-]+",t["id"]):raise ValueError("Invalid/duplicate task")
            ids.add(t["id"]);result.setdefault((t["track"],t["index"]),[]).append(t)
    return result
def verify_report(out):
    m=read(out/"manifest.json")
    if m.get("qa_sha256")!=sha(out/"qa-report.json"):raise ValueError("Stale or missing QA report")
    if m.get("publication_allowed") is not False:raise ValueError("Unexpected publication state")
    return m,read(out/"qa-report.json")
def plan(out):
    manifest,report=verify_report(out)
    base=read(out/"tasks.json");byline=group(base);original=read(out/"plan.json")
    pending={e:[] for e in ENGINES};blocked=[];seen=set()
    source={t["id"]:t for t in original["tracks"]}
    if set(source)!={t["id"] for t in report["tracks"]}:raise ValueError("Report track mismatch")
    for tr in report["tracks"]:
        spec=source[tr["id"]]
        if len(tr["lines"])!=len(spec["lines"]):raise ValueError("Report line mismatch")
        for i,line in enumerate(tr["lines"]):
            key=(tr["id"],i);seen.add(key);old=byline[key];expected=spec["lines"][i]
            if line["voice_key"]!=expected["voice_key"] or line["text"]!=expected["text"]:raise ValueError("Report line mismatch")
            if any(x["line"]!=expected or x["voice"]!=old[0]["voice"] for x in old):raise ValueError("Inconsistent existing voice or script")
            if {x["id"] for x in line["takes"]}!={x["id"] for x in old}:raise ValueError("Incomplete QA records")
            if line["selected_seed"] is not None:continue
            initial=spec["options"]["takes"];extra=len(old)-initial
            if extra<0 or extra>MAX_EXTRA_PER_LINE:raise ValueError("Invalid retry history")
            count=min(BATCH,MAX_EXTRA_PER_LINE-extra)
            if count==0:
                blocked.append({"track":tr["id"],"index":i,"reason":"retry_budget_exhausted"});continue
            for k in range(count):
                serial=len(old)+k
                t=copy.deepcopy(old[0]);uid=f'{tr["id"]}-{i:03d}-r{serial:02d}'
                t.update(id=uid,file=uid+".wav",seed=101+202*serial,retry=True)
                if t["seed"] in {x["seed"] for x in old}:raise ValueError("Retry seed collision")
                if (out/"takes"/t["file"]).exists():raise ValueError("Retry would overwrite existing audio")
                pending[t["line"]["engine"]].append(t)
    if seen!=set(byline):raise ValueError("Unmatched tasks")
    group(pending)
    write(out/"retry-tasks.json",pending)
    state={"status":"ready" if any(pending.values()) else ("blocked" if manifest["status"]=="blocked" else "complete"),"base_tasks_sha256":sha(out/"tasks.json"),"qa_sha256":sha(out/"qa-report.json"),"tasks_sha256":sha(out/"retry-tasks.json"),"new_takes":sum(map(len,pending.values())),"exhausted":blocked,"max_extra_per_line":MAX_EXTRA_PER_LINE}
    write(out/"retry-plan.json",state);print(json.dumps(state));return state
def merge(out):
    state=read(out/"retry-plan.json")
    if state["status"]!="ready" or any(state[k]!=sha(out/f) for k,f in (("base_tasks_sha256","tasks.json"),("qa_sha256","qa-report.json"),("tasks_sha256","retry-tasks.json"))):raise ValueError("Stale retry plan")
    base=read(out/"tasks.json");pending=read(out/"retry-tasks.json")
    combined={};all_results={}
    for e in ENGINES:
        combined[e]=base[e]+pending[e]
        if not combined[e]:continue
        old=read(out/f"synth-{e}.json") if base[e] else []
        new=read(out/f"retry-synth-{e}.json") if pending[e] else []
        for rows,tasks in ((old,base[e]),(new,pending[e])):
            byid={t["id"]:t for t in tasks}
            if len(rows)!=len(byid) or {r["id"] for r in rows}!=set(byid):raise ValueError("Incomplete or duplicate synthesis results")
            for r in rows:
                if any(r.get(k)!=v for k,v in byid[r["id"]].items()):raise ValueError("Result changed task")
                if r["status"]=="generated":
                    if sha(out/"takes"/r["file"])!=r["sha256"]:raise ValueError("Take checksum mismatch")
                elif r["status"]!="failed":raise ValueError("Unexpected synthesis status")
        all_results[e]=old+new
    group(combined)
    # Validate everything before changing the original manifests.
    for e,rows in all_results.items():write(out/f"synth-{e}.json",rows)
    write(out/"tasks.json",combined)
    state["status"]="merged";write(out/"retry-plan.json",state)
    print("Merged",state["new_takes"],"new takes; original recordings unchanged.")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["plan","merge"]);p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"));a=p.parse_args();globals()[a.mode](a.out)
