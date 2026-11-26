"""Unified MD renderer; engine-specific workers may run in isolated Python environments."""
import argparse, hashlib, json, os, pathlib, random, re, subprocess, sys
import numpy as np
import soundfile as sf

ROOT=pathlib.Path(__file__).resolve().parents[1]
PRESETS=json.loads((ROOT/"voice/presets.json").read_text())
ENGINES={"pocket","chatterbox","kitten"}
EMOTIONS={"angry","contemplative","excited","joyful","mundane","nervous","sad","stern","surprised","tender"}
def ff(*args):
    subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error",*map(str,args)],check=True)
def voice_config(line,production=False):
    engine=line["engine"]
    key=line.get("voice_key")
    cfg=PRESETS["voices"].get(key)
    if engine not in ENGINES or not cfg or (cfg["engine"],cfg["voice"])!=(engine,line["voice"]):
        raise ValueError("Unknown or mismatched voice; recompile Markdown")
    if not PRESETS["capabilities"].get(engine,{}).get("enabled") or PRESETS.get("model_review",{}).get(engine,{}).get("status")=="rejected" or cfg.get("status")=="rejected" or cfg["voice"] in PRESETS.get("rejected_voices",{}).get(engine,[]):
        raise ValueError("Rejected or disabled voice")
    if production and (cfg.get("status")!="approved" or not line.get("category") or cfg.get("category")!=line["category"]):
        raise ValueError("Production requires approved category voice")
    if engine=="kitten" and ("reference_file" in cfg or "reference_hf" in cfg):
        raise ValueError("Kitten C++ requires offline prepared voice assets; raw reference cloning is experimental and disabled in router")
    return cfg
def ref_path(cfg):
    if "reference_file" in cfg:
        base=(ROOT/"voice-assets").resolve()
        ref=(base/cfg["reference_file"]).resolve()
        if not ref.is_relative_to(base) or not ref.is_file(): raise ValueError("Invalid reference path")
        if hashlib.sha256(ref.read_bytes()).hexdigest()!=cfg.get("reference_sha256"): raise ValueError("Reference digest mismatch")
        return str(ref)
    if "reference_hf" in cfg:
        from huggingface_hub import hf_hub_download
        return hf_hub_download(repo_id=cfg["reference_hf"]["repo"],filename=cfg["reference_hf"]["filename"])
    return None
def stats(data,sr):
    data=np.asarray(data,dtype=np.float32).reshape(-1)
    if not len(data) or not np.isfinite(data).all(): raise ValueError("Empty or non-finite waveform")
    peak=float(np.max(np.abs(data))); rms=float(np.sqrt(np.mean(data**2)))
    if len(data)/sr<.25 or peak<.001 or rms<.0001: raise ValueError(f"Invalid waveform: seconds={len(data)/sr:.3f}, peak={peak:.5f}, rms={rms:.5f}")
    return data,{"seconds":round(len(data)/sr,3),"peak":peak,"rms":rms,"sample_rate":sr}
def spoken_text(line):
    text=line["text"]; emotion=line.get("emotion","neutral"); emphasis=line.get("emphasis",[])
    if emotion!="neutral" and (line["engine"]!="kitten" or emotion not in EMOTIONS): raise ValueError("Unsupported emotion")
    if emphasis and line["engine"]!="kitten": raise ValueError("Unsupported emphasis")
    if any(tag in text for tag in ("(((",")))")): raise ValueError("Raw emphasis tags not permitted")
    if line["engine"]=="kitten":
        for phrase in sorted(emphasis,key=len,reverse=True):
            if text.count(phrase)!=1: raise ValueError("Ambiguous emphasis")
            text=text.replace(phrase,"((("+phrase+")))",1)
        if emotion!="neutral": text="["+emotion+"] "+text
    return text
def worker(engine,request,response):
    import torch
    torch.set_num_threads(4)
    if engine=="pocket":
        from pocket_tts import TTSModel
        model=TTSModel.load_model(); sr=model.sample_rate
    elif engine=="chatterbox":
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        model=ChatterboxTurboTTS.from_pretrained(device="cpu"); sr=model.sr; default=model.conds
    elif engine=="kitten":
        from kitten_tts_cpp import KittenTTS
        model=KittenTTS("KittenML/kitten-tts-2",decoder="default",threads=4,repack=False); sr=model.sample_rate
    else: raise ValueError("Unknown engine")
    states={}; results={}
    for task in json.loads(request.read_text()):
        line=task["line"]; cfg=voice_config(line); text=spoken_text(line); path=pathlib.Path(task["path"]); key=line["voice_key"]
        attempts=[]
        for n,seed in enumerate((101,303,707),1):
            try:
                random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
                reference=ref_path(cfg) if key not in states else states[key][0]
                if engine=="pocket":
                    if key not in states: states[key]=(reference,model.get_state_for_audio_prompt(reference or cfg["voice"]))
                    audio=model.generate_audio(states[key][1],text).detach().cpu().numpy()
                elif engine=="chatterbox":
                    if reference:
                        if key not in states:
                            model.prepare_conditionals(reference); states[key]=(reference,model.conds)
                        model.conds=states[key][1]
                    elif cfg["voice"]=="default": model.conds=default
                    else: raise ValueError("Chatterbox requires a registered reference")
                    audio=model.generate(text).detach().cpu().numpy()
                else:
                    if reference: raise ValueError("Raw reference is unsupported by Kitten C++")
                    opts=[dict(temperature=0.8,top_p=0.8,top_k=50),dict(temperature=0.8,top_p=1.0,top_k=100,min_p=0.0),dict(temperature=0.9,top_p=1.0,top_k=200,min_p=0.0)][n-1]
                    audio=model.generate(text,voice=cfg["voice"],preset="expressive" if line.get("emotion","neutral")!="neutral" or line.get("emphasis") else "stable",advanced={"seed":seed},**opts)
                data,metrics=stats(audio,sr)
                word_count=max(1,len(re.findall(r"[A-Za-z0-9]+(?:\x27[A-Za-z]+)?",line["text"])))
                if metrics["seconds"]<max(.3,.14*word_count): raise ValueError(f"Truncated speech: {metrics}, words={word_count}")
                sf.write(path,data,sr,subtype="PCM_24")
                results[task["id"]]={"status":"generated","seed":seed,"attempts":attempts,**metrics}
                break
            except Exception as exc:
                attempts.append({"seed":seed,"error":repr(exc)})
                print(engine,task["id"],"attempt",n,repr(exc),flush=True)
                results[task["id"]]={"status":"failed","attempts":attempts}
        response.write_text(json.dumps(results,indent=2))
