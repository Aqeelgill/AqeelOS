import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import g, jsonify, request, session

from .db import db_exec, now_iso

SESSION_TTL_HOURS = 24 * 7


def _pbkdf2(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password, stored):
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, salt, digest = stored.split("$", 2)
            return hmac.compare_digest(_pbkdf2(password, salt), stored)
        except Exception:
            return False
    # legacy plain text migration path
    return hmac.compare_digest(str(password), str(stored))


def hash_password(password):
    return _pbkdf2(password)


def get_setting(key, default=None):
    row = db_exec("SELECT value FROM settings WHERE key=?", (key,), fetch=True, one=True)
    return row["value"] if row else default


def set_setting(key, value):
    db_exec(
        "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
        commit=True,
    )


def create_session(role, user_id=None, data=None):
    sid = secrets.token_urlsafe(32)
    expires = (datetime.now().astimezone() + timedelta(hours=SESSION_TTL_HOURS)).isoformat(timespec="seconds")
    db_exec(
        "INSERT INTO sessions(id,user_id,role,data,created_at,expires_at) VALUES (?,?,?,?,?,?)",
        (sid, user_id, role, json.dumps(data or {}), now_iso(), expires),
        commit=True,
    )
    session["sid"] = sid
    session["role"] = role
    session["user_id"] = user_id
    return sid


def clear_session():
    sid = session.get("sid")
    if sid:
        db_exec("DELETE FROM sessions WHERE id=?", (sid,), commit=True)
    session.clear()


def load_session():
    g.auth = {"role": "guest", "user_id": None}
    sid = session.get("sid")
    if not sid:
        return
    row = db_exec("SELECT * FROM sessions WHERE id=?", (sid,), fetch=True, one=True)
    if not row:
        session.clear()
        return
    if row["expires_at"] <= now_iso():
        db_exec("DELETE FROM sessions WHERE id=?", (sid,), commit=True)
        session.clear()
        return
    g.auth = {"role": row["role"], "user_id": row["user_id"], "sid": sid, "data": json.loads(row.get("data") or "{}")}


def current_role():
    return getattr(g, "auth", {}).get("role", "guest")


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_role() not in roles:
                return jsonify({"error": "Unauthorized", "required_roles": list(roles)}), 401
            return fn(*args, **kwargs)
        return wrapper
    return deco


def audit(action, details, actor_role=None, actor_id=None):
    a = getattr(g, "auth", {})
    db_exec(
        "INSERT INTO audit_log(actor_role,actor_id,action,details,created_at) VALUES (?,?,?,?,?)",
        (actor_role or a.get("role"), actor_id if actor_id is not None else a.get("user_id"), action, details, now_iso()),
        commit=True,
    )
