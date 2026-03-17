#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import traceback
from typing import List, Optional
from models import AccountInfo
from ozon_core import run_task_with_skus


class TaskService:
    def __init__(self, app):
        self.app = app
        self.append_log = app.append_log
        self._logged_in_accounts = app._logged_in_accounts
        self._heartbeat_stop = app._heartbeat_stop
        self.client_id = app.client_id
        self.accounts = app.accounts
        self.headless_var = app.headless_var
        self.image_var = app.image_var
        self.dispatch_service = app.dispatch_service

    def run_task_from_dispatch(self, task: dict):
        """处理从分派服务拉取的任务"""
        try:
            task_id = task["id"]
            account = task.get("assigned_account")
            skus = task.get("sku_payload", [])

            self.append_log(f"🚀 开始执行任务 {task_id}，分配账号: {account}")
            self.append_log(f"📋 任务包含 SKU: {skus}")

            # 查找对应的账号
            target_account = None
            for acc in self.accounts:
                if acc.email == account:
                    target_account = acc
                    break

            if not target_account:
                self.append_log(f"❌ 找不到分配的账号: {account}")
                self.dispatch_service.mark_task_complete(
                    task_id,
                    success=False,
                    error=f"找不到分配的账号: {account}"
                )
                return

            # 确保账号已登录
            if target_account.login_status != "已登录":
                self.append_log(f"⚠️ 账号 {account} 未登录，尝试登录")
                self.app.login_account_thread(target_account)
                if target_account.login_status != "已登录":
                    self.append_log(f"❌ 账号 {account} 登录失败，无法执行任务")
                    self.dispatch_service.mark_task_complete(
                        task_id,
                        success=False,
                        error=f"账号 {account} 登录失败"
                    )
                    return

            # 检查是否有SKU需要处理
            if not skus:
                self.append_log(f"❌ 任务中没有包含任何SKU")
                self.dispatch_service.mark_task_complete(
                    task_id,
                    success=False,
                    error="任务中没有包含任何SKU"
                )
                return

            image_path = self.image_var.get().strip()
            if not os.path.exists(image_path):
                self.append_log(f"❌ 图片文件不存在: {image_path}")
                self.dispatch_service.mark_task_complete(
                    task_id,
                    success=False,
                    error=f"图片文件不存在: {image_path}"
                )
                return

            # 标记任务为运行中
            self.dispatch_service.mark_task_running(task['id'])

            # 执行任务（直接使用SKU列表，不再从Excel读取）
            run_task_with_skus(
                email=target_account.email,
                skus=skus,
                image_path=image_path,
                imap_password=target_account.imap_password,
                storage_path=target_account.storage_path,
                headless=self.headless_var.get(),
                use_manual_login=target_account.use_manual_login,
            )

            # 标记任务为成功
            self.dispatch_service.mark_task_complete(
                task_id,
                success=True,
                sku_count=len(skus)
            )

            self.append_log(f"✅ 任务 {task_id} 执行成功")

        except Exception as exc:
            self.append_log(f"❌ 任务执行失败: {str(exc)}")
            self.append_log(f"📝 错误详情: {traceback.format_exc()}")
            try:
                self.dispatch_service.mark_task_complete(
                    task_id,
                    success=False,
                    error=str(exc)
                )
            except:
                pass