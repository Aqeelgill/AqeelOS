import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config import DB_PATH, LEGACY_DB_PATH

DB_LOCK = threading.Lock()

DEPARTMENTS = [
    ("development", "Development Department", "code", "Engineering, infrastructure, and product delivery", "public"),
    ("social_media", "Social Media Department", "share", "Brand, content, publishing, and audience growth", "public"),
    ("internal_promotion", "Internal Promotion", "shield", "Owner-only promotion and growth agents", "internal"),
]

PUBLIC_AGENTS = [
    ("frontend", "Frontend Developer Bot", "development", "online", "Ready"),
    ("uiux", "UI/UX Designer Bot", "development", "online", "Ready"),
    ("backend", "Backend Developer Bot", "development", "online", "Ready"),
    ("webmaster", "Webmaster Bot", "development", "offline", "Ready"),
    ("dba", "Database Administrator Bot", "development", "online", "Ready"),
    ("devops", "DevOps Bot", "development", "online", "Ready"),
    ("reviewer", "Code Reviewer Bot", "development", "online", "Ready"),
    ("api", "API Developer Bot", "development", "offline", "Ready"),
    ("whatsapp", "WhatsApp Manager Bot", "social_media", "online", "Ready"),
    ("facebook", "Facebook Manager Bot", "social_media", "offline", "Ready"),
    ("instagram", "Instagram Manager Bot", "social_media", "online", "Ready"),
    ("twitter", "Twitter/X Manager Bot", "social_media", "online", "Ready"),
    ("linkedin", "LinkedIn Manager Bot", "social_media", "offline", "Ready"),
    ("youtube", "YouTube Manager Bot", "social_media", "online", "Ready"),
    ("tiktok", "TikTok Manager Bot", "social_media", "offline", "Ready"),
    ("pinterest", "Pinterest Manager Bot", "social_media", "online", "Ready"),
    ("scheduler", "Content Scheduler Bot", "social_media", "online", "Ready"),
    ("analytics", "Analytics & Reports Bot", "social_media", "online", "Ready"),
]

INTERNAL_AGENTS = [
    ("promo_growth", "Growth Strategist Bot", "internal_promotion", "online", "Ready"),
    ("promo_outreach", "Outreach Campaign Bot", "internal_promotion", "online", "Ready"),
    ("promo_brand", "Brand Promotion Bot", "internal_promotion", "offline", "Ready"),
]

DEFAULT_SETTINGS = {
    "company": "AqeelOS",
    "owner": "AQEEL GILL",
    "owner_role": "Owner",
    "ceo_role": "Chief Executive Officer",
    "working_hours": "24/7 (Mon-Sat), Sunday OFF",
}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_str():
    return datetime.now().astimezone().date().isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def db_exec(query, params=(), fetch=False, one=False, commit=False):
    with DB_LOCK:
        with connect() as conn:
            cur = conn.execute(query, params)
            if commit:
                conn.commit()
            if fetch:
                rows = cur.fetchall()
                return (dict(rows[0]) if rows else None) if one else [dict(r) for r in rows]
            return cur.lastrowid


def _table_exists(conn, name):
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return bool(row)


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn, table, coldef):
    col = coldef.split()[0]
    if col not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


def _migrate_legacy_db_if_needed():
    # Use target DB if it exists; otherwise copy legacy DB as starting point.
    if DB_PATH.exists():
        return
    if LEGACY_DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)


