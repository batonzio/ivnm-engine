"""Versioned reusable resource metadata, on the existing Memory interface."""
import json
import re
from .memory import identifier, text_field

KINDS = {"image", "audio", "text", "worksheet", "lesson"}
LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}

def _validate(data):
    fields = {"schema_version","resource_id","course_key","kind","title","description","tags",
              "levels","sha256","license","attribution","source"}
    if not isinstance(data,dict) or set(data)!=fields or type(data["schema_version"]) is not int or data["schema_version"]!=1:
        raise ValueError("Invalid resource contract")
    identifier(data["resource_id"]); identifier(data["course_key"])
    if data["kind"] not in KINDS: raise ValueError("Invalid resource kind")
    for key,limit in (("title",200),("description",2000),("license",100),("attribution",1000),("source",1000)):
        text_field(data[key],limit)
    if not isinstance(data["sha256"],str) or not re.fullmatch(r"[a-f0-9]{64}",data["sha256"]):
        raise ValueError("Invalid asset checksum")
    for key in ("tags","levels"):
        values=data[key]
        if not isinstance(values,list) or len(values)>30 or any(not isinstance(v,str) or not v.strip() or len(v)>80 for v in values):
            raise ValueError("Invalid metadata list")
        if len(set(values))!=len(values): raise ValueError("Duplicate metadata")
    if not set(data["levels"])<=LEVELS: raise ValueError("Invalid CEFR level")
    return data

def register(memory, scope, data, *, expected_revision, status="draft"):
    """Only trusted caller may approve reuse; no license is automatically approved."""
    _validate(data)
    key=identifier(data["course_key"]+".res."+data["resource_id"])
    return memory.put(scope,"resource",key,data["title"],
                      json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":")),
                      status=status,expected_revision=expected_revision)

def candidates(memory, scope, *, allowed_licenses, course_key=None, kind=None, level=None):
    """Return approved, authorized metadata; never download or copy the asset."""
    if not isinstance(allowed_licenses,(list,tuple,set)) or not allowed_licenses:
        raise ValueError("Explicit reuse license policy required")
    for value in allowed_licenses: text_field(value,100)
    if course_key is not None: identifier(course_key)
    if kind is not None and kind not in KINDS: raise ValueError("Invalid resource kind")
    if level is not None and level not in LEVELS: raise ValueError("Invalid level")
    result=[]
    for row in memory.current(scope,kind="resource"):
        if ".res." not in row["key"]: continue
        data=_validate(json.loads(row["content"]))
        if row["key"]!=data["course_key"]+".res."+data["resource_id"]:
            raise ValueError("Resource key mismatch")
        if data["license"] not in allowed_licenses: continue
        if course_key is not None and data["course_key"]!=course_key: continue
        if kind is not None and data["kind"]!=kind: continue
        if level is not None and level not in data["levels"]: continue
        result.append({**data,"scope":row["scope"],"revision":row["revision"],
                       "metadata_digest":row["digest"]})
    return result

def reusable_bytes(rows):
    """Group metadata pointing to identical bytes; keep attribution and rights separate."""
    groups={}
    for row in rows:
        groups.setdefault(row["sha256"],[]).append(row)
    return groups
