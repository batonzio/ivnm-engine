"""Targeted diagnostic: no changes to successful Pocket/Chatterbox jobs or recordings."""
import argparse, hashlib, json, pathlib, random, re
import numpy as np
import soundfile as sf
import torch
from round2 import REFERENCE, LINES, save
from repair_kitten import validate

def seed_all(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
def gate(wave,sr,text):
    words=len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text))
    # Conservative duration floor, not an ASR accuracy claim.
    return validate(wave,sr,max(.5,words*.14))
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def rescue(out,refs):
    from kittenml import KittenTTS
    model=KittenTTS("KittenML/kitten-tts-2",device="cpu")
    sr=model.sample_rate
    name="CA-T-F-02"; ref=refs/(name+"-ref.wav")
    if not ref.is_file(): raise FileNotFoundError(ref)
    # Only line 2 and assembled audition are replaced. Preserve every other audio file.
    keep={p.name:sha(p) for p in out.iterdir() if p.suffix in (".wav",".mp3") and p.name not in {name+"-line2.wav",name+"-line2.mp3",name+"-audition.wav",name+"-audition.mp3"}}
    report={"candidate":name,"reference_sha256":sha(ref),"line":2,"text":LINES[1],"preserved":keep,"attempts":[],"status":"failed"}
    rp=out/"targeted-rescue.json"
    def checkpoint(): rp.write_text(json.dumps(report,indent=2))
    trials=[
        (801,False,[LINES[1]]),
        (913,False,["That's great news.","Shall we go out for lunch afterwards?"]),
        (1051,True,["That's great news.","Shall we go out for lunch afterwards?"]),
    ]
    for seed,use_prompt,segments in trials:
        item={"seed":seed,"use_reference_prompt":use_prompt,"segments":segments,"metrics":[]}
        try:
            pieces=[]
            for i,segment in enumerate(segments):
                seed_all(seed+i)
                raw=model.generate(segment,reference=str(ref),reference_text=REFERENCE,preset="stable",use_reference_prompt=use_prompt)
                data,metrics=gate(raw,sr,segment); item["metrics"].append(metrics)
                if pieces: pieces.append(np.zeros(round(sr*.16),dtype=np.float32))
                pieces.append(data)
            audio=np.concatenate(pieces)
            gate(audio,sr,LINES[1])
            save(audio,sr,out/(name+"-line2.wav"))
            allpieces=[]
            for i,text in enumerate(LINES,1):
                wav,rate=sf.read(out/f"{name}-line{i}.wav",dtype="float32")
                if rate!=sr: raise ValueError("Sample rate mismatch")
                wave,_=gate(wav,sr,text)
                if allpieces: allpieces.append(np.zeros(round(sr*.32),dtype=np.float32))
                allpieces.append(wave)
            save(np.concatenate(allpieces),sr,out/(name+"-audition.wav"))
            item["status"]="generated"
            report["attempts"].append(item)
            assert all(sha(out/f)==v for f,v in keep.items()),"Successful recording modified"
            report["status"]="pending_listening_review"
            report["identity_warning"]="Speaker reference kept; disabling audio prompt may affect identity. Manual audition required."
            checkpoint()
            oldpath=out/"comparison-report.json"
            old=json.loads(oldpath.read_text())
            for entry in old["samples"]:
                if entry["id"]==name:
                    entry.update(status="pending_listening_review",file=name+"-audition.wav",targeted_rescue=rp.name)
            oldpath.write_text(json.dumps(old,indent=2))
            print("Recovered CA-T-F-02 line 2",flush=True)
            return
        except Exception as exc:
            item.update(status="failed",error=repr(exc)); report["attempts"].append(item); checkpoint()
            print("Trial failed",item,flush=True)
    raise RuntimeError("Targeted rescue exhausted; do not relax quality gate or substitute voice")
def cpp_smoke(out):
    from kitten_tts_cpp import KittenTTS
    model=KittenTTS("KittenML/kitten-tts-2",decoder="default",threads=4,repack=False)
    sr=model.sample_rate
    tests=[("Bella","Did you enjoy the exhibition?","Did you enjoy the exhibition?","stable"),("Jasper","Yes, it was wonderful.","[joyful] Yes, it was (((wonderful))).","expressive")]
    report=[]
    for i,(voice,plain,text,preset) in enumerate(tests):
        item={"voice":voice,"text":plain,"conditioning":text,"attempts":[],"status":"failed"}
        for seed in (101,303,707):
            try:
                audio=model.generate(text,voice=voice,preset=preset,advanced={"seed":seed})
                data,metrics=gate(audio,sr,plain)
                save(data,sr,out/f"cpp-smoke-{i}.wav")
                item.update(status="pending_listening_review",seed=seed,metrics=metrics)
                break
            except Exception as e: item["attempts"].append({"seed":seed,"error":repr(e)})
        report.append(item)
        (out/"cpp-smoke-report.json").write_text(json.dumps(report,indent=2))
        print(item,flush=True)
    if any(i["status"]=="failed" for i in report): raise RuntimeError("C++ smoke failed")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["rescue","cpp"]);p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"));p.add_argument("--refs",type=pathlib.Path,default=pathlib.Path("refs"));a=p.parse_args()
    torch.set_num_threads(4);a.out.mkdir(parents=True,exist_ok=True)
    if a.mode=="rescue": rescue(a.out,a.refs)
    else: cpp_smoke(a.out)
