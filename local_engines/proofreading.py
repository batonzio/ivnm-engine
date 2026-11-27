"""Advisory LanguageTool adapter, British English by default."""
from urllib.parse import urlencode
from .transport import EngineError, post_json, require_text

def check(text, *, port=8081, timeout=30):
    text = require_text(text, 20000)
    raw = post_json(port, "/v2/check", urlencode({"language": "en-GB", "text": text}).encode(),
                    "application/x-www-form-urlencoded", timeout)
    matches = raw.get("matches")
    if not isinstance(matches, list):
        raise EngineError("Missing proofreading matches")
    findings = []
    for m in matches:
        if not isinstance(m, dict):
            raise EngineError("Invalid proofreading match")
        rule = m.get("rule")
        offset, length = m.get("offset"), m.get("length")
        if (not isinstance(rule, dict) or not isinstance(rule.get("id"), str)
            or type(offset) is not int or type(length) is not int
            or offset < 0 or length < 0 or offset + length > len(text.encode("utf-16-le")) // 2
            or not isinstance(m.get("message"), str)):
            raise EngineError("Invalid proofreading match")
        replacements = m.get("replacements", [])
        if not isinstance(replacements, list) or any(not isinstance(r, dict) or not isinstance(r.get("value"), str) for r in replacements):
            raise EngineError("Invalid proofreading suggestions")
        findings.append({"rule_id": rule["id"], "offset": offset, "length": length,
                         "message": m["message"], "suggestions": [r["value"] for r in replacements[:5]]})
    return {"schema_version": 1, "engine": "languagetool", "language": "en-GB",
            "offset_units": "upstream", "findings": findings, "advisory_only": True,
            "grade": None, "publication_allowed": False}
