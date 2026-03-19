#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from urllib.parse import urlparse
from typing import Optional


def extract_session_id_with_regex(url: str) -> Optional[str]:
    """
    使用正则表达式从URL中提取session_id参数
    匹配格式: id=42c24dbf-26ed-401d-a41a-f1c7088c17bc
    """
    if not url:
        return None

    # 正则表达式模式：匹配id=后面的UUID格式字符串
    pattern = r'[?&]id=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    match = re.search(pattern, url, re.IGNORECASE)

    if match:
        return match.group(1).strip()

    # 兼容非UUID格式的ID
    pattern_generic = r'[?&]id=([^&]+)'
    match_generic = re.search(pattern_generic, url)
    if match_generic:
        return match_generic.group(1).strip()

    return None


def is_support_v2_page_with_regex(url: str) -> bool:
    """
    使用正则表达式判断是否是support_v2页面
    匹配格式: https://seller.ozon.ru/app/messenger/?id=xxx&group=support_v2
    """
    if not url:
        return False

    # 检查URL中是否包含/app/messenger/
    if "/app/messenger/" not in url:
        return False

    # 检查是否有id参数和group=support_v2参数
    has_id = re.search(r'[?&]id=[^&]+', url) is not None
    has_support_group = re.search(r'[?&]group=support_v2', url, re.IGNORECASE) is not None

    return has_id and has_support_group


def is_chat_detail_page_with_regex(url: str) -> bool:
    """
    使用正则表达式判断是否是聊天详情页面
    """
    if not url:
        return False

    # 检查是否是messenger页面且包含id或group参数
    return "/app/messenger/" in url and (
        re.search(r'[?&]id=[^&]+', url) is not None or
        re.search(r'[?&]group=[^&]+', url) is not None
    )


def main():
    # 测试URL
    test_url = "https://seller.ozon.ru/app/messenger/?id=42c24dbf-26ed-401d-a41a-f1c7088c17bc&group=support_v2"

    print(f"测试URL: {test_url}")
    print(f"提取的session_id: {extract_session_id_with_regex(test_url)}")
    print(f"是否是support_v2页面: {is_support_v2_page_with_regex(test_url)}")
    print(f"是否是聊天详情页面: {is_chat_detail_page_with_regex(test_url)}")


if __name__ == "__main__":
    main()
