"""Deterministic, bounded context selection. No AI call, embeddings or network."""
import json
from .memory import identifier

def build(memory, scope, *, required_standards, course_key, budget=30000):
    identifier(scope); identifier(course_key)
    if not isinstance(required_standards,(list,tuple)) or not required_standards:
        raise ValueError("Explicit required standards needed")
    if len(set(required_standards)) != len(required_standards):
        raise ValueError("Duplicate standard key")
    for key in required_standards: identifier(key)
    if type(budget) is not int or not 1000 <= budget <= 40000:
        raise ValueError("Invalid context budget")
    rows = memory.current(scope)
    def select(kind,key):
        matches = [r for r in rows if r["kind"]==kind and r["key"]==key]
        if len(matches)!=1:
            raise ValueError("Missing or ambiguous approved " + kind + ": " + key)
        return matches[0]
    mandatory = [select("standard",k) for k in required_standards]
    mandatory.append(select("course",course_key))
    progress = [r for r in rows if r["kind"]=="progress" and r["key"]==course_key and r["scope"]==scope]
    mandatory.extend(progress)
    # Optional material must belong to this course explicitly. Do not pull unrelated classes.
    course_keys={r["key"] for r in rows if r["kind"]=="course"}
    def belongs(r):
        if r["kind"]=="resource" and ".res." in r["key"]:
            data=json.loads(r["content"])
            if not isinstance(data,dict) or not isinstance(data.get("course_key"),str) or not isinstance(data.get("resource_id"),str):
                raise ValueError("Invalid resource context record")
            if r["key"]!=data["course_key"]+".res."+data["resource_id"]:
                raise ValueError("Resource context key mismatch")
            return data["course_key"]==course_key
        owners=[k for k in course_keys if r["key"].startswith(k+".")]
        return bool(owners) and max(owners,key=len)==course_key
    optional = [r for r in rows if r["kind"] in ("decision","resource") and belongs(r)]
    def projection(r):
        return {k:r[k] for k in ("scope","kind","key","revision","title","content","digest")}
    selected = [projection(r) for r in mandatory]
    def encode(records):
        return json.dumps({"schema_version":1,"records":records},ensure_ascii=False,separators=(",",":"))
    if len(encode(selected))>budget:
        raise ValueError("Required context exceeds budget")
    omitted=[]
    for r in optional:
        candidate=selected+[projection(r)]
        if len(encode(candidate))<=budget: selected=candidate
        else: omitted.append({"scope":r["scope"],"kind":r["kind"],"key":r["key"],"revision":r["revision"]})
    return {"schema_version":1,"context":encode(selected),
            "included":[{k:r[k] for k in ("scope","kind","key","revision","digest")} for r in selected],
            "omitted":omitted,"progress_known":bool(progress)}
