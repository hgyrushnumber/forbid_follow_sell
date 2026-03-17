#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""客户端身份工具：优先环境变量，其次机器码。"""

import hashlib
import os
import platform
import socket
import uuid


def machine_code() -> str:
    """生成稳定机器码（基于网卡/系统信息做哈希脱敏）。"""
    raw = "|".join([
        str(uuid.getnode()),
        platform.system(),
        platform.machine(),
        socket.gethostname(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def resolve_client_id() -> str:
    """返回客户端ID：可由 CLIENT_ID 覆盖，默认主机名+机器码。"""
    override = os.environ.get("CLIENT_ID", "").strip()
    if override:
        return override
    return f"{socket.gethostname()}-{machine_code()}"
