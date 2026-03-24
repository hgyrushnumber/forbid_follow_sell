#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import datetime
import os
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from services.page_service import PageService
from services.utils import sleep
from services.constants import MENU_BUTTONS, TARGET_URL
from services.constants import RU_SKU_VERIFICATION_TEXT, RU_SKU_VERIFICATION_TIMEOUT, ZH_LANGUAGE_CODE
from models import SkuProcessResult


class SkuService:
    def __init__(self, logger_func):
        self._logger = logger_func
        self.page_service = PageService(logger_func)
        self._prepared_session_ids = set()
        self.verification_screenshots_dir = "verification_screenshots"
        os.makedirs(self.verification_screenshots_dir, exist_ok=True)

    def _save_verification_screenshot(self, page, sku: str) -> Optional[str]:
        """保存验证成功后的截图，返回截图路径"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_sku = sku.replace("/", "_").replace("\\", "_").replace(":", "_")[:50]
            filename = f"sku_verified_{safe_sku}_{timestamp}.png"
            screenshot_path = os.path.join(self.verification_screenshots_dir, filename)
            page.screenshot(path=screenshot_path, full_page=True)
            self._logger(f"📸 验证截图已保存: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            self._logger(f"⚠️ 保存验证截图失败: {e}")
            return None

    def _wait_for_sku_verification_ru(self, page, sku: str, timeout_sec: int = RU_SKU_VERIFICATION_TIMEOUT) -> Optional[str]:
        """等待俄文验证成功消息，返回验证截图路径"""
        deadline = time.time() + timeout_sec
        verification_text = RU_SKU_VERIFICATION_TEXT

        self._logger(f"⏳ 等待俄文验证成功提示（包含 '{verification_text}'），超时: {timeout_sec}秒")

        while time.time() < deadline:
            try:
                body_text = page.locator("body").inner_text(timeout=1000)
                if verification_text in body_text:
                    self._logger(f"✅ 检测到验证成功提示: {verification_text}")
                    return self._save_verification_screenshot(page, sku)

                elapsed = time.time() - (deadline - timeout_sec)
                if elapsed > 5:  # 每5秒输出一次进度
                    self._logger(f"⏳ 等待验证中... {int(elapsed)}秒")
                    deadline = time.time() + timeout_sec  # 重置进度输出计时
            except Exception:
                pass
            sleep(500)

        self._logger(f"⚠️ 等待验证成功提示超时: {sku}")
        return None

    def _check_language_before_process(self, page) -> str:
        """检查语言并返回，如果是 zh-hans 则抛出异常"""
        lang = self._detect_language(page)
        if lang == "zh":
            # 进一步检查是否为 zh-hans
            try:
                cookies = page.context.cookies()
                for cookie in cookies:
                    if cookie.get("name") == "x-o3-language":
                        lang_value = cookie.get("value", "")
                        if lang_value.lower() in ("zh-hans", "zh_hans"):
                            raise RuntimeError(f"当前语言为 {lang_value}，暂不支持验证，跳过处理")
                            break
            except Exception as e:
                if "暂不支持" in str(e):
                    raise
        return lang
    def _extract_session_id(self, url: str) -> Optional[str]:
        """
        从URL中提取session_id参数
        使用正则表达式匹配UUID格式的ID，更高效和准确
        """
        if not url:
            return None

        import re
        # 正则表达式模式：匹配id=后面的UUID格式字符串
        pattern = r'[?&]id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
        match = re.search(pattern, url, re.IGNORECASE)

        if match:
            return match.group(1).strip()

        # 兼容使用urllib.parse的方式作为备用
        try:
            query = parse_qs(urlparse(url).query)
            values = query.get("id") or []
            sid = (values[0] if values else "").strip()
            return sid or None
        except Exception:
            return None

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

    def _detect_language(self, page) -> str:
        """检测当前页面语言，返回 'ru' 或 'zh'。"""
        try:
            cookies = page.context.cookies()
            for cookie in cookies:
                if cookie.get("name") == "x-o3-language":
                    lang = cookie.get("value", "")
                    if lang == "ru":
                        return "ru"
                    if lang in ("zh-Hans", "zh", "zh-CN", "zh_Hans"):
                        return "zh"
        except Exception as e:
            self._logger(f"⚠️ 读取 cookie 失败: {e}")

        # 兜底：根据页面文本判断
        try:
            body_text = page.locator("body").inner_text(timeout=2000)
            if "Товары и Цены" in body_text or "Контроль качества" in body_text:
                return "ru"
            if "商品和价格" in body_text or "质量监督" in body_text:
                return "zh"
        except Exception:
            pass

        return "zh"  # 默认中文

    def _is_menu_text_visible(self, page, text: str) -> bool:
        value = (text or "").strip()
        if not value:
            return False

        try:
            role_loc = page.get_by_role("button", name=value)
            if role_loc.count() > 0 and role_loc.first.is_visible():
                return True
        except Exception:
            pass

        try:
            text_loc = page.get_by_text(value, exact=False)
            count = text_loc.count()
            for i in range(count):
                if text_loc.nth(i).is_visible():
                    return True
        except Exception:
            pass

        return False

    def _detect_language_by_menu(self, page, menu_config: list) -> Tuple[Optional[str], int, int]:
        zh_hits = 0
        ru_hits = 0

        for item in menu_config or []:
            zh_text = (item.get("text") or "").strip()
            ru_text = (item.get("ru_text") or "").strip()

            if zh_text and self._is_menu_text_visible(page, zh_text):
                zh_hits += 1
            if ru_text and self._is_menu_text_visible(page, ru_text):
                ru_hits += 1

        if zh_hits == 0 and ru_hits == 0:
            return None, zh_hits, ru_hits

        if ru_hits > zh_hits:
            return "ru", zh_hits, ru_hits
        if zh_hits > ru_hits:
            return "zh", zh_hits, ru_hits

        # 平局兜底：命中仅俄文第4步（中文为空）时判定为 ru
        for item in menu_config or []:
            zh_text = (item.get("text") or "").strip()
            ru_text = (item.get("ru_text") or "").strip()
            if (not zh_text) and ru_text and self._is_menu_text_visible(page, ru_text):
                return "ru", zh_hits, ru_hits

        return None, zh_hits, ru_hits

    def _filter_menu_by_language(self, menu_config: list, lang: str) -> list:
        """根据语言过滤菜单项。"""
        filtered = []
        for item in menu_config:
            if lang == "ru":
                # 俄文：使用 ru_text，跳过 text 为 None 的项（如果有）
                ru_text = (item.get("ru_text") or "").strip()
                if ru_text:
                    filtered.append({"text": ru_text, "ru_text": ru_text})
            else:
                # 中文：使用 text，跳过 text 为 None 的项
                text = (item.get("text") or "").strip()
                if text:
                    filtered.append({"text": text, "ru_text": item.get("ru_text", "")})
        return filtered

    def navigate_menu(self, page, menu_config):
        session_id = self._wait_chat_session_id(page)
        if session_id and session_id in self._prepared_session_ids:
            self._logger(f"ℹ️ 会话 {session_id} 已完成投诉入口点击，跳过菜单导航")
            return session_id

        if session_id:
            self._logger(f"ℹ️ 检测到未缓存的投诉会话页 id={session_id}，补做一次菜单点击")
        else:
            self.page_service.normalize_messenger_home(page, TARGET_URL)
            self._logger("ℹ️ 当前尚未进入投诉会话页，将按菜单路径首次进入目标会话")

        # 检测语言并过滤菜单：优先用可见菜单文本，兜底回退 cookie/正文判断
        lang_by_menu, zh_hits, ru_hits = self._detect_language_by_menu(page, menu_config)
        if lang_by_menu:
            lang = lang_by_menu
            self._logger(f"ℹ️ 语言判定(菜单命中): {lang}, zh_hits={zh_hits}, ru_hits={ru_hits}")
        else:
            lang = self._detect_language(page)
            self._logger(f"ℹ️ 语言判定(cookie/正文回退): {lang}, zh_hits={zh_hits}, ru_hits={ru_hits}")
        filtered_menu = self._filter_menu_by_language(menu_config, lang)

        for idx, item in enumerate(filtered_menu, 1):
            text = (item.get("text") or "").strip()
            ru_text = (item.get("ru_text") or "").strip()

            if not text and not ru_text:
                self._logger(f"⚠️ 菜单配置为空，跳过第 {idx} 项")
                continue

            self._logger(f"🎯 菜单导航 {idx}/{len(filtered_menu)}: {text or ru_text}")
            next_labels: List[str] = []
            if idx < len(filtered_menu):
                next_item = filtered_menu[idx]
                next_text = (next_item.get("text") or "").strip()
                next_ru_text = (next_item.get("ru_text") or "").strip()
                if next_text:
                    next_labels.append(next_text)
                if next_ru_text and next_ru_text not in next_labels:
                    next_labels.append(next_ru_text)

            self.page_service.click_menu_button(
                page,
                text or ru_text,
                ru_text or None,
                expected_next_texts=next_labels,
                require_input=(idx == len(filtered_menu)),
            )

        resolved_session_id = session_id or self._wait_chat_session_id(page, timeout_ms=15000)
        if resolved_session_id:
            self._prepared_session_ids.add(resolved_session_id)
            self._logger(f"✅ 会话 {resolved_session_id} 已标记为完成投诉入口点击")
        else:
            self._logger("⚠️ 菜单点击后仍未识别到投诉会话 id，本次不缓存会话状态")
        return resolved_session_id

    def process_single_sku(self, page, sku: str, image_path: str) -> SkuProcessResult:
        self._logger(f"📦 开始处理 SKU: {sku}")

        result = SkuProcessResult(sku=sku, stage="init")

        try:
            result.stage = "search"

            sku_input = self.page_service.find_sku_input(page)
            self.page_service.set_input_value(sku_input, sku)
            self.page_service.press_enter(sku_input)
            sleep(2000)

            self.page_service.wait_for_search_result(page, sku)

            result.stage = "upload"

            file_input = self.page_service.find_file_input(page)
            file_input.set_input_files(image_path)
            self._logger("✅ 图片已选择，等待发送按钮")
            sleep(1500)

            self.page_service.click_send_button(page, file_input, timeout_ms=20000)
            sleep(2000)

            self.page_service.wait_for_upload_finished(page)

            result.stage = "verify"

            lang = self._check_language_before_process(page)

            if lang == "ru":
                screenshot_path = self._wait_for_sku_verification_ru(page, sku)
                result.verification_screenshot = screenshot_path or ""
                if screenshot_path:
                    self.page_service.click_continue_complaint_button(page)
                    result.stage = "finish"
                    result.success = True
                    result.message = "验证成功"
                else:
                    result.stage = "failed"
                    result.message = "等待验证超时"
            else:
                result.stage = "finish"
                result.success = True
                result.message = f"语言 {lang} 跳过验证"

            self._logger(f"✅ SKU 处理完成: {sku}, 状态: {result.stage}")

        except Exception as exc:
            result.stage = "failed"
            result.message = str(exc)
            self._logger(f"❌ SKU 处理失败: {sku}, 错误: {exc}")

        return result

    def execute(self, page, skus: List[str], image_path: str, menu_config) -> Dict[str, object]:
        session_id = self.navigate_menu(page, menu_config)
        self._logger(f"✅ 菜单导航完成，开始处理 {len(skus)} 个 SKU")

        processed_results: List[SkuProcessResult] = []

        for i, sku in enumerate(skus, 1):
            self._logger(f"➡️ {i}/{len(skus)}")
            result = self.process_single_sku(page, sku, image_path)
            processed_results.append(result)
            sleep(1200)

        success_count = sum(1 for r in processed_results if r.success)
        failed_count = len(processed_results) - success_count

        summary = {
            "session_id": session_id,
            "total": len(skus),
            "success_count": success_count,
            "failed_count": failed_count,
            "processed_skus": [r.to_dict() for r in processed_results],
        }
        self._logger(
            f"📊 SKU执行统计: total={summary['total']}, success={summary['success_count']}, failed={summary['failed_count']}"
        )
        return summary
