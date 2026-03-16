#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse

from ..services import (
    cleanup_wechat_sessions,
    create_auth_response,
    fetch_wechat_profile,
    get_current_user,
)
from ..state import CENTER, DAILY_TASK_LIMIT, WECHAT_LOGIN_EXPIRES_SECONDS, wechat_login_sessions
from ..services import build_wechat_login_url

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register_user():
    raise HTTPException(status_code=403, detail="系统仅支持微信扫码登录，已禁用账号密码注册")


@router.post("/login")
async def login_user():
    raise HTTPException(status_code=403, detail="系统仅支持微信扫码登录，已禁用账号密码登录")


@router.get("/me")
async def auth_me(authorization: str | None = Header(default=None)):
    user = get_current_user(authorization)
    day_prefix = datetime.utcnow().strftime("%Y-%m-%d")
    today_task_count = CENTER.count_user_tasks_for_day(user["id"], day_prefix)
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "daily_limit": DAILY_TASK_LIMIT,
            "today_used": today_task_count,
            "today_remaining": max(DAILY_TASK_LIMIT - today_task_count, 0),
        }
    }


@router.get("/wechat/qr")
async def create_wechat_qr_session():
    cleanup_wechat_sessions()
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=WECHAT_LOGIN_EXPIRES_SECONDS)
    login_url = build_wechat_login_url(session_id)
    wechat_login_sessions[session_id] = {
        "status": "pending",
        "expires_at": expires_at,
        "wechat_openid": None,
        "nickname": None,
        "auth": None,
    }
    return {"session_id": session_id, "login_url": login_url, "expires_in": WECHAT_LOGIN_EXPIRES_SECONDS}


@router.get("/wechat/status/{session_id}")
async def get_wechat_qr_status(session_id: str):
    cleanup_wechat_sessions()
    session = wechat_login_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="扫码会话不存在或已过期")
    if session["status"] != "confirmed":
        return {"status": session["status"]}
    return {"status": "confirmed", **session["auth"]}


@router.get("/wechat/callback")
async def confirm_wechat_login(code: str = "", state: str = ""):
    if not code or not state:
        raise HTTPException(status_code=400, detail="缺少微信回调参数 code/state")

    cleanup_wechat_sessions()
    session = wechat_login_sessions.get(state)
    if not session:
        raise HTTPException(status_code=404, detail="扫码会话不存在或已过期")

    profile = fetch_wechat_profile(code)
    user = CENTER.create_or_update_wechat_user(profile["openid"], profile["nickname"])
    auth = create_auth_response(user)
    session["status"] = "confirmed"
    session["wechat_openid"] = profile["openid"]
    session["nickname"] = profile["nickname"]
    session["auth"] = auth

    success_redirect = os.getenv("WECHAT_LOGIN_SUCCESS_REDIRECT", "").strip()
    if success_redirect:
        separator = "&" if "?" in success_redirect else "?"
        html = (
            "<html><body><script>window.location.href='"
            + success_redirect
            + separator
            + "wechat_session_id="
            + state
            + "';</script>微信登录成功，正在跳转...</body></html>"
        )
        return HTMLResponse(content=html)

    return HTMLResponse(
        content=(
            "<html><body><script>"
            "if (window.opener) { window.opener.postMessage({type: 'wechat-login-complete', sessionId: '"
            + state
            + "'}, '*'); window.close(); }"
            "</script>微信登录成功，你可以关闭此页面并回到业务系统。</body></html>"
        )
    )
