#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
任务历史查看窗口
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Callable, List, Optional
from services.task_record_service import TaskRecord


class TaskHistoryWindow:
    """任务历史查看窗口"""

    BG_COLOR = "#f3f6fb"
    CARD_BG = "#ffffff"
    PRIMARY = "#2563eb"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"
    DANGER = "#dc2626"
    MUTED = "#64748b"
    BORDER = "#dbe3f0"
    DARK = "#0f172a"

    # 自动刷新间隔（毫秒）
    AUTO_REFRESH_INTERVAL = 3000

    def __init__(self, parent, task_service, task_records: List[TaskRecord], on_close: Optional[Callable] = None):
        self.parent = parent
        self.task_service = task_service
        self.task_records = task_records
        self.on_close = on_close
        self.selected_record: Optional[TaskRecord] = None
        self._displayed_records: List[TaskRecord] = []
        self.filtered_accounts: List[str] = ["全部"]
        self.filtered_status: str = "全部"
        self._auto_refresh_timer = None
        self._last_refresh_record_ids = set()

        # 收集所有账号
        all_accounts = list(set(r.account_email for r in task_records if r.account_email))
        self.available_accounts = sorted(all_accounts)
        self.filtered_accounts.extend(self.available_accounts)

        # 初始化筛选变量
        self.account_var = tk.StringVar(value="全部")
        self.status_var = tk.StringVar(value="全部")
        self.auto_refresh_var = tk.StringVar(value="自动刷新已开启")
        self._auto_refresh_enabled = True

        self.window = tk.Toplevel(parent)
        self.window.title("任务执行历史")
        self.window.geometry("1000x700")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.configure(bg=self.BG_COLOR)

        self._build_ui()
        self._refresh_task_list()
        self._start_auto_refresh()

        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

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
        style.configure("Header.TLabel", background=self.BG_COLOR, foreground=self.DARK, font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Title.TLabel", background=self.CARD_BG, foreground=self.DARK, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Caption.TLabel", background=self.CARD_BG, foreground=self.MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Body.TLabel", background=self.CARD_BG, foreground="#1e293b", font=("Microsoft YaHei UI", 10))
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9), background="#fbfdff", fieldbackground="#fbfdff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), background="#e8eef8", foreground=self.DARK)

    def _build_ui(self) -> None:
        self._setup_style()

        shell = ttk.Frame(self.window, style="App.TFrame", padding=14)
        shell.pack(fill=tk.BOTH, expand=True)

        # 顶部筛选栏
        toolbar_card = ttk.LabelFrame(shell, text="筛选条件", style="Card.TLabelframe", padding=12)
        toolbar_card.pack(fill=tk.X, pady=(0, 10))
        toolbar_card.columnconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=0)

        ttk.Label(toolbar_card, text="账号:", style="Caption.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=6)
        self.account_combo = ttk.Combobox(toolbar_card, textvariable=self.account_var, values=self.filtered_accounts, state="readonly", width=25)
        self.account_combo.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=6)
        self.account_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)

        ttk.Label(toolbar_card, text="状态:", style="Caption.TLabel").grid(row=0, column=2, sticky="e", padx=(0, 6), pady=6)
        status_options = ["全部", "待执行", "运行中", "已完成", "失败"]
        self.status_combo = ttk.Combobox(toolbar_card, textvariable=self.status_var, values=status_options, state="readonly", width=12)
        self.status_combo.grid(row=0, column=3, sticky="w", padx=(0, 12), pady=6)
        self.status_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)

        ttk.Button(toolbar_card, text="🔄 刷新", command=self._on_refresh, style="Secondary.TButton").grid(row=0, column=4, sticky="w", padx=(0, 12), pady=6)
        ttk.Button(toolbar_card, text="自动刷新", command=self._toggle_auto_refresh, style="Secondary.TButton").grid(row=0, column=5, sticky="w", padx=(0, 12), pady=6)
        ttk.Button(toolbar_card, text="❌ 关闭", command=self.on_window_close, style="Secondary.TButton").grid(row=0, column=6, sticky="w", pady=6)

        # 自动刷新状态标签
        ttk.Label(toolbar_card, textvariable=self.auto_refresh_var, style="Caption.TLabel", foreground=self.SUCCESS).grid(row=0, column=7, sticky="w", padx=(12, 0))

        # 主内容区：左右分栏
        content = ttk.Panedwindow(shell, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)

        # 左侧：任务列表
        left = ttk.Frame(content, style="App.TFrame")
        right = ttk.Frame(content, style="App.TFrame")
        content.add(left, weight=3)
        content.add(right, weight=2)

        list_card = ttk.LabelFrame(left, text="任务列表", style="Card.TLabelframe", padding=12)
        list_card.pack(fill=tk.BOTH, expand=True)

        table_wrap = ttk.Frame(list_card, style="App.TFrame")
        table_wrap.pack(fill=tk.BOTH, expand=True)
        columns = ("task_id", "account", "type", "status", "sku_count", "start_time", "duration")
        self.tasks_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="single", height=18)
        self.tasks_tree.heading("task_id", text="任务ID")
        self.tasks_tree.heading("account", text="账号")
        self.tasks_tree.heading("type", text="类型")
        self.tasks_tree.heading("status", text="状态")
        self.tasks_tree.heading("sku_count", text="SKU数")
        self.tasks_tree.heading("start_time", text="开始时间")
        self.tasks_tree.heading("duration", text="耗时")
        self.tasks_tree.column("task_id", width=120, anchor="w")
        self.tasks_tree.column("account", width=220, anchor="w")
        self.tasks_tree.column("type", width=80, anchor="center")
        self.tasks_tree.column("status", width=80, anchor="center")
        self.tasks_tree.column("sku_count", width=70, anchor="center")
        self.tasks_tree.column("start_time", width=140, anchor="center")
        self.tasks_tree.column("duration", width=70, anchor="center")
        self.tasks_tree.pack(side="left", fill=tk.BOTH, expand=True)
        self.tasks_tree.bind("<<TreeviewSelect>>", self._on_task_select)
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tasks_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tasks_tree.configure(yscrollcommand=scrollbar.set)

        # 右侧：任务详情
        detail_card = ttk.LabelFrame(right, text="任务详情", style="Card.TLabelframe", padding=12)
        detail_card.pack(fill=tk.BOTH, expand=True)

        # 基本信息
        self.detail_info = tk.Text(detail_card, height=8, bg="#f8fafc", fg="#1e293b", relief=tk.FLAT, highlightthickness=0, font=("Microsoft YaHei UI", 9), wrap=tk.WORD)
        self.detail_info.pack(fill=tk.X, pady=(0, 10))
        self.detail_info.insert(tk.END, "请从左侧选择一个任务查看详情")
        self.detail_info.config(state=tk.DISABLED)

        # SKU处理结果
        ttk.Label(detail_card, text="SKU 处理结果", style="Title.TLabel").pack(anchor="w", pady=(0, 8))

        sku_table_wrap = ttk.Frame(detail_card, style="App.TFrame")
        sku_table_wrap.pack(fill=tk.BOTH, expand=True)
        sku_columns = ("sku", "status", "message")
        self.sku_tree = ttk.Treeview(sku_table_wrap, columns=sku_columns, show="headings", selectmode="none", height=12)
        self.sku_tree.heading("sku", text="SKU")
        self.sku_tree.heading("status", text="状态")
        self.sku_tree.heading("message", text="消息")
        self.sku_tree.column("sku", width=120, anchor="w")
        self.sku_tree.column("status", width=80, anchor="center")
        self.sku_tree.column("message", width=180, anchor="w")
        self.sku_tree.pack(side="left", fill=tk.BOTH, expand=True)
        sku_scrollbar = ttk.Scrollbar(sku_table_wrap, orient="vertical", command=self.sku_tree.yview)
        sku_scrollbar.pack(side="right", fill="y")
        self.sku_tree.configure(yscrollcommand=sku_scrollbar.set)

    def _format_status(self, status: str) -> str:
        """格式化状态文本"""
        status_map = {
            "pending": "待执行",
            "running": "运行中",
            "finished": "已完成",
            "failed": "失败",
        }
        return status_map.get(status, status)

    def _format_type(self, task_type: str) -> str:
        """格式化任务类型文本"""
        type_map = {
            "local": "本地",
            "dispatch": "分派",
        }
        return type_map.get(task_type, task_type)

    def _format_timestamp(self, timestamp: Optional[float]) -> str:
        """格式化时间戳"""
        if not timestamp:
            return "-"
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def _format_duration(self, started_at: Optional[float], finished_at: Optional[float]) -> str:
        """格式化执行时长"""
        if not started_at or not finished_at:
            return "-"
        duration = int(finished_at - started_at)
        if duration < 60:
            return f"{duration}秒"
        minutes = duration // 60
        seconds = duration % 60
        return f"{minutes}分{seconds}秒"

    def _refresh_task_list(self) -> None:
        """刷新任务列表"""
        # 清空当前列表
        for item in self.tasks_tree.get_children():
            self.tasks_tree.delete(item)

        # 筛选记录
        self._displayed_records = self._filter_records()

        # 填充列表
        for record in self._displayed_records:
            values = (
                record.task_id,
                record.account_email,
                self._format_type(record.task_type),
                self._format_status(record.status),
                str(len(record.skus)),
                self._format_timestamp(record.started_at),
                self._format_duration(record.started_at, record.finished_at),
            )
            self.tasks_tree.insert("", tk.END, values=values, tags=(record.status,))

        # 配置状态颜色标签
        self.tasks_tree.tag_configure("running", foreground=self.WARNING)
        self.tasks_tree.tag_configure("finished", foreground=self.SUCCESS)
        self.tasks_tree.tag_configure("failed", foreground=self.DANGER)

    def _filter_records(self) -> List[TaskRecord]:
        """根据筛选条件过滤记录"""
        filtered = list(self.task_records)

        # 账号筛选
        selected_account = self.account_var.get()
        if selected_account != "全部":
            filtered = [r for r in filtered if r.account_email == selected_account]

        # 状态筛选
        selected_status = self.status_var.get()
        status_map = {
            "待执行": "pending",
            "运行中": "running",
            "已完成": "finished",
            "失败": "failed",
        }
        if selected_status != "全部":
            target_status = status_map.get(selected_status)
            if target_status:
                filtered = [r for r in filtered if r.status == target_status]

        # 按创建时间倒序排列
        filtered.sort(key=lambda r: r.created_at, reverse=True)
        return filtered

    def _on_filter_changed(self, *_args) -> None:
        """筛选条件改变时刷新列表"""
        self._refresh_task_list()
        self._clear_detail()

    def _on_refresh(self) -> None:
        """刷新按钮点击事件"""
        # 从父窗口获取最新记录
        if hasattr(self.parent, "task_service"):
            self.task_records = self.parent.task_service.get_task_records()
            # 更新账号列表
            all_accounts = list(set(r.account_email for r in self.task_records if r.account_email))
            self.available_accounts = sorted(all_accounts)
            self.filtered_accounts = ["全部"] + self.available_accounts
            # 更新账号下拉框
            self.account_combo['values'] = self.filtered_accounts
        self._refresh_task_list()
        self._clear_detail()

    def _start_auto_refresh(self) -> None:
        """启动自动刷新"""
        if not self._auto_refresh_enabled:
            return
        self._auto_refresh()
        self._auto_refresh_timer = self.window.after(self.AUTO_REFRESH_INTERVAL, self._start_auto_refresh)

    def _auto_refresh(self) -> None:
        """自动刷新逻辑"""
        try:
            # 检查窗口是否还存在
            if not self.window.winfo_exists():
                self._stop_auto_refresh()
                return

            # 从父窗口获取最新记录
            if hasattr(self.parent, "task_service"):
                current_records = self.parent.task_service.get_task_records()
                current_record_ids = set(r.task_id for r in current_records)

                # 如果记录ID有变化，说明有新任务或状态更新
                if current_record_ids != self._last_refresh_record_ids:
                    self.task_records = current_records
                    self._last_refresh_record_ids = current_record_ids
                    self._refresh_task_list()

                    # 如果正在查看某个任务，也更新详情面板
                    if self.selected_record:
                        for record in self.task_records:
                            if record.task_id == self.selected_record.task_id:
                                self.selected_record = record
                                self._update_detail_panel(record)
                                break
        except Exception:
            # 窗口可能已经被关闭
            self._stop_auto_refresh()

    def _stop_auto_refresh(self) -> None:
        """停止自动刷新"""
        if self._auto_refresh_timer:
            self.window.after_cancel(self._auto_refresh_timer)
            self._auto_refresh_timer = None

    def _toggle_auto_refresh(self) -> None:
        """切换自动刷新状态"""
        self._auto_refresh_enabled = not self._auto_refresh_enabled
        if self._auto_refresh_enabled:
            self.auto_refresh_var.set("自动刷新已开启")
            self._start_auto_refresh()
        else:
            self.auto_refresh_var.set("自动刷新已关闭")
            self._stop_auto_refresh()

    def _on_task_select(self, _event) -> None:
        """任务选择事件"""
        selection = self.tasks_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        values = self.tasks_tree.item(item_id, "values")
        if not values:
            return

        task_id = values[0]
        # 从显示的记录中查找匹配的记录
        for record in self._displayed_records:
            if record.task_id == task_id:
                self.selected_record = record
                self._update_detail_panel(record)
                break

    def _update_detail_panel(self, record: TaskRecord) -> None:
        """更新详情面板"""
        self.detail_info.config(state=tk.NORMAL)
        self.detail_info.delete("1.0", tk.END)

        # 基本信息
        info_lines = [
            f"任务ID: {record.task_id}",
            f"账号: {record.account_email}",
            f"类型: {self._format_type(record.task_type)}",
            f"状态: {self._format_status(record.status)}",
            f"SKU数量: {len(record.skus)}",
            f"SKU列表: {', '.join(record.skus)}",
            f"创建时间: {self._format_timestamp(record.created_at)}",
            f"开始时间: {self._format_timestamp(record.started_at)}",
            f"结束时间: {self._format_timestamp(record.finished_at)}",
            f"执行时长: {self._format_duration(record.started_at, record.finished_at)}",
        ]

        if record.error:
            info_lines.append(f"\n错误信息: {record.error}")

        self.detail_info.insert(tk.END, "\n".join(info_lines))
        self.detail_info.config(state=tk.DISABLED)

        # 更新SKU处理结果
        self._update_sku_list(record)

    def _update_sku_list(self, record: TaskRecord) -> None:
        """更新SKU处理结果列表"""
        for item in self.sku_tree.get_children():
            self.sku_tree.delete(item)

        # 从结果中获取SKU处理信息
        result = record.result
        processed_skus = result.get("summary", {}).get("processed_skus", []) if result else []

        if not processed_skus:
            self.sku_tree.insert("", tk.END, values=("-", "-", "任务未完成或无详细结果"))
            return

        for sku_info in processed_skus:
            sku = sku_info.get("sku", "")
            success = sku_info.get("success", False)
            stage = sku_info.get("stage", "unknown")
            message = sku_info.get("message", "")

            # 确定状态文本
            if stage == "finish" or success:
                status = "完成"
            elif stage == "failed" or not success:
                status = "失败"
            else:
                status = "处理中"

            values = (sku, status, message)
            self.sku_tree.insert("", tk.END, values=values, tags=("status_" + status,))
            self.sku_tree.tag_configure("status_完成", foreground=self.SUCCESS)
            self.sku_tree.tag_configure("status_失败", foreground=self.DANGER)
            self.sku_tree.tag_configure("status_处理中", foreground=self.WARNING)

    def _clear_detail(self) -> None:
        """清空详情面板"""
        self.detail_info.config(state=tk.NORMAL)
        self.detail_info.delete("1.0", tk.END)
        self.detail_info.insert(tk.END, "请从左侧选择一个任务查看详情")
        self.detail_info.config(state=tk.DISABLED)

        for item in self.sku_tree.get_children():
            self.sku_tree.delete(item)

    def on_window_close(self) -> None:
        """窗口关闭事件"""
        self._stop_auto_refresh()
        if self.on_close:
            self.on_close()
        self.window.destroy()

    def update_records(self, task_records: List[TaskRecord]) -> None:
        """更新任务记录并刷新列表"""
        self.task_records = task_records
        self._refresh_task_list()
