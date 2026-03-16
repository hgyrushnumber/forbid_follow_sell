#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services import broadcast_clients_updated, dispatch_one_for_worker
from ..state import CENTER, observer_connections, worker_connections

router = APIRouter(tags=["ws"])


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    connected = True
    role = "observer"

    try:
        data = await websocket.receive_json()
        msg_type = data.get("type")
        if msg_type == "register":
            accounts = data.get("accounts", [])
            CENTER.register_client(client_id, accounts)
            worker_connections[client_id] = websocket
            role = "worker"
            await broadcast_clients_updated()
            await dispatch_one_for_worker(client_id)
        else:
            observer_connections[client_id] = websocket
            role = "observer"
    except Exception:
        observer_connections[client_id] = websocket
        role = "observer"

    async def send_heartbeat():
        while connected:
            try:
                await asyncio.sleep(30)
                if connected:
                    await websocket.send_json({"type": "heartbeat"})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(send_heartbeat())

    try:
        while connected:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                msg_type = data.get("type")

                if msg_type == "heartbeat" and role == "worker":
                    CENTER.heartbeat(client_id)
                    await dispatch_one_for_worker(client_id)
                elif msg_type == "register" and role == "observer":
                    accounts = data.get("accounts", [])
                    CENTER.register_client(client_id, accounts)
                    observer_connections.pop(client_id, None)
                    worker_connections[client_id] = websocket
                    role = "worker"
                    await broadcast_clients_updated()
                    await dispatch_one_for_worker(client_id)
                elif msg_type == "register_observer" and role == "worker":
                    worker_connections.pop(client_id, None)
                    observer_connections[client_id] = websocket
                    CENTER.set_client_offline(client_id)
                    role = "observer"
                    await broadcast_clients_updated()
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        connected = False
        heartbeat_task.cancel()
        worker_connections.pop(client_id, None)
        observer_connections.pop(client_id, None)
        if role == "worker":
            CENTER.set_client_offline(client_id)
            await broadcast_clients_updated()
