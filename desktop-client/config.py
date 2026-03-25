#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一执行配置模块。
支持本地/远程模式切换，控制是否启用分派服务器交互。
通过环境变量控制各行为，并提供查询接口。
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class ExecutionMode(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


@dataclass
class ExecutionConfig:
    execution_mode: ExecutionMode
    dispatch_enabled: bool
    dispatch_server: str

    @property
    def is_local(self) -> bool:
        return self.execution_mode == ExecutionMode.LOCAL

    @property
    def is_remote(self) -> bool:
        return self.execution_mode == ExecutionMode.REMOTE


_LOGGER: Callable[[str], None] = print
_config: Optional[ExecutionConfig] = None


def _resolve_mode_from_env() -> ExecutionMode:
    raw = os.environ.get("EXECUTION_MODE", "remote").strip().lower()
    try:
        return ExecutionMode(raw)
    except ValueError:
        # 暂宽容错误值，默认回退到 remote 以兼容现有部署
        return ExecutionMode.REMOTE


def _resolve_dispatch_enabled_from_env(mode: ExecutionMode) -> bool:
    # 若显式设置 DISPATCH_ENABLED，则优先
    if "DISPATCH_ENABLED" in os.environ:
        val = os.environ["DISPATCH_ENABLED"].strip().lower()
        return val in ("1", "true", "yes", "on")
    # 否则由 mode 派生：local -> false, remote -> true
    return mode == ExecutionMode.REMOTE


def _resolve_dispatch_server_from_env() -> str:
    return os.environ.get("DISPATCH_SERVER", "https://www.rus2cn.com")


def reload_config() -> ExecutionConfig:
    """强制重新解析配置（一般没必要，仅在动态修改 env 时用）"""
    global _config
    _config = _build_config()
    return _config


def _build_config() -> ExecutionConfig:
    mode = _resolve_mode_from_env()
    dispatch_enabled = _resolve_dispatch_enabled_from_env(mode)
    dispatch_server = _resolve_dispatch_server_from_env()
    return ExecutionConfig(
        execution_mode=mode,
        dispatch_enabled=dispatch_enabled,
        dispatch_server=dispatch_server,
    )


def get_config() -> ExecutionConfig:
    """获取当前配置，首次调用时解析 env 变量并缓存结果"""
    global _config
    if _config is None:
        _config = _build_config()
        _log_state()
    return _config


def is_dispatch_enabled() -> bool:
    """返回是否启用分派服务器同步/拉取任务"""
    return get_config().dispatch_enabled


def get_dispatch_server() -> str:
    """返回分派服务器基础 URL"""
    return get_config().dispatch_server


def get_execution_mode() -> ExecutionMode:
    """返回当前执行模式（LOCAL 或 REMOTE）"""
    return get_config().execution_mode


def set_logger(logger_func: Callable[[str], None]) -> None:
    """注入外部日志函数，便于统一日志输出"""
    global _LOGGER
    _LOGGER = logger_func


def _log_state() -> None:
    """首次解析配置时打印当前状态，方便排查模式设置"""
    if _config:
        mode_str = "local" if _config.is_local else "remote"
        dispatch_str = "enabled" if _config.dispatch_enabled else "disabled"
        _LOGGER(
            f"[config] execution_mode={mode_str}, dispatch={dispatch_str}, dispatch_server={_config.dispatch_server}"
        )


def reload_with_logger(logger_func: Callable[[str], None]) -> ExecutionConfig:
    """设置日志函数后重新解析配置并打印状态"""
    set_logger(logger_func)
    return reload_config()
