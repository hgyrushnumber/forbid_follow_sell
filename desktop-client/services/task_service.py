#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import os
import traceback
import uuid
from datetime import datetime
from typing import Callable, List, Optional
from ozon_core import run_task_with_skus, run_account_serialized
from services.task_record_service import TaskRecordService, TaskRecord


class TaskService:
    def __init__(
        self,
        accounts,
        append_log: Callable[[str], None],
        dispatch_service,
        get_image_path: Callable[[], str],
        get_headless: Callable[[], bool],
        login_account: Callable,
        accounts_lock: threading.RLock,
    ):
        self.accounts = accounts
        self.append_log = append_log
        self.dispatch_service = dispatch_service
        self.get_image_path = get_image_path
        self.get_headless = get_headless
        self.login_account = login_account
        self.record_service = TaskRecordService()
        self.accounts_lock = accounts_lock

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
            task_id = f"local_{uuid.uuid4().hex[:12]}"
            self.append_log(f"🚀 开始执行本地任务，账号: {account.email}，任务ID: {task_id}")

            # 创建任务记录
            record = self.record_service.create_record(
                task_id=task_id,
                account_email=account.email,
                task_type="local",
                skus=normalized_skus,
            )

            def _run_for_account():
                try:
                    # 标记任务开始
                    self.record_service.mark_running(task_id)

                    self.append_log(f"🚀 任务 {task_id} 开始执行，账号: {account.email}")
                    account.mark_task_running()

                    if account.login_status != "已登录":
                        self.append_log(f"⚠️ 账号 {account.email} 未登录，尝试登录")
                        self.login_account(account)
                        if account.login_status != "已登录":
                            self.append_log(f"❌ 账号登录失败，跳过: {account.email}")
                            account.mark_task_failed("账号登录失败")
                            self.record_service.mark_failed(task_id, "账号登录失败")
                            return

                    summary = run_task_with_skus(
                        email=account.email,
                        skus=normalized_skus,
                        image_path=image_path,
                        storage_path=account.storage_path,
                        headless=self.get_headless()
                    )

                    # 标记任务完成
                    self.record_service.mark_finished(task_id, {
                        "success": True,
                        "summary": summary,
                    })

                    account.mark_task_success()
                    account.last_error = ""
                    account.last_login = account.last_login or datetime.now().timestamp()
                    self.append_log(f"✅ 本地任务执行完成: {account.email}，任务ID: {task_id}")
                    self.append_log(
                        f"📊 {account.email} SKU统计: total={summary.get('total', 0)}, success={summary.get('success_count', 0)}, failed={summary.get('failed_count', 0)}"
                    )
                except Exception as exc:
                    self.append_log(f"❌ 本地任务执行失败: {account.email}，错误: {exc}")
                    account.mark_task_failed(str(exc))
                    self.record_service.mark_failed(task_id, str(exc))
                    raise

            run_account_serialized(account.email, "执行本地任务", _run_for_account)

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

                # 创建并标记失败的任务记录
                self.record_service.create_record(
                    task_id=task_id,
                    account_email=account,
                    task_type="dispatch",
                    skus=skus,
                )
                self.record_service.mark_failed(task_id, f"找不到分配的账号: {account}")

                self.dispatch_service.mark_task_complete(task_id, success=False, error=f"找不到分配的账号: {account}")
                return

            if not skus:
                self.append_log("❌ 任务中没有包含任何SKU")

                # 创建并标记失败的任务记录
                self.record_service.create_record(
                    task_id=task_id,
                    account_email=account,
                    task_type="dispatch",
                    skus=[],
                )
                self.record_service.mark_failed(task_id, "任务中没有包含任何SKU")

                self.dispatch_service.mark_task_complete(task_id, success=False, error="任务中没有包含任何SKU")
                return

            image_path = self.get_image_path()
            if not os.path.exists(image_path):
                self.append_log(f"❌ 图片文件不存在: {image_path}")

                # 创建并标记失败的任务记录
                self.record_service.create_record(
                    task_id=task_id,
                    account_email=account,
                    task_type="dispatch",
                    skus=skus,
                )
                self.record_service.mark_failed(task_id, f"图片文件不存在: {image_path}")

                self.dispatch_service.mark_task_complete(task_id, success=False, error=f"图片文件不存在: {image_path}")
                return

            # 创建任务记录
            self.record_service.create_record(
                task_id=task_id,
                account_email=account,
                task_type="dispatch",
                skus=skus,
            )

            def _run_dispatch_task():
                # 标记任务开始
                self.record_service.mark_running(task_id)

                try:
                    if target_account.login_status != "已登录":
                        self.append_log(f"⚠️ 账号 {account} 未登录，尝试登录")
                        self.login_account(target_account)
                        if target_account.login_status != "已登录":
                            self.append_log(f"❌ 账号 {account} 登录失败，无法执行任务")
                            target_account.mark_task_failed(f"账号 {account} 登录失败")

                            # 标记任务失败
                            self.record_service.mark_failed(task_id, f"账号 {account} 登录失败")

                            self.dispatch_service.mark_task_complete(task_id, success=False, error=f"账号 {account} 登录失败")
                            return

                    self.dispatch_service.mark_task_running(task_id)
                    target_account.mark_task_running()

                    summary = run_task_with_skus(
                        email=target_account.email,
                        skus=skus,
                        image_path=image_path,
                        storage_path=target_account.storage_path,
                        headless=self.get_headless()
                    )

                    failed_count = int(summary.get("failed_count", 0))
                    success = failed_count == 0
                    error = "" if success else f"部分SKU处理失败，失败数量: {failed_count}"

                    # 标记任务完成
                    self.record_service.mark_finished(task_id, {
                        "success": success,
                        "error": error,
                        "summary": summary,
                    })

                    if success:
                        target_account.mark_task_success()
                        target_account.last_error = ""
                    else:
                        target_account.mark_task_failed(error)

                    self.dispatch_service.mark_task_complete(
                        task_id,
                        success=success,
                        error=error,
                        sku_count=int(summary.get("success_count", 0)),
                        result=summary,
                    )
                    self.append_log(
                        f"✅ 任务 {task_id} 执行完成: total={summary.get('total', 0)}, success={summary.get('success_count', 0)}, failed={failed_count}"
                    )
                except Exception as exc:
                    self.append_log(f"❌ 任务执行失败: {task_id}，错误: {exc}")
                    self.record_service.mark_failed(task_id, str(exc))
                    target_account.mark_task_failed(str(exc))
                    try:
                        self.dispatch_service.mark_task_complete(task_id, success=False, error=str(exc))
                    except Exception:
                        pass

            run_account_serialized(target_account.email, "执行分派任务", _run_dispatch_task)

        except Exception as exc:
            self.append_log(f"❌ 任务执行失败: {str(exc)}")
            self.append_log(f"📝 错误详情: {traceback.format_exc()}")
            try:
                task_id = task.get("id", "unknown") if task else "unknown"
                self.record_service.mark_failed(task_id, str(exc))
                self.dispatch_service.mark_task_complete(task_id, success=False, error=str(exc))
            except Exception:
                pass

    def get_task_records(self) -> List[TaskRecord]:
        """获取所有任务记录"""
        return self.record_service.get_all_records()

    def get_task_record_by_id(self, task_id: str) -> Optional[TaskRecord]:
        """根据任务ID获取任务记录"""
        return self.record_service.get_record(task_id)

    def get_records_by_account(self, account_email: str) -> List[TaskRecord]:
        """获取指定账号的任务记录"""
        return self.record_service.get_records_by_account(account_email)

    def get_records_by_status(self, status: str) -> List[TaskRecord]:
        """获取指定状态的任务记录"""
        return self.record_service.get_records_by_status(status)
