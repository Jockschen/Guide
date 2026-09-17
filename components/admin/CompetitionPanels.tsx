"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  FilePenLine,
  FileText,
  Headphones,
  MessageSquareText,
  RefreshCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
  Users
} from "lucide-react";
import type { DashboardMetrics, Health } from "@/lib/types";
import { BarList, DonutChart, LineTrend } from "../MiniCharts";

export type CompetitionOverview = {
  digital_human?: Record<string, unknown>;
  knowledge?: Record<string, number | string>;
  feedback?: Record<string, number | string>;
  quality?: Record<string, number | string | boolean | null>;
  provenance?: string[] | Record<string, string>;
  today_questions?: number;
  active_visitors?: number;
  average_rating?: number | null;
};

export type KnowledgeDocument = {
  id: number | string;
  title?: string;
  name?: string;
  content?: string;
  source_name?: string;
  source_type?: string;
  status?: string;
  content_version?: number;
  index_version?: number;
  index_status?: string;
  updated_at?: string;
  document_kind?: "source_file" | "managed_document";
  editable?: boolean;
  file_type?: string;
  records_count?: number;
  chunk_count?: number;
};

export type DigitalHumanDriverProvider = "opentalking" | "flashtalk" | "flashhead" | "legacy_mp4" | "audio_only";
export type SourceVideoKind = "real_source_video" | "still_image_fallback";
export type PrewarmStatus = "pending" | "ready" | "failed" | "unavailable";
export type DigitalHumanAssetKind = "avatar_image" | "clothing_image" | "neutral_source_video";

export type DigitalHumanProfile = {
  id?: number;
  profile_key: string;
  name: string;
  persona: string;
  driver_provider: DigitalHumanDriverProvider;
  avatar_asset_url: string;
  clothing_asset_url?: string;
  clothing_version?: string;
  voice: string;
  source_video_url?: string;
  source_video_kind?: SourceVideoKind;
  opentalking_avatar_id?: string;
  prewarm_status?: PrewarmStatus;
  version?: number;
  status?: string;
  is_active?: boolean;
};

export type DigitalHumanAssetResult = {
  asset_kind: DigitalHumanAssetKind;
  url: string;
  source_video_kind: SourceVideoKind;
  opentalking_avatar_id?: string;
  prewarm_status?: PrewarmStatus;
  prewarm_message?: string;
};

export type VisitorFeedback = {
  id: number;
  log_id?: number | null;
  rating?: number | null;
  text: string;
  sentiment?: string;
  sentiment_source?: "manual" | "qwen" | "rating" | "rules";
  sentiment_confidence?: number | null;
  topics?: string[];
  status?: string;
  recommendation?: string;
  management_note?: string;
  created_at?: string;
};

export type QualityRun = {
  id?: number;
  dataset_version: string;
  accuracy: number;
  sample_count: number;
  passed_count: number;
  sample_details?: Array<{
    id?: string;
    question?: string;
    answer?: string;
    passed?: boolean;
    facts_passed?: boolean;
    source_passed?: boolean;
  }>;
  latency_ms?: Record<string, number>;
  environment?: string | Record<string, unknown>;
  official_evaluation: boolean;
  official_evidence_reference?: string;
  scope_label?: string;
  created_at?: string;
};

export type E2ELatencyReport = {
  kind: "end_to_end_latency";
  scope_label: string;
  official_evaluation: false;
  timings_ms: Record<string, number>;
  measured_total_ms: number;
  target_ms: number;
  measurement_complete: boolean;
  within_target: boolean;
  generated_at?: string;
  tts_audio_ready?: boolean;
};

