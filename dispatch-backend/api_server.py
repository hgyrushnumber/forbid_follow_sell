#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote
from urllib.request import urlopen
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
from task_center import create_default_center
from pydantic import BaseModel, Field

app = FastAPI(title="Dispatch API")

# 配置CORS（生产环境替换为具体前端域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CENTER = create_default_center()
# worker websocket 连接
worker_connections: Dict[str, WebSocket] = {}
# observer websocket 连接（用于前端看板）
observer_connections: Dict[str, WebSocket] = {}
user_tokens: Dict[str, str] = {}

DAILY_TASK_LIMIT = 20
WECHAT_LOGIN_EXPIRES_SECONDS = 180
wechat_login_sessions: Dict[str, dict] = {}


class CreateTaskRequest(BaseModel):
    sku_text: str = ""
    skus: List[str] = None
    user_id: str = "anonymous"


class CompleteTaskRequest(BaseModel):
    success: bool
    result: dict = Field(default_factory=dict)
    error: str = ""

class RegisterClientRequest(BaseModel):
    client_id: str
    accounts: List[str] = []

class HeartbeatRequest(BaseModel):
    client_id: str
    accounts: Optional[List[str]] = None


class AuthRegisterRequest(BaseModel):
    username: str
    password: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _get_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少授权信息")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="授权格式错误")
    return authorization[7:].strip()


def _get_current_user(authorization: Optional[str]) -> dict:
    token = _get_token(authorization)
    user_id = user_tokens.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录态已失效，请重新登录")
    user = CENTER.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def _create_auth_response(user: dict) -> dict:
    token = secrets.token_urlsafe(32)
    user_tokens[token] = user["id"]
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "daily_limit": DAILY_TASK_LIMIT,
        },
    }


def _build_wechat_login_url(session_id: str) -> str:
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


def _wechat_fetch_json(url: str) -> dict:
    with urlopen(url, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("errcode"):
        raise HTTPException(status_code=502, detail=f"微信接口错误: {data.get('errmsg', 'unknown')}")
    return data


def _fetch_wechat_profile(code: str) -> Dict[str, str]:
    appid = os.getenv("WECHAT_OPEN_APPID", "").strip()
    secret = os.getenv("WECHAT_OPEN_APPSECRET", "").strip()
    if not appid or not secret:
        raise HTTPException(status_code=500, detail="微信开放平台参数未配置：WECHAT_OPEN_APPID / WECHAT_OPEN_APPSECRET")

    access_url = (
        "https://api.weixin.qq.com/sns/oauth2/access_token"
        f"?appid={quote(appid, safe='')}&secret={quote(secret, safe='')}&code={quote(code, safe='')}&grant_type=authorization_code"
    )
    token_data = _wechat_fetch_json(access_url)
    access_token = token_data.get("access_token")
    openid = token_data.get("openid")
    if not access_token or not openid:
        raise HTTPException(status_code=502, detail="微信返回数据不完整")

    userinfo_url = (
        "https://api.weixin.qq.com/sns/userinfo"
        f"?access_token={quote(access_token, safe='')}&openid={quote(openid, safe='')}&lang=zh_CN"
    )
    profile = _wechat_fetch_json(userinfo_url)
    nickname = profile.get("nickname") or f"wx_{openid[-6:]}"
    return {"openid": openid, "nickname": nickname}


def _cleanup_wechat_sessions():
    now = datetime.utcnow()
    expired = [sid for sid, session in wechat_login_sessions.items() if session["expires_at"] <= now]
    for sid in expired:
        wechat_login_sessions.pop(sid, None)


async def _send_json_safe(conn_map: Dict[str, WebSocket], conn_id: str, payload: dict):
    websocket = conn_map.get(conn_id)
    if not websocket:
        return False
    try:
        await websocket.send_json(payload)
        return True
    except Exception:
        conn_map.pop(conn_id, None)
        return False


async def _broadcast_observers(payload: dict):
    for observer_id in list(observer_connections.keys()):
        await _send_json_safe(observer_connections, observer_id, payload)


async def _broadcast_clients_updated():
    await _broadcast_observers({"type": "clients_updated", "items": CENTER.list_active_clients()})


async def _dispatch_one_for_worker(client_id: str):
    task = CENTER.pull_task_for_client(client_id)
    if not task:
        return None

    ok = await _send_json_safe(
        worker_connections,
        client_id,
        {
            "type": "task_assigned",
            "task": task,
        },
    )
    if not ok:
        return None

    await _broadcast_observers({"type": "task_updated", "task": task})
    return task


async def _dispatch_pending_tasks():
    if not worker_connections:
        return
    # 为每个在线 worker 尝试派发一个待处理任务
    for client_id in list(worker_connections.keys()):
        await _dispatch_one_for_worker(client_id)


@app.post("/api/tasks")
async def create_task(request: CreateTaskRequest, authorization: Optional[str] = Header(default=None)):
    try:
        user = _get_current_user(authorization)
        day_prefix = datetime.utcnow().strftime("%Y-%m-%d")
        today_task_count = CENTER.count_user_tasks_for_day(user["id"], day_prefix)
        if today_task_count >= DAILY_TASK_LIMIT:
            raise HTTPException(status_code=429, detail=f"今日任务已达上限（{DAILY_TASK_LIMIT}）")

        result = CENTER.create_task(
            sku_text=request.sku_text,
            skus=request.skus,
            user_id=user["id"],
        )
        # 通知观察端有新任务
        await _broadcast_observers({"type": "task_created", "task": result})
        # 任务创建后立即尝试按在线 worker 分派
        await _dispatch_pending_tasks()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tasks")
async def list_tasks(authorization: Optional[str] = Header(default=None)):
    user = _get_current_user(authorization)
    return {"items": CENTER.list_tasks_for_user(user["id"])}


@app.post("/api/auth/register")
async def register_user(request: AuthRegisterRequest):
    username = request.username.strip().lower()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="用户名长度至少3位")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少6位")

    try:
        user = CENTER.create_user(username=username, password_hash=_hash_password(request.password))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _create_auth_response(user)


