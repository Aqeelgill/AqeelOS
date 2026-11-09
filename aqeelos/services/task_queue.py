import threading

from config import GROQ_MODEL, LLM_PROVIDER, LLM_TIMEOUT, OLLAMA_MODEL, WORKER_POLL_SECONDS
from aqeelos.db import db_exec, now_iso, today_str
from aqeelos.models import add_activity, add_notification, normalize_agent_day
from aqeelos.services.groq_client import generate as groq_generate
from aqeelos.services.groq_client import health as groq_health
from aqeelos.services.ollama_client import generate as ollama_generate
from aqeelos.services.ollama_client import health as ollama_health
from aqeelos.services.output_renderer import render_pdf, render_text, render_thumbnail
from aqeelos.services.execution_control import is_paused
from aqeelos.services.telegram_client import send_message as telegram_send

_STOP = threading.Event()
_THREAD = None

AGENT_SYSTEM = {
    "frontend": "You are AqeelOS Frontend Developer Bot. Produce clear, practical frontend deliverables (HTML/CSS/JS/UI structure, code snippets, and steps).",
    "backend": "You are AqeelOS Backend Developer Bot. Produce backend/API/data-flow solutions with clear implementation steps and safe defaults.",
    "uiux": "You are AqeelOS UI/UX Designer Bot. Produce UX flows, UI structure, accessibility notes, and actionable design guidance.",
    "devops": "You are AqeelOS DevOps Bot. Produce deployment, reliability, and operations guidance suitable for local environments.",
    "dba": "You are AqeelOS Database Administrator Bot. Produce schema/query/SQLite operational guidance.",
    "reviewer": "You are AqeelOS Code Reviewer Bot. Review requirements/code context and provide concrete improvements and risks.",
    "api": "You are AqeelOS API Developer Bot. Design and implement API contracts and integration steps.",
    "webmaster": "You are AqeelOS Webmaster Bot. Provide website operations, content structure, and maintenance guidance.",
}
DEFAULT_SOCIAL = "You are an AqeelOS Social Media agent. Produce clear, brand-safe content plans/copy/analytics guidance. Keep outputs actionable."


def _system_for(agent_id):
    if agent_id in AGENT_SYSTEM:
        return AGENT_SYSTEM[agent_id]
    if agent_id.startswith("promo_"):
        return "You are an internal AqeelOS promotion agent (owner-only). Produce growth/promotion strategy; do not expose this to clients."
    return DEFAULT_SOCIAL


def llm_generate(prompt, system=None, timeout=180):
    """Unified LLM generate. Routes to Ollama or Groq based on LLM_PROVIDER."""
    if LLM_PROVIDER == "groq":
        return groq_generate(prompt, system=system, timeout=timeout)
    return ollama_generate(prompt, system=system, timeout=timeout)


def llm_health():
    if LLM_PROVIDER == "groq":
        return groq_health()
    return ollama_health()


