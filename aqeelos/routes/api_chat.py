import json
import re

from flask import Blueprint, g, jsonify, request

from aqeelos.auth import audit, current_role
from aqeelos.db import db_exec, now_iso
from aqeelos.models import add_activity, add_notification, get_agents
from aqeelos.services.ollama_client import generate
from aqeelos.validation import clean_text

bp = Blueprint('api_chat', __name__)

CONFIRM_WORDS = ('yes', 'confirm', 'go ahead', 'approved', 'proceed', 'create it', 'start task', 'do it')


def _json():
    return request.get_json(silent=True) or {}


def _get_or_create_conversation(client_id):
    row = db_exec(
        "SELECT * FROM conversations WHERE client_id=? AND channel='ceo' AND status='open' ORDER BY id DESC LIMIT 1",
        (client_id,), fetch=True, one=True,
    )
    if row:
        return row['id']
    ts = now_iso()
    return db_exec(
        "INSERT INTO conversations(client_id,channel,status,created_at,updated_at,pending_route) VALUES (?,?,?,?,?,?)",
        (client_id, 'ceo', 'open', ts, ts, None), commit=True,
    )


def _create_task_from_route(uid, agent, ttext, conv_id):
    tid = db_exec(
        "INSERT INTO tasks(agent_id,department_id,task,status,created_at,client_id,source,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (agent['id'], agent['department_id'], ttext, 'queued', now_iso(), uid, 'ceo_bot', now_iso()), commit=True,
    )
    db_exec("UPDATE agents SET status='busy', current_task=?, last_active=? WHERE id=?", (ttext, now_iso(), agent['id']), commit=True)
    db_exec(
        "INSERT INTO task_runs(task_id,agent_id,status,stage,detail,started_at) VALUES (?,?,?,?,?,?)",
        (tid, agent['id'], 'queued', 'queued', 'Created by CEO Bot (confirmed)', now_iso()), commit=True,
    )
    add_activity(agent['id'], 'queued', f'CEO Bot queued: {ttext}', client_id=uid)
    add_notification('Task Created', f"CEO Bot assigned {agent['name']}.", 'info', 'client', user_id=uid)
    audit('ceo_route_confirmed', f'task#{tid} agent={agent["id"]} conv={conv_id}')
    db_exec("UPDATE conversations SET pending_route=NULL, updated_at=? WHERE id=?", (now_iso(), conv_id), commit=True)
    return db_exec("SELECT * FROM tasks WHERE id=?", (tid,), fetch=True, one=True)


@bp.get('/ceo/history')
def ceo_history():
    if current_role() != 'client':
        return jsonify({'error': 'Unauthorized'}), 401
    cid = _get_or_create_conversation(g.auth.get('user_id'))
    msgs = db_exec(
        "SELECT id,sender_role,sender_name,body,created_at FROM messages WHERE conversation_id=? ORDER BY id ASC LIMIT 80",
        (cid,), fetch=True,
    )
    conv = db_exec("SELECT pending_route FROM conversations WHERE id=?", (cid,), fetch=True, one=True) or {}
    pending = None
    if conv.get('pending_route'):
        try:
            pending = json.loads(conv['pending_route'])
        except Exception:
            pending = None
    return jsonify({'conversation_id': cid, 'messages': msgs, 'pending_route': pending})


@bp.post('/ceo/confirm')
def ceo_confirm():
    if current_role() != 'client':
        return jsonify({'error': 'Unauthorized'}), 401
    data = _json()
    uid = g.auth.get('user_id')
    conv_id = data.get('conversation_id') or _get_or_create_conversation(uid)
    conv = db_exec("SELECT * FROM conversations WHERE id=? AND client_id=? AND channel='ceo'", (conv_id, uid), fetch=True, one=True)
    if not conv or not conv.get('pending_route'):
        return jsonify({'error': 'No pending task proposal to confirm'}), 400
    try:
        route = json.loads(conv['pending_route'])
    except Exception:
        return jsonify({'error': 'Invalid pending proposal'}), 400
    agents = get_agents(role='client')
    agent = next((a for a in agents if a['id'] == route.get('agent_id') and a.get('visibility') == 'public'), None)
    if not agent:
        db_exec("UPDATE conversations SET pending_route=NULL WHERE id=?", (conv_id,), commit=True)
        return jsonify({'error': 'Proposed agent is unavailable'}), 400
    task = _create_task_from_route(uid, agent, clean_text(route.get('task'), 2000), conv_id)
    reply = f"Confirmed. I created task #{task['id']} for {agent['name']} (queued). I'll update status as it progresses."
    db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
            (conv_id, 'assistant', 'CEO Bot', reply, now_iso()), commit=True)
    db_exec("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), conv_id), commit=True)
    return jsonify({'reply': reply, 'task': task, 'conversation_id': conv_id, 'pending_route': None})


@bp.post('/ceo/cancel')
def ceo_cancel():
    if current_role() != 'client':
        return jsonify({'error': 'Unauthorized'}), 401
    data = _json()
    uid = g.auth.get('user_id')
    conv_id = data.get('conversation_id') or _get_or_create_conversation(uid)
    db_exec("UPDATE conversations SET pending_route=NULL, updated_at=? WHERE id=? AND client_id=?", (now_iso(), conv_id, uid), commit=True)
    reply = 'Cancelled the pending task proposal. Tell me if you want a different agent or revised task.'
    db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
            (conv_id, 'assistant', 'CEO Bot', reply, now_iso()), commit=True)
    return jsonify({'reply': reply, 'conversation_id': conv_id, 'pending_route': None})


