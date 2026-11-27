"""Draft course sequence from explicit pedagogical targets, without inventing progress."""
from .memory import identifier, text_field

def plan(course_key, units, *, lesson_minutes, max_lessons, mastered=()):
    identifier(course_key)
    if type(lesson_minutes) is not int or not 15<=lesson_minutes<=120:
        raise ValueError("Invalid lesson duration")
    if type(max_lessons) is not int or not 1<=max_lessons<=200:
        raise ValueError("Invalid lesson capacity")
    if not isinstance(units,(list,tuple)) or not units or len(units)>100:
        raise ValueError("Invalid unit list")
    if not isinstance(mastered,(list,tuple,set)) or any(not isinstance(x,str) for x in mastered):
        raise ValueError("Explicit mastery list required")
    known=set(mastered)
    for key in known: identifier(key)
    seen=set(); normalized=[]
    for u in units:
        if not isinstance(u,dict) or set(u)!={"id","title","lessons","prerequisites"}:
            raise ValueError("Invalid unit contract")
        key=identifier(u["id"])
        if key in seen: raise ValueError("Duplicate unit")
        seen.add(key); text_field(u["title"],200)
        if type(u["lessons"]) is not int or not 1<=u["lessons"]<=20:
            raise ValueError("Invalid unit duration")
        pre=u["prerequisites"]
        if not isinstance(pre,list) or any(not isinstance(x,str) for x in pre) or len(set(pre))!=len(pre):
            raise ValueError("Invalid prerequisites")
        for p in pre: identifier(p)
        normalized.append(u)
    for u in normalized:
        if any(p not in seen and p not in known for p in u["prerequisites"]):
            raise ValueError("Unknown prerequisite")
    # Explicitly scheduled units must still obey graph order, even if already mastered.
    external_known=known-seen
    # Stable topological order, preserving input order where dependencies allow.
    remaining=list(normalized); scheduled=set(); ordered=[]
    while remaining:
        ready=next((u for u in remaining if set(u["prerequisites"])<=external_known|scheduled),None)
        if ready is None: raise ValueError("Cyclic prerequisites")
        remaining.remove(ready); scheduled.add(ready["id"]); ordered.append(ready)
    total=sum(u["lessons"] for u in ordered)
    if total>max_lessons: raise ValueError("Insufficient lesson capacity")
    lessons=[]; prior=[]
    for u in ordered:
        review=list(dict.fromkeys(u["prerequisites"]+prior[-2:]))
        for i in range(u["lessons"]):
            stage="integrated-practice" if u["lessons"]==1 else (
                "presentation" if i==0 else "application" if i==u["lessons"]-1 else "practice")
            lessons.append({"number":len(lessons)+1,"unit":u["id"],"title":u["title"],
                            "stage":stage,"minutes":lesson_minutes,
                            "review_units":review if i==0 else [u["id"]],"status":"planned"})
        prior.append(u["id"])
    return {"schema_version":1,"course_key":course_key,"lessons":lessons,
            "capacity":max_lessons,"unused_slots":max_lessons-total,
            "status":"REVIEW_REQUIRED","publication_allowed":False}
