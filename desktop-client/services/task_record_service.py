#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
任务记录服务：负责本地任务记录的持久化和查询
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from threading import Lock
from models import TaskResult, SkuProcessResult


class TaskRecord:
    """单个任务的记录"""

    def __init__(
        self,
        task_id: str,
        account_email: str,
        task_type: str,  # "local" 或 "dispatch"
        skus: List[str],
        status: str = "pending",  # pending, running, finished, failed
        created_at: Optional[float] = None,
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        self.task_id = task_id
        self.account_email = account_email
        self.task_type = task_type
        self.skus = skus
        self.status = status
        self.created_at = created_at or datetime.now().timestamp()
        self.started_at = started_at
        self.finished_at = finished_at
        self.result = result or {}
        self.error = error

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "account_email": self.account_email,
            "task_type": self.task_type,
            "skus": self.skus,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRecord":
        return cls(
            task_id=data.get("task_id"),
            account_email=data.get("account_email"),
            task_type=data.get("task_type"),
            skus=data.get("skus", []),
            status=data.get("status", "pending"),
            created_at=data.get("created_at"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            result=data.get("result"),
            error=data.get("error"),
        )


class TaskRecordService:
    """任务记录服务"""

    def __init__(self, storage_dir: str = "tasks"):
        self.storage_dir = storage_dir
        self._file_path = os.path.join(storage_dir, "task_history.jsonl")
        self._lock = Lock()
        self._records: Dict[str, TaskRecord] = {}
        os.makedirs(storage_dir, exist_ok=True)
        self._load_records()

    def _load_records(self, reload: bool = False) -> None:
        """从文件加载历史记录

        Args:
            reload: 是否重新加载（清空现有记录）
        """
        if not os.path.exists(self._file_path):
            return

        try:
            with self._lock:
                # 如果需要重新加载，先清空记录
                if reload:
                    self._records.clear()

                with open(self._file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            record = TaskRecord.from_dict(data)
                            self._records[record.task_id] = record
                        except Exception:
                            pass
        except Exception:
            pass

    def _save_record(self, record: TaskRecord) -> None:
        """保存单条记录到文件（追加模式）"""
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def create_record(
        self,
        task_id: str,
        account_email: str,
        task_type: str,
        skus: List[str],
    ) -> TaskRecord:
        """创建新的任务记录"""
        record = TaskRecord(
            task_id=task_id,
            account_email=account_email,
            task_type=task_type,
            skus=skus,
            status="pending",
        )
        with self._lock:
            self._records[record.task_id] = record
            self._save_record(record)
        return record

    def mark_running(self, task_id: str) -> Optional[TaskRecord]:
        """标记任务为运行中"""
        with self._lock:
            if task_id in self._records:
                self._records[task_id].status = "running"
                self._records[task_id].started_at = datetime.now().timestamp()
                self._save_record(self._records[task_id])
                return self._records[task_id]
        return None

    def mark_finished(self, task_id: str, result: Dict) -> Optional[TaskRecord]:
        """标记任务完成（成功或失败）"""
        with self._lock:
            if task_id in self._records:
                record = self._records[task_id]
                record.status = "finished"
                record.finished_at = datetime.now().timestamp()
                record.result = result

                success = result.get("success", False)
                if not success:
                    record.status = "failed"
                    record.error = result.get("error", "")

                self._save_record(record)
                return record
        return None

    def mark_failed(self, task_id: str, error: str) -> Optional[TaskRecord]:
        """标记任务失败"""
        with self._lock:
            if task_id in self._records:
                record = self._records[task_id]
                record.status = "failed"
                record.finished_at = datetime.now().timestamp()
                record.error = error
                self._save_record(record)
                return record
        return None

    def get_record(self, task_id: str) -> Optional[TaskRecord]:
        """获取单个任务记录"""
        with self._lock:
            return self._records.get(task_id)

    def reload_records(self) -> None:
        """重新读取文件并刷新内存"""
        self._clear_records()
        self._load_records(reload=True)

    def _clear_records(self) -> None:
        """清空内存中的记录"""
        with self._lock:
            self._records.clear()

    def get_all_records(self) -> List[TaskRecord]:
        """获取所有任务记录（按创建时间倒序）"""
        self.reload_records()
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    def get_records_by_account(self, account_email: str) -> List[TaskRecord]:
        """获取指定账号的任务记录"""
        with self._lock:
            return sorted(
                [r for r in self._records.values() if r.account_email == account_email],
                key=lambda r: r.created_at,
                reverse=True,
            )

    def get_records_by_status(self, status: str) -> List[TaskRecord]:
        """获取指定状态的任务记录"""
        with self._lock:
            return sorted(
                [r for r in self._records.values() if r.status == status],
                key=lambda r: r.created_at,
                reverse=True,
            )
