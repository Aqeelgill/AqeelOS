from aqeelos.auth import get_setting, set_setting
from aqeelos.db import db_exec, now_iso
from aqeelos.models import add_activity, add_notification


VALID_STATES = {'running', 'paused'}


def get_state():
    state = (get_setting('execution_state') or 'paused').strip().lower()
    return state if state in VALID_STATES else 'paused'


def is_paused():
    return get_state() != 'running' or (get_setting('task_pickup_enabled') or '0') != '1'


def set_state(state, actor_role='owner', actor_id=None, reason=''):
    state = (state or '').strip().lower()
    if state not in VALID_STATES:
        raise ValueError('Invalid execution state')
    ts = now_iso()
    set_setting('execution_state', state)
    set_setting('task_pickup_enabled', '1' if state == 'running' else '0')
    set_setting('execution_changed_at', ts)
    set_setting('execution_changed_by', actor_role or 'owner')
    if state == 'paused':
        set_setting('execution_paused_at', ts)
        set_setting('execution_pause_reason', (reason or '')[:500])
    else:
        set_setting('execution_resumed_at', ts)
    detail = f'Execution {state}' + (f': {reason}' if reason else '')
    db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
            (actor_role, actor_id, f'execution_{state}', detail[:1000], ts), commit=True)
    add_activity('system', 'control', detail, 'warning' if state == 'paused' else 'success', read=1)
    add_notification('Execution ' + ('Paused' if state == 'paused' else 'Resumed'), detail[:240], 'warning' if state == 'paused' else 'success', 'internal')
    return get_control_status()


def cancel_queued_tasks(task_ids=None, actor_role='owner', actor_id=None, reason='Cancelled by owner'):
    ts = now_iso(); reason = (reason or 'Cancelled by owner')[:500]
    if task_ids:
        ids = [int(t) for t in task_ids]
        q = f"SELECT * FROM tasks WHERE id IN ({','.join(['?']*len(ids))}) AND status='queued'"
        rows = db_exec(q, tuple(ids), fetch=True)
    else:
        rows = db_exec("SELECT * FROM tasks WHERE status='queued'", fetch=True)
    cancelled = []
    for t in rows:
        db_exec("UPDATE tasks SET status='cancelled', error_text=?, updated_at=? WHERE id=? AND status='queued'", (reason, ts, t['id']), commit=True)
        db_exec("UPDATE task_runs SET status='cancelled', stage='cancelled', detail=?, finished_at=? WHERE task_id=? AND status='queued'", (reason, ts, t['id']), commit=True)
        db_exec("UPDATE agents SET status='online', current_task='Ready', last_active=? WHERE id=? AND status='busy'", (ts, t['agent_id']), commit=True)
        add_activity(t['agent_id'], 'cancelled', f"Cancelled queued task #{t['id']}: {reason}", 'warning', client_id=t.get('client_id'))
        cancelled.append(t['id'])
    if cancelled:
        db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
                (actor_role, actor_id, 'tasks_cancelled', f'Cancelled queued tasks: {cancelled}. {reason}'[:1000], ts), commit=True)
    return cancelled


def pause_processing_tasks(task_ids=None, actor_role='owner', actor_id=None, reason='Paused by owner'):
    ts = now_iso(); reason = (reason or 'Paused by owner')[:500]
    if task_ids:
        ids = [int(t) for t in task_ids]
        q = f"SELECT * FROM tasks WHERE id IN ({','.join(['?']*len(ids))}) AND status='processing'"
        rows = db_exec(q, tuple(ids), fetch=True)
    else:
        rows = db_exec("SELECT * FROM tasks WHERE status='processing'", fetch=True)
    paused = []
    for t in rows:
        db_exec("UPDATE tasks SET status='paused', error_text=?, updated_at=? WHERE id=? AND status='processing'", (reason, ts, t['id']), commit=True)
        db_exec("UPDATE task_runs SET status='paused', stage='paused', detail=?, finished_at=? WHERE task_id=? AND status='processing'",
                (reason + ' (if an in-flight model call was active, the worker may finish later; owner should review result)', ts, t['id']), commit=True)
        db_exec("UPDATE agents SET status='online', current_task='Paused by owner', last_active=? WHERE id=?", (ts, t['agent_id']), commit=True)
        add_activity(t['agent_id'], 'paused', f"Paused task #{t['id']}: {reason}", 'warning', client_id=t.get('client_id'))
        paused.append(t['id'])
    if paused:
        db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
                (actor_role, actor_id, 'tasks_paused', f'Paused processing tasks: {paused}. {reason}'[:1000], ts), commit=True)
    return paused


