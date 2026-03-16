#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException

from ..models import CreateTaskRequest
from ..services import broadcast_observers, dispatch_pending_tasks, get_current_user
from ..state import CENTER, DAILY_TASK_LIMIT

router = APIRouter(tags=["tasks"])


@router.post("/tasks")
async def create_task(request: CreateTaskRequest, authorization: str | None = Header(default=None)):
    try:
        user = get_current_user(authorization)
        day_prefix = datetime.utcnow().strftime("%Y-%m-%d")
        today_task_count = CENTER.count_user_tasks_for_day(user["id"], day_prefix)
        if today_task_count >= DAILY_TASK_LIMIT:
            raise HTTPException(status_code=429, detail=f"今日任务已达上限（{DAILY_TASK_LIMIT}）")

        result = CENTER.create_task(sku_text=request.sku_text, skus=request.skus, user_id=user["id"])
        await broadcast_observers({"type": "task_created", "task": result})
        await dispatch_pending_tasks()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks")
async def list_tasks(authorization: str | None = Header(default=None)):
    user = get_current_user(authorization)
    return {"items": CENTER.list_tasks_for_user(user["id"])}
