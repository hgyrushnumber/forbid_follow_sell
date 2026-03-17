#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
多账号版 Ozon SKU 上传工具 - 基于邮箱 + IMAP 授权码登录
"""

import imaplib
import json
import os
import threading
import traceback
import tkinter as tk
import socket
import time
import urllib.request
from dotenv import load_dotenv
from services import ConfigService

# 加载.env配置文件
load_dotenv()

from dataclasses import dataclass, field
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext
from typing import List, Optional
from imapclient import IMAPClient

from email_otp import get_imap_server
from models import AccountInfo
from ui.account_dialog import AccountDialog
from services.mail_service import get_latest_mail_id
from services.dispatch_service import DispatchService
from services.task_service import TaskService
from services.account_service import AccountService
from ozon_core import (
    close_all_sessions,
    close_session,
    prepare_browser,
    run_task,
    set_logger,
)


DISPATCH_SERVER = os.environ.get("DISPATCH_SERVER", "https://www.rus2cn.com")
HEARTBEAT_INTERVAL = 15





class OzonMultiApp:
    """多账号版 Ozon SKU 上传工具"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Ozon SKU 上传工具 - 多账号管理")
        self.root.geometry("1200x800")

        self.accounts: List[AccountInfo] = []
        self.browser_ready = False
        self.task_running = False
        self.client_id = f"{socket.gethostname()}-{os.getpid()}"
        self._heartbeat_stop = threading.Event()
        # 初始化分派服务
        self.dispatch_service = DispatchService(self.append_log)
        self.dispatch_service.set_client_id(self.client_id)
        self.task_service = TaskService(self)
        self.account_service = AccountService(self)
        self.accounts = self.account_service.accounts

        # 先构建UI，确保log_text存在
        self.build_ui()

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
        self.config_service = ConfigService()

    def build_ui(self) -> None:
        """构建 UI 界面"""
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.LabelFrame(paned_window, text="账号管理")
        paned_window.add(left_frame, width=400)

        self.accounts_listbox = tk.Listbox(left_frame, width=50, height=20, selectmode=tk.MULTIPLE)
        self.accounts_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.accounts_listbox.bind("<<ListboxSelect>>", self.on_account_select)

        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Button(btn_frame, text="➕ 添加账号", command=self.add_account).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✏️ 编辑账号", command=self.edit_account).pack(side="left", padx=2)
        tk.Button(btn_frame, text="🗑️ 删除账号", command=self.delete_account).pack(side="left", padx=2)
        tk.Button(btn_frame, text="🔄 刷新列表", command=self.update_accounts_list).pack(side="left", padx=2)

        info_frame = tk.LabelFrame(left_frame, text="账号详情")
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(info_frame, text="当前选中:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.selected_account_var = tk.StringVar(value="无")
        tk.Label(info_frame, textvariable=self.selected_account_var, fg="blue").grid(
            row=0, column=1, padx=5, pady=2, sticky="w"
        )

        tk.Label(info_frame, text="登录状态:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.login_status_var = tk.StringVar(value="未登录")
        tk.Label(info_frame, textvariable=self.login_status_var).grid(
            row=1, column=1, padx=5, pady=2, sticky="w"
        )

        tk.Label(info_frame, text="登录次数:").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.login_count_var = tk.StringVar(value="0")
        tk.Label(info_frame, textvariable=self.login_count_var).grid(
            row=2, column=1, padx=5, pady=2, sticky="w"
        )

        right_frame = tk.LabelFrame(paned_window, text="任务执行")
        paned_window.add(right_frame)

        config_frame = tk.LabelFrame(right_frame, text="任务配置")
        config_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(config_frame, text="SKU列表:").grid(row=0, column=0, padx=5, pady=5, sticky="ne")
        self.sku_text_var = tk.StringVar(value="")
        sku_text = tk.Text(config_frame, height=6, width=50)
        sku_text.grid(row=0, column=1, padx=5, pady=5)
        sku_text.insert(tk.END, "SKU001\nSKU002,SKU003\nSKU004")  # 示例文本

        tk.Label(config_frame, text="图片文件:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.image_var = tk.StringVar(value="icon.png")
        tk.Entry(config_frame, textvariable=self.image_var, width=40).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(config_frame, text="浏览", command=self.choose_image).grid(row=1, column=2, padx=5, pady=5)

        self.headless_var = tk.BooleanVar(value=False)
        tk.Checkbutton(config_frame, text="无头模式", variable=self.headless_var).grid(
            row=2, column=0, columnspan=3, padx=5, pady=5
        )

        action_frame = tk.Frame(right_frame)
        action_frame.pack(fill=tk.X, padx=10, pady=10)

        self.login_btn = tk.Button(action_frame, text="🚀 登录选中账号", command=self.login_selected_accounts)
        self.login_btn.pack(fill=tk.X, padx=5, pady=2)

        self.task_btn = tk.Button(action_frame, text="🎯 执行任务到选中账号", command=self.run_task_on_selected)
        self.task_btn.pack(fill=tk.X, padx=5, pady=2)

        self.close_btn = tk.Button(action_frame, text="🛑 关闭选中账号", command=self.close_selected_accounts)
        self.close_btn.pack(fill=tk.X, padx=5, pady=2)

        log_frame = tk.LabelFrame(right_frame, text="运行日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, padx=10, pady=2
        )

    def update_accounts_list(self) -> None:
        """更新账号列表显示"""
        self.accounts_listbox.delete(0, tk.END)

        for account in self.accounts:
            status_icon = "✅" if account.login_status == "已登录" else "🔴"
            display_text = f"{status_icon} {account.email}"

            self.accounts_listbox.insert(tk.END, display_text)
            last_index = self.accounts_listbox.size() - 1

            if account.login_status == "已登录":
                self.accounts_listbox.itemconfig(last_index, {"fg": "green"})
            elif account.login_status == "登录中":
                self.accounts_listbox.itemconfig(last_index, {"fg": "blue"})
            elif account.login_status == "登录失败":
                self.accounts_listbox.itemconfig(last_index, {"fg": "red"})
            else:
                self.accounts_listbox.itemconfig(last_index, {"fg": "black"})

        total = len(self.accounts)
        logged_in = sum(1 for acc in self.accounts if acc.login_status == "已登录")
        self.status_var.set(f"就绪 - 共 {total} 个账号, {logged_in} 个已登录")

    def on_account_select(self, event) -> None:
        """账号选中事件"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            self.selected_account_var.set("无")
            self.login_status_var.set("未登录")
            self.login_count_var.set("0")
            return

        index = selected_indices[0]
        account = self.accounts[index]

        self.selected_account_var.set(account.email)
        self.login_status_var.set(account.login_status)
        self.login_count_var.set(str(account.login_count))

    def add_account(self) -> None:
        """添加新账号"""
        self.account_service.add_account()

    def edit_account(self) -> None:
        """编辑选中的账号"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要编辑的账号")
            return

        index = selected_indices[0]
        self.account_service.edit_account(index)

    def delete_account(self) -> None:
        """删除选中的账号"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要删除的账号")
            return

        index = selected_indices[0]
        account = self.accounts[index]

        if messagebox.askyesno("确认", f"确定要删除账号: {account.email}?"):
            self.account_service.delete_account(index)

    def choose_image(self) -> None:
        """选择图片文件"""
        path = filedialog.askopenfilename(
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg"), ("所有文件", "*.*")]
        )
        if path:
            self.image_var.set(path)



    def pull_task_from_dispatch(self) -> Optional[dict]:
        return self.dispatch_service.pull_task()

    def _logged_in_accounts(self) -> List[str]:
        return [a.email for a in self.accounts if a.login_status == "已登录" and a.validate()]

    def sync_dispatch_status_once(self) -> None:
        try:
            accounts = self._logged_in_accounts()
            self.dispatch_service.sync_status_once(accounts)
        except Exception as e:
            self.append_log(f"❌ 同步分派状态失败: {str(e)}")
            raise

    def dispatch_heartbeat_loop(self) -> None:
        from services.dispatch_service import HEARTBEAT_INTERVAL
        self.append_log(f"🚀 启动分派心跳循环，间隔: {HEARTBEAT_INTERVAL}秒")
        while not self._heartbeat_stop.is_set():
            try:
                self.append_log(f"🔄 开始第 {time.strftime('%H:%M:%S')} 次分派状态同步")
                self.sync_dispatch_status_once()
                self.append_log(f"✅ 第 {time.strftime('%H:%M:%S')} 次分派状态同步完成")
            except Exception as e:
                self.append_log(f"❌ 分派心跳循环出错: {str(e)}")
            self.append_log(f"⏳ 等待 {HEARTBEAT_INTERVAL} 秒后下次同步")
            self._heartbeat_stop.wait(HEARTBEAT_INTERVAL)
        self.append_log("🛑 分派心跳循环已停止")

    def start_dispatch_heartbeat(self) -> None:
        threading.Thread(target=self.dispatch_heartbeat_loop, daemon=True).start()

    def task_polling_loop(self) -> None:
        self.append_log("🚀 启动任务轮询循环")
        while not self._heartbeat_stop.is_set():
            try:
                # 只在有登录账号的情况下拉取任务
                if self._logged_in_accounts():
                    task = self.pull_task_from_dispatch()
                    if task:
                        self.append_log(f"📋 处理任务: {task.get('id', '未知ID')}")
                        # 标记任务为运行中
                        self.dispatch_service.mark_task_running(task['id'])
                        # 执行任务
                        self.run_task_from_dispatch(task)
                else:
                    self.append_log("⚠️ 没有登录的账号，跳过任务拉取")
            except Exception as e:
                self.append_log(f"❌ 任务轮询循环出错: {str(e)}")
            # 每10秒轮询一次
            self._heartbeat_stop.wait(10)
        self.append_log("🛑 任务轮询循环已停止")

    def run_task_from_dispatch(self, task: dict):
        """处理从分派服务拉取的任务"""
        self.task_service.run_task_from_dispatch(task)
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
                self.login_account_thread(target_account)
                if target_account.login_status != "已登录":
                    self.append_log(f"❌ 账号 {account} 登录失败，无法执行任务")
                    self._dispatch_post(f"/api/clients/{self.client_id}/tasks/{task_id}/complete", {
                        "success": False,
                        "error": f"账号 {account} 登录失败"
                    })
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
            from ozon_core import run_task_with_skus

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

    def append_log(self, msg: str) -> None:
        """添加日志"""
        try:
            if hasattr(self, 'log_text') and self.log_text is not None:
                self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
                self.log_text.see(tk.END)
                if hasattr(self, 'root') and self.root:
                    self.root.update_idletasks()
            else:
                # 如果log_text还不存在，先打印到控制台
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        except Exception as e:
            # 如果日志系统失败，至少打印到控制台
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg} (日志显示失败: {e})")

    def login_account_thread(self, account: AccountInfo) -> None:
        """账号登录线程"""
        self.account_service.login_account_thread(account)

    def login_selected_accounts(self) -> None:
        """登录选中的账号"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要登录的账号")
            return

        self.account_service.login_selected_accounts(selected_indices)



    def close_selected_accounts(self) -> None:
        """关闭选中账号会话"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要关闭的账号")
            return

        self.account_service.close_selected_accounts(selected_indices)

    def on_close(self) -> None:
        """窗口关闭事件"""
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
    """程序入口"""
    print(f"=== Ozon SKU 上传工具 启动 ===")
    print(f"分派服务器地址: {DISPATCH_SERVER}")
    print(f"客户端ID: {socket.gethostname()}-{os.getpid()}")

    os.makedirs("accounts", exist_ok=True)

    root = tk.Tk()
    app = OzonMultiApp(root)

    # 先设置logger，确保所有日志都能被正确记录
    set_logger(app.append_log)

    # 现在可以记录日志了
    app.append_log("=== Ozon SKU 上传工具 启动 ===")
    app.append_log(f"分派服务器地址: {DISPATCH_SERVER}")
    app.append_log(f"客户端ID: {app.client_id}")

    root.mainloop()

    app.append_log("=== 程序退出 ===")


if __name__ == "__main__":
    main()