def init_db():
    _migrate_legacy_db_if_needed()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DB_LOCK:
        with connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS departments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    department_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_task TEXT NOT NULL,
                    tasks_completed INTEGER NOT NULL DEFAULT 0,
                    tasks_failed INTEGER NOT NULL DEFAULT 0,
                    tasks_completed_today INTEGER NOT NULL DEFAULT 0,
                    tasks_completed_today_date TEXT,
                    last_active TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    department_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    agent_name TEXT,
                    department_id TEXT,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    timestamp TEXT NOT NULL,
                    read INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    target TEXT NOT NULL DEFAULT 'all',
                    read INTEGER NOT NULL DEFAULT 0,
                    timestamp TEXT NOT NULL
                );
                """
            )
            # Migrations for new schema
            _add_column(conn, "departments", "visibility TEXT NOT NULL DEFAULT 'public'")
            _add_column(conn, "agents", "visibility TEXT NOT NULL DEFAULT 'public'")
            _add_column(conn, "agents", "capabilities TEXT NOT NULL DEFAULT ''")
            _add_column(conn, "agents", "system_prompt_key TEXT NOT NULL DEFAULT ''")
            _add_column(conn, "tasks", "client_id INTEGER")
            _add_column(conn, "tasks", "source TEXT NOT NULL DEFAULT 'dashboard'")
            _add_column(conn, "tasks", "output_text TEXT")
            _add_column(conn, "tasks", "error_text TEXT")
            _add_column(conn, "tasks", "updated_at TEXT")
            _add_column(conn, "conversations", "pending_route TEXT")
            _add_column(conn, "activity", "client_id INTEGER")
            _add_column(conn, "notifications", "user_id INTEGER")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'client',
                    created_at TEXT NOT NULL,
                    last_login TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    role TEXT NOT NULL,
                    data TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'queued',
                    detail TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    client_id INTEGER,
                    kind TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pending_route TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    sender_role TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    conversation_id INTEGER,
                    subject TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_role TEXT,
                    actor_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
            # Migrate legacy plain passwords into hashed owner/client placeholders (Phase 1 will use users table; keep settings for compatibility)
            for did, name, icon, desc, vis in DEPARTMENTS:
                conn.execute(
                    "INSERT OR IGNORE INTO departments(id,name,icon,description,visibility) VALUES (?,?,?,?,?)",
                    (did, name, icon, desc, vis),
                )
                conn.execute("UPDATE departments SET visibility=? WHERE id=? AND (visibility IS NULL OR visibility='')", (vis, did))
            ts = now_iso()
            for aid, name, dept, status, task in PUBLIC_AGENTS:
                conn.execute(
                    """INSERT OR IGNORE INTO agents
                    (id,name,department_id,status,current_task,tasks_completed,tasks_failed,tasks_completed_today,tasks_completed_today_date,last_active,visibility)
                    VALUES (?,?,?,?,?,0,0,0,?,?, 'public')""",
                    (aid, name, dept, status, task, today_str(), ts),
                )
                conn.execute("UPDATE agents SET visibility='public' WHERE id=? AND department_id!='internal_promotion'", (aid,))
            for aid, name, dept, status, task in INTERNAL_AGENTS:
                conn.execute(
                    """INSERT OR IGNORE INTO agents
                    (id,name,department_id,status,current_task,tasks_completed,tasks_failed,tasks_completed_today,tasks_completed_today_date,last_active,visibility)
                    VALUES (?,?,?,?,?,0,0,0,?,?, 'internal')""",
                    (aid, name, dept, status, task, today_str(), ts),
                )
                conn.execute("UPDATE agents SET visibility='internal' WHERE department_id='internal_promotion'", ())
            if conn.execute("SELECT COUNT(*) c FROM activity").fetchone()["c"] == 0:
                conn.execute(
                    "INSERT INTO activity(agent_id,agent_name,department_id,action,details,level,timestamp,read) VALUES (?,?,?,?,?,?,?,1)",
                    ("system", "System", None, "startup", "AqeelOS initialized", "info", ts),
                )
            if conn.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"] == 0:
                conn.execute(
                    "INSERT INTO notifications(title,message,level,target,read,timestamp) VALUES (?,?,?,?,0,?)",
                    ("System Ready", "AqeelOS connected to SQLite.", "success", "all", ts),
                )
            conn.commit()
