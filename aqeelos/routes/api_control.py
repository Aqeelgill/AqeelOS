from flask import Blueprint, jsonify, request

from aqeelos.auth import require_role
from aqeelos.db import db_exec
from aqeelos.models import get_agents, get_departments
from aqeelos.services.execution_control import (
    cancel_queued_tasks, get_control_status, pause_processing_tasks, requeue_tasks, set_state,
)
from aqeelos.services.task_queue import llm_health
from aqeelos.validation import clean_text
from config import GROQ_API_KEY, GROQ_MODEL, LLM_PROVIDER, OLLAMA_MODEL

bp = Blueprint('api_control', __name__)


def _json():
    return request.get_json(silent=True) or {}


@bp.get('/owner/control')
@require_role('owner')
def owner_control():
    status = get_control_status()
    status['llm'] = llm_health()
    agents = db_exec("SELECT id,name,department_id,status,current_task,last_active,visibility,tasks_completed,tasks_failed FROM agents ORDER BY department_id,name", fetch=True)
    queue = db_exec("""SELECT t.id,t.agent_id,t.department_id,t.client_id,t.source,t.status,t.task,t.created_at,t.updated_at,t.completed_at,
                       (SELECT stage FROM task_runs tr WHERE tr.task_id=t.id ORDER BY tr.id DESC LIMIT 1) AS stage,
                       (SELECT detail FROM task_runs tr WHERE tr.task_id=t.id ORDER BY tr.id DESC LIMIT 1) AS detail
                       FROM tasks t ORDER BY CASE t.status WHEN 'processing' THEN 0 WHEN 'queued' THEN 1 WHEN 'paused' THEN 2 WHEN 'failed' THEN 3 ELSE 4 END, t.id DESC LIMIT 250""", fetch=True)
    users = db_exec("SELECT id,email,name,role,created_at,last_login FROM users ORDER BY id DESC LIMIT 200", fetch=True)
    errors = db_exec("SELECT id,agent_id,action,details,level,timestamp,client_id FROM activity WHERE level='error' OR action IN ('failed','paused','cancelled') ORDER BY id DESC LIMIT 80", fetch=True)
    history = db_exec("SELECT * FROM task_runs ORDER BY id DESC LIMIT 120", fetch=True)
    artifacts = db_exec("SELECT a.id,a.task_id,a.client_id,a.kind,a.filename,a.mime_type,a.created_at,t.agent_id,t.status AS task_status FROM artifacts a LEFT JOIN tasks t ON t.id=a.task_id ORDER BY a.id DESC LIMIT 120", fetch=True)
    tickets = db_exec("""SELECT t.*, u.name AS client_name, u.email AS client_email,
                         (SELECT body FROM messages m WHERE m.conversation_id=t.conversation_id ORDER BY id DESC LIMIT 1) AS last_message
                         FROM support_tickets t LEFT JOIN users u ON u.id=t.client_id ORDER BY t.id DESC LIMIT 80""", fetch=True)
    audit = db_exec("SELECT * FROM audit_log ORDER BY id DESC LIMIT 120", fetch=True)
    ceo = db_exec("SELECT c.*, u.name AS client_name, u.email AS client_email FROM conversations c LEFT JOIN users u ON u.id=c.client_id WHERE c.channel='ceo' ORDER BY c.id DESC LIMIT 80", fetch=True)
    settings = db_exec("SELECT key,value FROM settings ORDER BY key", fetch=True)
    return jsonify({
        'status': status,
        'config': {
            'llm_provider': LLM_PROVIDER,
            'ollama_model': OLLAMA_MODEL,
            'groq_model': GROQ_MODEL,
            'groq_configured': bool(GROQ_API_KEY),
        },
        'departments': get_departments(role='owner'),
        'agents': agents,
        'queue': queue,
        'users': users,
        'errors': errors,
        'history': history,
        'artifacts': artifacts,
        'tickets': tickets,
        'audit_log': audit,
        'ceo_conversations': ceo,
        'settings': settings,
    })


