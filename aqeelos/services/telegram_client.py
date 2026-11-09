import json
import urllib.parse
import urllib.request

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_message(text, parse_mode="Markdown"):
    """Send a message to the configured Telegram chat. Returns dict with ok flag."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"ok": False, "error": "Telegram bot token or chat ID not configured"}
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8", "ignore"))
        return {"ok": result.get("ok", False), "raw": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def health():
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8", "ignore"))
        return {"ok": result.get("ok", False), "raw": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
