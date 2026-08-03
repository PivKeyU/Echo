from __future__ import annotations

from pydantic import BaseModel


class InitDataPayload(BaseModel):
    init_data: str


class AdminBootstrapPayload(BaseModel):
    token: str | None = None
    init_data: str | None = None
