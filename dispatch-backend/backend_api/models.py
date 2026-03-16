#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional
from pydantic import BaseModel, Field


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