export function OverviewPanel({
  overview,
  dashboard,
  health,
  onOpen
}: {
  overview: CompetitionOverview | null;
  dashboard: DashboardMetrics | null;
  health: Health | null;
  onOpen: (area: "knowledge" | "digital-human" | "feedback" | "quality") => void;
}) {
  const todayQuestions = Number(dashboard?.today_questions ?? overview?.today_questions ?? 0);
  const todayVisitors = Number(dashboard?.today_visitors ?? overview?.active_visitors ?? 0);
  const weekQuestions = Number(dashboard?.week_questions ?? dashboard?.live_questions ?? 0);
  const weekVisitors = Number(dashboard?.week_visitors ?? dashboard?.live_visitors ?? 0);
  const rating = Number(overview?.average_rating ?? dashboard?.live_average_rating ?? 0);
  const indexed = Number(overview?.knowledge?.indexed ?? overview?.knowledge?.documents ?? health?.counts?.chunks ?? 0);
  const trend = dashboard?.live_date_distribution?.length ? dashboard.live_date_distribution : dashboard?.monthly_visits || [];
  const hotQuestions = dashboard?.live_hot_questions || [];
  return (
    <div className="admin-area overview-area">
      <section className="admin-editorial-hero">
        <div>
          <span>今日运营脉搏</span>
          <h2>让每一次问答，都能回到真实服务</h2>
          <p>从游客提问、知识更新到数字人发布，所有关键状态集中在一处。</p>
          <div className="provenance-row" aria-label="数据来源">
            {["实时交互数据", "示例景区数据", "本地自测数据"].map((label) => <span key={label}>{label}</span>)}
          </div>
        </div>
        <img src="/assets/generated/operations-lingshan-v2.png" alt="灵山景区运营服务空间" />
      </section>

      <section className="metric-ribbon" aria-label="运营关键指标">
        <Metric icon={<Users size={20} />} label="今日服务人次" value={todayVisitors.toLocaleString("zh-CN")} note={`实时交互数据 · ${todayQuestions.toLocaleString("zh-CN")} 次问答`} />
        <Metric icon={<MessageSquareText size={20} />} label="本周服务人次" value={weekVisitors.toLocaleString("zh-CN")} note={`实时交互数据 · ${weekQuestions.toLocaleString("zh-CN")} 次问答`} />
        <Metric icon={<Sparkles size={20} />} label="平均满意度" value={rating ? `${rating.toFixed(1)} / 5` : "待积累"} note="游客反馈" />
        <Metric icon={<BookOpen size={20} />} label="已索引内容" value={indexed.toLocaleString("zh-CN")} note="知识内容" />
      </section>

      <section className="overview-grid">
        <div className="analytics-block">
          <header><div><span>实时交互数据</span><h3>服务趋势</h3></div><button type="button" onClick={() => onOpen("feedback")}>查看感受 <ChevronRight size={17} /></button></header>
          <LineTrend data={trend} tall />
        </div>
        <div className="analytics-block">
          <header><div><span>实时交互数据</span><h3>热门问答</h3></div><button type="button" onClick={() => onOpen("knowledge")}>维护内容 <ChevronRight size={17} /></button></header>
          <BarList data={hotQuestions} />
        </div>
      </section>

      <section className="operation-links" aria-label="快捷运营入口">
        <button type="button" onClick={() => onOpen("digital-human")}><UserRound size={22} /><span><b>数字人形象</b><small>检查当前发布版本与声音</small></span><ChevronRight size={19} /></button>
        <button type="button" onClick={() => onOpen("knowledge")}><FilePenLine size={22} /><span><b>知识内容</b><small>维护景区资料与问答依据</small></span><ChevronRight size={19} /></button>
        <button type="button" onClick={() => onOpen("quality")}><ShieldCheck size={22} /><span><b>质量报告</b><small>查看固定题集与完整响应时间</small></span><ChevronRight size={19} /></button>
      </section>
    </div>
  );
}

function Metric({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note: string }) {
  return <article><span>{icon}</span><div><small>{label}</small><strong>{value}</strong><em>{note}</em></div></article>;
}

