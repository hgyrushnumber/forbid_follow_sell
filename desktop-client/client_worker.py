#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""客户端执行器：HTTP轮询接收任务/执行回传。"""

import json
import os
import socket
import time
import uuid
import urllib.request
import asyncio
from task_center import parse_sku_text
from ozon_core import run_task_with_skus

# 替换为后端HTTP地址（线上替换为服务器域名）
SERVER = os.environ.get("DISPATCH_SERVER", "http://127.0.0.1:18080")
CLIENT_ID = os.environ.get("CLIENT_ID", f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}")

def post(path: str, payload: dict):
    """HTTP POST请求工具"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def get(path: str):
    """HTTP GET请求工具"""
    req = urllib.request.Request(
        f"{SERVER}{path}",
        method="GET",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def load_accounts() -> list[str]:
    """加载可用账号列表"""
    BASE_DIR = os.path.dirname(__file__)
    config = os.path.join(BASE_DIR, "ozon_accounts_config.json")
    if not os.path.exists(config):
        return []
    with open(config, "r", encoding="utf-8") as f:
        data = json.load(f)
    accounts = []
    for item in data:
        if item.get("email") and item.get("imap_password"):
            accounts.append(item["email"])
    return list(dict.fromkeys(accounts))

def account_detail_map() -> dict:
    """加载账号详细配置"""
    BASE_DIR = os.path.dirname(__file__)
    config = os.path.join(BASE_DIR, "ozon_accounts_config.json")
    if not os.path.exists(config):
        return {}
    with open(config, "r", encoding="utf-8") as f:
        data = json.load(f)
    m = {}
    for item in data:
        if item.get("email") and item.get("imap_password"):
            m[item["email"]] = {
                "imap_password": item.get("imap_password", ""),
                "storage_path": item.get("storage_path"),
            }
    return m

async def process_task(task):
    """处理单个任务"""
    task_id = task["id"]
    account = task.get("assigned_account")
    detail_map = account_detail_map()

    if not account or account not in detail_map:
        post(f"/api/clients/{CLIENT_ID}/tasks/{task_id}/complete", {"success": False, "error": "本地无可用账号"})
        return

    skus = task.get("sku_payload") or []
    if isinstance(skus, str):
        skus = parse_sku_text(skus)

    # 标记任务开始执行
    post(f"/api/clients/{CLIENT_ID}/tasks/{task_id}/running", {})

    try:
        run_task_with_skus(
            email=account,
            skus=skus,
            image_path=os.path.join(os.path.dirname(__file__), "icon.png"),
            imap_password=detail_map[account]["imap_password"],
            storage_path=detail_map[account].get("storage_path"),
            headless=False,
        )
        post(f"/api/clients/{CLIENT_ID}/tasks/{task_id}/complete", {"success": True, "result": {"sku_count": len(skus)}})
    except Exception as exc:
        post(f"/api/clients/{CLIENT_ID}/tasks/{task_id}/complete", {"success": False, "error": str(exc)})

async def main():
    """主循环，处理注册、心跳和拉取任务"""
    # 加载账号
    accounts = load_accounts()

    while True:
        try:
            # 首先注册客户端
            try:
                print(f"尝试注册客户端 {CLIENT_ID}")
                post("/api/clients/register", {"client_id": CLIENT_ID, "accounts": accounts})
                print("客户端注册成功")
            except Exception as e:
                print(f"注册失败: {e}")
                await asyncio.sleep(5)
                continue

            # 进入轮询循环
            while True:
                try:
                    # 发送心跳
                    try:
                        post("/api/clients/heartbeat", {"client_id": CLIENT_ID, "accounts": accounts})
                    except Exception as e:
                        print(f"心跳失败: {e}")
                        break

                    # 拉取任务
                    try:
                        task = get(f"/api/clients/{CLIENT_ID}/task")
                        if task:
                            print(f"收到任务: {task['id']}")
                            await process_task(task)
                    except Exception as e:
                        print(f"拉取任务失败: {e}")

                    # 等待一段时间后再次轮询
                    await asyncio.sleep(10)
                except Exception as e:
                    print(f"轮询失败: {e}")
                    break

            # 如果出现问题，等待后重新注册
            await asyncio.sleep(5)
        except Exception as e:
            print(f"主循环错误: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
