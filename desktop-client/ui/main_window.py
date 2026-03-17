#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, scrolledtext
from typing import Callable, List

from models import AccountInfo


class MainWindow:
    """主窗口 UI 编排：只负责界面元素与交互呈现。"""

    MAX_LOG_LINES = 2000

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
        self.root.geometry("1200x800")

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

    def _build(self, **callbacks) -> None:
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.LabelFrame(paned_window, text="账号管理")
        paned_window.add(left_frame, width=400)

        self.accounts_listbox = tk.Listbox(left_frame, width=50, height=20, selectmode=tk.MULTIPLE)
        self.accounts_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.accounts_listbox.bind("<<ListboxSelect>>", callbacks["on_account_select"])

        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Button(btn_frame, text="➕ 添加账号", command=callbacks["on_add_account"]).pack(side="left", padx=2)
        tk.Button(btn_frame, text="✏️ 编辑账号", command=callbacks["on_edit_account"]).pack(side="left", padx=2)
        tk.Button(btn_frame, text="🗑️ 删除账号", command=callbacks["on_delete_account"]).pack(side="left", padx=2)
        tk.Button(btn_frame, text="🔄 刷新列表", command=callbacks["on_refresh_accounts"]).pack(side="left", padx=2)

        info_frame = tk.LabelFrame(left_frame, text="账号详情")
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(info_frame, text="当前选中:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.selected_account_var = tk.StringVar(value="无")
        tk.Label(info_frame, textvariable=self.selected_account_var, fg="blue").grid(
            row=0, column=1, padx=5, pady=2, sticky="w"
        )

        tk.Label(info_frame, text="登录状态:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.login_status_var = tk.StringVar(value="未登录")
        tk.Label(info_frame, textvariable=self.login_status_var).grid(row=1, column=1, padx=5, pady=2, sticky="w")

        tk.Label(info_frame, text="任务状态:").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.task_status_var = tk.StringVar(value="空闲")
        tk.Label(info_frame, textvariable=self.task_status_var).grid(row=2, column=1, padx=5, pady=2, sticky="w")

        tk.Label(info_frame, text="登录次数:").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.login_count_var = tk.StringVar(value="0")
        tk.Label(info_frame, textvariable=self.login_count_var).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        right_frame = tk.LabelFrame(paned_window, text="任务执行")
        paned_window.add(right_frame)

        config_frame = tk.LabelFrame(right_frame, text="任务配置")
        config_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(config_frame, text="SKU列表:").grid(row=0, column=0, padx=5, pady=5, sticky="ne")
        self.sku_text = tk.Text(config_frame, height=6, width=50)
        self.sku_text.grid(row=0, column=1, padx=5, pady=5)
        self.sku_text.insert(tk.END, "SKU001\nSKU002,SKU003\nSKU004")

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

        tk.Button(action_frame, text="🚀 登录选中账号", command=callbacks["on_login_selected"]).pack(fill=tk.X, padx=5, pady=2)
        tk.Button(action_frame, text="🎯 执行任务到选中账号", command=callbacks["on_run_task_selected"]).pack(fill=tk.X, padx=5, pady=2)
        tk.Button(action_frame, text="🛑 关闭选中账号", command=callbacks["on_close_selected"]).pack(fill=tk.X, padx=5, pady=2)

        log_frame = tk.LabelFrame(right_frame, text="运行日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        log_toolbar = tk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, padx=2, pady=2)
        tk.Button(log_toolbar, text="🧹 清空日志", command=self.clear_log).pack(side="left", padx=2)
        self.auto_scroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(log_toolbar, text="自动滚动", variable=self.auto_scroll_var).pack(side="left", padx=8)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, padx=10, pady=2)

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("图片文件", "*.png;*.jpg;*.jpeg"), ("所有文件", "*.*")])
        if path:
            self.image_var.set(path)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

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

    def update_accounts_list(self, accounts: List[AccountInfo]) -> None:
        self.accounts_listbox.delete(0, tk.END)

        for account in accounts:
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

        total = len(accounts)
        logged_in = sum(1 for acc in accounts if acc.login_status == "已登录")
        running = sum(1 for acc in accounts if acc.task_status == "执行中")
        self.set_status_message(f"就绪 - 共 {total} 个账号, {logged_in} 个已登录, {running} 个执行中")

    def get_skus(self) -> List[str]:
        raw = self.sku_text.get("1.0", tk.END)
        tokens = [seg.strip() for line in raw.splitlines() for seg in line.split(",")]
        return [t for t in tokens if t]

    def get_image_path(self) -> str:
        return self.image_var.get().strip()

    def is_headless(self) -> bool:
        return self.headless_var.get()

    def append_log(self, msg: str) -> None:
        try:
            self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

            # 控制日志最大行数，避免长时间运行卡顿
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > self.MAX_LOG_LINES:
                trim = lines - self.MAX_LOG_LINES
                self.log_text.delete("1.0", f"{trim + 1}.0")

            if self.auto_scroll_var.get():
                self.log_text.see(tk.END)

            self.root.update_idletasks()
        except Exception:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