export function KnowledgePanel({
  documents,
  busy,
  onCreate,
  onUpdate,
  onDelete,
  onReindex,
  onRebuild,
  onUpload
}: {
  documents: KnowledgeDocument[];
  busy: boolean;
  onCreate: (value: { title: string; content: string; source_name: string }) => Promise<void>;
  onUpdate: (id: KnowledgeDocument["id"], value: { title: string; content: string }) => Promise<void>;
  onDelete: (id: KnowledgeDocument["id"]) => Promise<void>;
  onReindex: (id: KnowledgeDocument["id"]) => Promise<void>;
  onRebuild: () => Promise<void>;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  const [selectedId, setSelectedId] = useState<KnowledgeDocument["id"] | null>(documents[0]?.id ?? null);
  const selected = documents.find((document) => document.id === selectedId) || documents[0] || null;
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const selectedEditable = selected?.editable !== false;
  useEffect(() => {
    setDraftTitle(selected?.title || selected?.name || "");
    setDraftContent(selected?.content || "");
    if (selected && selectedId === null) setSelectedId(selected.id);
  }, [selected?.id, selected?.title, selected?.name, selected?.content, selectedId]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draftTitle.trim() || !draftContent.trim()) return;
    await onCreate({ title: draftTitle.trim(), content: draftContent.trim(), source_name: "运营维护" });
    setNewOpen(false);
  }

  return (
    <div className="admin-area knowledge-area">
      <header className="area-intro"><div><span>内容即服务</span><h2>景区资料管理</h2><p>查看本地资料，补充或修改景区内容；保存后系统会自动更新问答依据。</p></div><div className="area-actions"><button className="secondary-action" type="button" disabled={busy} onClick={() => void onRebuild()}><RefreshCcw size={18} />全部更新</button><label className="secondary-action"><Upload size={18} />导入资料<input type="file" multiple accept=".docx,.xlsx,.pdf,.txt,.md,.csv" disabled={busy} onChange={onUpload} /></label><button className="primary-action" type="button" disabled={busy} onClick={() => { setNewOpen(true); setSelectedId(null); setDraftTitle(""); setDraftContent(""); }}><FileText size={18} />补充内容</button></div></header>
      <div className="knowledge-layout">
        <section className="document-list" aria-label="知识文档列表">
          <div className="list-heading"><b>{documents.length} 份资料</b><span>问答依据</span></div>
          {documents.length ? documents.map((document) => {
            const indexed = ["ready", "indexed"].includes(document.index_status || "");
            const isOperationalDataset = document.document_kind === "source_file" && Boolean(document.records_count);
            const sourceDetail = isOperationalDataset
              ? `游客数据表 · ${(document.records_count || 0).toLocaleString("zh-CN")} 条记录`
              : `景区资料包 · 已整理 ${document.chunk_count ?? 0} 段内容`;
            return (
              <button className={selected?.id === document.id && !newOpen ? "active" : ""} key={document.id} type="button" onClick={() => { setNewOpen(false); setSelectedId(document.id); }}>
                <FileText size={20} />
                <span><b>{document.title || document.name || `内容 ${document.id}`}</b><small>{document.document_kind === "source_file" ? sourceDetail : `第 ${document.content_version ?? 1} 版 · ${indexed ? "问答依据已更新" : "等待更新"}`}</small></span>
                <em className={`status-label ${indexed ? "success" : ""}`}>{indexed ? (isOperationalDataset ? "已载入" : "可用于问答") : "等待更新"}</em>
              </button>
            );
          }) : <div className="empty-state"><BookOpen size={28} /><p>还没有可编辑的知识内容。</p></div>}
        </section>
        <form className="knowledge-editor" onSubmit={newOpen ? create : (event) => { event.preventDefault(); if (selected && selectedEditable) void onUpdate(selected.id, { title: draftTitle, content: draftContent }); }}>
          <header><div><span>{newOpen ? "补充内容" : selected?.document_kind === "source_file" ? "本地资料" : "内容编辑"}</span><h3>{newOpen ? "添加景区内容" : selected?.title || selected?.name || "选择一份资料"}</h3></div>{selected && !newOpen ? <span className="version-badge">{selected.document_kind === "source_file" ? "本地只读资料" : ["ready", "indexed"].includes(selected.index_status || "") ? "问答依据已更新" : "等待更新"}</span> : null}</header>
          <label>标题<input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} disabled={!newOpen && (!selected || !selectedEditable)} /></label>
          <label>正文<textarea value={draftContent} onChange={(event) => setDraftContent(event.target.value)} disabled={!newOpen && (!selected || !selectedEditable)} rows={14} placeholder="输入由景区资料确认的内容" /></label>
          <footer>
            {selected && !newOpen && selectedEditable ? <><button className="danger-action" type="button" disabled={busy} onClick={() => { if (window.confirm("确定删除这份补充内容吗？")) void onDelete(selected.id); }}><Trash2 size={18} />删除</button><button className="secondary-action" type="button" disabled={busy} onClick={() => void onReindex(selected.id)}><RefreshCcw size={18} />更新问答依据</button></> : selected?.document_kind === "source_file" && !newOpen ? <span className="source-readonly-note">导入资料或点击“全部更新”后自动同步</span> : <span />}
            {newOpen || selectedEditable ? <button className="primary-action" type="submit" disabled={busy || !draftTitle.trim() || !draftContent.trim()}><Save size={18} />{newOpen ? "创建内容" : "保存修改"}</button> : null}
          </footer>
        </form>
      </div>
    </div>
  );
}

