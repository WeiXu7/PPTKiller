from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
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
    ExportArtifactRead, RevisionRequest, SessionRead, SessionStart, SlideImageRequest, SlideUpdateRequest, UserCreate, UserRead,
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


def apply_slide_update(session: AgentSession, slide_number: int, payload: SlideUpdateRequest) -> AgentSession:
    artifacts = dict(session.artifacts or {})
    outline = dict(artifacts.get("outline") or {})
    slides = [dict(slide) for slide in outline.get("slides") or []]
    if not slides:
        raise HTTPException(status_code=409, detail="当前会话还没有可编辑的大纲")
    if slide_number < 1 or slide_number > len(slides):
        raise HTTPException(status_code=404, detail="幻灯片不存在")

    clean_bullets = [item.strip() for item in payload.bullets if item.strip()]
    index = slide_number - 1
    updated = {
        **slides[index],
        "number": slide_number,
        "title": payload.title.strip(),
        "layout": payload.layout,
        "bullets": clean_bullets,
        "key_message": payload.key_message.strip(),
        "speaker_notes": payload.speaker_notes.strip(),
    }
    if payload.layout in {"data", "case"}:
        updated["type"] = payload.layout
    elif payload.layout == "summary":
        updated["type"] = "summary"
    elif payload.layout == "cover":
        updated["type"] = "cover"
    else:
        updated["type"] = "content"

    slides[index] = updated
    outline["slides"] = slides
    outline["target_count"] = len(slides)
    outline["note"] = f"已保存第 {slide_number} 页编辑。"
    artifacts["outline"] = outline

    generated = dict(artifacts.get("slides") or {})
    if generated:
        generated["generated"] = len(slides)
        generated["slides"] = slides
        generated["editable"] = True
        generated["note"] = f"已同步 {len(slides)} 页可编辑幻灯片数据。"
        artifacts["slides"] = generated

    notes = dict(artifacts.get("notes") or {})
    if notes:
        enabled = bool(notes.get("enabled", True))
        items = [
            {"number": slide.get("number", item_index + 1), "text": slide.get("speaker_notes", "")}
            for item_index, slide in enumerate(slides)
            if enabled and slide.get("speaker_notes")
        ]
        notes["items"] = items
        notes["coverage"] = len(items) if enabled else 0
        notes["note"] = f"已同步 {len(items)} 页演讲稿。" if enabled else "用户选择跳过演讲稿。"
        artifacts["notes"] = notes

    artifacts["_export_revision"] = datetime.now(timezone.utc).isoformat()
    session.artifacts = artifacts
    return session


def _replace_slide(session: AgentSession, slide_number: int, updater) -> AgentSession:
    artifacts = dict(session.artifacts or {})
    outline = dict(artifacts.get("outline") or {})
    slides = [dict(slide) for slide in outline.get("slides") or []]
    if not slides:
        raise HTTPException(status_code=409, detail="当前会话还没有可编辑的大纲")
    if slide_number < 1 or slide_number > len(slides):
        raise HTTPException(status_code=404, detail="幻灯片不存在")

    index = slide_number - 1
    slides[index] = updater(slides[index])
    outline["slides"] = slides
    outline["target_count"] = len(slides)
    artifacts["outline"] = outline

    generated = dict(artifacts.get("slides") or {})
    if generated:
        generated["generated"] = len(slides)
        generated["slides"] = slides
        generated["editable"] = True
        artifacts["slides"] = generated

    artifacts["_export_revision"] = datetime.now(timezone.utc).isoformat()
    session.artifacts = artifacts
    return session


def apply_slide_image_assignment(session: AgentSession, slide_number: int, assignment: dict) -> AgentSession:
    mode = assignment.get("mode", "auto")
    if mode not in {"auto", "none", "search", "upload"}:
        raise HTTPException(status_code=422, detail="图片模式不支持")

    clean = {"mode": mode}
    if mode == "search":
        image = assignment.get("image") or assignment
        parsed_image_url = urlparse(image.get("url", ""))
        parsed_source_url = urlparse(image.get("source_url", ""))
        if parsed_image_url.scheme != "https" or not parsed_image_url.netloc.endswith("images.unsplash.com"):
            raise HTTPException(status_code=422, detail="请选择来自图片检索结果的图片")
        if parsed_source_url.netloc and not parsed_source_url.netloc.endswith("unsplash.com"):
            raise HTTPException(status_code=422, detail="图片来源链接不受支持")
        clean.update({
            "query": (assignment.get("query") or "").strip(),
            "url": image.get("url", ""),
            "thumb": image.get("thumb", ""),
            "description": image.get("description", ""),
            "author": image.get("author", ""),
            "source_url": image.get("source_url", ""),
        })
        if not clean["url"]:
            raise HTTPException(status_code=422, detail="请选择一张检索图片")
    elif mode == "upload":
        clean.update({
            "asset_id": assignment.get("asset_id", ""),
            "filename": assignment.get("filename", ""),
            "path": assignment.get("path", ""),
            "content_type": assignment.get("content_type", "application/octet-stream"),
            "author": assignment.get("author", "用户上传"),
        })
        if not clean["asset_id"] or not clean["path"]:
            raise HTTPException(status_code=422, detail="请选择一张上传图片")

    def updater(slide: dict) -> dict:
        updated = dict(slide)
        updated["image_assignment"] = clean
        return updated

    return _replace_slide(session, slide_number, updater)


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


@router.patch("/sessions/{session_id}/slides/{slide_number}", response_model=SessionRead)
def update_session_slide(
    session_id: str, slide_number: int, payload: SlideUpdateRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, _ = owned_session(db, user, session_id)
    apply_slide_update(session, slide_number, payload)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/sessions/{session_id}/slides/{slide_number}/image", response_model=SessionRead)
def update_session_slide_image(
    session_id: str, slide_number: int, payload: SlideImageRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    session, project = owned_session(db, user, session_id)
    assignment = payload.model_dump()
    if payload.mode == "upload":
        asset = db.scalar(
            select(ProjectAsset).where(ProjectAsset.id == payload.asset_id, ProjectAsset.project_id == project.id)
        )
        if not asset or not asset.content_type.startswith("image/"):
            raise HTTPException(status_code=404, detail="上传图片不存在")
        assignment.update({
            "filename": asset.filename,
            "path": asset.path,
            "content_type": asset.content_type,
            "author": "用户上传",
        })
    apply_slide_image_assignment(session, slide_number, assignment)
    db.commit()
    db.refresh(session)
    return session


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
