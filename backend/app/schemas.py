from __future__ import annotations

from datetime import datetime

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(ORMModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    topic: str = ""
    slide_count: int = Field(default=15, ge=3, le=80)
    speaker_notes_enabled: bool = True


class ProjectRead(ORMModel):
    id: str
    title: str
    topic: str
    status: str
    slide_count: int
    speaker_notes_enabled: bool
    created_at: datetime
    updated_at: datetime


class AssetRead(ORMModel):
    id: str
    project_id: str
    filename: str
    content_type: str
    description: str
    size_bytes: int
    created_at: datetime


class SessionStart(BaseModel):
    audience: str = "专业听众"
    tone: str = "专业、清晰"
    language: str = "中文"
    instructions: str = ""
    require_approval: bool = True
    presentation_mode: Literal["general", "radiology_case"] = "general"


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)


class ApprovalRequest(BaseModel):
    approved: bool
    feedback: str = ""


class SlideUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    layout: Literal["cover", "image_split", "statement", "two_column", "process", "architecture", "evidence", "summary", "content", "data", "case"]
    bullets: list[str] = Field(default_factory=list, max_length=8)
    key_message: str = Field(default="", max_length=500)
    speaker_notes: str = Field(default="", max_length=4000)


class SlideImageRequest(BaseModel):
    mode: Literal["auto", "none", "search", "upload"] = "auto"
    query: str = Field(default="", max_length=240)
    asset_id: str = ""
    image: dict = Field(default_factory=dict)


class EventRead(ORMModel):
    id: str
    step_key: str
    status: str
    title: str
    detail: str
    payload: dict
    created_at: datetime


class SessionRead(ORMModel):
    id: str
    project_id: str
    status: str
    current_step: int
    brief: dict
    artifacts: dict
    created_at: datetime
    updated_at: datetime
    events: list[EventRead] = []


class ExportSlideRead(BaseModel):
    number: int
    thumbnail_url: str


class ExportWarningRead(BaseModel):
    code: str
    severity: str
    message: str
    slide_number: Optional[int] = None


class ExportArtifactRead(BaseModel):
    session_id: str
    project_id: str
    project_title: str
    slide_count: int
    created_at: str
    file_status: str = "ready"
    pptx_size_bytes: int = 0
    design_template: str = "consulting-default"
    template_version: str = "1.0"
    renderer_version: str = ""
    pptx_url: str
    montage_url: str
    warnings: list[ExportWarningRead] = Field(default_factory=list)
    slides: list[ExportSlideRead]
