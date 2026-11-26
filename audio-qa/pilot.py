"""Pilot of multi-take QA using the same synthetic reference and scripts for two engines."""
import argparse, hashlib, json, os, pathlib, random, subprocess, time
import numpy as np
import soundfile as sf
from quality import signal,evaluate,select

LINES=["The exhibition opens tomorrow morning.","If you arrive before half past ten, we can meet outside the library and walk to the museum together."]
SEEDS=[101,303,707]

def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["generate","judge"]);p.add_argument("engine",choices=["pocket","chatterbox"]);p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"));p.add_argument("--ref",type=pathlib.Path,default=pathlib.Path("refs/CA-A-M-01-ref.wav"));a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True); manifest=a.out/"takes.json"
    if a.mode=="generate":
        import torch
        torch.set_num_threads(4)
        if a.engine=="pocket":
            from pocket_tts import TTSModel
            model=TTSModel.load_model(); sr=model.sample_rate; state=model.get_state_for_audio_prompt(str(a.ref))
            def synth(text):return model.generate_audio(state,text)
        else:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            model=ChatterboxTurboTTS.from_pretrained(device="cpu"); sr=model.sr
            model.prepare_conditionals(str(a.ref))
            def synth(text):return model.generate(text)
        report={"engine":a.engine,"reference_sha256":hashlib.sha256(a.ref.read_bytes()).hexdigest(),"status":"candidate_only","lines":[]}
        for idx,text in enumerate(LINES,1):
            line={"index":idx,"text":text,"takes":[]}
            report["lines"].append(line)
            for seed in SEEDS:
                item={"seed":seed,"status":"failed"}
                start=time.monotonic()
                try:
                    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
                    wave=synth(text).detach().cpu().numpy().reshape(-1)
                    item["signal"]=signal(wave,sr,text)
                    if item["signal"]["passed"]:
                        name=f"line{idx}-seed{seed}.wav";sf.write(a.out/name,wave,sr,subtype="PCM_24")
                        item.update(status="generated",file=name)
                except Exception as exc:item["error"]=repr(exc)
                item["generation_seconds"]=round(time.monotonic()-start,3)
                line["takes"].append(item);manifest.write_text(json.dumps(report,indent=2));print(idx,item,flush=True)
        return
    from faster_whisper import WhisperModel
    model=WhisperModel("small.en",device="cpu",compute_type="int8",cpu_threads=4)
    report=json.loads(manifest.read_text());report["asr_model"]="faster-whisper small.en / int8 CPU";report["gate"]="strict normalized word match; manual listening required"
    pieces=[];all_pass=True
    for line in report["lines"]:
        for item in line["takes"]:
            if item["status"]!="generated":continue
            try:
                path=a.out/item["file"];wave,sr=sf.read(path,dtype="float32")
                segments,_=model.transcribe(str(path),language="en",beam_size=5,temperature=0,condition_on_previous_text=False)
                transcript=" ".join(s.text.strip() for s in segments)
                item["qa"]=evaluate(wave,sr,line["text"],transcript)
            except Exception as exc:item["qa"]={"passed":False,"reasons":[repr(exc)]}
        winner=select(line["takes"]);line["selected_seed"]=winner["seed"] if winner else None
        if winner:
            path=a.out/winner["file"]; pcm=a.out/f"selected-line{line['index']}.wav"
            subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-i",str(path),"-ar","24000","-ac","1",str(pcm)],check=True)
            wave,_=sf.read(pcm,dtype="float32");pieces.append(wave)
            if line["index"]<len(report["lines"]):pieces.append(np.zeros(7680,dtype=np.float32))
        else:all_pass=False
        print("line",line["index"],"selected seed",line["selected_seed"],flush=True)
        (a.out/"qa-report.json").write_text(json.dumps(report,indent=2))
    report["status"]="technical_pass_pending_listening" if all_pass else "rejected_incomplete"
    if all_pass:
        sf.write(a.out/"selected.wav",np.concatenate(pieces),24000,subtype="PCM_24")
        subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-i",str(a.out/"selected.wav"),"-af","loudnorm=I=-18:TP=-2:LRA=7","-ar","24000","-c:a","libmp3lame","-b:a","128k",str(a.out/"selected.mp3")],check=True)
    (a.out/"qa-report.json").write_text(json.dumps(report,indent=2))
    if not all_pass:raise SystemExit("No acceptable take for one or more lines; no final master published")
if __name__=="__main__":main()
