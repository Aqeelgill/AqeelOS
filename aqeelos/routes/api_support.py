from flask import Blueprint, g, jsonify, request
from aqeelos.auth import audit, current_role, require_role
from aqeelos.db import db_exec, now_iso
from aqeelos.services.ollama_client import generate
from aqeelos.validation import clean_text

bp = Blueprint("api_support", __name__)


def _json():
    return request.get_json(silent=True) or {}


@bp.post("/support/chat")
def support_chat():
    msg = clean_text((_json().get("message")), 4000)
    if not msg:
        return jsonify({"error": "Message required"}), 400
    prompt = f"You are AqeelOS support assistant. Answer briefly and professionally about local platform usage, privacy, terms, or escalation. If the user needs a human, tell them to use Request Human Support. User: {msg}"
    res = generate(prompt)
    reply = res["text"] if res.get("ok") and res.get('text') else "Support bot is unavailable because Ollama is not reachable. You can request human help and the owner will be notified locally."
    return jsonify({"reply": reply, "ollama_ok": res.get("ok", False)})


@bp.post("/support/escalate")
def support_escalate():
    data = _json()
    uid = getattr(g, 'auth', {}).get('user_id')
    role = current_role()
    subject = clean_text(data.get("subject") or "Human support requested", 200)
    message = clean_text(data.get("message") or "", 4000)
    ts = now_iso()
    cid = db_exec("INSERT INTO conversations(client_id,channel,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                  (uid, "support", "human_requested", ts, ts), commit=True)
    if message:
        db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
                (cid, role or 'guest', 'User', message, ts), commit=True)
    tid = db_exec("INSERT INTO support_tickets(client_id,conversation_id,subject,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                  (uid, cid, subject, "open", ts, ts), commit=True)
    db_exec("INSERT INTO notifications(title,message,level,target,read,timestamp,user_id) VALUES (?,?,?,?,0,?,?)",
            ("Human Support Requested", f"Ticket #{tid}: {subject}", "warning", "owner", ts, uid), commit=True)
    if uid:
        db_exec("INSERT INTO notifications(title,message,level,target,read,timestamp,user_id) VALUES (?,?,?,?,0,?,?)",
                ("Support Ticket Created", f"Your request was escalated as ticket #{tid}. The owner will respond here.", "info", "client", ts, uid), commit=True)
    audit("support_escalate", f"ticket#{tid}")
    return jsonify({"ok": True, "ticket_id": tid, "conversation_id": cid})


@bp.get('/support/tickets')
@require_role('owner')
def tickets_list():
    rows = db_exec("""SELECT t.*, u.name AS client_name, u.email AS client_email,
                      (SELECT body FROM messages m WHERE m.conversation_id=t.conversation_id ORDER BY id DESC LIMIT 1) AS last_message,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=t.conversation_id) AS message_count
                      FROM support_tickets t LEFT JOIN users u ON u.id=t.client_id
                      ORDER BY CASE t.status WHEN 'open' THEN 0 WHEN 'human_requested' THEN 1 WHEN 'answered' THEN 2 ELSE 3 END, t.id DESC LIMIT 100""", fetch=True)
    return jsonify({'tickets': rows})


@bp.get('/support/tickets/<int:ticket_id>')
@require_role('owner')
def ticket_detail(ticket_id):
    t = db_exec("""SELECT t.*, u.name AS client_name, u.email AS client_email
                   FROM support_tickets t LEFT JOIN users u ON u.id=t.client_id WHERE t.id=?""",
                (ticket_id,), fetch=True, one=True)
    if not t:
        return jsonify({'error': 'Not found'}), 404
    msgs = []
    if t.get('conversation_id'):
        msgs = db_exec("SELECT id,sender_role,sender_name,body,created_at FROM messages WHERE conversation_id=? ORDER BY id ASC LIMIT 200",
                       (t['conversation_id'],), fetch=True)
    return jsonify({'ticket': t, 'messages': msgs})


@bp.post('/support/tickets/<int:ticket_id>/respond')
@require_role('owner')
def ticket_respond(ticket_id):
    msg = (_json().get('message') or '').strip()
    if not msg:
        return jsonify({'error': 'Message required'}), 400
    t = db_exec("SELECT * FROM support_tickets WHERE id=?", (ticket_id,), fetch=True, one=True)
    if not t:
        return jsonify({'error': 'Not found'}), 404
    ts = now_iso()
    if t.get('conversation_id'):
        db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
                (t['conversation_id'], 'owner', 'Owner', msg[:4000], ts), commit=True)
        db_exec("UPDATE conversations SET updated_at=?, status='answered' WHERE id=?", (ts, t['conversation_id']), commit=True)
    db_exec("UPDATE support_tickets SET status='answered', updated_at=? WHERE id=?", (ts, ticket_id), commit=True)
    if t.get('client_id'):
        db_exec("INSERT INTO notifications(title,message,level,target,read,timestamp,user_id) VALUES (?,?,?,?,0,?,?)",
                ("Support Response", f"Owner responded to ticket #{ticket_id}.", "info", "client", ts, t['client_id']), commit=True)
    audit('support_respond', f'ticket#{ticket_id}')
    return jsonify({'ok': True, 'ticket_id': ticket_id})


