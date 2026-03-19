#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Tuple
from playwright.sync_api import Page
from services.page_service import PageService


class TabReuseChecker:
    """
    标签页复用检查器 - 用于判断标签页是否可以直接处理任务
    """
    def __init__(self, logger_func):
        self.page_service = PageService(logger_func)
        self._logger = logger_func

    def is_tab_eligible_for_reuse(self, page: Page, required_type: str = "any") -> Tuple[bool, str, Optional[str]]:
        """
        判断标签页是否可以直接复用

        Args:
            page: Playwright Page对象
            required_type: 需要的页面类型，可选值: "any", "support_v2", "chat_detail"

        Returns:
            (是否可复用, 原因描述, session_id)
        """
        try:
            url = page.url or ""
        except Exception:
            return False, "无法获取页面URL", None

        # 基本检查：页面是否处于活动状态
        if not self.page_service._is_page_alive(page):
            return False, "页面已关闭", None

        # 提取session_id
        session_id = self.page_service.extract_session_id_with_regex(url)

        # 检查页面类型
        if required_type == "support_v2":
            is_support = self.page_service.is_support_v2_page_with_regex(page)
            if not is_support:
                return False, "不是support_v2类型的页面", session_id
            return True, "可复用的support_v2页面", session_id

        elif required_type == "chat_detail":
            is_chat = self.page_service.is_chat_detail_page(page)
            if not is_chat:
                return False, "不是聊天详情页面", session_id
            return True, "可复用的聊天详情页面", session_id

        else:  # "any"
            # 检查是否是任何支持的页面类型
            if self.page_service.is_support_v2_page(page):
                return True, "可复用的support_v2页面", session_id
            elif self.page_service.is_chat_detail_page(page):
                return True, "可复用的聊天详情页面", session_id
            else:
                return False, "不是支持的页面类型", session_id

    def check_tab_eligibility_from_url(self, url: str, required_type: str = "any") -> Tuple[bool, str, Optional[str]]:
        """
        仅通过URL判断标签页是否可以复用

        Args:
            url: 页面URL
            required_type: 需要的页面类型

        Returns:
            (是否可复用, 原因描述, session_id)
        """
        # 基本检查：URL格式
        if not url or not url.startswith(("http://", "https://")):
            return False, "无效的URL格式", None

        # 提取session_id
        session_id = self.page_service.extract_session_id_with_regex(url)

        # 检查URL模式
        if required_type == "support_v2":
            import re
            has_messenger = "/app/messenger/" in url
            has_support_group = re.search(r'[?&]group=support_v2', url, re.IGNORECASE) is not None
            has_id = session_id is not None

            if not has_messenger:
                return False, "URL中不包含/app/messenger/", session_id
            elif not has_support_group:
                return False, "URL中不包含group=support_v2", session_id
            elif not has_id:
                return False, "URL中不包含id参数", session_id
            else:
                return True, "URL匹配support_v2页面模式", session_id

        elif required_type == "chat_detail":
            import re
            has_messenger = "/app/messenger/" in url
            has_id_or_group = (
                re.search(r'[?&]id=[^&]+', url) is not None or
                re.search(r'[?&]group=[^&]+', url) is not None
            )

            if not has_messenger:
                return False, "URL中不包含/app/messenger/", session_id
            elif not has_id_or_group:
                return False, "URL中不包含id或group参数", session_id
            else:
                return True, "URL匹配聊天详情页面模式", session_id

        else:  # "any"
            import re
            has_messenger = "/app/messenger/" in url
            has_valid_params = (
                re.search(r'[?&]id=[^&]+', url) is not None or
                re.search(r'[?&]group=[^&]+', url) is not None
            )

            if has_messenger and has_valid_params:
                return True, "URL匹配支持的页面模式", session_id
            else:
                return False, "URL不匹配任何支持的页面模式", session_id

    def describe_url_pattern(self, url: str) -> dict:
        """
        描述URL的模式信息，用于调试和日志记录
        """
        import re
        from urllib.parse import urlparse

        result = {
            "url": url,
            "has_messenger_path": "/app/messenger/" in url,
            "has_id_param": bool(re.search(r'[?&]id=[^&]+', url)),
            "has_group_param": bool(re.search(r'[?&]group=[^&]+', url)),
            "extracted_id": self.page_service.extract_session_id_with_regex(url),
            "extracted_group": None,
            "is_support_v2": False,
            "is_chat_detail": False,
        }

        # 提取group参数
        group_match = re.search(r'[?&]group=([^&]+)', url)
        if group_match:
            result["extracted_group"] = group_match.group(1).strip().lower()
            result["is_support_v2"] = result["extracted_group"] == "support_v2"

        result["is_chat_detail"] = result["has_messenger_path"] and (
            result["has_id_param"] or result["has_group_param"]
        )

        return result


def main():
    """
    测试TabReuseChecker
    """
    def dummy_logger(message):
        print(f"[LOG] {message}")

    checker = TabReuseChecker(dummy_logger)

    # 测试URL
    test_urls = [
        "https://seller.ozon.ru/app/messenger/?id=42c24dbf-26ed-401d-a41a-f1c7088c17bc&group=support_v2",
        "https://seller.ozon.ru/app/messenger/?id=123456",
        "https://seller.ozon.ru/app/messenger/?group=support_v2",
        "https://seller.ozon.ru/app/dashboard/main",
        "https://example.com",
    ]

    print("=== 测试标签页复用检查 ===\n")
    for url in test_urls:
        print(f"URL: {url}")

        # 检查URL模式
        pattern_info = checker.describe_url_pattern(url)
        print(f"  路径包含messenger: {pattern_info['has_messenger_path']}")
        print(f"  有id参数: {pattern_info['has_id_param']}")
        print(f"  有group参数: {pattern_info['has_group_param']}")
        print(f"  提取的ID: {pattern_info['extracted_id']}")
        print(f"  提取的group: {pattern_info['extracted_group']}")
        print(f"  是support_v2: {pattern_info['is_support_v2']}")
        print(f"  是聊天详情页: {pattern_info['is_chat_detail']}")

        # 检查复用资格
        eligible, reason, sid = checker.check_tab_eligibility_from_url(url, "any")
        print(f"  可复用: {eligible} - {reason}")
        print()


if __name__ == "__main__":
    main()
