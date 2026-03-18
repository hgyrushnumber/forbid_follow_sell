#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List

from models import AccountInfo


class MainWindow:
    """主窗口 UI 编排：只负责界面元素与交互呈现。"""

    BG_COLOR = "#f5f7fb"
    CARD_BG = "#ffffff"
    PRIMARY = "#2563eb"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"
    DANGER = "#dc2626"
    MUTED = "#6b7280"

    def __init__(
        self,
        root: tk.Tk,
        on_add_account: Callable[[], None],
        on_edit_account: Callable[[], None],
        on_delete_account: Callable[[], None],
        on_refresh_accounts: Callable[[], None],
        on_login_selected: Callable[[], None],
        on_run_task_selected: Callable[[], None],
        on_close_selected: Callable[[], None],
        on_account_select: Callable,
    ):
        self.root = root
        self.root.title("Ozon SKU 上传工具 - 多账号管理")
        self.root.geometry("1240x820")
        self.root.minsize(1080, 720)
        self.root.configure(bg=self.BG_COLOR)
        self._setup_style()
        self._build(
            on_add_account=on_add_account,
            on_edit_account=on_edit_account,
            on_delete_account=on_delete_account,
            on_refresh_accounts=on_refresh_accounts,
            on_login_selected=on_login_selected,
            on_run_task_selected=on_run_task_selected,
            on_close_selected=on_close_selected,
            on_account_select=on_account_select,
        )

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("App.TFrame", background=self.BG_COLOR)
        style.configure("Card.TLabelframe", background=self.CARD_BG, borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=self.CARD_BG, foreground="#111827", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Section.TLabel", background=self.CARD_BG, foreground="#111827", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Muted.TLabel", background=self.CARD_BG, foreground=self.MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Value.TLabel", background=self.CARD_BG, foreground="#111827", font=("Microsoft YaHei UI", 10))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(10, 8))
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 10), padding=(8, 6))
        style.configure("StatusBar.TLabel", background="#e5e7eb", foreground="#111827", font=("Microsoft YaHei UI", 10), padding=(10, 6))
        style.configure("Header.TLabel", background=self.BG_COLOR, foreground="#0f172a", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("SubHeader.TLabel", background=self.BG_COLOR, foreground=self.MUTED, font=("Microsoft YaHei UI", 10))

    def _build(self, **callbacks) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=12)
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Ozon 多账号投诉工作台", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="更稳定的账号管理、任务调度与运行日志视图", style="SubHeader.TLabel").pack(anchor="w", pady=(2, 0))

        paned_window = ttk.Panedwindow(shell, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.LabelFrame(paned_window, text="账号管理", style="Card.TLabelframe", padding=12)
        right_frame = ttk.LabelFrame(paned_window, text="任务执行", style="Card.TLabelframe", padding=12)
        paned_window.add(left_frame, weight=2)
        paned_window.add(right_frame, weight=3)

        self.accounts_listbox = tk.Listbox(
            left_frame,
            width=46,
            height=20,
            selectmode=tk.MULTIPLE,
            activestyle="none",
            bg="#f8fafc",
            fg="#111827",
            selectbackground="#dbeafe",
            selectforeground="#111827",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#d1d5db",
            font=("Microsoft YaHei UI", 10),
        )
        self.accounts_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.accounts_listbox.bind("<<ListboxSelect>>", callbacks["on_account_select"])

        btn_frame = ttk.Frame(left_frame, style="App.TFrame")
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(btn_frame, text="➕ 添加账号", command=callbacks["on_add_account"], style="Secondary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="✏️ 编辑账号", command=callbacks["on_edit_account"], style="Secondary.TButton").pack(side="left", padx=6)
        ttk.Button(btn_frame, text="🗑️ 删除账号", command=callbacks["on_delete_account"], style="Secondary.TButton").pack(side="left", padx=6)
        ttk.Button(btn_frame, text="🔄 刷新列表", command=callbacks["on_refresh_accounts"], style="Secondary.TButton").pack(side="left", padx=6)

        info_frame = ttk.LabelFrame(left_frame, text="账号详情", style="Card.TLabelframe", padding=12)
        info_frame.pack(fill=tk.X)
        info_frame.columnconfigure(1, weight=1)

        ttk.Label(info_frame, text="当前选中", style="Muted.TLabel").grid(row=0, column=0, padx=(0, 10), pady=4, sticky="e")
        self.selected_account_var = tk.StringVar(value="无")
        ttk.Label(info_frame, textvariable=self.selected_account_var, style="Value.TLabel").grid(row=0, column=1, pady=4, sticky="w")

        ttk.Label(info_frame, text="登录状态", style="Muted.TLabel").grid(row=1, column=0, padx=(0, 10), pady=4, sticky="e")
        self.login_status_var = tk.StringVar(value="未登录")
        ttk.Label(info_frame, textvariable=self.login_status_var, style="Value.TLabel").grid(row=1, column=1, pady=4, sticky="w")

        ttk.Label(info_frame, text="任务状态", style="Muted.TLabel").grid(row=2, column=0, padx=(0, 10), pady=4, sticky="e")
        self.task_status_var = tk.StringVar(value="空闲")
        ttk.Label(info_frame, textvariable=self.task_status_var, style="Value.TLabel").grid(row=2, column=1, pady=4, sticky="w")

        ttk.Label(info_frame, text="登录次数", style="Muted.TLabel").grid(row=3, column=0, padx=(0, 10), pady=4, sticky="e")
        self.login_count_var = tk.StringVar(value="0")
        ttk.Label(info_frame, textvariable=self.login_count_var, style="Value.TLabel").grid(row=3, column=1, pady=4, sticky="w")

        config_frame = ttk.LabelFrame(right_frame, text="任务配置", style="Card.TLabelframe", padding=12)
        config_frame.pack(fill=tk.X)
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="SKU 列表", style="Section.TLabel").grid(row=0, column=0, padx=(0, 10), pady=6, sticky="ne")
        self.sku_text = tk.Text(
            config_frame,
            height=7,
            width=52,
            bg="#f8fafc",
            fg="#111827",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#d1d5db",
            font=("Consolas", 10),
        )
        self.sku_text.grid(row=0, column=1, columnspan=2, padx=0, pady=6, sticky="ew")
        self.sku_text.insert(tk.END, "SKU001\nSKU002,SKU003\nSKU004")

        ttk.Label(config_frame, text="图片文件", style="Section.TLabel").grid(row=1, column=0, padx=(0, 10), pady=6, sticky="e")
        self.image_var = tk.StringVar(value="icon.png")
        self.image_var.trace_add("write", self._on_image_path_changed)
        ttk.Entry(config_frame, textvariable=self.image_var).grid(row=1, column=1, padx=0, pady=6, sticky="ew")
        ttk.Button(config_frame, text="浏览…", command=self.choose_image, style="Secondary.TButton").grid(row=1, column=2, padx=(8, 0), pady=6)

        self.image_hint_var = tk.StringVar(value="请确认图片文件存在后再执行任务")
        self.image_hint_label = tk.Label(config_frame, textvariable=self.image_hint_var, bg=self.CARD_BG, fg=self.MUTED, anchor="w", font=("Microsoft YaHei UI", 9))
        self.image_hint_label.grid(row=2, column=1, columnspan=2, pady=(0, 8), sticky="w")

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(config_frame, text="无头模式", variable=self.headless_var).grid(row=3, column=1, columnspan=2, pady=(2, 4), sticky="w")

        action_frame = ttk.LabelFrame(right_frame, text="快捷操作", style="Card.TLabelframe", padding=12)
        action_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(action_frame, text="🚀 登录选中账号", command=callbacks["on_login_selected"], style="Primary.TButton").pack(fill=tk.X, pady=4)
        ttk.Button(action_frame, text="🎯 执行任务到选中账号", command=callbacks["on_run_task_selected"], style="Primary.TButton").pack(fill=tk.X, pady=4)
        ttk.Button(action_frame, text="🛑 关闭选中账号", command=callbacks["on_close_selected"], style="Secondary.TButton").pack(fill=tk.X, pady=4)

        tips_frame = ttk.LabelFrame(right_frame, text="运行说明", style="Card.TLabelframe", padding=12)
        tips_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        tips = [
            "• 运行日志不再在界面实时渲染，统一写入日志文件，避免 desktop 卡顿。",
            "• 执行任务前请确认图片文件状态为“图片已就绪”。",
            "• 登录流程为：登录 -> 邮箱登录 -> 输入邮箱 -> 手动输入验证码。",
            "• 每个邮箱仅保留一个标签页，减少页面状态互相干扰。",
        ]
        for tip in tips:
            ttk.Label(tips_frame, text=tip, style="Muted.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=4)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(shell, textvariable=self.status_var, style="StatusBar.TLabel", anchor=tk.W).pack(fill=tk.X, pady=(10, 0))
        self._refresh_image_hint()

    def _on_image_path_changed(self, *_args) -> None:
        self._refresh_image_hint()

    def _refresh_image_hint(self) -> None:
        path = self.get_image_path()
        if path and os.path.exists(path):
            self.image_hint_var.set(f"图片已就绪：{path}")
            self.image_hint_label.configure(fg=self.SUCCESS)
        elif path:
            self.image_hint_var.set(f"图片不存在：{path}")
            self.image_hint_label.configure(fg=self.DANGER)
        else:
            self.image_hint_var.set("请先选择要上传的图片文件")
            self.image_hint_label.configure(fg=self.WARNING)

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("图片文件", "*.png;*.jpg;*.jpeg"), ("所有文件", "*.*")])
        if path:
            self.image_var.set(path)

    def clear_log(self) -> None:
        return

    def get_selected_indices(self) -> List[int]:
        return list(self.accounts_listbox.curselection())

    def set_selected_account_info(self, email: str, login_status: str, login_count: int, task_status: str = "空闲") -> None:
        self.selected_account_var.set(email)
        self.login_status_var.set(login_status)
        self.login_count_var.set(str(login_count))
        self.task_status_var.set(task_status)

    def reset_selected_account_info(self) -> None:
        self.set_selected_account_info("无", "未登录", 0, "空闲")

    def set_status_message(self, text: str) -> None:
        self.status_var.set(text)

    def show_warning(self, title: str, message: str) -> None:
        self.root.after(0, lambda: messagebox.showwarning(title, message))

    def ensure_image_exists(self) -> bool:
        path = self.get_image_path()
        if not path:
            self.show_warning("图片缺失", "请先选择要上传的图片文件。")
            self.set_status_message("⚠️ 图片文件为空，请先选择图片")
            return False
        if not os.path.exists(path):
            self.show_warning("图片不存在", f"图片文件不存在，请重新选择：\n{path}")
            self.set_status_message(f"⚠️ 图片不存在：{path}")
            self._refresh_image_hint()
            return False
        return True

    def update_accounts_list(self, accounts: List[AccountInfo]) -> None:
        self.accounts_listbox.delete(0, tk.END)

        for account in accounts:
            if account.login_status == "已登录":
                status_icon, color = "🟢", self.SUCCESS
            elif account.login_status == "登录中":
                status_icon, color = "🟡", self.WARNING
            elif account.login_status == "登录失败":
                status_icon, color = "🔴", self.DANGER
            else:
                status_icon, color = "⚪", "#111827"

            display_text = f"{status_icon} {account.email}  |  登录:{account.login_status}  任务:{account.task_status}"
            self.accounts_listbox.insert(tk.END, display_text)
            self.accounts_listbox.itemconfig(self.accounts_listbox.size() - 1, {"fg": color})

        total = len(accounts)
        logged_in = sum(1 for acc in accounts if acc.login_status == "已登录")
        running = sum(1 for acc in accounts if acc.task_status == "执行中")
        self.set_status_message(f"就绪 - 共 {total} 个账号，{logged_in} 个已登录，{running} 个执行中")

    def get_skus(self) -> List[str]:
        raw = self.sku_text.get("1.0", tk.END)
        tokens = [seg.strip() for line in raw.splitlines() for seg in line.split(",")]
        return [t for t in tokens if t]

    def get_image_path(self) -> str:
        return self.image_var.get().strip()

    def is_headless(self) -> bool:
        return self.headless_var.get()

    def append_log(self, msg: str) -> None:
        text = msg.strip()
        if "❌" in text:
            self.set_status_message(text)
        elif "⚠️" in text:
            self.set_status_message(text)
