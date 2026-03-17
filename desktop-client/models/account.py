from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_STORAGE_DIR = "accounts"


@dataclass
class AccountInfo:
    """
    通用账号模型。
    同时兼容原 app.py 和 ozon_core.py 的账号字段。
    """

    email: str
    imap_password: str = ""
    storage_path: Optional[str] = None
    use_manual_login: bool = False

    # UI / 运行时状态
    is_selected: bool = False
    login_status: str = "未登录"   # 未登录 / 登录中 / 已登录 / 登录失败
    task_status: str = "空闲"     # 空闲 / 执行中 / 完成 / 失败
    last_login: float = 0
    login_count: int = 0
    last_error: str = ""

    def __post_init__(self) -> None:
        if self.storage_path is None:
            self.storage_path = self.build_storage_path(self.email)

    @staticmethod
    def build_storage_path(email: str) -> str:
        safe_email = email.replace("@", "_").replace(".", "_")
        return os.path.join(DEFAULT_STORAGE_DIR, f"ozon_auth_{safe_email}.json")

    def validate(self) -> bool:
        """
        验证账号信息是否完整。
        手动验证码模式只要求 email；
        IMAP 模式要求 email + imap_password。
        """
        if self.use_manual_login:
            return bool(self.email.strip())
        return bool(self.email.strip() and self.imap_password.strip())

    def is_logged_in(self) -> bool:
        return self.login_status == "已登录"

    def mark_login_success(self, timestamp: float) -> None:
        self.login_status = "已登录"
        self.last_login = timestamp
        self.login_count += 1
        self.last_error = ""

    def mark_login_failed(self, error: str) -> None:
        self.login_status = "登录失败"
        self.last_error = error or ""

    def mark_task_running(self) -> None:
        self.task_status = "执行中"

    def mark_task_success(self) -> None:
        self.task_status = "完成"

    def mark_task_failed(self, error: str = "") -> None:
        self.task_status = "失败"
        if error:
            self.last_error = error

    def reset_task_status(self) -> None:
        self.task_status = "空闲"

    def to_dict(self) -> dict:
        """
        用于配置持久化。
        注意：这里只保存可持久化字段。
        """
        return {
            "email": self.email,
            "imap_password": self.imap_password,
            "storage_path": self.storage_path,
            "use_manual_login": self.use_manual_login,
            "is_selected": self.is_selected,
            "login_status": self.login_status,
            "task_status": self.task_status,
            "last_login": self.last_login,
            "login_count": self.login_count,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccountInfo":
        return cls(
            email=data.get("email", ""),
            imap_password=data.get("imap_password", ""),
            storage_path=data.get("storage_path"),
            use_manual_login=data.get("use_manual_login", False),
            is_selected=data.get("is_selected", False),
            login_status=data.get("login_status", "未登录"),
            task_status=data.get("task_status", "空闲"),
            last_login=data.get("last_login", 0),
            login_count=data.get("login_count", 0),
            last_error=data.get("last_error", ""),
        )


# 兼容 ozon_core.py 原命名
OzonAccount = AccountInfo