const CULTURAL_STYLE_PRESETS = ["灵山墨蓝雅韵", "梵宫朱砂礼仪", "太湖素雅禅意"] as const;

export function DigitalHumanPanel({
  profiles,
  busy,
  previewMessage,
  onAssetUpload,
  onVoicePreview,
  onPublish
}: {
  profiles: DigitalHumanProfile[];
  busy: boolean;
  previewMessage: string;
  onAssetUpload: (kind: DigitalHumanAssetKind, file: File, profile: DigitalHumanProfile) => Promise<DigitalHumanAssetResult | undefined>;
  onVoicePreview: (profile: DigitalHumanProfile, text: string) => Promise<void>;
  onPublish: (profile: DigitalHumanProfile) => Promise<DigitalHumanProfile | undefined>;
}) {
  const selected = profiles.find((profile) => profile.is_active) || profiles[0];
  const emptyProfile: DigitalHumanProfile = { profile_key: "lingjing-guide", name: "灵境导游", persona: "温柔、准确、熟悉景区的数字人导游", driver_provider: "opentalking", avatar_asset_url: "/assets/generated/avatar-guide-v2.png", voice: "gentle", clothing_version: CULTURAL_STYLE_PRESETS[0], source_video_kind: "still_image_fallback", prewarm_status: "unavailable", status: "draft" };
  const [draft, setDraft] = useState<DigitalHumanProfile>(selected ? normalizeProfileForEditor(selected) : emptyProfile);
  const [sampleText, setSampleText] = useState("欢迎来到灵山胜境，今天想先了解哪里？");
  const [assetMessage, setAssetMessage] = useState("");
  useEffect(() => { if (selected) setDraft(normalizeProfileForEditor(selected)); }, [selected?.id, selected?.version, selected?.avatar_asset_url]);

  async function publishDraft() {
    const published = await onPublish(draft);
    if (published) setDraft(published);
  }

  async function uploadAvatar(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setAssetMessage("正在上传照片并准备讲解形象，请稍候…");
    const uploaded = await onAssetUpload("avatar_image", file, draft);
    if (!uploaded) {
      setAssetMessage("照片没有上传成功，请换一张清晰的正面照片重试。");
      return;
    }
    setDraft((current) => ({
      ...current,
      avatar_asset_url: uploaded.url,
      opentalking_avatar_id: uploaded.opentalking_avatar_id || current.opentalking_avatar_id,
      prewarm_status: uploaded.prewarm_status || "pending",
      driver_provider: "opentalking",
      source_video_kind: "still_image_fallback"
    }));
    setAssetMessage(uploaded.prewarm_status === "ready" ? "新形象已经准备好，点击“保存并应用”即可更新游客端。" : "照片已上传，讲解形象仍在准备；可以稍后再点击保存并应用。");
  }

  return (
    <div className="admin-area digital-human-area">
      <header className="area-intro"><div><span>当前数字人</span><h2>形象与声音</h2><p>上传一张清晰正面照片，选择讲解声音，再点击保存并应用。其余准备工作由系统自动完成。</p></div></header>
      <div className="profile-layout single-profile-layout">
        <section className="profile-stage">
          <div className="profile-preview">
            <img src={draft.avatar_asset_url || "/assets/generated/avatar-guide-v2.png"} alt={`${draft.name}形象预览`} />
            <div><span className={draft.is_active ? "status-label success" : "status-label"}>{draft.is_active ? "当前已应用" : "修改待应用"}</span><h3>{draft.name}</h3><p>{draft.persona}</p><small>当前文化风格：{draft.clothing_version || CULTURAL_STYLE_PRESETS[0]}</small><small>游客端会使用这一形象和声音进行讲解。</small></div>
          </div>
          {previewMessage || assetMessage ? <div className="preview-notice" role="status">{assetMessage || previewMessage}</div> : null}
        </section>
        <form className="profile-editor simple-profile-editor" onSubmit={(event) => { event.preventDefault(); void publishDraft(); }}>
          <h3>导游设置</h3>
          <p className="editor-help">建议使用正面、光线均匀、嘴部无遮挡的半身照片。</p>
          <label className="avatar-upload-card"><Upload size={20} /><span><b>上传形象照片</b><small>支持 JPG、PNG、WEBP，上传后会自动准备讲解画面</small></span><input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" disabled={busy} onChange={(event) => void uploadAvatar(event)} /></label>
          <div className="field-grid"><label>显示名称<input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label>讲解声音<select value={draft.voice} onChange={(event) => setDraft({ ...draft, voice: event.target.value })}><option value="gentle">温暖女声</option><option value="calm">沉稳男声</option><option value="bright">活力女声</option></select></label></div>
          <label>服装风格<select value={draft.clothing_version || CULTURAL_STYLE_PRESETS[0]} onChange={(event) => setDraft({ ...draft, clothing_version: event.target.value })}>{CULTURAL_STYLE_PRESETS.map((preset) => <option key={preset} value={preset}>{preset}</option>)}</select></label>
          <label>导游风格<textarea required rows={4} value={draft.persona} onChange={(event) => setDraft({ ...draft, persona: event.target.value })} /></label>
          <label>试听内容<input value={sampleText} onChange={(event) => setSampleText(event.target.value)} /></label>
          <footer><button className="secondary-action" type="button" disabled={busy} onClick={() => void onVoicePreview(draft, sampleText)}><Headphones size={18} />试听声音</button><button className="primary-action" type="submit" disabled={busy}><CheckCircle2 size={18} />保存并应用</button></footer>
        </form>
      </div>
    </div>
  );
}

