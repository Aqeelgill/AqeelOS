import json
import urllib.request

from aqeelos.auth import get_setting
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_URL


def _resolve_api_key():
    return get_setting('groq_api_key') or GROQ_API_KEY


def _resolve_model(model=None):
    return model or get_setting('groq_model') or GROQ_MODEL


def generate(prompt, system=None, model=None, timeout=120):
    """Generate text using Groq Chat Completions API (OpenAI-compatible)."""
    api_key = _resolve_api_key()
    if not api_key:
        return {"ok": False, "error": "GROQ_API_KEY not configured"}

    payload = {
        "model": _resolve_model(model),
        "messages": [],
    }
    if system:
        payload["messages"].append({"role": "system", "content": system})
    payload["messages"].append({"role": "user", "content": prompt})
    req = urllib.request.Request(
        f"{GROQ_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "AqeelOS/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        choices = data.get("choices") or []
        text = ""
        if choices:
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()
        return {"ok": True, "text": text, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def health():
    try:
        api_key = _resolve_api_key()
        req = urllib.request.Request(
            f"{GROQ_URL}/models",
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "AqeelOS/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        models = [m.get("id") for m in data.get("data", [])]
        return {"ok": True, "models": models, "has_model": _resolve_model() in models, "provider": "groq"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
