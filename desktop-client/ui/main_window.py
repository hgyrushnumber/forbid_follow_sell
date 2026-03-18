#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List

from models import AccountInfo


class MainWindow:
    """主窗口 UI 编排：只负责界面元素与交互呈现。"""

    BG_COLOR = "#f3f6fb"
    CARD_BG = "#ffffff"
    PRIMARY = "#2563eb"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"
    DANGER = "#dc2626"
    MUTED = "#64748b"
    BORDER = "#dbe3f0"
    DARK = "#0f172a"

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
        self.root.geometry("1280x840")
        self.root.minsize(1120, 760)
        self.root.configure(bg=self.BG_COLOR)
        self._displayed_accounts: List[AccountInfo] = []
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
        style.configure("Card.TLabelframe", background=self.CARD_BG, borderwidth=1, relief="solid")
        style.configure(
            "Card.TLabelframe.Label",
            background=self.CARD_BG,
            foreground=self.DARK,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure("Header.TLabel", background=self.BG_COLOR, foreground=self.DARK, font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("SubHeader.TLabel", background=self.BG_COLOR, foreground=self.MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background=self.CARD_BG, foreground=self.DARK, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Caption.TLabel", background=self.CARD_BG, foreground=self.MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Body.TLabel", background=self.CARD_BG, foreground="#1e293b", font=("Microsoft YaHei UI", 10))
        style.configure("StatusBar.TLabel", background="#e2e8f0", foreground="#0f172a", font=("Microsoft YaHei UI", 10), padding=(10, 8))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(12, 10))
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 10), padding=(10, 8))
        style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 10), background="#fbfdff", fieldbackground="#fbfdff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), background="#e8eef8", foreground=self.DARK)

    def _build_metric_card(self, parent, title: str, value_var: tk.StringVar, color: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="App.TFrame")
        outer = tk.Frame(card, bg=self.CARD_BG, highlightthickness=1, highlightbackground=self.BORDER, bd=0)
        outer.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        tk.Label(outer, text=title, bg=self.CARD_BG, fg=self.MUTED, font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(outer, textvariable=value_var, bg=self.CARD_BG, fg=color, font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=12, pady=(0, 10))
        return card

    def _build(self, **callbacks) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=14)
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="Ozon 多账号投诉工作台", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="更现代的账号表格视图、图片校验提示与任务执行面板。运行日志仅写入文件，不在 UI 内实时刷屏。",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        content = ttk.Panedwindow(shell, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(content, style="App.TFrame")
        right = ttk.Frame(content, style="App.TFrame")
        content.add(left, weight=5)
        content.add(right, weight=4)

        metrics = ttk.Frame(left, style="App.TFrame")
        metrics.pack(fill=tk.X, pady=(0, 10))
        metrics.columnconfigure((0, 1, 2, 3), weight=1)
        self.total_accounts_var = tk.StringVar(value="0")
        self.logged_in_var = tk.StringVar(value="0")
        self.running_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self._build_metric_card(metrics, "账号总数", self.total_accounts_var, self.DARK).grid(row=0, column=0, sticky="nsew")
        self._build_metric_card(metrics, "已登录", self.logged_in_var, self.SUCCESS).grid(row=0, column=1, sticky="nsew")
        self._build_metric_card(metrics, "执行中", self.running_var, self.WARNING).grid(row=0, column=2, sticky="nsew")
        self._build_metric_card(metrics, "登录失败", self.failed_var, self.DANGER).grid(row=0, column=3, sticky="nsew")

        account_card = ttk.LabelFrame(left, text="账号管理", style="Card.TLabelframe", padding=12)
        account_card.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(account_card, style="App.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(toolbar, text="➕ 添加账号", command=callbacks["on_add_account"], style="Secondary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="✏️ 编辑账号", command=callbacks["on_edit_account"], style="Secondary.TButton").pack(side="left", padx=6)
        ttk.Button(toolbar, text="🗑️ 删除账号", command=callbacks["on_delete_account"], style="Secondary.TButton").pack(side="left", padx=6)
        ttk.Button(toolbar, text="🔄 刷新", command=callbacks["on_refresh_accounts"], style="Secondary.TButton").pack(side="left", padx=6)

        table_wrap = ttk.Frame(account_card, style="App.TFrame")
        table_wrap.pack(fill=tk.BOTH, expand=True)
        columns = ("email", "login", "task", "count")
        self.accounts_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="extended", height=18)
        self.accounts_tree.heading("email", text="账号邮箱")
        self.accounts_tree.heading("login", text="登录状态")
        self.accounts_tree.heading("task", text="任务状态")
        self.accounts_tree.heading("count", text="登录次数")
        self.accounts_tree.column("email", width=320, anchor="w")
        self.accounts_tree.column("login", width=120, anchor="center")
        self.accounts_tree.column("task", width=120, anchor="center")
        self.accounts_tree.column("count", width=90, anchor="center")
        self.accounts_tree.pack(side="left", fill=tk.BOTH, expand=True)
        self.accounts_tree.bind("<<TreeviewSelect>>", callbacks["on_account_select"])
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.accounts_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.accounts_tree.configure(yscrollcommand=scrollbar.set)

        detail_card = ttk.LabelFrame(left, text="账号详情", style="Card.TLabelframe", padding=12)
        detail_card.pack(fill=tk.X, pady=(10, 0))
        detail_card.columnconfigure(1, weight=1)
        ttk.Label(detail_card, text="当前选中", style="Caption.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=4)
        self.selected_account_var = tk.StringVar(value="无")
        ttk.Label(detail_card, textvariable=self.selected_account_var, style="Body.TLabel").grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(detail_card, text="登录状态", style="Caption.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 10), pady=4)
        self.login_status_var = tk.StringVar(value="未登录")
        ttk.Label(detail_card, textvariable=self.login_status_var, style="Body.TLabel").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(detail_card, text="任务状态", style="Caption.TLabel").grid(row=2, column=0, sticky="e", padx=(0, 10), pady=4)
        self.task_status_var = tk.StringVar(value="空闲")
        ttk.Label(detail_card, textvariable=self.task_status_var, style="Body.TLabel").grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(detail_card, text="登录次数", style="Caption.TLabel").grid(row=3, column=0, sticky="e", padx=(0, 10), pady=4)
        self.login_count_var = tk.StringVar(value="0")
        ttk.Label(detail_card, textvariable=self.login_count_var, style="Body.TLabel").grid(row=3, column=1, sticky="w", pady=4)

        task_card = ttk.LabelFrame(right, text="任务配置", style="Card.TLabelframe", padding=14)
        task_card.pack(fill=tk.X)
        task_card.columnconfigure(1, weight=1)
        ttk.Label(task_card, text="SKU 列表", style="Title.TLabel").grid(row=0, column=0, sticky="ne", padx=(0, 10), pady=6)
        self.sku_text = tk.Text(
            task_card,
            height=10,
            width=44,
            bg="#f8fafc",
            fg="#111827",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            font=("Consolas", 10),
        )
        self.sku_text.grid(row=0, column=1, columnspan=2, sticky="ew", pady=6)
        self.sku_text.insert(tk.END, "SKU001\nSKU002,SKU003\nSKU004")

        ttk.Label(task_card, text="图片文件", style="Title.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 10), pady=6)
        self.image_var = tk.StringVar(value="icon.png")
        self.image_var.trace_add("write", self._on_image_path_changed)
        ttk.Entry(task_card, textvariable=self.image_var).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(task_card, text="浏览…", command=self.choose_image, style="Secondary.TButton").grid(row=1, column=2, padx=(8, 0), pady=6)
        self.image_hint_var = tk.StringVar(value="请确认图片文件存在后再执行任务")
        self.image_hint_label = tk.Label(task_card, textvariable=self.image_hint_var, bg=self.CARD_BG, fg=self.MUTED, anchor="w", font=("Microsoft YaHei UI", 9))
        self.image_hint_label.grid(row=2, column=1, columnspan=2, sticky="w", pady=(0, 8))

        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(task_card, text="无头模式", variable=self.headless_var).grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 6))

        action_card = ttk.LabelFrame(right, text="快速操作", style="Card.TLabelframe", padding=14)
        action_card.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(action_card, text="🚀 登录选中账号", command=callbacks["on_login_selected"], style="Primary.TButton").pack(fill=tk.X, pady=4)
        ttk.Button(action_card, text="🎯 执行任务到选中账号", command=callbacks["on_run_task_selected"], style="Primary.TButton").pack(fill=tk.X, pady=4)
        ttk.Button(action_card, text="🛑 关闭选中账号", command=callbacks["on_close_selected"], style="Secondary.TButton").pack(fill=tk.X, pady=4)

        tips_card = ttk.LabelFrame(right, text="运行说明", style="Card.TLabelframe", padding=14)
        tips_card.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        tips = [
            "• 运行日志统一写入日志文件，不在桌面端实时渲染。",
            "• 第一次进入投诉会话会执行菜单点击；后续同一会话 id 会直接复用。",
            "• 执行任务前请确认图片状态为“图片已就绪”。",
            "• 登录标准流程：登录 -> 邮箱登录 -> 输入邮箱 -> 手动输入验证码。",
            "• 每个邮箱仅保留一个标签页，减少状态干扰。",
        ]
        for tip in tips:
            ttk.Label(tips_card, text=tip, style="Caption.TLabel", wraplength=420, justify="left").pack(anchor="w", pady=4)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(shell, textvariable=self.status_var, style="StatusBar.TLabel", anchor=tk.W).pack(fill=tk.X, pady=(12, 0))
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
        selection = self.accounts_tree.selection()
        indices = []
        for item_id in selection:
            try:
                indices.append(int(item_id))
            except Exception:
                continue
        return indices

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
        self._displayed_accounts = list(accounts)
        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)

        for index, account in enumerate(accounts):
            self.accounts_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(account.email, account.login_status, account.task_status, account.login_count),
            )

        total = len(accounts)
        logged_in = sum(1 for acc in accounts if acc.login_status == "已登录")
        running = sum(1 for acc in accounts if acc.task_status == "执行中")
        failed = sum(1 for acc in accounts if acc.login_status == "登录失败")
        self.total_accounts_var.set(str(total))
        self.logged_in_var.set(str(logged_in))
        self.running_var.set(str(running))
        self.failed_var.set(str(failed))
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
        if "❌" in text or "⚠️" in text or "✅" in text:
            self.set_status_message(text)
