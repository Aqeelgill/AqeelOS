import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# Load .env file if present
load_dotenv(BASE_DIR / ".env")
DB_PATH = Path(os.environ.get("AQEELOS_DB", BASE_DIR / "aqeelos.db"))
LEGACY_DB_PATH = Path(os.environ.get("AQEELOS_LEGACY_DB", BASE_DIR.parent / "ceo-dashboard" / "aqeelos.db"))
DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"
UPLOADS_DIR = DATA_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
PAGES_DIR = BASE_DIR / "pages"
SECRET_KEY = os.environ.get("AQEELOS_SECRET", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:3b")
GROQ_URL = os.environ.get("GROQ_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # ollama | groq
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))  # seconds
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SESSION_COOKIE_NAME = "aqeelos_session"
WORKER_POLL_SECONDS = float(os.environ.get("AQEELOS_WORKER_POLL", "2.0"))
