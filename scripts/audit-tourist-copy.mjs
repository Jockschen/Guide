import { readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const files = [
  path.join(root, "components", "TouristExperience.tsx"),
  path.join(root, "components", "DigitalHuman.tsx"),
  path.join(root, "components", "ItineraryPanel.tsx")
];

const forbiddenTerms = [
  "ASR", "TTS", "Qwen", "Vivo", "Provider", "provider", "mock",
  "OpenTalking", "QuickTalk", "WebRTC", "session", "模型 ID", "API Key",
  "生成口型中", "同步口型讲解", "口型链路异常", "口型视频生成失败",
  "讲解准备中", "正在为你讲解", "正在整理资料", "正在查找本地资料",
  "正在整理景区问答", "正在为你准备讲解", "正在为你整理景点信息",
  "正在播报", "正在识别"
];

function extractVisibleCandidates(source) {
  const candidates = [];

  for (const match of source.matchAll(/>\s*([^<>{}\n][^<>{}]*)\s*</g)) {
    const text = match[1].trim();
    if (text) candidates.push(text);
  }

  for (const match of source.matchAll(/\b(?:title|placeholder|aria-label|alt)=["']([^"']+)["']/g)) {
    candidates.push(match[1].trim());
  }

  for (const match of source.matchAll(/(?:setSubtitle|setStatusLabel|setQuestion|useState)\(\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']/g)) {
    candidates.push(match[1].trim());
  }

  for (const match of source.matchAll(/["']([^"']*[\u4e00-\u9fff][^"']*)["']/g)) {
    const text = match[1].trim();
    if (text && !text.includes("source_file") && !text.startsWith("/api/")) candidates.push(text);
  }

  return [...new Set(candidates)].filter(Boolean);
}

const violations = [];

for (const file of files) {
  const source = readFileSync(file, "utf-8");
  for (const text of extractVisibleCandidates(source)) {
    for (const term of forbiddenTerms) {
      if (text.includes(term)) {
        violations.push({ file: path.relative(root, file), term, text });
      }
    }
  }
}

if (violations.length > 0) {
  console.error("游客端可见文案包含技术细节：");
  for (const item of violations) {
    console.error(`- ${item.file}: [${item.term}] ${item.text}`);
  }
  process.exit(1);
}

console.log("tourist copy audit passed");
