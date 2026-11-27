"""Reconstruct existing dialogue boundaries, validate selected WAV hashes, and compare ASR.
Read-only diagnostics: no synthesis, new voices, publication, or perceptual pass claims.
"""
import argparse,hashlib,json,pathlib,time,sys
import numpy as np
import soundfile as sf
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"audio-qa"))
from quality import edits
from continuity import features
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def load(p,h=None):
    if h is not None and sha(p)!=h:raise ValueError("Audio hash mismatch")
    x,sr=sf.read(p,dtype="float32")
    if x.ndim!=1 or sr!=24000 or not len(x) or not np.isfinite(x).all():raise ValueError("Expected mono 24 kHz audio")
    return x
def energy(x):
    return float(20*np.log10(max(1e-10,np.sqrt(np.mean(x.astype(np.float64)**2)))))
def edge_ms(x,reverse=False):
    if reverse:x=x[::-1]
    frame=240
    if len(x)<frame:return 0
    frames=x[:len(x)//frame*frame].reshape(-1,frame)
    rms=np.sqrt(np.mean(frames.astype(np.float64)**2,axis=1))
    threshold=max(1e-5,float(rms.max())*.015)
    active=np.flatnonzero(rms>threshold)
    return int(active[0]*10) if len(active) else int(len(frames)*10)
def inspect(root,label):
    plan=read(root/"plan.json");qa=read(root/"qa-report.json");manifest=read(root/"manifest.json")
    if manifest.get("qa_sha256")!=sha(root/"qa-report.json") or manifest.get("publication_allowed") is not False:raise ValueError("Unbound QA")
    rows=[]
    for track in plan["tracks"]:
        report=next(q for q in qa["tracks"] if q["id"]==track["id"])
        if report["status"]!="technical_pass_pending_listening" or len(report["lines"])!=len(track["lines"]):raise ValueError("Unaccepted technical track")
        selected=[];pieces=[];texts=[];seams=[]
        for i,(line,q) in enumerate(zip(track["lines"],report["lines"])):
            if q["text"]!=line["text"] or q["voice_key"]!=line["voice_key"]:raise ValueError("Line binding mismatch")
            winner=next(c for c in q["takes"] if c["seed"]==q["selected_seed"])
            if pathlib.Path(winner["file"]).name!=winner["file"]:raise ValueError("Invalid take name")
            if not winner["qa"]["passed"] or not winner["postprocess"]["qa"]["passed"]:raise ValueError("Rejected take")
            if winner["qa"]["lexical"]["errors"] or winner["postprocess"]["qa"]["lexical"]["errors"]:raise ValueError("Transcript failed")
            raw=root/"takes"/winner["file"]
            if sha(raw)!=winner["sha256"]:raise ValueError("Raw hash mismatch")
            clean=root/"cleaned"/winner["file"];x=load(clean,winner["postprocess"]["sha256"])
            selected.append({"speaker":line["speaker"],"voice_key":line["voice_key"],"raw_sha256":winner["sha256"],"clean_sha256":winner["postprocess"]["sha256"],"seconds":len(x)/24000,"rms_dbfs":energy(x),"leading_ms":edge_ms(x),"trailing_ms":edge_ms(x,True),"continuity":features(x,24000)})
            pieces.append(x);texts.append(line.get("qa_text",line["text"]))
            if i+1<len(track["lines"]):
                pause=round(24000*line["pause_after_ms"]/1000)
                pieces.append(np.zeros(pause,dtype=np.float32))
        for i in range(len(selected)-1):
            a,b=selected[i:i+2];x,y=pieces[2*i],pieces[2*i+2]
            seams.append({"lines":[i,i+1],"same_speaker":a["speaker"]==b["speaker"],"planned_pause_ms":track["lines"][i]["pause_after_ms"],"estimated_low_energy_gap_ms":a["trailing_ms"]+track["lines"][i]["pause_after_ms"]+b["leading_ms"],"whole_line_rms_difference_db":abs(a["rms_dbfs"]-b["rms_dbfs"]),"boundary_peak_jump":max(abs(float(x[-1])),abs(float(y[0])))})
        premaster=load(root/"audio"/(track["id"]+".premaster.wav"))
        expected=np.concatenate(pieces)
        if premaster.shape!=expected.shape or np.max(np.abs(premaster-expected))>2e-7:raise ValueError("Premaster differs from verified line assembly")
        audio=root/report["file"]
        if sha(audio)!=report["sha256"]:raise ValueError("Mastered MP3 checksum mismatch")
        rows.append({"label":label,"id":track["id"],"audio_sha256":report["sha256"],"premaster_exact":True,"selected":selected,"seams":seams,"speaker_similarity":report["speaker_similarity"],"expected":" ".join(texts),"audio_path":str(audio)})
    return rows
def main():
    p=argparse.ArgumentParser();p.add_argument("pocket",type=pathlib.Path);p.add_argument("chatterbox",type=pathlib.Path);p.add_argument("out",type=pathlib.Path);a=p.parse_args()
    start=time.perf_counter();rows=inspect(a.pocket,"Pocket") + inspect(a.chatterbox,"Chatterbox");waveform_seconds=time.perf_counter()-start
    from faster_whisper import WhisperModel
    start=time.perf_counter();model=WhisperModel("small.en",device="cpu",compute_type="int8",cpu_threads=4);load_seconds=time.perf_counter()-start
    for row in rows:
        row["asr_ab"]=[]
        for vad in (False,True):
            start=time.perf_counter()
            segments,_=model.transcribe(row["audio_path"],language="en",beam_size=5,temperature=0,condition_on_previous_text=False,word_timestamps=True,vad_filter=vad)
            text=" ".join(s.text.strip() for s in segments)
            row["asr_ab"].append({"vad":vad,"wall_seconds":time.perf_counter()-start,"transcript":text,"lexical":edits(row["expected"],text)})
        del row["audio_path"]
    a.out.write_text(json.dumps({"schema":1,"status":"diagnostics_pending_listening","publication_allowed":False,"waveform_seconds":waveform_seconds,"asr_model_load_seconds":load_seconds,"tracks":rows},indent=2))
    for row in rows:print(json.dumps({"label":row["label"],"premaster_exact":row["premaster_exact"],"seams":row["seams"],"asr_ab":row["asr_ab"]}))
if __name__=="__main__":main()
