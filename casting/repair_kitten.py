"""Resume failed Kitten auditions, retaining byte-identical successful candidates."""
import argparse, hashlib, json, pathlib, random, time
import numpy as np
import soundfile as sf
import torch
from round2 import BANK, LINES, REFERENCE, save

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(wave,sr,min_duration=.5):
    wave=np.asarray(wave,dtype=np.float32).reshape(-1)
    seconds=len(wave)/sr
    finite=bool(np.isfinite(wave).all())
    peak=float(np.max(np.abs(wave))) if len(wave) and finite else None
    rms=float(np.sqrt(np.mean(wave**2))) if len(wave) and finite else None
    metrics={"seconds":round(seconds,3),"finite":finite,"peak":peak,"rms":rms,"sample_rate":sr}
    if not finite or seconds<min_duration or peak is None or peak<.001 or rms<.0001:
        raise ValueError("Invalid waveform: "+json.dumps(metrics))
    return wave,metrics
def main():
    p=argparse.ArgumentParser()
    p.add_argument("category",choices=sorted(BANK["slots"]))
    p.add_argument("--refs",type=pathlib.Path,default=pathlib.Path("refs"))
    p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"))
    a=p.parse_args()
    a.out.mkdir(exist_ok=True)
    reportpath=a.out/"comparison-report.json"
    old=json.loads(reportpath.read_text())
    previous={x["id"]:x for x in old["samples"]}
    report={"engine":"kitten","category":a.category,"status":"candidate_only","reference_text":REFERENCE,"source_run":45850434632,"samples":[]}
    manifest=a.out/"repair-report.json"
    preserved={}
    model=None
    torch.set_num_threads(4)
    for n in (1,2):
        name=f"{a.category}-{n:02d}"
        entry=previous[name]
        ref=a.refs/(name+"-ref.wav")
        refdata,refsr=sf.read(ref)
        _,refmetrics=validate(refdata,refsr,5.0)
        entry["reference_sha256"]=digest(ref)
        entry["reference_metrics"]=refmetrics
        if entry["status"]=="pending_listening_review":
            for f in sorted(a.out.glob(name+"-*.wav"))+sorted(a.out.glob(name+"-*.mp3")): preserved[f.name]=digest(f)
            report["samples"].append(entry)
            print(name,"preserved complete candidate",flush=True)
            continue
        if model is None:
            from kittenml import KittenTTS
            model=KittenTTS("KittenML/kitten-tts-2",device="cpu")
        sr=model.sample_rate
        start=time.monotonic()
        item={"id":name,"reference_sha256":digest(ref),"reference_metrics":refmetrics,"lines":[],"status":"pending"}
        pieces=[]
        # CA-A-M-01 has a new reference. Never combine old and new identities.
        if name=="CA-A-M-01":
            for f in a.out.glob(name+"-*.wav"): f.unlink()
            for f in a.out.glob(name+"-*.mp3"): f.unlink()
        for i,text in enumerate(LINES,1):
            wav=a.out/f"{name}-line{i}.wav"
            mp3=wav.with_suffix(".mp3")
            attempts=[]
            audio=None
            if wav.is_file() and mp3.is_file():
                try:
                    data,oldsr=sf.read(wav)
                    if oldsr!=sr: raise ValueError("Sample rate mismatch")
                    audio,metrics=validate(data,sr)
                    preserved[wav.name]=digest(wav); preserved[mp3.name]=digest(mp3)
                    attempts.append({"status":"preserved"})
                except Exception as exc:
                    audio=None
                    attempts.append({"status":"discarded_invalid","error":repr(exc)})
            if audio is None:
                for seed,options in [(313,{"preset":"stable"}),(719,{"preset":"stable","temperature":0.85,"top_p":0.95}),(1201,{"preset":"expressive","temperature":0.9,"top_p":0.95}),(2027,{"preset":"stable","temperature":0.75,"top_p":0.99})]:
                    try:
                        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
                        candidate=model.generate(text,reference=str(ref),reference_text=REFERENCE,**options)
                        audio,metrics=validate(candidate,sr)
                        save(audio,sr,wav)
                        attempts.append({"seed":seed,"options":options,"status":"generated",**metrics})
                        break
                    except Exception as exc:
                        audio=None
                        attempts.append({"seed":seed,"options":options,"status":"failed","error":repr(exc)})
                        print(name,i,seed,repr(exc),flush=True)
            item["lines"].append({"index":i,"text":text,"file":wav.name if audio is not None else None,"attempts":attempts,"status":"generated" if audio is not None else "failed"})
            if audio is not None: pieces.extend([audio,np.zeros(round(sr*.32),dtype=np.float32)])
            else:
                wav.unlink(missing_ok=True); mp3.unlink(missing_ok=True)
            manifest.write_text(json.dumps({"samples":report["samples"]+[item],"preserved":preserved},indent=2))
        master=a.out/(name+"-audition.wav")
        if all(x["status"]=="generated" for x in item["lines"]):
            save(np.concatenate(pieces[:-1]),sr,master)
            item.update(status="pending_listening_review",file=master.name)
        else:
            master.unlink(missing_ok=True); master.with_suffix(".mp3").unlink(missing_ok=True)
            item["status"]="failed"
        item["generation_seconds"]=round(time.monotonic()-start,2)
        report["samples"].append(item)
        print(name,item["status"],flush=True)
    for name,sha in preserved.items(): assert digest(a.out/name)==sha, f"Preserved output modified: {name}"
    report["preserved"]=preserved
    manifest.write_text(json.dumps(report,indent=2))
    reportpath.write_text(json.dumps(report,indent=2))
    if any(x["status"]!="pending_listening_review" for x in report["samples"]):
        raise SystemExit("Incomplete recovery; inspect metrics and retained audio")
if __name__=="__main__": main()
