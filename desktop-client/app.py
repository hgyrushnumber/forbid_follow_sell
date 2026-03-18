#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多账号版 Ozon SKU 上传工具 - 基于邮箱 + IMAP 授权码登录
"""

import os
import threading
import tkinter as tk
from datetime import datetime

from typing import List, Optional

from dotenv import load_dotenv

from models import AccountInfo
from services import ConfigService
from services.dispatch_service import DispatchService
from services.task_service import TaskService
from services.account_service import AccountService
from services.mail_service import get_latest_mail_id as _get_latest_mail_id
from services.client_identity import resolve_client_id
from ui.main_window import MainWindow
from ozon_core import close_all_sessions, set_logger

# 加载.env配置文件
load_dotenv()

DISPATCH_SERVER = os.environ.get("DISPATCH_SERVER", "https://www.rus2cn.com")


def get_latest_mail_id(email_addr: str, email_pass: str, imap_server: str):
    """兼容 AccountDialog 的导入路径。"""
    return _get_latest_mail_id(email_addr, email_pass, imap_server)


class OzonMultiApp:
    """应用编排层：协调 UI、服务与生命周期。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.accounts: List[AccountInfo] = []
        self.client_id = resolve_client_id()
        self._heartbeat_stop = threading.Event()
        self.log_file = os.environ.get("DESKTOP_LOG_FILE", os.path.join("logs", "desktop-client.log"))

        self.config_service = ConfigService()

        self.ui = MainWindow(
            root=self.root,
            on_add_account=self.add_account,
            on_edit_account=self.edit_account,
            on_delete_account=self.delete_account,
            on_refresh_accounts=self.update_accounts_list,
            on_login_selected=self.login_selected_accounts,
            on_run_task_selected=self.run_task_on_selected,
            on_close_selected=self.close_selected_accounts,
            on_account_select=self.on_account_select,
        )

        self.dispatch_service = DispatchService(self.append_log)
        self.dispatch_service.set_client_id(self.client_id)

        self.account_service = AccountService(
            root=self.root,
            accounts=self.accounts,
            append_log=self.append_log,
            update_accounts_list=self.update_accounts_list,
            save_accounts_config=self.save_accounts_config,
            get_headless=self.ui.is_headless,
            sync_dispatch_status_once=self.sync_dispatch_status_once,
        )
        self.task_service = TaskService(
            accounts=self.accounts,
            append_log=self.append_log,
            dispatch_service=self.dispatch_service,
            get_image_path=self.ui.get_image_path,
            get_headless=self.ui.is_headless,
            login_account=self.account_service.login_account_thread,
        )

        self.append_log("🚀 程序初始化开始")
        self.append_log("📂 加载账号配置")
        self.load_accounts_config()
        self.append_log("🔄 更新账号列表")
        self.update_accounts_list()
        self.append_log("💓 启动分派心跳循环")
        self.start_dispatch_heartbeat()
        self.append_log("📋 启动任务轮询循环")
        threading.Thread(target=self.task_polling_loop, daemon=True).start()
        self.append_log("✅ 程序初始化完成")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def append_log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        self.ui.append_log(line)

    def load_accounts_config(self) -> None:
        self.accounts.clear()
        self.accounts.extend(self.config_service.load_accounts())

    def save_accounts_config(self) -> None:
        self.config_service.save_accounts(self.accounts)

    def update_accounts_list(self) -> None:
        self.ui.update_accounts_list(self.accounts)

    def _selected_indices(self) -> List[int]:
        return self.ui.get_selected_indices()

    def on_account_select(self, event) -> None:
        selected_indices = self._selected_indices()
        if not selected_indices:
            self.ui.reset_selected_account_info()
            return

        account = self.accounts[selected_indices[0]]
        self.ui.set_selected_account_info(account.email, account.login_status, account.login_count, account.task_status)

    def add_account(self) -> None:
        self.account_service.add_account()

    def edit_account(self) -> None:
        selected_indices = self._selected_indices()
        if not selected_indices:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先选择要编辑的账号")
            return
        self.account_service.edit_account(selected_indices[0])

    def delete_account(self) -> None:
        selected_indices = self._selected_indices()
        if not selected_indices:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先选择要删除的账号")
            return

        index = selected_indices[0]
        account = self.accounts[index]
        from tkinter import messagebox
        if messagebox.askyesno("确认", f"确定要删除账号: {account.email}?"):
            self.account_service.delete_account(index)

    def run_task_on_selected(self) -> None:
        selected_indices = self._selected_indices()
        if not selected_indices:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先选择要执行任务的账号")
            return

        skus = self.ui.get_skus()
        selected_accounts = [self.accounts[i] for i in selected_indices]

        def _runner():
            try:
                self.task_service.run_task_on_accounts(skus, selected_accounts)
            except Exception as exc:
                self.append_log(f"❌ 执行本地任务失败: {exc}")

        threading.Thread(target=_runner, daemon=True).start()

    def _logged_in_accounts(self) -> List[str]:
        return [a.email for a in self.accounts if a.login_status == "已登录" and a.validate()]

    def sync_dispatch_status_once(self) -> None:
        self.dispatch_service.sync_status_once(self._logged_in_accounts())

    def dispatch_heartbeat_loop(self) -> None:
        from services.dispatch_service import HEARTBEAT_INTERVAL

        self.append_log(f"🚀 启动分派心跳循环，间隔: {HEARTBEAT_INTERVAL}秒")
        while not self._heartbeat_stop.is_set():
            try:
                self.sync_dispatch_status_once()
            except Exception as e:
                self.append_log(f"❌ 分派心跳循环出错: {str(e)}")
            self._heartbeat_stop.wait(HEARTBEAT_INTERVAL)
        self.append_log("🛑 分派心跳循环已停止")

    def start_dispatch_heartbeat(self) -> None:
        threading.Thread(target=self.dispatch_heartbeat_loop, daemon=True).start()

    def pull_task_from_dispatch(self) -> Optional[dict]:
        return self.dispatch_service.pull_task()

    def task_polling_loop(self) -> None:
        self.append_log("🚀 启动任务轮询循环")
        while not self._heartbeat_stop.is_set():
            try:
                if self._logged_in_accounts():
                    task = self.pull_task_from_dispatch()
                    if task:
                        self.append_log(f"📋 处理任务: {task.get('id', '未知ID')}")
                        self.task_service.run_task_from_dispatch(task)
            except Exception as e:
                self.append_log(f"❌ 任务轮询循环出错: {str(e)}")
            self._heartbeat_stop.wait(10)
        self.append_log("🛑 任务轮询循环已停止")

    def login_selected_accounts(self) -> None:
        selected_indices = self._selected_indices()
        if not selected_indices:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先选择要登录的账号")
            return

        self.account_service.login_selected_accounts(selected_indices)

    def close_selected_accounts(self) -> None:
        selected_indices = self._selected_indices()
        if not selected_indices:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先选择要关闭的账号")
            return

        self.account_service.close_selected_accounts(selected_indices)

    def on_close(self) -> None:
        from tkinter import messagebox

        if messagebox.askyesno("确认", "确定要退出程序吗？"):
            self._heartbeat_stop.set()
            try:
                self.dispatch_service.mark_client_offline()
            except Exception:
                pass

            try:
                close_all_sessions()
            except Exception:
                pass

            self.root.destroy()


def main() -> None:
    print("=== Ozon SKU 上传工具 启动 ===")
    print(f"分派服务器地址: {DISPATCH_SERVER}")
    print(f"客户端ID: {resolve_client_id()}")

    os.makedirs("accounts", exist_ok=True)

    root = tk.Tk()
    app = OzonMultiApp(root)

    set_logger(app.append_log)

    app.append_log("=== Ozon SKU 上传工具 启动 ===")
    app.append_log(f"分派服务器地址: {DISPATCH_SERVER}")
    app.append_log(f"客户端ID: {app.client_id}")

    root.mainloop()
    app.append_log("=== 程序退出 ===")


if __name__ == "__main__":
    main()
