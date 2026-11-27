"""Local lexical and semantic ranking. No implicit cloud or model download."""
import json
import math
import re
from .transport import EngineError, post_json, require_text

def _tokens(text):
    return set(re.findall(r"[^\W_]+",text.casefold()))

def _limit(limit):
    if type(limit) is not int or not 1<=limit<=100: raise ValueError("Invalid result limit")

def _rank(rows, score, limit):
    ranked=[]
    for row in rows:
        value=score(row)
        if value is not None:
            ranked.append({"resource":row,"score":value})
    return sorted(ranked,key=lambda r:(-r["score"],r["resource"]["metadata_digest"]))[:limit]

def lexical(query, rows, *, limit=10):
    _limit(limit)
    q=_tokens(require_text(query,2000))
    if not q: raise ValueError("Empty search terms")
    def score(row):
        title=_tokens(row["title"]+" "+" ".join(row["tags"]))
        body=_tokens(row["description"])
        value=(2*len(q&title)+len(q&body))/(3*len(q))
        return value if value else None
    return {"schema_version":1,"mode":"lexical","matches":_rank(rows,score,limit)}

def _model(model):
    if not isinstance(model,str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}",model) or "cloud" in model.lower():
        raise ValueError("Explicit local embedding model required")
    return model

def _fingerprint(value):
    if not isinstance(value,str) or not re.fullmatch(r"[a-f0-9]{64}",value):
        raise ValueError("Model fingerprint required")
    return value

def _vector(values):
    if not isinstance(values,(list,tuple)) or not 1<=len(values)<=4096:
        raise ValueError("Invalid vector dimensions")
    if any(type(x) not in (int,float) or abs(x)>1e100 or not math.isfinite(x) for x in values):
        raise ValueError("Invalid vector values")
    norm=math.hypot(*values)
    if not norm: raise ValueError("Zero vector")
    return [x/norm for x in values]

def embed(text, *, model, fingerprint, port=11434, timeout=60):
    """Fingerprint is supplied by the trusted caller from its pinned model inventory."""
    _model(model); _fingerprint(fingerprint); require_text(text,10000)
    body=json.dumps({"model":model,"input":text,"truncate":False},ensure_ascii=False).encode()
    raw=post_json(port,"/api/embed",body,"application/json",timeout)
    vectors=raw.get("embeddings")
    if not isinstance(vectors,list) or len(vectors)!=1:
        raise EngineError("Invalid embedding response")
    try: vector=_vector(vectors[0])
    except ValueError: raise EngineError("Invalid embedding vector") from None
    return {"model":model,"fingerprint":fingerprint,"vector":vector}

def semantic(query_embedding, rows, index, *, limit=10):
    """Index maps metadata_digest to an embedding; stale or missing entries are reported."""
    _limit(limit)
    model=_model(query_embedding["model"]); fingerprint=_fingerprint(query_embedding["fingerprint"])
    q=_vector(query_embedding["vector"])
    missing=[]
    def score(row):
        digest=row["metadata_digest"]
        entry=index.get(digest)
        if entry is None or entry.get("model")!=model or entry.get("fingerprint")!=fingerprint:
            missing.append(digest); return None
        v=_vector(entry["vector"])
        if len(v)!=len(q): raise ValueError("Embedding dimension mismatch")
        return max(-1.0,min(1.0,math.fsum(a*b for a,b in zip(q,v))))
    matches=_rank(rows,score,limit)
    return {"schema_version":1,"mode":"semantic","matches":matches,"unindexed":missing,
            "complete":not missing}
