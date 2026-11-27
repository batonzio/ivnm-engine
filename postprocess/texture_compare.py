"""Audition minimally processed and softened alternatives using identical existing takes.
No TTS, no voice substitution, no destructive filtering or production publication."""
import argparse, hashlib, json, pathlib, tempfile
import numpy as np
import soundfile as sf
from mastering import ff,measure
PROFILES={"B-natural":"highpass=f=45","C-soft":"highpass=f=45,equalizer=f=3500:t=q:w=0.8:g=-1.8,highshelf=f=6500:g=-2.0"}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode(src,dest,gain):
    ff("-i",src,"-af",f"volume={gain}dB","-c:a","libmp3lame","-b:a","128k",dest)
def build(source,dest):
    dest.mkdir(parents=True,exist_ok=True)
    qa=read(source/"qa-report.json");plan=read(source/"plan.json")
    assert len(qa["tracks"])==len(plan["tracks"])==1
    track=qa["tracks"][0];p=plan["tracks"][0]
    assert track["status"]=="technical_pass_pending_listening" and track["id"]==p["id"]
    assert len(track["lines"])==len(p["lines"])
    baseline=source/"audio"/(track["id"]+".wav")
    original=source/track["file"];assert sha(original)==track["sha256"]
    results={}
    with tempfile.TemporaryDirectory() as tmp:
        work=pathlib.Path(tmp)
        for profile,chain in PROFILES.items():
            pieces=[];lines=[]
            for i,(line,pl) in enumerate(zip(track["lines"],p["lines"])):
                assert line["text"]==pl["text"] and line["voice_key"]==pl["voice_key"]
                c=next(c for c in line["takes"] if c["seed"]==line["selected_seed"])
                raw=source/"takes"/c["file"];assert sha(raw)==c["sha256"]
                filtered=work/"filtered.wav"
                ff("-i",raw,"-af",chain,"-ar",24000,"-ac",1,"-c:a","pcm_f32le",filtered)
                x,sr=sf.read(filtered,dtype="float32");m=measure(filtered)
                assert m["input_i"] is not None and m["input_tp"] is not None
                gain=min(12.,max(-12.,-20-m["input_i"]),-3.5-m["input_tp"])
                x=x.astype("float64")*10**(gain/20)
                n=min(round(sr*.012),len(x)//2)
                if n:
                    ramp=.5-.5*np.cos(np.linspace(0,np.pi,n));x[:n]*=ramp;x[-n:]*=ramp[::-1]
                pieces.append(x);lines.append({"speaker":line["speaker"],"source_sha256":c["sha256"],"gain_db":round(gain,2)})
                if i<len(p["lines"])-1:pieces.append(np.zeros(round(sr*pl["pause_after_ms"]/1000)))
            pre=work/"pre.wav";sf.write(pre,np.concatenate(pieces),24000,subtype="PCM_24")
            m=measure(pre);gain=min(-18-m["input_i"],-2.8-m["input_tp"])
            wav=dest/(profile+".wav")
            ff("-i",pre,"-af",f"volume={gain}dB","-c:a","pcm_s24le",wav)
            mp3=dest/(profile+".mp3");encode(wav,mp3,0)
            results[profile]={"filters":chain,"lines":lines,"wav":measure(wav),"mp3":measure(mp3),"speed":1.0}
        # Match baseline to the softer versions for a fair listening test.
        target=min(v["mp3"]["input_i"] for v in results.values())
        a=dest/"A-matched.mp3"
        initial=measure(original)["input_i"];encode(baseline,a,target-initial)
        results["A-matched"]={"mp3":measure(a),"description":"v1.0 master, gain matched"}
        assert max(v["mp3"]["input_i"] for v in results.values())-min(v["mp3"]["input_i"] for v in results.values())<=.6
        assert all(v["mp3"]["input_tp"]<=-2 for v in results.values())
    (dest/"texture-report.json").write_text(json.dumps({"status":"experimental_listening_required","publication_allowed":False,"profiles":results},indent=2))
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("source",type=pathlib.Path);a.add_argument("output",type=pathlib.Path);args=a.parse_args();build(args.source,args.output)
