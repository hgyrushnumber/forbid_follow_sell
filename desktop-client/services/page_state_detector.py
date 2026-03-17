#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Tuple

from services.utils import safe_body_text


def _has_url(url: str, *keywords: str) -> bool:
    value = (url or "").lower()
    return any(k.lower() in value for k in keywords)


def _has_visible(page, selector: str) -> bool:
    try:
        loc = page.locator(selector)
        if loc.count() <= 0:
            return False
        return loc.first.is_visible()
    except Exception:
        return False


def _count_contains(body_text: str, keywords) -> int:
    return sum(1 for sign in keywords if sign in body_text)


def detect_page_state(page) -> Tuple[str, Dict[str, int]]:
    """
    统一页面状态识别：URL > 结构化元素 > 文本关键词。

    返回 (page_type, score_map)
    """
    try:
        url = page.url or ""
    except Exception:
        url = ""

    body_text = safe_body_text(page, timeout=3500)

    scores: Dict[str, int] = {
        "blocked": 0,
        "login": 0,
        "ozon_id_phone": 0,
        "otp": 0,
        "company_select": 0,
        "messenger": 0,
        "dashboard": 0,
    }

    # URL 优先
    if _has_url(url, "antibot", "challenge"):
        scores["blocked"] += 6
    if _has_url(url, "/app/messenger"):
        scores["messenger"] += 6
    if _has_url(url, "/app/dashboard", "dashboard/main"):
        scores["dashboard"] += 6
    if _has_url(url, "/otp", "id.ozon.ru/otp"):
        scores["otp"] += 4
    if _has_url(url, "/signin", "/registration", "login"):
        scores["login"] += 3

    # 结构化 selector
    if _has_visible(page, "input[name='otp']"):
        scores["otp"] += 5
    if _has_visible(page, "input[type='email']") and _has_visible(page, "button[type='submit']"):
        scores["login"] += 2
    if _has_visible(page, "[role='radio']") and (
        "Выберите компанию" in body_text or "请选择公司" in body_text
    ):
        scores["company_select"] += 5

    # 文本关键词
    blocked_signs = [
        "Доступ ограничен",
        "Обновить",
        "Служба поддержки",
        "Antibot Challenge Page",
        "访问受限",
    ]
    scores["blocked"] += _count_contains(body_text, blocked_signs)

    if (
        ("Введите номер телефона" in body_text and "Войти по почте" in body_text)
        or ("输入电话号码" in body_text and "使用邮箱登录" in body_text)
    ):
        scores["ozon_id_phone"] += 4

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
    scores["otp"] += max(_count_contains(body_text, otp_signs_ru), _count_contains(body_text, otp_signs_cn))

    if ("请选择公司" in body_text and "下一步" in body_text) or (
        "Выберите компанию" in body_text and "Далее" in body_text
    ):
        scores["company_select"] += 4

    login_signs = [
        "Вход и регистрация",
        "Войти",
        "Зарегистрироваться",
        "登录",
        "注册",
    ]
    scores["login"] += _count_contains(body_text, login_signs)

    messenger_markers = [
        "商品和价格",
        "质量监督",
        "卖家使用我的品牌",
        "Товары и цены",
        "Контроль качества",
    ]
    if _count_contains(body_text, messenger_markers) >= 2:
        scores["messenger"] += 3

    winner = max(scores, key=scores.get)
    if scores[winner] < 3:
        return "unknown", scores
    return winner, scores


def detect_page_type(page) -> str:
    page_type, _ = detect_page_state(page)
    return page_type


def is_messenger_page(page) -> bool:
    page_type, scores = detect_page_state(page)
    if page_type == "messenger":
        return True
    # 兜底：允许高置信 messenger 文本/URL命中
    return scores.get("messenger", 0) >= 4
