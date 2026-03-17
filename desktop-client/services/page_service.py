#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from typing import List, Optional
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from services.utils import safe_body_text, log, sleep, escape_xpath_text, build_text_xpaths, find_visible_by_xpaths


class PageService:
    def __init__(self, logger_func):
        self._logger = logger_func

    def detect_page_type(self, page):
        """
        返回:
        - blocked
        - login
        - ozon_id_phone
        - otp
        - company_select
        - messenger
        - dashboard
        - unknown
        """
        body_text = safe_body_text(page, timeout=5000)

        blocked_signs = [
            "Доступ ограничен",
            "Обновить",
            "Служба поддержки",
            "Antibot Challenge Page",
            "访问受限",
        ]
        if sum(sign in body_text for sign in blocked_signs) >= 2:
            return "blocked"

        if (
            ("Введите номер телефона" in body_text and "Войти по почте" in body_text)
            or ("输入电话号码" in body_text and "使用邮箱登录" in body_text)
        ):
            return "ozon_id_phone"

        otp_signs_ru = [
            "Введите код",
            "Отправили код на почту",
            "Получить новый код",
            "Не могу войти",
        ]
        otp_signs_cn = [
            "输入验证码",
            "验证码",
            "重新获取",
        ]
        if sum(sign in body_text for sign in otp_signs_ru) >= 2 or sum(sign in body_text for sign in otp_signs_cn) >= 2:
            return "otp"

        company_cn = "请选择公司" in body_text and "下一步" in body_text
        company_ru = "Выберите компанию" in body_text and "Далее" in body_text
        if company_cn or company_ru:
            return "company_select"

        try:
            url = page.url or ""
        except Exception:
            url = ""

        if "/app/messenger" in url:
            return "messenger"

        if "dashboard" in url or "/app/dashboard" in url:
            return "dashboard"

        login_signs = [
            "Вход и регистрация",
            "Войти",
            "Зарегистрироваться",
            "登录",
            "注册",
        ]
        if sum(sign in body_text for sign in login_signs) >= 2:
            return "login"

        return "unknown"

    def is_messenger_page(self, page) -> bool:
        if self.detect_page_type(page) == "messenger":
            return True

        body = safe_body_text(page, timeout=2000)
        markers = [
            "商品和价格",
            "质量监督",
            "卖家使用我的品牌",
            "Товары и цены",
            "Контроль качества",
        ]
        return any(m in body for m in markers)

    def is_company_select_page(self, page) -> bool:
        return self.detect_page_type(page) == "company_select"

    def is_chat_detail_page(self, page) -> bool:
        try:
            url = page.url or ""
        except Exception:
            url = ""
        return "/app/messenger/" in url and ("group=" in url or "id=" in url)

    def normalize_messenger_home(self, page, TARGET_URL):
        if self.is_chat_detail_page(page):
            self._logger("ℹ️ 当前处于具体会话页，准备回到 messenger 首页")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            sleep(4000)
            self._logger(f"✅ 已回到 messenger 首页: {page.url}")

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

    def login_with_email_otp(self, page, context, account, get_otp_from_email, TARGET_URL):
        self._logger(f"开始邮箱验证码登录流程: {account.email}")

        current_type = self.detect_page_type(page)
        self._logger(f"登录流程起始页面类型: {current_type}")

        if current_type == "messenger":
            self._logger("✅ 已在 messenger 页面，无需登录")
            return True

        if current_type == "company_select":
            ok = self.handle_company_select(page)
            if ok:
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
            return ok

        if current_type == "login":
            try:
                from services.utils import dump_page_state
                dump_page_state(page, "before_click_login")

                # 支持点击中文或俄文的登录按钮
                login_btn = None
                try:
                    # 先尝试查找俄文按钮 "Войти"
                    login_btn = page.get_by_text("Войти", exact=True).first
                    login_btn.wait_for(state="visible", timeout=5000)
                except:
                    # 如果俄文按钮未找到，尝试查找中文按钮 "登录"
                    login_btn = page.get_by_text("登录", exact=True).first
                    login_btn.wait_for(state="visible", timeout=5000)

                login_btn.click()
                page.wait_for_load_state("networkidle", timeout=20000)
                self._logger("✅ 已点击登录按钮")

                from services.utils import dump_page_state
                dump_page_state(page, "after_click_login")
            except Exception as e:
                self._logger(f"⚠️ 点击登录按钮失败: {e}")
                from services.utils import dump_page_state
                dump_page_state(page, "error_click_login")
                return False

        current_type = self.detect_page_type(page)
        self._logger(f"点击登录后页面类型: {current_type}")

        if current_type == "ozon_id_phone":
            try:
                from services.utils import dump_page_state
                dump_page_state(page, "before_click_email_login")

                # 支持点击中文或俄文的邮箱登录按钮
                email_login_btn = None
                try:
                    # 先尝试查找俄文按钮 "Войти по почте"
                    email_login_btn = page.get_by_text("Войти по почте", exact=True).first
                    email_login_btn.wait_for(state="visible", timeout=5000)
                except:
                    # 如果俄文按钮未找到，尝试查找中文按钮 "邮箱登录"
                    email_login_btn = page.get_by_text("使用邮箱登录", exact=True).first
                    email_login_btn.wait_for(state="visible", timeout=5000)

                email_login_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                self._logger("✅ 已点击“通过邮箱登录”")

                from services.utils import dump_page_state
                dump_page_state(page, "after_click_email_login")
            except Exception as e:
                self._logger(f"⚠️ 点击“通过邮箱登录”失败: {e}")
                from services.utils import dump_page_state
                dump_page_state(page, "error_click_email_login")
                return False
        elif current_type not in ("otp",):
            self._logger("⚠️ 当前不是预期的 Ozon ID 手机号登录页")
            from services.utils import dump_page_state
            dump_page_state(page, "error_unexpected_login_stage")
            return False

        try:
            if self.detect_page_type(page) != "otp":
                page.wait_for_selector("input[type='email']", timeout=20000)
                self._logger("✅ 邮箱输入框已出现")
                from services.utils import dump_page_state
                dump_page_state(page, "email_input_visible")
        except Exception as e:
            self._logger(f"⚠️ 未找到邮箱输入框: {e}")
            from services.utils import dump_page_state
            dump_page_state(page, "error_email_input_not_found")
            return False

        if self.detect_page_type(page) != "otp":
            baseline_mail_id = get_latest_ozon_mail_id()
            self._logger(f"提交前基线邮件 ID: {baseline_mail_id}")

            try:
                page.fill("input[type='email']", account.email)
                request_time = datetime.now(timezone.utc)

                submit_btn = page.locator("button[type='submit']").first
                submit_btn.click()
                self._logger("✅ 已提交邮箱")
                self._logger(f"验证码请求时间(UTC): {request_time.isoformat()}")

                from services.utils import dump_page_state
                dump_page_state(page, "after_submit_email")
            except Exception as e:
                self._logger(f"⚠️ 填写邮箱或提交失败: {e}")
                from services.utils import dump_page_state
                dump_page_state(page, "error_submit_email")
                return False
        else:
            baseline_mail_id = get_latest_ozon_mail_id()
            request_time = datetime.now(timezone.utc)

        try:
            self._logger("已提交邮箱，等待验证码输入框...")

            otp_kind, otp_input = self.wait_for_otp_input(page, timeout_ms=30000)

            if otp_kind == "page_changed":
                self._logger("⚠️ 等待验证码输入框时页面已跳转")
                from services.utils import dump_page_state
                dump_page_state(page, "error_otp_page_changed_before_input")
                return False

            if not otp_input:
                self._logger("⚠️ 未识别到验证码输入框")
                self.log_input_candidates(page, "OTP_INPUT_NOT_FOUND")
                from services.utils import dump_page_state
                dump_page_state(page, "error_otp_input_not_found")
                return False

            self._logger(f"✅ 验证码输入框已出现，识别类型: {otp_kind}")
            self.log_input_candidates(page, "OTP_INPUT_FOUND")
            from services.utils import dump_page_state
            dump_page_state(page, "otp_input_visible")

        except Exception as e:
            self._logger(f"⚠️ 未出现验证码输入框: {e}")
            self.log_input_candidates(page, "OTP_INPUT_WAIT_EXCEPTION")
            from services.utils import dump_page_state
            dump_page_state(page, "error_otp_input_not_found")
            return False

        # 根据账号配置决定是否使用IMAP获取验证码
        if hasattr(account, 'use_manual_login') and account.use_manual_login:
            self._logger("✅ 账号配置为手动输入验证码，跳过IMAP获取")
            otp_result = None
        else:
            self._logger("✅ 账号配置为使用IMAP获取验证码")
            otp_result = get_otp_from_email(
                request_time=request_time,
                min_mail_id=baseline_mail_id,
                max_wait_seconds=60,
                email_account=account.email,
                email_password=account.imap_password
            )

        if not otp_result:
            self._logger("❌ 验证码提取失败，尝试手动输入")
            from services.utils import dump_page_state
            dump_page_state(page, "error_otp_fetch_failed")

            # 尝试手动输入验证码
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口

            # 提示用户手动输入验证码
            otp = simpledialog.askstring("验证码输入", "请输入收到的验证码:", parent=root)

            if not otp:
                self._logger("❌ 用户未输入验证码")
                return False

            # 创建一个模拟的otp_result
            otp_result = {
                "otp": otp,
                "mail_id": None,
                "email_dt": None,
                "subject": "手动输入",
                "from_addr": "manual"
            }

        otp = otp_result["otp"]
        self._logger(f"本次使用的验证码: {otp}")
        self._logger(f"本次使用的邮件 ID: {otp_result['mail_id']}")
        self._logger(f"本次使用的邮件时间: {otp_result['email_dt']}")

        try:
            self._logger(f"正在填入验证码: {otp}")

            otp_kind, otp_input = self.get_otp_input_locator(page)
            if not otp_input:
                self._logger("⚠️ 填写验证码前无法重新定位输入框")
                self.log_input_candidates(page, "OTP_INPUT_RELOCATE_FAILED")
                from services.utils import dump_page_state
                dump_page_state(page, "error_fill_otp_locator_missing")
                return False

            self.clear_and_type_otp(otp_input, otp, page, otp_kind)

            try:
                current_value = otp_input.input_value()
                self._logger(f"当前输入框中的验证码值: {current_value}")
            except Exception:
                self._logger("⚠️ 输入后页面可能已跳转，无法再读取 otp input 值")

            from services.utils import dump_page_state
            dump_page_state(page, "after_fill_otp")

            self._logger("验证码已填写，等待页面自动跳转...")
            sleep(5000)
            from services.utils import dump_page_state
            dump_page_state(page, "after_fill_otp_wait")

        except Exception as e:
            self._logger(f"⚠️ 填写验证码失败: {e}")
            self.log_input_candidates(page, "OTP_INPUT_FILL_EXCEPTION")
            from services.utils import dump_page_state
            dump_page_state(page, "error_fill_otp")
            return False

        result_type = self.wait_for_post_otp_result(page, timeout_ms=20000)
        self._logger(f"OTP 提交后的页面类型: {result_type}")

        from services.utils import dump_page_state
        dump_page_state(page, "after_otp_result")

        if result_type == "otp_error":
            self._logger("❌ 页面明确提示验证码提交失败")
            return False

        if result_type == "otp_still_here":
            self._logger("⚠️ 输入验证码后仍停留在 OTP 页面")
            return False

        if result_type == "blocked":
            self._logger("❌ OTP 成功后被风控拦截")
            return False

        if result_type == "company_select":
            ok = self.handle_company_select(page)
            if not ok:
                return False

            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                sleep(3000)
            except Exception:
                pass

            from services.utils import save_login_state
            save_login_state(context, account.storage_path)
            return True

        if result_type in ("dashboard", "messenger"):
            from services.utils import save_login_state
            save_login_state(context, account.storage_path)
            return True

        self._logger("⚠️ 验证码提交后页面状态未知")
        return False

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
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
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
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            sleep(3000)

            if self.is_messenger_page(page):
                from services.utils import save_login_state
                save_login_state(context, account.storage_path)
                self._logger("✅ 手动跳转后已进入 messenger 页面")
                return

        if "/signin" in page.url or "/registration" in page.url:
            self._logger("⚠️ 当前仍在登录相关页面，尝试再次打开目标页")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            sleep(3000)

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

                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                sleep(3000)
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

    def click_menu_button(self, page, text: str, ru_text: Optional[str] = None, max_retries: int = 4):
        candidates = []
        if text:
            candidates.append(text)
        if ru_text:
            candidates.append(ru_text)

        if not candidates:
            raise RuntimeError("菜单文本为空")

        for attempt in range(1, max_retries + 1):
            self._logger(f"🎯 查找菜单：{text or ru_text}，第 {attempt}/{max_retries} 次")

            # 1. role button
            for name in candidates:
                try:
                    loc = page.get_by_role("button", name=name)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.scroll_into_view_if_needed()
                        sleep(300)
                        loc.first.click(timeout=5000)
                        sleep(2500)
                        return True
                except Exception:
                    pass

            # 2. 文本点击
            for name in candidates:
                try:
                    loc = page.get_by_text(name, exact=False)
                    count = loc.count()
                    for i in range(count):
                        item = loc.nth(i)
                        if item.is_visible():
                            item.scroll_into_view_if_needed()
                            sleep(300)
                            item.click(timeout=5000)
                            sleep(2500)
                            return True
                except Exception:
                    pass

            # 3. XPath
            selectors = build_text_xpaths(text, ru_text)
            target = find_visible_by_xpaths(page, selectors, timeout_ms=3000)
            if target:
                try:
                    target.scroll_into_view_if_needed()
                    sleep(300)
                    target.click(timeout=5000)
                    sleep(2500)
                    return True
                except Exception as e:
                    self._logger(f"⚠️ XPath 点击菜单失败：{text or ru_text}，原因：{e}")

            # 4. 尝试滚动
            try:
                page.mouse.wheel(0, 1000)
            except Exception:
                pass
            sleep(800)

        raise RuntimeError(f"找不到或无法点击菜单按钮: {text or ru_text}")