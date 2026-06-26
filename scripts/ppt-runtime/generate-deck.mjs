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
  navy: "#18256F",
  violet: "#5442D6",
  pale: "#F1F2F8",
  panel: "#F7F8FB",
  muted: "#687086",
  line: "#D9DDE8",
  green: "#218B4B",
  white: "#FFFFFF",
};
const FONT = "Arial";
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
  addText(slide, String(index + 1).padStart(2, "0"), { left: PAGE.left, top: 30, width: 70, height: 24 }, { fontSize: 14, bold: true, color: C.violet });
  addText(slide, data.project.title, { left: 970, top: 30, width: 242, height: 24 }, { fontSize: 11, color: C.muted, alignment: "right" });
  addRule(slide, PAGE.left, 64, PAGE.width);
}

function addFooter(slide, slideData, index) {
  const citations = (slideData.citations || []).slice(0, 2);
  let sourceText = citations.length
    ? citations.map((item) => item.doi || item.url || item.title).join("  ·  ")
    : "PPTKiller · AI generated, human approved";
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
  addRect(slide, { left: 0, top: 0, width: 20, height: 720 }, C.violet, C.violet);
  addText(slide, "PPTKILLER / PROFESSIONAL DECK", { left: 74, top: 72, width: 430, height: 28 }, { fontSize: 13, bold: true, color: C.violet });
  addText(slide, item.title, { left: 74, top: 184, width: image ? 590 : 1020, height: 180 }, { fontSize: 58, bold: true, color: C.ink }, "deck-title");
  addText(slide, data.project.topic || item.key_message || "", { left: 78, top: 390, width: image ? 560 : 930, height: 100 }, { fontSize: 24, color: C.muted });
  addRule(slide, 78, 536, 120, C.violet, 4);
  addText(slide, `${data.project.slide_count} 页 · ${data.project.speaker_notes_enabled ? "含演讲稿" : "不含演讲稿"}`, { left: 78, top: 558, width: 430, height: 28 }, { fontSize: 14, color: C.muted });
  if (image) {
    addRect(slide, { left: 760, top: 0, width: 520, height: 720 }, C.pale, C.pale);
    slide.images.add({ blob: image, contentType: item.image_content_type || "image/jpeg", alt: item.image_alt || item.title, fit: "cover", position: { left: 760, top: 0, width: 520, height: 720 } });
    addRect(slide, { left: 720, top: 0, width: 120, height: 720 }, C.navy, C.navy);
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
  else if (layout === "evidence" || layout === "data") buildEvidence(slide, item, index);
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
