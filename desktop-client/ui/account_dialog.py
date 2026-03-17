#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import messagebox
import os
from typing import Optional
from models import AccountInfo


class AccountDialog(tk.Toplevel):
    """账号管理对话框（手动验证码模式）"""

    def __init__(self, parent, app, account: Optional[AccountInfo] = None):
        super().__init__(parent)
        self.title("添加 Ozon 账号" if account is None else "编辑 Ozon 账号")
        self.app = app
        self.result: Optional[AccountInfo] = None

        self.email_var = tk.StringVar(value=account.email if account else "")
        self.storage_path_var = tk.StringVar(value=account.storage_path if account else "")

        self._build_ui()

        self.grab_set()
        self.wait_window()

    def _build_ui(self) -> None:
        """构建对话框 UI"""
        tk.Label(self, text="邮箱地址:").grid(row=0, column=0, padx=10, pady=8, sticky="e")
        tk.Entry(self, textvariable=self.email_var, width=50).grid(row=0, column=1, padx=10, pady=8)

        tk.Label(self, text="登录态保存路径:").grid(row=1, column=0, padx=10, pady=8, sticky="e")
        tk.Entry(self, textvariable=self.storage_path_var, width=40).grid(row=1, column=1, padx=5, pady=8)
        tk.Button(self, text="自动生成", command=self.auto_generate_path).grid(row=1, column=2, padx=5, pady=8)

        help_text = (
            "📝 登录说明：\n"
            "1. 系统仅支持手动输入验证码登录（已取消 IMAP 密钥登录）。\n"
            "2. 登录过程中会弹窗提示输入邮箱收到的验证码。\n"
            "3. Outlook 等不支持 IMAP 授权码的邮箱可直接使用。\n"
        )
        tk.Label(self, text=help_text, justify="left", fg="gray").grid(
            row=2,
            column=0,
            columnspan=3,
            padx=10,
            pady=5,
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=3, padx=10, pady=10)

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

    def save(self) -> None:
        """保存账号信息"""
        email = self.email_var.get().strip()
        storage_path = self.storage_path_var.get().strip()

        if not email:
            messagebox.showwarning("提示", "邮箱地址不能为空")
            return

        self.result = AccountInfo(
            email=email,
            imap_password="",
            storage_path=storage_path or None,
            use_manual_login=True,
        )
        self.destroy()