@app.post("/api/auth/login")
async def login_user(request: AuthLoginRequest):
    username = request.username.strip().lower()
    user = CENTER.get_user_by_username(username)
    if not user or user["password_hash"] != _hash_password(request.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _create_auth_response(user)


@app.get("/api/auth/me")
async def auth_me(authorization: Optional[str] = Header(default=None)):
    user = _get_current_user(authorization)
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


@app.post("/api/auth/wechat/qr")
async def create_wechat_qr_session():
    _cleanup_wechat_sessions()
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=WECHAT_LOGIN_EXPIRES_SECONDS)
    login_url = _build_wechat_login_url(session_id)
    wechat_login_sessions[session_id] = {
        "status": "pending",
        "expires_at": expires_at,
        "wechat_openid": None,
        "nickname": None,
        "auth": None,
    }
    return {
        "session_id": session_id,
        "status": "pending",
        "expires_in": WECHAT_LOGIN_EXPIRES_SECONDS,
        "login_url": login_url,
        "qr_image_url": f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote(login_url, safe='')}",
    }


@app.get("/api/auth/wechat/status/{session_id}")
async def get_wechat_qr_status(session_id: str):
    _cleanup_wechat_sessions()
    session = wechat_login_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="扫码会话不存在或已过期")

    if session["status"] != "confirmed":
        return {"status": session["status"]}

    return {
        "status": "confirmed",
        **session["auth"],
    }


@app.get("/api/auth/wechat/callback")
async def confirm_wechat_login(code: str = "", state: str = ""):
    if not code or not state:
        raise HTTPException(status_code=400, detail="缺少微信回调参数 code/state")

    _cleanup_wechat_sessions()
    session = wechat_login_sessions.get(state)
    if not session:
        raise HTTPException(status_code=404, detail="扫码会话不存在或已过期")

    profile = _fetch_wechat_profile(code)
    user = CENTER.create_or_update_wechat_user(profile["openid"], profile["nickname"])
    auth = _create_auth_response(user)
    session["status"] = "confirmed"
    session["wechat_openid"] = profile["openid"]
    session["nickname"] = profile["nickname"]
    session["auth"] = auth

    success_redirect = os.getenv("WECHAT_LOGIN_SUCCESS_REDIRECT", "").strip()
    if success_redirect:
        html = (
            "<html><body><script>window.location.href='"
            + success_redirect
            + "';</script>微信登录成功，正在跳转...</body></html>"
        )
        return HTMLResponse(content=html)
    return HTMLResponse(content="<html><body>微信登录成功，你可以关闭此页面并回到业务系统。</body></html>")


