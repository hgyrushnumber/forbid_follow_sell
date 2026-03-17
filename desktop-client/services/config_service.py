from __future__ import annotations

import json
import os
from typing import List, Optional

from models import AccountInfo


DEFAULT_CONFIG_FILE = "ozon_accounts_config.json"


class ConfigService:
    """
    账号配置读写服务。
    负责：
    - 从 JSON 文件加载账号列表
    - 将账号列表保存到 JSON 文件
    - 初始化默认配置文件
    """

    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE):
        self.config_file = config_file

    def exists(self) -> bool:
        return os.path.exists(self.config_file)

    def load_accounts(self) -> List[AccountInfo]:
        """
        从配置文件加载账号列表。
        如果文件不存在，返回空列表。
        如果文件损坏，返回空列表。
        """
        if not os.path.exists(self.config_file):
            return []

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                return []

            accounts: List[AccountInfo] = []
            for item in data:
                try:
                    account = AccountInfo.from_dict(item)
                    accounts.append(account)
                except Exception:
                    # 单条损坏不影响整体读取
                    continue

            return accounts

        except Exception:
            return []

    def save_accounts(self, accounts: List[AccountInfo]) -> None:
        """
        保存账号列表到配置文件。
        """
        data = [account.to_dict() for account in accounts]

        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def ensure_initialized(
        self,
        default_accounts: Optional[List[AccountInfo]] = None,
    ) -> List[AccountInfo]:
        """
        确保配置文件存在。
        - 如果已有配置，直接加载返回
        - 如果没有配置，则写入 default_accounts（如果提供）
        """
        accounts = self.load_accounts()
        if accounts:
            return accounts

        default_accounts = default_accounts or []
        self.save_accounts(default_accounts)
        return default_accounts

    def add_account(self, account: AccountInfo) -> List[AccountInfo]:
        """
        添加账号并保存。
        若邮箱已存在，则覆盖旧账号。
        """
        accounts = self.load_accounts()

        replaced = False
        for idx, item in enumerate(accounts):
            if item.email.strip().lower() == account.email.strip().lower():
                accounts[idx] = account
                replaced = True
                break

        if not replaced:
            accounts.append(account)

        self.save_accounts(accounts)
        return accounts

    def remove_account_by_email(self, email: str) -> List[AccountInfo]:
        """
        按邮箱删除账号并保存。
        """
        target = email.strip().lower()
        accounts = self.load_accounts()
        accounts = [acc for acc in accounts if acc.email.strip().lower() != target]
        self.save_accounts(accounts)
        return accounts

    def update_account(self, account: AccountInfo) -> List[AccountInfo]:
        """
        更新账号，本质上按邮箱覆盖。
        """
        return self.add_account(account)