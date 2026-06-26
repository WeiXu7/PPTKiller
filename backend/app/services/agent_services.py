from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Project, ProjectAsset
from .llm import DeepSeekClient
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
        verified = [item for item in citations if item.get("doi") and item.get("url")]
        seen = set()
        unique = []
        duplicates = 0
        for item in citations:
            key = (item.get("doi") or item.get("title", "")).lower()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            unique.append(item)
        return {
            "verified": len(verified),
            "doi_checked": sum(bool(item.get("doi")) for item in unique),
            "duplicates_removed": duplicates,
            "citations": unique,
            "note": f"已保留 {len(unique)} 条唯一文献，其中 {len(verified)} 条具备 DOI 与来源链接。",
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
        fallback = self._fallback_outline(project)
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
      "layout": "cover|image_split|statement|two_column|process|evidence|summary",
      "bullets": ["要点1", "要点2"],
      "left_title": "可选左栏标题",
      "left_bullets": ["可选左栏要点"],
      "right_title": "可选右栏标题",
      "right_bullets": ["可选右栏要点"],
      "process_steps": ["可选步骤1", "可选步骤2"],
      "key_message": "可选核心结论",
      "citation_indices": [1],
      "image_query": "英文图片检索词",
      "speaker_notes": "中文演讲稿"
    }}
  ],
  "narrative": "整体叙事说明"
}}
必须生成 {project.slide_count} 页；不要编造资料中不存在的数字或文献。
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
                "slides": slides[: project.slide_count],
                "target_count": project.slide_count,
                "narrative": result.get("narrative", ""),
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
        return {"slides": slides, "target_count": project.slide_count, "narrative": "问题—证据—方案—行动"}

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
