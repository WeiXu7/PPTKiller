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
  ink: "#111936",
  navy: "#14245A",
  violet: "#5B4BE7",
  pale: "#F4F6FB",
  panel: "#F8FAFD",
  muted: "#687086",
  line: "#E3E7F0",
  green: "#218B4B",
  amber: "#C47A1B",
  white: "#FFFFFF",
};
const FONT = "Heiti SC";
const PAGE = { left: 68, top: 46, width: 1144, height: 624 };

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
  addText(slide, String(index + 1).padStart(2, "0"), { left: PAGE.left, top: 31, width: 70, height: 22 }, { fontSize: 12, bold: true, color: C.violet });
  addText(slide, data.project.title, { left: 908, top: 31, width: 304, height: 22 }, { fontSize: 10, color: C.muted, alignment: "right" });
  addRule(slide, PAGE.left, 64, PAGE.width, C.line);
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
  addRule(slide, PAGE.left, 666, PAGE.width);
  addText(slide, sourceText, { left: PAGE.left, top: 673, width: 980, height: 22 }, { fontSize: 9, color: C.muted });
  addText(slide, `${index + 1} / ${data.slides.length}`, { left: 1080, top: 673, width: 132, height: 22 }, { fontSize: 10, color: C.muted, alignment: "right" });
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

async function buildCover(slide, item, image) {
  slide.background.fill = C.white;
  addRect(slide, { left: 0, top: 0, width: 1280, height: 720 }, C.white, C.white);
  addRect(slide, { left: 0, top: 0, width: 1280, height: 14 }, C.navy, C.navy);
  addText(slide, "PPTKILLER / CONSULTING DECK", { left: 76, top: 76, width: 430, height: 24 }, { fontSize: 12, bold: true, color: C.violet });
  addText(slide, item.title, { left: 76, top: 178, width: image ? 610 : 1000, height: 168 }, { fontSize: 50, bold: true, color: C.ink }, "deck-title");
  addText(slide, data.project.topic || item.key_message || "", { left: 78, top: 368, width: image ? 560 : 900, height: 92 }, { fontSize: 20, color: C.muted });
  addRule(slide, 78, 514, 112, C.violet, 4);
  addText(slide, `${data.project.slide_count} 页 · ${data.project.speaker_notes_enabled ? "含演讲稿" : "不含演讲稿"}`, { left: 78, top: 540, width: 430, height: 26 }, { fontSize: 13, color: C.muted });
  if (image) {
    addRect(slide, { left: 760, top: 78, width: 420, height: 520 }, C.pale, C.pale, 10);
    slide.images.add({ blob: image, contentType: item.image_content_type || "image/jpeg", alt: item.image_alt || item.title, fit: "cover", position: { left: 760, top: 78, width: 420, height: 520 }, geometry: "roundRect", borderRadius: 10 });
  }
}

async function buildImageSplit(slide, item, image, index) {
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 96, width: 560, height: 94 }, { fontSize: 42, bold: true });
  addText(slide, item.key_message || "", { left: PAGE.left, top: 202, width: 520, height: 76 }, { fontSize: 21, color: C.violet, bold: true });
  addBullets(slide, item.bullets, { left: PAGE.left, top: 298, width: 520, height: 290 }, { fontSize: 20, max: 5 });
  if (image) {
    slide.images.add({ blob: image, contentType: item.image_content_type || "image/jpeg", alt: item.image_alt || item.title, fit: "cover", position: { left: 674, top: 94, width: 538, height: 520 }, geometry: "roundRect", borderRadius: 10 });
  } else {
    addRect(slide, { left: 674, top: 94, width: 538, height: 520 }, C.pale, C.pale);
    addText(slide, item.image_query || "Visual evidence", { left: 740, top: 326, width: 405, height: 60 }, { fontSize: 24, color: C.muted, alignment: "center" });
  }
  addFooter(slide, item, index);
}

function buildStatement(slide, item, index) {
  slide.background.fill = C.navy;
  addText(slide, String(index + 1).padStart(2, "0"), { left: 74, top: 46, width: 70, height: 25 }, { fontSize: 14, color: "#BFC5EA", bold: true });
  addText(slide, item.title, { left: 110, top: 170, width: 1060, height: 120 }, { fontSize: 44, bold: true, color: C.white, alignment: "center" });
  addText(slide, item.key_message || item.bullets?.[0] || "", { left: 150, top: 320, width: 980, height: 150 }, { fontSize: 34, color: C.white, alignment: "center" });
  addRule(slide, 560, 520, 160, "#7566E4", 5);
  addText(slide, "核心观点", { left: 520, top: 542, width: 240, height: 28 }, { fontSize: 14, color: "#D8DAEE", alignment: "center" });
}

function buildTwoColumn(slide, item, index) {
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 90, width: 1040, height: 76 }, { fontSize: 40, bold: true });
  const leftTitle = item.left_title || "现状与机会";
  const rightTitle = item.right_title || "挑战与应对";
  addRect(slide, { left: PAGE.left, top: 196, width: 542, height: 410 }, C.panel, C.panel);
  addRect(slide, { left: 670, top: 196, width: 542, height: 410 }, C.white, C.line);
  addText(slide, leftTitle, { left: 98, top: 230, width: 440, height: 48 }, { fontSize: 25, bold: true, color: C.violet });
  addText(slide, rightTitle, { left: 700, top: 230, width: 440, height: 48 }, { fontSize: 25, bold: true, color: C.navy });
  addBullets(slide, item.left_bullets?.length ? item.left_bullets : (item.bullets || []).slice(0, 3), { left: 98, top: 300, width: 440, height: 250 }, { fontSize: 20, max: 4 });
  addBullets(slide, item.right_bullets?.length ? item.right_bullets : (item.bullets || []).slice(3), { left: 700, top: 300, width: 440, height: 250 }, { fontSize: 20, max: 4 });
  addFooter(slide, item, index);
}

function buildProcess(slide, item, index) {
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 92, width: 1000, height: 74 }, { fontSize: 40, bold: true });
  const steps = (item.process_steps?.length ? item.process_steps : item.bullets || []).slice(0, 5);
  const startX = 84;
  const gap = 22;
  const width = (1112 - gap * Math.max(steps.length - 1, 0)) / Math.max(steps.length, 1);
  steps.forEach((step, stepIndex) => {
    const x = startX + stepIndex * (width + gap);
    addText(slide, String(stepIndex + 1).padStart(2, "0"), { left: x, top: 220, width, height: 60 }, { fontSize: 38, bold: true, color: C.violet });
    addRule(slide, x, 292, width, stepIndex === steps.length - 1 ? C.violet : C.line, 3);
    addText(slide, step, { left: x, top: 320, width, height: 190 }, { fontSize: 18, bold: true });
  });
  addText(slide, item.key_message || "", { left: 84, top: 558, width: 1112, height: 56 }, { fontSize: 20, color: C.muted, alignment: "center" });
  addFooter(slide, item, index);
}

function buildArchitectureSlide(slide, item, index) {
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 88, width: 900, height: 52 }, { fontSize: 34, bold: true });
  addText(slide, item.key_message || item.visual_rationale || "用主链路说明模块、关系与反馈闭环", { left: PAGE.left, top: 146, width: 920, height: 40 }, { fontSize: 17, color: C.muted });
  addText(slide, item.diagram_title || "主链路架构", { left: PAGE.left, top: 214, width: 520, height: 28 }, { fontSize: 18, bold: true, color: C.violet });

  const modules = architectureModules(item);
  const gap = 18;
  const moduleWidth = (PAGE.width - gap * (modules.length - 1)) / Math.max(modules.length, 1);
  const top = 280;
  modules.forEach((module, moduleIndex) => {
    const left = PAGE.left + moduleIndex * (moduleWidth + gap);
    addRect(slide, { left, top, width: moduleWidth, height: 250 }, C.panel, C.line, 8);
    addText(slide, String(moduleIndex + 1).padStart(2, "0"), { left: left + 18, top: top + 18, width: 38, height: 20 }, { fontSize: 12, bold: true, color: C.violet });
    addText(slide, module.label, { left: left + 18, top: top + 46, width: moduleWidth - 36, height: 42 }, { fontSize: 17, bold: true, color: C.ink });
    (module.children || []).slice(0, 2).forEach((child, childIndex) => {
      const childTop = top + 112 + childIndex * 58;
      addRect(slide, { left: left + 16, top: childTop, width: moduleWidth - 32, height: 44 }, C.white, C.line, 6);
      addText(slide, child.label || child.detail || "", { left: left + 28, top: childTop + 10, width: moduleWidth - 56, height: 18 }, { fontSize: 11, bold: true, color: C.ink });
      if (child.detail) addText(slide, child.detail, { left: left + 28, top: childTop + 27, width: moduleWidth - 56, height: 13 }, { fontSize: 8, color: C.muted });
    });
    if (moduleIndex < modules.length - 1) {
      const x = left + moduleWidth + 4;
      addRule(slide, x, top + 126, gap - 8, C.violet, 2);
      addText(slide, "→", { left: x + gap - 18, top: top + 113, width: 20, height: 22 }, { fontSize: 16, bold: true, color: C.violet });
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
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 90, width: 900, height: 74 }, { fontSize: 40, bold: true });
  addRect(slide, { left: PAGE.left, top: 196, width: 760, height: 410 }, C.panel, C.panel);
  addText(slide, item.key_message || item.bullets?.[0] || "证据指向明确的行动窗口", { left: 104, top: 245, width: 690, height: 130 }, { fontSize: 34, bold: true });
  addBullets(slide, item.bullets?.slice(1), { left: 104, top: 410, width: 650, height: 150 }, { fontSize: 19, max: 3, color: C.muted });
  addText(slide, "引用来源", { left: 876, top: 210, width: 280, height: 34 }, { fontSize: 20, bold: true, color: C.violet });
  const citations = (item.citations || []).slice(0, 4);
  if (citations.length) {
    citations.forEach((citation, citationIndex) => {
      const y = 270 + citationIndex * 78;
      addText(slide, String(citationIndex + 1), { left: 876, top: y, width: 28, height: 30 }, { fontSize: 14, bold: true, color: C.violet });
      addText(slide, citation.title || citation.doi || citation.url, { left: 914, top: y, width: 282, height: 56 }, { fontSize: 14, color: C.ink });
    });
  } else {
    addText(slide, "本页结论来自用户资料与检索结果的综合归纳。正式交付前建议补充可核验来源。", { left: 876, top: 270, width: 300, height: 150 }, { fontSize: 16, color: C.muted });
  }
  addFooter(slide, item, index);
}

function buildDataSlide(slide, item, index) {
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 88, width: 780, height: 62 }, { fontSize: 38, bold: true });
  addText(slide, item.key_message || "数据支撑核心判断", { left: PAGE.left, top: 154, width: 850, height: 46 }, { fontSize: 18, color: C.muted });
  const chartType = item.chart_type || "table";
  if (chartType === "table") buildDataTable(slide, item);
  else if (chartType === "kpi") buildKpis(slide, item);
  else buildChart(slide, item, chartType);
  const source = item.data_source ? `数据来源：${item.data_source.filename || ""}${item.data_source.sheet ? ` / ${item.data_source.sheet}` : ""}` : "";
  addText(slide, source, { left: PAGE.left, top: 628, width: 720, height: 24 }, { fontSize: 11, color: C.muted });
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
        addRule(slide, Math.min(prevX, x), Math.min(prevY, y), Math.hypot(x - prevX, y - prevY), C.violet, 3);
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
      addRect(slide, { left: x, top: y, width: barWidth, height: barHeight }, C.violet, C.violet, 4);
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
  addRect(slide, { left, top, width: 1030, height: 36 }, C.navy, C.navy);
  headers.forEach((header, index) => addText(slide, header, { left: left + index * colWidth + 10, top: top + 9, width: colWidth - 20, height: 20 }, { fontSize: 12, color: C.white, bold: true }));
  rows.forEach((row, rowIndex) => {
    const y = top + 36 + rowIndex * 42;
    addRect(slide, { left, top: y, width: 1030, height: 42 }, rowIndex % 2 ? C.white : C.panel, C.line);
    headers.forEach((_, colIndex) => addText(slide, row[colIndex] || "", { left: left + colIndex * colWidth + 10, top: y + 12, width: colWidth - 20, height: 20 }, { fontSize: 11, color: C.ink }));
  });
}

function buildKpis(slide, item, box = { left: PAGE.left, top: 238, width: PAGE.width }) {
  const kpis = (item.kpis || []).slice(0, 4);
  if (!kpis.length) return;
  const cardWidth = box.width / kpis.length - 12;
  kpis.forEach((kpi, index) => {
    const x = box.left + index * (cardWidth + 12);
    addRect(slide, { left: x, top: box.top, width: cardWidth, height: 112 }, C.panel, C.line, 8);
    addText(slide, kpi.label, { left: x + 18, top: box.top + 18, width: cardWidth - 36, height: 24 }, { fontSize: 12, color: C.muted });
    addText(slide, kpi.value, { left: x + 18, top: box.top + 50, width: cardWidth - 36, height: 40 }, { fontSize: 30, bold: true, color: C.violet });
  });
}

function buildSummary(slide, item, index) {
  slide.background.fill = C.white;
  addHeader(slide, item, index);
  addText(slide, item.title, { left: PAGE.left, top: 96, width: 950, height: 90 }, { fontSize: 44, bold: true });
  const bullets = (item.bullets || []).slice(0, 4);
  bullets.forEach((bullet, bulletIndex) => {
    const top = 220 + bulletIndex * 92;
    addText(slide, `0${bulletIndex + 1}`, { left: 82, top, width: 70, height: 48 }, { fontSize: 26, bold: true, color: C.violet });
    addText(slide, bullet, { left: 170, top, width: 950, height: 64 }, { fontSize: 24, bold: true });
    addRule(slide, 170, top + 72, 950);
  });
  addText(slide, item.key_message || "从洞察走向行动", { left: 172, top: 590, width: 940, height: 44 }, { fontSize: 20, color: C.muted });
  addFooter(slide, item, index);
}

for (const [index, item] of data.slides.entries()) {
  const slide = deck.slides.add();
  const image = await imageBytes(item.image_path);
  const layout = index === 0 ? "cover" : item.layout || item.type || "content";
  if (layout === "cover") await buildCover(slide, item, image);
  else if (layout === "image_split" || (layout === "case" && image)) await buildImageSplit(slide, item, image, index);
  else if (layout === "statement") buildStatement(slide, item, index);
  else if (layout === "two_column") buildTwoColumn(slide, item, index);
  else if (layout === "process") buildProcess(slide, item, index);
  else if (layout === "architecture") buildArchitectureSlide(slide, item, index);
  else if (layout === "data") buildDataSlide(slide, item, index);
  else if (layout === "evidence") buildEvidence(slide, item, index);
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
