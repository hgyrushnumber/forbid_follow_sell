#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import os
import queue
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Optional, TypeVar

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from models import OzonAccount, BrowserSession

T = TypeVar("T")


class SessionService:
    """会话管理服务 - 每个邮箱独占一个 Browser，会话操作固定在该邮箱线程执行。"""

    def __init__(self, logger_func):
        self.sessions: Dict[str, BrowserSession] = {}
        self._session_locks: Dict[str, threading.RLock] = {}
        self._workers: Dict[str, dict] = {}
        self._locks_guard = threading.Lock()
        self._workers_guard = threading.Lock()
        self._logger = logger_func
        self._local = threading.local()
        self._ensure_dirs()
        self._start_workers()

    def _ensure_dirs(self):
        from services.utils import ensure_dirs

        ensure_dirs()

    def _start_workers(self) -> None:
        for index in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(index,),
                name=f"session-worker-{index}",
                daemon=True,
            )
            worker.start()
            self._worker_threads.append(worker)
        self._logger(f"🧵 会话工作线程池已启动: count={self._worker_count}")

    def _worker_loop(self, worker_index: int) -> None:
        self._local.worker_index = worker_index
        current_thread = threading.current_thread()
        self._logger(f"🧵 会话工作线程启动: {current_thread.name}({current_thread.ident})")

        while True:
            task = self._worker_queues[worker_index].get()
            event = task["event"]
            try:
                result = self._execute_serialized(task["email"], task["operation"], task["action"])
                task["result"] = result
            except Exception as exc:
                task["exception"] = exc
            finally:
                event.set()

    def _assign_worker_index(self, email: str) -> int:
        digest = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self._worker_count

    def _get_account_lock(self, email: str) -> threading.RLock:
        with self._locks_guard:
            lock = self._session_locks.get(email)
            if lock is None:
                lock = threading.RLock()
                self._session_locks[email] = lock
            return lock

    def _ensure_worker(self, email: str) -> dict:
        with self._workers_guard:
            worker = self._workers.get(email)
            if worker is not None:
                return worker

            task_queue: queue.Queue = queue.Queue()
            ready = threading.Event()
            worker = {
                "email": email,
                "queue": task_queue,
                "ready": ready,
                "thread": None,
                "thread_id": None,
                "thread_name": None,
            }

            thread = threading.Thread(
                target=self._worker_loop,
                args=(worker,),
                name=f"session-email-{uuid.uuid4().hex[:8]}",
                daemon=True,
            )
            worker["thread"] = thread
            self._workers[email] = worker
            thread.start()
            ready.wait()
            self._logger(
                f"🧵 邮箱会话线程已启动: email={email}, thread={worker['thread_name']}({worker['thread_id']})"
            )
            return worker

    def _worker_loop(self, worker: dict) -> None:
        worker["thread_id"] = threading.get_ident()
        worker["thread_name"] = threading.current_thread().name
        self._local.worker_email = worker["email"]
        worker["ready"].set()

        while True:
            task = worker["queue"].get()
            event = task["event"]
            try:
                result = self._execute_serialized(task["email"], task["operation"], task["action"])
                task["result"] = result
            except Exception as exc:
                task["exception"] = exc
            finally:
                event.set()

    @contextmanager
    def account_session_scope(self, email: str, operation: str = "操作") -> Iterator[None]:
        """按邮箱串行化会话操作，确保同邮箱同一时刻只有一个流程可运行。"""
        lock = self._get_account_lock(email)
        self._logger(f"🔒 等待账号会话锁[{operation}]: {email}")
        with lock:
            self._logger(f"🔓 已获取账号会话锁[{operation}]: {email}")
            yield

    def _execute_serialized(self, email: str, operation: str, action: Callable[[], T]) -> T:
        with self.account_session_scope(email, operation):
            return action()

    def run_serialized(self, email: str, operation: str, action: Callable[[], T]) -> T:
        """在邮箱绑定的固定线程中串行执行操作。"""
        current_email = getattr(self._local, "worker_email", None)
        if current_email == email:
            return self._execute_serialized(email, operation, action)

        worker = self._ensure_worker(email)
        event = threading.Event()
        task = {
            "email": email,
            "operation": operation,
            "action": action,
            "event": event,
            "result": None,
            "exception": None,
        }
        worker["queue"].put(task)
        event.wait()
        if task["exception"] is not None:
            raise task["exception"]
        return task["result"]

    def get_session(
        self,
        account: OzonAccount,
        headless: bool = False,
        slow_mo: int = 200,
        storage_state: str = None,
    ) -> BrowserSession:
        """获取或创建账号的浏览器会话。"""
        with self.account_session_scope(account.email, "获取会话"):
            session = self.sessions.get(account.email)
            if session:
                if self._is_session_alive(session):
                    self._refresh_page_registry(session)
                    self._ensure_primary_page(session)
                    self._logger(
                        f"✅ 复用邮箱级浏览器会话: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
                    )
                    session.touch()
                    return session

                self._logger(
                    f"⚠️ 邮箱级浏览器会话已失效，重新创建: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
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

    def _ensure_thread_browser(self, headless: bool, slow_mo: int):
        desired_config = self._build_browser_config(headless=headless, slow_mo=slow_mo)
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name

        with self._browser_guard:
            entry = self._thread_browsers.get(thread_id)
            if entry and self._is_browser_alive(entry.get("browser")):
                if entry.get("config") != desired_config:
                    self._logger(
                        "ℹ️ 当前工作线程检测到新的浏览器启动参数请求，继续复用该线程已有 Browser "
                        f"(thread={thread_name}({thread_id}), current={entry.get('config')}, requested={desired_config})"
                    )
                return entry

            self._logger(f"🚀 正在启动线程级共享 Browser: thread={thread_name}({thread_id})")
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(**desired_config)
            entry = {
                "playwright": playwright,
                "browser": browser,
                "config": desired_config,
                "browser_instance_id": uuid.uuid4().hex[:12],
                "thread_name": thread_name,
            }
            self._thread_browsers[thread_id] = entry
            self._logger(
                "✅ 线程级共享 Browser 启动成功: "
                f"thread={thread_name}({thread_id}), browser_instance_id={entry['browser_instance_id']}, config={desired_config}"
            )
            return entry

    def _is_browser_alive(self, browser) -> bool:
        if not browser:
            return False
        try:
            _ = browser.contexts
            return True
        except Exception:
            return False

    def _refresh_page_registry(self, session: BrowserSession) -> None:
        """同步 session 中记录的页面集合，允许一个 BrowserContext 维护多个标签页。"""
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

    def tag_existing_page(self, session: BrowserSession, page, role: str, operation_name: str) -> None:
        page_id = self._get_page_id(session, page)
        if not page_id:
            page_id = self._register_page(session, page, role=role, operation_name=operation_name)
        meta = session.page_meta.setdefault(page_id, {})
        meta["role"] = role
        meta["operation_name"] = operation_name
        meta["last_used_at"] = time.time()
        session.touch()

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
        if not session.belongs_to_current_thread():
            raise RuntimeError(
                f"账号会话绑定在线程 {session.owner_thread_name}({session.owner_thread_id})，不能在线程 {threading.current_thread().name}({threading.get_ident()}) 上直接创建标签页"
            )
        page = session.context.new_page()
        self._attach_debug_listeners(page)
        self._apply_stealth(page)
        self._register_page(session, page, role=role, operation_name=operation_name)
        if make_primary or session.page is None:
            session.page = page
        session.touch()
        return page

    def release_page(self, session: BrowserSession, page, keep_primary: bool = True, keep_reused: bool = True) -> None:
        page_id = self._get_page_id(session, page)
        if not page_id:
            return

        meta = session.page_meta.get(page_id) or {}
        is_primary = session.page is page
        if is_primary and keep_primary:
            self._mark_page_used(session, page)
            return

        if keep_reused and meta.get("role") == "reused_task":
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
        """检查邮箱会话是否有效。"""
        if not session.is_alive or not session.context or not session.browser:
            return False

        if not session.belongs_to_current_thread():
            return False

        try:
            primary = self._ensure_primary_page(session)
            if not primary:
                return False
            _ = session.browser.contexts
            _ = primary.url
            primary.title()
            return True
        except Exception as e:
            self._logger(f"⚠️ 会话检查失败: {e}")
            return False

    def _create_session(self, account: OzonAccount, headless: bool, slow_mo: int, storage_state: str = None) -> BrowserSession:
        """创建新的邮箱级 Browser / BrowserContext。"""
        session = BrowserSession(
            email=account.email,
            storage_path=account.storage_path,
            owner_thread_id=threading.get_ident(),
            owner_thread_name=threading.current_thread().name,
        )
        self._logger(
            f"🚀 正在启动邮箱级浏览器会话: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}, thread={session.owner_thread_name}({session.owner_thread_id})"
        )

        session.playwright = sync_playwright().start()
        session.browser = session.playwright.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--disable-gpu",
                "--start-maximized",
            ],
        )

        if storage_state is None and os.path.exists(account.storage_path):
            storage_state = account.storage_path

        session.context = browser_entry["browser"].new_context(
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
            f"✅ 邮箱级浏览器会话创建成功: email={account.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
        )
        return session

    def _abandon_session(self, session: BrowserSession) -> None:
        """放弃不可安全跨线程关闭的会话引用，避免触发 Playwright 线程错误。"""
        self._logger(
            "⚠️ 检测到跨线程旧会话，已放弃旧引用并将在新工作线程重建: "
            f"email={session.email}, old_thread={session.owner_thread_name}({session.owner_thread_id}), browser_instance_id={session.browser_instance_id}"
        )
        session.context = None
        session.page = None
        session.pages.clear()
        session.page_meta.clear()
        session.mark_dead()

    def _close_session(self, session: BrowserSession):
        """关闭邮箱级会话，销毁该邮箱独占的 Browser / Context / Page。"""
        self._logger(
            f"🛑 正在关闭邮箱级浏览器会话: email={session.email}, session_key={session.session_key}, browser_instance_id={session.browser_instance_id}"
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

        try:
            if session.browser:
                session.browser.close()
        except Exception:
            pass

        try:
            if session.playwright:
                session.playwright.stop()
        except Exception:
            pass

        session.context = None
        session.browser = None
        session.playwright = None
        session.mark_dead()

    def close_all_sessions(self):
        """关闭所有会话。"""
        with self._locks_guard:
            emails = list(self.sessions.keys())
        for email in emails:
            self.close_session(email)

    def close_session(self, email: str):
        """关闭指定邮箱的浏览器会话。"""

        def _close_current_session() -> None:
            session = self.sessions.pop(email, None)
            if session:
                self._close_session(session)

        self.run_serialized(email, "关闭会话", _close_current_session)

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
