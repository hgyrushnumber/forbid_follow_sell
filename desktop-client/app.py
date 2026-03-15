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

from dataclasses import dataclass, field
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext
from typing import List, Optional
from imapclient import IMAPClient

from email_otp import get_imap_server
from ozon_core import (
    close_all_sessions,
    close_session,
    prepare_browser,
    run_task,
    set_logger,
)


DISPATCH_SERVER = os.environ.get("DISPATCH_SERVER", "http://127.0.0.1:18080")
HEARTBEAT_INTERVAL = 15


@dataclass
class AccountInfo:
    """账号信息数据模型"""

    email: str
    imap_password: str = ""
    storage_path: Optional[str] = field(default=None)
    is_selected: bool = False
    login_status: str = "未登录"   # 未登录 / 登录中 / 已登录 / 登录失败
    task_status: str = "空闲"     # 空闲 / 执行中 / 完成 / 失败
    last_login: float = 0
    login_count: int = 0
    last_error: str = ""

    def __post_init__(self) -> None:
        if self.storage_path is None:
            safe_email = self.email.replace("@", "_").replace(".", "_")
            self.storage_path = os.path.join("accounts", f"ozon_auth_{safe_email}.json")

    def validate(self) -> bool:
        """验证账号信息是否完整"""
        return bool(self.email.strip() and self.imap_password.strip())


# def get_latest_mail_id(email_addr: str, email_pass: str, imap_server: str) -> dict:

#     print("正在获取当前邮箱最新邮件 ID...")

#     mail = None
#     try:
#         mail = imaplib.IMAP4_SSL(imap_server, 993)
#         mail.login(email_addr, email_pass)
#         print("✅ 邮箱登录成功")
#         # 先告诉 imaplib 我们要用 ID 命令（它默认不在命令表里）
#         imaplib.Commands['ID'] = ('AUTH', 'SELECTED')   # 或 ('NONAUTH',) 也可以

#         # 构造一个假的但常见的客户端身份（name / version 随便写，但要发）
#         # 很多客户端这样写都能过，写得太离谱反而可能被拒
#         typ, data = mail._simple_command(
#             'ID',
#             '("name" "Python-IMAPClient" "version" "1.0" "vendor" "CustomApp" "os" "Windows")'
#         )

#         print(f"发送 ID 命令结果: {typ}, {data}")

#         # 如果 typ == 'OK' 最好，如果 'BAD'/'NO' 也可以继续（网易对 ID 失败通常是宽容的）

#         try:
#             cap_status, caps = mail.capability()
#             print(f"CAPABILITY: {cap_status}, {caps}")
#         except Exception as e:
#             print(f"⚠️ 获取 CAPABILITY 失败: {e}")

#         try:
#             typ, data = mail.select("INBOX")
#             print(f"SELECT 状态: {typ}, 数据: {data}")
#         except Exception as e:
#             print(f"❌ SELECT INBOX 异常: {e}")
#             return {
#                 "success": False,
#                 "message": f"打开 INBOX 失败: {e}",
#                 "latest_mail_id": None,
#             }

#         if typ != "OK":
#             server_msg = ""
#             if data:
#                 try:
#                     server_msg = (
#                         data[0].decode("utf-8", errors="ignore")
#                         if isinstance(data[0], bytes)
#                         else str(data[0])
#                     )
#                 except Exception:
#                     server_msg = str(data)

#             return {
#                 "success": False,
#                 "message": f"无法打开邮箱目录: {server_msg}",
#                 "latest_mail_id": None,
#             }

#         search_status, search_data = mail.search(None, "ALL")
#         print(f"SEARCH 状态: {search_status}, 数据: {search_data}")

#         if search_status != "OK":
#             return {
#                 "success": False,
#                 "message": "无法读取邮件列表",
#                 "latest_mail_id": None,
#             }

#         ids = search_data[0].split() if search_data and search_data[0] else []
#         if not ids:
#             return {
#                 "success": True,
#                 "message": "邮箱连接成功，但邮箱内暂无邮件",
#                 "latest_mail_id": None,
#             }

