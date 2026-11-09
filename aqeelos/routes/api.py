import json
from flask import Blueprint, g, jsonify, request

from aqeelos.auth import (
    audit, clear_session, create_session, current_role, get_setting, hash_password,
    require_role, set_setting, verify_password,
)
from aqeelos.db import db_exec, now_iso, today_str
from aqeelos.models import add_activity, add_notification, agent_payload, get_agents, get_departments
from aqeelos.services.ollama_client import health as ollama_health
from aqeelos.services.groq_client import health as groq_health
from config import GROQ_API_KEY, LLM_PROVIDER, OLLAMA_MODEL
from aqeelos.validation import clean_text, valid_email, valid_password

bp = Blueprint("api", __name__)


def _json():
    return request.get_json(silent=True) or {}


def _role():
    return current_role()


def _visible_agent(agent_id, role):
    if not agent_id:
        return None
    row = db_exec("SELECT * FROM agents WHERE id=?", (agent_id,), fetch=True, one=True)
    if not row:
        return None
    if role not in ("owner", "ceo") and row.get("visibility") != "public":
        return None
    return agent_payload(row)


@bp.get("/health")
def health():
    db_exec("SELECT 1", fetch=True, one=True)
    return jsonify({"status": "ok", "database": "sqlite", "time": now_iso()})


@bp.get("/system")
def system():
    if _role() not in ("owner", "ceo"):
        return jsonify({"ollama": {"ok": None}})
    provider = LLM_PROVIDER
    ollama = ollama_health()
    groq = groq_health()
    return jsonify({
        "ollama": ollama,
        "groq": groq,
        "provider": provider,
        "ollama_model": OLLAMA_MODEL,
        "groq_model_available": bool(GROQ_API_KEY),
        "time": now_iso(),
    })


@bp.get("/status")
@bp.get("/legacy/status")
def status():
    role = _role()
    departments = get_departments(role=role)
    agents = get_agents(role=role)
    # clients only see their own tasks/activity summaries
    if role == "client":
        uid = g.auth.get("user_id")
        tasks = db_exec("SELECT * FROM tasks WHERE client_id=? ORDER BY id DESC LIMIT 100", (uid,), fetch=True)
        activity = db_exec("SELECT * FROM activity WHERE client_id=? OR (client_id IS NULL AND agent_id='system' AND action='startup') ORDER BY id DESC LIMIT 40", (uid,), fetch=True)
        notifications = db_exec("SELECT * FROM notifications WHERE user_id=? OR target IN ('all','client') ORDER BY id DESC LIMIT 20", (uid,), fetch=True)
        unread = db_exec("SELECT COUNT(*) c FROM notifications WHERE read=0 AND (user_id=? OR target IN ('all','client'))", (uid,), fetch=True, one=True)["c"]
    else:
        tasks = db_exec("SELECT * FROM tasks ORDER BY id DESC LIMIT 200", fetch=True)
        activity = db_exec("SELECT * FROM activity ORDER BY id DESC LIMIT 60", fetch=True)
        notifications = db_exec("SELECT * FROM notifications ORDER BY id DESC LIMIT 20", fetch=True)
        unread = db_exec("SELECT COUNT(*) c FROM notifications WHERE read=0", fetch=True, one=True)["c"]
    return jsonify({
        "platform": "AqeelOS", "company": get_setting("company"), "owner": get_setting("owner"),
        "owner_role": get_setting("owner_role"), "ceo_role": get_setting("ceo_role"),
        "working_hours": get_setting("working_hours"), "auth_role": role,
        "departments": departments, "agents": {a["id"]: a for a in agents},
        "tasks": tasks, "activity": activity, "notifications": notifications,
        "notifications_unread": unread, "time": now_iso(),
    })


@bp.get("/me")
def me():
    role = _role()
    user = None
    if g.auth.get("user_id"):
        user = db_exec("SELECT id,email,name,role,created_at,last_login FROM users WHERE id=?", (g.auth["user_id"],), fetch=True, one=True)
    return jsonify({"authenticated": role != "guest", "role": role, "user": user})


