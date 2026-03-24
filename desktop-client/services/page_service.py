#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from urllib.parse import parse_qs, urlparse
from typing import List, Optional
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from services.utils import safe_body_text, log, sleep, escape_xpath_text, build_text_xpaths, find_visible_by_xpaths
from services.page_state_detector import detect_page_type as _detect_page_type, is_messenger_page as _is_messenger_page


class PageService:
    def __init__(self, logger_func):
        self._logger = logger_func

    def detect_page_type(self, page):
        """统一委托给页面状态识别器。"""
        return _detect_page_type(page)

    def is_messenger_page(self, page) -> bool:
        return _is_messenger_page(page)

    def is_company_select_page(self, page) -> bool:
        return self.detect_page_type(page) == "company_select"

    def is_chat_detail_page(self, page) -> bool:
        try:
            url = page.url or ""
        except Exception:
            url = ""
        return "/app/messenger/" in url and ("group=" in url or "id=" in url)

    def extract_session_id(self, url: str) -> Optional[str]:
        """
        从URL中提取session_id参数
        """
        if not url:
            return None

        try:
            query = parse_qs(urlparse(url).query)
        except Exception:
            return None
        values = query.get("id") or []
        sid = (values[0] if values else "").strip()
        return sid or None

    def extract_session_id_with_regex(self, url: str) -> Optional[str]:
        """
        使用正则表达式从URL中提取session_id参数
        匹配格式: id=42c24dbf-26ed-401d-a41a-f1c7088c17bc
        """
        if not url:
            return None

        import re
        pattern = r'[?&]id=([^&]+)'
        match = re.search(pattern, url)

        if match:
            return match.group(1).strip()

        return None

    def is_support_v2_page(self, page) -> bool:
        """
        判断是否是support_v2页面
        使用正则表达式匹配URL中的id和group参数，更高效和准确
        """
        try:
            url = page.url or ""
        except Exception:
            return False

        # 检查URL中是否包含/app/messenger/
        if "/app/messenger/" not in url:
            return False

        # 使用正则表达式匹配id和group参数
        import re
        # 匹配id=xxx（支持UUID格式）
        id_match = re.search(r'[?&]id=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', url, re.IGNORECASE)
        # 匹配group=support_v2
        group_match = re.search(r'[?&]group=support_v2', url, re.IGNORECASE)

        return bool(id_match and group_match)

    def extract_session_id_with_regex(self, url: str) -> Optional[str]:
        """
        使用正则表达式从URL中提取session_id参数
        匹配格式: id=42c24dbf-26ed-401d-a41a-f1c7088c17bc
        """
        if not url:
            return None

        import re
        pattern = r'[?&]id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
        match = re.search(pattern, url, re.IGNORECASE)

        if match:
            return match.group(1).strip()

        return None

    def normalize_messenger_home(self, page, TARGET_URL):
        if self.is_chat_detail_page(page):
            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""
            session_id = self.extract_session_id(current_url)
            if session_id:
                self._logger(f"ℹ️ 当前处于具体会话页 {session_id}，保留状态并跳过跳转")
                return session_id
            self._logger("ℹ️ 当前处于具体会话页，但未识别到会话id，继续跳转 messenger 首页")
        else:
            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""
            if not (self.is_chat_detail_page(page) and self.extract_session_id(current_url)):
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                sleep(4000)
                self._logger(f"✅ 已回到 messenger 首页: {page.url}")
            else:
                sid = self.extract_session_id(current_url)
                self._logger(f"ℹ️ 保留聊天会话 {sid}，跳过跳转到 TARGET_URL")


    def has_any_menu_button(self, page, menu_config) -> bool:
        for item in menu_config:
            names = [item.get("text"), item.get("ru_text")]
            for name in [n.strip() for n in names if n and n.strip()]:
                try:
                    loc = page.get_by_role("button", name=name)
                    if loc.count() > 0 and loc.first.is_visible():
                        return True
                except Exception:
                    pass

                try:
                    loc = page.get_by_text(name, exact=False)
                    count = loc.count()
                    for i in range(count):
                        if loc.nth(i).is_visible():
                            return True
                except Exception:
                    pass
        return False

    def has_support_compose_prompt(self, page) -> bool:
        prompt_texts = [
            "您正在给客服发短信",
            "您正在给客服发送短信",
            "Вы пишете в поддержку",
        ]

        for text in prompt_texts:
            try:
                loc = page.get_by_text(text, exact=False)
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            except Exception:
                pass

        try:
            body_text = page.locator("body").inner_text(timeout=1000)
            return any(text in body_text for text in prompt_texts)
        except Exception:
            return False

    def has_closed_session_prompt(self, page) -> bool:
        """
        检测是否是已关闭的会话页面
        如: "Обращение закрыто. Если есть вопрос, создайте новое обращение"
        或中文版本
        """
        closed_texts = [
            "Обращение закрыто",
            "Вы больше не можете отвечать на это обращение",
            "您已无法回复此对话",
            "对话已关闭",
            "Обращение завершено",
            "对话已结束",
        ]

        for text in closed_texts:
            try:
                loc = page.get_by_text(text, exact=False)
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            except Exception:
                pass

        try:
            body_text = page.locator("body").inner_text(timeout=1000)
            return any(text in body_text for text in closed_texts)
        except Exception:
            return False

    def is_ready_for_new_chat(self, page) -> bool:
        """
        检查页面是否准备好开始新的聊天
        包括两种情况：
        1. 显示"您正在给客服发短信"等提示
        2. 显示已关闭会话提示，可以创建新对话
        """
        return self.has_support_compose_prompt(page) or self.has_closed_session_prompt(page)

    def has_visible_sku_input(self, page) -> bool:
        selectors = ["textarea", "input[type='text']"]
        for selector in selectors:
            try:
                loc = page.locator(selector)
                count = loc.count()
                for i in range(count):
                    if loc.nth(i).is_visible():
                        return True
            except Exception:
                pass
        return False

    def is_reusable_task_page(self, page, menu_config) -> bool:
        if not self.is_chat_detail_page(page):
            return False

        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""

        if "id=" not in current_url:
            return False

        # 如果页面显示"Обращение закрыто"，表示会话已结束，不可复用，需要创建新标签页
        if self.has_closed_session_prompt(page):
            return False

        # 检查是否已经准备好进行聊天（有输入框且有提示文本）
        if self.has_support_compose_prompt(page):
            return self.has_visible_sku_input(page)

        # 否则需要检查是否有菜单按钮
        return self.has_any_menu_button(page, menu_config)

    def is_reusable_support_task_page(self, page, menu_config) -> bool:
        if not self.is_support_v2_page(page):
            return False

        # 如果页面显示"Обращение закрыто"，表示会话已结束，不可复用，需要创建新标签页
        if self.has_closed_session_prompt(page):
            return False

        return self.has_any_menu_button(page, menu_config) or (
            self.has_support_compose_prompt(page) and self.has_visible_sku_input(page)
        )

    def wait_for_url_contains(self, page, keyword: str, timeout_ms: int = 20000) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                if keyword in page.url:
                    return True
            except Exception:
                pass
            sleep(300)
        return False

    # 公司选择页处理
    def click_next_button(self, page, timeout_ms=10000):
        candidate_texts = ["下一步", "Далее", "Next"]

        deadline = time.time() + timeout_ms / 1000
        last_error = None

        while time.time() < deadline:
            for text in candidate_texts:
                try:
                    btn = page.get_by_role("button", name=text)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.scroll_into_view_if_needed()
                        sleep(300)
                        btn.first.click(timeout=5000)
                        self._logger(f"✅ 已点击按钮: {text}")
                        return True
                except Exception as e:
                    last_error = e

            for text in candidate_texts:
                try:
                    btn = page.get_by_text(text, exact=True)
                    if btn.count() > 0 and btn.first.is_visible():
                        btn.first.scroll_into_view_if_needed()
                        sleep(300)
                        btn.first.click(timeout=5000)
                        self._logger(f"✅ 已通过文本点击按钮: {text}")
                        return True
                except Exception as e:
                    last_error = e

            sleep(500)

        self._logger(f"⚠️ 点击下一步失败: {last_error}")
        return False

    def click_first_company_option(self, page):
        exclude_words = [
            "添加公司", "退出", "下一步",
            "Добавить компанию", "Выйти", "Далее",
            "帮助中心", "个人信息处理的条件",
            "中文", "Русский", "English",
        ]

        radio_selectors = [
            "[role='radio']",
            "label:has(input[type='radio'])",
            "input[type='radio']",
        ]

        for selector in radio_selectors:
            try:
                loc = page.locator(selector)
                count = loc.count()
                self._logger(f"尝试公司候选选择器 {selector}，数量: {count}")

                for i in range(count):
                    try:
                        item = loc.nth(i)
                        if not item.is_visible():
                            continue

                        clickable = item
                        if selector == "input[type='radio']":
                            try:
                                parent = item.locator("xpath=ancestor::*[self::label or self::div][1]")
                                if parent.count() > 0:
                                    clickable = parent.first
                            except Exception:
                                clickable = item

                        clickable.scroll_into_view_if_needed()
                        sleep(300)
                        clickable.click(timeout=5000)
                        self._logger(f"✅ 已点击公司候选项（radio类），第 {i + 1} 个")
                        sleep(1000)
                        return True
                    except Exception as e:
                        self._logger(f"⚠️ 点击 radio 候选失败，第 {i + 1} 个: {e}")
            except Exception as e:
                self._logger(f"⚠️ 枚举选择器失败 {selector}: {e}")

        candidate_selectors = ["label", "div"]

        for selector in candidate_selectors:
            try:
                loc = page.locator(selector)
                count = loc.count()
                self._logger(f"尝试公司卡片选择器 {selector}，数量: {count}")

                for i in range(count):
                    try:
                        item = loc.nth(i)
                        if not item.is_visible():
                            continue

                        txt = item.inner_text(timeout=500).strip()
                        if not txt:
                            continue

                        if any(word in txt for word in exclude_words):
                            continue

                        looks_like_company = (
                            ("@" in txt) or
                            ("*" in txt) or
                            ("+" in txt) or
                            ("\n" in txt)
                        )
                        if not looks_like_company:
                            continue

                        if len(txt) > 300:
                            continue

                        item.scroll_into_view_if_needed()
                        sleep(300)
                        item.click(timeout=5000)
                        self._logger(f"✅ 已点击公司候选项（文本结构识别），第 {i + 1} 个")
                        self._logger(f"候选内容: {txt[:120]}")
                        sleep(1000)
                        return True
                    except Exception as e:
                        self._logger(f"⚠️ 点击公司卡片失败，第 {i + 1} 个: {e}")
            except Exception as e:
                self._logger(f"⚠️ 枚举公司卡片失败 {selector}: {e}")

        return False

    def handle_company_select(self, page):
        self._logger("检测到公司选择页，开始处理...")
        from services.utils import dump_page_state
        dump_page_state(page, "company_select_before")

        selected = self.click_first_company_option(page)
        if not selected:
            self._logger("⚠️ 未能识别并点击公司项")
            from services.utils import dump_page_state
            dump_page_state(page, "error_company_option_not_found")
            return False

        next_ok = self.click_next_button(page, timeout_ms=10000)
        if not next_ok:
            self._logger("⚠️ 未能点击下一步")
            from services.utils import dump_page_state
            dump_page_state(page, "error_click_next_after_company_select")
            return False

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        sleep(3000)
        from services.utils import dump_page_state
        dump_page_state(page, "company_select_after")
        return True

    # OTP 登录恢复
    def is_on_otp_page(self, page):
        body_text = safe_body_text(page)
        try:
            current_url = page.url
        except Exception:
            current_url = ""

        return (
            "Введите код" in body_text
            or "Отправили код на почту" in body_text
            or "Получить новый код" in body_text
            or "输入验证码" in body_text
            or "/otp" in current_url
            or "id.ozon.ru/otp" in current_url
        )

    def log_input_candidates(self, page, tag="OTP_INPUT_DEBUG"):
        try:
            inputs = page.locator("input")
            count = inputs.count()
            self._logger(f"[{tag}] 当前页面 input 数量: {count}")

            for i in range(count):
                try:
                    el = inputs.nth(i)
                    info = el.evaluate(
                        """e => ({
                            type: e.getAttribute('type'),
                            name: e.getAttribute('name'),
                            value: e.value || '',
                            placeholder: e.getAttribute('placeholder'),
                            className: e.className || '',
                            inputMode: e.getAttribute('inputmode'),
                            autocomplete: e.getAttribute('autocomplete'),
                            outerHTML: e.outerHTML.slice(0, 300)
                        })"""
                    )
                    self._logger(f"[{tag}] input[{i}]: {info}")
                except Exception as e:
                    self._logger(f"[{tag}] 读取 input[{i}] 失败: {e}")
        except Exception as e:
            self._logger(f"[{tag}] 枚举 input 失败: {e}")

    def get_otp_input_locator(self, page):
        if not self.is_on_otp_page(page):
            return None, None

        try:
            named = page.locator("input[name='otp']")
            if named.count() > 0:
                first = named.first
                if first.is_visible():
                    return "otp_named", first
        except Exception:
            pass

        try:
            text_inputs = page.locator("input[type='text']")
            count = text_inputs.count()

            visible_candidates = []
            for i in range(count):
                try:
                    el = text_inputs.nth(i)
                    if not el.is_visible():
                        continue

                    info = el.evaluate(
                        """e => ({
                            value: e.value || '',
                            className: e.className || '',
                            placeholder: e.getAttribute('placeholder') || '',
                            inputMode: e.getAttribute('inputmode') || '',
                            autocomplete: e.getAttribute('autocomplete') || '',
                            outerHTML: e.outerHTML.slice(0, 300)
                        })"""
                    )
                    visible_candidates.append((el, info))
                except Exception:
                    continue

            for el, info in visible_candidates:
                value = info.get("value", "")
                class_name = info.get("className", "")
                outer_html = info.get("outerHTML", "")

                if "−" in value or "—" in value:
                    return "otp_masked_text", el

                if "input-code" in class_name.lower() or "dsinputcode" in outer_html.lower():
                    return "otp_masked_text", el

            if len(visible_candidates) == 1:
                return "otp_generic_text", visible_candidates[0][0]

            for el, info in visible_candidates:
                value = (info.get("value", "") or "").replace(" ", "")
                if len(value) <= 10:
                    return "otp_generic_text", el

        except Exception:
            pass

        return None, None

    def wait_for_otp_input(self, page, timeout_ms=30000):
        start = time.time()
        timeout_sec = timeout_ms / 1000

        while time.time() - start < timeout_sec:
            kind, locator = self.get_otp_input_locator(page)
            if kind and locator:
                try:
                    locator.wait_for(state="visible", timeout=1000)
                    return kind, locator
                except Exception:
                    pass

            page_type = self.detect_page_type(page)
            if page_type in ("blocked", "dashboard", "messenger", "company_select"):
                return "page_changed", None

            sleep(500)

        return None, None

    def clear_and_type_otp(self, otp_input, otp_code, page, input_kind):
        otp_input.wait_for(state="visible", timeout=10000)
        otp_input.click()
        sleep(300)

        if input_kind == "otp_named":
            try:
                otp_input.fill("")
            except Exception:
                try:
                    otp_input.press("Control+A")
                    otp_input.press("Backspace")
                except Exception:
                    pass

            otp_input.type(otp_code, delay=180)
            return

        try:
            otp_input.press("Control+A")
            otp_input.press("Backspace")
            sleep(200)
        except Exception:
            pass

        for ch in otp_code:
            otp_input.type(ch, delay=180)
            sleep(80)

    def wait_for_post_otp_result(self, page, timeout_ms=20000):
        start = time.time()
        timeout_sec = timeout_ms / 1000

        while time.time() - start < timeout_sec:
            page_type = self.detect_page_type(page)

            if page_type in ("dashboard", "company_select", "messenger", "blocked"):
                return page_type

            try:
                body_text = page.locator("body").inner_text(timeout=1000)

                if "Произошла ошибка. Попробуйте еще раз" in body_text:
                    return "otp_error"
                if "Неверный код" in body_text or "Неправильный код" in body_text:
                    return "otp_error"
                if "验证码错误" in body_text or "验证码无效" in body_text:
                    return "otp_error"
            except Exception:
                pass

            sleep(500)

        final_type = self.detect_page_type(page)
        if final_type == "otp":
            return "otp_still_here"
        return final_type

    def _click_primary_login_button(self, page) -> bool:
        try:
            from services.utils import dump_page_state
            dump_page_state(page, "before_click_login")

            try:
                login_btn = page.get_by_text("Войти", exact=True).first
                login_btn.wait_for(state="visible", timeout=5000)
            except Exception:
                login_btn = page.get_by_text("登录", exact=True).first
                login_btn.wait_for(state="visible", timeout=5000)

            login_btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)
            self._logger("✅ 第1步完成：已点击登录按钮")
            dump_page_state(page, "after_click_login")
            return True
        except Exception as e:
            self._logger(f"⚠️ 第1步失败：点击登录按钮失败: {e}")
            from services.utils import dump_page_state
            dump_page_state(page, "error_click_login")
            return False

    def _click_email_login_button(self, page) -> bool:
        try:
            from services.utils import dump_page_state
            dump_page_state(page, "before_click_email_login")

            try:
                email_login_btn = page.get_by_text("Войти по почте", exact=True).first
                email_login_btn.wait_for(state="visible", timeout=5000)
            except Exception:
                email_login_btn = page.get_by_text("使用邮箱登录", exact=True).first
                email_login_btn.wait_for(state="visible", timeout=5000)

            email_login_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            self._logger("✅ 第2步完成：已点击通过邮箱登录")
            dump_page_state(page, "after_click_email_login")
            return True
        except Exception as e:
            self._logger(f"⚠️ 第2步失败：点击通过邮箱登录失败: {e}")
            from services.utils import dump_page_state
            dump_page_state(page, "error_click_email_login")
            return False

    def _submit_email_for_login(self, page, email: str) -> bool:
        try:
            page.wait_for_selector("input[type='email']", timeout=20000)
            self._logger("✅ 第3步完成：邮箱输入框已出现")
            from services.utils import dump_page_state
            dump_page_state(page, "email_input_visible")
        except Exception as e:
            self._logger(f"⚠️ 第3步失败：未找到邮箱输入框: {e}")
            from services.utils import dump_page_state
            dump_page_state(page, "error_email_input_not_found")
            return False

        try:
            page.fill("input[type='email']", email)
            submit_btn = page.locator("button[type='submit']").first
            submit_btn.click()
            self._logger(f"✅ 第4步完成：已提交登录邮箱 {email}")
            from services.utils import dump_page_state
            dump_page_state(page, "after_submit_email")
            return True
        except Exception as e:
            self._logger(f"⚠️ 第4步失败：填写邮箱或提交失败: {e}")
            from services.utils import dump_page_state
            dump_page_state(page, "error_submit_email")
            return False

    def _wait_for_otp_stage(self, page):
        try:
            self._logger("ℹ️ 第5步：已提交邮箱，等待验证码输入框...")
            otp_kind, otp_input = self.wait_for_otp_input(page, timeout_ms=30000)

            if otp_kind == "page_changed":
                self._logger("⚠️ 第5步失败：等待验证码输入框时页面已跳转")
                from services.utils import dump_page_state
                dump_page_state(page, "error_otp_page_changed_before_input")
                return None, None

            if not otp_input:
                self._logger("⚠️ 第5步失败：未识别到验证码输入框")
                self.log_input_candidates(page, "OTP_INPUT_NOT_FOUND")
                from services.utils import dump_page_state
                dump_page_state(page, "error_otp_input_not_found")
                return None, None

            self._logger(f"✅ 第5步完成：验证码输入框已出现，识别类型: {otp_kind}")
            self.log_input_candidates(page, "OTP_INPUT_FOUND")
            from services.utils import dump_page_state
            dump_page_state(page, "otp_input_visible")
            return otp_kind, otp_input
        except Exception as e:
            self._logger(f"⚠️ 第5步失败：未出现验证码输入框: {e}")
            self.log_input_candidates(page, "OTP_INPUT_WAIT_EXCEPTION")
            from services.utils import dump_page_state
            dump_page_state(page, "error_otp_input_not_found")
            return None, None

    def _prompt_manual_otp(self) -> str:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        otp = simpledialog.askstring("验证码输入", "请输入邮箱中收到的验证码:", parent=root)
        root.destroy()
        if not otp:
            self._logger("❌ 第6步失败：用户未输入验证码")
            return ""
        self._logger("✅ 第6步完成：已接收手动输入验证码")
        return otp.strip()

    def _fill_manual_otp(self, page, otp: str) -> bool:
        try:
            self._logger("ℹ️ 第7步：正在填入验证码")
            otp_kind, otp_input = self.get_otp_input_locator(page)
            if not otp_input:
                self._logger("⚠️ 第7步失败：填写验证码前无法重新定位输入框")
                self.log_input_candidates(page, "OTP_INPUT_RELOCATE_FAILED")
                from services.utils import dump_page_state
                dump_page_state(page, "error_fill_otp_locator_missing")
                return False

            self.clear_and_type_otp(otp_input, otp, page, otp_kind)

            from services.utils import dump_page_state
            dump_page_state(page, "after_fill_otp")

            self._logger("✅ 第7步完成：验证码已填写，等待页面自动跳转...")
            sleep(5000)
            dump_page_state(page, "after_fill_otp_wait")
            return True
        except Exception as e:
            self._logger(f"⚠️ 第7步失败：填写验证码失败: {e}")
            self.log_input_candidates(page, "OTP_INPUT_FILL_EXCEPTION")
            from services.utils import dump_page_state
            dump_page_state(page, "error_fill_otp")
            return False

    def _finalize_login_after_otp(self, page, context, account, TARGET_URL) -> bool:
        result_type = self.wait_for_post_otp_result(page, timeout_ms=20000)
        self._logger(f"ℹ️ 第8步：OTP 提交后的页面类型: {result_type}")

        from services.utils import dump_page_state
        dump_page_state(page, "after_otp_result")

        if result_type in ("otp_error", "otp_still_here", "blocked"):
            self._logger("❌ 第8步失败：验证码登录未成功")
            return False

        if result_type == "company_select":
            self._logger("ℹ️ 第8步：进入公司选择页，继续处理")
            ok = self.handle_company_select(page)
            if not ok:
                return False
            try:
                try:
                    current_url = page.url or ""
                except Exception:
                    current_url = ""
                if not (self.is_chat_detail_page(page) and self.extract_session_id(current_url)):
                    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                else:
                    sid = self.extract_session_id(current_url)
                    self._logger(f"ℹ️ 保留聊天会话 {sid}，跳过跳转到 TARGET_URL")
                sleep(3000)
            except Exception:
                pass

        success = self.is_messenger_page(page)
        if success:
            from services.utils import save_login_state
            save_login_state(context, account.storage_path)
            self._logger("✅ 第8步完成：登录成功，已进入 messenger 页面")
        else:
            self._logger(f"❌ 第8步失败：登录后未进入 messenger 页面，当前 URL: {page.url}")
        return success

    def login_with_email_otp(self, page, context, account, TARGET_URL):
        self._logger(f"开始标准化登录流程: {account.email}")
        self._logger("登录流程规范: 打开登录页 -> 点击登录 -> 通过邮箱登录 -> 输入邮箱 -> 手动输入验证码 -> 校验是否进入 messenger")

        current_type = self.detect_page_type(page)
        self._logger(f"登录流程起始页面类型: {current_type}")

        if current_type == "messenger":
            self._logger("✅ 已在 messenger 页面，无需登录")
            return True

        if current_type == "company_select":
            self._logger("ℹ️ 起始即为公司选择页，先完成公司选择")
            ok = self.handle_company_select(page)
            if ok:
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
            return ok

        if current_type == "login":
            if not self._click_primary_login_button(page):
                return False
            current_type = self.detect_page_type(page)
            self._logger(f"第1步后页面类型: {current_type}")

        if current_type == "ozon_id_phone":
            if not self._click_email_login_button(page):
                return False
            current_type = self.detect_page_type(page)
            self._logger(f"第2步后页面类型: {current_type}")
        elif current_type not in ("otp",):
            self._logger("⚠️ 当前不是预期的 Ozon ID 手机号登录页")
            from services.utils import dump_page_state
            dump_page_state(page, "error_unexpected_login_stage")
            return False

        if self.detect_page_type(page) != "otp":
            if not self._submit_email_for_login(page, account.email):
                return False

        otp_kind, otp_input = self._wait_for_otp_stage(page)
        if not otp_input:
            return False

        otp = self._prompt_manual_otp()
        if not otp:
            return False

        if not self._fill_manual_otp(page, otp):
            return False

        return self._finalize_login_after_otp(page, context, account, TARGET_URL)

    def ensure_logged_in_and_ready(self, page, context, account, TARGET_URL):
        self._logger(f"🌐 登录后检查页面: {page.url}")
        sleep(3000)

        page_type = self.detect_page_type(page)
        self._logger(f"当前页面类型: {page_type}")

        if self.is_messenger_page(page):
            self._logger("✅ 已进入 messenger 页面")
            return

        if page_type in ("login", "ozon_id_phone", "otp", "company_select"):
            self._logger("ℹ️ 检测到登录态失效或登录流程页面，开始自动恢复登录")
            ok = self.login_with_email_otp(page, context, account, TARGET_URL)
            if not ok:
                raise RuntimeError("自动登录恢复失败")

            try:
                try:
                    current_url = page.url or ""
                except Exception:
                    current_url = ""
                if not (self.is_chat_detail_page(page) and self.extract_session_id(current_url)):
                    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                else:
                    sid = self.extract_session_id(current_url)
                    self._logger(f"ℹ️ 保留聊天会话 {sid}，跳过跳转到 TARGET_URL")
                sleep(3000)
            except Exception:
                pass

            if self.is_messenger_page(page):
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
                self._logger("✅ 自动登录恢复后已进入 messenger 页面")
                return

        if self.is_company_select_page(page):
            self._logger("ℹ️ 检测到公司选择页，准备选择公司并点击下一步")

            ok = self.handle_company_select(page)
            if not ok:
                raise RuntimeError("公司选择页处理失败")

            if self.wait_for_url_contains(page, "/app/messenger", timeout_ms=15000):
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
                self._logger("✅ 点击下一步后已进入 messenger 页面")
                return

            self._logger("⚠️ 点击下一步后未自动进入目标页，尝试手动打开 TARGET_URL")
            try:
                try:
                    current_url = page.url or ""
                except Exception:
                    current_url = ""
                if not (self.is_chat_detail_page(page) and self.extract_session_id(current_url)):
                    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                else:
                    sid = self.extract_session_id(current_url)
                    self._logger(f"ℹ️ 保留聊天会话 {sid}，跳过跳转到 TARGET_URL")
                sleep(3000)
            except Exception:
                pass

            if self.is_messenger_page(page):
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
                self._logger("✅ 手动跳转后已进入 messenger 页面")
                return

        if "/signin" in page.url or "/registration" in page.url:
            self._logger("⚠️ 当前仍在登录相关页面，尝试再次打开目标页")
            try:
                try:
                    current_url = page.url or ""
                except Exception:
                    current_url = ""
                if not (self.is_chat_detail_page(page) and self.extract_session_id(current_url)):
                    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                else:
                    sid = self.extract_session_id(current_url)
                    self._logger(f"ℹ️ 保留聊天会话 {sid}，跳过跳转到 TARGET_URL")
                sleep(3000)
            except Exception:
                pass

            if self.is_messenger_page(page):
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
                self._logger("✅ 重试后已进入 messenger 页面")
                return

            page_type = self.detect_page_type(page)
            if page_type in ("login", "ozon_id_phone", "otp", "company_select"):
                ok = self.login_with_email_otp(page, context, account, TARGET_URL)
                if not ok:
                    raise RuntimeError("再次尝试自动登录恢复失败")

                try:
                    try:
                        current_url = page.url or ""
                    except Exception:
                        current_url = ""
                    if not (self.is_chat_detail_page(page) and self.extract_session_id(current_url)):
                        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                    else:
                        sid = self.extract_session_id(current_url)
                        self._logger(f"ℹ️ 保留聊天会话 {sid}，跳过跳转到 TARGET_URL")
                    sleep(3000)
                except Exception:
                    pass
                if self.is_messenger_page(page):
                    from services.utils import save_login_state
                    save_login_state(context, account.storage_path)
                    self._logger("✅ 再次自动登录恢复后已进入 messenger 页面")
                    return

        if self.is_messenger_page(page):
            from services.utils import save_login_state
            save_login_state(context, account.storage_path)
            return

        raise RuntimeError(f"登录后未能进入目标页面，当前 URL: {page.url}")

    # 业务页面查找
    def find_sku_input(self, page, max_retries: int = 5):
        for attempt in range(1, max_retries + 1):
            locator = page.locator("textarea")
            try:
                count = locator.count()
                for i in range(count):
                    item = locator.nth(i)
                    if item.is_visible():
                        self._logger(f"✅ 找到 SKU 输入框 textarea，第 {i + 1} 个")
                        return item
            except Exception:
                pass

            try:
                locator = page.locator("input[type='text']")
                count = locator.count()
                for i in range(count):
                    item = locator.nth(i)
                    if item.is_visible():
                        self._logger(f"✅ 找到 SKU 输入框 input[type='text']，第 {i + 1} 个")
                        return item
            except Exception:
                pass

            self._logger(f"⏳ 查找 SKU 输入框，第 {attempt}/{max_retries} 次")
            sleep(1000)

        raise RuntimeError("未找到 SKU 输入框 textarea / input[type='text']")

    def set_input_value(self, locator, value: str):
        locator.click()
        sleep(200)
        locator.fill("")
        sleep(150)
        locator.fill(value)

    def press_enter(self, locator):
        locator.press("Enter")

    def wait_for_search_result(self, page, sku: str, timeout_ms: int = 10000):
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0:
                    return True
            except Exception:
                pass

            try:
                body_text = page.locator("body").inner_text(timeout=800)
                if sku in body_text:
                    return True
            except Exception:
                pass

            sleep(500)

        raise RuntimeError(f"等待 SKU 查询结果超时: {sku}")

    def find_file_input(self, page, max_retries: int = 5):
        for attempt in range(1, max_retries + 1):
            selectors = [
                "input[type='file'][accept*='image']",
                "input[type='file']",
            ]

            for selector in selectors:
                locator = page.locator(selector)
                try:
                    count = locator.count()
                    if count > 0:
                        for i in range(count - 1, -1, -1):
                            chosen = locator.nth(i)
                            try:
                                if chosen.is_visible():
                                    self._logger(f"✅ 找到上传控件：{selector}，第 {i + 1} 个")
                                    return chosen
                            except Exception:
                                pass

                        chosen = locator.nth(count - 1)
                        self._logger(f"✅ 找到上传控件：{selector}，第 {count} 个（不可见兜底）")
                        return chosen
                except Exception:
                    pass

            self._logger(f"⏳ 查找上传控件，第 {attempt}/{max_retries} 次")
            sleep(1000)

        raise RuntimeError("未找到图片上传 input[type='file']")

    def get_send_button_from_file_input(self, page, file_input):
        candidates = []

        try:
            locator = page.locator("input[type='file'] + div + button")
            if locator.count() > 0:
                candidates.append(locator.last)
        except Exception:
            pass

        try:
            locator = page.locator("input[type='file'] ~ button")
            if locator.count() > 0:
                candidates.append(locator.last)
        except Exception:
            pass

        try:
            locator = file_input.locator("xpath=following-sibling::button[1]")
            if locator.count() > 0:
                candidates.append(locator.first)
        except Exception:
            pass

        try:
            locator = file_input.locator("xpath=following-sibling::*//button[1]")
            if locator.count() > 0:
                candidates.append(locator.first)
        except Exception:
            pass

        try:
            for name in ["发送", "Отправить", "Send"]:
                locator = page.get_by_role("button", name=name)
                if locator.count() > 0:
                    candidates.append(locator.last)
        except Exception:
            pass

        for idx, btn in enumerate(candidates, 1):
            try:
                if btn.count() > 0 and btn.first.is_visible():
                    self._logger(f"✅ 发送按钮定位成功，候选 #{idx}")
                    return btn.first
            except Exception:
                pass

        try:
            locator = page.locator("xpath=(//input[@type='file']/following-sibling::button)[last()]")
            if locator.count() > 0 and locator.first.is_visible():
                self._logger("✅ 发送按钮定位成功，使用全局 XPath 兜底")
                return locator.first
        except Exception:
            pass

        raise RuntimeError("未找到发送按钮")

    def wait_for_send_button_enabled(self, page, file_input, timeout_ms: int = 15000):
        deadline = time.time() + timeout_ms / 1000
        last_state = ""

        while time.time() < deadline:
            try:
                btn = self.get_send_button_from_file_input(page, file_input)

                visible = btn.is_visible()
                disabled = btn.is_disabled()
                enabled = not disabled

                last_state = f"visible={visible}, disabled={disabled}, enabled={enabled}"
                self._logger(f"⏳ 发送按钮状态: {last_state}")

                if visible and enabled:
                    return btn
            except Exception as e:
                last_state = str(e)

            sleep(300)

        raise RuntimeError(f"等待发送按钮可用超时，最后状态: {last_state}")

    def click_send_button(self, page, file_input, timeout_ms: int = 15000):
        btn = self.wait_for_send_button_enabled(page, file_input, timeout_ms=timeout_ms)

        try:
            btn.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            btn.click(timeout=5000)
            self._logger("✅ 已点击发送按钮")
            return
        except Exception as e:
            self._logger(f"⚠️ 普通点击发送按钮失败：{e}")

        try:
            btn.click(force=True, timeout=5000)
            self._logger("✅ 已强制点击发送按钮")
            return
        except Exception as e:
            self._logger(f"⚠️ 强制点击发送按钮失败：{e}")

        raise RuntimeError("发送按钮点击失败")

    def wait_for_upload_finished(self, page, timeout_ms: int = 20000):
        success_texts = ["上传成功", "已上传", "上传完成", "успешно", "загружено", "готово", "success"]
        error_texts = ["上传失败", "失败", "error", "ошибка"]

        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                body_text = page.locator("body").inner_text(timeout=1000).lower()

                for t in error_texts:
                    if t.lower() in body_text:
                        raise RuntimeError("检测到上传失败提示")

                for t in success_texts:
                    if t.lower() in body_text:
                        return True
            except PlaywrightTimeoutError:
                pass

            sleep(800)

        return True

    def click_continue_complaint_button(self, page, timeout_ms: int = 10000) -> bool:
        """点击“投诉其他商品”按钮，准备下一个投诉"""
        from services.constants import RU_ANOTHER_PRODUCT_BUTTON

        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                locator = page.get_by_text(RU_ANOTHER_PRODUCT_BUTTON, exact=True)
                if locator.count() > 0 and locator.first.is_visible():
                    locator.first.click(timeout=5000)
                    self._logger(f"✅ 已点击按钮: {RU_ANOTHER_PRODUCT_BUTTON}")
                    sleep(800)
                    return True
            except Exception:
                pass

            try:
                locator = page.get_by_text(RU_ANOTHER_PRODUCT_BUTTON, exact=False)
                if locator.count() > 0 and locator.first.is_visible():
                    locator.first.click(timeout=5000)
                    self._logger(f"✅ 已点击按钮: {RU_ANOTHER_PRODUCT_BUTTON}")
                    sleep(800)
                    return True
            except Exception:
                pass

            try:
                locator = page.get_by_role("button", name=RU_ANOTHER_PRODUCT_BUTTON)
                if locator.count() > 0 and locator.first.is_visible():
                    locator.first.click(timeout=5000)
                    self._logger(f"✅ 已点击按钮(role): {RU_ANOTHER_PRODUCT_BUTTON}")
                    sleep(800)
                    return True
            except Exception:
                pass

            sleep(500)

        self._logger(f"⚠️ 未找到 {RU_ANOTHER_PRODUCT_BUTTON} 按钮")
        return False

    def click_menu_button(
        self,
        page,
        text: str,
        ru_text: Optional[str] = None,
        max_retries: int = 4,
        expected_next_texts: Optional[List[str]] = None,
        require_input: bool = False,
    ):
        if text:
            candidates.append(text)
        if ru_text:
            candidates.append(ru_text)

        if not candidates:
            raise RuntimeError("菜单文本为空，无法执行菜单点击")

        def _click_if_interactive(node, name: str, source: str) -> bool:
            try:
                if node.count() <= 0:
                    return False
                item = node.first
                if not item.is_visible():
                    return False
                try:
                    if item.is_disabled():
                        return False
                except Exception:
                    pass
                item.scroll_into_view_if_needed()
                sleep(300)
                item.click(timeout=5000)
                sleep(2500)
                self._logger(f"✅ 菜单点击成功({source}): {name}")
                return True
            except Exception:
                return False

        def _try_click_from_raw(raw, name: str, source: str) -> bool:
            if _click_if_interactive(raw, name, source):
                return True
            ancestors = [
                raw.locator("xpath=ancestor-or-self::*[@role='button'][1]"),
                raw.locator("xpath=ancestor-or-self::button[1]"),
                raw.locator("xpath=ancestor-or-self::a[1]"),
            ]
            for a in ancestors:
                if _click_if_interactive(a, name, f"{source}-ancestor"):
                    return True
            return False

        def _click_and_verify(raw, name: str, source: str) -> bool:
            if not _try_click_from_raw(raw, name, source):
                return False
            progressed = self.wait_for_menu_or_input_progress(
                page,
                expected_next_texts=expected_next_texts,
                timeout_ms=7000,
                require_input=require_input,
            )
            if progressed:
                return True
            self._logger(f"⚠️ 菜单点击后未观测到下一步按钮或输入框，准备重试: {name}")
            return False

        for attempt in range(1, max_retries + 1):
            self._logger(f"🎯 查找菜单：{text or ru_text}，第 {attempt}/{max_retries} 次")

            for name in candidates:
                try:
                    role_loc = page.get_by_role("button", name=name)
                    count = role_loc.count()
                    for i in range(count):
                        if _click_and_verify(role_loc.nth(i), name, "role"):
                            return True
                except Exception:
                    pass

            for name in candidates:
                try:
                    exact_loc = page.get_by_text(name, exact=True)
                    count = exact_loc.count()
                    for i in range(count):
                        if _click_and_verify(exact_loc.nth(i), name, "text-exact"):
                            return True
                except Exception:
                    pass

            for name in candidates:
                try:
                    fuzzy_loc = page.get_by_text(name, exact=False)
                    count = fuzzy_loc.count()
                    for i in range(count):
                        if _click_and_verify(fuzzy_loc.nth(i), name, "text-fuzzy"):
                            return True
                except Exception:
                    pass

            selectors = build_text_xpaths(text, ru_text)
            target = find_visible_by_xpaths(page, selectors, timeout_ms=3000)
            if target:
                try:
                    if _click_and_verify(target, text or ru_text, "xpath"):
                        return True
                except Exception:
                    pass

            try:
                page.mouse.wheel(0, 1000)
            except Exception:
                pass
            sleep(800)

        raise RuntimeError(f"找不到或无法点击菜单按钮: {text or ru_text}")
