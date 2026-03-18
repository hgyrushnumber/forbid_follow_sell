#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
import uuid
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Optional, TypeVar

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from models import OzonAccount, BrowserSession

T = TypeVar("T")


class SessionService:
    """会话管理服务 - 复用全局 Browser，按账号隔离 BrowserContext。"""

    def __init__(self, logger_func):
        self.sessions: Dict[str, BrowserSession] = {}
        self._session_locks: Dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._browser_guard = threading.RLock()
        self._logger = logger_func

        self._shared_playwright = None
        self._shared_browser = None
        self._shared_browser_instance_id = ""
        self._shared_browser_config = None

        self._ensure_dirs()

    def _ensure_dirs(self):
        from services.utils import ensure_dirs

        ensure_dirs()

    def _get_account_lock(self, email: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._session_locks.get(email)
            if lock is None:
                lock = threading.RLock()
                self._session_locks[email] = lock
            return lock

    @contextmanager
    def account_session_scope(self, email: str, operation: str = "操作") -> Iterator[None]:
        """按邮箱串行化会话操作，确保同邮箱同一时刻只有一个流程可运行。"""
        lock = self._get_account_lock(email)
        self._logger(f"🔒 等待账号会话锁[{operation}]: {email}")
        with lock:
            self._logger(f"🔓 已获取账号会话锁[{operation}]: {email}")
            yield

    def run_serialized(self, email: str, operation: str, action: Callable[[], T]) -> T:
        """在邮箱级互斥锁内执行操作。"""
        with self.account_session_scope(email, operation):
            return action()

    def get_session(
        self,
        account: OzonAccount,
        headless: bool = False,
        slow_mo: int = 200,
        storage_state: str = None,
    ) -> BrowserSession:
        """获取或创建账号的浏览器会话。"""
        with self.account_session_scope(account.email, "获取会话"):
            if account.email in self.sessions:
                session = self.sessions[account.email]
                if self._is_session_alive(session):
                    self._refresh_page_registry(session)
                    self._ensure_primary_page(session)
                    self._logger(
                        f"✅ 复用已存在的账号上下文: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
                    )
                    session.last_activity = time.time()
                    return session

                self._logger(
                    f"⚠️ 账号上下文已失效，重新创建: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
                )
                self._close_session(session)

            session = self._create_session(account, headless, slow_mo, storage_state)
            self.sessions[account.email] = session
            return session

    def _new_page_id(self) -> str:
        return uuid.uuid4().hex[:10]

    def _build_browser_config(self, headless: bool, slow_mo: int) -> dict:
        return {
            "headless": headless,
            "slow_mo": slow_mo,
            "args": [
                "--disable-gpu",
                "--start-maximized",
            ],
        }

    def _ensure_shared_browser(self, headless: bool, slow_mo: int):
        desired_config = self._build_browser_config(headless=headless, slow_mo=slow_mo)

        with self._browser_guard:
            if self._shared_browser and self._is_browser_alive(self._shared_browser):
                if self._shared_browser_config != desired_config:
                    self._logger(
                        "ℹ️ 检测到新的浏览器启动参数请求，继续复用现有全局 Browser "
                        f"(current={self._shared_browser_config}, requested={desired_config})"
                    )
                return self._shared_browser

            self._logger("🚀 正在启动全局共享 Browser 实例")
            self._shared_playwright = sync_playwright().start()
            self._shared_browser = self._shared_playwright.chromium.launch(**desired_config)
            self._shared_browser_config = desired_config
            self._shared_browser_instance_id = uuid.uuid4().hex[:12]
            self._logger(
                "✅ 全局共享 Browser 启动成功: "
                f"browser_instance_id={self._shared_browser_instance_id}, config={desired_config}"
            )
            return self._shared_browser

    def _is_browser_alive(self, browser) -> bool:
        if not browser:
            return False
        try:
            _ = browser.contexts
            return True
        except Exception:
            return False

    def _refresh_page_registry(self, session: BrowserSession) -> None:
        """同步 session 中记录的页面集合，允许一个 context 维护多个标签页。"""
        if not session.context:
            session.pages.clear()
            session.page_meta.clear()
            session.page = None
            return

        try:
            context_pages = list(session.context.pages)
        except Exception:
            context_pages = []

        for page_id, page in list(session.pages.items()):
            if page in context_pages and self._is_page_alive(page):
                continue
            session.pages.pop(page_id, None)
            session.page_meta.pop(page_id, None)

        known_pages = {page for page in session.pages.values()}
        for page in context_pages:
            if page in known_pages or not self._is_page_alive(page):
                continue
            self._register_page(session, page, role="shared", operation_name="detected_existing_tab")

        if session.page and not self._is_page_alive(session.page):
            session.page = None

        if session.page not in session.pages.values():
            session.page = None

    def _register_page(self, session: BrowserSession, page, role: str, operation_name: str) -> str:
        page_id = self._new_page_id()
        session.pages[page_id] = page
        session.page_meta[page_id] = {
            "role": role,
            "operation_name": operation_name,
            "created_at": time.time(),
            "last_used_at": time.time(),
        }
        return page_id

    def _get_page_id(self, session: BrowserSession, page) -> Optional[str]:
        for page_id, existing in session.pages.items():
            if existing is page:
                return page_id
        return None

    def _mark_page_used(self, session: BrowserSession, page) -> None:
        page_id = self._get_page_id(session, page)
        if not page_id:
            return
        meta = session.page_meta.get(page_id)
        if meta is not None:
            meta["last_used_at"] = time.time()

    def _ensure_primary_page(self, session: BrowserSession):
        self._refresh_page_registry(session)
        if session.page and self._is_page_alive(session.page):
            self._mark_page_used(session, session.page)
            return session.page

        if session.pages:
            page_id, primary = next(iter(session.pages.items()))
            session.page = primary
            meta = session.page_meta.get(page_id)
            if meta is not None and meta.get("role") == "shared":
                meta["role"] = "primary"
            self._mark_page_used(session, primary)
            return primary

        if not session.context:
            return None

        primary = self._create_managed_page(
            session,
            role="primary",
            operation_name="restore_primary_page",
            make_primary=True,
        )
        return primary

    def _is_page_alive(self, page) -> bool:
        if not page:
            return False
        try:
            _ = page.url
            page.title()
            return True
        except Exception:
            return False

    def create_managed_page(
        self,
        session: BrowserSession,
        role: str = "task",
        operation_name: str = "操作",
        make_primary: bool = False,
    ):
        page = self._create_managed_page(
            session,
            role=role,
            operation_name=operation_name,
            make_primary=make_primary,
        )
        self._logger(
            f"🪟 已创建标签页: email={session.email}, role={role}, operation={operation_name}, total_pages={len(session.pages)}"
        )
        return page

    def _create_managed_page(self, session: BrowserSession, role: str, operation_name: str, make_primary: bool):
        if not session.context:
            raise RuntimeError("浏览器上下文不可用，无法创建标签页")
        page = session.context.new_page()
        self._attach_debug_listeners(page)
        self._apply_stealth(page)
        self._register_page(session, page, role=role, operation_name=operation_name)
        if make_primary or session.page is None:
            session.page = page
        session.touch()
        return page

    def release_page(self, session: BrowserSession, page, keep_primary: bool = True) -> None:
        page_id = self._get_page_id(session, page)
        if not page_id:
            return

        is_primary = session.page is page
        if is_primary and keep_primary:
            self._mark_page_used(session, page)
            return

        session.pages.pop(page_id, None)
        session.page_meta.pop(page_id, None)

        try:
            if self._is_page_alive(page):
                page.close()
        except Exception:
            pass

        if is_primary:
            session.page = None
            self._ensure_primary_page(session)
        session.touch()

    def _is_session_alive(self, session: BrowserSession) -> bool:
        """检查会话是否有效。"""
        if not session.is_alive or not session.context:
            return False

        if not self._is_browser_alive(self._shared_browser):
            return False

        try:
            primary = self._ensure_primary_page(session)
            if not primary:
                return False
            _ = primary.url
            primary.title()
            return True
        except Exception as e:
            self._logger(f"⚠️ 会话检查失败: {e}")
            return False

    def _create_session(self, account: OzonAccount, headless: bool, slow_mo: int, storage_state: str = None) -> BrowserSession:
        """创建新的账号级 BrowserContext，会复用全局 Browser。"""
        browser = self._ensure_shared_browser(headless=headless, slow_mo=slow_mo)
        session = BrowserSession(
            email=account.email,
            storage_path=account.storage_path,
            browser_instance_id=self._shared_browser_instance_id,
        )
        self._logger(
            f"🚀 正在创建账号上下文: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
        )

        if storage_state is None and os.path.exists(account.storage_path):
            storage_state = account.storage_path

        session.context = browser.new_context(
            storage_state=storage_state,
            user_agent=os.environ.get(
                "USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            ),
            viewport={"width": 1600, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            record_video_dir=os.environ.get("VIDEO_DIR", "videos"),
            record_video_size={"width": 1280, "height": 720},
        )

        session.page = self._create_managed_page(
            session,
            role="primary",
            operation_name="bootstrap_primary_page",
            make_primary=True,
        )

        session.mark_alive()
        self._logger(
            f"✅ 账号上下文创建成功: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
        )
        return session

    def _close_session(self, session: BrowserSession):
        """关闭账号级会话，仅销毁其 Context/Page，不关闭共享 Browser。"""
        self._logger(
            f"🛑 正在关闭账号上下文: email={session.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
        )

        try:
            if session.context:
                from services.utils import save_login_state

                save_login_state(session.context, session.storage_path)
        except Exception as e:
            self._logger(f"⚠️ 保存登录态失败: {e}")

        self._refresh_page_registry(session)
        for page in list(session.pages.values()):
            try:
                if self._is_page_alive(page):
                    page.close()
            except Exception:
                pass
        session.pages.clear()
        session.page_meta.clear()
        session.page = None

        try:
            if session.context:
                session.context.close()
        except Exception:
            pass

        session.context = None
        session.mark_dead()
        self._cleanup_shared_browser_if_idle()

    def _cleanup_shared_browser_if_idle(self):
        with self._browser_guard:
            if any(session.is_alive and session.context for session in self.sessions.values()):
                return

            if self._shared_browser:
                try:
                    self._shared_browser.close()
                except Exception:
                    pass
                self._shared_browser = None

            if self._shared_playwright:
                try:
                    self._shared_playwright.stop()
                except Exception:
                    pass
                self._shared_playwright = None

            if self._shared_browser_instance_id:
                self._logger(
                    f"🧹 全局共享 Browser 已释放: browser_instance_id={self._shared_browser_instance_id}"
                )

            self._shared_browser_instance_id = ""
            self._shared_browser_config = None

    def close_all_sessions(self):
        """关闭所有会话。"""
        with self._locks_guard:
            emails = list(self.sessions.keys())
        for email in emails:
            self.close_session(email)

    def close_session(self, email: str):
        """关闭指定邮箱的浏览器会话。"""
        with self.account_session_scope(email, "关闭会话"):
            session = self.sessions.pop(email, None)
            if session:
                self._close_session(session)

    def _attach_debug_listeners(self, page):
        """添加调试监听器。"""

        def on_request(request):
            try:
                if request.method in ("POST", "PUT", "PATCH"):
                    data = request.post_data
                    if data:
                        self._logger(f"[REQUEST BODY] {data[:1500]}")
            except Exception as e:
                self._logger(f"[REQUEST ERROR] {e}")

        def on_response(response):
            try:
                url = response.url.lower()

                if any(
                    k in url
                    for k in [
                        "otp",
                        "auth",
                        "verify",
                        "login",
                        "code",
                        "id.ozon",
                        "widget/json/v2",
                        "_action/emailotpentry",
                    ]
                ):
                    try:
                        text = response.text()
                        self._logger(f"[RESPONSE BODY] {text[:3000]}")
                    except Exception:
                        pass
            except Exception as e:
                self._logger(f"[RESPONSE ERROR] {e}")

        def on_request_failed(request):
            try:
                self._logger(f"[REQUEST FAILED] {request.method} {request.url} -> {request.failure}")
            except Exception as e:
                self._logger(f"[REQUEST FAILED ERROR] {e}")

        def on_console(msg):
            try:
                self._logger(f"[CONSOLE] {msg.type}: {msg.text}")
            except Exception:
                pass

        def on_page_error(error):
            self._logger(f"[PAGE ERROR] {error}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
        page.on("console", on_console)
        page.on("pageerror", on_page_error)

    def _apply_stealth(self, page) -> None:
        try:
            Stealth().apply_stealth_sync(page)
            self._logger("✅ Stealth 注入成功")
        except Exception as e:
            self._logger(f"⚠️ Stealth 注入失败（但不影响后续运行）: {e}")
