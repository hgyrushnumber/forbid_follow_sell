from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BrowserSession:
    """
    浏览器会话模型。

    这里只保存运行时对象引用，不做序列化。
    Playwright 的对象类型在运行时注入，因此这里用 Any。
    """

    email: str
    storage_path: str

    playwright: Optional[Any] = None
    browser: Optional[Any] = None
    context: Optional[Any] = None
    page: Optional[Any] = None

    is_alive: bool = False
    last_activity: float = 0.0

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
        return self.browser is not None

    def summary(self) -> dict:
        return {
            "email": self.email,
            "storage_path": self.storage_path,
            "is_alive": self.is_alive,
            "last_activity": self.last_activity,
            "has_playwright": self.playwright is not None,
            "has_browser": self.browser is not None,
            "has_context": self.context is not None,
            "has_page": self.page is not None,
        }