#         latest_id = ids[-1]
#         if isinstance(latest_id, bytes):
#             latest_id = latest_id.decode(errors="ignore")

#         print(f"✅ 当前最新邮件 ID: {latest_id}")

#         return {
#             "success": True,
#             "message": "邮箱连接成功，能够正常读取邮件列表",
#             "latest_mail_id": latest_id,
#         }

#     except Exception as e:
#         print(f"❌ 获取最新邮件 ID 失败: {e}")
#         return {
#             "success": False,
#             "message": str(e),
#             "latest_mail_id": None,
#         }

#     finally:
#         if mail is not None:
#             try:
#                 mail.logout()
#             except Exception:
#                 pass


def get_latest_mail_id(email_addr: str, email_pass: str, imap_server: str) -> dict:
    print("正在获取当前邮箱最新邮件 ID...")

    try:
        # 使用 with 自动管理连接和登出
        with IMAPClient(imap_server, ssl=True, port=993) as client:
            print(f"正在连接 IMAP 服务器: {imap_server}")

            # 关键步骤：网易163必须发送 ID 命令，否则 SELECT 会报 Unsafe Login
            client.id_({
                'name': 'Ozon Upload Tool',
                'version': '1.0',
                'vendor': 'CustomApp',
                'os': 'Windows',
            })
            print("已发送 ID 命令（绕过网易 Unsafe Login 保护）")

            # 登录
            client.login(email_addr, email_pass)
            print("✅ 邮箱登录成功")

            # 选择收件箱
            client.select_folder('INBOX')
            print("已打开 INBOX")

            # 获取所有邮件 ID
            messages = client.search(['ALL'])
            if not messages:
                return {
                    "success": True,
                    "message": "邮箱连接成功，但暂无邮件",
                    "latest_mail_id": None,
                }

            latest_id = max(messages)  # 最大的 ID 就是最新邮件
            print(f"✅ 当前最新邮件 ID: {latest_id}")

            return {
                "success": True,
                "message": "邮箱连接成功，能够正常读取邮件列表",
                "latest_mail_id": str(latest_id),
            }

    except Exception as e:
        error_str = str(e).lower()
        print(f"❌ 获取最新邮件 ID 失败: {e}")

        if "unsafe login" in error_str:
            msg = "网易邮箱拒绝访问（Unsafe Login），可能是 ID 命令未发送或风控触发"
        elif "login" in error_str or "auth" in error_str:
            msg = "认证失败，请检查邮箱 + 授权码是否正确"
        elif "connect" in error_str or "timeout" in error_str:
            msg = f"无法连接到 {imap_server}，请检查网络或服务器地址"
        else:
            msg = str(e)

        return {
            "success": False,
            "message": msg,
            "latest_mail_id": None,
        }