@bp.post("/auth/register")
def register():
    data = _json()
    email = valid_email(data.get("email"))
    name = clean_text(data.get("name"), 120)
    password = valid_password(data.get("password"), 6, 256)
    if not email or not name or not password:
        return jsonify({"error": "Valid name, email, and password (min 6 chars) required"}), 400
    if db_exec("SELECT id FROM users WHERE email=?", (email,), fetch=True, one=True):
        return jsonify({"error": "Email already registered"}), 409
    uid = db_exec(
        "INSERT INTO users(email,name,password_hash,role,created_at) VALUES (?,?,?,?,?)",
        (email, name, hash_password(password), "client", now_iso()), commit=True,
    )
    create_session("client", user_id=uid)
    add_notification("Welcome", f"Welcome to AqeelOS, {name}.", "success", "client", user_id=uid)
    audit("register", f"client registered: {email}", "client", uid)
    return jsonify({"ok": True, "role": "client", "user": {"id": uid, "email": email, "name": name}}), 201


@bp.post("/auth/login")
def login():
    data = _json()
    email = valid_email(data.get("email")) or ''
    password = str(data.get("password") or "")
    user = db_exec("SELECT * FROM users WHERE email=?", (email,), fetch=True, one=True)
    if not user or not verify_password(password, user.get("password_hash")):
        return jsonify({"error": "Invalid credentials"}), 401
    db_exec("UPDATE users SET last_login=? WHERE id=?", (now_iso(), user["id"]), commit=True)
    role = user.get("role") or "client"
    create_session(role, user_id=user["id"])
    audit("login", f"{role} login: {email}", role, user["id"])
    return jsonify({"ok": True, "role": role, "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": role}})


@bp.post("/auth/logout")
def logout():
    audit("logout", "session closed")
    clear_session()
    return jsonify({"ok": True})


# Legacy password gates -> server sessions (migrates plain settings values)
@bp.post("/auth/agent-view")
@bp.post("/auth/ceo")
def auth_ceo():
    pw = str((_json().get("password") or ""))
    stored = get_setting("agent_view_password", "AQEEL2026")
    if verify_password(pw, stored) or pw == stored:
        if not str(stored).startswith("pbkdf2$"):
            set_setting("agent_view_password", hash_password(stored))
        create_session("ceo")
        add_activity("system", "access", "CEO access granted", read=1)
        audit("ceo_access", "CEO/agent-view unlocked", "ceo")
        return jsonify({"status": "ok", "ok": True, "authorized": True, "role": "ceo"})
    return jsonify({"status": "error", "authorized": False, "error": "Invalid password"}), 401


@bp.post("/auth/owner")
def auth_owner():
    pw = str((_json().get("password") or ""))
    stored = get_setting("owner_password", "AQEEL2026")
    if verify_password(pw, stored) or pw == stored:
        if not str(stored).startswith("pbkdf2$"):
            set_setting("owner_password", hash_password(stored))
        create_session("owner")
        add_activity("system", "access", "Owner access granted", read=1)
        audit("owner_access", "Owner unlocked", "owner")
        return jsonify({"status": "ok", "ok": True, "authorized": True, "role": "owner"})
    return jsonify({"status": "error", "authorized": False, "error": "Invalid password"}), 401


@bp.get("/departments")
def departments():
    return jsonify({"departments": get_departments(role=_role()), "time": now_iso()})


@bp.get("/departments/<dept_id>")
def department(dept_id):
    row = db_exec("SELECT * FROM departments WHERE id=?", (dept_id,), fetch=True, one=True)
    if not row:
        return jsonify({"error": "Department not found"}), 404
    if _role() not in ("owner", "ceo") and row.get("visibility") != "public":
        return jsonify({"error": "Department not found"}), 404
    agents = get_agents(dept_id, role=_role())
    return jsonify({"department": {**row, "agents": agents}, "time": now_iso()})