@bp.post('/owner/control/pause')
@require_role('owner')
def owner_pause():
    reason = clean_text(_json().get('reason') or 'Emergency pause by owner', 500)
    status = set_state('paused', actor_role='owner', reason=reason)
    paused = pause_processing_tasks(actor_role='owner', reason=reason)
    return jsonify({'ok': True, 'status': status, 'paused_tasks': paused})


@bp.post('/owner/control/resume')
@require_role('owner')
def owner_resume():
    status = set_state('running', actor_role='owner', reason='Resumed by owner')
    return jsonify({'ok': True, 'status': status})


@bp.post('/owner/control/tasks/cancel')
@require_role('owner')
def owner_cancel_tasks():
    data = _json()
    ids = data.get('task_ids')
    cancelled = cancel_queued_tasks(task_ids=ids, actor_role='owner', reason=clean_text(data.get('reason') or 'Cancelled by owner', 500))
    return jsonify({'ok': True, 'cancelled_task_ids': cancelled})


@bp.post('/owner/control/tasks/pause')
@require_role('owner')
def owner_pause_tasks():
    data = _json()
    paused = pause_processing_tasks(task_ids=data.get('task_ids'), actor_role='owner', reason=clean_text(data.get('reason') or 'Paused by owner', 500))
    return jsonify({'ok': True, 'paused_task_ids': paused})


@bp.post('/owner/control/tasks/requeue')
@require_role('owner')
def owner_requeue_tasks():
    data = _json()
    ids = data.get('task_ids') or []
    requeued = requeue_tasks(ids, actor_role='owner')
    return jsonify({'ok': True, 'requeued_task_ids': requeued})


@bp.post('/owner/control/tasks/<int:task_id>/cancel')
@require_role('owner')
def owner_cancel_one(task_id):
    cancelled = cancel_queued_tasks(task_ids=[task_id], actor_role='owner', reason='Cancelled by owner')
    if not cancelled:
        # allow pausing processing as safe stop
        paused = pause_processing_tasks(task_ids=[task_id], actor_role='owner', reason='Stopped by owner')
        return jsonify({'ok': bool(paused), 'paused_task_ids': paused, 'cancelled_task_ids': []})
    return jsonify({'ok': True, 'cancelled_task_ids': cancelled, 'paused_task_ids': []})


@bp.post('/owner/control/agents/<agent_id>/toggle')
@require_role('owner')
def owner_toggle_agent(agent_id):
    row = db_exec("SELECT * FROM agents WHERE id=?", (agent_id,), fetch=True, one=True)
    if not row:
        return jsonify({'error': 'Agent not found'}), 404
    next_status = 'online' if row['status'] == 'offline' else 'offline'
    task = 'Ready' if next_status == 'online' else 'Disabled by owner'
    db_exec("UPDATE agents SET status=?, current_task=?, last_active=? WHERE id=?", (next_status, task, __import__('aqeelos.db', fromlist=['now_iso']).now_iso(), agent_id), commit=True)
    db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
            ('owner', None, 'agent_toggle', f'{agent_id} -> {next_status}', __import__('aqeelos.db', fromlist=['now_iso']).now_iso()), commit=True)
    return jsonify({'ok': True, 'agent_id': agent_id, 'status': next_status})


@bp.post('/owner/control/users/<int:user_id>/role')
@require_role('owner')
def owner_set_user_role(user_id):
    role = ( _json().get('role') or '').strip().lower()
    if role not in ('client', 'owner', 'ceo'):
        return jsonify({'error': 'Invalid role'}), 400
    cur = db_exec("SELECT * FROM users WHERE id=?", (user_id,), fetch=True, one=True)
    if not cur:
        return jsonify({'error': 'User not found'}), 404
    db_exec("UPDATE users SET role=? WHERE id=?", (role, user_id), commit=True)
    db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
            ('owner', None, 'user_role', f'user#{user_id} {cur.get("role")} -> {role}', __import__('aqeelos.db', fromlist=['now_iso']).now_iso()), commit=True)
    return jsonify({'ok': True, 'user_id': user_id, 'role': role})
