from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import AgentEvent, AgentSession, Project
from .agent_services import AgentServices


@dataclass(frozen=True)
class HarnessStep:
    key: str
    title: str
    detail: str
    approval_gate: bool = False


STEPS = [
    HarnessStep("brief", "理解需求（理解简报）", "提取主题、受众、目标与交付约束"),
    HarnessStep("parse", "解析上传内容（文档与图片）", "抽取事实、表格、图片描述与可引用信息"),
    HarnessStep("research", "搜索网络与学术文献", "检索可追溯网页资料、论文与 DOI"),
    HarnessStep("verify", "验证与筛选引用来源", "去重并校验作者、年份、期刊与链接"),
    HarnessStep("images", "查找与筛选图片素材", "保留作者、来源和授权信息"),
    HarnessStep("outline", "构建演示大纲", "将论点、证据和图片映射到每一页", True),
    HarnessStep("slides", "生成演示文稿（幻灯片）", "按主题系统生成可编辑页面"),
    HarnessStep("notes", "生成演讲备注（可选）", "为每页生成讲述目标、转场与时间建议"),
    HarnessStep("review", "最终检查与一致性优化", "检查引用、叙事、版式与内容一致性", True),
    HarnessStep("export", "导出与交付", "输出可编辑 PPTX 与引用清单"),
]


class AgentHarness:
    def __init__(self, db: Session, services: AgentServices | None = None):
        self.db = db
        self.services = services or AgentServices(db)

    async def start(self, project: Project, brief: dict) -> AgentSession:
        session = AgentSession(project_id=project.id, status="running", current_step=0, brief=brief, artifacts={})
        self.db.add(session)
        project.status = "generating"
        self.db.flush()
        await self._run_until_gate(session, project)
        self.db.commit()
        self.db.refresh(session)
        return session

    async def approve(self, session: AgentSession, project: Project, approved: bool, feedback: str) -> AgentSession:
        if not approved:
            session.status = "revision_requested"
            self._event(session, "approval", "needs_revision", "人工审核：请求修改", feedback or "请调整当前结果")
        else:
            session.status = "running"
            session.current_step += 1
            self._event(session, "approval", "completed", "人工审核：已通过", feedback or "继续执行后续步骤")
            await self._run_until_gate(session, project)
        self.db.commit()
        self.db.refresh(session)
        return session

    async def revise(self, session: AgentSession, project: Project, instruction: str) -> AgentSession:
        self._event(session, "revision", "completed", "已接收修改指令", instruction)
        brief = dict(session.brief or {})
        brief["revision"] = instruction
        session.brief = brief
        # Rebuild from outline so model-backed content can incorporate the revision.
        session.current_step = next(index for index, step in enumerate(STEPS) if step.key == "outline")
        session.status = "running"
        await self._run_until_gate(session, project)
        self.db.commit()
        self.db.refresh(session)
        return session

    async def _run_until_gate(self, session: AgentSession, project: Project) -> None:
        while session.current_step < len(STEPS):
            step = STEPS[session.current_step]
            payload = await self._execute(step.key, project, session)
            event_status = "failed" if payload.get("fatal") else "completed"
            self._event(session, step.key, event_status, step.title, payload.get("note", step.detail), payload)
            artifacts = dict(session.artifacts or {})
            artifacts[step.key] = payload
            session.artifacts = artifacts
            if payload.get("fatal"):
                session.status = "failed"
                project.status = "failed"
                return
            if step.approval_gate:
                session.status = "waiting_approval"
                return
            session.current_step += 1
        session.status = "completed"
        project.status = "completed"

    async def _execute(self, key: str, project: Project, session: AgentSession) -> dict:
        artifacts = dict(session.artifacts or {})
        if key == "brief":
            return {
                "title": project.title,
                "topic": project.topic,
                "slide_count": project.slide_count,
                "speaker_notes_enabled": project.speaker_notes_enabled,
                "brief": session.brief,
                "note": "已确认项目主题、页数、受众与演讲稿要求。",
            }
        if key == "parse":
            return await self.services.parse_assets(project)
        if key == "research":
            return await self.services.research(project)
        if key == "verify":
            return await self.services.verify(artifacts.get("research", {}))
        if key == "images":
            return await self.services.images(project)
        if key == "outline":
            return await self.services.outline(project, session.brief or {}, artifacts)
        if key == "slides":
            return await self.services.slides(project, artifacts)
        if key == "notes":
            return await self.services.notes(project, artifacts)
        if key == "review":
            outline_count = len(artifacts.get("outline", {}).get("slides", []))
            citation_count = len(artifacts.get("verify", {}).get("citations", []))
            return {
                "slide_count": outline_count,
                "citation_count": citation_count,
                "checks": {
                    "slide_count_matches": outline_count == project.slide_count,
                    "citations_traceable": citation_count > 0,
                    "speaker_notes": not project.speaker_notes_enabled or artifacts.get("notes", {}).get("coverage", 0) > 0,
                },
                "note": f"已检查 {outline_count} 页内容和 {citation_count} 条引用，请进行最终人工审核。",
            }
        return {"ok": True, "note": "导出材料已准备完成。"}

    def _event(self, session, key, status, title, detail, payload=None):
        self.db.add(AgentEvent(
            session_id=session.id,
            step_key=key,
            status=status,
            title=title,
            detail=detail,
            payload=payload or {},
        ))
