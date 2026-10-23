from __future__ import annotations

from fastapi import APIRouter

from docmind.api.routes import api_keys, auth, chat, documents, health, insights, search, workspaces

api_router = APIRouter()
for module in (health, auth, workspaces, documents, chat, search, insights, api_keys):
    api_router.include_router(module.router)