class AccountDialog(tk.Toplevel):
    """账号管理对话框"""

    def __init__(self, parent, app, account: Optional[AccountInfo] = None):
        super().__init__(parent)
        self.title("添加 Ozon 账号" if account is None else "编辑 Ozon 账号")
        self.app = app
        self.result: Optional[AccountInfo] = None

        self.email_var = tk.StringVar(value=account.email if account else "")
        self.imap_pwd_var = tk.StringVar(value=account.imap_password if account else "")
        self.storage_path_var = tk.StringVar(value=account.storage_path if account else "")

        self._build_ui()

        self.grab_set()
        self.wait_window()

    def _build_ui(self) -> None:
        """构建对话框 UI"""
        tk.Label(self, text="邮箱地址:").grid(row=0, column=0, padx=10, pady=8, sticky="e")
        tk.Entry(self, textvariable=self.email_var, width=50).grid(row=0, column=1, padx=10, pady=8)

        tk.Label(self, text="IMAP授权码:").grid(row=1, column=0, padx=10, pady=8, sticky="e")
        self.imap_entry = tk.Entry(self, textvariable=self.imap_pwd_var, width=50, show="•")
        self.imap_entry.grid(row=1, column=1, padx=10, pady=8)

        self.show_pwd_btn = tk.Button(self, text="显示", command=self.toggle_show_password)
        self.show_pwd_btn.grid(row=1, column=2, padx=5, pady=8)

        tk.Label(self, text="登录态保存路径:").grid(row=2, column=0, padx=10, pady=8, sticky="e")
        tk.Entry(self, textvariable=self.storage_path_var, width=40).grid(row=2, column=1, padx=5, pady=8)
        tk.Button(self, text="自动生成", command=self.auto_generate_path).grid(row=2, column=2, padx=5, pady=8)

        help_text = (
            "📝 说明：\n"
            "1. 邮箱地址: 您的 Ozon 登录邮箱\n"
            "2. IMAP授权码: 邮箱客户端授权密码\n"
            "   - 163邮箱: 设置 → POP3/SMTP/IMAP → 开启 IMAP\n"
            "   - QQ邮箱: 设置 → 账户 → 开启 POP3/IMAP/SMTP 服务\n"
        )
        tk.Label(self, text=help_text, justify="left", fg="gray").grid(
            row=3,
            column=0,
            columnspan=3,
            padx=10,
            pady=5,
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=3, padx=10, pady=10)

        tk.Button(btn_frame, text="测试连接", command=self.test_connection).pack(side="left", padx=10)
        tk.Button(btn_frame, text="保存", command=self.save).pack(side="left", padx=10)
        tk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=10)

    def auto_generate_path(self) -> None:
        """自动生成存储路径"""
        email = self.email_var.get().strip()
        if not email:
            return

        safe_email = email.replace("@", "_").replace(".", "_")
        path = os.path.join("accounts", f"ozon_auth_{safe_email}.json")
        self.storage_path_var.set(path)

    def test_connection(self) -> None:
        """测试邮箱连接"""
        email_addr = self.email_var.get().strip()
        imap_pwd = self.imap_pwd_var.get().strip()

        if not email_addr or not imap_pwd:
            messagebox.showwarning("提示", "请先填写邮箱和 IMAP 授权码")
            return

        try:
            imap_server = get_imap_server(email_addr)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在测试邮箱: {email_addr}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IMAP服务器: {imap_server}")

            result = get_latest_mail_id(email_addr, imap_pwd, imap_server)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] 测试结果: {result}")

            if result["success"]:
                if result["latest_mail_id"] is not None:
                    messagebox.showinfo(
                        "成功",
                        f"✅ 邮箱连接测试成功！\n"
                        f"{result['message']}\n"
                        f"最新邮件ID: {result['latest_mail_id']}"
                    )
                else:
                    messagebox.showinfo(
                        "成功",
                        f"✅ 邮箱连接测试成功！\n{result['message']}"
                    )
            else:
                error_msg = result["message"].lower()

                if "unsafe login" in error_msg:
                    messagebox.showerror(
                        "失败",
                        "❌ 邮箱服务器拒绝读取收件箱（Unsafe Login）\n"
                        "这通常是邮箱服务商的安全风控导致的，请检查邮箱安全设置或联系邮箱客服。"
                    )
                elif "authentication failed" in error_msg or "invalid credentials" in error_msg:
                    messagebox.showerror("失败", "❌ 认证失败，请检查 IMAP 授权码是否正确")
                elif "timed out" in error_msg or "connection refused" in error_msg:
                    messagebox.showerror("失败", f"❌ 无法连接到 IMAP 服务器: {imap_server}")
                else:
                    messagebox.showerror("失败", f"❌ 邮箱连接失败: {result['message']}")

        except Exception:
            error_details = traceback.format_exc()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 完整错误信息:")
            print(error_details)
            messagebox.showerror("失败", "❌ 邮箱连接测试过程中发生异常，请查看控制台日志")

    def toggle_show_password(self) -> None:
        """切换 IMAP 授权码显示/隐藏"""
        if self.imap_entry.cget("show") == "•":
            self.imap_entry.config(show="")
            self.show_pwd_btn.config(text="隐藏")
        else:
            self.imap_entry.config(show="•")
            self.show_pwd_btn.config(text="显示")

    def save(self) -> None:
        """保存账号信息"""
        email = self.email_var.get().strip()
        imap_pwd = self.imap_pwd_var.get().strip()
        storage_path = self.storage_path_var.get().strip()

        if not email:
            messagebox.showwarning("提示", "邮箱地址不能为空")
            return

        if not imap_pwd:
            messagebox.showwarning("提示", "IMAP 授权码不能为空")
            return

        self.result = AccountInfo(
            email=email,
            imap_password=imap_pwd,
            storage_path=storage_path or None,
        )
        self.destroy()


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

        self.load_accounts_config()
        self.build_ui()
        self.update_accounts_list()
        self.start_dispatch_heartbeat()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_accounts_config(self) -> None:
        """从配置文件加载账号信息"""
        config_file = "ozon_accounts_config.json"

        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    accounts_data = json.load(f)

                for data in accounts_data:
                    try:
                        account = AccountInfo(
                            email=data["email"],
                            imap_password=data.get("imap_password", ""),
                            storage_path=data.get("storage_path"),
                        )
                        account.is_selected = data.get("is_selected", False)
                        account.login_status = data.get("login_status", "未登录")
                        account.last_login = data.get("last_login", 0)
                        account.login_count = data.get("login_count", 0)
                        account.last_error = data.get("last_error", "")
                        self.accounts.append(account)
                    except Exception as exc:
                        print(f"加载账号失败: {exc}")
            except Exception as exc:
                print(f"加载配置文件失败: {exc}")

        if not self.accounts:
            default_account = AccountInfo(
                email="xpw709@163.com",
                imap_password="UE4NLW7W2X4NzunU",
            )
            self.accounts.append(default_account)

        self.save_accounts_config()

    def save_accounts_config(self) -> None:
        """保存账号配置到文件"""
        config_file = "ozon_accounts_config.json"

        accounts_data = []
        for account in self.accounts:
            accounts_data.append(
                {
                    "email": account.email,
                    "imap_password": account.imap_password,
                    "storage_path": account.storage_path,
                    "is_selected": account.is_selected,
                    "login_status": account.login_status,
                    "last_login": account.last_login,
                    "login_count": account.login_count,
                    "last_error": account.last_error,
                }
            )

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(accounts_data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.append_log(f"保存配置失败: {exc}")

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

        tk.Label(config_frame, text="Excel文件:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.excel_var = tk.StringVar(value="sku.xlsx")
        tk.Entry(config_frame, textvariable=self.excel_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(config_frame, text="浏览", command=self.choose_excel).grid(row=0, column=2, padx=5, pady=5)

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
        dialog = AccountDialog(self.root, self)
        if dialog.result:
            self.accounts.append(dialog.result)
            self.update_accounts_list()
            self.save_accounts_config()

    def edit_account(self) -> None:
        """编辑选中的账号"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要编辑的账号")
            return

        index = selected_indices[0]
        dialog = AccountDialog(self.root, self, self.accounts[index])
        if dialog.result:
            self.accounts[index] = dialog.result
            self.update_accounts_list()
            self.save_accounts_config()

    def delete_account(self) -> None:
        """删除选中的账号"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要删除的账号")
            return

        index = selected_indices[0]
        account = self.accounts[index]

        if messagebox.askyesno("确认", f"确定要删除账号: {account.email}?"):
            try:
                close_session(account.email)
            except Exception as exc:
                self.append_log(f"关闭会话时出错: {exc}")

            del self.accounts[index]
            self.update_accounts_list()
            self.save_accounts_config()

    def choose_excel(self) -> None:
        """选择 Excel 文件"""
        path = filedialog.askopenfilename(
            filetypes=[("Excel 文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if path:
            self.excel_var.set(path)

    def choose_image(self) -> None:
        """选择图片文件"""
        path = filedialog.askopenfilename(
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg"), ("所有文件", "*.*")]
        )
        if path:
            self.image_var.set(path)

    def _dispatch_post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            DISPATCH_SERVER + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))

    def _logged_in_accounts(self) -> List[str]:
        return [a.email for a in self.accounts if a.login_status == "已登录" and a.validate()]

    def sync_dispatch_status_once(self) -> None:
        accounts = self._logged_in_accounts()
        if not accounts:
            return
        self._dispatch_post("/api/clients/register", {"client_id": self.client_id, "accounts": accounts})
        self._dispatch_post("/api/clients/heartbeat", {"client_id": self.client_id, "accounts": accounts})

    def dispatch_heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.is_set():
            try:
                self.sync_dispatch_status_once()
            except Exception:
                pass
            self._heartbeat_stop.wait(HEARTBEAT_INTERVAL)

    def start_dispatch_heartbeat(self) -> None:
        threading.Thread(target=self.dispatch_heartbeat_loop, daemon=True).start()

    def append_log(self, msg: str) -> None:
        """添加日志"""
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def login_account_thread(self, account: AccountInfo) -> None:
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
                headless=self.headless_var.get(),
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

    def login_selected_accounts(self) -> None:
        """登录选中的账号"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要登录的账号")
            return

        for index in selected_indices:
            account = self.accounts[index]
            threading.Thread(
                target=self.login_account_thread,
                args=(account,),
                daemon=True,
            ).start()

    def run_task_thread(self, account: AccountInfo) -> None:
        """执行任务线程"""
        if not account.validate():
            self.append_log(f"❌ 账号信息不完整: {account.email}")
            return

        excel_path = self.excel_var.get().strip()
        image_path = self.image_var.get().strip()

        if not os.path.exists(excel_path):
            self.append_log(f"❌ Excel 文件不存在: {excel_path}")
            return

        if not os.path.exists(image_path):
            self.append_log(f"❌ 图片文件不存在: {image_path}")
            return

        try:
            account.task_status = "执行中"
            self.update_accounts_list()
            self.append_log(f"🚀 开始在账号 {account.email} 上执行任务")

            run_task(
                email=account.email,
                excel_path=excel_path,
                image_path=image_path,
                imap_password=account.imap_password,
                storage_path=account.storage_path,
                headless=self.headless_var.get(),
            )

            account.task_status = "完成"
            self.append_log(f"✅ 任务执行完成: {account.email}")

        except Exception as exc:
            account.task_status = "失败"
            self.append_log(f"❌ 任务执行失败: {account.email}, {exc}")

        finally:
            account.task_status = "空闲"
            self.update_accounts_list()
            self.save_accounts_config()

    def run_task_on_selected(self) -> None:
        """在选中的账号上执行任务"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要执行任务的账号")
            return

        for index in selected_indices:
            account = self.accounts[index]

            if account.login_status != "已登录":
                self.append_log(f"⚠️ 账号未登录: {account.email}，请先登录")
                continue

            threading.Thread(
                target=self.run_task_thread,
                args=(account,),
                daemon=True,
            ).start()

    def close_selected_accounts(self) -> None:
        """关闭选中账号会话"""
        selected_indices = self.accounts_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("提示", "请先选择要关闭的账号")
            return

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

    def on_close(self) -> None:
        """窗口关闭事件"""
        if messagebox.askyesno("确认", "确定要退出程序吗？"):
            self._heartbeat_stop.set()
            try:
                self._dispatch_post("/api/clients/offline", {"client_id": self.client_id})
            except Exception:
                pass

            try:
                close_all_sessions()
            except Exception:
                pass

            self.root.destroy()


def main() -> None:
    """程序入口"""
    os.makedirs("accounts", exist_ok=True)

    root = tk.Tk()
    app = OzonMultiApp(root)

    set_logger(app.append_log)

    root.mainloop()


if __name__ == "__main__":
    main()