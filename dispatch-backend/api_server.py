#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

from backend_api.main import app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 18080))
    host = os.getenv("HOST", "127.0.0.1")

    print(f"🚀 启动Dispatch API服务器，监听地址: {host}:{port}")
    uvicorn.run("api_server:app", host=host, port=port, reload=False)
