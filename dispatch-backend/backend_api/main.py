#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.auth import router as auth_router
from .routers.clients import router as clients_router
from .routers.tasks import router as tasks_router
from .routers.ws import router as ws_router

load_dotenv()

app = FastAPI(title="Dispatch API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(ws_router)
