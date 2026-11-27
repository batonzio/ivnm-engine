"""Offline audio handoff contract. Reuse Factory's existing approved asset cache."""
import hashlib
import json
import math
import re
from pathlib import Path

HEX = re.compile(r"[a-f0-9]{64}")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
PASS = "technical_pass_pending_listening"

def digest(value):
    if not isinstance(value,str) or not HEX.fullmatch(value):
        raise ValueError("Invalid SHA-256")
    return value

def identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise ValueError("Invalid track identifier")
    return value

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()

def request_key(track, *, runtime_fingerprints, reference_fingerprints, processing_fingerprint):
    """Hash a resolved production track plus pinned runtime/reference/QA configuration.
    The caller obtains fingerprints from its verified inventory, not from this helper.
    Include runtime, model weights, settings, seed policy and QA versions in those hashes.
    """
    if track.get("status")!="ready" or not track.get("lines") or track.get("options",{}).get("speed")!=1:
        raise ValueError("Unready track or unsupported speed")
    if not isinstance(runtime_fingerprints,dict) or not isinstance(reference_fingerprints,dict):
        raise ValueError("Invalid fingerprint mapping")
    engines=set(); voices=set()
    for line in track["lines"]:
        engine=line.get("engine")
        voice=line.get("voice_key")
        if engine not in {"chatterbox","pocket","kitten"} or not isinstance(voice,str) or line.get("voice_status")!="approved":
            raise ValueError("Unapproved voice or engine")
        engines.add(engine); voices.add(voice)
    if set(runtime_fingerprints)!=engines or set(reference_fingerprints)!=voices:
        raise ValueError("Missing or extra fingerprint")
    for value in [*runtime_fingerprints.values(),*reference_fingerprints.values(),processing_fingerprint]:
        digest(value)
    # Binding is checked separately; identical spoken content may be reused across lessons.
    payload={"schema_version":1,"track":{k:v for k,v in track.items() if k not in ("id","lesson","slide")},
             "runtimes":runtime_fingerprints,"references":reference_fingerprints,"processing":processing_fingerprint}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def file_under(root, relative, limit):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe package root")
    p=root
    for part in relative.split("/"):
        if part in ("",".",".."): raise ValueError("Unsafe package path")
        p=p/part
        if p.is_symlink(): raise ValueError("Symlink forbidden")
    if not p.is_file() or not 0<p.stat().st_size<=limit:
        raise ValueError("Missing or oversized package file")
    return p

def load(path):
    def unique(pairs):
        data={}
        for k,v in pairs:
            if k in data: raise ValueError("Duplicate JSON key")
            data[k]=v
        return data
    def invalid(_): raise ValueError("Nonfinite JSON")
    data=json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=unique,parse_constant=invalid)
    if not isinstance(data,dict): raise ValueError("Expected JSON object")
    return data

def inspect_package(root, *, expected_bindings, minimum_seconds):
    """Validate current production package and explicit review, without publishing or copying.
    expected_bindings maps track IDs to (lesson, slide); minimum_seconds maps IDs to duration.
    This checks byte integrity and metadata, not audio decoding or listening quality.
    """
    if not isinstance(expected_bindings,dict) or not expected_bindings or set(expected_bindings)!=set(minimum_seconds):
        raise ValueError("Explicit expected bindings and durations required")
    manifest_path=file_under(root,"manifest.json",1048576)
    manifest=load(manifest_path)
    if manifest.get("schema")!=1 or manifest.get("demo") is not False or manifest.get("status")!=PASS or manifest.get("publication_allowed") is not False:
        raise ValueError("Unready or demo audio package")
    qa=file_under(root,"qa-report.json",33554432)
    if sha(qa)!=digest(manifest.get("qa_sha256")):
        raise ValueError("QA checksum mismatch")
    qa_data=load(qa)
    if qa_data.get("publication_allowed") is not False:
        raise ValueError("Invalid QA publication guard")
    review=load(file_under(root,"release-review.json",1048576))
    if review.get("manifest_sha256")!=sha(manifest_path) or review.get("listening_approved") is not True or not isinstance(review.get("reviewer"),str) or not review["reviewer"].strip():
        raise ValueError("Missing or stale listening review")
    reviewed=review.get("tracks")
    if not isinstance(reviewed,dict) or set(reviewed)!=set(expected_bindings):
        raise ValueError("Review track set mismatch")
    tracks=manifest.get("tracks")
    if not isinstance(tracks,list) or len(tracks)!=len(expected_bindings):
        raise ValueError("Unexpected track count")
    qa_tracks=qa_data.get("tracks")
    if not isinstance(qa_tracks,list) or len(qa_tracks)!=len(tracks):
        raise ValueError("QA track count mismatch")
    qa_by_id={}
    for record in qa_tracks:
        if not isinstance(record,dict): raise ValueError("Invalid QA track")
        key=identifier(record.get("id"))
        if key in qa_by_id: raise ValueError("Duplicate QA track")
        qa_by_id[key]=record
    if set(qa_by_id)!=set(expected_bindings): raise ValueError("QA track set mismatch")
    seen=set(); bindings=set(); result=[]
    for t in tracks:
        key=identifier(t.get("id"))
        if key in seen or key not in expected_bindings: raise ValueError("Unexpected or duplicate track")
        seen.add(key)
        binding=(t.get("lesson"),t.get("slide"))
        if any(not isinstance(v,str) or not v.strip() for v in binding) or binding!=tuple(expected_bindings[key]) or binding in bindings:
            raise ValueError("Incorrect or duplicate binding")
        bindings.add(binding)
        if t.get("status")!=PASS or t.get("file")!="audio/"+key+".mp3":
            raise ValueError("Unpassed track or invalid path")
        seconds=t.get("seconds"); minimum=minimum_seconds[key]
        if any(type(v) not in (int,float) or not 0<v<=86400 or not math.isfinite(v) for v in (seconds,minimum)) or seconds<minimum:
            raise ValueError("Audio duration below requirement")
        q=qa_by_id[key]
        if any(q.get(field)!=t.get(field) for field in ("id","lesson","slide","status","file","sha256","seconds")):
            raise ValueError("QA track disagrees with manifest")
        lines=q.get("lines")
        if not isinstance(lines,list) or not lines or any(not isinstance(line,dict) or type(line.get("selected_seed")) is not int for line in lines):
            raise ValueError("Missing selected QA take")
        p=file_under(root,t["file"],67108864)
        checksum=digest(t.get("sha256"))
        if sha(p)!=checksum or reviewed[key]!=checksum:
            raise ValueError("Audio checksum or review mismatch")
        result.append({"id":key,"lesson":binding[0],"slide":binding[1],"file":t["file"],
                       "sha256":checksum,"seconds":seconds,"bytes":p.stat().st_size})
    return {"schema_version":1,"status":"REVIEW_RECORD_VERIFIED","tracks":result,
            "reviewer":review["reviewer"],"manifest_sha256":sha(manifest_path),"publication_allowed":False}
