"""Private audition only: edit one real line, retain all other selected WAVs.
Legacy fingerprint authorizes original artifact replay, never new cache admission.
"""
import pathlib,json,shutil,copy,argparse,time
from line_cache_audition import seed
from line_cache import require,file_hash,passed
import pipeline
from quality import edits
TARGET=1
NEW="That's great! I'll bring my English notebook."
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2))
def stage(prior,refs,bundle,out):
    seed(prior,refs,bundle,"15187344062")
    plan=read(prior/"plan.json");tasks=read(prior/"tasks.json");qa=read(prior/"qa-report.json")
    require(len(plan["tracks"])==len(qa["tracks"])==1,"Unexpected audition scope")
    track=plan["tracks"][0];report=qa["tracks"][0]
    require(len(track["lines"])==5 and track["lines"][TARGET]["voice_key"]=="UK-T-F-02-pocket","Voice or script changed")
    line=track["lines"][TARGET]
    require(line["text"]=="That's great! I'll bring my notebook.","Unexpected original line")
    for k in ("text","qa_text","synthesis_text"):line[k]=NEW
    out.mkdir();(out/"takes").mkdir();(out/"cleaned").mkdir()
    old=[]
    for engine,rows in tasks.items():
        fixed=[]
        for t in rows:
            i=t["index"];q=report["lines"][i];prior_t=next(r for r in q["takes"] if r["id"]==t["id"])
            require(all(prior_t[k]==v for k,v in t.items()),"Original take task mismatch")
            ref=t["voice"].get("reference_file")
            if ref:
                p=refs/"refs"/pathlib.Path(ref).name
                require(file_hash(p)==t["voice"]["reference_sha256"],"Reference changed")
                t["voice"]["reference_file"]=str(p.resolve())
            if i==TARGET:
                t["line"]=copy.deepcopy(line)
                require(engine=="pocket","Unexpected changed engine")
            else:
                winner=next(r for r in q["takes"] if r["seed"]==q["selected_seed"])
                require(passed(winner),"Prior selected take not accepted")
                if t["seed"]==winner["seed"]:old.append({"index":i,"voice":t["line"]["voice_key"],"seed":t["seed"],"file":t["file"],"raw":winner["sha256"],"clean":winner["postprocess"]["sha256"]})
                if engine=="kitten":
                    r={**copy.deepcopy(prior_t),**t,"cache_hit":True,"cached_preferred_seed":winner["seed"]}
                    if r["status"]=="generated":
                        src=prior/"takes"/t["file"];require(file_hash(src)==r["sha256"],"Kitten raw mismatch");shutil.copyfile(src,out/"takes"/t["file"])
                    if t["seed"]==winner["seed"]:
                        src=prior/"cleaned"/t["file"];require(file_hash(src)==winner["postprocess"]["sha256"],"Kitten cleaned mismatch");shutil.copyfile(src,out/"cleaned"/t["file"]);r["cached_postprocess"]=winner["postprocess"]
                    fixed.append(r)
        if fixed:write(out/f"synth-{engine}.json",fixed)
    write(out/"plan.json",plan);write(out/"tasks.json",tasks)
    write(out/"manifest.json",{"demo":True,"publication_allowed":False,"status":"prepared","source":"one-line audition edit"})
    write(out/"unchanged.json",old)
    print(json.dumps({"fingerprint":read(bundle/"seed-report.json")["fingerprint"],"changed_index":TARGET,"unchanged":old}))
