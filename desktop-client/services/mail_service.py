#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import imaplib
import os
from datetime import datetime
from typing import Optional, Dict
from imapclient import IMAPClient
from email_otp import get_imap_server


def get_latest_mail_id(email_addr: str, email_pass: str, imap_server: str) -> Dict:
    print("正在获取当前邮箱最新邮件 ID...")

    try:
        # 使用 with 自动管理连接和登出
        with IMAPClient(imap_server, ssl=True, port=993) as client:
            print(f"正在连接 IMAP 服务器: {imap_server}")

            # 关键步骤：网易163必须发送 ID 命令，否则 SELECT 会报 Unsafe Login
            client.id_({
                'name': 'Ozon Upload Tool',
                'version': '1.0',
                'vendor': 'CustomApp',
                'os': 'Windows',
            })
            print("已发送 ID 命令（绕过网易 Unsafe Login 保护）")

            # 登录
            client.login(email_addr, email_pass)
            print("✅ 邮箱登录成功")

            # 选择收件箱
            client.select_folder('INBOX')
            print("已打开 INBOX")

            # 获取所有邮件 ID
            messages = client.search(['ALL'])
            if not messages:
                return {
                    "success": True,
                    "message": "邮箱连接成功，但暂无邮件",
                    "latest_mail_id": None,
                }

            latest_id = max(messages)  # 最大的 ID 就是最新邮件
            print(f"✅ 当前最新邮件 ID: {latest_id}")

            return {
                "success": True,
                "message": "邮箱连接成功，能够正常读取邮件列表",
                "latest_mail_id": str(latest_id),
            }

    except Exception as e:
        error_str = str(e).lower()
        print(f"❌ 获取最新邮件 ID 失败: {e}")

        if "unsafe login" in error_str:
            msg = "网易邮箱拒绝访问（Unsafe Login），可能是 ID 命令未发送或风控触发"
        elif "login" in error_str or "auth" in error_str:
            msg = "认证失败，请检查邮箱 + 授权码是否正确"
        elif "connect" in error_str or "timeout" in error_str:
            msg = f"无法连接到 {imap_server}，请检查网络或服务器地址"
        else:
            msg = str(e)

        return {
            "success": False,
            "message": msg,
            "latest_mail_id": None,
        }