const EDITOR_VOICES = ["gentle", "calm", "bright"] as const;

function normalizeProfileForEditor(profile: DigitalHumanProfile): DigitalHumanProfile {
  return {
    ...profile,
    avatar_asset_url: profile.avatar_asset_url || "/assets/generated/avatar-guide-v2.png",
    voice: EDITOR_VOICES.includes(profile.voice as typeof EDITOR_VOICES[number]) ? profile.voice : "gentle",
    clothing_version: CULTURAL_STYLE_PRESETS.includes(profile.clothing_version as typeof CULTURAL_STYLE_PRESETS[number]) ? profile.clothing_version : CULTURAL_STYLE_PRESETS[0]
  };
}

export function FeedbackPanel({ feedback, busy, onUpdate }: { feedback: VisitorFeedback[]; busy: boolean; onUpdate: (id: number, value: Partial<VisitorFeedback>) => Promise<void> }) {
  const [selectedId, setSelectedId] = useState(feedback[0]?.id || 0);
  const selected = feedback.find((item) => item.id === selectedId) || feedback[0];
  const [note, setNote] = useState("");
  const [recommendation, setRecommendation] = useState("");
  useEffect(() => { setNote(selected?.management_note || ""); setRecommendation(selected?.recommendation || ""); }, [selected?.id, selected?.management_note, selected?.recommendation]);
  const statusLabel = (value?: string) => value === "resolved" ? "已解决" : value === "acknowledged" ? "跟进中" : "待处理";
  const topicLabel = (value?: string) => value === "other" ? "其他" : value || "未标注";
  const sentimentLabel = (value?: string) => value === "positive" ? "正向" : value === "negative" ? "负向" : value === "neutral" ? "中性" : "待分析";
  const sentimentSourceLabel = (value?: string) => value === "qwen" ? "大模型分析" : value === "rating" ? "星级判断" : value === "rules" ? "关键词规则" : value === "manual" ? "人工标注" : "未记录";
  const sentiments = useMemo(() => Object.entries(feedback.reduce<Record<string, number>>((acc, item) => { const key = sentimentLabel(item.sentiment); acc[key] = (acc[key] || 0) + 1; return acc; }, {})), [feedback]) as [string, number][];
  return (
    <div className="admin-area feedback-area">
      <header className="area-intro"><div><span>游客感受闭环</span><h2>从一条建议到一次改进</h2><p>查看文字反馈、情感趋势、服务建议和处理状态。</p></div><span className="source-badge">实时交互数据</span></header>
      <section className="feedback-summary"><div><h3>情感趋势</h3><DonutChart data={sentiments} /></div><div><h3>待处理事项</h3><strong>{feedback.filter((item) => !["resolved", "closed"].includes(item.status || "new")).length}</strong><p>优先查看低评分与明确服务建议。</p></div></section>
      <div className="feedback-layout">
        <section className="feedback-list" aria-label="游客反馈列表">
          {feedback.length ? feedback.map((item) => <button className={selected?.id === item.id ? "active" : ""} key={item.id} type="button" onClick={() => setSelectedId(item.id)}><span className={`sentiment-dot ${item.sentiment === "positive" ? "positive" : item.sentiment === "negative" || item.rating && item.rating <= 2 ? "negative" : ""}`} /><span><b>{item.text || "仅提交星级评价"}</b><small>{item.rating ? `${item.rating} 星` : "未评分"} · {sentimentLabel(item.sentiment)}</small></span><em>{item.status === "resolved" ? "已解决" : item.status === "acknowledged" ? "跟进中" : "待处理"}</em></button>) : <div className="empty-state"><MessageSquareText size={28} /><p>还没有游客文字反馈。</p></div>}
        </section>
        {selected ? <form className="feedback-detail" onSubmit={(event) => { event.preventDefault(); void onUpdate(selected.id, { status: "resolved", management_note: note, recommendation }); }}><header><div><span>反馈 第{selected.id}条</span><h3>{selected.text || "星级评价"}</h3></div><span className="status-label">{statusLabel(selected.status)}</span></header><dl><div><dt>情感</dt><dd>{sentimentLabel(selected.sentiment)}</dd></div><div><dt>分析方式</dt><dd>{sentimentSourceLabel(selected.sentiment_source)}{typeof selected.sentiment_confidence === "number" ? ` · ${Math.round(selected.sentiment_confidence * 100)}%` : ""}</dd></div><div><dt>关注点</dt><dd>{selected.topics?.map(topicLabel).join("、") || "未标注"}</dd></div><div><dt>时间</dt><dd>{selected.created_at ? new Date(selected.created_at).toLocaleString("zh-CN") : "暂无"}</dd></div></dl><label>服务建议<textarea rows={3} value={recommendation} onChange={(event) => setRecommendation(event.target.value)} placeholder="给一线服务的行动建议" /></label><label>管理备注<textarea rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录处理过程" /></label><footer><button className="secondary-action" type="button" disabled={busy} onClick={() => void onUpdate(selected.id, { status: "acknowledged", management_note: note, recommendation })}><CheckCircle2 size={18} />标记跟进</button><button className="primary-action" type="submit" disabled={busy}><ShieldCheck size={18} />完成处理</button></footer></form> : null}
      </div>
    </div>
  );
}

export function QualityPanel({ latest, e2eLatency, history, busy, onRun }: { latest: QualityRun | null; e2eLatency: E2ELatencyReport | null; history: QualityRun[]; busy: boolean; onRun: () => Promise<void> }) {
  const latencyNames: Record<string, string> = { average: "平均问答", median: "典型问答", p95: "较慢问答（95%）" };
  const e2eNames: Record<string, string> = { chat_ms: "生成回答", tts_ms: "生成语音", session_enqueue_ms: "准备讲解", first_frame_ms: "数字人画面" };
  const latencyPairs = Object.entries(latest?.latency_ms || {}).flatMap(([key, value]) => latencyNames[key] ? [[latencyNames[key], value] as [string, number]] : []);
  const e2ePairs = Object.entries(e2eLatency?.timings_ms || {}).flatMap(([key, value]) => e2eNames[key] ? [[e2eNames[key], value] as [string, number]] : []);
  const failedSamples = (latest?.sample_details || []).filter((item) => item.passed === false);
  const accuracy = latest ? latest.accuracy * (latest.accuracy <= 1 ? 100 : 1) : 0;
  return (
    <div className="admin-area quality-area">
      <header className="area-intro"><div><span>回答质量</span><h2>问答自测</h2><p>用固定的景区事实题检查回答是否完整、来源是否正确。这里展示的是本机自测，不等同于比赛官方成绩。</p></div><button className="primary-action" type="button" disabled={busy} onClick={() => void onRun()}><RefreshCcw size={18} />重新测试</button></header>
      {latest ? <>
        <section className="quality-verdict quality-verdict-readable">
          <div className="quality-score"><span>本次自测</span><strong>{accuracy.toFixed(1)}%</strong><small>{latest.sample_count} 题中答对 {latest.passed_count} 题</small></div>
          <div><span className={latest.official_evaluation ? "status-label success" : "status-label warning"}>{latest.official_evaluation ? "官方结果" : "本地自测"}</span><h3>固定景区知识问答</h3><p>每题必须同时包含要求的关键事实，并引用正确的本地资料，才计为答对。</p><small>计算方式：正确题数 ÷ 总题数 × 100%</small></div>
        </section>
        <section className="quality-method" aria-labelledby="quality-method-title">
          <header className="quality-method-head">
            <h3 id="quality-method-title">本次自测如何计算</h3>
            <p>三步说明本地结果的来源、判定和用途。</p>
          </header>
          <ol className="quality-method-steps">
            <li><span>01</span><div><b>题集</b><p>使用本地固定的 {latest.sample_count} 道景区事实题。</p></div></li>
            <li><span>02</span><div><b>判定</b><p>关键事实与资料来源都通过，才计为答对。</p></div></li>
            <li><span>03</span><div><b>结果用途</b><p>用于本机回归和改进；比赛成绩以官方评审为准。</p></div></li>
          </ol>
        </section>
        {failedSamples.length ? <section className="quality-failures"><header><div><span>下一步改进</span><h3>本次待改进 {failedSamples.length} 题</h3></div></header><ol>{failedSamples.map((item, index) => <li key={item.id || `${item.question}-${index}`}><span>{index + 1}</span><div><b>{item.question || "未命名问题"}</b><small>{item.facts_passed === false ? "回答缺少必备事实" : "资料来源需要核对"}</small></div></li>)}</ol></section> : <section className="quality-boundary success-boundary"><CheckCircle2 size={24} /><h3>本次题目全部通过</h3><p>仍建议保留人工抽查，并继续扩充官方验收题集。</p></section>}
        <section className="quality-grid"><div className="analytics-block"><header><div><span>单位：毫秒</span><h3>回答用时</h3></div><Clock3 size={20} /></header><BarList data={latencyPairs} /></div><div className="quality-boundary"><CircleAlert size={24} /><h3>结果边界</h3><p>这份自测只说明当前本机、当前资料和固定题集的表现，不替代比赛现场评测。</p></div></section>
      </> : <div className="empty-state large"><ShieldCheck size={34} /><h3>还没有自测结果</h3><p>点击“重新测试”，系统会逐题检查回答事实和资料来源。</p></div>}
      {e2eLatency ? <section className="quality-grid" aria-label="完整响应时间报告"><div className="analytics-block"><header><div><span>本机实测</span><h3>从提问到数字人画面</h3></div><span className={e2eLatency.measurement_complete && e2eLatency.within_target ? "status-label success" : "status-label warning"}>{!e2eLatency.measurement_complete ? "尚未测完" : e2eLatency.within_target ? "低于 5 秒" : "需要提速"}</span></header><BarList data={e2ePairs} /></div><div className="quality-score"><span>完整响应时间</span><strong>{(e2eLatency.measured_total_ms / 1000).toFixed(2)} 秒</strong><small>目标小于 {(e2eLatency.target_ms / 1000).toFixed(1)} 秒 · {e2eLatency.generated_at ? new Date(e2eLatency.generated_at).toLocaleString("zh-CN") : "时间未记录"}</small></div></section> : <section className="quality-boundary"><CircleAlert size={24} /><h3>完整响应时间还未测完</h3><p>系统会分别记录生成回答、生成语音、准备讲解和数字人画面出现的时间；缺少任一阶段都不会宣称达到 5 秒目标。</p></section>}
      <section className="quality-history"><h3>历史自测</h3><div role="table" aria-label="质量运行历史">{history.map((run, index) => <div role="row" key={run.id || `${run.dataset_version}-${index}`}><span role="cell"><b>{`第 ${history.length - index} 次自测`}</b><small>{run.official_evaluation ? "官方评审" : "本地固定题集"}</small></span><span role="cell">{(run.accuracy * (run.accuracy <= 1 ? 100 : 1)).toFixed(1)}%</span><span role="cell">答对 {run.passed_count}/{run.sample_count}</span><span role="cell">{run.created_at ? new Date(run.created_at).toLocaleString("zh-CN") : "暂无时间"}</span></div>)}</div></section>
    </div>
  );
}