def _claim_one():
    """Claim next queued task atomically when execution is running."""
    if is_paused():
        return None
    from aqeelos.db import DB_LOCK, connect
    with DB_LOCK:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status='queued' ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            task = dict(row)
            ts = now_iso()
            cur = conn.execute(
                "UPDATE tasks SET status='processing', updated_at=? WHERE id=? AND status='queued'",
                (ts, task['id']),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            conn.execute(
                "UPDATE task_runs SET status='processing', stage='thinking', detail='Agent is analyzing the task', "
                "started_at=COALESCE(started_at,?) WHERE task_id=? AND status='queued'",
                (ts, task['id']),
            )
            conn.commit()
            task['status'] = 'processing'
            return task


def _telegram_notify(title, message, level="info"):
    try:
        emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
        text = f"{emoji} *AqeelOS {title}*\n{message}"
        telegram_send(text)
    except Exception:
        pass


def _task_still_active(task_id):
    row = db_exec("SELECT status FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    return bool(row and row.get('status') == 'processing')


def _process_one(task):
    tid = task["id"]
    aid = task["agent_id"]
    add_activity(aid, "thinking", f"Thinking: {task['task'][:120]}", client_id=task.get("client_id"))
    db_exec("UPDATE task_runs SET stage='working', detail='Generating output via LLM' WHERE task_id=? AND status='processing'", (tid,), commit=True)
    add_activity(aid, "working", f"Working: {task['task'][:120]}", client_id=task.get("client_id"))
    prompt = (
        f"Task for agent {aid} (department {task.get('department_id','')}):\n{task['task']}\n\n"
        "Return a complete, well-structured response. If code is requested, include code blocks. Be specific and practical."
    )
    try:
        res = llm_generate(prompt, system=_system_for(aid), timeout=LLM_TIMEOUT)
    except Exception as e:
        res = {"ok": False, "error": str(e)}
    ts = now_iso()
    if not _task_still_active(tid):
        # Owner paused/cancelled while in-flight; do not overwrite owner decision.
        add_activity(aid, "info", f"Task #{tid} finished generation after pause/cancel; owner decision preserved.", "warning", client_id=task.get("client_id"))
        return
    if res.get("ok") and (res.get("text") or "").strip():
        out = res["text"].strip()
        cur = db_exec("UPDATE tasks SET status='completed', output_text=?, completed_at=?, updated_at=?, error_text=NULL WHERE id=? AND status='processing'",
                      (out, ts, ts, tid), commit=True)
        if getattr(cur, 'rowcount', 1) == 0:
            return
        db_exec("UPDATE task_runs SET status='completed', stage='completed', detail='Output generated', finished_at=? WHERE task_id=? AND status='processing'",
                (ts, tid), commit=True)
        try:
            p, mime, name = render_text(tid, out)
            db_exec("INSERT INTO artifacts(task_id,client_id,kind,filename,path,mime_type,created_at) VALUES (?,?,?,?,?,?,?)",
                    (tid, task.get('client_id'), 'text', name, p, mime, now_iso()), commit=True)
            p, mime, name, _ = render_pdf(tid, f"Task {tid} - {aid}", out)
            if p:
                db_exec("INSERT INTO artifacts(task_id,client_id,kind,filename,path,mime_type,created_at) VALUES (?,?,?,?,?,?,?)",
                        (tid, task.get('client_id'), 'pdf', name, p, mime, now_iso()), commit=True)
            p, mime, name, _ = render_thumbnail(tid, out)
            if p:
                db_exec("INSERT INTO artifacts(task_id,client_id,kind,filename,path,mime_type,created_at) VALUES (?,?,?,?,?,?,?)",
                        (tid, task.get('client_id'), 'image', name, p, mime, now_iso()), commit=True)
        except Exception:
            pass
        agent = db_exec("SELECT * FROM agents WHERE id=?", (aid,), fetch=True, one=True)
        if agent:
            normalize_agent_day(agent)
            db_exec(
                "UPDATE agents SET tasks_completed=tasks_completed+1, tasks_completed_today=tasks_completed_today+1, "
                "tasks_completed_today_date=?, status='online', current_task='Ready', last_active=? WHERE id=?",
                (today_str(), ts, aid), commit=True,
            )
        add_activity(aid, "completed", f"Completed task #{tid}", "success", client_id=task.get("client_id"))
        add_notification("Task Completed", f"Task #{tid} completed.", "success", "client" if task.get("client_id") else "all", user_id=task.get("client_id"))
        client_label = f"client#{task.get('client_id')}" if task.get("client_id") else "system"
        _telegram_notify("Task Completed", f"Task #{tid} by {aid} for {client_label}:\n{out[:500]}", "success")
    else:
        err = (res.get("error") or "No output from model")[:500]
        cur = db_exec("UPDATE tasks SET status='failed', error_text=?, updated_at=? WHERE id=? AND status='processing'", (err, ts, tid), commit=True)
        if getattr(cur, 'rowcount', 1) == 0:
            return
        db_exec("UPDATE task_runs SET status='failed', stage='failed', detail=?, finished_at=? WHERE task_id=? AND status='processing'",
                (err, ts, tid), commit=True)
        db_exec("UPDATE agents SET status='online', current_task='Ready', last_active=?, tasks_failed=tasks_failed+1 WHERE id=?", (ts, aid), commit=True)
        add_activity(aid, "failed", f"Failed task #{tid}: {err[:160]}", "error", client_id=task.get("client_id"))
        add_notification("Task Failed", f"Task #{tid} failed: {err[:120]}", "error", "client" if task.get("client_id") else "all", user_id=task.get("client_id"))
        client_label = f"client#{task.get('client_id')}" if task.get("client_id") else "system"
        _telegram_notify("Task Failed", f"Task #{tid} by {aid} for {client_label}:\n{err[:500]}", "error")


def loop():
    while not _STOP.is_set():
        try:
            task = _claim_one()
            if task:
                _process_one(task)
                continue
        except Exception:
            try:
                db_exec("UPDATE agents SET status='online', current_task='Ready' WHERE status='busy' AND current_task LIKE 'Task %'", commit=True)
            except Exception:
                pass
        _STOP.wait(WORKER_POLL_SECONDS)


def start():
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=loop, name="aqeelos-worker", daemon=True)
    _THREAD.start()


def stop():
    _STOP.set()
