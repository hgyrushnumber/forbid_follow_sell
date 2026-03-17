#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from typing import List
from services.page_service import PageService
from services.utils import log, sleep, MENU_BUTTONS
from ozon_core import TARGET_URL


class SkuService:
    def __init__(self, logger_func):
        self._logger = logger_func
        self.page_service = PageService(logger_func)

    def navigate_menu(self, page, menu_config):
        self.page_service.normalize_messenger_home(page, TARGET_URL)

        for idx, item in enumerate(menu_config, 1):
            text = (item.get("text") or "").strip()
            ru_text = (item.get("ru_text") or "").strip()

            if not text and not ru_text:
                self._logger(f"⚠️ 菜单配置为空，跳过第 {idx} 项")
                continue

            self._logger(f"🎯 菜单导航 {idx}/{len(menu_config)}: {text or ru_text}")
            self.page_service.click_menu_button(page, text or ru_text, ru_text or None)

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

    def execute(self, page, skus: List[str], image_path: str, menu_config):
        self.navigate_menu(page, menu_config)
        self._logger(f"✅ 菜单导航完成，开始处理 {len(skus)} 个 SKU")

        for i, sku in enumerate(skus, 1):
            self._logger(f"➡️ {i}/{len(skus)}")
            self.process_single_sku(page, sku, image_path)
            sleep(1200)