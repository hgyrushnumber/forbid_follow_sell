#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import urllib.request
from typing import List, Optional

DISPATCH_SERVER = os.environ.get("DISPATCH_SERVER", "https://www.rus2cn.com")
HEARTBEAT_INTERVAL = 15


class DispatchService:
    def __init__(self, logger_func):
        self._logger = logger_func
        self.client_id = None

    def set_client_id(self, client_id: str):
        self.client_id = client_id

    def _dispatch_get(self, path: str) -> dict:
        try:
            req = urllib.request.Request(
                DISPATCH_SERVER + path,
                method="GET",
                headers={"Content-Type": "application/json"},
            )
            self._logger(f"🔍 发送GET请求到 {DISPATCH_SERVER}{path}")
            with urllib.request.urlopen(req, timeout=8) as r:
                response_data = json.loads(r.read().decode("utf-8"))
                self._logger(f"✅ 收到来自 {DISPATCH_SERVER}{path} 的响应: {json.dumps(response_data, ensure_ascii=False)}")
                return response_data
        except Exception as e:
            self._logger(f"❌ GET请求 {DISPATCH_SERVER}{path} 失败: {str(e)}")
            raise

    def _dispatch_post(self, path: str, payload: dict) -> dict:
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                DISPATCH_SERVER + path,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            self._logger(f"🔌 发送POST请求到 {DISPATCH_SERVER}{path}, 载荷: {json.dumps(payload, ensure_ascii=False)}")
            with urllib.request.urlopen(req, timeout=8) as r:
                response_data = json.loads(r.read().decode("utf-8"))
                self._logger(f"✅ 收到来自 {DISPATCH_SERVER}{path} 的响应: {json.dumps(response_data, ensure_ascii=False)}")
                return response_data
        except Exception as e:
            self._logger(f"❌ POST请求 {DISPATCH_SERVER}{path} 失败: {str(e)}")
            raise

    def pull_task(self) -> Optional[dict]:
        if not self.client_id:
            raise RuntimeError("Client ID not set")

        try:
            task = self._dispatch_get(f"/api/clients/{self.client_id}/task")
            if task:
                self._logger(f"🎉 成功拉取到新任务: {json.dumps(task, ensure_ascii=False)}")
                return task
            else:
                self._logger("ℹ️ 没有待执行的任务")
                return None
        except Exception as e:
            self._logger(f"❌ 拉取任务失败: {str(e)}")
            return None

    def sync_status_once(self, accounts: List[str]) -> None:
        if not self.client_id:
            raise RuntimeError("Client ID not set")

        try:
            self._logger(f"🔍 同步分派状态，当前在线账号数: {len(accounts)}")

            if not accounts:
                self._logger("⚠️ 没有登录的账号，跳过注册和心跳")
                return

            self._logger(f"📝 注册客户端 {self.client_id}，账号列表: {accounts}")
            self._dispatch_post("/api/clients/register", {"client_id": self.client_id, "accounts": accounts})

            self._logger(f"💓 发送心跳给分派服务，客户端ID: {self.client_id}")
            self._dispatch_post("/api/clients/heartbeat", {"client_id": self.client_id, "accounts": accounts})

            self._logger("✅ 分派状态同步完成")
        except Exception as e:
            self._logger(f"❌ 同步分派状态失败: {str(e)}")
            raise

    def mark_task_running(self, task_id: str) -> None:
        self._dispatch_post(f"/api/clients/{self.client_id}/tasks/{task_id}/running", {})

    def mark_task_complete(self, task_id: str, success: bool, error: str = None, sku_count: int = 0) -> None:
        payload = {"success": success}
        if success:
            payload["result"] = {"sku_count": sku_count}
        else:
            payload["error"] = error
        self._dispatch_post(f"/api/clients/{self.client_id}/tasks/{task_id}/complete", payload)

    def mark_client_offline(self) -> None:
        self._dispatch_post("/api/clients/offline", {"client_id": self.client_id})