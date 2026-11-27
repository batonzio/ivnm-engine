"""Bounded loopback-only HTTP transport, no redirects, proxy or cloud fallback."""
import http.client
import json

class EngineError(RuntimeError):
    """Safe failure; never includes the submitted text or raw remote response."""

def post_json(port, path, body, content_type, timeout):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid local port")
    if not 0 < timeout <= 300:
        raise ValueError("Invalid timeout")
    if not isinstance(body, bytes) or len(body) > 524288:
        raise ValueError("Request exceeds limit")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": content_type, "Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise EngineError("Local engine HTTP status " + str(response.status))
        raw = response.read(2097153)
        if len(raw) > 2097152:
            raise EngineError("Local engine response exceeds limit")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise EngineError("Invalid local engine JSON") from None
        if not isinstance(data, dict):
            raise EngineError("Expected JSON object")
        return data
    except (OSError, http.client.HTTPException):
        raise EngineError("Local engine unavailable") from None
    finally:
        conn.close()

def require_text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Invalid text length")
    return value
