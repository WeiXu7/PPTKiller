from datetime import datetime

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


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)


class ApprovalRequest(BaseModel):
    approved: bool
    feedback: str = ""


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


class ExportArtifactRead(BaseModel):
    session_id: str
    project_id: str
    project_title: str
    slide_count: int
    created_at: str
    pptx_url: str
    montage_url: str
    slides: list[ExportSlideRead]
