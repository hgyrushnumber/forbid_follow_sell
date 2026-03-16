#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from typing import Any, Dict
from fastapi import WebSocket
from task_center import create_default_center

CENTER = create_default_center()
worker_connections: Dict[str, WebSocket] = {}
observer_connections: Dict[str, WebSocket] = {}
TOKEN_EXPIRES_SECONDS = int(os.getenv("TOKEN_EXPIRES_SECONDS", 86400))
user_tokens: Dict[str, Dict[str, Any]] = {}
DAILY_TASK_LIMIT = int(os.getenv("DAILY_TASK_LIMIT", 20))
WECHAT_LOGIN_EXPIRES_SECONDS = int(os.getenv("WECHAT_LOGIN_EXPIRES_SECONDS", 180))
wechat_login_sessions: Dict[str, dict] = {}
