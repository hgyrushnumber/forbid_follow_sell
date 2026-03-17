#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable, List
import threading
from datetime import datetime
from models import AccountInfo
from ui.account_dialog import AccountDialog
from ozon_core import prepare_browser, close_session


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
        if not account.validate():
            self.append_log(f"❌ 账号信息不完整: {account.email}")
            account.login_status = "登录失败"
            account.last_error = "账号信息不完整"
            self.update_accounts_list()
            return

        try:
            account.login_status = "登录中"
            self.update_accounts_list()
            self.append_log(f"🚀 开始登录账号: {account.email}")

            prepare_browser(
                email=account.email,
                imap_password=account.imap_password,
                storage_path=account.storage_path,
                headless=self.get_headless(),
                use_manual_login=account.use_manual_login,
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

        self.update_accounts_list()
        self.save_accounts_config()
