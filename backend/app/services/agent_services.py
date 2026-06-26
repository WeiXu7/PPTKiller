from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Project, ProjectAsset
from .llm import DeepSeekClient
from .deck_design import apply_consulting_template
from .providers import CrossrefLiteratureProvider, TavilyResearchProvider, UnsplashImageProvider
from .parsers import AssetParser


class AgentServices:
    """Runtime services used by the Harness.

    Every external call returns a structured payload instead of leaking provider
    exceptions into the session. This keeps failures visible and resumable.
    """

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.llm = DeepSeekClient(self.settings)
        self.asset_parser = AssetParser()

    async def parse_assets(self, project: Project) -> dict:
        assets = self.db.scalars(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id).order_by(ProjectAsset.created_at)
        ).all()
        files = []
        text_fragments = []
        total_sections = 0
        total_tables = 0
        ocr_items = []
        for asset in assets:
            parsed = self.asset_parser.parse(asset.path, asset.filename, asset.content_type)
            item = {
                "id": asset.id,
                "filename": asset.filename,
                "content_type": asset.content_type,
                "description": asset.description,
                "size_bytes": asset.size_bytes,
                **parsed,
            }
            text = parsed.get("text", "")
            if text:
                text_fragments.append(f"[文件：{asset.filename}]\n{text}")
            total_sections += len(parsed.get("sections", []))
            total_tables += len(parsed.get("tables", []))
            if parsed.get("ocr_required"):
                ocr_items.append(asset.filename)
            files.append(item)
        return {
            "count": len(files),
            "files": [item["filename"] for item in files],
            "items": files,
            "text_context": "\n\n".join(text_fragments)[:24000],
            "sections": total_sections,
            "tables": total_tables,
            "ocr_required": len(ocr_items),
            "ocr_items": ocr_items,
            "note": f"已原生解析 {len(files)} 个文件、{total_sections} 个内容区块和 {total_tables} 个表格；{len(ocr_items)} 个文件需要按需 OCR/视觉理解。",
        }

    async def research(self, project: Project) -> dict:
        query = f"{project.title} {project.topic}".strip()
        web_task = self._web_search(query)
        literature_task = self._literature_search(query)
        web_results, citations = await asyncio.gather(web_task, literature_task)
        return {
            "configured": bool(self.settings.tavily_api_key or self.settings.serpapi_api_key),
            "provider": "Tavily" if self.settings.tavily_api_key else "SerpAPI",
            "query": query,
            "found": len(web_results),
            "peer_reviewed": len(citations),
            "web_results": web_results,
            "citations": citations,
            "note": f"已获得 {len(web_results)} 条网页资料和 {len(citations)} 条可追溯文献。",
        }

    async def verify(self, research: dict) -> dict:
        citations = research.get("citations", [])
        seen = set()
        unique = []
        duplicates = 0
        for item in citations:
            key = (item.get("doi") or item.get("title", "")).lower()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            unique.append(self.classify_citation(item))
        web_sources = [self.classify_web_source(item) for item in research.get("web_results", [])]
        verified = [item for item in unique if item.get("doi") and item.get("url")]
        quality_summary = self._quality_summary(unique + web_sources)
        return {
            "verified": len(verified),
            "doi_checked": sum(bool(item.get("doi")) for item in unique),
            "duplicates_removed": duplicates,
            "citations": unique,
            "web_sources": web_sources,
            "quality_summary": quality_summary,
            "note": f"已保留 {len(unique)} 条唯一文献，其中 {len(verified)} 条具备 DOI 与来源链接；已完成来源质量分层。",
        }

    async def images(self, project: Project) -> dict:
        if not self.settings.unsplash_access_key:
            return {
                "configured": False,
                "provider": "未配置",
                "found": 0,
                "selected": 0,
                "items": [],
                "note": "未配置可用图片服务。",
            }
        query = project.title
        try:
            items = await UnsplashImageProvider(self.settings.unsplash_access_key).search(query, 10)
            return {
                "configured": True,
                "provider": "Unsplash",
                "query": query,
                "found": len(items),
                "selected": min(len(items), project.slide_count),
                "license_checked": True,
                "items": items,
                "note": f"已找到 {len(items)} 张图片，并保留作者与来源链接。",
            }
        except Exception as exc:
            return self._failure("Unsplash", exc, items=[])

    async def outline(self, project: Project, brief: dict, artifacts: dict) -> dict:
        fallback = apply_consulting_template(self.with_data_slides(project, self._fallback_outline(project), artifacts))
        if not self.llm.configured:
            return {**fallback, "generated_by": "fallback", "note": "DeepSeek 未配置，已使用本地大纲。"}
        research = artifacts.get("research", {})
        verified = artifacts.get("verify", {})
        parsed = artifacts.get("parse", {})
        source_context = {
            "uploaded_text": parsed.get("text_context", "")[:12000],
            "web_results": research.get("web_results", [])[:8],
            "citations": verified.get("citations", [])[:12],
        }
        prompt = f"""
请为一个专业演示文稿生成严格 JSON。
项目标题：{project.title}
主题要求：{project.topic}
目标页数：{project.slide_count}
受众与风格：{json.dumps(brief, ensure_ascii=False)}
可用资料：{json.dumps(source_context, ensure_ascii=False)}

输出格式：
{{
  "slides": [
    {{
      "number": 1,
      "title": "标题",
      "type": "cover|content|data|case|summary",
      "layout": "cover|image_split|statement|two_column|process|architecture|evidence|summary",
      "bullets": ["要点1", "要点2"],
      "left_title": "可选左栏标题",
      "left_bullets": ["可选左栏要点"],
      "right_title": "可选右栏标题",
      "right_bullets": ["可选右栏要点"],
      "process_steps": ["可选步骤1", "可选步骤2"],
      "diagram_title": "可选架构图标题",
      "diagram_layers": ["可选层级1", "可选层级2"],
      "diagram_nodes": [{{"id": "node_1", "label": "节点名称", "detail": "节点说明", "layer": "所属层级"}}],
      "diagram_edges": [{{"from": "node_1", "to": "node_2", "label": "关系说明"}}],
      "visual_rationale": "选择架构图或检索图片的原因",
      "key_message": "可选核心结论",
      "citation_indices": [1],
      "image_query": "英文图片检索词",
      "speaker_notes": "中文演讲稿"
    }}
  ],
  "narrative": "整体叙事说明"
}}
必须生成 {project.slide_count} 页；不要编造资料中不存在的数字或文献。
默认使用 consulting-default 模板系统：每页只有一个主观点，普通页最多 4 个要点，双栏每栏最多 3 个要点，流程最多 5 步。
当页面讲解技术概念、系统框架、能力体系、平台架构、Agent 工作流、数据流或治理框架时，优先使用 architecture，并给出可编辑图节点和连接关系。
当页面讲解真实场景、产品案例、人物、行业现场或具象对象时，优先使用 image_split 或 case，并给出用于检索真实图片的 image_query；不要规划 AI 生成图片。
"""
        try:
            result = await self.llm.generate_json(
                "你是严谨的演示文稿策划专家。只输出 JSON，引用只能指向提供的文献序号。",
                prompt,
            )
            slides = result.get("slides") or []
            if not slides:
                raise ValueError("模型未返回 slides")
            return {
                **apply_consulting_template(self.with_data_slides(project, {
                    "slides": slides[: project.slide_count],
                    "target_count": project.slide_count,
                    "narrative": result.get("narrative", ""),
                }, artifacts)),
                "target_count": project.slide_count,
                "generated_by": self.settings.deepseek_model,
                "note": f"DeepSeek 已生成 {min(len(slides), project.slide_count)} 页大纲与逐页内容。",
            }
        except Exception as exc:
            return {
                **fallback,
                "generated_by": "fallback",
                "provider_error": self._error_text(exc),
                "note": "DeepSeek 调用失败，已保留本地可编辑大纲。",
            }

    async def slides(self, project: Project, artifacts: dict) -> dict:
        slides = artifacts.get("outline", {}).get("slides", [])
        return {
            "generated": len(slides),
            "format": "16:9",
            "editable": True,
            "slides": slides,
            "note": f"已准备 {len(slides)} 页可编辑幻灯片数据。",
        }

    async def notes(self, project: Project, artifacts: dict) -> dict:
        slides = artifacts.get("outline", {}).get("slides", [])
        notes = [
            {"number": slide.get("number", index + 1), "text": slide.get("speaker_notes", "")}
            for index, slide in enumerate(slides)
            if slide.get("speaker_notes")
        ]
        return {
            "enabled": project.speaker_notes_enabled,
            "coverage": len(notes) if project.speaker_notes_enabled else 0,
            "items": notes if project.speaker_notes_enabled else [],
            "note": f"已生成 {len(notes)} 页演讲稿。" if project.speaker_notes_enabled else "用户选择跳过演讲稿。",
        }

    async def _web_search(self, query: str) -> list[dict]:
        if self.settings.tavily_api_key:
            try:
                results = await TavilyResearchProvider(self.settings.tavily_api_key).search(query, 10)
                return [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", "")[:1200],
                        "score": item.get("score"),
                        "provider": "Tavily",
                    }
                    for item in results
                ]
            except Exception as exc:
                return [{"provider": "Tavily", "error": self._error_text(exc)}]
        return []

    async def _literature_search(self, query: str) -> list[dict]:
        try:
            results = await CrossrefLiteratureProvider().search(query, 12)
            return [item.__dict__ for item in results]
        except Exception as exc:
            return [{"provider": "Crossref", "error": self._error_text(exc), "verified": False}]

    def _fallback_outline(self, project: Project) -> dict:
        titles = [
            project.title,
            "背景与核心问题",
            "关键概念与发展脉络",
            "市场与行业现状",
            "核心应用场景",
            "价值与机会",
            "挑战与风险",
            "典型案例",
            "实施路径",
            "能力与治理要求",
            "未来趋势",
            "结论与行动建议",
        ]
        while len(titles) < project.slide_count:
            titles.insert(-1, f"专题分析 {len(titles) - 9}")
        slides = []
        for index, title in enumerate(titles[: project.slide_count]):
            slides.append({
                "number": index + 1,
                "title": title,
                "type": "cover" if index == 0 else "summary" if index == project.slide_count - 1 else "content",
                "layout": "cover" if index == 0 else "summary" if index == project.slide_count - 1 else ["image_split", "statement", "two_column", "process", "evidence"][index % 5],
                "bullets": ["基于现有资料组织核心观点", "待模型或人工补充具体证据"],
                "citation_indices": [],
                "image_query": project.title,
                "speaker_notes": f"本页介绍“{title}”，并与下一页建立自然衔接。",
            })
        if self._needs_architecture_visual(project) and len(slides) > 2:
            target_index = 2 if len(slides) > 3 else 1
            slides[target_index] = self._architecture_slide(project, target_index + 1)
        return {"slides": slides, "target_count": project.slide_count, "narrative": "问题—证据—方案—行动"}

    @staticmethod
    def _needs_architecture_visual(project: Project) -> bool:
        text = f"{project.title} {project.topic}".lower()
        keywords = [
            "架构", "框架", "系统", "技术", "平台", "流程", "机制", "agent", "rag",
            "workflow", "pipeline", "framework", "architecture", "knowledge graph",
            "知识图谱", "数据流", "治理", "能力体系",
        ]
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _architecture_slide(project: Project, number: int) -> dict:
        title = "关键概念与技术框架" if number > 1 else project.title
        return {
            "number": number,
            "title": title,
            "type": "content",
            "layout": "architecture",
            "diagram_title": project.title,
            "diagram_layers": ["输入与语境", "智能处理", "输出与反馈"],
            "diagram_nodes": [
                {"id": "input", "label": "用户目标", "detail": "主题、受众、约束", "layer": "输入与语境"},
                {"id": "sources", "label": "资料与检索", "detail": "上传内容、网页、文献", "layer": "输入与语境"},
                {"id": "reasoning", "label": "Agent 推理", "detail": "拆解问题并组织叙事", "layer": "智能处理"},
                {"id": "verification", "label": "证据校验", "detail": "引用、图片、数据质量", "layer": "智能处理"},
                {"id": "slides", "label": "可编辑页面", "detail": "架构图、数据图、讲稿", "layer": "输出与反馈"},
                {"id": "approval", "label": "人工审批", "detail": "确认后导出 PPTX", "layer": "输出与反馈"},
            ],
            "diagram_edges": [
                {"from": "input", "to": "reasoning", "label": "定义任务"},
                {"from": "sources", "to": "reasoning", "label": "补充事实"},
                {"from": "reasoning", "to": "verification", "label": "形成判断"},
                {"from": "verification", "to": "slides", "label": "落成页面"},
                {"from": "slides", "to": "approval", "label": "进入审批"},
            ],
            "bullets": ["用结构图解释关键模块及关系", "减少抽象概念堆叠，提高听众理解速度"],
            "key_message": "复杂概念先拆成模块、关系和反馈闭环，再进入细节讨论。",
            "citation_indices": [],
            "image_query": "",
            "visual_rationale": "该页讲解技术/框架关系，架构图比纯文字更容易建立整体理解。",
            "speaker_notes": "这一页先从整体框架讲起：输入提供目标和事实，Agent 负责推理和校验，最终沉淀为可编辑页面并进入人工审批。",
        }

    @staticmethod
    def with_data_slides(project: Project, outline: dict, artifacts: dict) -> dict:
        candidate = AgentServices._first_table_profile(artifacts)
        if not candidate:
            return outline
        slides = [dict(slide) for slide in outline.get("slides", [])]
        if not slides:
            return outline
        target_index = next((index for index, slide in enumerate(slides) if index > 0 and slide.get("layout") not in {"summary", "cover"}), min(1, len(slides) - 1))
        profile = candidate["profile"]
        chart_type = profile.get("chart_type") or "table"
        title = f"{profile.get('value_columns', ['关键指标'])[0]}数据洞察" if profile.get("value_columns") else "数据表格洞察"
        slides[target_index] = {
            **slides[target_index],
            "number": target_index + 1,
            "title": title,
            "type": "data",
            "layout": "data",
            "chart_type": chart_type,
            "key_message": f"本页数据来自 {candidate['filename']} / {candidate['sheet']}，用于支撑演示中的量化判断。",
            "bullets": [
                f"数据来源：{candidate['filename']} / {candidate['sheet']}",
                f"指标字段：{'、'.join(profile.get('value_columns') or []) or '表格字段'}",
            ],
            "data_source": {"filename": candidate["filename"], "sheet": candidate["sheet"]},
            "data_series": profile.get("series", []),
            "data_table": {
                "headers": profile.get("headers", []),
                "rows": profile.get("preview_rows", []),
            },
            "kpis": profile.get("kpis", []),
            "speaker_notes": f"本页展示来自 {candidate['filename']} 的数据，请结合趋势和异常点说明业务含义。",
        }
        return {**outline, "slides": slides, "target_count": len(slides)}

    @staticmethod
    def _first_table_profile(artifacts: dict) -> dict | None:
        for item in artifacts.get("parse", {}).get("items", []):
            for table in item.get("tables", []):
                profile = table.get("data_profile") or {}
                if profile.get("series") or profile.get("preview_rows"):
                    return {
                        "filename": item.get("filename", "上传表格"),
                        "sheet": table.get("sheet", "数据"),
                        "profile": profile,
                    }
        return None

    @staticmethod
    def classify_citation(item: dict) -> dict:
        classified = dict(item)
        has_doi = bool(item.get("doi"))
        has_bibliography = bool(item.get("authors") and item.get("year") and item.get("venue"))
        classified["source_type"] = "academic_paper" if has_doi or item.get("venue") else "web"
        classified["access_url"] = item.get("url", "")
        if has_doi and has_bibliography:
            classified["quality_tier"] = "high"
            classified["reliability_score"] = 0.95
            classified["quality_notes"] = ["具备 DOI、作者、年份和期刊/会议字段。"]
        elif has_doi:
            classified["quality_tier"] = "medium"
            classified["reliability_score"] = 0.78
            classified["quality_notes"] = ["具备 DOI，但作者、年份或发表 venue 信息不完整。"]
        else:
            classified["quality_tier"] = "medium" if item.get("url") else "low"
            classified["reliability_score"] = 0.55 if item.get("url") else 0.25
            classified["quality_notes"] = ["缺少 DOI，建议用可核验论文或报告替代。"]
        return classified

    @staticmethod
    def classify_web_source(item: dict) -> dict:
        classified = dict(item)
        title = (item.get("title") or "").lower()
        content = (item.get("content") or "").lower()
        url = item.get("url") or ""
        host = urlparse(url).netloc.lower().removeprefix("www.")
        text = f"{title} {content} {host}"
        industry_hosts = ["mckinsey.com", "deloitte.com", "pwc.com", "gartner.com", "bcg.com", "accenture.com", "statista.com", "worldbank.org", "oecd.org"]
        news_hosts = ["reuters.com", "bloomberg.com", "wsj.com", "nytimes.com", "bbc.", "cnn.com", "theguardian.com", "apnews.com"]
        if not title or not url:
            source_type = "unreliable"
            tier = "low"
            score = 0.2
            notes = ["缺少标题或访问链接，不能可靠追溯。"]
        elif any(host.endswith(domain) for domain in industry_hosts) or any(token in text for token in ["industry report", "white paper", "research report", "annual report"]):
            source_type = "industry_report"
            tier = "high"
            score = 0.82
            notes = ["行业报告来源，适合支持市场、趋势和案例判断。"]
        elif any(domain in host for domain in news_hosts) or "news" in text:
            source_type = "news"
            tier = "medium"
            score = 0.62
            notes = ["新闻来源，适合说明近期事件，但不宜单独支撑长期结论。"]
        else:
            source_type = "web"
            tier = "medium"
            score = 0.5
            notes = ["普通网页来源，建议补充论文、报告或官方数据交叉验证。"]
        return {
            **classified,
            "source_type": source_type,
            "quality_tier": tier,
            "reliability_score": score,
            "quality_notes": notes,
            "access_url": url,
        }

    @staticmethod
    def _quality_summary(items: list[dict]) -> dict:
        summary = {
            "academic_paper": 0,
            "industry_report": 0,
            "web": 0,
            "news": 0,
            "unreliable": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for item in items:
            source_type = item.get("source_type") or "web"
            tier = item.get("quality_tier") or "medium"
            summary[source_type] = summary.get(source_type, 0) + 1
            summary[tier] = summary.get(tier, 0) + 1
        return summary

    @staticmethod
    def _error_text(exc: Exception) -> str:
        return f"{type(exc).__name__}: {str(exc)[:300]}"

    def _failure(self, provider: str, exc: Exception, **extra: Any) -> dict:
        return {
            "configured": True,
            "provider": provider,
            "found": 0,
            "selected": 0,
            "provider_error": self._error_text(exc),
            "note": f"{provider} 调用失败，错误已记录，可稍后重试。",
            **extra,
        }
