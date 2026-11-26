"""Compile Markdown voice blocks into a deterministic, capability-checked render plan."""
import argparse, json, pathlib, re
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRESETS = json.loads((ROOT / "voice/presets.json").read_text(encoding="utf-8"))
BANK = json.loads((ROOT / "voice/voice-bank.json").read_text(encoding="utf-8"))
BLOCK = re.compile(r"^\s*```ivnm-voice[ \t]*\n(.*?)^\s*```[ \t]*$", re.M | re.S)
ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")

def compile_md(path):
    blocks = BLOCK.findall(path.read_text(encoding="utf-8"))
    if not blocks:
        raise ValueError("No ivnm-voice blocks")
    tracks, seen = [], set()
    for raw in blocks:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict): raise ValueError("Block must be a mapping")
        track_id = data["id"]
        if not isinstance(track_id, str) or not ID.fullmatch(track_id) or track_id in seen:
            raise ValueError(f"Invalid or duplicate track id: {track_id}")
        seen.add(track_id)
        profile = PRESETS["profiles"][data["profile"]]
        opts = PRESETS["defaults"] | {k:data[k] for k in ("quality","takes","speed") if k in data}
        if opts["speed"] != 1: raise ValueError("Only native speed 1.0 is supported")
        if not isinstance(opts["takes"],int) or not 1 <= opts["takes"] <= 10: raise ValueError("takes must be 1-10")
        speakers = data["speakers"]
        if not isinstance(speakers,dict) or not speakers: raise ValueError("speakers must be a nonempty mapping")
        voices = {}
        for name, selector in speakers.items():
            if isinstance(selector, str) and selector in BANK["slots"]:
                selector = {"category":selector}
            if isinstance(selector, dict):
                category=selector["category"]
                slot=BANK["slots"][category]
                variant=selector.get("variant","primary")
                if variant not in ("primary","alternate"): raise ValueError("Unknown voice variant")
                key=slot[variant]
                voice=PRESETS["voices"].get(key,{})
                verified=(voice.get("status")=="approved" and voice.get("category")==category and voice.get("accent")==slot["accent"] and voice.get("age_group")==slot["age_group"] and voice.get("gender")==slot["gender"])
                voices[name]=({**voice,"category":category,"category_direction":slot["direction"]} if verified else {"engine":"unassigned","voice":None,"accent":slot["accent"],"status":"pending_audition","category":category,"category_direction":slot["direction"]})
            else:
                voices[name]=PRESETS["voices"][selector]
        direction = str(data.get("direction","")).strip()
        accent = data.get("accent")
        lines, reasons = [], set()
        for turn in data["script"]:
            speaker = turn["speaker"]
            voice = voices[speaker]
            text = turn["text"]
            if not isinstance(text,str) or not text.strip(): raise ValueError("Empty spoken text")
            pause = turn.get("pause_after_ms",profile["pause_ms"])
            if not isinstance(pause,int) or not 0 <= pause <= 5000: raise ValueError("Pause must be 0-5000 ms")
            local = str(turn.get("direction","")).strip()
            emotion = str(turn.get("emotion","neutral"))
            expressive = bool(profile["expressive"] or direction or local or emotion != "neutral" or turn.get("emphasis"))
            if voice["engine"] == "unassigned": reasons.add("No approved voice for category "+voice["category"])
            cap = PRESETS["capabilities"].get(voice["engine"],{"enabled":False,"native_direction":False})
            if expressive and not cap["native_direction"]: reasons.add("Native instruction conditioning not available for selected voice")
            if accent and voice["accent"] != accent: reasons.add("Requested accent has not been verified")
            if not cap["enabled"]: reasons.add("Engine not enabled")
            if voice.get("status") == "rejected" or voice["voice"] in PRESETS.get("rejected_voices",{}).get(voice["engine"],[]): reasons.add("Voice rejected by listening review")
            lines.append({"speaker":speaker,"voice":voice["voice"],"engine":voice["engine"],"text":text,"pause_after_ms":pause,"category":voice.get("category"),"direction":" ".join(filter(None,[voice.get("category_direction"),profile["direction"],direction,local])),"emotion":emotion,"emphasis":turn.get("emphasis",[])})
        if not lines: raise ValueError("Script is empty")
        if opts["takes"] != 1: reasons.add("Multi-take selection not implemented yet")
        if len({l["engine"] for l in lines})!=1: reasons.add("Mixed-engine tracks not supported")
        if len({l["voice"] for l in lines}) < len(speakers): reasons.add("Distinct speakers must have distinct voices")
        tracks.append({"id":track_id,"lesson":data.get("lesson"),"slide":data.get("slide"),"profile":data["profile"],"accent":accent,"options":opts,"lines":lines,"status":"blocked" if reasons else "ready","reasons":sorted(reasons)})
    return {"schema":1,"tracks":tracks}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("source",type=pathlib.Path)
    p.add_argument("output",type=pathlib.Path)
    args=p.parse_args()
    plan=compile_md(args.source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
    for t in plan["tracks"]: print(t["id"],t["status"],"; ".join(t["reasons"]))

if __name__=="__main__": main()
