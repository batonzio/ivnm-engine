"""MD-first production pipeline. Never publish unapproved voices or failed takes."""
import argparse, hashlib, importlib.util, json, os, pathlib, re, subprocess, sys, time
import line_cache
import numpy as np
import soundfile as sf
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"audio-qa"))
from quality import signal,select
sys.path.insert(0,str(ROOT/"postprocess"))
from mastering import cleanup,master,repetition_report
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def read(p):return json.loads(p.read_text())
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ff(*args):subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error",*map(str,args)],check=True)
def file_under(base,rel):
    p=(base/rel).resolve()
    if not p.is_relative_to(base.resolve()) or not p.is_file():raise ValueError("Missing or unsafe asset")
    return p
def registry(path,assets,demo=False):
    compiler=load_module("compiler",ROOT/"md-first/compile.py")
    presets=compiler.PRESETS; bank=compiler.BANK
    if path:
        for item in read(path)["voices"]:
            category=item["category"]; slot=bank["slots"][category]
            if item["engine"] not in ("chatterbox","pocket"):raise ValueError("Custom Kitten C++ assets not yet supported")
            key=item["key"]
            rejected=read(ROOT/"casting/preferences.json").get("rejected_candidates",{})
            if key in rejected or (item["engine"]=="pocket" and pathlib.Path(item["reference_file"]).name=="UK-T-F-01-ref.wav"):
                raise ValueError("Voice rejected by user listening review")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",key) or key in presets["voices"]:raise ValueError("Invalid/duplicate key")
            ref=file_under(assets,item["reference_file"])
            if sha(ref)!=item["reference_sha256"]:raise ValueError("Reference checksum mismatch")
            if sf.info(ref).duration<5.1:raise ValueError("Reference too short")
            reviewed=item.get("reviewed") is True and item.get("accent_ok") is True and item.get("age_ok") is True and item.get("naturalness_ok") is True and item.get("gender_ok") is True
            if not demo and not reviewed:raise ValueError("Missing human audition approval")
            cfg={**item,"voice":key,"accent":slot["accent"] if reviewed else "unverified","age_group":slot["age_group"],"gender":slot["gender"],"status":"approved" if reviewed else "candidate","reference_file":str(ref)}
            presets["voices"][key]=cfg
            if reviewed:
                variant=item["variant"]
                if variant not in ("primary","alternate") or slot[variant] is not None:raise ValueError("Duplicate/invalid slot")
                slot[variant]=key;slot["status"]="approved"
    return compiler,presets,bank
