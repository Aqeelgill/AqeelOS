# AqeelOS (Local SaaS Platform)

Local-only Flask + SQLite platform with Ollama-backed agents.

## Setup (using existing venv)
```bash
cd /home/aqeel-gill/ai-team/my-ai-team
source venv/bin/activate
pip install -r aqeelos/requirements.txt
```

## Run
```bash
cd /home/aqeel-gill/ai-team/my-ai-team/aqeelos
python3 app.py
```
Open http://localhost:5000

## Verify Ollama
```bash
python3 scripts/verify_ollama.py
```
Requires Ollama running with model `qwen2.5-coder:3b`.

## Legacy dashboard
The original prototype remains in `../ceo-dashboard/` for reference/parity checks.

## Notes (current build)
- **Default access after reset:** owner and CEO passwords are `AQEEL2026` (PBKDF2-hashed in settings). Reset with `python3 scripts/reset_passwords.py --owner AQEEL2026 --ceo AQEEL2026`.
- **Legacy migration:** if `aqeelos/aqeelos.db` does not exist, DB init copies `../ceo-dashboard/aqeelos.db` when present.
- **Worker:** runs in-process by default; set `AQEELOS_DISABLE_WORKER=1` for tests/dev without Ollama execution.
- **Artifacts:** completed tasks generate `output.txt`, `task-*.pdf` (ReportLab), and `task-*-preview.png` (Pillow) under `data/outputs/<task_id>/`; downloads are authorized by role/client ownership.
- **CSRF:** cookie-authenticated state-changing API requests require `X-CSRF-Token` (issued via `/api/csrf`); auth and selected chat/support endpoints are exempt for local UX.
- **Backups:** `python3 scripts/backup.py` copies DB and outputs to `data/backups/<timestamp>/`.
