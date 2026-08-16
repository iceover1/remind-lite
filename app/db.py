"""SQLite 访问层：连接管理 + 建表 DDL + 通用行转换。

不引入 ORM，sqlite3 标准库直连，row_factory=dict 便于 JSON 序列化。
"""
import sqlite3
import threading
from contextlib import contextmanager

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    api_token TEXT UNIQUE,
    session_ver INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '其他',
    note TEXT DEFAULT '',
    expire_date TEXT NOT NULL,              -- YYYY-MM-DD
    cycle TEXT NOT NULL DEFAULT 'none',     -- none|month|year|custom
    cycle_days INTEGER DEFAULT NULL,        -- cycle=custom 时的周期天数
    advance_days INTEGER NOT NULL DEFAULT 30,   -- 提前几天的窗口
    remind_days TEXT NOT NULL DEFAULT '[30,7,1,0]', -- JSON:窗口内哪几天推；"all"=窗口内每天
    remind_times TEXT NOT NULL DEFAULT '["09:00"]', -- JSON:当天哪几个时刻推
    status TEXT NOT NULL DEFAULT 'active',  -- active|done
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_expire ON items(expire_date);

CREATE TABLE IF NOT EXISTS push_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    remind_date TEXT NOT NULL,      -- YYYY-MM-DD
    remind_time TEXT NOT NULL,      -- HH:MM
    channel_id INTEGER,
    channel_name TEXT DEFAULT '',
    ok INTEGER NOT NULL DEFAULT 0,  -- 1=成功 0=失败
    detail TEXT DEFAULT '',         -- Bark 响应或错误信息
    pushed_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_logs_item_date ON push_logs(item_id, remind_date);

CREATE TABLE IF NOT EXISTS acks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    ack_date TEXT NOT NULL,         -- YYYY-MM-DD，当日剩余推送全部取消
    acked_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(item_id, ack_date)
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    server_url TEXT NOT NULL,
    device_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    """线程局部连接；SQLite WAL 模式，写操作串行安全。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        _local.conn = conn
    return conn


@contextmanager
def tx():
    """写事务：with tx() as conn: conn.execute(...)"""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    # 轻量迁移：老库补列
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "session_ver" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN session_ver INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def query(sql: str, params=()) -> list[dict]:
    rows = get_conn().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_one(sql: str, params=()) -> dict | None:
    row = get_conn().execute(sql, params).fetchone()
    return dict(row) if row else None


def execute(sql: str, params=()) -> int:
    """单条写（自动提交），返回 lastrowid。"""
    with tx() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid
