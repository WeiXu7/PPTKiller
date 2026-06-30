import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const [, , inputPath, outputPath, qaDir] = process.argv;
if (!inputPath || !outputPath || !qaDir) {
  throw new Error("Usage: node generate-deck.mjs <input.json> <output.pptx> <qa-dir>");
}

const data = JSON.parse(await fs.readFile(inputPath, "utf8"));
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(qaDir, { recursive: true });

const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const C = {
  ink: "#172033",
  navy: "#355C88",
  blue: "#2D5F91",
  teal: "#4F89A8",
  tealSoft: "#E9F1F6",
  violet: "#7A6FA8",
  pale: "#F4F1EA",
  panel: "#FFFFFF",
  paper: "#F7F4EE",
  muted: "#667085",
  line: "#C8D1DA",
  green: "#1F8A5B",
  amber: "#B76E00",
  amberSoft: "#FFF4E6",
  slate: "#344054",
  white: "#FFFFFF",
  red: "#C94040",
  softBlue: "#DDE9F2",
  tableGreen: "#DCEAD1",
  tableOrange: "#F1D7BF",
};
const FONT = "Heiti SC";
const LATIN_FONT = "Arial";
const PAGE = { left: 66, top: 38, width: 1148, height: 626 };

function addSlideBase(slide, index, tone = "light") {
  const fill = tone === "dark" ? C.navy : C.paper;
  slide.background.fill = fill;
  addRect(slide, { left: 0, top: 0, width: 1280, height: 720 }, fill, fill);
  if (tone !== "dark") {
    addRect(slide, { left: 0, top: 0, width: 1280, height: 720 }, "#F8F5EF", "#F8F5EF");
  }
}

function addSectionLabel(slide, label, position = { left: PAGE.left, top: 82, width: 460, height: 22 }, color = C.teal) {
  addText(slide, String(label || "MEDICAL TEACHING").toUpperCase(), position, {
    fontSize: 9,
    bold: true,
    color,
    letterSpacing: 1,
  });
}

function addMedicalMarker(slide, left = PAGE.left, top = 32, color = C.navy) {
  addRect(slide, { left, top, width: 7, height: 30 }, color, color);
  addRect(slide, { left: left + 11, top, width: 7, height: 30 }, color, color);
}

function addTitleBlock(slide, item, top = 88, width = 930) {
  if (item.key_message) {
    addText(slide, item.key_message, { left: PAGE.left, top, width: Math.min(width, 940), height: 36 }, { fontSize: 15, color: C.slate, fontFamily: FONT });
    addRule(slide, PAGE.left, top + 44, Math.min(width, 940), "#D5DCE3");
  }
}

function addPill(slide, text, left, top, fill = C.tealSoft, color = C.teal) {
  addRect(slide, { left, top, width: Math.max(92, String(text || "").length * 11 + 28), height: 28 }, fill, fill, 6);
  addText(slide, text, { left: left + 14, top: top + 7, width: Math.max(64, String(text || "").length * 11), height: 14 }, { fontSize: 9, bold: true, color });
}

function safeDeckSubtitle(item, index) {
  if (item.key_message && String(item.key_message).length <= 90) return item.key_message;
  if (index > 0) return "感谢聆听 · 欢迎讨论";
  const topic = String(data.project.topic || "").replace(/\s+/g, " ").trim();
  const looksLikeInstruction = /请|不要|基于上传|生成一份|教学目标|缺失信息|病例驱动/.test(topic);
  if (!looksLikeInstruction && topic.length > 0 && topic.length <= 70) return topic;
  return "病例驱动影像教学 · CT 鉴别诊断与报告建议";
}

function addText(slide, text, position, style = {}, name = undefined) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    ...(name ? { name } : {}),
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = String(text || "");
  shape.text.style = {
    fontFamily: FONT,
    fontSize: 22,
    color: C.ink,
    ...style,
  };
  return shape;
}

function addRect(slide, position, fill, lineFill = fill, radius = 0) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position,
    fill,
    line: { style: "solid", fill: lineFill, width: lineFill === "none" ? 0 : 1 },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function addRule(slide, left, top, width, fill = C.line, height = 1) {
  addRect(slide, { left, top, width, height }, fill, fill);
}

function addHeader(slide, slideData, index) {
  addSlideBase(slide, index);
  addMedicalMarker(slide, PAGE.left, 28);
  addText(slide, slideData.title || data.project.title, { left: PAGE.left + 28, top: 28, width: 820, height: 34 }, { fontSize: 24, bold: true, color: C.navy, fontFamily: FONT });
  addText(slide, data.project.title, { left: 880, top: 39, width: 300, height: 18 }, { fontSize: 9, color: C.muted, alignment: "right" });
  addRule(slide, PAGE.left, 72, PAGE.width, "#AEBAC6");
}

function addFooter(slide, slideData, index) {
  const citations = (slideData.citations || []).slice(0, 2);
  let sourceText = citations.length
    ? citations.map((item) => item.doi || item.url || item.title).join("  ·  ")
    : "PPTKiller · human approved";
  if (slideData.image_author || slideData.image_source) {
    let sourceHost = "";
    try {
      sourceHost = slideData.image_source ? new URL(slideData.image_source).hostname.replace(/^www\./, "") : "";
    } catch {
      sourceHost = "";
    }
    const credit = `图片：${slideData.image_author || "来源链接"}${sourceHost ? ` / ${sourceHost}` : ""}`;
    sourceText = citations.length ? `${sourceText}  ·  ${credit}` : credit;
  }
  sourceText = sourceText.length > 125 ? `${sourceText.slice(0, 122)}…` : sourceText;
  addRect(slide, { left: 514, top: 676, width: 10, height: 10 }, "#E56B2E", "#E56B2E", 5);
  addRect(slide, { left: 526, top: 676, width: 10, height: 10 }, "#2E9E6F", "#2E9E6F", 5);
  addText(slide, data.project.title || "医学影像病例教学", { left: 540, top: 670, width: 330, height: 18 }, { fontSize: 8, color: C.muted, alignment: "center" });
  addText(slide, sourceText, { left: PAGE.left, top: 670, width: 430, height: 24 }, { fontSize: 7, color: C.muted });
  addText(slide, `${index + 1}`, { left: 1160, top: 670, width: 52, height: 20 }, { fontSize: 9, color: C.muted, alignment: "right" });
}

async function imageBytes(imagePath) {
  if (!imagePath) return null;
  try {
    return new Uint8Array(await fs.readFile(imagePath));
  } catch {
    return null;
  }
}

function addBullets(slide, bullets, position, options = {}) {
  const items = (bullets || []).filter(Boolean).slice(0, options.max || 5);
  const text = items.map((item) => `•  ${item}`).join("\n\n");
  return addText(slide, text, position, {
    fontSize: options.fontSize || 22,
    color: options.color || C.ink,
  });
}

async function buildCover(slide, item, image, index = 0) {
  addSlideBase(slide, 0);
  addRect(slide, { left: 0, top: 236, width: 1280, height: 168 }, C.navy, C.navy);
  addRect(slide, { left: 0, top: 404, width: 1280, height: 6 }, C.teal, C.teal);
  addMedicalMarker(slide, 96, 82);
  addText(slide, "Department Case Conference", { left: 126, top: 88, width: 420, height: 22 }, { fontSize: 13, color: C.navy, fontFamily: LATIN_FONT });
  addText(slide, item.title, { left: 96, top: 270, width: image ? 610 : 970, height: 74 }, { fontSize: 38, bold: true, color: C.white, fontFamily: FONT }, "deck-title");
  addText(slide, safeDeckSubtitle(item, index), { left: 100, top: 350, width: image ? 560 : 840, height: 34 }, { fontSize: 16, color: "#E8EFF5", fontFamily: FONT });
  addPill(slide, `${data.project.slide_count} 页`, 96, 462, C.softBlue, C.navy);
  addPill(slide, data.project.speaker_notes_enabled ? "含演讲稿" : "不含演讲稿", 204, 462, "#F5E7D8", C.amber);
  addText(slide, "病例驱动 · 文献可追溯 · 可编辑 PPTX", { left: 96, top: 542, width: 520, height: 24 }, { fontSize: 12, color: C.muted });
  if (image) {
    addRect(slide, { left: 748, top: 92, width: 438, height: 512 }, C.white, C.line, 6);
    slide.images.add({ blob: image, contentType: item.image_content_type || "image/jpeg", alt: item.image_alt || item.title, fit: "cover", position: { left: 764, top: 108, width: 406, height: 480 }, geometry: "roundRect", borderRadius: 4 });
  }
  addFooter(slide, item, index);
}

async function buildImageSplit(slide, item, image, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 560);
  addBullets(slide, item.bullets, { left: PAGE.left, top: 220, width: 520, height: 330 }, { fontSize: 17, max: 5, color: C.slate });
  if (image) {
    addRect(slide, { left: 642, top: 116, width: 570, height: 454 }, "#111111", "#111111", 2);
    slide.images.add({ blob: image, contentType: item.image_content_type || "image/jpeg", alt: item.image_alt || item.title, fit: "contain", position: { left: 656, top: 130, width: 542, height: 426 } });
  } else {
    addRect(slide, { left: 642, top: 116, width: 570, height: 454 }, C.white, C.line, 2);
    addRect(slide, { left: 662, top: 136, width: 530, height: 414 }, C.pale, C.pale, 2);
    addText(slide, item.image_query || "Visual evidence", { left: 730, top: 326, width: 405, height: 60 }, { fontSize: 21, color: C.muted, alignment: "center" });
  }
  addFooter(slide, item, index);
}

function buildStatement(slide, item, index) {
  addSlideBase(slide, index, "dark");
  addMedicalMarker(slide, 96, 86, "#DCE8F2");
  addSectionLabel(slide, "CORE MESSAGE", { left: 126, top: 92, width: 300, height: 22 }, "#DCE8F2");
  addText(slide, item.title, { left: 132, top: 178, width: 1010, height: 100 }, { fontSize: 36, bold: true, color: C.white, alignment: "center" });
  addText(slide, item.key_message || item.bullets?.[0] || "", { left: 170, top: 322, width: 940, height: 118 }, { fontSize: 26, color: "#EAF0F6", alignment: "center" });
  addRule(slide, 560, 512, 160, C.softBlue, 4);
  addText(slide, "核心观点", { left: 520, top: 538, width: 240, height: 28 }, { fontSize: 12, color: "#D8DEE9", alignment: "center" });
}

function buildTwoColumn(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 980);
  const leftTitle = item.left_title || "现状与机会";
  const rightTitle = item.right_title || "挑战与应对";
  addRect(slide, { left: PAGE.left, top: 214, width: 536, height: 356 }, "#FBFAF7", C.line, 4);
  addRect(slide, { left: 676, top: 214, width: 536, height: 356 }, "#FBFAF7", C.line, 4);
  addRect(slide, { left: PAGE.left, top: 214, width: 536, height: 7 }, C.navy, C.navy);
  addRect(slide, { left: 676, top: 214, width: 536, height: 7 }, C.teal, C.teal);
  addText(slide, leftTitle, { left: 100, top: 252, width: 440, height: 42 }, { fontSize: 22, bold: true, color: C.teal });
  addText(slide, rightTitle, { left: 708, top: 252, width: 440, height: 42 }, { fontSize: 22, bold: true, color: C.blue });
  addBullets(slide, item.left_bullets?.length ? item.left_bullets : (item.bullets || []).slice(0, 3), { left: 100, top: 320, width: 430, height: 220 }, { fontSize: 18, max: 4, color: C.slate });
  addBullets(slide, item.right_bullets?.length ? item.right_bullets : (item.bullets || []).slice(3), { left: 708, top: 320, width: 430, height: 220 }, { fontSize: 18, max: 4, color: C.slate });
  addFooter(slide, item, index);
}

function buildProcess(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 1000);
  const steps = (item.process_steps?.length ? item.process_steps : item.bullets || []).slice(0, 5);
  const startX = 84;
  const gap = 22;
  const width = (1112 - gap * Math.max(steps.length - 1, 0)) / Math.max(steps.length, 1);
  steps.forEach((step, stepIndex) => {
    const x = startX + stepIndex * (width + gap);
    addRect(slide, { left: x, top: 244, width, height: 238 }, "#FBFAF7", C.line, 4);
    addText(slide, String(stepIndex + 1).padStart(2, "0"), { left: x + 18, top: 268, width: 54, height: 42 }, { fontSize: 26, bold: true, color: stepIndex === 0 ? C.teal : C.blue });
    addRule(slide, x + 18, 322, width - 36, stepIndex === steps.length - 1 ? C.teal : C.line, 2);
    addText(slide, step, { left: x + 18, top: 346, width: width - 36, height: 94 }, { fontSize: 16, bold: true, color: C.ink });
    if (stepIndex < steps.length - 1) addText(slide, "→", { left: x + width + 2, top: 336, width: 18, height: 26 }, { fontSize: 17, bold: true, color: C.teal });
  });
  addText(slide, item.key_message || "", { left: 92, top: 540, width: 1090, height: 46 }, { fontSize: 17, color: C.slate, alignment: "center" });
  addFooter(slide, item, index);
}

function buildArchitectureSlide(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 940);
  addText(slide, item.diagram_title || "主链路架构", { left: PAGE.left, top: 218, width: 520, height: 28 }, { fontSize: 16, bold: true, color: C.teal });

  const modules = architectureModules(item);
  const gap = 18;
  const moduleWidth = (PAGE.width - gap * (modules.length - 1)) / Math.max(modules.length, 1);
  const top = 280;
  modules.forEach((module, moduleIndex) => {
    const left = PAGE.left + moduleIndex * (moduleWidth + gap);
    addRect(slide, { left, top, width: moduleWidth, height: 250 }, "#FBFAF7", C.line, 4);
    addRect(slide, { left, top, width: moduleWidth, height: 8 }, moduleIndex === 0 ? C.teal : C.blue, moduleIndex === 0 ? C.teal : C.blue);
    addText(slide, String(moduleIndex + 1).padStart(2, "0"), { left: left + 18, top: top + 24, width: 38, height: 20 }, { fontSize: 12, bold: true, color: C.teal });
    addText(slide, module.label, { left: left + 18, top: top + 46, width: moduleWidth - 36, height: 42 }, { fontSize: 17, bold: true, color: C.ink });
    (module.children || []).slice(0, 2).forEach((child, childIndex) => {
      const childTop = top + 112 + childIndex * 58;
      addRect(slide, { left: left + 16, top: childTop, width: moduleWidth - 32, height: 44 }, C.pale, C.line, 2);
      addText(slide, child.label || child.detail || "", { left: left + 28, top: childTop + 10, width: moduleWidth - 56, height: 18 }, { fontSize: 11, bold: true, color: C.ink });
      if (child.detail) addText(slide, child.detail, { left: left + 28, top: childTop + 27, width: moduleWidth - 56, height: 13 }, { fontSize: 8, color: C.muted });
    });
    if (moduleIndex < modules.length - 1) {
      const x = left + moduleWidth + 4;
      addRule(slide, x, top + 126, gap - 8, C.teal, 2);
      addText(slide, "→", { left: x + gap - 18, top: top + 113, width: 20, height: 22 }, { fontSize: 16, bold: true, color: C.teal });
    }
  });
  if (item.visual_rationale) addText(slide, item.visual_rationale, { left: PAGE.left, top: 560, width: PAGE.width, height: 32 }, { fontSize: 13, color: C.muted, alignment: "center" });
  addFooter(slide, item, index);
}

function architectureModules(item) {
  if (item.diagram_modules?.length) return item.diagram_modules.slice(0, 5);
  const nodes = (item.diagram_nodes || []).slice(0, 10);
  const layers = item.diagram_layers?.length ? item.diagram_layers.slice(0, 5) : [...new Set(nodes.map((node) => node.layer).filter(Boolean))].slice(0, 5);
  const fallbackLayers = layers.length ? layers : ["输入", "处理", "输出"];
  return fallbackLayers.map((layer, index) => ({
    id: `module_${index + 1}`,
    label: layer,
    children: nodes.filter((node) => node.layer === layer).slice(0, 2).map((node) => ({ label: node.label || node.id, detail: node.detail || "" })),
  }));
}

function buildEvidence(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 900);
  addRect(slide, { left: PAGE.left, top: 214, width: 748, height: 366 }, "#FBFAF7", C.line, 4);
  addRect(slide, { left: PAGE.left, top: 214, width: 8, height: 366 }, C.navy, C.navy);
  addText(slide, item.key_message || item.bullets?.[0] || "证据指向明确的行动窗口", { left: 108, top: 260, width: 660, height: 112 }, { fontSize: 30, bold: true, color: C.ink });
  addBullets(slide, item.bullets?.slice(1), { left: 108, top: 410, width: 650, height: 128 }, { fontSize: 17, max: 3, color: C.slate });
  addText(slide, "引用来源", { left: 862, top: 230, width: 280, height: 34 }, { fontSize: 18, bold: true, color: C.teal });
  const citations = (item.citations || []).slice(0, 4);
  if (citations.length) {
    citations.forEach((citation, citationIndex) => {
      const y = 288 + citationIndex * 72;
      addText(slide, String(citationIndex + 1), { left: 862, top: y, width: 28, height: 30 }, { fontSize: 13, bold: true, color: C.teal });
      addText(slide, citation.title || citation.doi || citation.url, { left: 900, top: y, width: 292, height: 54 }, { fontSize: 13, color: C.ink });
    });
  } else {
    addText(slide, "本页结论来自用户资料与检索结果的综合归纳。正式交付前建议补充可核验来源。", { left: 862, top: 286, width: 320, height: 150 }, { fontSize: 15, color: C.muted });
  }
  addFooter(slide, item, index);
}

function buildDataSlide(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 860);
  const chartType = item.chart_type || "table";
  if (chartType === "table") buildDataTable(slide, item);
  else if (chartType === "kpi") buildKpis(slide, item);
  else buildChart(slide, item, chartType);
  const source = item.data_source ? `数据来源：${item.data_source.filename || ""}${item.data_source.sheet ? ` / ${item.data_source.sheet}` : ""}` : "";
  addText(slide, source, { left: PAGE.left, top: 626, width: 720, height: 24 }, { fontSize: 10, color: C.muted });
  addFooter(slide, item, index);
}

function buildChart(slide, item, chartType) {
  const series = (item.data_series || [])[0];
  const points = (series?.points || []).slice(0, 8);
  if (!points.length) return buildDataTable(slide, item);
  const values = points.map((point) => Number(point.value) || 0);
  const max = Math.max(...values, 1);
  const left = 92;
  const top = 250;
  const width = 720;
  const height = 300;
  addRect(slide, { left: 72, top: 226, width: 770, height: 366 }, "#FBFAF7", C.line, 4);
  addRule(slide, left, top + height, width, C.line, 2);
  addRule(slide, left, top, 1, C.line, height);
  if (chartType === "line") {
    points.forEach((point, pointIndex) => {
      const x = left + 22 + pointIndex * ((width - 44) / Math.max(points.length - 1, 1));
      const y = top + height - (values[pointIndex] / max) * (height - 36);
      addRect(slide, { left: x - 4, top: y - 4, width: 8, height: 8 }, C.violet, C.violet, 4);
      if (pointIndex > 0) {
        const prevX = left + 22 + (pointIndex - 1) * ((width - 44) / Math.max(points.length - 1, 1));
        const prevY = top + height - (values[pointIndex - 1] / max) * (height - 36);
        addRule(slide, Math.min(prevX, x), Math.min(prevY, y), Math.hypot(x - prevX, y - prevY), C.teal, 3);
      }
      addText(slide, point.label, { left: x - 34, top: top + height + 16, width: 68, height: 22 }, { fontSize: 10, color: C.muted, alignment: "center" });
    });
  } else {
    const gap = 16;
    const barWidth = (width - gap * (points.length + 1)) / points.length;
    points.forEach((point, pointIndex) => {
      const barHeight = (values[pointIndex] / max) * (height - 36);
      const x = left + gap + pointIndex * (barWidth + gap);
      const y = top + height - barHeight;
      addRect(slide, { left: x, top: y, width: barWidth, height: barHeight }, pointIndex % 2 ? C.blue : C.teal, pointIndex % 2 ? C.blue : C.teal, 2);
      addText(slide, point.label, { left: x - 8, top: top + height + 16, width: barWidth + 16, height: 22 }, { fontSize: 10, color: C.muted, alignment: "center" });
      addText(slide, point.value, { left: x - 8, top: y - 28, width: barWidth + 16, height: 20 }, { fontSize: 11, color: C.ink, alignment: "center", bold: true });
    });
  }
  buildKpis(slide, item, { left: 875, top: 250, width: 270 });
}

function buildDataTable(slide, item) {
  const headers = (item.data_table?.headers || []).slice(0, 5);
  const rows = (item.data_table?.rows || []).slice(0, 7);
  const left = PAGE.left;
  const top = 230;
  const colWidth = 1030 / Math.max(headers.length, 1);
  addRect(slide, { left, top, width: 1030, height: 36 }, C.navy, C.navy, 2);
  headers.forEach((header, index) => addText(slide, header, { left: left + index * colWidth + 10, top: top + 9, width: colWidth - 20, height: 20 }, { fontSize: 12, color: C.white, bold: true }));
  rows.forEach((row, rowIndex) => {
    const y = top + 36 + rowIndex * 42;
    addRect(slide, { left, top: y, width: 1030, height: 42 }, rowIndex % 2 ? "#FBFAF7" : C.pale, C.line);
    headers.forEach((_, colIndex) => addText(slide, row[colIndex] || "", { left: left + colIndex * colWidth + 10, top: y + 12, width: colWidth - 20, height: 20 }, { fontSize: 11, color: C.ink }));
  });
}

function buildKpis(slide, item, box = { left: PAGE.left, top: 238, width: PAGE.width }) {
  const kpis = (item.kpis || []).slice(0, 4);
  if (!kpis.length) return;
  const cardWidth = box.width / kpis.length - 12;
  kpis.forEach((kpi, index) => {
    const x = box.left + index * (cardWidth + 12);
    addRect(slide, { left: x, top: box.top, width: cardWidth, height: 112 }, "#FBFAF7", C.line, 4);
    addRect(slide, { left: x, top: box.top, width: cardWidth, height: 6 }, index % 2 ? C.blue : C.teal, index % 2 ? C.blue : C.teal);
    addText(slide, kpi.label, { left: x + 18, top: box.top + 18, width: cardWidth - 36, height: 24 }, { fontSize: 12, color: C.muted });
    addText(slide, kpi.value, { left: x + 18, top: box.top + 50, width: cardWidth - 36, height: 40 }, { fontSize: 30, bold: true, color: C.teal });
  });
}

function buildSummary(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 96, 950);
  const bullets = (item.bullets || []).slice(0, 4);
  bullets.forEach((bullet, bulletIndex) => {
    const top = 220 + bulletIndex * 84;
    addText(slide, `0${bulletIndex + 1}`, { left: 84, top, width: 70, height: 42 }, { fontSize: 22, bold: true, color: C.teal });
    addText(slide, bullet, { left: 170, top, width: 950, height: 58 }, { fontSize: 22, bold: true, color: C.ink });
    addRule(slide, 170, top + 66, 950, C.line);
  });
  addText(slide, item.key_message || "从洞察走向行动", { left: 172, top: 590, width: 940, height: 44 }, { fontSize: 18, color: C.slate });
  addFooter(slide, item, index);
}

function buildCaseSlide(slide, item, index) {
  addHeader(slide, item, index);
  addTitleBlock(slide, item, 92, 920);
  const card = item.case_card || {};
  const missing = card.missing_information || item.missing_information || [];
  const facts = [
    ["检查方式", card.modality || "待补充"],
    ["临床背景", card.clinical_background || "待补充"],
    ["诊断依据", card.diagnosis_basis || "待补充"],
    ["展示方式", card.display_mode || item.display_mode || "先提问后揭示"],
  ];
  addRect(slide, { left: PAGE.left, top: 214, width: 500, height: 336 }, "#FBFAF7", C.line, 4);
  addRect(slide, { left: PAGE.left, top: 214, width: 500, height: 7 }, C.navy, C.navy);
  addText(slide, card.case_id || item.title || "Case", { left: 100, top: 254, width: 220, height: 32 }, { fontSize: 21, bold: true, color: C.ink });
  addPill(slide, card.teaching_role || "教学病例", 330, 254, C.tealSoft, C.teal);
  facts.forEach(([label, value], factIndex) => {
    const top = 310 + factIndex * 50;
    addText(slide, label, { left: 104, top, width: 110, height: 18 }, { fontSize: 10, color: C.muted, bold: true });
    addText(slide, value, { left: 220, top: top - 2, width: 300, height: 26 }, { fontSize: 14, color: C.ink });
  });
  addRect(slide, { left: 604, top: 214, width: 608, height: 336 }, missing.length ? C.amberSoft : C.tealSoft, missing.length ? "#F3D7A8" : "#CFEDEB", 4);
  addText(slide, missing.length ? "待医生补充确认" : "病例信息可用于生成", { left: 638, top: 258, width: 420, height: 32 }, { fontSize: 22, bold: true, color: missing.length ? C.amber : C.teal });
  const detailBullets = missing.length ? missing : (item.bullets || ["病例事实已具备基础教学可用性"]);
  addBullets(slide, detailBullets, { left: 638, top: 318, width: 500, height: 158 }, { fontSize: 17, max: 4, color: C.slate });
  addText(slide, item.key_message || "病例页只展示已确认事实，不自动编造诊断结论。", { left: 638, top: 494, width: 500, height: 34 }, { fontSize: 13, color: C.muted });
  addFooter(slide, item, index);
}

for (const [index, item] of data.slides.entries()) {
  const slide = deck.slides.add();
  const image = await imageBytes(item.image_path);
  const layout = index === 0 ? "cover" : item.layout || item.type || "content";
  if (layout === "cover") await buildCover(slide, item, image, index);
  else if (layout === "image_split" || (layout === "case" && image)) await buildImageSplit(slide, item, image, index);
  else if (layout === "statement") buildStatement(slide, item, index);
  else if (layout === "two_column") buildTwoColumn(slide, item, index);
  else if (layout === "process") buildProcess(slide, item, index);
  else if (layout === "architecture") buildArchitectureSlide(slide, item, index);
  else if (layout === "data") buildDataSlide(slide, item, index);
  else if (layout === "evidence") buildEvidence(slide, item, index);
  else if (layout === "case") buildCaseSlide(slide, item, index);
  else if (layout === "summary") buildSummary(slide, item, index);
  else if (image) await buildImageSplit(slide, item, image, index);
  else buildTwoColumn(slide, item, index);

  if (item.speaker_notes) {
    slide.speakerNotes.textFrame.setText(item.speaker_notes);
    slide.speakerNotes.setVisible(true);
  }
}

for (const [index, slide] of deck.slides.items.entries()) {
  const stem = `slide-${String(index + 1).padStart(2, "0")}`;
  const png = await deck.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(qaDir, `${stem}.png`), new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(qaDir, `${stem}.layout.json`), await layout.text());
}

const montage = await deck.export({ format: "webp", montage: true, scale: 0.5 });
await fs.writeFile(path.join(qaDir, "montage.webp"), new Uint8Array(await montage.arrayBuffer()));
const inspection = await deck.inspect({ kind: "slide,textbox,shape,image,table,chart,notes,layout", maxChars: 50000 });
await fs.writeFile(path.join(qaDir, "inspect.ndjson"), inspection.ndjson);
const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(outputPath);

console.log(JSON.stringify({ output: outputPath, qaDir, slides: data.slides.length }));
