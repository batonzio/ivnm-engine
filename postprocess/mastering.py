"""Non-destructive speech cleanup and mastering, native timing, FFmpeg CPU only."""
import json, math, pathlib, re, subprocess
import numpy as np
import soundfile as sf

VERSION="1.0"
TARGET_LUFS=-18.0
TARGET_TP=-2.0
def ff(*args,log="error"):
    return subprocess.run(["ffmpeg","-nostdin","-hide_banner","-y","-loglevel",log,*map(str,args)],check=True,capture_output=True,text=True)
def db(x):return 20*math.log10(max(float(x),1e-12))
def measure(path):
    result=ff("-i",path,"-af","loudnorm=I=-18:TP=-2:LRA=7:print_format=json","-f","null","-",log="info")
    blocks=re.findall(r'\{\s*"input_i"\s*:.*?\}',result.stderr,re.S)
    if not blocks:raise RuntimeError("FFmpeg loudness measurement unavailable")
    d=json.loads(blocks[-1])
    def value(key):
        x=float(d[key]);return x if math.isfinite(x) else None
    return {k:value(k) for k in ("input_i","input_tp","input_lra","input_thresh","target_offset","output_i","output_tp")}
def waveform(path):
    x,sr=sf.read(path,dtype="float32")
    if x.ndim!=1 or not len(x) or not np.isfinite(x).all():raise ValueError("Invalid mono waveform")
    return x,sr
