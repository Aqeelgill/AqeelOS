# AqeelOS Deployment Guide

## GitHub Upload

1. Initialize git (if not already):
```bash
cd /home/aqeel-gill/ai-team/my-ai-team/aqeelos
git init
git add .
git commit -m "Initial AqeelOS release"
```

2. Create a repository on GitHub and push:
```bash
git remote add origin https://github.com/yourusername/aqeelos.git
git branch -M main
git push -u origin main
```

**Important:** Never commit `.env`, `aqeelos.db`, or `venv/`. They are in `.gitignore`.

---

## PythonAnywhere Deployment

### 1. Create a PythonAnywhere web app

- Go to PythonAnywhere Dashboard → Web → Add a new web app
- Choose "Manual configuration" (not a pre-configured framework)
- Python version: 3.10+
- Source code: `/home/yourusername/aqeelos`
- Working directory: `/home/yourusername/aqeelos`
- WSGI file: `/home/yourusername/aqeelos/wsgi.py`

### 2. Install dependencies

```bash
# In a bash console on PythonAnywhere
cd /home/yourusername/aqeelos
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Optionally install gunicorn for production
pip install gunicorn python-dotenv
```

### 3. Configure environment variables

Create `.env` in `/home/yourusername/aqeelos/`:
```bash
cp .env.example .env
# Edit .env with your values:
nano .env
```

Key settings:
- `AQEELOS_SECRET`: Change from default for production
- `LLM_PROVIDER`: Set to `groq` for online deployment (no Ollama needed)
- `GROQ_API_KEY`: Your Groq API key
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: For task completion notifications
- `AQEELOS_DB`: Absolute path to your SQLite database

### 4. Configure PythonAnywhere web app

In the PythonAnywhere web tab:
- **WSGI file:** Point to `/home/yourusername/aqeelos/wsgi.py`
- **Source code:** `/home/yourusername/aqeelos`
- **Working directory:** `/home/yourusername/aqeelos`
- **Virtualenv:** `/home/yourusername/aqeelos/venv`
- Add environment variables from `.env` to the "Environment variables" section

### 5. Static files

Map URL `/static/` to directory `/home/yourusername/aqeelos/static/`

### 6. Database

The app initializes the SQLite database on first run (`init_db()`).
- DB path defaults to `aqeelos/aqeelos.db` (relative to app directory)
- Set `AQEELOS_DB` env var for a custom path
- Back up regularly: `python3 scripts/backup.py`

### 7. LLM Provider Options

**Local (Ollama):**
```bash
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b
```

**Online (Groq API - recommended for PythonAnywhere):**
```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile
```

Groq requires no local model installation and works on restricted environments like PythonAnywhere.

### 8. Telegram Notifications (optional)

Create a Telegram bot via @BotFather, get the token, and send `/start` to your bot to get your chat ID.

```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
```

### 9. First login

After deployment, visit `https://yourusername.pythonanywhere.com/owner` and log in with:
- **Owner password:** `AQEEL2026` (change immediately after first login)

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `AQEELOS_SECRET` | `aqeelos-local-dev-secret-change-on-first-owner-login` | Flask session secret |
| `AQEELOS_DB` | `aqeelos.db` | SQLite database path |
| `LLM_PROVIDER` | `ollama` | `ollama` or `groq` |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen2.5-coder:3b` | Ollama model name |
| `GROQ_URL` | `https://api.groq.com/openai/v1` | Groq API base URL |
| `GROQ_API_KEY` | `` | Groq API key (required for groq provider) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `TELEGRAM_BOT_TOKEN` | `` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | `` | Telegram chat ID for notifications |
| `AQEELOS_WORKER_POLL` | `2.0` | Worker poll interval (seconds) |
| `AQEELOS_DISABLE_WORKER` | `` | Set to `1` to disable background worker |

---

## Security Checklist for Production

- [ ] Change `AQEELOS_SECRET` from default
- [ ] Change default owner password (`AQEEL2026`) via Owner Console
- [ ] Use HTTPS (PythonAnywhere provides this by default)
- [ ] Set `SESSION_COOKIE_SECURE=True` if behind HTTPS
- [ ] Review CSRF exemptions before exposing beyond localhost
- [ ] Regularly back up the SQLite database
- [ ] Rotate Groq API key and Telegram bot token periodically
