import json
import urllib.request

from config import OLLAMA_MODEL, OLLAMA_URL


def generate(prompt, system=None, model=None, timeout=120):
    payload = {"model": model or OLLAMA_MODEL, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        return {"ok": True, "text": (data.get("response") or "").strip(), "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def health():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        models = [m.get("name") for m in data.get("models", [])]
        return {"ok": True, "models": models, "has_model": OLLAMA_MODEL in models}
    except Exception as e:
        return {"ok": False, "error": str(e)}
