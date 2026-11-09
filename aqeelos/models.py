from .db import db_exec, now_iso, today_str


def success_rate(done, failed):
    total = (done or 0) + (failed or 0)
    return round(((done or 0) / total) * 100, 1) if total else 100.0


def normalize_agent_day(agent):
    if not agent:
        return agent
    if agent.get("tasks_completed_today_date") != today_str():
        db_exec(
            "UPDATE agents SET tasks_completed_today=0, tasks_completed_today_date=? WHERE id=?",
            (today_str(), agent["id"]),
            commit=True,
        )
        agent["tasks_completed_today"] = 0
        agent["tasks_completed_today_date"] = today_str()
    return agent


def agent_payload(a):
    a = normalize_agent_day(dict(a))
    a["success_rate"] = success_rate(a.get("tasks_completed"), a.get("tasks_failed"))
    return a


def visibility_clause(role):
    if role in ("owner", "ceo", "admin"):
        return "", ()
    return "WHERE visibility='public'", ()


def get_agents(department_id=None, role="owner"):
    where, params = visibility_clause(role)
    if department_id:
        if where:
            rows = db_exec(f"SELECT * FROM agents {where} AND department_id=? ORDER BY name", (*params, department_id), fetch=True)
        else:
            rows = db_exec("SELECT * FROM agents WHERE department_id=? ORDER BY name", (department_id,), fetch=True)
    else:
        order = "ORDER BY department_id, name"
        rows = db_exec(f"SELECT * FROM agents {where} {order}", params, fetch=True)
    return [agent_payload(r) for r in rows]


def get_departments(role="owner"):
    rows = db_exec("SELECT * FROM departments ORDER BY CASE id WHEN 'development' THEN 1 WHEN 'social_media' THEN 2 WHEN 'internal_promotion' THEN 3 ELSE 9 END", fetch=True)
    out = []
    for dept in rows:
        agents = get_agents(dept["id"], role=role)
        if role not in ("owner", "ceo", "admin") and dept.get("visibility") != "public":
            continue
        if role not in ("owner", "ceo", "admin"):
            agents = [a for a in agents if a.get("visibility") == "public"]
        active = [a for a in agents if a.get("status") in ("online", "busy")]
        done = sum(a.get("tasks_completed", 0) for a in agents)
        failed = sum(a.get("tasks_failed", 0) for a in agents)
        out.append({
            **dept,
            "status": "active" if active else "idle",
            "total_agents": len(agents),
            "active_agents": len(active),
            "inactive_agents": len(agents) - len(active),
            "tasks_completed": done,
            "tasks_completed_today": sum(a.get("tasks_completed_today", 0) for a in agents),
            "success_rate": success_rate(done, failed),
            "agents": agents,
        })
    return out


def add_activity(agent_id, action, details, level="info", read=0, client_id=None):
    agent = db_exec("SELECT id,name,department_id FROM agents WHERE id=?", (agent_id,), fetch=True, one=True) if agent_id else None
    db_exec(
        """INSERT INTO activity(agent_id,agent_name,department_id,action,details,level,timestamp,read,client_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            agent_id,
            (agent or {}).get("name", "System" if agent_id in (None, "system") else str(agent_id)),
            (agent or {}).get("department_id"),
            action, details, level, now_iso(), 1 if read else 0, client_id,
        ), commit=True,
    )
    db_exec("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT 500)", commit=True)


def add_notification(title, message, level="info", target="all", user_id=None):
    db_exec(
        "INSERT INTO notifications(title,message,level,target,read,timestamp,user_id) VALUES (?,?,?,?,0,?,?)",
        (title, message, level, target, now_iso(), user_id), commit=True,
    )
    db_exec("DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY id DESC LIMIT 200)", commit=True)