@bp.get("/agents")
def agents():
    return jsonify({"agents": get_agents(request.args.get("department_id"), role=_role())})


@bp.get("/agents/<agent_id>")
def agent(agent_id):
    row = _visible_agent(agent_id, _role())
    if not row:
        return jsonify({"error": "Agent not found"}), 404
    tasks_q = "SELECT * FROM tasks WHERE agent_id=? ORDER BY id DESC LIMIT 50"
    params = (agent_id,)
    if _role() == "client":
        tasks_q = "SELECT * FROM tasks WHERE agent_id=? AND client_id=? ORDER BY id DESC LIMIT 50"
        params = (agent_id, g.auth.get("user_id"))
    tasks = db_exec(tasks_q, params, fetch=True)
    activity = db_exec("SELECT * FROM activity WHERE agent_id=? ORDER BY id DESC LIMIT 50", (agent_id,), fetch=True)
    return jsonify({"agent": row, "tasks": tasks, "activity": activity})


@bp.post("/agents/<agent_id>/toggle")
@require_role("owner", "ceo")
def toggle_agent(agent_id):
    row = db_exec("SELECT * FROM agents WHERE id=?", (agent_id,), fetch=True, one=True)
    if not row:
        return jsonify({"error": "Agent not found"}), 404
    next_status = "online" if row["status"] == "offline" else "offline"
    task = "Ready" if next_status == "online" else "Standby"
    db_exec("UPDATE agents SET status=?, current_task=?, last_active=? WHERE id=?", (next_status, task, now_iso(), agent_id), commit=True)
    add_activity(agent_id, "status", f"Status changed to {next_status}")
    add_notification("Agent Status", f"{row['name']} is now {next_status}.", "info", "internal")
    audit("agent_toggle", f"{agent_id} -> {next_status}")
    return jsonify({"status": "ok", "agent": _visible_agent(agent_id, _role())})