def requeue_tasks(task_ids, actor_role='owner', actor_id=None):
    ts = now_iso(); ids = [int(t) for t in (task_ids or [])]
    if not ids: return []
    q = f"SELECT * FROM tasks WHERE id IN ({','.join(['?']*len(ids))}) AND status IN ('paused','cancelled','failed')"
    rows = db_exec(q, tuple(ids), fetch=True)
    out = []
    for t in rows:
        db_exec("UPDATE tasks SET status='queued', error_text=NULL, completed_at=NULL, output_text=NULL, updated_at=? WHERE id=?", (ts, t['id']), commit=True)
        db_exec("INSERT INTO task_runs(task_id,agent_id,status,stage,detail,started_at) VALUES (?,?,?,?,?,?)",
                (t['id'], t['agent_id'], 'queued', 'queued', f'Requeued by {actor_role}', ts), commit=True)
        db_exec("UPDATE agents SET status='busy', current_task=?, last_active=? WHERE id=?", (t['task'][:200], ts, t['agent_id']), commit=True)
        add_activity(t['agent_id'], 'queued', f"Requeued task #{t['id']} by owner", 'info', client_id=t.get('client_id'))
        out.append(t['id'])
    if out:
        db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
                (actor_role, actor_id, 'tasks_requeued', f'Requeued tasks: {out}', ts), commit=True)
    return out


def retry_failed_tasks(task_ids, actor_role='owner', actor_id=None):
    """Requeue failed tasks back to 'queued' for re-execution."""
    ts = now_iso(); ids = [int(t) for t in (task_ids or [])]
    if not ids: return []
    q = f"SELECT * FROM tasks WHERE id IN ({','.join(['?']*len(ids))}) AND status='failed'"
    rows = db_exec(q, tuple(ids), fetch=True)
    out = []
    for t in rows:
        db_exec("UPDATE tasks SET status='queued', error_text=NULL, completed_at=NULL, output_text=NULL, updated_at=? WHERE id=?",
                (ts, t['id']), commit=True)
        db_exec("INSERT INTO task_runs(task_id,agent_id,status,stage,detail,started_at) VALUES (?,?,?,?,?,?)",
                (t['id'], t['agent_id'], 'queued', 'queued', f'Retried by {actor_role}', ts), commit=True)
        db_exec("UPDATE agents SET status='busy', current_task=?, last_active=? WHERE id=?",
                (t['task'][:200], ts, t['agent_id']), commit=True)
        add_activity(t['agent_id'], 'queued', f"Retried failed task #{t['id']} by owner", 'info', client_id=t.get('client_id'))
        out.append(t['id'])
    if out:
        db_exec("INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
                (actor_role, actor_id, 'tasks_retried', f'Retried failed tasks: {out}', ts), commit=True)
    return out


def get_control_status():
    counts = db_exec("""SELECT
        SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) queued,
        SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) processing,
        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
        SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
        SUM(CASE WHEN status='paused' THEN 1 ELSE 0 END) paused,
        SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) cancelled,
        COUNT(*) total
        FROM tasks""", fetch=True, one=True) or {}
    agent_counts = db_exec("""SELECT
        SUM(CASE WHEN status='online' THEN 1 ELSE 0 END) online,
        SUM(CASE WHEN status='busy' THEN 1 ELSE 0 END) busy,
        SUM(CASE WHEN status='offline' THEN 1 ELSE 0 END) offline,
        COUNT(*) total
        FROM agents""", fetch=True, one=True) or {}
    return {
        'execution_state': get_state(),
        'task_pickup_enabled': not is_paused(),
        'paused': is_paused(),
        'paused_at': get_setting('execution_paused_at'),
        'pause_reason': get_setting('execution_pause_reason'),
        'changed_at': get_setting('execution_changed_at'),
        'tasks': {k: int(counts.get(k) or 0) for k in ('queued','processing','completed','failed','paused','cancelled','total')},
        'agents': {k: int(agent_counts.get(k) or 0) for k in ('online','busy','offline','total')},
        'time': now_iso(),
    }
