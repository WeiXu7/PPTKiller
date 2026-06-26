import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import Project, User
from backend.app.security import hash_password, verify_password
from backend.app.services.harness import AgentHarness
from backend.app.services.pptx_export import export_pptx


class FakeServices:
    async def parse_assets(self, project):
        return {"count": 0, "files": [], "text_context": "", "note": "无上传资料"}

    async def research(self, project):
        return {
            "configured": True,
            "provider": "Fake",
            "found": 1,
            "peer_reviewed": 1,
            "web_results": [{"title": "Source", "url": "https://example.com"}],
            "citations": [{
                "title": "Verified Paper",
                "authors": ["A. Author"],
                "year": 2025,
                "venue": "Journal",
                "url": "https://doi.org/10.1000/test",
                "doi": "10.1000/test",
                "verified": True,
            }],
            "note": "真实服务测试替身",
        }

    async def verify(self, research):
        return {
            "verified": 1,
            "doi_checked": 1,
            "duplicates_removed": 0,
            "citations": research["citations"],
            "note": "已验证",
        }

    async def images(self, project):
        return {"configured": True, "provider": "Fake", "found": 1, "selected": 1, "items": [], "note": "已检索图片"}

    async def outline(self, project, brief, artifacts):
        slides = []
        for index in range(project.slide_count):
            slides.append({
                "number": index + 1,
                "title": project.title if index == 0 else f"第 {index + 1} 页",
                "type": "cover" if index == 0 else "content",
                "bullets": ["核心观点", "证据与建议"],
                "citation_indices": [1],
                "speaker_notes": "演讲稿",
            })
        return {"slides": slides, "target_count": project.slide_count, "generated_by": "fake", "note": "已生成"}

    async def slides(self, project, artifacts):
        return {"generated": len(artifacts["outline"]["slides"]), "slides": artifacts["outline"]["slides"], "note": "已准备"}

    async def notes(self, project, artifacts):
        return {"enabled": True, "coverage": project.slide_count, "items": [], "note": "已生成演讲稿"}


def test_password_roundtrip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_harness_stops_for_outline_approval():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="demo@example.com", name="Demo", password_hash="x")
    db.add(user)
    db.flush()
    project = Project(owner_id=user.id, title="AI 教育趋势", slide_count=15)
    db.add(project)
    db.commit()
    session = asyncio.run(AgentHarness(db, FakeServices()).start(project, {"audience": "教育工作者"}))
    assert session.status == "waiting_approval"
    assert session.events[-1].step_key == "outline"


def test_harness_completes_after_two_approvals(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="complete@example.com", name="Complete", password_hash="x")
    db.add(user)
    db.flush()
    project = Project(owner_id=user.id, title="完整闭环", topic="验证导出", slide_count=12)
    db.add(project)
    db.commit()
    harness = AgentHarness(db, FakeServices())
    session = asyncio.run(harness.start(project, {"audience": "管理者"}))
    session = asyncio.run(harness.approve(session, project, True, ""))
    assert session.status == "waiting_approval"
    assert session.current_step == 8
    session = asyncio.run(harness.approve(session, project, True, ""))
    assert session.status == "completed"
    assert project.status == "completed"
    monkeypatch.chdir(tmp_path)
    (tmp_path / "backend" / "generated").mkdir(parents=True)
    output = export_pptx(project, session)
    assert output.exists()
    assert output.stat().st_size > 0
