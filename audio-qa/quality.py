"""Conservative technical audio and transcript gates; not a listening-quality judge."""
import math, re, unicodedata
import numpy as np

def tokens(text):
    text=unicodedata.normalize("NFKC",text).casefold().replace("’","'")
    words=re.findall(r"[a-z0-9]+(?:'[a-z]+)?",text)
    expansions={"i'm":["i","am"],"it's":["it","is"],"we're":["we","are"],"they're":["they","are"],"you're":["you","are"],"don't":["do","not"],"didn't":["did","not"],"can't":["can","not"],"couldn't":["could","not"],"won't":["will","not"],"that's":["that","is"],"i've":["i","have"],"we've":["we","have"],"i'll":["i","will"],"we'll":["we","will"]}
    return [token for word in words for token in expansions.get(word,[word])]

def edits(reference,hypothesis):
    a,b=tokens(reference),tokens(hypothesis)
    # edit distance with explicit substitution/deletion/insertion counts
    dp=[[(0,0,0,0) for _ in range(len(b)+1)] for _ in range(len(a)+1)]
    for i in range(1,len(a)+1): dp[i][0]=(i,0,i,0)
    for j in range(1,len(b)+1): dp[0][j]=(j,0,0,j)
    def add(v,k):
        x=list(v);x[0]+=1;x[k]+=1;return tuple(x)
    for i in range(1,len(a)+1):
        for j in range(1,len(b)+1):
            dp[i][j]=dp[i-1][j-1] if a[i-1]==b[j-1] else min(add(dp[i-1][j-1],1),add(dp[i-1][j],2),add(dp[i][j-1],3))
    n,s,d,ins=dp[-1][-1]
    return {"reference_words":len(a),"hypothesis_words":len(b),"errors":n,"substitutions":s,"deletions":d,"insertions":ins,"wer":n/max(1,len(a))}

def signal(wave,sr,text):
    wave=np.asarray(wave,dtype=np.float32)
    reasons=[]
    if sr<=0 or wave.ndim!=1 or not wave.size or not np.isfinite(wave).all():
        return {"passed":False,"reasons":["empty, non-finite or non-mono waveform"]}
    sec=wave.size/sr; words=max(1,len(tokens(text)))
    peak=float(np.max(np.abs(wave))); rms=float(np.sqrt(np.mean(wave**2)))
    clipped=float(np.mean(np.abs(wave)>=.999))
    wpm=60*words/sec
    if sec<max(.3,.14*words): reasons.append("duration below conservative speech floor")
    if sec>max(5.,1.2*words+2.): reasons.append("duration above conservative speech ceiling")
    if peak<.001 or rms<.0001: reasons.append("near-silent signal")
    if clipped>.01: reasons.append("excessive clipping")
    # This metric is a heuristic, not a speech detector.
    frame=max(1,int(sr*.025)); frames=wave[:wave.size//frame*frame].reshape(-1,frame)
    active=float(np.mean(np.sqrt(np.mean(frames**2,axis=1))>max(.0005,peak*.01))) if len(frames) else 0.
    if active<.12: reasons.append("mostly inactive signal")
    return {"passed":not reasons,"reasons":reasons,"seconds":sec,"peak":peak,"rms":rms,"clipped_fraction":clipped,"active_fraction":active,"wpm":wpm,"sample_rate":sr}

def evaluate(wave,sr,expected,transcript):
    technical=signal(wave,sr,expected); lexical=edits(expected,transcript)
    # Strict default: no recognized missing, added or changed words.
    reasons=list(technical["reasons"])
    if lexical["errors"]: reasons.append("ASR transcript mismatch")
    return {"passed":not reasons,"reasons":reasons,"signal":technical,"transcript":transcript,"lexical":lexical,"listening_review_required":True}

def select(candidates,target_wpm=150):
    valid=[c for c in candidates if c.get("qa",{}).get("passed")]
    if not valid:return None
    # Only technical tie-breaks. Do not equate these with naturalness or accent.
    return min(valid,key=lambda c:(c["qa"]["lexical"]["errors"],c["qa"]["signal"]["clipped_fraction"],abs(c["qa"]["signal"]["wpm"]-target_wpm),-c["qa"]["signal"]["active_fraction"],c["seed"]))