@bp.post("/tasks")
def create_task():
    data = _json()
    agent_id = data.get("agent_id")
    task_text = clean_text(data.get("task"), 4000)
    role = _role()
    agent = _visible_agent(agent_id, role)
    if not agent:
        return jsonify({"error": "Valid agent_id is required"}), 400
    if not task_text:
        return jsonify({"error": "Task is required"}), 400
    client_id = g.auth.get("user_id") if role == "client" else None
    task_id = db_exec(
        "INSERT INTO tasks(agent_id,department_id,task,status,created_at,client_id,source,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (agent_id, agent["department_id"], task_text, "queued", now_iso(), client_id, data.get("source") or "api", now_iso()),
        commit=True,
    )
    db_exec("UPDATE agents SET status='busy', current_task=?, last_active=? WHERE id=?", (task_text, now_iso(), agent_id), commit=True)
    db_exec("INSERT INTO task_runs(task_id,agent_id,status,stage,detail,started_at) VALUES (?,?,?,?,?,?)",
            (task_id, agent_id, "queued", "queued", "Task queued", now_iso()), commit=True)
    add_activity(agent_id, "queued", f"Queued task: {task_text}", client_id=client_id)
    add_notification("Task Assigned", f"{agent['name']} received: {task_text[:80]}", "info", "all" if role != "client" else "internal")
    audit("task_create", f"task#{task_id} agent={agent_id}")
    task = db_exec("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    return jsonify({"status": "ok", "task": task}), 201


@bp.get("/tasks")
def tasks_get():
    role = _role()
    if role == "client":
        rows = db_exec("SELECT * FROM tasks WHERE client_id=? ORDER BY id DESC LIMIT 200", (g.auth.get("user_id"),), fetch=True)
    else:
        rows = db_exec("SELECT * FROM tasks ORDER BY id DESC LIMIT 300", fetch=True)
    return jsonify({"tasks": rows})


@bp.post("/tasks/<int:task_id>/complete")
@require_role("owner", "ceo")
def task_complete(task_id):
    task = db_exec("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task["status"] != "completed":
        ts = now_iso()
        db_exec("UPDATE tasks SET status='completed', completed_at=?, updated_at=? WHERE id=?", (ts, ts, task_id), commit=True)
        agent = db_exec("SELECT * FROM agents WHERE id=?", (task["agent_id"],), fetch=True, one=True)
        if agent:
            a = agent_payload(agent)
            db_exec(
                "UPDATE agents SET tasks_completed=tasks_completed+1, tasks_completed_today=tasks_completed_today+1, tasks_completed_today_date=?, status='online', current_task='Ready', last_active=? WHERE id=?",
                (today_str(), ts, task["agent_id"]), commit=True,
            )
        add_activity(task["agent_id"], "completed", f"Completed: {task['task']}", "success", client_id=task.get("client_id"))
        add_notification("Task Completed", f"{(agent or {}).get('name','Agent')} completed a task.", "success", "all")
        task = db_exec("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    return jsonify({"status": "ok", "task": task})


@bp.get("/activity")
def activity():
    limit = max(1, min(request.args.get("limit", default=80, type=int), 300))
    if _role() == "client":
        rows = db_exec("SELECT * FROM activity WHERE client_id=? ORDER BY id DESC LIMIT ?", (g.auth.get("user_id"), limit), fetch=True)
    else:
        rows = db_exec("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,), fetch=True)
    return jsonify({"activity": rows, "time": now_iso()})


@bp.get("/notifications")
def notifications():
    if _role() == "client":
        uid = g.auth.get("user_id")
        rows = db_exec("SELECT * FROM notifications WHERE user_id=? OR target IN ('all','client') ORDER BY id DESC LIMIT 50", (uid,), fetch=True)
        unread = db_exec("SELECT COUNT(*) c FROM notifications WHERE read=0 AND (user_id=? OR target IN ('all','client'))", (uid,), fetch=True, one=True)["c"]
    else:
        rows = db_exec("SELECT * FROM notifications ORDER BY id DESC LIMIT 50", fetch=True)
        unread = db_exec("SELECT COUNT(*) c FROM notifications WHERE read=0", fetch=True, one=True)["c"]
    return jsonify({"notifications": rows, "unread": unread})


@bp.post("/notifications/read")
def notifications_read():
    nid = _json().get("id")
    if nid:
        db_exec("UPDATE notifications SET read=1 WHERE id=?", (nid,), commit=True)
    elif _role() == "client":
        db_exec("UPDATE notifications SET read=1 WHERE user_id=? OR target IN ('all','client')", (g.auth.get("user_id"),), commit=True)
    else:
        db_exec("UPDATE notifications SET read=1", commit=True)
    return jsonify({"status": "ok"})


@bp.get("/settings")
@require_role("owner", "ceo")
def settings_get():
    return jsonify({
        "company": get_setting("company"), "owner": get_setting("owner"),
        "owner_role": get_setting("owner_role"), "ceo_role": get_setting("ceo_role"),
        "working_hours": get_setting("working_hours"),
        "groq_model": get_setting("groq_model"),
        "llm_provider": get_setting("llm_provider"),
    })


@bp.post("/settings")
@require_role("owner")
def settings_post():
    data = _json()
    for key in ("company", "owner", "owner_role", "ceo_role", "working_hours", "groq_model"):
        if key in data and str(data[key]).strip():
            set_setting(key, str(data[key]).strip())
    changed = []
    if str(data.get("agent_view_password") or data.get("ceo_password") or "").strip():
        set_setting("agent_view_password", hash_password(str(data.get("agent_view_password") or data.get("ceo_password")).strip()))
        changed.append("CEO access password")
    if str(data.get("owner_password") or "").strip():
        set_setting("owner_password", hash_password(str(data["owner_password"]).strip()))
        changed.append("owner password")
    if str(data.get("groq_api_key") or "").strip():
        set_setting("groq_api_key", str(data["groq_api_key"]).strip())
        changed.append("Groq API key")
    if str(data.get("llm_provider") or "").strip():
        set_setting("llm_provider", str(data["llm_provider"]).strip())
        changed.append("LLM provider")
    details = "Updated " + ", ".join(changed) if changed else "Updated company settings"
    add_activity("system", "settings", details)
    add_notification("Settings Updated", details, "info", "all")
    audit("settings", details)
    return jsonify({"status": "ok"})

@bp.get('/tasks/<int:task_id>')
def task_get(task_id):
    task = db_exec("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    if not task:
        return jsonify({"error":"Task not found"}), 404
    if _role() == 'client' and task.get('client_id') != g.auth.get('user_id'):
        return jsonify({"error":"Task not found"}), 404
    runs = db_exec("SELECT * FROM task_runs WHERE task_id=? ORDER BY id DESC LIMIT 20", (task_id,), fetch=True)
    artifacts = db_exec("SELECT id,task_id,kind,filename,mime_type,created_at FROM artifacts WHERE task_id=? ORDER BY id DESC", (task_id,), fetch=True)
    return jsonify({"task": task, "runs": runs, "artifacts": artifacts})

@bp.get('/artifacts/<int:artifact_id>/download')
def artifact_download(artifact_id):
    from flask import send_file, abort
    art = db_exec("SELECT * FROM artifacts WHERE id=?", (artifact_id,), fetch=True, one=True)
    if not art:
        return jsonify({"error":"Not found"}), 404
    if _role() == 'client' and art.get('client_id') != g.auth.get('user_id'):
        return jsonify({"error":"Not found"}), 404
    if _role() == 'guest':
        return jsonify({"error":"Unauthorized"}), 401
    try:
        return send_file(art['path'], mimetype=art.get('mime_type') or 'application/octet-stream', as_attachment=True, download_name=art.get('filename'))
    except Exception:
        return jsonify({"error":"File unavailable"}), 404

@bp.get('/tasks/<int:task_id>/artifacts')
def task_artifacts(task_id):
    task = db_exec("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    if not task: return jsonify({'error':'Not found'}), 404
    if _role()=='client' and task.get('client_id')!=g.auth.get('user_id'): return jsonify({'error':'Not found'}), 404
    rows = db_exec("SELECT id,task_id,kind,filename,mime_type,created_at FROM artifacts WHERE task_id=? ORDER BY id DESC", (task_id,), fetch=True)
    return jsonify({'artifacts': rows})

@bp.post('/agents/<agent_id>/task')
def create_agent_task(agent_id):
    return create_task_for(agent_id)

def create_task_for(agent_id):
    data = _json()
    task_text = clean_text(data.get('task'), 4000)
    role = _role()
    agent = _visible_agent(agent_id, role)
    if not agent:
        return jsonify({'error':'Valid agent_id is required'}), 400
    if not task_text:
        return jsonify({'error':'Task is required'}), 400
    client_id = g.auth.get('user_id') if role == 'client' else None
    task_id = db_exec("INSERT INTO tasks(agent_id,department_id,task,status,created_at,client_id,source,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (agent_id, agent['department_id'], task_text, 'queued', now_iso(), client_id, data.get('source') or 'api', now_iso()), commit=True)
    db_exec("UPDATE agents SET status='busy', current_task=?, last_active=? WHERE id=?", (task_text, now_iso(), agent_id), commit=True)
    db_exec("INSERT INTO task_runs(task_id,agent_id,status,stage,detail,started_at) VALUES (?,?,?,?,?,?)", (task_id, agent_id, 'queued', 'queued', 'Task queued', now_iso()), commit=True)
    add_activity(agent_id, 'queued', f'Queued task: {task_text}', client_id=client_id)
    add_notification('Task Assigned', f"{agent['name']} received: {task_text[:80]}", 'info', 'all' if role != 'client' else 'internal')
    audit('task_create', f'task#{task_id} agent={agent_id}')
    task = db_exec("SELECT * FROM tasks WHERE id=?", (task_id,), fetch=True, one=True)
    return jsonify({'status':'ok','task':task}), 201
