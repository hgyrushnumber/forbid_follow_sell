#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
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

    def is_account_logged_in(self, page):
        """更严格的登录状态校验"""
        try:
            url = page.url.lower()
            # 检查是否在卖家后台页面
            if "/app/dashboard" in url or "/app/messenger" in url:
                # 检查页面是否包含卖家后台特有的元素
                from services.utils import safe_body_text
                body_text = safe_body_text(page)
                return (
                    "Товары и цены" in body_text or  # 商品和价格（俄文）
                    "商品和价格" in body_text or      # 商品和价格（中文）
                    "seller.ozon.ru/app/messenger" in url    # 确保在卖家后台路径下
                )
            return False
        except Exception as e:
            self._logger(f"⚠️ 登录状态校验失败: {e}")
            return False

    def ensure_ready(
        self,
        account: OzonAccount,
        headless: bool = False,
        slow_mo: int = 200,
    ) -> BrowserSession:
        """确保账号对应的唯一浏览器会话已经就绪。"""

        def _prepare() -> BrowserSession:
            self._logger(f"🔍 正在准备账号会话: {account.email}")
            session = self._session_service.get_session(account, headless, slow_mo)
            primary_page = self._session_service._ensure_primary_page(session)

            if not self._session_service._is_session_alive(session):
                raise RuntimeError("浏览器页面不可用")

            # 严格校验登录状态
            try:
                # 导航到目标页面
                primary_page.goto(self._target_url, wait_until="domcontentloaded", timeout=60000)
                self._sleep(3000)

                # 等待页面跳转到目标URL模式
                try:
                    # 先等待dashboard页面
                    primary_page.wait_for_url("**/app/dashboard**", wait_until="load", timeout=30000)
                except Exception:
                    try:
                        # 再等待messenger页面
                        primary_page.wait_for_url("**/app/messenger**", wait_until="load", timeout=30000)
                    except Exception:
                        self._logger("⚠️ 页面未跳转到预期的URL模式（/app/dashboard 或 /app/messenger）")
                self._sleep(3000)

                if self.is_account_logged_in(primary_page):
                    self._logger("✅ 会话已登录并就绪")
                    self._page_service.normalize_messenger_home(primary_page, self._target_url)
                    session.touch()
                    return session
                else:
                    self._logger("⚠️ 检测到未登录页面，将启动登录流程")
                    # 清理失效的登录态文件
                    if os.path.exists(account.storage_path):
                        os.remove(account.storage_path)

            except Exception as e:
                self._logger(f"⚠️ 页面导航或状态检测失败: {e}")

            # 无效登录态，启动完整登录流程
            self._logger("🔄 启动完整登录流程")
            self._page_service.ensure_logged_in_and_ready(
                primary_page,
                session.context,
                account,
                self._target_url,
            )
            self._save_login_state(session.context, account.storage_path)
            self._page_service.normalize_messenger_home(primary_page, self._target_url)

            session.touch()
            self._logger("✅ 登录流程完成，会话已就绪")
            return session

        return self._session_service.run_serialized(account.email, "准备账号会话", _prepare)

    def save_after_task(self, session: BrowserSession, storage_path: str) -> None:
        self._save_login_state(session.context, storage_path)

    def acquire_task_page(
        self,
        account: OzonAccount,
        headless: bool = False,
        slow_mo: int = 200,
        operation_name: str = "执行任务",
    ):
        """在邮箱唯一 BrowserContext 中为当前任务申请一个独立标签页。"""

        def _prepare_task_page():
            session = self.ensure_ready(account, headless=headless, slow_mo=slow_mo)
            task_page = self._session_service.create_managed_page(
                session,
                role="task",
                operation_name=operation_name,
                make_primary=False,
            )
            task_page.goto(self._target_url, wait_until="domcontentloaded", timeout=60000)
            self._sleep(3000)
            self._logger(f"🪟 任务标签页已就绪: {task_page.url}")
            return session, task_page

        return self._session_service.run_serialized(account.email, "申请任务标签页", _prepare_task_page)

    def release_task_page(self, session: BrowserSession, page) -> None:
        self._session_service.release_page(session, page, keep_primary=True)
