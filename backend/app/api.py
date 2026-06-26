from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_db
from .dependencies import get_current_user
from .models import AgentSession, Project, ProjectAsset, User
from .schemas import (
    ApprovalRequest, AssetRead, AuthResponse, LoginRequest, ProjectCreate, ProjectRead,
    ExportArtifactRead, RevisionRequest, SessionRead, SessionStart, UserCreate, UserRead,
)
from .security import create_access_token, hash_password, verify_password
from .services.harness import AgentHarness
from .services.pptx_export import export_montage_path, export_pptx, export_thumbnail_path, public_export_manifest
from .services.providers import CrossrefLiteratureProvider, UnsplashImageProvider, provider_status

router = APIRouter()


def owned_project(db: Session, user: User, project_id: str) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def owned_session(db: Session, user: User, session_id: str) -> tuple[AgentSession, Project]:
    session = db.scalar(
        select(AgentSession)
        .options(selectinload(AgentSession.events), selectinload(AgentSession.project))
        .join(Project)
        .where(AgentSession.id == session_id, Project.owner_id == user.id)
    )
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session, session.project


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="邮箱已注册")
    user = User(email=payload.email.lower(), name=payload.name, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc())).all()


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = Project(owner_id=user.id, **payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}/sessions", response_model=list[SessionRead])
def project_sessions(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_project(db, user, project_id)
    return db.scalars(
        select(AgentSession)
        .options(selectinload(AgentSession.events))
        .where(AgentSession.project_id == project_id)
        .order_by(AgentSession.updated_at.desc())
    ).all()


@router.get("/sessions/{session_id}", response_model=SessionRead)
def get_session(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session, _ = owned_session(db, user, session_id)
    return session


@router.post("/projects/{project_id}/assets", response_model=AssetRead, status_code=201)
async def upload_asset(
    project_id: str,
    file: UploadFile = File(...),
    description: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = owned_project(db, user, project_id)
    safe_name = Path(file.filename or "upload.bin").name
    target_dir = Path("backend/data/uploads") / project.id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4()}-{safe_name}"
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="单个文件不能超过 50MB")
    target.write_bytes(content)
    asset = ProjectAsset(
        project_id=project.id,
        filename=safe_name,
        content_type=file.content_type or "application/octet-stream",
        path=str(target),
        description=description,
        size_bytes=len(content),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/projects/{project_id}/assets", response_model=list[AssetRead])
def list_assets(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_project(db, user, project_id)
    return db.scalars(
        select(ProjectAsset).where(ProjectAsset.project_id == project_id).order_by(ProjectAsset.created_at.desc())
    ).all()


@router.get("/research/literature")
async def search_literature(q: str, limit: int = 8, user: User = Depends(get_current_user)):
    results = await CrossrefLiteratureProvider().search(q, min(max(limit, 1), 20))
    return [citation.__dict__ for citation in results]


@router.get("/research/images")
async def search_images(q: str, limit: int = 8, user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.unsplash_access_key:
        raise HTTPException(status_code=503, detail="请配置 UNSPLASH_ACCESS_KEY 后使用图片检索")
    return await UnsplashImageProvider(settings.unsplash_access_key).search(q, min(max(limit, 1), 20))


@router.post("/projects/{project_id}/sessions", response_model=SessionRead, status_code=201)
async def start_session(
    project_id: str, payload: SessionStart,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return await AgentHarness(db).start(owned_project(db, user, project_id), payload.model_dump())


@router.post("/sessions/{session_id}/approve", response_model=SessionRead)
async def approve_session(
    session_id: str, payload: ApprovalRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    return await AgentHarness(db).approve(session, project, payload.approved, payload.feedback)


@router.post("/sessions/{session_id}/revise", response_model=SessionRead)
async def revise_session(
    session_id: str, payload: RevisionRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    return await AgentHarness(db).revise(session, project, payload.instruction)


@router.get("/sessions/{session_id}/export")
def export_session(
    session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="请先完成全部人工审批再导出")
    try:
        path = export_pptx(project, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return FileResponse(path, filename=f"{project.title}.pptx")


@router.get("/sessions/{session_id}/export/manifest", response_model=ExportArtifactRead)
def export_manifest(
    session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="请先完成全部人工审批再查看导出预览")
    try:
        return public_export_manifest(project, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/sessions/{session_id}/export/thumbnails/{slide_number}")
def export_thumbnail(
    session_id: str, slide_number: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="请先完成全部人工审批再查看缩略图")
    try:
        path = export_thumbnail_path(project, session, slide_number)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(path, media_type="image/png")


@router.get("/sessions/{session_id}/export/montage")
def export_montage(
    session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    if session.status != "completed":
        raise HTTPException(status_code=409, detail="请先完成全部人工审批再查看总览图")
    try:
        path = export_montage_path(project, session)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(path, media_type="image/webp")


@router.get("/providers")
def providers(user: User = Depends(get_current_user)):
    return provider_status(get_settings())