def verify(prior,out,review):
    manifest=read(out/"manifest.json");report=read(out/"qa-report.json")["tracks"][0];plan=read(out/"plan.json")["tracks"][0]
    require(manifest["status"]=="technical_pass_pending_listening" and manifest["publication_allowed"] is False and manifest["qa_sha256"]==file_hash(out/"qa-report.json"),"Edited dialogue failed")
    p=read(out/"synth-timing-pocket.json");c=read(out/"synth-timing-chatterbox.json")
    require(p["synthesis_calls"]==3 and p["cache_hit_takes"]==3 and c["synthesis_calls"]==0,"Unexpected synthesis scope")
    old=read(out/"unchanged.json");require(len(old)==4,"Missing unchanged lines")
    for e in old:
        q=report["lines"][e["index"]]
        require(q["selected_seed"]==e["seed"] and q["voice_key"]==e["voice"],"Unchanged selection changed")
        require(file_hash(out/"takes"/e["file"])==e["raw"] and file_hash(out/"cleaned"/e["file"])==e["clean"],"Unchanged audio bytes changed")
    changed=report["lines"][TARGET];w=next(r for r in changed["takes"] if r["seed"]==changed["selected_seed"])
    require(passed(w) and changed["text"]==NEW,"Changed line QA failed")
    oldq=read(prior/"qa-report.json")["tracks"][0]["lines"][TARGET];oldw=next(r for r in oldq["takes"] if r["seed"]==oldq["selected_seed"])
    require(w["sha256"]!=oldw["sha256"] and w["voice"]["reference_sha256"]==oldw["voice"]["reference_sha256"],"Changed audio or reference mismatch")
    from faster_whisper import WhisperModel
    start=time.perf_counter();model=WhisperModel("small.en",device="cpu",compute_type="int8",cpu_threads=4);load=time.perf_counter()-start
    review.mkdir(exist_ok=True)
    full=out/report["file"];require(file_hash(full)==report["sha256"],"Master hash mismatch")
    start=time.perf_counter();s,_=model.transcribe(str(full),language="en",beam_size=5,temperature=0,condition_on_previous_text=False);observed=" ".join(x.text.strip() for x in s);elapsed=time.perf_counter()-start
    expected=" ".join(l.get("qa_text",l["text"]) for l in plan["lines"])
    lex=edits(expected,observed)
    require(lex["errors"]==0,"Full dialogue ASR failed")
    shutil.copyfile(full,review/"B-edited-dialogue.mp3")
    prev=read(prior/"qa-report.json")["tracks"][0];src=prior/prev["file"];require(file_hash(src)==prev["sha256"],"Original full dialogue mismatch");shutil.copyfile(src,review/"A-original-dialogue.mp3")
    shutil.copyfile(prior/"cleaned"/oldw["file"],review/"A-original-Lucy.wav");shutil.copyfile(out/"cleaned"/w["file"],review/"B-edited-Lucy.wav")
    (review/"transcript-edited.txt").write_text("\n".join(l["speaker"]+": "+l["text"] for l in plan["lines"]))
    (review/"LISTENING-REVIEW.md").write_text("# User listening review\nA = original, B = one edited Lucy line. All other selected raw and cleaned WAVs are identical. Review intelligibility, UK accent, age, naturalness, stutter-like articulation, pacing and seams. Technical ASR does not establish subjective approval. No publication.\n")
    result={"status":"technical_pass_pending_listening","changed_index":TARGET,"unchanged_selected_hashes":old,"changed_raw_sha256":w["sha256"],"changed_clean_sha256":w["postprocess"]["sha256"],"reference_sha256":w["voice"]["reference_sha256"],"pocket":p,"chatterbox":c,"full_asr":lex,"asr_model_load_seconds":load,"full_asr_seconds":elapsed,"judge":read(out/"judge-timing.json"),"samples":{f.name:file_hash(f) for f in review.iterdir() if f.suffix in (".wav",".mp3")},"publication_allowed":False,"cache_scope":"legacy artifact replay only; fresh takes not admitted to legacy identity"}
    write(review/"acceptance-report.json",result);print(json.dumps(result))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["stage","verify"]);a=p.parse_args()
    if a.mode=="stage":stage(pathlib.Path("prior"),pathlib.Path("review").resolve(),pathlib.Path("bundle"),pathlib.Path("edited"))
    else:verify(pathlib.Path("prior"),pathlib.Path("edited"),pathlib.Path("audition"))
