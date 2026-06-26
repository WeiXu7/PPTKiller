from __future__ import annotations

from copy import deepcopy


TEMPLATE_ID = "consulting-default"
TEMPLATE_VERSION = "1.0"
ALLOWED_LAYOUTS = {"cover", "image_split", "statement", "two_column", "process", "architecture", "evidence", "summary", "content", "data", "case"}


def apply_consulting_template(outline: dict) -> dict:
    """Constrain generated content to the default consulting deck system."""
    templated = deepcopy(outline or {})
    slides = []
    raw_slides = templated.get("slides") or []
    for index, slide in enumerate(raw_slides):
        clean = dict(slide)
        is_deck_cover = index == 0 and int(clean.get("number") or 1) == 1
        layout = "cover" if is_deck_cover else clean.get("layout") or clean.get("type") or "content"
        if layout not in ALLOWED_LAYOUTS:
            layout = "content"
        clean["layout"] = layout
        clean["design_template"] = TEMPLATE_ID
        clean["design_role"] = _design_role(layout, index, len(raw_slides), is_deck_cover)
        clean["max_bullets"] = 4
        clean["bullets"] = [str(item) for item in (clean.get("bullets") or []) if str(item).strip()][:4]
        if clean.get("left_bullets"):
            clean["left_bullets"] = [str(item) for item in clean["left_bullets"] if str(item).strip()][:3]
        if clean.get("right_bullets"):
            clean["right_bullets"] = [str(item) for item in clean["right_bullets"] if str(item).strip()][:3]
        if clean.get("process_steps"):
            clean["process_steps"] = [str(item) for item in clean["process_steps"] if str(item).strip()][:5]
        if layout == "architecture":
            clean = normalize_architecture_diagram(clean)
        slides.append(clean)
    templated["slides"] = slides
    templated["target_count"] = len(slides)
    templated["design_template"] = TEMPLATE_ID
    templated["template_version"] = TEMPLATE_VERSION
    return templated


def normalize_architecture_diagram(slide: dict) -> dict:
    clean = dict(slide)
    nodes = [dict(node) for node in (clean.get("diagram_nodes") or []) if node.get("label") or node.get("id")]
    layers = [str(layer) for layer in (clean.get("diagram_layers") or []) if str(layer).strip()]
    if not layers:
        layers = list(dict.fromkeys(node.get("layer") for node in nodes if node.get("layer")))
    if not layers:
        layers = ["输入", "处理", "输出"]
    layers = layers[:5]
    modules = []
    used_node_ids = set()
    for layer in layers:
        layer_nodes = [node for node in nodes if node.get("layer") == layer and node.get("id") not in used_node_ids]
        if not layer_nodes:
            layer_nodes = [node for node in nodes if node.get("id") not in used_node_ids][:1]
        children = []
        for node in layer_nodes[:2]:
            used_node_ids.add(node.get("id"))
            label = str(node.get("label") or node.get("id") or "").strip()
            detail = str(node.get("detail") or "").strip()
            if label:
                children.append({"label": label[:24], "detail": detail[:42]})
        modules.append({
            "id": _module_id(layer, len(modules)),
            "label": layer[:18],
            "children": children,
        })
    modules = [module for module in modules if module["children"] or module["label"]]
    if len(modules) < 2:
        modules = _fallback_modules(clean)
    clean["diagram_style"] = "main_chain"
    clean["diagram_modules"] = modules[:5]
    clean["diagram_layers"] = [module["label"] for module in clean["diagram_modules"]]
    clean["diagram_edges"] = [
        {"from": clean["diagram_modules"][index]["id"], "to": clean["diagram_modules"][index + 1]["id"], "label": "推进"}
        for index in range(max(len(clean["diagram_modules"]) - 1, 0))
    ]
    return clean


def _design_role(layout: str, index: int, total: int, is_deck_cover: bool) -> str:
    if is_deck_cover or layout == "cover":
        return "cover"
    if layout == "summary":
        return "summary"
    if layout in {"data", "architecture", "evidence", "process"}:
        return layout
    return "content"


def _module_id(label: str, index: int) -> str:
    return f"module_{index + 1}_{abs(hash(label)) % 10000}"


def _fallback_modules(slide: dict) -> list[dict]:
    labels = slide.get("diagram_layers") or ["输入", "处理", "输出"]
    return [
        {"id": f"module_{index + 1}", "label": str(label)[:18], "children": []}
        for index, label in enumerate(labels[:3])
    ]
