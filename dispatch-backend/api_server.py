#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
async def create_task(request: CreateTaskRequest):
    try:
        result = CENTER.create_task(
            sku_text=request.sku_text,
            skus=request.skus,
            user_id=request.user_id,
        )
        # 通知观察端有新任务
        await _broadcast_observers({"type": "task_created", "task": result})
        # 任务创建后立即尝试按在线 worker 分派
        await _dispatch_pending_tasks()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tasks")
async def list_tasks():
    return {"items": CENTER.list_tasks()}


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
