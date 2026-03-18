#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Callable

from models import BrowserSession, OzonAccount


class AccountSessionService:
    """账号级会话编排服务：统一管理登录准备与任务前会话复用。"""

    def __init__(
        self,
        logger_func: Callable[[str], None],
        session_service,
        page_service,
        target_url: str,
        sleep_func: Callable[[int], None],
    ):
        self._logger = logger_func
        self._session_service = session_service
        self._page_service = page_service
        self._target_url = target_url
        self._sleep = sleep_func

    def _save_login_state(self, context, storage_path: str) -> None:
        try:
            from services.utils import save_login_state

            save_login_state(context, storage_path)
            self._logger(f"✅ 已刷新并保存登录态: {storage_path}")
        except Exception as exc:
            self._logger(f"⚠️ 保存登录态失败: {exc}")

    def ensure_ready(
        self,
        account: OzonAccount,
        headless: bool = False,
        slow_mo: int = 200,
    ) -> BrowserSession:
        """确保账号对应的唯一浏览器会话已经就绪。"""

        def _prepare() -> BrowserSession:
            session = self._session_service.get_session(account, headless, slow_mo)

            if not self._session_service._is_session_alive(session):
                raise RuntimeError("浏览器页面不可用")

            try:
                current_type = self._page_service.detect_page_type(session.page)
            except Exception:
                current_type = "unknown"

            if current_type not in ("messenger", "company_select", "login", "ozon_id_phone", "otp"):
                session.page.goto(self._target_url, wait_until="domcontentloaded", timeout=60000)
                self._sleep(3000)

            self._logger(f"当前页面: {session.page.url}")
            self._logger(f"当前标题: {session.page.title()}")

            self._page_service.ensure_logged_in_and_ready(
                session.page,
                session.context,
                account,
                self._target_url,
            )
            self._save_login_state(session.context, account.storage_path)
            self._page_service.normalize_messenger_home(session.page, self._target_url)

            session.touch()
            self._logger(f"浏览器准备完成，当前页面: {session.page.url}")
            return session

        return self._session_service.run_serialized(account.email, "准备账号会话", _prepare)

    def save_after_task(self, session: BrowserSession, storage_path: str) -> None:
        self._save_login_state(session.context, storage_path)
