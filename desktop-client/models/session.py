from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class BrowserSession:
    """
    邮箱级浏览器会话模型。

    每个邮箱独占一个 Browser / BrowserContext，业务请求在该会话内创建新的 Page。
    这里只保存运行时对象引用，不做序列化。
    """

    email: str
    storage_path: str
    session_key: str = ""
    browser_instance_id: str = ""
    owner_thread_id: int = 0
    owner_thread_name: str = ""

    context: Optional[Any] = None
    page: Optional[Any] = None
    pages: Dict[str, Any] = field(default_factory=dict)
    page_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    is_alive: bool = False
    last_activity: float = 0.0

    def __post_init__(self) -> None:
        if not self.session_key:
            self.session_key = self.build_session_key(self.email)
        if not self.browser_instance_id:
            self.browser_instance_id = self.build_browser_instance_id()
        if not self.owner_thread_id:
            self.owner_thread_id = threading.get_ident()
        if not self.owner_thread_name:
            self.owner_thread_name = threading.current_thread().name

    @staticmethod
    def build_session_key(email: str) -> str:
        safe_email = email.strip().lower().replace("@", "_at_").replace(".", "_")
        return f"email::{safe_email}"

    @staticmethod
    def build_browser_instance_id() -> str:
        return uuid.uuid4().hex[:12]

    def touch(self) -> None:
        self.last_activity = time.time()

    def mark_alive(self) -> None:
        self.is_alive = True
        self.touch()

    def mark_dead(self) -> None:
        self.is_alive = False

    def has_page(self) -> bool:
        return self.page is not None

    def has_context(self) -> bool:
        return self.context is not None

    def has_browser(self) -> bool:
        return bool(self.browser_instance_id)

    def belongs_to_current_thread(self) -> bool:
        return self.owner_thread_id == threading.get_ident()

    def belongs_to_current_thread(self) -> bool:
        return self.owner_thread_id == threading.get_ident()

    def summary(self) -> dict:
        return {
            "email": self.email,
            "storage_path": self.storage_path,
            "session_key": self.session_key,
            "browser_instance_id": self.browser_instance_id,
            "owner_thread_id": self.owner_thread_id,
            "owner_thread_name": self.owner_thread_name,
            "is_alive": self.is_alive,
            "last_activity": self.last_activity,
            "has_browser": bool(self.browser_instance_id),
            "has_context": self.context is not None,
            "has_page": self.page is not None,
            "page_count": len(self.pages),
        }
