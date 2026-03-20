#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的日志模块。

使用方式：
    from utils.logger import log
    log("消息内容")

在应用启动时，通过 set_logger 设置实际的日志处理函数（通常是 UI 的 append_log）：
    from utils.logger import set_logger
    set_logger(self.append_log)
"""

from typing import Callable

# 默认 logger：简单地 print（可被 set_logger 替换）
_LOGGER: Callable[[str], None] = print


def set_logger(logger_func: Callable[[str], None]) -> None:
    """
    设置全局日志回调。logger_func 应接受单个字符串参数。
    注意：不要在这里写文件或做 UI 更新，app.append_log 负责这些。
    """
    global _LOGGER
    if not callable(logger_func):
        raise TypeError("logger_func must be callable")
    _LOGGER = logger_func


def log(msg: str) -> None:
    """将 msg 转发给当前的 logger 回调。"""
    try:
        _LOGGER(msg)
    except Exception:
        # 避免 logger 回调抛异常中断业务逻辑；默认回退到 print
        try:
            print(msg)
        except Exception:
            pass


# 导出名称
__all__ = ["set_logger", "log"]