def render(plan,output,production=False):
    output.mkdir(parents=True,exist_ok=True); work=output/"segments"; work.mkdir(exist_ok=True)
    tasks={e:[] for e in ENGINES}; tracks=[]; report=[]
    for t in plan["tracks"]:
        if t["status"]!="ready":
            report.append({"id":t["id"],"status":"blocked","reasons":t.get("reasons",[])}); continue
        try:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}",t["id"]): raise ValueError("Unsafe track id")
            if t["options"]["speed"]!=1 or t["options"]["takes"]!=1: raise ValueError("Unsupported speed or take count")
            for line in t["lines"]: voice_config(line,production); spoken_text(line)
            for i,line in enumerate(t["lines"]):
                uid=f'{t["id"]}-{i:03d}'; path=work/(uid+".wav")
                path.unlink(missing_ok=True)
                tasks[line["engine"]].append({"id":uid,"line":line,"path":str(path.resolve())})
            tracks.append(t)
        except Exception as exc: report.append({"id":t["id"],"status":"failed","error":repr(exc)})
    results={}
    for engine,items in sorted(tasks.items()):
        if not items: continue
        req=work/(engine+"-request.json"); res=work/(engine+"-result.json")
        req.write_text(json.dumps(items)); res.unlink(missing_ok=True)
        proc=subprocess.run([os.environ.get("IVNM_PYTHON_"+engine.upper(),sys.executable),str(pathlib.Path(__file__).resolve()),"--worker",engine,str(req.resolve()),str(res.resolve())])
        if res.exists(): results.update(json.loads(res.read_text()))
        if proc.returncode: print(engine,"worker exited",proc.returncode,flush=True)
    for t in tracks:
        try:
            pieces=[]; detail=[]
            for i,line in enumerate(t["lines"]):
                uid=f'{t["id"]}-{i:03d}'; r=results.get(uid,{"status":"failed","error":"Worker did not complete"})
                if r["status"]!="generated": raise RuntimeError(f"{uid}: {r}")
                pcm=work/(uid+".pcm.wav")
                ff("-i",work/(uid+".wav"),"-ar",24000,"-ac",1,"-c:a","pcm_s16le",pcm)
                data,_=sf.read(pcm,dtype="float32"); pieces.append(data)
                if i+1<len(t["lines"]): pieces.append(np.zeros(round(24000*line["pause_after_ms"]/1000),dtype=np.float32))
                detail.append({"speaker":line["speaker"],"engine":line["engine"],"voice":line["voice"],**r})
            full=np.concatenate(pieces); wav=output/(t["id"]+".wav"); mp3=output/(t["id"]+".mp3")
            sf.write(wav,full,24000,subtype="PCM_24")
            ff("-i",wav,"-af","loudnorm=I=-18:TP=-2:LRA=7","-ar",24000,"-c:a","libmp3lame","-b:a","128k",mp3)
            report.append({"id":t["id"],"seconds":len(full)/24000,"status":"rendered; manual listening required","lesson":t.get("lesson"),"slide":t.get("slide"),"file":mp3.name,"lines":detail,"warnings":t.get("warnings",[])})
        except Exception as exc:
            report.append({"id":t["id"],"status":"failed","error":repr(exc)})
    (output/"render-report.json").write_text(json.dumps(report,indent=2))
    if not tracks or any(t["status"]=="failed" for t in report): raise SystemExit("Incomplete render; inspect report")
if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--worker":
        worker(sys.argv[2],pathlib.Path(sys.argv[3]),pathlib.Path(sys.argv[4]))
    else:
        p=argparse.ArgumentParser(); p.add_argument("plan",type=pathlib.Path); p.add_argument("output",type=pathlib.Path); p.add_argument("--production",action="store_true"); a=p.parse_args()
        render(json.loads(a.plan.read_text()),a.output,a.production)
