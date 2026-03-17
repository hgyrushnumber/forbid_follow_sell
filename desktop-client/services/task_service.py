#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import traceback
from typing import Callable, List
from ozon_core import run_task_with_skus


class TaskService:
    def __init__(
        self,
        accounts,
        append_log: Callable[[str], None],
        dispatch_service,
        get_image_path: Callable[[], str],
        get_headless: Callable[[], bool],
        login_account: Callable,
    ):
        self.accounts = accounts
        self.append_log = append_log
        self.dispatch_service = dispatch_service
        self.get_image_path = get_image_path
        self.get_headless = get_headless
        self.login_account = login_account

    def run_task_on_accounts(self, skus: List[str], selected_accounts) -> None:
        """在选中的账号上执行本地手动任务"""
        normalized_skus = [str(s).strip() for s in skus if str(s).strip()]
        normalized_skus = list(dict.fromkeys(normalized_skus))
        if not normalized_skus:
            raise ValueError("请先输入至少一个有效 SKU")

        image_path = self.get_image_path()
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        for account in selected_accounts:
            self.append_log(f"🚀 开始执行本地任务，账号: {account.email}")

            if account.login_status != "已登录":
                self.append_log(f"⚠️ 账号 {account.email} 未登录，尝试登录")
                self.login_account(account)
                if account.login_status != "已登录":
                    self.append_log(f"❌ 账号登录失败，跳过: {account.email}")
                    continue

            run_task_with_skus(
                email=account.email,
                skus=normalized_skus,
                image_path=image_path,
                imap_password=account.imap_password,
                storage_path=account.storage_path,
                headless=self.get_headless(),
                use_manual_login=account.use_manual_login,
            )
            self.append_log(f"✅ 本地任务执行完成: {account.email}")

    def run_task_from_dispatch(self, task: dict):
        """处理从分派服务拉取的任务"""
        try:
            task_id = task["id"]
            account = task.get("assigned_account")
            skus = task.get("sku_payload", [])

            self.append_log(f"🚀 开始执行任务 {task_id}，分配账号: {account}")
            self.append_log(f"📋 任务包含 SKU: {skus}")

            target_account = next((acc for acc in self.accounts if acc.email == account), None)
            if not target_account:
                self.append_log(f"❌ 找不到分配的账号: {account}")
                self.dispatch_service.mark_task_complete(task_id, success=False, error=f"找不到分配的账号: {account}")
                return

            if target_account.login_status != "已登录":
                self.append_log(f"⚠️ 账号 {account} 未登录，尝试登录")
                self.login_account(target_account)
                if target_account.login_status != "已登录":
                    self.append_log(f"❌ 账号 {account} 登录失败，无法执行任务")
                    self.dispatch_service.mark_task_complete(task_id, success=False, error=f"账号 {account} 登录失败")
                    return

            if not skus:
                self.append_log("❌ 任务中没有包含任何SKU")
                self.dispatch_service.mark_task_complete(task_id, success=False, error="任务中没有包含任何SKU")
                return

            image_path = self.get_image_path()
            if not os.path.exists(image_path):
                self.append_log(f"❌ 图片文件不存在: {image_path}")
                self.dispatch_service.mark_task_complete(task_id, success=False, error=f"图片文件不存在: {image_path}")
                return

            self.dispatch_service.mark_task_running(task["id"])

            run_task_with_skus(
                email=target_account.email,
                skus=skus,
                image_path=image_path,
                imap_password=target_account.imap_password,
                storage_path=target_account.storage_path,
                headless=self.get_headless(),
                use_manual_login=target_account.use_manual_login,
            )

            self.dispatch_service.mark_task_complete(task_id, success=True, sku_count=len(skus))
            self.append_log(f"✅ 任务 {task_id} 执行成功")

        except Exception as exc:
            self.append_log(f"❌ 任务执行失败: {str(exc)}")
            self.append_log(f"📝 错误详情: {traceback.format_exc()}")
            try:
                self.dispatch_service.mark_task_complete(task_id, success=False, error=str(exc))
            except Exception:
                pass
