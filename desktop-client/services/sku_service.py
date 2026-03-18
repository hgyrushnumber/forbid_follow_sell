#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse
from services.page_service import PageService
from services.utils import sleep, MENU_BUTTONS
from ozon_core import TARGET_URL


class SkuService:
    def __init__(self, logger_func):
        self._logger = logger_func
        self.page_service = PageService(logger_func)
        self._prepared_session_ids = set()

    def _extract_session_id(self, url: str) -> Optional[str]:
        try:
            query = parse_qs(urlparse(url).query)
        except Exception:
            return None
        values = query.get("id") or []
        sid = (values[0] if values else "").strip()
        return sid or None

    def _wait_chat_session_id(self, page, timeout_ms: int = 12000) -> Optional[str]:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                url = page.url or ""
            except Exception:
                url = ""
            sid = self._extract_session_id(url)
            if sid and self.page_service.is_chat_detail_page(page):
                return sid
            sleep(300)
        return None

    def navigate_menu(self, page, menu_config):
        session_id = self._wait_chat_session_id(page)
        if session_id:
            if session_id in self._prepared_session_ids:
                self._logger(f"ℹ️ 会话 {session_id} 已完成投诉入口点击，跳过菜单导航")
                return session_id
            self._logger(f"ℹ️ 检测到投诉会话页 id={session_id}，执行一次菜单点击")
        else:
            self.page_service.normalize_messenger_home(page, TARGET_URL)

        for idx, item in enumerate(menu_config, 1):
            text = (item.get("text") or "").strip()
            ru_text = (item.get("ru_text") or "").strip()

            if not text and not ru_text:
                self._logger(f"⚠️ 菜单配置为空，跳过第 {idx} 项")
                continue

            self._logger(f"🎯 菜单导航 {idx}/{len(menu_config)}: {text or ru_text}")
            self.page_service.click_menu_button(page, text or ru_text, ru_text or None)

        if session_id:
            self._prepared_session_ids.add(session_id)
            self._logger(f"✅ 会话 {session_id} 已标记为完成投诉入口点击")
        return session_id

    def process_single_sku(self, page, sku: str, image_path: str):
        self._logger(f"📦 开始处理 SKU: {sku}")

        sku_input = self.page_service.find_sku_input(page)
        self.page_service.set_input_value(sku_input, sku)

        self.page_service.press_enter(sku_input)
        sleep(2000)

        self.page_service.wait_for_search_result(page, sku)

        file_input = self.page_service.find_file_input(page)
        file_input.set_input_files(image_path)
        self._logger("✅ 图片已选择，等待发送按钮")
        sleep(1500)

        self.page_service.click_send_button(page, file_input, timeout_ms=20000)
        sleep(2000)

        self.page_service.wait_for_upload_finished(page)
        self._logger(f"✅ SKU 处理完成: {sku}")

    def execute(self, page, skus: List[str], image_path: str, menu_config) -> Dict[str, object]:
        session_id = self.navigate_menu(page, menu_config)
        self._logger(f"✅ 菜单导航完成，开始处理 {len(skus)} 个 SKU")

        success_items: List[str] = []
        failed_items: List[Dict[str, str]] = []

        for i, sku in enumerate(skus, 1):
            self._logger(f"➡️ {i}/{len(skus)}")
            try:
                self.process_single_sku(page, sku, image_path)
                success_items.append(sku)
            except Exception as exc:
                failed_items.append({"sku": sku, "error": str(exc)})
                self._logger(f"❌ SKU 处理失败: {sku}, 错误: {exc}")
            sleep(1200)

        summary = {
            "session_id": session_id,
            "total": len(skus),
            "success_count": len(success_items),
            "failed_count": len(failed_items),
            "success_skus": success_items,
            "failed_items": failed_items,
        }
        self._logger(
            f"📊 SKU执行统计: total={summary['total']}, success={summary['success_count']}, failed={summary['failed_count']}"
        )
        return summary