@app.get("/api/clients/active")
async def list_active_clients():
    return {"items": CENTER.list_active_clients()}


@app.post("/api/clients/{client_id}/tasks/{task_id}/running")
async def mark_task_running(client_id: str, task_id: str):
    try:
        action = CENTER.mark_task_running(task_id, client_id)
        task = CENTER.get_task(task_id)
        if task and action.get("updated"):
            await _broadcast_observers({"type": "task_updated", "task": task})
        return {"ok": True, **action}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/clients/{client_id}/tasks/{task_id}/complete")
async def complete_task(client_id: str, task_id: str, request: CompleteTaskRequest):
    try:
        action = CENTER.complete_task(
            task_id=task_id,
            client_id=client_id,
            success=request.success,
            result=request.result,
            error=request.error,
        )
        task = CENTER.get_task(task_id)
        if task and action.get("updated"):
            await _broadcast_observers({"type": "task_updated", "task": task})
        # 完成后继续尝试分派下一批
        await _dispatch_pending_tasks()
        return {"ok": True, **action}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 客户端注册API
@app.post("/api/clients/register")
async def register_client(request: RegisterClientRequest):
    try:
        result = CENTER.register_client(request.client_id, request.accounts)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 客户端心跳API
@app.post("/api/clients/heartbeat")
async def client_heartbeat(request: HeartbeatRequest):
    try:
        result = CENTER.heartbeat(request.client_id, request.accounts)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 客户端拉取任务API
@app.get("/api/clients/{client_id}/task")
async def pull_task_for_client(client_id: str):
    try:
        task = CENTER.pull_task_for_client(client_id)
        return task
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 客户端离线API
@app.post("/api/clients/offline")
async def client_offline(request: dict):
    try:
        client_id = request.get("client_id")
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id不能为空")
        CENTER.set_client_offline(client_id)
        return {"status": "success", "message": f"客户端 {client_id} 已标记为离线"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    connected = True
    role = "observer"

    # 首包决定角色（worker 或 observer）
    try:
        data = await websocket.receive_json()
        msg_type = data.get("type")
        if msg_type == "register":
            accounts = data.get("accounts", [])
            CENTER.register_client(client_id, accounts)
            worker_connections[client_id] = websocket
            role = "worker"
            await _broadcast_clients_updated()
            await _dispatch_one_for_worker(client_id)
        else:
            observer_connections[client_id] = websocket
            role = "observer"
    except Exception as e:
        print(f"WebSocket注册失败 {client_id}: {e}")
        observer_connections[client_id] = websocket
        role = "observer"

    async def send_heartbeat():
        while connected:
            try:
                await asyncio.sleep(30)
                if connected:
                    await websocket.send_json({"type": "heartbeat"})
            except Exception as e:
                print(f"WebSocket心跳发送失败 {client_id}: {e}")
                break

    heartbeat_task = asyncio.create_task(send_heartbeat())

    try:
        while connected:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                msg_type = data.get("type")

                if msg_type == "heartbeat" and role == "worker":
                    CENTER.heartbeat(client_id)
                    await _dispatch_one_for_worker(client_id)
                elif msg_type == "register" and role == "observer":
                    accounts = data.get("accounts", [])
                    CENTER.register_client(client_id, accounts)
                    observer_connections.pop(client_id, None)
                    worker_connections[client_id] = websocket
                    role = "worker"
                    await _broadcast_clients_updated()
                    await _dispatch_one_for_worker(client_id)
                elif msg_type == "register_observer" and role == "worker":
                    worker_connections.pop(client_id, None)
                    observer_connections[client_id] = websocket
                    CENTER.set_client_offline(client_id)
                    role = "observer"
                    await _broadcast_clients_updated()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"WebSocket接收消息失败 {client_id}: {e}")
                break
    except WebSocketDisconnect:
        print(f"WebSocket连接断开 {client_id}")
    except Exception as e:
        print(f"WebSocket连接异常 {client_id}: {e}")
    finally:
        connected = False
        heartbeat_task.cancel()
        worker_connections.pop(client_id, None)
        observer_connections.pop(client_id, None)
        if role == "worker":
            CENTER.set_client_offline(client_id)
            await _broadcast_clients_updated()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18080)
