#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import quote
from urllib.request import urlopen

from fastapi import HTTPException, WebSocket

from .state import (
    CENTER,
    DAILY_TASK_LIMIT,
    TOKEN_EXPIRES_SECONDS,
    observer_connections,
    user_tokens,
    wechat_login_sessions,
    worker_connections,
)


def get_daily_limit() -> int:
    return DAILY_TASK_LIMIT


def get_token_expire_seconds() -> int:
    return TOKEN_EXPIRES_SECONDS


def _get_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少授权信息")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="授权格式错误")
    return authorization[7:].strip()


def cleanup_user_tokens() -> None:
    now = datetime.utcnow()
    expired = [token for token, payload in user_tokens.items() if payload.get("expires_at") and payload["expires_at"] <= now]
    for token in expired:
        user_tokens.pop(token, None)


def get_current_user(authorization: Optional[str]) -> dict:
    cleanup_user_tokens()
    token = _get_token(authorization)
    token_payload = user_tokens.get(token)
    if not token_payload:
        raise HTTPException(status_code=401, detail="登录态已失效，请重新登录")
    user = CENTER.get_user_by_id(token_payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def create_auth_response(user: dict) -> dict:
    token = secrets.token_urlsafe(32)
    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(seconds=TOKEN_EXPIRES_SECONDS)
    user_tokens[token] = {"user_id": user["id"], "issued_at": issued_at, "expires_at": expires_at}
    return {
        "token": token,
        "expires_in": TOKEN_EXPIRES_SECONDS,
        "expires_at": expires_at.isoformat(timespec="seconds") + "Z",
        "user": {"id": user["id"], "username": user["username"], "daily_limit": DAILY_TASK_LIMIT},
    }


def build_wechat_login_url(session_id: str) -> str:
    appid = os.getenv("WECHAT_OPEN_APPID", "").strip()
    redirect_uri = os.getenv("WECHAT_OPEN_REDIRECT_URI", "").strip()
    if not appid or not redirect_uri:
        raise HTTPException(status_code=500, detail="微信开放平台参数未配置：WECHAT_OPEN_APPID / WECHAT_OPEN_REDIRECT_URI")
    return (
        "https://open.weixin.qq.com/connect/qrconnect"
        f"?appid={quote(appid, safe='')}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        "&response_type=code"
        "&scope=snsapi_login"
        f"&state={quote(session_id, safe='')}"
        "#wechat_redirect"
    )


def wechat_fetch_json(url: str) -> dict:
    with urlopen(url, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("errcode"):
        raise HTTPException(status_code=502, detail=f"微信接口错误: {data.get('errmsg', 'unknown')}")
    return data


def fetch_wechat_profile(code: str) -> Dict[str, str]:
    appid = os.getenv("WECHAT_OPEN_APPID", "").strip()
    secret = os.getenv("WECHAT_OPEN_APPSECRET", "").strip()
    if not appid or not secret:
        raise HTTPException(status_code=500, detail="微信开放平台参数未配置：WECHAT_OPEN_APPID / WECHAT_OPEN_APPSECRET")
    access_url = (
        "https://api.weixin.qq.com/sns/oauth2/access_token"
        f"?appid={quote(appid, safe='')}&secret={quote(secret, safe='')}&code={quote(code, safe='')}&grant_type=authorization_code"
    )
    token_data = wechat_fetch_json(access_url)
    access_token = token_data.get("access_token")
    openid = token_data.get("openid")
    if not access_token or not openid:
        raise HTTPException(status_code=502, detail="微信返回数据不完整")
    userinfo_url = (
        "https://api.weixin.qq.com/sns/userinfo"
        f"?access_token={quote(access_token, safe='')}&openid={quote(openid, safe='')}&lang=zh_CN"
    )
    profile = wechat_fetch_json(userinfo_url)
    nickname = profile.get("nickname") or f"wx_{openid[-6:]}"
    return {"openid": openid, "nickname": nickname}


def cleanup_wechat_sessions() -> None:
    now = datetime.utcnow()
    expired = [sid for sid, session in wechat_login_sessions.items() if session["expires_at"] <= now]
    for sid in expired:
        wechat_login_sessions.pop(sid, None)


async def send_json_safe(conn_map: Dict[str, WebSocket], conn_id: str, payload: dict):
    websocket = conn_map.get(conn_id)
    if not websocket:
        return False
    try:
        await websocket.send_json(payload)
        return True
    except Exception:
        conn_map.pop(conn_id, None)
        return False


async def broadcast_observers(payload: dict):
    for observer_id in list(observer_connections.keys()):
        await send_json_safe(observer_connections, observer_id, payload)


async def broadcast_clients_updated():
    await broadcast_observers({"type": "clients_updated", "items": CENTER.list_active_clients()})


async def dispatch_one_for_worker(client_id: str):
    task = CENTER.pull_task_for_client(client_id)
    if not task:
        return None
    ok = await send_json_safe(worker_connections, client_id, {"type": "task_assigned", "task": task})
    if not ok:
        return None
    await broadcast_observers({"type": "task_updated", "task": task})
    return task


async def dispatch_pending_tasks():
    if not worker_connections:
        return
    for client_id in list(worker_connections.keys()):
        await dispatch_one_for_worker(client_id)
