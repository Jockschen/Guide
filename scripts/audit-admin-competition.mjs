import { readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const admin = readFileSync(path.join(root, "components", "AdminConsole.tsx"), "utf-8");
const panels = readFileSync(path.join(root, "components", "admin", "CompetitionPanels.tsx"), "utf-8");
const charts = readFileSync(path.join(root, "components", "MiniCharts.tsx"), "utf-8");
const css = readFileSync(path.join(root, "app", "globals.css"), "utf-8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

for (const label of ["运营概览", "知识内容", "数字人形象", "游客感受", "质量报告"]) {
  assert(admin.includes(label), `管理端缺少一级区域：${label}`);
}

assert(admin.includes('role="tablist"') && admin.includes('role="tab"') && admin.includes('role="tabpanel"'), "管理端一级导航缺少标签页语义。");
assert(admin.includes("/api/admin/competition/overview"), "管理端未读取比赛运营概览。");
assert(admin.includes('apiGet<DashboardMetrics | null>("/api/admin/dashboard")'), "运营概览成功时未同步加载实时问答和景点分布，图表会长期为空。");
assert(admin.includes("/api/admin/competition/knowledge/documents"), "知识内容未接入 CRUD 接口。");
assert(admin.includes("/reindex"), "知识内容缺少单条重新索引操作。");
assert(admin.includes("rebuildAllKnowledgeIndexes") && panels.includes("全部更新"), "知识内容缺少基础资料与运营知识的一键更新入口。");
assert(admin.includes('method: "PUT"') && admin.includes('method: "DELETE"'), "知识内容缺少真实编辑或删除请求。");
assert(admin.includes("/api/admin/competition/digital-human/profiles"), "数字人形象未读取或创建版本化配置。");
assert(admin.includes("/api/admin/competition/digital-human/active"), "首次启动无版本记录时，管理端没有显示当前生效的兼容形象。");
assert(!panels.includes("新建形象") && !panels.includes("profile-list"), "数字人设置仍暴露多版本/多形象操作，不符合单形象简化要求。");
assert(panels.includes("上传形象照片") && panels.includes("保存并应用"), "数字人设置缺少单形象上传与一步应用入口。");
for (const technicalCopy of ["配置键", "OpenTalking Avatar ID", "OpenTalking 预热状态", "驱动方案", "授权源视频地址"]) {
  assert(!panels.includes(technicalCopy), `数字人主界面仍向运营人员暴露技术字段：${technicalCopy}`);
}
assert(admin.includes("/voice-preview") && admin.includes("/preview") && admin.includes("/publish"), "数字人形象缺少声音试听、预览或发布调用。");
assert(admin.includes("/api/admin/competition/assets"), "数字人形象未接入真实素材上传接口。");
for (const field of ['formData.append("asset_kind"', 'formData.append("file"', 'formData.append("prepare_avatar"']) {
  assert(admin.includes(field), `数字人素材上传缺少 multipart 字段：${field}`);
}
assert(admin.includes('kind === "avatar_image" || kind === "neutral_source_video"'), "上传形象照片未触发 OpenTalking 形象准备，游客端不会真正更换动态形象。");
assert(!admin.includes("请先保存草稿，再试听声音"), "声音试听仍要求先保存版本，操作步骤过多。");
assert(panels.includes("normalizeProfileForEditor") && panels.includes('["gentle", "calm", "bright"]'), "旧配置的声音值未在简化编辑器中转换，声音下拉框可能显示为空。");
assert(panels.includes("服装风格") || panels.includes("文化风格"), "数字人设置缺少可见的服装/文化风格配置。");
assert(panels.includes("value={draft.clothing_version") && panels.includes("clothing_version: event.target.value"), "服装风格未作为 draft.clothing_version 受控选择项。");
for (const preset of ["灵山墨蓝雅韵", "梵宫朱砂礼仪", "太湖素雅禅意"]) {
  assert(panels.includes(preset), `数字人缺少景区文化风格预设：${preset}`);
}
assert(panels.includes("当前文化风格") && panels.includes("draft.clothing_version"), "数人预览未显示当前文化风格。");
assert(panels.includes("still_image_fallback") && panels.includes('driver_provider: "opentalking"'), "数字人草稿默认值与后端契约不一致。");
assert(!panels.includes('driver_provider: "session"') && !panels.includes('"neutral_motion"') && !panels.includes('"still_fallback"'), "数字人编辑器仍包含已废弃的枚举值。");
assert(admin.includes("/api/admin/competition/feedback"), "游客感受未接入文字反馈列表。");
assert(admin.includes('method: "PATCH"') && admin.includes("management_note"), "游客反馈缺少处理状态和管理备注闭环。");
assert(admin.includes("/api/admin/competition/quality-runs/latest") && admin.includes("/api/admin/competition/quality-runs"), "质量报告未接入最新与历史运行数据。");
assert(admin.includes("/api/admin/competition/quality-runs/run"), "运行本地自测仍在复制历史记录，未触发真实冻结问答集评测。");
assert(admin.includes("/api/admin/competition/quality-runs/e2e-latency/latest"), "管理端未分开读取问答回归耗时与问答到 WebRTC 首帧端到端报告。");
assert(panels.includes("回答用时") && panels.includes("从提问到数字人画面"), "质量页未用运营人员能理解的中文区分回答耗时与数字人画面。");
assert(panels.includes("official_evaluation") && panels.includes("本地自测"), "质量报告未区分本地自测和官方评审。");
assert(panels.includes("本次自测如何计算") && panels.includes("正确题数 ÷ 总题数"), "准确率页面没有用中文解释数据集、判定规则和计算方法。");
assert(panels.includes('className="quality-method-steps"'), "自测方法未使用紧凑三步结构。");
for (const label of ["题集", "判定", "结果用途"]) {
  assert(panels.includes(`<b>${label}</b>`), `自测方法缺少 ${label}。`);
}
assert(!panels.includes('<details className="quality-method"'), "自测方法仍是展开式大卡。");
assert(css.includes(".quality-method-steps"), "紧凑自测步骤缺少样式。");
assert(!panels.includes("JSON.stringify(latest.environment)"), "质量页仍直接展示运行环境 JSON 技术文本。");
assert(!panels.includes("<h3>{latest.dataset_version}</h3>") && !panels.includes("WebRTC 首帧"), "质量页仍向运营人员展示数据集标识或 WebRTC 等技术术语。");
assert(admin.includes("source_name") && !admin.includes("source_type: \"manual\""), "知识内容创建字段与后端 source_name 契约不一致。");
assert(panels.includes("今日服务人次") && panels.includes("本周服务人次"), "运营概览未展示今日与本周服务人次。");
assert(panels.includes("dashboard?.live_hot_questions") && panels.includes("<h3>热门问答</h3>"), "热门问答未使用实时重复原始问题。");
assert(!panels.includes("dashboard?.live_spot_distribution"), "热门问答仍在使用景点分布代替真实问题。");
assert(panels.includes("实时交互数据"), "实时运营指标丢失数据来源标识。");
assert(panels.includes("document_kind") && panels.includes("editable"), "本地资料包与可编辑运营知识没有在界面上区分。");
assert(panels.includes("景区资料包") && panels.includes("chunk_count"), "知识管理未展示本地三份资料及其真实整理状态。");
assert(panels.includes("游客数据表") && panels.includes("records_count"), "本地 XLSX 游客数据仍被误显示为普通问答资料。");
for (const technicalCopy of ["重建全部索引", "重新索引", "个检索分片", "P95 问答", "冻结问答集", "端到端耗时"]) {
  assert(!panels.includes(technicalCopy) && !admin.includes(technicalCopy), `管理端仍暴露不必要的技术文案：${technicalCopy}`);
}
assert(panels.includes("更新问答依据") && panels.includes("已整理") && panels.includes("段内容"), "知识资料操作仍未改成运营人员容易理解的中文。");
assert(panels.includes("较慢问答（95%）") && panels.includes("完整响应时间"), "质量报告仍未用通俗中文解释速度指标。");
assert(panels.includes('item.sentiment === "positive"'), "情感标记仍使用中文旧值，未匹配后端 positive/neutral/negative 契约。");
assert(panels.includes("分析方式") && panels.includes("大模型分析") && panels.includes("sentiment_confidence"), "游客感受页未展示情感分类来源与置信度。");
assert(admin.includes("实时交互数据") && admin.includes("示例景区数据") && admin.includes("本地自测数据"), "数据看板缺少来源标识。");
assert(charts.includes('role="img"') && charts.includes("aria-label"), "管理图表缺少无障碍名称。");
assert(charts.includes('viewBox="0 0 600 180"'), "服务趋势图未使用适配宽屏卡片的横向坐标系，图形会缩在中间或被压扁。");
assert(!charts.includes("linearGradient"), "管理图表仍使用视觉渐变。");
assert(css.includes(".admin-shell") && css.includes("min-height: 44px"), "管理端缺少基础壳层或 44 像素触控目标。");
assert(admin.includes("/assets/generated/app-icon-v2.png"), "管理端仍在使用旧品牌图标。");
assert(panels.includes("/assets/generated/operations-lingshan-v2.png"), "管理端概览仍在使用不符合景区运营语境的科幻图片。");

console.log("admin competition audit passed");
