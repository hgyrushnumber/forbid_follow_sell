#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
import json
from task_center import create_default_center

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
# 维护活跃WebSocket连接（生产环境建议用Redis共享连接）
active_connections: Dict[str, WebSocket] = {}

# 兼容现有REST API接口
from pydantic import BaseModel

class CreateTaskRequest(BaseModel):
    sku_text: str = ""
    skus: List[str] = None
    user_id: str = "anonymous"

@app.post("/api/tasks")
async def create_task(request: CreateTaskRequest):
    try:
        result = CENTER.create_task(
            sku_text=request.sku_text,
            skus=request.skus,
            user_id=request.user_id
        )
        # 任务创建后主动推送给所有活跃客户端
        for client_id, websocket in list(active_connections.items()):
            try:
                await websocket.send_json({
                    "type": "task_created",
                    "task": result
                })
            except:
                # 推送失败则移除无效连接
                del active_connections[client_id]
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 其他现有REST接口复用原有逻辑
@app.get("/api/tasks")
async def list_tasks():
    return {"items": CENTER.list_tasks()}

@app.get("/api/clients/active")
async def list_active_clients():
    return {"items": CENTER.list_active_clients()}

# WebSocket端点（客户端连接）
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket

    # 客户端首次连接时自动注册
    accounts = []
    try:
        data = await websocket.receive_json()
        if data.get("type") == "register":
            accounts = data.get("accounts", [])
            CENTER.register_client(client_id, accounts)
    except:
        pass

    # 保持连接，不阻塞接收（使用定时器发送心跳检测）
    try:
        while True:
            await asyncio.sleep(30)  # 每30秒发送一次心跳检测
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        del active_connections[client_id]
        CENTER.set_client_offline(client_id)
    except Exception as e:
        print(f"WebSocket连接异常 {client_id}: {e}")
        del active_connections[client_id]
        CENTER.set_client_offline(client_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18080)