@bp.post('/ceo/chat')
def ceo_chat():
    data = _json()
    msg = clean_text(data.get('message'), 4000)
    if not msg:
        return jsonify({'error': 'Message required'}), 400
    if current_role() != 'client':
        return jsonify({'error': 'Unauthorized'}), 401
    uid = g.auth.get('user_id')
    conv_id = data.get('conversation_id') or _get_or_create_conversation(uid)
    conv = db_exec(
        "SELECT * FROM conversations WHERE id=? AND client_id=? AND channel='ceo'",
        (conv_id, uid), fetch=True, one=True,
    )
    if not conv:
        conv_id = _get_or_create_conversation(uid)
        conv = db_exec("SELECT * FROM conversations WHERE id=?", (conv_id,), fetch=True, one=True) or {}
    db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
            (conv_id, 'client', 'Client', msg, now_iso()), commit=True)

    agents = get_agents(role='client')
    # Explicit confirmation path for pending route
    pending = None
    if conv.get('pending_route'):
        try:
            pending = json.loads(conv['pending_route'])
        except Exception:
            pending = None
    lower = msg.lower().strip()
    if pending and any(lower == w or lower.startswith(w + ' ') or w in lower for w in CONFIRM_WORDS) and not lower.startswith(('no', "don't", 'do not', 'cancel', 'stop', 'wait')):
        agent = next((a for a in agents if a['id'] == pending.get('agent_id') and a.get('visibility') == 'public'), None)
        if agent:
            task = _create_task_from_route(uid, agent, clean_text(pending.get('task'), 2000), conv_id)
            reply = f"Confirmed. I created task #{task['id']} for {agent['name']} (queued)."
            db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
                    (conv_id, 'assistant', 'CEO Bot', reply, now_iso()), commit=True)
            return jsonify({'reply': reply, 'task': task, 'conversation_id': conv_id, 'pending_route': None})
    if pending and any(w in lower for w in ('no', "don't", 'do not', 'cancel', 'stop', 'different')):
        db_exec("UPDATE conversations SET pending_route=NULL, updated_at=? WHERE id=?", (now_iso(), conv_id), commit=True)
        reply = 'Understood — I cancelled that pending proposal. What should I change?'
        db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
                (conv_id, 'assistant', 'CEO Bot', reply, now_iso()), commit=True)
        return jsonify({'reply': reply, 'task': None, 'conversation_id': conv_id, 'pending_route': None})

    catalog = "\n".join([f"- {a['id']} ({a['department_id']}): {a['name']}, status={a['status']}" for a in agents])
    history = db_exec("SELECT sender_role,body FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 8", (conv_id,), fetch=True)
    hist = "\n".join([f"{m['sender_role']}: {m['body'][:400]}" for m in reversed(history)])
    prompt = f"""You are the AqeelOS CEO Bot. Be professional, clear, and helpful.
You may ONLY recommend or route to these PUBLIC agents/departments:
{catalog}
Never mention internal promotion agents. If the user asks for a human, tell them to use Support / Request Human.
If the request is actionable, propose a route by ending with JSON: ROUTE:{{"agent_id":"<public id>","task":"<concise task>","confidence":"high|medium|low"}}
The system will ask the client to confirm before creating the task; do NOT claim the task was created.
If ambiguous, ask a clarifying question and do NOT include ROUTE.
Recent conversation:
{hist}
User message: {msg}"""
    res = generate(prompt)
    reply = (res.get('text') or 'I can help route your request to a public team agent. Please describe the task and preferred department.').strip()
    route = None
    if 'ROUTE:' in reply:
        m = re.search(r'ROUTE:(\{.*\})', reply, re.S)
        if m:
            try:
                route = json.loads(m.group(1))
            except Exception:
                route = None
    pending_route = None
    if isinstance(route, dict):
        aid = route.get('agent_id')
        ttext = clean_text(route.get('task') or msg, 2000)
        agent = next((a for a in agents if a['id'] == aid and a.get('visibility') == 'public'), None)
        if agent and ttext:
            pending_route = {'agent_id': aid, 'agent_name': agent['name'], 'department_id': agent['department_id'], 'task': ttext, 'confidence': route.get('confidence', 'medium')}
            db_exec("UPDATE conversations SET pending_route=?, updated_at=? WHERE id=?", (json.dumps(pending_route), now_iso(), conv_id), commit=True)
            reply = reply.split('ROUTE:')[0].strip()
            reply += f"\n\nProposed task (confirmation required): assign **{agent['name']}** to: “{ttext}”.\nReply with **Confirm** to create this task, or **Cancel** / tell me what to change."
        else:
            db_exec("UPDATE conversations SET pending_route=NULL WHERE id=?", (conv_id,), commit=True)
            reply = reply.split('ROUTE:')[0].strip()
    db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
            (conv_id, 'assistant', 'CEO Bot', reply[:4000], now_iso()), commit=True)
    db_exec("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), conv_id), commit=True)
    return jsonify({'reply': reply, 'task': None, 'conversation_id': conv_id, 'pending_route': pending_route, 'ollama_ok': res.get('ok', False)})

