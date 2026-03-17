#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import filedialog, messagebox
import os
from datetime import datetime
import traceback
from typing import Optional
from models import AccountInfo
from email_otp import get_imap_server


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
        self.manual_login_var = tk.BooleanVar(value=account.use_manual_login if account else False)

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

        # 添加手动登录选项
        manual_login_checkbox = tk.Checkbutton(
            self,
            text="手动输入验证码（不使用IMAP）",
            variable=self.manual_login_var
        )
        manual_login_checkbox.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky="w")

        help_text = (
            "📝 说明：\n"
            "1. 邮箱地址: 您的 Ozon 登录邮箱\n"
            "2. IMAP授权码: 邮箱客户端授权密码\n"
            "   - 163邮箱: 设置 → POP3/SMTP/IMAP → 开启 IMAP\n"
            "   - QQ邮箱: 设置 → 账户 → 开启 POP3/IMAP/SMTP 服务\n"
            "3. 手动输入验证码: 如果您的邮箱不支持IMAP或IMAP授权码无法获取，请勾选此项，后续将手动输入收到的验证码\n"
        )
        tk.Label(self, text=help_text, justify="left", fg="gray").grid(
            row=5,
            column=0,
            columnspan=3,
            padx=10,
            pady=5,
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=3, padx=10, pady=10)

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

        # 如果是手动登录模式，不需要测试邮箱连接
        if self.manual_login_var.get():
            messagebox.showinfo("提示", "手动登录模式不需要测试邮箱连接")
            return

        imap_pwd = self.imap_pwd_var.get().strip()

        if not email_addr or not imap_pwd:
            messagebox.showwarning("提示", "请先填写邮箱和 IMAP 授权码")
            return

        try:
            imap_server = get_imap_server(email_addr)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在测试邮箱: {email_addr}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] IMAP服务器: {imap_server}")

            from app import get_latest_mail_id
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

        # 如果不是手动登录模式，则需要验证IMAP授权码
        if not self.manual_login_var.get() and not imap_pwd:
            messagebox.showwarning("提示", "IMAP 授权码不能为空")
            return

        self.result = AccountInfo(
            email=email,
            imap_password=imap_pwd,
            storage_path=storage_path or None,
            use_manual_login=self.manual_login_var.get(),
        )
        self.destroy()