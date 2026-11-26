"""Render only capability-approved Pocket TTS plans. Never read director instructions aloud."""
import json, pathlib, subprocess, sys
import numpy as np
import soundfile as sf
from pocket_tts import TTSModel

def render(plan, output):
    output.mkdir(parents=True,exist_ok=True)
    ready = [t for t in plan["tracks"] if t["status"] == "ready"]
    if not ready: raise RuntimeError("No renderable tracks")
    model=TTSModel.load_model()
    states={}
    report=[]
    for track in ready:
        if any(l["engine"]!="pocket" for l in track["lines"]): raise ValueError("Unsupported engine")
        pieces=[]
        for i,line in enumerate(track["lines"]):
            v=line["voice"]
            if v not in states: states[v]=model.get_state_for_audio_prompt(v)
            data=model.generate_audio(states[v],line["text"]).detach().cpu().numpy().reshape(-1)
            if not len(data) or not np.isfinite(data).all() or np.max(np.abs(data))<0.001: raise RuntimeError("Invalid waveform")
            pieces.append(data.astype(np.float32))
            if i+1<len(track["lines"]):
                pieces.append(np.zeros(round(model.sample_rate*line["pause_after_ms"]/1000),dtype=np.float32))
        full=np.concatenate(pieces)
        wav=output/(track["id"]+".wav")
        mp3=output/(track["id"]+".mp3")
        sf.write(wav,full,model.sample_rate,subtype="PCM_24")
        subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-i",str(wav),"-af","loudnorm=I=-18:TP=-2:LRA=7","-ar",str(model.sample_rate),"-c:a","libmp3lame","-b:a","128k",str(mp3)],check=True)
        report.append({"id":track["id"],"seconds":len(full)/model.sample_rate,"status":"rendered; manual listening required","lesson":track["lesson"],"slide":track["slide"],"file":mp3.name})
    (output/"render-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")

if __name__=="__main__":
    render(json.loads(pathlib.Path(sys.argv[1]).read_text()),pathlib.Path(sys.argv[2]))
