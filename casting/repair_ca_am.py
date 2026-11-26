"""Repair only CA-A-M-01; preserve CA-A-M-02 and the other eleven categories."""
import argparse, hashlib, json, pathlib, random
import numpy as np
import soundfile as sf
import torch
from round2 import BANK, REFERENCE, LINES, save

P=pathlib.Path("out")
CANDIDATE="CA-A-M-01"
KEEP="CA-A-M-02"
MIN_SECONDS=6.0

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=["design","chatterbox","verify"])
    args=parser.parse_args()
    torch.set_num_threads(4)
    ref=P/(CANDIDATE+"-ref.wav")
    keep_files=sorted(P.glob(KEEP+"-*.wav"))+sorted(P.glob(KEEP+"-*.mp3"))
    if not (P/(KEEP+"-audition.wav")).is_file(): raise RuntimeError("Successful second candidate is missing")
    manifest=P/"repair-ca-am.json"
    if args.stage=="design":
        report={"category":"CA-A-M","source_run":45844095394,"source_artifact":15133351616,"candidate":CANDIDATE,"previous_reference_seconds":sf.info(ref).duration,"preserved":{x.name:digest(x) for x in keep_files},"attempts":[]}
        manifest.write_text(json.dumps(report,indent=2))
        from qwen_tts import Qwen3TTSModel
        model=Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",device_map="cpu",dtype=torch.float32,attn_implementation="eager")
        prompt="A fictional adult male speaker, 30 to 45 years old, mainstream Canadian English. Clear relaxed natural timbre. Conversational, unhurried and clearly articulated; natural pauses at sentence boundaries. No forced pitch, rasp, nasal congestion, or metallic tone. Not an impression of any real person."
        for seed in (303,404,505,606):
            random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
            try:
                wavs,sr=model.generate_voice_design(text=REFERENCE,language="English",instruct=prompt,max_new_tokens=768)
                wave=np.asarray(wavs[0]).reshape(-1)
                duration=len(wave)/sr
                if not np.isfinite(wave).all() or duration<MIN_SECONDS: raise ValueError(f"Reference duration {duration:.3f}s or invalid samples; need >= {MIN_SECONDS}s")
                save(wave,sr,ref)
                report["attempts"].append({"seed":seed,"duration":duration,"status":"accepted_technical"})
                report.update(seed=seed,reference_text=REFERENCE,reference_seconds=sf.info(ref).duration,reference_sha256=digest(ref),status="reference_ready")
                manifest.write_text(json.dumps(report,indent=2))
                print("Valid reference:",report["reference_seconds"],flush=True)
                return
            except Exception as e:
                report["attempts"].append({"seed":seed,"status":"failed","error":repr(e)})
                manifest.write_text(json.dumps(report,indent=2))
                print("Reference retry",seed,repr(e),flush=True)
        raise RuntimeError("No valid reference after four attempts")
    report=json.loads(manifest.read_text())
    assert all(digest(P/name)==sha for name,sha in report["preserved"].items()),"Second candidate was modified"
    assert sf.info(ref).duration>=MIN_SECONDS and digest(ref)==report["reference_sha256"]
    if args.stage=="chatterbox":
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        model=ChatterboxTurboTTS.from_pretrained(device="cpu")
        pieces=[]
        for i,line in enumerate(LINES,1):
            error=None
            for seed in (101+i,301+i,501+i):
                try:
                    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
                    audio=model.generate(line,audio_prompt_path=str(ref)).detach().cpu().numpy().reshape(-1)
                    save(audio,model.sr,P/f"{CANDIDATE}-line{i}.wav")
                    pieces.extend([audio,np.zeros(round(model.sr*.32),dtype=np.float32)])
                    error=None
                    break
                except Exception as e:
                    error=e
                    print("Synthesis retry",i,seed,repr(e),flush=True)
            if error is not None: raise error
        save(np.concatenate(pieces[:-1]),model.sr,P/f"{CANDIDATE}-audition.wav")
        report["status"]="pending_listening_review"
        report["lines"]=LINES
        manifest.write_text(json.dumps(report,indent=2))
        for stage in ("design","chatterbox"):
            path=P/(stage+"-report.json")
            old=json.loads(path.read_text())
            entry=next(x for x in old["samples"] if x["id"]==CANDIDATE)
            entry.pop("error",None)
            entry.update(status="pending_listening_review",seed=report["seed"] if stage=="design" else 101,file=CANDIDATE+("-ref.wav" if stage=="design" else "-audition.wav"),repair_manifest=manifest.name)
            if stage=="design": entry["prompt"]= "See repair-ca-am.json; same reference transcript, new seed, natural unhurried delivery."
            path.write_text(json.dumps(old,indent=2))
    else:
        for n in (CANDIDATE,KEEP):
            for s in ("ref","line1","line2","line3","audition"):
                for ext in ("wav","mp3"):
                    assert (P/f"{n}-{s}.{ext}").stat().st_size>0
        assert report["status"]=="pending_listening_review"
        print("Both candidates complete; second candidate unchanged; reference duration",sf.info(ref).duration,flush=True)
if __name__=="__main__": main()