@bp.post('/support/tickets/<int:ticket_id>/close')
@require_role('owner')
def ticket_close(ticket_id):
    ts = now_iso()
    db_exec("UPDATE support_tickets SET status='closed', updated_at=? WHERE id=?", (ts, ticket_id), commit=True)
    audit('support_close', f'ticket#{ticket_id}')
    return jsonify({'ok': True})


@bp.get('/support/my-tickets')
def my_tickets():
    if current_role() != 'client':
        return jsonify({'error':'Unauthorized'}), 401
    uid = getattr(g,'auth',{}).get('user_id')
    rows = db_exec("""SELECT t.*, (SELECT body FROM messages m WHERE m.conversation_id=t.conversation_id ORDER BY id DESC LIMIT 1) AS last_message,
                      (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=t.conversation_id) AS message_count
                      FROM support_tickets t WHERE t.client_id=? ORDER BY t.id DESC LIMIT 100""", (uid,), fetch=True)
    return jsonify({'tickets': rows})

@bp.get('/support/my-tickets/<int:ticket_id>')
def my_ticket_detail(ticket_id):
    if current_role() != 'client':
        return jsonify({'error':'Unauthorized'}), 401
    uid = getattr(g,'auth',{}).get('user_id')
    t = db_exec("SELECT * FROM support_tickets WHERE id=? AND client_id=?", (ticket_id, uid), fetch=True, one=True)
    if not t:
        return jsonify({'error':'Not found'}), 404
    msgs = []
    if t.get('conversation_id'):
        msgs = db_exec("SELECT id,sender_role,sender_name,body,created_at FROM messages WHERE conversation_id=? ORDER BY id ASC LIMIT 200",
                       (t['conversation_id'],), fetch=True)
    return jsonify({'ticket': t, 'messages': msgs})

@bp.post('/support/my-tickets/<int:ticket_id>/reply')
def my_ticket_reply(ticket_id):
    if current_role() != 'client':
        return jsonify({'error':'Unauthorized'}), 401
    uid = getattr(g,'auth',{}).get('user_id')
    msg = clean_text((_json().get('message') or ''), 4000)
    if not msg:
        return jsonify({'error':'Message required'}), 400
    t = db_exec("SELECT * FROM support_tickets WHERE id=? AND client_id=?", (ticket_id, uid), fetch=True, one=True)
    if not t:
        return jsonify({'error':'Not found'}), 404
    ts = now_iso()
    if t.get('conversation_id'):
        db_exec("INSERT INTO messages(conversation_id,sender_role,sender_name,body,created_at) VALUES (?,?,?,?,?)",
                (t['conversation_id'], 'client', 'Client', msg, ts), commit=True)
        db_exec("UPDATE conversations SET updated_at=?, status='open' WHERE id=?", (ts, t['conversation_id']), commit=True)
    db_exec("UPDATE support_tickets SET status='open', updated_at=? WHERE id=?", (ts, ticket_id), commit=True)
    db_exec("INSERT INTO notifications(title,message,level,target,read,timestamp,user_id) VALUES (?,?,?,?,0,?,?)",
            ("Client Replied to Support Ticket", f"Ticket #{ticket_id} has a new client message.", "warning", "owner", ts, uid), commit=True)
    audit('support_client_reply', f'ticket#{ticket_id}')
    return jsonify({'ok': True})