def frame_rms(x,sr,ms=10):
    n=max(1,round(sr*ms/1000))
    a=x[:len(x)//n*n].reshape(-1,n)
    return np.sqrt(np.mean(a.astype(np.float64)**2,axis=1)),n
def trim_edges(x,sr):
    # Only near-digital-silence at the edges. Never trim inside a phrase.
    rms,n=frame_rms(x,sr)
    threshold=min(.001,max(.00001,float(np.max(np.abs(x)))*.001))
    active=np.flatnonzero(rms>threshold)
    if not len(active):return x.copy(),{"leading_ms":0,"trailing_ms":0}
    retain=round(.10*sr); maxtrim=round(.35*sr)
    start=min(maxtrim,max(0,int(active[0])*n-retain))
    end=min(maxtrim,max(0,len(x)-(int(active[-1])+1)*n-retain))
    if len(x)-start-end<.3*sr:return x.copy(),{"leading_ms":0,"trailing_ms":0}
    return x[start:len(x)-end if end else len(x)].copy(),{"leading_ms":round(1000*start/sr,2),"trailing_ms":round(1000*end/sr,2)}
def noise_floor(x,sr):
    # Enable mild spectral denoising only when both boundary windows look like
    # quiet stationary noise. This is deliberately conservative, not a classifier.
    n=round(.12*sr)
    if len(x)<sr or n<1:return None
    edges=[x[:n],x[-n:]]
    levels=[db(np.sqrt(np.mean(z.astype(np.float64)**2))) for z in edges]
    if max(levels)>-40 or min(levels)<-72 or abs(levels[0]-levels[1])>4:return None
    for z in edges:
        r,_=frame_rms(z,sr,20)
        if len(r)<4 or np.max(r)>2.2*max(np.min(r),1e-8):return None
    if db(np.max(np.abs(x)))-max(levels)<28:return None
    return round(max(-75,min(-42,sum(levels)/2)),1)
def cleanup(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    x,sr=waveform(src)
    before=measure(src)
    noise=noise_floor(x,sr)
    trimmed,edge=trim_edges(x,sr)
    tmp=dest.with_suffix(".pre.wav");filtered=dest.with_suffix(".filtered.wav")
    try:
        sf.write(tmp,trimmed,sr,subtype="FLOAT")
        filters=["highpass=f=55"]
        if noise is not None:filters.append(f"afftdn=nr=5:nf={noise}")
        # Gentle compression, no gate or speech-rate manipulation.
        filters.append("acompressor=threshold=0.125:ratio=1.5:attack=15:release=150:makeup=1:knee=2.8")
        ff("-i",tmp,"-af",",".join(filters),"-ar","24000","-ac","1","-c:a","pcm_f32le",filtered)
        y,rate=waveform(filtered);rms,_=frame_rms(y,rate,20)
        active=rms[rms>max(.0005,float(np.max(rms,initial=0))*.08)]
        if not len(active):raise ValueError("Cleanup produced near-silence")
        mid=measure(filtered)
        # Use integrated loudness when measurable; short isolated words may have
        # no reliable LUFS reading, so use a conservative active-frame RMS proxy.
        method="integrated_lufs" if mid["input_i"] is not None else "active_rms_proxy"
        level=mid["input_i"] if method=="integrated_lufs" else db(np.sqrt(np.mean(active**2)))
        desired=(-20.0 if method=="integrated_lufs" else -22.0)-level
        gain=max(-9.,min(9.,desired))
        peak=mid["input_tp"] if mid["input_tp"] is not None else db(np.max(np.abs(y)))
        gain=min(gain,-3.0-peak)
        y=y.astype(np.float64)*10**(gain/20)
        # 5 ms endpoint fade, outside the intended speech whenever possible.
        n=min(round(rate*.005),len(y)//2)
        if n:
            y[:n]*=np.linspace(0,1,n);y[-n:]*=np.linspace(1,0,n)
        sf.write(dest,y,rate,subtype="PCM_24")
        after=measure(dest)
        if after["input_tp"] is None or after["input_tp"]>-2.0:raise ValueError("Unsafe line peak after cleanup")
        return {"version":VERSION,"trim":edge,"noise_floor_dbfs":noise,"denoise_applied":noise is not None,"filters":filters,"line_gain_db":round(gain,2),"gain_method":method,"before":before,"after":after,"seconds_before":len(x)/sr,"seconds_after":len(y)/rate,"speed":1.0}
    finally:
        tmp.unlink(missing_ok=True);filtered.unlink(missing_ok=True)
def repetition_report(expected,transcript,words):
    # Report suspicious *additional* repeated words/phrases, not intentional
    # repeats in the script. Exact transcript verification remains mandatory.
    from quality import tokens,edits
    a,b=tokens(expected),tokens(transcript)
    repeats=[]
    for width in (1,2,3):
        for i in range(len(b)-2*width+1):
            phrase=b[i:i+width]
            if phrase!=b[i+width:i+2*width]:continue
            if any(a[j:j+2*width]==phrase+phrase for j in range(len(a)-2*width+1)):continue
            repeats.append({"phrase":" ".join(phrase),"token_index":i,"span_words":width})
    gaps=[]
    for u,v in zip(words,words[1:]):
        if u.get("end") is not None and v.get("start") is not None:
            gap=float(v["start"])-float(u["end"])
            if gap>1.2:gaps.append({"after":u["word"],"before":v["word"],"seconds":round(gap,3)})
    return {"unexpected_repetitions":repeats,"long_internal_pauses":gaps,"word_edits":edits(expected,transcript),"method":"ASR lexical repeats + timestamp gaps; phoneme stutters not guaranteed detectable"}
def master(src,wav,mp3):
    # Two-pass EBU R128 measurement; create WAV first, then encode MP3 from
    # that exact master (previous pipeline normalized only MP3).
    before=measure(src)
    if any(before[k] is None for k in ("input_i","input_tp","input_lra","input_thresh","target_offset")):raise ValueError("Track too short or quiet for reliable integrated loudness")
    attempts=[]
    for ceiling in (-2.5,-3.5):
        filt=(f"loudnorm=I={TARGET_LUFS}:TP={ceiling}:LRA=7:"
              f"measured_I={before['input_i']}:measured_TP={before['input_tp']}:"
              f"measured_LRA={before['input_lra']}:measured_thresh={before['input_thresh']}:"
              f"offset={before['target_offset']}:linear=true:print_format=summary")
        ff("-i",src,"-af",filt,"-ar","24000","-ac","1","-c:a","pcm_s24le",wav)
        ff("-i",wav,"-c:a","libmp3lame","-b:a","128k",mp3)
        wm,mm=measure(wav),measure(mp3)
        attempt={"ceiling":ceiling,"wav":wm,"mp3_decoded":mm};attempts.append(attempt)
        ok=all(m["input_i"] is not None and abs(m["input_i"]-TARGET_LUFS)<=1.5 and m["input_tp"] is not None and m["input_tp"]<=TARGET_TP for m in (wm,mm))
        if ok:
            return {"version":VERSION,"target_lufs":TARGET_LUFS,"target_true_peak_dbtp":TARGET_TP,"before":before,"attempts":attempts,"speed":1.0,"passed":True}
    wav.unlink(missing_ok=True);mp3.unlink(missing_ok=True)
    raise ValueError("Mastering loudness/true-peak gate failed: "+json.dumps(attempts))
