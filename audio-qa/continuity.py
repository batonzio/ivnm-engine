"""Experimental waveform continuity features. Not a validated stutter detector."""
import argparse, hashlib, json, pathlib
import numpy as np
def features(x,sr):
    x=np.asarray(x,dtype=np.float64)
    if x.ndim!=1 or not len(x) or not np.isfinite(x).all() or sr<8000:raise ValueError("Invalid mono audio")
    n=round(sr*.010);rms=np.sqrt(np.mean(x[:len(x)//n*n].reshape(-1,n)**2,axis=1))
    if not len(rms) or rms.max()<1e-6:return {"status":"insufficient_signal"}
    # Detect bounded low-energy gaps, not silence at either edge.
    active=rms>max(1e-5,float(rms.max())*.015)
    gaps=[];i=0
    while i<len(active):
        if active[i]:i+=1;continue
        j=i
        while j<len(active) and not active[j]:j+=1
        if i>0 and j<len(active) and 3<=j-i<=25:
            gaps.append({"start_s":round(i*n/sr,3),"duration_ms":round((j-i)*n*1000/sr)})
        i=j
    # Exact-like repeated 80 ms waveforms: a conservative digital-repeat
    # feature, not phoneme recognition. Exclude low energy and constant tones.
    win=round(sr*.08);step=round(sr*.04);repeats=[]
    for i in range(0,max(0,len(x)-2*win+1),step):
        a=x[i:i+win];b=x[i+win:i+2*win]
        a=a-a.mean();b=b-b.mean()
        na=np.linalg.norm(a);nb=np.linalg.norm(b)
        if min(na,nb)<rms.max()*np.sqrt(win)*.06:continue
        # Reject sustained narrowband periodic tones.
        power=np.abs(np.fft.rfft(a*np.hanning(win)))**2
        if power.sum()==0 or np.sort(power)[-5:].sum()/power.sum()>.85:continue
        corr=float(np.dot(a,b)/(na*nb))
        if corr>.985 and .8<na/nb<1.25:repeats.append({"start_s":round(i/sr,3),"correlation":round(corr,4)})
    # Spectral flux between active frames, a descriptive feature only.
    w=round(sr*.025);hop=round(sr*.010)
    prev=None;flux=[]
    for i in range(0,max(0,len(x)-w+1),hop):
        z=x[i:i+w]
        if np.sqrt(np.mean(z*z))<rms.max()*.03:prev=None;continue
        v=np.abs(np.fft.rfft(z*np.hanning(w)));v=v/(np.linalg.norm(v)+1e-12)
        if prev is not None:flux.append(float(np.linalg.norm(v-prev)))
        prev=v
    return {"status":"diagnostic_only","seconds":round(len(x)/sr,3),"bounded_low_energy_gaps":gaps,"near_duplicate_waveform_windows":repeats,"active_spectral_flux_p95":float(np.percentile(flux,95)) if flux else None,"warning":"Normal stops, hesitations and articulation can produce these features; no rejection or naturalness score."}
def audit(sources,out):
    import soundfile as sf
    rows=[]
    for label,root in sources:
        report=json.loads((root/"qa-report.json").read_text())
        for track in report["tracks"]:
            for i,line in enumerate(track["lines"]):
                if line["speaker"]!="Lucy":continue
                for c in line["takes"]:
                    if c["status"]!="generated":continue
                    path=root/"takes"/c["file"]
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=c["sha256"]:raise ValueError("Take checksum mismatch")
                    x,sr=sf.read(path,dtype="float32")
                    rows.append({"engine":label,"line":i,"seed":c["seed"],"selected":c["seed"]==line["selected_seed"],"sha256":c["sha256"],"features":features(x,sr)})
    assert len(rows)==12,len(rows)
    out.write_text(json.dumps({"schema":1,"status":"uncalibrated_diagnostics","user_preferred":"pocket","takes":rows},indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("pocket",type=pathlib.Path);p.add_argument("chatterbox",type=pathlib.Path);p.add_argument("out",type=pathlib.Path);a=p.parse_args();audit([("pocket",a.pocket),("chatterbox",a.chatterbox)],a.out)
