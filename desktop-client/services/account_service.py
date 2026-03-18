#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable, List
import threading
from datetime import datetime
from models import AccountInfo
from ui.account_dialog import AccountDialog
from ozon_core import prepare_browser, close_session, run_account_serialized


class AccountService:
    def __init__(
        self,
        root,
        accounts: List[AccountInfo],
        append_log: Callable[[str], None],
        update_accounts_list: Callable[[], None],
        save_accounts_config: Callable[[], None],
        get_headless: Callable[[], bool],
        sync_dispatch_status_once: Callable[[], None],
    ):
        self.root = root
        self.accounts = accounts
        self.append_log = append_log
        self.update_accounts_list = update_accounts_list
        self.save_accounts_config = save_accounts_config
        self.get_headless = get_headless
        self.sync_dispatch_status_once = sync_dispatch_status_once

    def _schedule_ui(self, callback: Callable[[], None]) -> None:
        try:
            self.root.after(0, callback)
        except Exception:
            callback()

    def _refresh_accounts_list(self) -> None:
        self._schedule_ui(self.update_accounts_list)

    def add_account(self):
        """添加新账号"""
        dialog = AccountDialog(self.root, self)
        if dialog.result:
            self.accounts.append(dialog.result)
            self.update_accounts_list()
            self.save_accounts_config()
            self.append_log(f"➕ 添加新账号: {dialog.result.email}")

    def edit_account(self, index):
        """编辑选中的账号"""
        account = self.accounts[index]
        dialog = AccountDialog(self.root, self, account)
        if dialog.result:
            old_email = account.email
            self.accounts[index] = dialog.result
            self.update_accounts_list()
            self.save_accounts_config()
            self.append_log(f"✏️ 编辑账号: {old_email} -> {dialog.result.email}")

    def delete_account(self, index):
        """删除选中的账号"""
        account = self.accounts[index]

        try:
            close_session(account.email)
            self.append_log(f"🔌 关闭账号会话: {account.email}")
        except Exception as exc:
            self.append_log(f"❌ 关闭会话时出错: {exc}")

        del self.accounts[index]
        self.update_accounts_list()
        self.save_accounts_config()
        self.append_log(f"🗑️ 删除账号: {account.email}")

    def login_account_thread(self, account: AccountInfo):
        """账号登录线程"""
        # 对应实体类的操作
        if not account.validate():
            self.append_log(f"❌ 账号信息不完整: {account.email}")
            account.login_status = "登录失败"
            account.last_error = "账号信息不完整"
            self.update_accounts_list()
            return

        def _login() -> None:
            try:
                account.login_status = "登录中"
                self.update_accounts_list()
                self.append_log(f"🚀 开始登录账号: {account.email}")

                prepare_browser(
                    email=account.email,
                    storage_path=account.storage_path,
                    headless=self.get_headless()
                )

                account.login_status = "已登录"
                account.last_login = datetime.now().timestamp()
                account.login_count += 1
                account.last_error = ""

                self.append_log(f"✅ 账号登录成功: {account.email}")
                try:
                    self.sync_dispatch_status_once()
                except Exception as exc:
                    self.append_log(f"⚠️ 同步登录状态到分派服务失败: {exc}")

            except Exception as exc:
                account.login_status = "登录失败"
                account.last_error = str(exc)
                self.append_log(f"❌ 登录账号出错: {account.email}, {exc}")

            finally:
                self.update_accounts_list()
                self.save_accounts_config()

        run_account_serialized(account.email, "登录账号", _login)

    # selected_indices可以选择多个登录账号
    def login_selected_accounts(self, selected_indices):
        """登录选中的账号"""
        for index in selected_indices:
            account = self.accounts[index]
            # daemon=True 表示将这个线程设置为守护线程（后台线程）
            threading.Thread(
                target=self.login_account_thread,
                args=(account,),
                daemon=True,
            ).start()

    def close_selected_accounts(self, selected_indices):
        """关闭选中账号会话"""
        summary = {"total": len(selected_indices), "success": [], "failed": []}

        for index in selected_indices:
            account = self.accounts[index]
            account.login_status = "关闭中"
            account.task_status = "关闭中"
        self._refresh_accounts_list()

        for index in selected_indices:
            account = self.accounts[index]

            try:
                close_session(account.email)
                account.login_status = "未登录"
                account.task_status = "空闲"
                account.last_error = ""
                summary["success"].append(account.email)
                self.append_log(f"✅ 已关闭账号会话: {account.email}")
            except Exception as exc:
                account.login_status = "关闭失败"
                account.task_status = "关闭失败"
                account.last_error = str(exc)
                summary["failed"].append({"email": account.email, "error": str(exc)})
                self.append_log(f"❌ 关闭账号会话失败: {account.email}, {exc}")

        self.save_accounts_config()
        self._refresh_accounts_list()
        try:
            self.sync_dispatch_status_once()
        except Exception as exc:
            self.append_log(f"⚠️ 同步关闭后的分派状态失败: {exc}")

        self.append_log(
            f"📊 关闭账号汇总: total={summary['total']}, success={len(summary['success'])}, failed={len(summary['failed'])}"
        )
        return summary
