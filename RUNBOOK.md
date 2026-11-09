# AqeelOS Runbook (local)

## Start
```bash
cd /home/aqeel-gill/ai-team/my-ai-team
source venv/bin/activate
pip install -r aqeelos/requirements.txt
cd aqeelos
python3 scripts/verify_ollama.py   # optional but recommended
python3 app.py                      # http://localhost:5000
```

## Default credentials (after migration/reset)
- **Owner password:** `AQEEL2026` (PBKDF2 hashed in settings). Change in Owner Console or:
  `python3 scripts/reset_passwords.py --owner AQEEL2026 --ceo AQEEL2026`
- **CEO/agent-view password:** `AQEEL2026` by default/reset.
- **Client accounts:** register at `/register`; stored in `users` table.

## Roles and visibility
- **Owner:** full access, sees internal promotion agents (`visibility=internal`).
- **CEO:** operational access; internal promotion agents hidden by API/model filtering for non-owner contexts as designed.
- **Client:** public departments/agents only; can see only own tasks/artifacts/conversations.
- Never expose `promo_*`/internal agents to client routes/UI.

## Data and services
- SQLite DB: `aqeelos/aqeelos.db` (WAL). On first run, may copy legacy `../ceo-dashboard/aqeelos.db`.
- Ollama: `http://localhost:11434`, model `qwen2.5-coder:3b` (configurable via env).
- Worker: in-process thread polls queued tasks; set `AQEELOS_DISABLE_WORKER=1` to disable.

## Artifacts
- Generated under `data/outputs/<task_id>/`: `output.txt`, PDF (ReportLab), preview PNG (Pillow).
- Download endpoint: `/api/artifacts/<id>/download` (authorized).

## Security notes (local MVP)
- DB-backed sessions; PBKDF2 password hashes.
- CSRF token required for protected cookie-authenticated state changes (`X-CSRF-Token`, `/api/csrf`). Some auth/chat/support endpoints exempt for local UX; review before exposing beyond localhost.
- Validate all external input; client cannot set arbitrary `client_id`.
- Page guards redirect unauthenticated/unauthorized users from portal pages.

## Backup
```bash
python3 scripts/backup.py
```
Writes DB and outputs to `data/backups/<timestamp>/`.

## Tests
```bash
cd /home/aqeel-gill/ai-team/my-ai-team/aqeelos
AQEELOS_DISABLE_WORKER=1 ../venv/bin/python -m unittest discover -s tests -v
```
