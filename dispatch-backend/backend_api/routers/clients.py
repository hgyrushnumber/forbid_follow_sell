#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter, HTTPException

from ..models import CompleteTaskRequest, HeartbeatRequest, RegisterClientRequest
from ..services import broadcast_clients_updated, broadcast_observers, dispatch_one_for_worker, dispatch_pending_tasks
from ..state import CENTER

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/active")
async def list_active_clients():
    return {"items": CENTER.list_active_clients()}


@router.post("/{client_id}/tasks/{task_id}/running")
async def mark_task_running(client_id: str, task_id: str):
    try:
        action = CENTER.mark_task_running(task_id, client_id)
        task = CENTER.get_task(task_id)
        if task and action.get("updated"):
            await broadcast_observers({"type": "task_updated", "task": task})
        return {"ok": True, **action}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{client_id}/tasks/{task_id}/complete")
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
            await broadcast_observers({"type": "task_updated", "task": task})
        await dispatch_pending_tasks()
        return {"ok": True, **action}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/register")
async def register_client(request: RegisterClientRequest):
    try:
        return CENTER.register_client(request.client_id, request.accounts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/heartbeat")
async def client_heartbeat(request: HeartbeatRequest):
    try:
        return CENTER.heartbeat(request.client_id, request.accounts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{client_id}/task")
async def pull_task_for_client(client_id: str):
    try:
        return CENTER.pull_task_for_client(client_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/offline")
async def client_offline(request: dict):
    try:
        client_id = request.get("client_id")
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id不能为空")
        CENTER.set_client_offline(client_id)
        await broadcast_clients_updated()
        return {"status": "success", "message": f"客户端 {client_id} 已标记为离线"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
