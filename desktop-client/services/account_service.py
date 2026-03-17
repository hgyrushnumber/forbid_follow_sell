#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
import threading
import time
from datetime import datetime
from models import AccountInfo
from ui.account_dialog import AccountDialog
from ozon_core import prepare_browser, close_session


class AccountService:
    def __init__(self, app):
        self.app = app
        self.append_log = app.append_log
        self.accounts: List[AccountInfo] = []

    def add_account(self):
        """添加新账号"""
        dialog = AccountDialog(self.app.root, self.app)
        if dialog.result:
            self.accounts.append(dialog.result)
            self.app.update_accounts_list()
            self.app.save_accounts_config()
            self.append_log(f"➕ 添加新账号: {dialog.result.email}")

    def edit_account(self, index):
        """编辑选中的账号"""
        account = self.accounts[index]
        dialog = AccountDialog(self.app.root, self.app, account)
        if dialog.result:
            old_email = account.email
            self.accounts[index] = dialog.result
            self.app.update_accounts_list()
            self.app.save_accounts_config()
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
        self.app.update_accounts_list()
        self.app.save_accounts_config()
        self.append_log(f"🗑️ 删除账号: {account.email}")

    def login_account_thread(self, account: AccountInfo):
        """账号登录线程"""
        if not account.validate():
            self.append_log(f"❌ 账号信息不完整: {account.email}")
            account.login_status = "登录失败"
            account.last_error = "账号信息不完整"
            self.app.update_accounts_list()
            return

        try:
            account.login_status = "登录中"
            self.app.update_accounts_list()
            self.append_log(f"🚀 开始登录账号: {account.email}")

            prepare_browser(
                email=account.email,
                imap_password=account.imap_password,
                storage_path=account.storage_path,
                headless=self.app.headless_var.get(),
                use_manual_login=account.use_manual_login,
            )

            account.login_status = "已登录"
            account.last_login = datetime.now().timestamp()
            account.login_count += 1
            account.last_error = ""

            self.append_log(f"✅ 账号登录成功: {account.email}")
            try:
                self.app.sync_dispatch_status_once()
            except Exception as exc:
                self.append_log(f"⚠️ 同步登录状态到分派服务失败: {exc}")

        except Exception as exc:
            account.login_status = "登录失败"
            account.last_error = str(exc)
            self.append_log(f"❌ 登录账号出错: {account.email}, {exc}")

        finally:
            self.app.update_accounts_list()
            self.app.save_accounts_config()

    def login_selected_accounts(self, selected_indices):
        """登录选中的账号"""
        for index in selected_indices:
            account = self.accounts[index]
            threading.Thread(
                target=self.login_account_thread,
                args=(account,),
                daemon=True,
            ).start()

    def close_selected_accounts(self, selected_indices):
        """关闭选中账号会话"""
        for index in selected_indices:
            account = self.accounts[index]

            try:
                close_session(account.email)
                account.login_status = "未登录"
                self.append_log(f"✅ 已关闭账号会话: {account.email}")
            except Exception as exc:
                self.append_log(f"❌ 关闭账号会话失败: {account.email}, {exc}")

        self.app.update_accounts_list()
        self.app.save_accounts_config()