"""Conservative, deterministic, opt-in Speech Director Lite. No external LLM."""
import re,unicodedata
VERSION="1.0"
WORD=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
EMOTIONS={"angry","contemplative","excited","joyful","mundane","nervous","sad","stern","surprised","tender","neutral"}
ONES="zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS="zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()
def number(n):
    return ONES[n] if n<20 else TENS[n//10]+(" "+ONES[n%10] if n%10 else "")
def normalize(text,emphasis=()):
    # Only unambiguous times following a time preposition. Do not expand IDs,
    # dates, decimals, names or arbitrary abbreviations without lexical context.
    changes=[]
    def clock(m):
        h,minute=int(m[2]),int(m[3])
        if h<1 or h>12 or minute<10 or minute>59:return m[0]
        if any(m[0] in e or m[2]+":"+m[3] in e for e in emphasis):return m[0]
        spoken=m[1]+number(h)+" "+number(minute)
        changes.append({"source":m[0],"spoken":spoken,"rule":"12h clock with explicit temporal preposition"})
        return spoken
    spoken=re.sub(r"\b((?:at|before|after|around|by)\s+)([1-9]|1[0-2]):([1-5][0-9])(?![\d:])",clock,text,flags=re.I)
    warnings=[]
    if re.search(r"\d",spoken):warnings.append("Remaining numeric expression requires pronunciation review; no guessed expansion")
    if re.search(r"\b[A-Z]{2,}\b",spoken):warnings.append("Possible acronym: pronunciation left unchanged")
    return spoken,changes,warnings
def classify(text):
    s=text.strip();low=s.casefold()
    if re.match(r"^(really|what|oh)[!?](?:\s|$)",low):return "reaction"
    if re.match(r"^(please\b|could you\b|would you\b|can you\b|would you mind\b)",low):return "request"
    if s.endswith("?"):return "question"
    if re.match(r"^(yes|no|sure|of course|absolutely|exactly)\b",low):return "response"
    if re.match(r"^(hi|hello|good morning|good afternoon)\b",low):return "greeting"
    return "statement"
def emotion_hint(text,direction,scene,intent):
    # Explicit lexical cues only; not a general semantic parser. Negative
    # language may be quoted or hypothetical, so inferred emotions stay hints.
    d=direction.casefold()
    for e,pattern in [("nervous",r"\b(?:nervous|anxious|worried|frightened|тревож\w*|нервнича\w*)\b"),("surprised",r"\b(?:surprised|astonished|удивл\w*)\b"),("joyful",r"\b(?:joyful|delighted|cheerful|радост\w*)\b"),("sad",r"\b(?:sad|upset|груст\w*)\b"),("stern",r"\b(?:stern|strict|строг\w*)\b"),("excited",r"\b(?:excited|enthusiastic|воодушев\w*)\b"),("contemplative",r"\b(?:thoughtful|reflective|задумчив\w*)\b")]:
        if re.search(pattern,d):return e,"explicit direction cue"
    if intent=="reaction" and re.match(r"^(really|what)[!?]",text.strip(),re.I):return "surprised","lexical reaction cue"
    if re.match(r"^(that's great|wonderful|great news|brilliant)[!.]?",text.strip(),re.I):return "joyful","lexical positive reaction cue"
    return "neutral","no reliable cue"
def pace_hint(profile,turn,block):
    pace=turn.get("pace",block.get("pace","auto"))
    if pace not in ("auto","measured","natural","lively"):raise ValueError("Unknown director pace")
    if pace=="auto":
        pace="measured" if profile in ("vocabulary","exam_notice") else "natural"
    return pace,{"measured":135,"natural":150,"lively":170}[pace]
def planned_pause(line,turn,next_line,profile,intent):
    if "pause_after_ms" in turn:return line["pause_after_ms"],"explicit"
    if next_line is None:return line["pause_after_ms"],"terminal; not rendered"
    base=line["pause_after_ms"]
    if profile=="vocabulary":return base,"vocabulary isolation"
    if profile=="exam_notice":return max(base,500),"announcement boundary"
    if line["speaker"]==next_line["speaker"]:return max(220,base-80),"continuing speaker"
    if classify(next_line["text"])=="reaction":return 240,"quick reaction"
    if intent in ("question","request"):return max(base,420),"response opportunity"
    if line["text"].rstrip().endswith("..."):return max(base,550),"hesitation cue"
    return base,"profile baseline"
def apply(plan,blocks,capabilities):
    """Keep existing compiler gates and raw text; enrich opt-in tracks only."""
    source={b["id"]:b for b in blocks}
    for track in plan["tracks"]:
        block=source[track["id"]]
        mode=block.get("director","off")
        if mode not in ("off","lite"):raise ValueError("director must be off or lite")
        if mode=="off":continue
        scene=block.get("scene","")
        if not isinstance(scene,str):raise ValueError("scene must be a string")
        track["director"]={"version":VERSION,"mode":"lite","scene":scene,"method":"deterministic context cues, not full semantic understanding","native_speed":1.0}
        for i,(line,turn) in enumerate(zip(track["lines"],block["script"])):
            if not isinstance(turn,dict):raise ValueError("Invalid turn")
            intent=classify(line["text"])
            next_line=track["lines"][i+1] if i+1<len(track["lines"]) else None
            pause,reason=planned_pause(line,turn,next_line,track["profile"],intent)
            pace,target=pace_hint(track["profile"],turn,block)
            direction=" ".join(str(x) for x in (block.get("direction",""),turn.get("direction","")))
            hint,why=emotion_hint(line["text"],direction,scene,intent)
            cap=capabilities.get(line["engine"],{})
            explicit="emotion" in turn
            if explicit:hint=line["emotion"];why="explicit structured emotion"
            # Never choose a different voice or turn advisory hints into
            # unsupported controls. Inferred emotion only on opt-in Kitten.
            applied=line["emotion"]
            if not explicit and hint!="neutral" and cap.get("native_emotion") and track["options"].get("direction_mode")=="advisory":
                applied=hint;line["emotion"]=hint
            spoken,changes,warnings=normalize(line["text"],line["emphasis"])
            line["pause_after_ms"]=pause
            line["synthesis_text"]=spoken
            line["qa_text"]=spoken
            line["director"]={"intent":intent,"emotion_hint":hint,"emotion_reason":why,
                "applied_emotion":applied,"native_emotion_supported":bool(cap.get("native_emotion")),
                "emphasis_supported":bool(cap.get("native_emphasis")),"pace":pace,
                "target_wpm_for_take_ranking":target,"pace_is_advisory":True,"pause_ms":pause,
                "pause_reason":reason,"pronunciation_changes":changes,"warnings":warnings,
                "internal_prosody":"native punctuation only; no forced intra-line pauses",
                "speaker_preserved":True}
            if hint!="neutral" and applied!=hint:warnings.append("Emotion is a hint, not a native model control")
            track["warnings"]=sorted(set(track["warnings"]+warnings))
    return plan
