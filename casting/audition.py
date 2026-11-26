"""Create synthetic actor candidates. No recordings of real people are used."""
import argparse, json, pathlib, time, subprocess
import numpy as np
import soundfile as sf
import torch
from voxcpm import VoxCPM
ROOT=pathlib.Path(__file__).resolve().parents[1]
BANK=json.loads((ROOT/"voice/voice-bank.json").read_text())
TEXT="I thought we were meeting near the house at half past ten. Could you show me the route on your phone?"
REACTION="Oh, really? That's wonderful! I didn't expect to see you here."
def main():
    p=argparse.ArgumentParser()
    p.add_argument("category",choices=sorted(BANK["slots"]))
    p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"))
    args=p.parse_args()
    slot=BANK["slots"][args.category]
    args.out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4)
    model=VoxCPM.from_pretrained("openbmb/VoxCPM2",load_denoiser=False,optimize=False,device="cpu")
    sr=model.tts_model.sample_rate
    style=f'{slot["direction"]} Ordinary everyday conversation, clean and relaxed voice, no growling, creak, nasal congestion or artificial pitch. '
    if args.category.startswith("UK"): style+="Use contemporary standard southern British English pronunciation."
    else: style+="Use authentic mainstream Canadian English pronunciation, not an exaggerated regional caricature."
    report={"category":args.category,"model":"openbmb/VoxCPM2","sample_rate":sr,"status":"candidate_only","samples":[]}
    def save(wav,name):
        wav=np.asarray(wav).reshape(-1)
        if not np.isfinite(wav).all() or len(wav)<sr or np.max(np.abs(wav))<.001: raise ValueError("Invalid audio")
        path=args.out/(name+".wav")
        sf.write(path,wav,sr,subtype="PCM_24")
        subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-i",str(path),"-c:a","libmp3lame","-b:a","192k",str(path.with_suffix(".mp3"))],check=True)
        return path,len(wav)/sr
    for seed in (101,202):
        name=f"{args.category}-{seed}"
        t=time.monotonic()
        try:
            audio=model.generate(text=f"({style}){TEXT}",cfg_value=2.0,inference_timesteps=10,seed=seed)
            ref,duration=save(audio,name+"-reference")
            item={"id":name,"seed":seed,"prompt":style,"reference":ref.name,"text":TEXT,"duration_seconds":duration,"generation_seconds":round(time.monotonic()-t,2),"status":"reference_generated"}
            report["samples"].append(item)
            (args.out/"casting-report.json").write_text(json.dumps(report,indent=2))
            emotion="Genuine mild surprise followed by warm happiness, natural conversational rhythm. Retain the reference voice identity."
            reaction=model.generate(text=f"({emotion}){REACTION}",reference_wav_path=str(ref),cfg_value=2.0,inference_timesteps=10,seed=seed+1)
            path,duration=save(reaction,name+"-reaction")
            item.update({"reaction":path.name,"reaction_text":REACTION,"reaction_seconds":duration,"status":"pending_listening_review"})
        except Exception as e:
            report["samples"].append({"id":name,"status":"error","error":repr(e)})
            print(name,repr(e),flush=True)
        finally:
            (args.out/"casting-report.json").write_text(json.dumps(report,indent=2))
    if not any(s["status"]=="pending_listening_review" for s in report["samples"]): raise RuntimeError("No complete voice audition")
if __name__=="__main__": main()
