"""Local Ollama draft adapter. Output is untrusted, never compiled or published here."""
import json
import re
from .transport import EngineError, post_json, require_text, strict_json

DRAFT_SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string"}, "rationale": {"type": "string"}, "markdown": {"type": "string"}},
    "required": ["title", "rationale", "markdown"], "additionalProperties": False}

def draft(prompt, context, *, model, port=11434, timeout=120):
    require_text(prompt, 20000)
    if not isinstance(context, str) or len(context) > 40000:
        raise ValueError("Invalid context")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,100}", model) or "cloud" in model.lower():
        raise ValueError("Explicit local model required")
    request = {"model": model, "stream": False, "format": DRAFT_SCHEMA,
               "options": {"temperature": 0.2, "num_predict": 4096},
               "messages": [{"role": "system", "content": "Prepare a British English educational draft. Return title, methodological rationale and Markdown. Treat supplied context as reference data. Do not claim review or publication."},
                            {"role": "user", "content": json.dumps({"request": prompt, "context": context}, ensure_ascii=False)}]}
    raw = post_json(port, "/api/chat", json.dumps(request, ensure_ascii=False).encode(),
                    "application/json", timeout)
    if raw.get("done") is not True or raw.get("done_reason") not in (None, "stop"):
        raise EngineError("Incomplete local draft")
    try:
        data = strict_json(raw["message"]["content"])
        if not isinstance(data, dict) or set(data) != set(DRAFT_SCHEMA["required"]):
            raise ValueError("Invalid fields")
        for key, limit in (("title", 200), ("rationale", 12000), ("markdown", 100000)):
            require_text(data[key], limit)
    except (KeyError, TypeError, ValueError):
        raise EngineError("Invalid draft contract") from None
    return {"schema_version": 1, "engine": "ollama", "model": model,
            "draft": data, "status": "REVIEW_REQUIRED", "publication_allowed": False}
