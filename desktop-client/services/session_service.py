#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
from typing import Dict, Optional
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from models import OzonAccount, BrowserSession


class SessionService:
    """会话管理服务 - 管理多账号的浏览器会话"""

    def __init__(self, logger_func):
        self.sessions: Dict[str, BrowserSession] = {}
        self._logger = logger_func
        self._ensure_dirs()

    def _ensure_dirs(self):
        from services.utils import ensure_dirs
        ensure_dirs()

    def get_session(self, account: OzonAccount, headless: bool = False, slow_mo: int = 200) -> BrowserSession:
        """获取或创建账号的浏览器会话"""
        if account.email in self.sessions:
            session = self.sessions[account.email]
            if self._is_session_alive(session):
                self._logger(f"✅ 复用已存在的会话: {account.email}")
                session.last_activity = time.time()
                return session
            else:
                self._logger(f"⚠️ 会话已失效，创建新会话: {account.email}")
                self._close_session(session)

        session = self._create_session(account, headless, slow_mo)
        self.sessions[account.email] = session
        return session

    def _is_session_alive(self, session: BrowserSession) -> bool:
        """检查会话是否有效"""
        if not session.is_alive or not session.page:
            return False

        try:
            # 尝试访问页面属性来判断会话是否有效
            _ = session.page.url
            session.page.title()
            return True
        except Exception as e:
            self._logger(f"⚠️ 会话检查失败: {e}")
            return False

    def _create_session(self, account: OzonAccount, headless: bool, slow_mo: int) -> BrowserSession:
        """创建新的浏览器会话"""
        self._logger(f"🚀 正在启动新的浏览器会话: {account.email}")

        session = BrowserSession(
            email=account.email,
            storage_path=account.storage_path
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

        # 加载已有的登录状态
        storage_state = account.storage_path if os.path.exists(account.storage_path) else None

        session.context = session.browser.new_context(
            storage_state=storage_state,
            user_agent=os.environ.get("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            viewport={"width": 1600, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            record_video_dir=os.environ.get("VIDEO_DIR", "videos"),
            record_video_size={"width": 1280, "height": 720},
        )

        session.page = session.context.new_page()
        self._attach_debug_listeners(session.page)

        try:
            Stealth().apply_stealth_sync(session.page)
            self._logger("✅ Stealth 注入成功")
        except Exception as e:
            self._logger(f"⚠️ Stealth 注入失败（但不影响后续运行）: {e}")

        session.is_alive = True
        session.last_activity = time.time()

        self._logger(f"✅ 会话创建成功: {account.email}")
        return session

    def _close_session(self, session: BrowserSession):
        """关闭会话"""
        self._logger(f"🛑 正在关闭会话: {session.email}")

        try:
            if session.context:
                from services.utils import save_login_state
                save_login_state(session.context, session.storage_path)
        except Exception as e:
            self._logger(f"⚠️ 保存登录态失败: {e}")

        try:
            if session.page:
                session.page.close()
        except Exception:
            pass

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

        session.is_alive = False

    def close_all_sessions(self):
        """关闭所有会话"""
        for email, session in list(self.sessions.items()):
            self._close_session(session)
            del self.sessions[email]

    def close_session(self, email: str):
        """关闭指定邮箱的浏览器会话"""
        if email in self.sessions:
            session = self.sessions[email]
            self._close_session(session)
            del self.sessions[email]

    def _attach_debug_listeners(self, page):
        """添加调试监听器"""
        def on_request(request):
            try:
                self._logger(f"[REQUEST] {request.method} {request.url}")
                if request.method in ("POST", "PUT", "PATCH"):
                    data = request.post_data
                    if data:
                        self._logger(f"[REQUEST BODY] {data[:1500]}")
            except Exception as e:
                self._logger(f"[REQUEST ERROR] {e}")

        def on_response(response):
            try:
                self._logger(f"[RESPONSE] {response.status} {response.url}")
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