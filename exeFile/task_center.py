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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    sku_payload TEXT NOT NULL,
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

    # ---------- task ----------
    def create_task(self, *, sku_text: str = "", skus: Optional[List[str]] = None, user_id: str = "anonymous") -> Dict[str, Any]:
        final_skus = [str(s).strip() for s in (skus or []) if str(s).strip()] or parse_sku_text(sku_text)
        final_skus = list(dict.fromkeys(final_skus))
        if not final_skus:
            raise ValueError("未解析到有效 SKU")

        task_id = str(uuid.uuid4())
        ts = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, user_id, sku_payload, status, progress, message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, user_id, json.dumps(final_skus, ensure_ascii=False), "pending", 0, "任务已创建", ts, ts),
            )
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

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status='pending' AND assigned_client_id IS NULL ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None

            task = dict(row)
            assigned_account = accounts[0] if accounts else None
            ts = now_iso()
            conn.execute(
                """
                UPDATE tasks
                SET assigned_client_id=?, assigned_account=?, status='dispatched', progress=5,
                    message='任务已分派给客户端', picked_at=?, updated_at=?
                WHERE id=?
                """,
                (client_id, assigned_account, ts, ts, task["id"]),
            )

        return self.get_task(task["id"])

    def mark_task_running(self, task_id: str, client_id: str) -> None:
        ts = now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status='running', progress=20, message='客户端执行中', started_at=?, updated_at=? WHERE id=? AND assigned_client_id=?",
                (ts, ts, task_id, client_id),
            )

    def complete_task(self, task_id: str, client_id: str, success: bool, result: Optional[Dict[str, Any]] = None, error: str = "") -> None:
        ts = now_iso()
        with self._connect() as conn:
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


def create_default_center() -> TaskCenter:
    return TaskCenter()
