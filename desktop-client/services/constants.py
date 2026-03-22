#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
项目常量定义文件
用于避免循环导入问题，将所有共享常量集中管理
"""

# =========================
# 页面配置常量
# =========================

# 目标页面URL
TARGET_URL = "https://seller.ozon.ru/app/messenger?channel=SCRM"

# 仪表板页面URL
DASHBOARD_URL = "https://seller.ozon.ru/app/dashboard/main"

# 首页URL
HOME_URL = "https://seller.ozon.ru/"

# =========================
# 浏览器配置常量
# =========================

# 是否无头模式运行
HEADLESS = False

# 操作延迟（毫秒）
SLOW_MO = 200

# =========================
# 任务执行常量
# =========================

# 默认重试次数
DEFAULT_RETRY_COUNT = 3

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30

# 俄文 SKU 验证提示文本
RU_SKU_VERIFICATION_TEXT = "Скрыли товар"

# 俄文 SKU 验证等待超时时间（秒）
RU_SKU_VERIFICATION_TIMEOUT = 30

# 中文语言代码
ZH_LANGUAGE_CODE = "zh"

# 中文（简体 zh-Hans）语言代码
ZH_HANS_LANGUAGE_CODE = "zh-hans"

# =========================
# 页面操作常量
# =========================

# 菜单导航按钮配置
# 根据语言选择点击顺序：
# - ru: 点击全部4个按钮
# - zh-Hans: 只点击前3个按钮
MENU_BUTTONS = [
    {"text": "商品和价格", "ru_text": "Товары и Цены"},
    {"text": "质量监督", "ru_text": "Контроль качества"},
    {"text": "卖家使用我的品牌", "ru_text": "Нарушение правил площадки другим продавцом"},
    {"text": None, "ru_text": "Использование моего бренда"},  # 俄文第4步，中文跳过
]

# =========================
# 邮箱配置（保留但不再使用）
# =========================

# 默认邮箱地址（仅供参考）
DEFAULT_EMAIL = "xpw709@163.com"

# 邮箱授权码（仅供参考）
DEFAULT_EMAIL_PASS = "UE4NLW7W2X4NzunU"

# 默认IMAP服务器（仅供参考）
DEFAULT_IMAP_SERVER = "imap.163.com"
