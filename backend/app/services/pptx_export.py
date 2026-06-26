from __future__ import annotations

import json
import mimetypes
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from ..models import AgentSession, Project


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = PROJECT_ROOT / "scripts" / "ppt-runtime"
ENGINE_SCRIPT = RUNTIME_DIR / "generate-deck.mjs"
GENERATED_DIR = PROJECT_ROOT / "backend" / "generated"


def export_pptx(project: Project, session: AgentSession) -> Path:
    return ensure_export_artifact(project, session)["pptx_path"]


def ensure_export_artifact(project: Project, session: AgentSession) -> dict:
    cached = _find_cached_artifact(project, session)
    if cached:
        return cached

    artifacts = session.artifacts or {}
    outline = artifacts.get("outline", {}).get("slides", [])
    if not outline:
        raise RuntimeError("当前会话没有可导出的大纲")

    export_id = f"{project.id}-{uuid4().hex[:8]}"
    work_dir = GENERATED_DIR / export_id
    asset_dir = work_dir / "assets"
    qa_dir = work_dir / "qa"
    asset_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)
    output = GENERATED_DIR / f"{session.id}.pptx"

    citations = artifacts.get("verify", {}).get("citations", [])
    images = artifacts.get("images", {}).get("items", [])
    slides = []
    for index, slide in enumerate(outline):
        citation_indices = slide.get("citation_indices") or []
        slide_citations = [
            citations[citation_index - 1]
            for citation_index in citation_indices
            if isinstance(citation_index, int) and 0 < citation_index <= len(citations)
        ]
        if not slide_citations and citations:
            citation_count = min(3 if slide.get("layout") in {"evidence", "data"} else 1, len(citations))
            start = index % len(citations)
            slide_citations = [
                citations[(start + offset) % len(citations)]
                for offset in range(citation_count)
            ]
        layout = "cover" if index == 0 else slide.get("layout") or slide.get("type") or "content"
        uses_image = layout in {"cover", "image_split", "case", "content"}
        image = images[index % len(images)] if images and uses_image else None
        image_path = _download_image(image, asset_dir, index) if image else None
        slides.append({
            **slide,
            "number": slide.get("number", index + 1),
            "citations": slide_citations,
            "image_path": str(image_path) if image_path else None,
            "image_alt": (image or {}).get("description") or slide.get("image_query") or slide.get("title"),
            "image_content_type": mimetypes.guess_type(str(image_path))[0] if image_path else None,
            "image_source": (image or {}).get("source_url"),
            "image_author": (image or {}).get("author"),
        })

    payload = {
        "project": {
            "id": project.id,
            "title": project.title,
            "topic": project.topic,
            "slide_count": project.slide_count,
            "speaker_notes_enabled": project.speaker_notes_enabled,
        },
        "slides": slides,
        "citations": citations,
    }
    input_path = work_dir / "deck-input.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = subprocess.run(
        ["node", str(ENGINE_SCRIPT), str(input_path), str(output), str(qa_dir)],
        cwd=RUNTIME_DIR,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"专业 PPT 引擎导出失败：{details[:1200]}")
    if not output.exists() or output.stat().st_size < 10_000:
        raise RuntimeError("专业 PPT 引擎没有生成有效的 PPTX 文件")

    _validate_qa(qa_dir, len(slides))
    manifest = _artifact_manifest(project, session, output, work_dir, qa_dir, len(slides))
    (work_dir / "export-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return _hydrate_manifest(manifest)


def _find_cached_artifact(project: Project, session: AgentSession) -> dict | None:
    if not GENERATED_DIR.exists():
        return None
    manifests = sorted(
        GENERATED_DIR.glob(f"{project.id}-*/export-manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in manifests:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("session_id") != session.id:
            continue
        hydrated = _hydrate_manifest(manifest)
        pptx_path = hydrated["pptx_path"]
        qa_dir = hydrated["qa_dir"]
        if pptx_path.exists() and qa_dir.exists():
            try:
                _validate_qa(qa_dir, int(manifest.get("slide_count", 0)))
            except RuntimeError:
                continue
            return hydrated
    return None


def _artifact_manifest(project: Project, session: AgentSession, output: Path, work_dir: Path, qa_dir: Path, slide_count: int) -> dict:
    slides = [
        {
            "number": index,
            "thumbnail_path": str((qa_dir / f"slide-{index:02d}.png").resolve()),
            "layout_path": str((qa_dir / f"slide-{index:02d}.layout.json").resolve()),
        }
        for index in range(1, slide_count + 1)
    ]
    return {
        "project_id": project.id,
        "session_id": session.id,
        "project_title": project.title,
        "slide_count": slide_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pptx_path": str(output.resolve()),
        "work_dir": str(work_dir.resolve()),
        "qa_dir": str(qa_dir.resolve()),
        "montage_path": str((qa_dir / "montage.webp").resolve()),
        "slides": slides,
    }


def _hydrate_manifest(manifest: dict) -> dict:
    hydrated = dict(manifest)
    hydrated["pptx_path"] = Path(hydrated["pptx_path"])
    hydrated["work_dir"] = Path(hydrated["work_dir"])
    hydrated["qa_dir"] = Path(hydrated["qa_dir"])
    hydrated["montage_path"] = Path(hydrated["montage_path"])
    hydrated["slides"] = [
        {
            **slide,
            "thumbnail_path": Path(slide["thumbnail_path"]),
            "layout_path": Path(slide["layout_path"]),
        }
        for slide in hydrated.get("slides", [])
    ]
    return hydrated


def public_export_manifest(project: Project, session: AgentSession) -> dict:
    artifact = ensure_export_artifact(project, session)
    return {
        "session_id": artifact["session_id"],
        "project_id": artifact["project_id"],
        "project_title": artifact["project_title"],
        "slide_count": artifact["slide_count"],
        "created_at": artifact["created_at"],
        "pptx_url": f"/api/v1/sessions/{session.id}/export",
        "montage_url": f"/api/v1/sessions/{session.id}/export/montage",
        "slides": [
            {
                "number": slide["number"],
                "thumbnail_url": f"/api/v1/sessions/{session.id}/export/thumbnails/{slide['number']}",
            }
            for slide in artifact.get("slides", [])
        ],
    }


def export_thumbnail_path(project: Project, session: AgentSession, slide_number: int) -> Path:
    artifact = ensure_export_artifact(project, session)
    for slide in artifact.get("slides", []):
        if slide["number"] == slide_number and slide["thumbnail_path"].exists():
            return slide["thumbnail_path"]
    raise RuntimeError("缩略图不存在")


def export_montage_path(project: Project, session: AgentSession) -> Path:
    artifact = ensure_export_artifact(project, session)
    if artifact["montage_path"].exists():
        return artifact["montage_path"]
    raise RuntimeError("总览图不存在")


def _download_image(image: dict, asset_dir: Path, index: int) -> Path | None:
    url = image.get("url")
    if not url:
        return None
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        target = asset_dir / f"slide-{index + 1:02d}{extension}"
        target.write_bytes(response.content)
        return target
    except Exception:
        return None


def _validate_qa(qa_dir: Path, slide_count: int) -> None:
    pngs = sorted(qa_dir.glob("slide-*.png"))
    layouts = sorted(qa_dir.glob("slide-*.layout.json"))
    montage = qa_dir / "montage.webp"
    if len(pngs) != slide_count or len(layouts) != slide_count or not montage.exists():
        raise RuntimeError("PPT 渲染 QA 输出不完整")
    for png in pngs:
        if png.stat().st_size < 2_000:
            raise RuntimeError(f"幻灯片渲染结果异常：{png.name}")
