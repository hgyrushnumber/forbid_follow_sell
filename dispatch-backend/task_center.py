#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""exeFile 任务中心：任务持久化 + 客户端活跃会话 + 分派。"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.dirname(__file__)
DB_FILE = os.path.join(BASE_DIR, "task_center.db")
CLIENT_TTL_SECONDS = 45


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def parse_sku_text(sku_text: str) -> List[str]:
    text = (sku_text or "").replace("\r", "\n")
    for sep in [",", "，", ";", "；", "\t"]:
        text = text.replace(sep, "\n")
    skus = [line.strip() for line in text.split("\n") if line.strip()]
    return list(dict.fromkeys(skus))


class TaskCenter:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, col: str, ddl: str) -> None:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as conn:
            # 确保现有表的account_email和imap_password字段允许NULL值，因为API不再使用这些字段
            # 检查并修改account_email字段
            try:
                conn.execute("ALTER TABLE tasks ALTER COLUMN account_email DROP NOT NULL")
            except Exception:
                pass
            # 检查并修改imap_password字段
            try:
                conn.execute("ALTER TABLE tasks ALTER COLUMN imap_password DROP NOT NULL")
            except Exception:
                pass
            # 检查并修改image_path字段
            try:
                conn.execute("ALTER TABLE tasks ALTER COLUMN image_path DROP NOT NULL")
            except Exception:
                pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    account_email TEXT,
                    imap_password TEXT,
                    storage_path TEXT,
                    input_mode TEXT,
                    sku_payload TEXT NOT NULL,
                    source_file TEXT,
                    image_path TEXT,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT,
                    result_json TEXT,
                    error_message TEXT,
                    assigned_client_id TEXT,
                    assigned_account TEXT,
                    created_at TEXT NOT NULL,
                    picked_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # 兼容已有表
            self._ensure_column(conn, "tasks", "assigned_client_id", "assigned_client_id TEXT")
            self._ensure_column(conn, "tasks", "assigned_account", "assigned_account TEXT")
            self._ensure_column(conn, "tasks", "picked_at", "picked_at TEXT")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    client_id TEXT PRIMARY KEY,
                    accounts_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    wechat_openid TEXT UNIQUE,
                    wechat_nickname TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "users", "wechat_openid", "wechat_openid TEXT")
            self._ensure_column(conn, "users", "wechat_nickname", "wechat_nickname TEXT")

    # ---------- task ----------
    def create_task(self, *, sku_text: str = "", skus: Optional[List[str]] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        final_skus = [str(s).strip() for s in (skus or []) if str(s).strip()] or parse_sku_text(sku_text)
        final_skus = list(dict.fromkeys(final_skus))
        if not final_skus:
            raise ValueError("未解析到有效 SKU")

        task_id = str(uuid.uuid4())
        ts = now_iso()
        with self._connect() as conn:
            # 动态获取表结构，兼容不同版本的数据库schema
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [col[1] for col in cursor.fetchall()]

            # 基础字段
            insert_fields = ["id", "user_id", "sku_payload", "status", "progress", "message", "created_at", "updated_at"]
            insert_values = [task_id, user_id, json.dumps(final_skus, ensure_ascii=False), "pending", 0, "任务已创建", ts, ts]

            # 添加可选字段和默认值
            optional_fields = {
                "account_email": None,
                "imap_password": None,
                "storage_path": None,
                "input_mode": "manual",
                "source_file": None,
                "image_path": None,
                "started_at": None,
                "finished_at": None,
                "assigned_client_id": None,
                "assigned_account": None,
                "picked_at": None
            }

            for field, default_value in optional_fields.items():
                if field in columns:
                    insert_fields.append(field)
                    insert_values.append(default_value)

            # 生成SQL语句
            placeholders = ", ".join(["?"] * len(insert_values))
            sql = f"INSERT INTO tasks ({', '.join(insert_fields)}) VALUES ({placeholders})"

            conn.execute(sql, insert_values)
        return {"task_id": task_id, "status": "pending", "sku_count": len(final_skus)}

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_task(dict(row))

    def list_tasks(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_task(dict(r)) for r in rows]

    def list_tasks_for_user(self, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._row_to_task(dict(r)) for r in rows]

    def count_user_tasks_for_day(self, user_id: str, day_prefix: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) FROM tasks WHERE user_id=? AND created_at LIKE ?",
                (user_id, f"{day_prefix}%"),
            ).fetchone()
        return int(row[0] if row else 0)

    # ---------- user ----------
    def create_user(self, username: str, password_hash: str) -> Dict[str, Any]:
        clean_username = username.strip().lower()
        if not clean_username:
            raise ValueError("用户名不能为空")
        ts = now_iso()
        user_id = str(uuid.uuid4())
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE username=?", (clean_username,)).fetchone()
            if existing:
                raise ValueError("用户名已存在")
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, clean_username, password_hash, ts, ts),
            )
        return {"id": user_id, "username": clean_username}

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        clean_username = username.strip().lower()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (clean_username,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_wechat_openid(self, wechat_openid: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE wechat_openid=?", (wechat_openid,)).fetchone()
        return dict(row) if row else None

    def create_or_update_wechat_user(self, wechat_openid: str, wechat_nickname: str) -> Dict[str, Any]:
        if not wechat_openid.strip():
            raise ValueError("wechat_openid 不能为空")

        clean_openid = wechat_openid.strip()
        nickname = wechat_nickname.strip() or f"wx_{clean_openid[-6:]}"
        ts = now_iso()
        existing = self.get_user_by_wechat_openid(clean_openid)
        if existing:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE users SET wechat_nickname=?, updated_at=? WHERE id=?",
                    (nickname, ts, existing["id"]),
                )
            return {
                "id": existing["id"],
                "username": existing["username"],
                "wechat_openid": clean_openid,
                "wechat_nickname": nickname,
            }

        user_id = str(uuid.uuid4())
        generated_username = f"wx_{clean_openid[-10:]}"
        password_hash = str(uuid.uuid4())
        with self._connect() as conn:
            # 防止用户名冲突
            cursor = 0
            candidate = generated_username
            while conn.execute("SELECT id FROM users WHERE username=?", (candidate,)).fetchone():
                cursor += 1
                candidate = f"{generated_username}_{cursor}"

            conn.execute(
                """
                INSERT INTO users (id, username, password_hash, wechat_openid, wechat_nickname, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, candidate, password_hash, clean_openid, nickname, ts, ts),
            )
        return {
            "id": user_id,
            "username": candidate,
            "wechat_openid": clean_openid,
            "wechat_nickname": nickname,
        }

    def _row_to_task(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if item.get("sku_payload"):
            item["sku_payload"] = json.loads(item["sku_payload"])
        if item.get("result_json"):
            item["result_json"] = json.loads(item["result_json"])
        return item

    # ---------- client ----------
    def register_client(self, client_id: str, accounts: List[str]) -> Dict[str, Any]:
        clean_accounts = list(dict.fromkeys([a.strip() for a in accounts if a and a.strip()]))
        if not client_id.strip():
            raise ValueError("client_id 不能为空")
        if not clean_accounts:
            raise ValueError("accounts 不能为空")

        ts = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO clients (client_id, accounts_json, status, last_seen, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    accounts_json=excluded.accounts_json,
                    status='active',
                    last_seen=excluded.last_seen,
                    updated_at=excluded.updated_at
                """,
                (client_id, json.dumps(clean_accounts, ensure_ascii=False), ts, ts, ts),
            )
        return {"client_id": client_id, "status": "active", "accounts": clean_accounts}

    def heartbeat(self, client_id: str, accounts: Optional[List[str]] = None) -> Dict[str, Any]:
        if not client_id.strip():
            raise ValueError("client_id 不能为空")
        ts = now_iso()
        with self._connect() as conn:
            row = conn.execute("SELECT accounts_json FROM clients WHERE client_id=?", (client_id,)).fetchone()
            if not row:
                return self.register_client(client_id, accounts or [])

            accounts_json = row[0]
            if accounts:
                clean_accounts = list(dict.fromkeys([a.strip() for a in accounts if a and a.strip()]))
                if clean_accounts:
                    accounts_json = json.dumps(clean_accounts, ensure_ascii=False)

            conn.execute(
                "UPDATE clients SET status='active', accounts_json=?, last_seen=?, updated_at=? WHERE client_id=?",
                (accounts_json, ts, ts, client_id),
            )

        return {"client_id": client_id, "status": "active", "last_seen": ts}


    def set_client_offline(self, client_id: str) -> Dict[str, Any]:
        if not client_id.strip():
            raise ValueError("client_id 不能为空")
        ts = now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE clients SET status='offline', updated_at=? WHERE client_id=?",
                (ts, client_id),
            )
        return {"client_id": client_id, "status": "offline", "updated_at": ts}

    def list_active_clients(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM clients ORDER BY updated_at DESC").fetchall()

        result = []
        for row in rows:
            item = dict(row)
            try:
                alive = now - parse_iso(item["last_seen"]) <= timedelta(seconds=CLIENT_TTL_SECONDS)
            except Exception:
                alive = False
            item["alive"] = alive and item.get("status") == "active"
            item["accounts"] = json.loads(item.get("accounts_json") or "[]")
            result.append(item)
        return result

    def pull_task_for_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        active = [c for c in self.list_active_clients() if c["client_id"] == client_id and c["alive"]]
        if not active:
            return None

        accounts = active[0]["accounts"]
        if not accounts:
            return None

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status='pending' AND assigned_client_id IS NULL ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None

            task = dict(row)
            assigned_account = accounts[0]
            ts = now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET assigned_client_id=?, assigned_account=?, status='dispatched', progress=5,
                    message='任务已分派给客户端', picked_at=?, updated_at=?
                WHERE id=? AND status='pending' AND assigned_client_id IS NULL
                """,
                (client_id, assigned_account, ts, ts, task["id"]),
            )

        return self.get_task(task["id"])

    def mark_task_running(self, task_id: str, client_id: str) -> Dict[str, Any]:
        ts = now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, status, assigned_client_id FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if not row:
                raise ValueError("任务不存在")

            task = dict(row)
            if task.get("assigned_client_id") != client_id:
                raise ValueError("任务未分配给当前客户端")

            current_status = task.get("status")
            if current_status in ("success", "failed"):
                return {"updated": False, "reason": "already_finished"}
            if current_status == "running":
                return {"updated": False, "reason": "already_running"}
            if current_status != "dispatched":
                raise ValueError(f"任务状态不允许进入running: {current_status}")

            conn.execute(
                "UPDATE tasks SET status='running', progress=20, message='客户端执行中', started_at=?, updated_at=? WHERE id=? AND assigned_client_id=?",
                (ts, ts, task_id, client_id),
            )

        return {"updated": True, "reason": "ok"}

    def complete_task(self, task_id: str, client_id: str, success: bool, result: Optional[Dict[str, Any]] = None, error: str = "") -> Dict[str, Any]:
        ts = now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, status, assigned_client_id FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if not row:
                raise ValueError("任务不存在")

            task = dict(row)
            if task.get("assigned_client_id") != client_id:
                raise ValueError("任务未分配给当前客户端")

            current_status = task.get("status")
            if current_status in ("success", "failed"):
                return {"updated": False, "reason": "already_finished"}
            if current_status not in ("dispatched", "running"):
                raise ValueError(f"任务状态不允许完成: {current_status}")

            conn.execute(
                """
                UPDATE tasks
                SET status=?, progress=100, message=?, result_json=?, error_message=?, finished_at=?, updated_at=?
                WHERE id=? AND assigned_client_id=?
                """,
                (
                    "success" if success else "failed",
                    "任务执行成功" if success else "任务执行失败",
                    json.dumps(result or {}, ensure_ascii=False),
                    error,
                    ts,
                    ts,
                    task_id,
                    client_id,
                ),
            )

        return {"updated": True, "reason": "ok"}


def create_default_center() -> TaskCenter:
    return TaskCenter()