def prepare(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    compiler,presets,bank=registry(args.registry,args.assets,args.demo)
    plan=compiler.compile_md(args.md)
    import yaml
    director=load_module("speech_director",ROOT/"speech-director/director.py")
    director.apply(plan,[yaml.safe_load(b) for b in compiler.BLOCK.findall(args.md.read_text(encoding="utf-8"))],presets["capabilities"])
    # Only this pipeline implements multiple takes. Other compiler gates remain intact.
    for t in plan["tracks"]:
        t["reasons"]=[r for r in t["reasons"] if r!="Multi-take selection not implemented yet"]
        t["status"]="blocked" if t["reasons"] else "ready"
        if not args.demo:
            for line in t["lines"]:
                cfg=presets["voices"].get(line["voice_key"],{})
                if cfg.get("status")!="approved" or not line.get("category") or cfg.get("category")!=line["category"]:
                    t["status"]="blocked";t["reasons"].append("Production requires human-approved category voice")
        if not t["lesson"] or not t["slide"]:t["status"]="blocked";t["reasons"].append("Lesson and slide bindings required")
    write(out/"plan.json",plan)
    if any(t["status"]!="ready" for t in plan["tracks"]):raise SystemExit("Blocked tracks; inspect plan.json. Nothing rendered or published.")
    tasks={e:[] for e in ("pocket","chatterbox","kitten")}
    for t in plan["tracks"]:
        for i,line in enumerate(t["lines"]):
            cfg=presets["voices"][line["voice_key"]]
            for k in range(t["options"]["takes"]):
                uid=f'{t["id"]}-{i:03d}-{k:02d}'
                seed=101+202*k
                tasks[line["engine"]].append({"id":uid,"track":t["id"],"index":i,"seed":seed,"line":line,"voice":cfg,"file":uid+".wav"})
    write(out/"tasks.json",tasks);write(out/"manifest.json",{"schema":1,"source_sha256":sha(args.md),"demo":args.demo,"status":"prepared","publication_allowed":False})
def synth(args):
    started=time.perf_counter()
    retry=getattr(args,"retry",False)
    if retry:
        state=read(args.out/"retry-plan.json")
        if state["status"]!="ready" or state["tasks_sha256"]!=sha(args.out/"retry-tasks.json") or state["base_tasks_sha256"]!=sha(args.out/"tasks.json") or state["qa_sha256"]!=sha(args.out/"qa-report.json"):raise ValueError("Stale retry plan")
    tasks=read(args.out/("retry-tasks.json" if retry else "tasks.json"))[args.engine]
    if not tasks:return
    directory=args.out/"takes";directory.mkdir(exist_ok=True)
    restored={};cache=getattr(args,"line_cache",None);lookup_start=time.perf_counter()
    if cache and not retry:
        if read(args.out/"manifest.json").get("demo") is not True:raise ValueError("Line cache is preview only")
        tracks={t["id"]:t for t in read(args.out/"plan.json")["tracks"]}
        added=[];known={t["id"] for t in tasks}
        for (track,index),group in line_cache.group(tasks).items():
            identity=line_cache.identity(group,tracks[track],args.cache_fingerprint)
            hit=line_cache.restore(cache,identity,group,args.out)
            if hit:
                for row in hit:
                    restored[row["id"]]=row
                    if row["id"] not in known:
                        require_keys=("id","track","index","seed","line","voice","file","retry")
                        added.append({k:row[k] for k in require_keys});known.add(row["id"])
        if added:
            # Keep retry.py's complete original task/result history; no synthesized fake rows.
            all_tasks=read(args.out/"tasks.json")
            tasks=tasks+added;all_tasks[args.engine]=tasks
            write(args.out/"tasks.json",all_tasks)
    lookup_seconds=time.perf_counter()-lookup_start
    missing=[t for t in tasks if t["id"] not in restored]
    timing={"engine":args.engine,"cache_lookup_seconds":lookup_seconds,"cache_hit_takes":len(restored),"synthesis_calls":0,"model_load_seconds":0,"generation_seconds":0}
    if not missing:
        write(args.out/("synth-"+args.engine+".json"),[restored[t["id"]] for t in tasks])
        timing["wall_seconds"]=time.perf_counter()-started
        write(args.out/("synth-timing-"+args.engine+".json"),timing);return
    load_start=time.perf_counter()
    import torch,random
    renderer=load_module("renderer",ROOT/"md-first/render.py")
    torch.set_num_threads(4)
    if args.engine=="pocket":
        from pocket_tts import TTSModel
        model=TTSModel.load_model();sr=model.sample_rate
    elif args.engine=="chatterbox":
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        model=ChatterboxTurboTTS.from_pretrained(device="cpu");sr=model.sr;default=model.conds
    else:
        from kitten_tts_cpp import KittenTTS
        model=KittenTTS("KittenML/kitten-tts-2",decoder="default",threads=4,repack=False);sr=model.sample_rate
    timing["model_load_seconds"]=time.perf_counter()-load_start
    state={};results=[]
    for t in tasks:
        if t["id"] in restored:
            results.append(restored[t["id"]]);continue
        turn_start=time.perf_counter()
        timing["synthesis_calls"]+=1
        line=t["line"]; cfg=t["voice"];key=line["voice_key"];seed=t["seed"]
        item={**t,"status":"failed"}
        path=directory/t["file"]
        if retry and path.exists():raise ValueError("Retry must not overwrite a take")
        path.unlink(missing_ok=True)
        try:
            random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
            text=renderer.spoken_text({**line,"text":line.get("synthesis_text",line["text"])})
            ref=cfg.get("reference_file")
            if ref and sha(pathlib.Path(ref))!=cfg["reference_sha256"]:raise ValueError("Reference changed")
            if not ref and cfg.get("reference_hf"):
                from huggingface_hub import hf_hub_download
                ref=hf_hub_download(repo_id=cfg["reference_hf"]["repo"],filename=cfg["reference_hf"]["filename"])
            if args.engine=="pocket":
                if key not in state:state[key]=model.get_state_for_audio_prompt(ref or cfg["voice"])
                raw=model.generate_audio(state[key],text).detach().cpu().numpy()
            elif args.engine=="chatterbox":
                if ref:
                    if key not in state:model.prepare_conditionals(ref);state[key]=model.conds
                    model.conds=state[key]
                elif cfg["voice"]=="default":model.conds=default
                else:raise ValueError("Missing Chatterbox reference")
                raw=model.generate(text).detach().cpu().numpy()
            else:
                if ref:raise ValueError("Raw Kitten references disabled")
                raw=model.generate(text,voice=cfg["voice"],preset="expressive" if line["emotion"]!="neutral" or line["emphasis"] else "stable",temperature=.8,top_p=1.,top_k=100,min_p=0.,advanced={"seed":seed})
            raw=np.asarray(raw,dtype=np.float32).reshape(-1)
            item["signal"]=signal(raw,sr,line.get("qa_text",line["text"]))
            if item["signal"]["passed"]:
                sf.write(path,raw,sr,subtype="PCM_24")
                item.update(status="generated",sha256=sha(path))
        except Exception as exc:item["error"]=repr(exc)
        results.append(item);write(args.out/(("retry-synth-" if retry else "synth-")+args.engine+".json"),results)
        timing["generation_seconds"]+=time.perf_counter()-turn_start
        print(t["id"],item["status"],item.get("error",""),flush=True)
    write(args.out/(("retry-" if retry else "")+"synth-"+args.engine+".json"),results)
    timing["wall_seconds"]=time.perf_counter()-started
    write(args.out/(("retry-" if retry else "")+"synth-timing-"+args.engine+".json"),timing)
def judge(args):
    started=time.perf_counter()
    timing={"asr_model_load_seconds":0,"speaker_model_load_seconds":0,"asr_seconds":0,"speaker_embedding_seconds":0,"cleanup_seconds":0,"cache_cleaned_hits":0,"mastering_seconds":0,"cache_save_seconds":0,"cache_saved_lines":0}
    from quality import evaluate
    from faster_whisper import WhisperModel
    import torch,torchaudio
    from speechbrain.inference.classifiers import EncoderClassifier
    torch.set_num_threads(4)
    out=args.out;plan=read(out/"plan.json");manifest=read(out/"manifest.json")
    cache=getattr(args,"line_cache",None)
    if cache and manifest.get("demo") is not True:raise ValueError("Line cache is preview only")
    mark=time.perf_counter()
    asr=WhisperModel("small.en",device="cpu",compute_type="int8",cpu_threads=4)
    timing["asr_model_load_seconds"]=time.perf_counter()-mark
    mark=time.perf_counter()
    encoder=EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",savedir=str(out/"speaker-model"),run_opts={"device":"cpu"})
    timing["speaker_model_load_seconds"]=time.perf_counter()-mark
    def embedding(path):
        mark=time.perf_counter()
        x,sr=sf.read(path,dtype="float32")
        if x.ndim==2:x=x.mean(axis=1)
        x=torch.from_numpy(x).unsqueeze(0)
        if sr!=16000:x=torchaudio.functional.resample(x,sr,16000)
        with torch.inference_mode():v=encoder.encode_batch(x).reshape(-1).cpu().numpy()
        if not np.isfinite(v).all() or np.linalg.norm(v)<1e-8:raise ValueError("Invalid speaker embedding")
        timing["speaker_embedding_seconds"]+=time.perf_counter()-mark
        return v/np.linalg.norm(v)
    records=[]
    for engine,tasks in read(out/"tasks.json").items():
        if not tasks:continue
        p=out/("synth-"+engine+".json")
        if not p.is_file():raise RuntimeError("Missing synthesis result "+engine)
        records.extend(read(p))
    references={};selected={};report={"postprocess_version":"1.0","tracks":[],"speaker_model":"ECAPA-TDNN VoxCeleb; similarities are diagnostic, not calibrated identity decisions","publication_allowed":False}
    audio=out/"audio";audio.mkdir(exist_ok=True);failed=False
    cleaned=out/"cleaned";cleaned.mkdir(exist_ok=True)
    def transcribe(path):
        mark=time.perf_counter()
        seg,_=asr.transcribe(str(path),language="en",beam_size=5,temperature=0,condition_on_previous_text=False,word_timestamps=True)
        seg=list(seg)
        timing["asr_seconds"]+=time.perf_counter()-mark
        return " ".join(s.text.strip() for s in seg),[{"word":w.word.strip(),"start":w.start,"end":w.end} for s in seg for w in (s.words or [])]
    for t in plan["tracks"]:
        track={"id":t["id"],"lesson":t["lesson"],"slide":t["slide"],"lines":[],"status":"failed"}
        pieces=[];vectors=[];complete=True
        for suffix in (".wav",".mp3",".premaster.wav"):(audio/(t["id"]+suffix)).unlink(missing_ok=True)
        for i,line in enumerate(t["lines"]):
            candidates=[c for c in records if c["track"]==t["id"] and c["index"]==i]
            for c in candidates:
                if c["status"]!="generated":continue
                try:
                    p=out/"takes"/c["file"]
                    if sha(p)!=c["sha256"]:raise ValueError("Take checksum mismatch")
                    wave,sr=sf.read(p,dtype="float32")
                    transcript,words=transcribe(p)
                    c["qa"]=evaluate(wave,sr,line.get("qa_text",line["text"]),transcript)
                    c["fluency"]=repetition_report(line.get("qa_text",line["text"]),transcript,words)
                    if c["fluency"]["unexpected_repetitions"] and c["qa"]["lexical"]["errors"]:
                        c["qa"]["passed"]=False
                        c["qa"]["reasons"].append("Unexpected spoken repetition; reject rather than cut phonemes")
                    if c["qa"]["passed"]:
                        v=embedding(p)
                        ref=c["voice"].get("reference_file")
                        if ref:
                            key=line["voice_key"]
                            if key not in references:references[key]=embedding(pathlib.Path(ref))
                            c["reference_cosine"]=float(v@references[key])
                except Exception as exc:c["qa"]={"passed":False,"reasons":[repr(exc)]}
            # Rank only raw passing takes. Clean the winner; if cleaning damages
            # speech, try the next already-generated passing take.
            winner=None;cleanpath=None
            while True:
                preferred=[c for c in candidates if c.get("cached_preferred_seed")==c["seed"] and c.get("qa",{}).get("passed") is True]
                trial=select(preferred or candidates,target_wpm=line.get("director",{}).get("target_wpm_for_take_ranking",150))
                if trial is None:break
                try:
                    original=out/"takes"/trial["file"]
                    dest=cleaned/(trial["id"]+".wav")
                    mark=time.perf_counter()
                    cached=trial.get("cached_postprocess")
                    if cached is not None:
                        if not dest.is_file() or sha(dest)!=cached["sha256"]:raise ValueError("Cached cleaned WAV hash mismatch")
                        post=dict(cached);timing["cache_cleaned_hits"]+=1
                    else:post=cleanup(original,dest)
                    timing["cleanup_seconds"]+=time.perf_counter()-mark
                    wave,sr=sf.read(dest,dtype="float32")
                    transcript,words=transcribe(dest)
                    after=evaluate(wave,sr,line.get("qa_text",line["text"]),transcript)
                    trial["postprocess"]={**post,"qa":after,"fluency":repetition_report(line.get("qa_text",line["text"]),transcript,words)}
                    if not after["passed"]:raise ValueError("Cleaned transcript/signal failed")
                    trial["postprocess"]["raw_to_cleaned_cosine"]=float(embedding(original)@embedding(dest))
                    trial["postprocess"]["sha256"]=sha(dest)
                    winner=trial;cleanpath=dest;break
                except Exception as exc:
                    trial.setdefault("postprocess",{})["error"]=repr(exc)
                    trial["qa"]["passed"]=False
                    trial["qa"]["reasons"].append("Postprocessing failed; try next take")
            detail={"speaker":line["speaker"],"voice_key":line["voice_key"],"text":line["text"],"direction":line["direction"],"emotion":line["emotion"],"emphasis":line["emphasis"],"takes":candidates,"selected_seed":winner["seed"] if winner else None}
            if "director" in line:detail["director"]=line["director"];detail["synthesis_text"]=line["synthesis_text"]
            if winner:
                if cache and not any(c.get("cache_hit") for c in candidates):
                    mark=time.perf_counter()
                    identity=line_cache.identity(candidates,t,args.cache_fingerprint)
                    timing["cache_saved_lines"]+=int(line_cache.save(cache,identity,candidates,winner,out))
                    timing["cache_save_seconds"]+=time.perf_counter()-mark
                p=cleanpath
                wave,_=sf.read(p,dtype="float32");pieces.append(wave)
                if i+1<len(t["lines"]):pieces.append(np.zeros(round(24000*line["pause_after_ms"]/1000),dtype=np.float32))
                vectors.append((i,line["speaker"],embedding(p)))
            else:complete=False
            track["lines"].append(detail)
        track["speaker_similarity"]=[{"lines":[a[0],b[0]],"same_expected_speaker":a[1]==b[1],"cosine":float(a[2]@b[2])} for j,a in enumerate(vectors) for b in vectors[j+1:]]
        if complete:
            wav=audio/(t["id"]+".wav");mp3=audio/(t["id"]+".mp3")
            premaster=audio/(t["id"]+".premaster.wav")
            sf.write(premaster,np.concatenate(pieces),24000,subtype="PCM_24")
            try:
                mark=time.perf_counter();track["mastering"]=master(premaster,wav,mp3);timing["mastering_seconds"]+=time.perf_counter()-mark
                track.update(status="technical_pass_pending_listening",file="audio/"+mp3.name,sha256=sha(mp3),seconds=sf.info(wav).duration)
            except Exception as exc:
                track["mastering_error"]=repr(exc);failed=True
                wav.unlink(missing_ok=True);mp3.unlink(missing_ok=True)
        else:failed=True
        report["tracks"].append(track);write(out/"qa-report.json",report)
    manifest.update(status="blocked" if failed else "technical_pass_pending_listening",tracks=[{k:t[k] for k in ("id","lesson","slide","status","file","sha256","seconds") if k in t} for t in report["tracks"]],qa_sha256=sha(out/"qa-report.json"))
    write(out/"manifest.json",manifest)
    timing["wall_seconds"]=time.perf_counter()-started
    write(out/"judge-timing.json",timing)
    if failed:raise SystemExit("Missing acceptable take; no publication")
def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["prepare","synth","judge"]);p.add_argument("--md",type=pathlib.Path);p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"));p.add_argument("--registry",type=pathlib.Path);p.add_argument("--assets",type=pathlib.Path,default=pathlib.Path("refs"));p.add_argument("--demo",action="store_true");p.add_argument("--engine",choices=["pocket","chatterbox","kitten"]);p.add_argument("--retry",action="store_true");p.add_argument("--line-cache",type=pathlib.Path);p.add_argument("--cache-fingerprint");a=p.parse_args()
    if a.mode=="prepare":prepare(a)
    elif a.mode=="synth":synth(a)
    else:judge(a)
if __name__=="__main__":main()
