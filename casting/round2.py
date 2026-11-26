"""Generate fictional voice references and audition them through Chatterbox Turbo."""
import argparse, json, pathlib, random, subprocess, time
import numpy as np
import soundfile as sf
import torch

ROOT=pathlib.Path(__file__).resolve().parents[1]
BANK=json.loads((ROOT/"voice/voice-bank.json").read_text())
REFERENCE="Hi! I've just got back from the library. I thought we could meet outside the house at half past ten."
LINES=["Oh, really? I thought the exhibition was tomorrow!", "That's great news. Shall we go out for lunch afterwards?", "I was about to call you. Could you show me the route to the town centre?"]

def save(data,sr,path):
    data=np.asarray(data,dtype=np.float32).reshape(-1)
    if not np.isfinite(data).all() or len(data)<sr//2 or np.max(np.abs(data))<0.001:
        raise RuntimeError("Invalid waveform")
    sf.write(path,data,sr,subtype="PCM_24")
    subprocess.run(["ffmpeg","-nostdin","-y","-loglevel","error","-i",str(path),"-c:a","libmp3lame","-b:a","192k",str(path.with_suffix(".mp3"))],check=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=["design","chatterbox"])
    p.add_argument("category",choices=sorted(BANK["slots"]))
    p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out"))
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    slot=BANK["slots"][args.category]
    torch.set_num_threads(4)
    age=slot["perceived_age"]
    accent="contemporary mainstream southern British English" if args.category.startswith("UK") else "mainstream Canadian English"
    report_path=args.out/(args.mode+"-report.json")
    report={"category":args.category,"mode":args.mode,"status":"candidate_only","source":"synthetic Qwen3 VoiceDesign; no real-person voice recording","reference_model":"Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign","reference_model_license":"Apache-2.0","samples":[]}
    if args.mode=="design":
        from qwen_tts import Qwen3TTSModel
        model=Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",device_map="cpu",dtype=torch.float32,attn_implementation="eager")
    else:
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        model=ChatterboxTurboTTS.from_pretrained(device="cpu")
    for n,seed in enumerate((101,202),1):
        name=f"{args.category}-{n:02d}"
        reference=args.out/(name+"-ref.wav")
        item={"id":name,"seed":seed,"status":"pending","target":slot,"text":REFERENCE if args.mode=="design" else LINES}
        try:
            random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
            if args.mode=="design":
                variation="a clear, relaxed, bright timbre" if n==1 else "a warm, smooth, slightly softer timbre"
                prompt=f"A fictional {slot['gender']} speaker, sounding {age} years old, speaking {accent}, with {variation}. Natural conversational delivery, precise articulation, normal pace, no rasp, growl, metallic or nasal quality. Age-appropriate, not an impression of any real person."
                wavs,sr=model.generate_voice_design(text=REFERENCE,language="English",instruct=prompt,max_new_tokens=512)
                save(wavs[0],sr,reference)
                item["prompt"]=prompt
                item["file"]=reference.name
            else:
                if not reference.is_file(): raise FileNotFoundError(str(reference))
                pieces=[]
                for i,text in enumerate(LINES,1):
                    audio=model.generate(text,audio_prompt_path=str(reference)).detach().cpu().numpy().reshape(-1)
                    save(audio,model.sr,args.out/f"{name}-line{i}.wav")
                    pieces.extend([audio,np.zeros(round(model.sr*.32),dtype=np.float32)])
                save(np.concatenate(pieces[:-1]),model.sr,args.out/f"{name}-audition.wav")
                item["file"]=name+"-audition.wav"
            item["status"]="pending_listening_review"
        except Exception as e:
            item.update(status="failed",error=repr(e))
            print(name,repr(e),flush=True)
        report["samples"].append(item)
        report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(name,item["status"],flush=True)
    if any(i["status"]=="failed" for i in report["samples"]): raise SystemExit("Incomplete audition; inspect report. Existing samples preserved.")
if __name__=="__main__": main()
