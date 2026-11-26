"""Audition the same synthetic references and exact Round 2 text on additional engines."""
import argparse, json, pathlib, random, time
import numpy as np
import torch
from round2 import BANK, REFERENCE, LINES, save

def main():
    p=argparse.ArgumentParser()
    p.add_argument("engine",choices=["pocket","kitten"])
    p.add_argument("category",choices=sorted(BANK["slots"]))
    p.add_argument("--refs",type=pathlib.Path,default=pathlib.Path("refs"))
    p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"))
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    report={"category":args.category,"engine":args.engine,"reference_source":"exact Round 2 synthetic WAV","reference_text":REFERENCE,"lines":LINES,"samples":[],"status":"candidate_only","backend":"PyTorch"}
    rp=args.out/"comparison-report.json"
    torch.set_num_threads(4)
    if args.engine=="pocket":
        from pocket_tts import TTSModel
        model=TTSModel.load_model()
    else:
        from kittenml import KittenTTS
        model=KittenTTS("KittenML/kitten-tts-2",device="cpu")
    sr=model.sample_rate
    for n,seed in enumerate((101,202),1):
        name=f"{args.category}-{n:02d}"
        ref=args.refs/(name+"-ref.wav")
        entry={"id":name,"reference":ref.name,"seed":seed,"lines":[],"status":"pending"}
        start=time.monotonic()
        try:
            if not ref.is_file(): raise FileNotFoundError(str(ref))
            random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
            state=model.get_state_for_audio_prompt(str(ref)) if args.engine=="pocket" else None
            pieces=[]
            for i,text in enumerate(LINES,1):
                if args.engine=="pocket":
                    audio=model.generate_audio(state,text).detach().cpu().numpy()
                else:
                    # Python backend supports raw references; C++ currently requires offline prepared assets.
                    audio=model.generate(text,reference=str(ref),reference_text=REFERENCE,preset="stable")
                audio=np.asarray(audio,dtype=np.float32).reshape(-1)
                line=args.out/f"{name}-line{i}.wav"
                save(audio,sr,line)
                pieces.extend([audio,np.zeros(round(sr*.32),dtype=np.float32)])
                entry["lines"].append({"text":text,"file":line.name,"duration_seconds":round(len(audio)/sr,3)})
            master=args.out/(name+"-audition.wav")
            save(np.concatenate(pieces[:-1]),sr,master)
            entry.update(status="pending_listening_review",file=master.name)
        except Exception as exc:
            entry.update(status="failed",error=repr(exc))
        entry["generation_seconds"]=round(time.monotonic()-start,2)
        report["samples"].append(entry)
        rp.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(name,entry["status"],entry.get("error",""),flush=True)
    if any(s["status"]=="failed" for s in report["samples"]):
        raise SystemExit("Incomplete audition; successful files preserved")
if __name__=="__main__": main()
