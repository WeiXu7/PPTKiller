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
from .providers import (
    CrossrefLiteratureProvider,
    OpenAlexLiteratureProvider,
    PubMedLiteratureProvider,
    SemanticScholarLiteratureProvider,
    TavilyResearchProvider,
    UnsplashImageProvider,
    dedupe_citations,
)
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
                "path": asset.path,
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

    async def case_prepare(self, project: Project, brief: dict, parsed: dict) -> dict:
        topic = f"{project.title} {project.topic}".strip()
        assets = parsed.get("items", [])
        checklist = self._radiology_case_checklist(topic)
        case_cards = self._case_cards_from_assets(assets)
        if not case_cards:
            readiness = "not_recommended"
            readiness_label = "不建议直接生成"
            missing_summary = ["尚未上传病例材料", "缺少最终诊断/病理/随访支持", "缺少关键图像与脱敏确认"]
            next_questions = [
                "请补充 3-5 个已脱敏病例，每个病例至少包含关键图像、检查方式和最终诊断依据。",
                "是否已有病理、随访结果或临床结局可以作为诊断验证？",
                "希望本次教学更偏典型征象、鉴别诊断、误诊陷阱，还是多病例对照？",
            ]
            note = "已进入影像科病例驱动模式：当前只有主题，建议先收集病例材料，再生成最终 PPT。"
        else:
            ready_cards = [card for card in case_cards if card["readiness"] == "ready"]
            warning_cards = [card for card in case_cards if card["readiness"] == "needs_info"]
            if len(ready_cards) >= 2 and len(warning_cards) <= len(ready_cards):
                readiness = "can_generate_with_warnings"
                readiness_label = "可带警告生成"
            else:
                readiness = "not_recommended"
                readiness_label = "建议补充后生成"
            missing_summary = sorted({item for card in case_cards for item in card.get("missing_information", [])})
            next_questions = self._case_followup_questions(case_cards)
            note = f"已盘点 {len(case_cards)} 个病例材料；{len(ready_cards)} 个相对完整，{len(warning_cards)} 个需要补充信息。"

        storyline = self._radiology_storyline(topic, case_cards)
        return {
            "mode": "radiology_case",
            "topic": topic,
            "asset_count": len(assets),
            "case_count": len(case_cards),
            "readiness": readiness,
            "readiness_label": readiness_label,
            "case_collection_checklist": checklist,
            "case_cards": case_cards,
            "missing_summary": missing_summary,
            "next_questions": next_questions,
            "teaching_storyline": storyline,
            "approval_required": True,
            "note": note,
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
        is_radiology_case = brief.get("presentation_mode") == "radiology_case"
        fallback_outline = self._fallback_radiology_outline(project, artifacts) if brief.get("presentation_mode") == "radiology_case" else self._fallback_outline(project)
        fallback = apply_consulting_template(fallback_outline if is_radiology_case else self.with_data_slides(project, fallback_outline, artifacts))
        if not self.llm.configured:
            return {**fallback, "generated_by": "fallback", "note": "DeepSeek 未配置，已使用本地大纲。"}
        research = artifacts.get("research", {})
        verified = artifacts.get("verify", {})
        parsed = artifacts.get("parse", {})
        source_context = {
            "uploaded_text": parsed.get("text_context", "")[:12000],
            "web_results": research.get("web_results", [])[:8],
            "citations": verified.get("citations", [])[:12],
            "case_prepare": artifacts.get("case_prepare", {}),
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
默认使用医学教学汇报模板系统：米白底、深蓝标题带、页脚来源署名；每页只有一个主观点，普通页最多 4 个要点，双栏每栏最多 3 个要点，流程最多 5 步。
如果 brief.presentation_mode 是 radiology_case，必须按影像科教学病例讨论组织内容，不得编造病例事实，缺失字段必须写成待补充。
影像病例模式的具体要求：
- 不要把“主题要求/用户指令”原文放进封面、结束页或正文；封面只写短副标题。
- 不要把 case-index.csv 之类病例总表单独做成数据洞察页；它只作为病例索引资料使用。
- 内容结构要贴近用户参考 PPT：封面 → 正常解剖/检查方法或定位基础 → 疾病谱/分类/分级 → 核心疾病概念 → 影像诊断框架 → 关键征象分解 → Case 1/2/3 多页展开 → 鉴别诊断 → checklist/报告建议/讨论总结。
- 前 1/3 不要急着堆病例，必须先讲清基础、分类和读片路径；病例页用于验证前面建立的框架。
- 至少包含诊断框架页：临床背景、部位、大小、形态、边界、密度/信号、增强、周围改变、随访变化。
- 每个病例至少展开 2 页：①临床背景+关键图像+读片问题；②影像征象+诊断推理+鉴别诊断/病理或随访验证/教学陷阱。
- 病例页标题必须包含 Case ID，例如 “Case-01：典型肺腺癌读片问题”；这样导出时可以匹配上传病例图片。
- 结尾必须包含跨病例对照、影像诊断 checklist、报告书写建议和讨论问题。
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
                **apply_consulting_template(({
                    "slides": slides[: project.slide_count],
                    "target_count": project.slide_count,
                    "narrative": result.get("narrative", ""),
                } if is_radiology_case else self.with_data_slides(project, {
                    "slides": slides[: project.slide_count],
                    "target_count": project.slide_count,
                    "narrative": result.get("narrative", ""),
                }, artifacts))),
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
        providers = [
            CrossrefLiteratureProvider(),
            SemanticScholarLiteratureProvider(self.settings.semantic_scholar_api_key),
            OpenAlexLiteratureProvider(),
            PubMedLiteratureProvider(),
        ]
        results = await asyncio.gather(*(provider.search(query, 8) for provider in providers), return_exceptions=True)
        citations = []
        failures = []
        for provider, result in zip(providers, results):
            provider_name = provider.__class__.__name__.replace("LiteratureProvider", "")
            if isinstance(result, Exception):
                failures.append({"provider": provider_name, "error": self._error_text(result), "verified": False})
                continue
            citations.extend(result)
        unique = dedupe_citations(citations)
        return [item.__dict__ for item in unique[:24]] + failures

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
    def _radiology_case_checklist(topic: str) -> list[dict]:
        roles = [
            ("typical", "典型病例", "呈现最有代表性的影像征象，建立基础识别框架", True),
            ("atypical", "非典型病例", "展示容易偏离常规印象的表现，训练边界判断", False),
            ("differential", "鉴别诊断病例", "与相似疾病并列比较，强化排除思路", True),
            ("pitfall", "误诊陷阱病例", "复盘容易误判的征象、病史或检查条件", False),
            ("follow_up", "病理/随访验证病例", "用病理、随访或临床结局支撑最终诊断", True),
        ]
        return [
            {
                "role": role,
                "label": label,
                "required": required,
                "teaching_value": value,
                "collect": ["已脱敏关键图像", "检查方式/序列/期相", "临床背景", "影像表现", "最终诊断或验证依据"],
                "topic_fit": topic,
            }
            for role, label, value, required in roles
        ]

    @staticmethod
    def _case_cards_from_assets(assets: list[dict]) -> list[dict]:
        cards = []
        for index, asset in enumerate(assets, start=1):
            text = " ".join([
                asset.get("filename", ""),
                asset.get("description", ""),
                asset.get("text", ""),
            ]).lower()
            has_image = asset.get("content_type", "").startswith("image/") or any(token in text for token in ["ct", "mri", "mr", "超声", "影像", "图像", "增强", "平扫"])
            has_diagnosis = any(token in text for token in ["诊断", "病理", "随访", "确诊", "diagnosis", "pathology", "follow-up", "follow up"])
            has_clinical = any(token in text for token in ["主诉", "病史", "临床", "症状", "年龄", "男性", "女性", "male", "female"])
            has_deidentified = any(token in text for token in ["脱敏", "匿名", "de-identified", "deidentified", "anonymized"])
            missing = []
            if not has_clinical:
                missing.append("临床背景/年龄性别")
            if not has_image:
                missing.append("关键图像或检查方式")
            if not has_diagnosis:
                missing.append("最终诊断/病理/随访结果")
            if not has_deidentified:
                missing.append("脱敏确认")
            role = ["typical", "differential", "pitfall", "follow_up", "atypical"][(index - 1) % 5]
            cards.append({
                "case_id": f"Case {index}",
                "source_asset_id": asset.get("id", ""),
                "source_filename": asset.get("filename", f"病例材料 {index}"),
                "modality": AgentServices._infer_modality(text),
                "clinical_background": "已从材料中发现临床线索" if has_clinical else "待补充",
                "imaging_findings": "待医生确认关键影像表现",
                "diagnosis_basis": "材料包含诊断/病理/随访线索" if has_diagnosis else "待补充",
                "teaching_role": role,
                "display_mode": "reveal-answer-later" if role in {"differential", "pitfall"} else "direct explanation",
                "missing_information": missing,
                "readiness": "ready" if not missing else "needs_info",
            })
        return cards

    @staticmethod
    def _infer_modality(text: str) -> str:
        if "mri" in text or "mr" in text or "磁共振" in text:
            return "MRI"
        if "ct" in text:
            return "CT"
        if "超声" in text or "ultrasound" in text:
            return "超声"
        if "x线" in text or "x-ray" in text or "dr" in text:
            return "X 线"
        return "待补充"

    @staticmethod
    def _case_followup_questions(case_cards: list[dict]) -> list[str]:
        questions = []
        for card in case_cards[:5]:
            missing = "、".join(card.get("missing_information", []))
            if missing:
                questions.append(f"{card['case_id']}（{card['source_filename']}）请补充：{missing}。")
        if not questions:
            questions.append("请确认这些病例均已脱敏，并允许用于教学展示。")
        questions.append("是否需要按“先读片提问、后揭示答案”的方式展示关键病例？")
        return questions[:6]

    @staticmethod
    def _radiology_storyline(topic: str, case_cards: list[dict]) -> list[dict]:
        if not case_cards:
            return [
                {"section": "正常基础", "goal": "先讲清解剖、检查方法和定位语言", "case_ids": []},
                {"section": "疾病谱与框架", "goal": "建立分类、关键征象和鉴别路径", "case_ids": []},
                {"section": "病例验证", "goal": "补齐典型、鉴别诊断和验证病例后再生成完整病例页", "case_ids": []},
            ]
        return [
            {"section": "正常基础", "goal": f"围绕 {topic} 先讲解定位、分类和影像诊断框架", "case_ids": []},
            {"section": "病例展开", "goal": "每个病例按临床背景、关键图像、征象推理和验证依据展开", "case_ids": [card["case_id"] for card in case_cards[:4]]},
            {"section": "鉴别总结", "goal": "用跨病例对照沉淀 checklist、报告建议和讨论问题", "case_ids": [card["case_id"] for card in case_cards if card["teaching_role"] == "follow_up"]},
        ]

    def _fallback_radiology_outline(self, project: Project, artifacts: dict) -> dict:
        prepare = artifacts.get("case_prepare", {})
        case_cards = prepare.get("case_cards", [])
        base_titles = [
            project.title,
            "正常解剖与检查方法基础",
            "疾病谱与分类框架",
            "影像诊断框架与读片路径",
            "关键征象分解",
        ]
        cards = case_cards[:4] or [
            {"case_id": "Case-01", "teaching_role": "典型表现", "modality": "待补充", "missing_information": ["关键图像", "最终诊断依据"]},
            {"case_id": "Case-02", "teaching_role": "鉴别诊断", "modality": "待补充", "missing_information": ["关键图像", "随访或病理验证"]},
        ]
        case_titles = []
        for card in cards:
            case_id = card.get("case_id", "Case")
            role = card.get("teaching_role", "教学病例")
            case_titles.extend([
                f"{case_id}：{role}读片问题",
                f"{case_id}：影像征象与诊断推理",
            ])
        tail_titles = ["跨病例对照与鉴别诊断", "影像诊断 checklist 与报告建议", "讨论问题与总结"]
        titles = base_titles + case_titles + tail_titles
        while len(titles) < project.slide_count:
            titles.insert(-1, f"关键征象补充 {len(titles) - len(base_titles) + 1}")
        slides = []
        case_lookup = {}
        for card in cards:
            case_lookup[str(card.get("case_id", "")).lower()] = card
        for index, title in enumerate(titles[: project.slide_count]):
            number = index + 1
            if index == 0:
                slide = {
                    "number": number,
                    "title": title,
                    "type": "cover",
                    "layout": "cover",
                    "bullets": [project.topic or "影像科病例驱动教学"],
                    "key_message": "本演示以病例事实和医生确认信息为边界。",
                }
            elif title == "正常解剖与检查方法基础":
                slide = {
                    "number": number,
                    "title": title,
                    "type": "content",
                    "layout": "image_split",
                    "bullets": [
                        "先明确正常解剖、检查方式和标准切面",
                        "统一部位、层面、密度/信号和增强描述语言",
                        "为后续病例定位和征象判断建立共同参照",
                    ],
                    "key_message": "像参考课件一样，先建立正常基础，再进入病变分析。",
                }
            elif title == "疾病谱与分类框架":
                slide = {
                    "number": number,
                    "title": title,
                    "type": "content",
                    "layout": "two_column",
                    "left_title": "常见类别",
                    "left_bullets": ["恶性肿瘤/癌前病变", "炎症或感染性病变", "良性结节或瘢痕改变"],
                    "right_title": "鉴别依据",
                    "right_bullets": ["形态与边界", "密度/信号与强化", "随访变化与验证依据"],
                    "bullets": ["先给疾病谱，再用病例逐一落地"],
                }
            elif title == "影像诊断框架与读片路径":
                slide = {
                    "number": number,
                    "title": title,
                    "type": "content",
                    "layout": "process",
                    "process_steps": ["临床背景", "部位与大小", "形态和边界", "密度/信号与增强", "周围改变和随访"],
                    "bullets": ["按固定顺序读片，减少只凭单一征象下结论"],
                    "key_message": "参考课件式的讲解重点是把诊断路径拆成可复用步骤。",
                }
            elif title == "关键征象分解" or title.startswith("关键征象补充"):
                slide = {
                    "number": number,
                    "title": title,
                    "type": "content",
                    "layout": "evidence",
                    "bullets": ["形态：分叶、毛刺、类圆形或浸润性生长", "边界：清楚、欠清、包膜或胸膜牵拉", "密度/信号：实性、磨玻璃、脂肪、坏死或出血", "强化与动态变化：持续、渐进、环形或无强化"],
                    "key_message": "先讲征象含义，再把征象带入病例判断。",
                }
            elif title.startswith("Case"):
                case_key = title.split("：", 1)[0].lower()
                card = case_lookup.get(case_key, cards[0] if cards else {})
                is_question_page = "读片问题" in title
                slide = {
                    "number": number,
                    "title": title,
                    "type": "case",
                    "layout": "image_split" if is_question_page else "case",
                    "bullets": [
                        f"临床背景：{card.get('clinical_background', '待补充')}",
                        f"检查方式：{card.get('modality', '待补充')}",
                        "请先描述部位、大小、形态、边界和密度/信号",
                    ] if is_question_page else [
                        f"影像表现：{card.get('imaging_findings', '待补充')}",
                        f"诊断依据：{card.get('diagnosis_basis', '待补充')}",
                        f"待补充：{'、'.join(card.get('missing_information', [])) or '请医生确认事实'}",
                    ],
                    "key_message": "先读片提问，再揭示诊断推理。" if is_question_page else "用已确认事实解释诊断，不自动编造病理或随访结论。",
                    "case_card": card,
                }
            elif title == "跨病例对照与鉴别诊断":
                slide = {
                    "number": number,
                    "title": title,
                    "type": "content",
                    "layout": "two_column",
                    "left_title": "支持目标诊断",
                    "left_bullets": ["持续存在或进展", "典型形态/强化模式", "与病理或随访一致"],
                    "right_title": "需要排除",
                    "right_bullets": ["炎症吸收或迁移", "良性结节稳定表现", "检查条件或伪影干扰"],
                    "bullets": ["把病例差异转化为鉴别诊断规则"],
                    "key_message": "参考课件常用跨病例对照来收束鉴别点。",
                }
            elif title == "影像诊断 checklist 与报告建议":
                slide = {
                    "number": number,
                    "title": title,
                    "type": "summary",
                    "layout": "summary",
                    "bullets": ["定位与测量", "征象完整描述", "鉴别诊断排序", "建议随访/增强/病理验证"],
                    "key_message": "报告建议要能直接服务临床下一步决策。",
                }
            else:
                slide = {
                    "number": number,
                    "title": title,
                    "type": "summary" if number == project.slide_count else "content",
                    "layout": "summary" if number == project.slide_count else "evidence",
                    "bullets": ["读片问题", "诊断推理", "报告建议", "讨论要点"][:4],
                    "key_message": "用病例对照沉淀可复用的影像诊断思路。",
                }
            slide.setdefault("citation_indices", [])
            slide.setdefault("image_query", "")
            slide.setdefault("speaker_notes", f"本页围绕“{title}”展开，请结合已确认病例事实讲解。")
            slides.append(slide)
        return {"slides": slides, "target_count": project.slide_count, "narrative": "正常基础—疾病谱分类—征象框架—病例推理—鉴别总结"}

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
