"use client";

import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  BookOpen,
  ChevronLeft,
  Gauge,
  Menu,
  MessageSquareText,
  RefreshCcw,
  ShieldCheck,
  UserRound
} from "lucide-react";
import { API_BASE, apiGet, apiPost, apiUpload } from "@/lib/api";
import type { DashboardMetrics, Health, LogItem } from "@/lib/types";
import {
  DigitalHumanPanel,
  FeedbackPanel,
  KnowledgePanel,
  OverviewPanel,
  QualityPanel,
  type CompetitionOverview,
  type DigitalHumanAssetKind,
  type DigitalHumanAssetResult,
  type DigitalHumanProfile,
  type E2ELatencyReport,
  type KnowledgeDocument,
  type QualityRun,
  type VisitorFeedback
} from "./admin/CompetitionPanels";

type AdminArea = "overview" | "knowledge" | "digital-human" | "feedback" | "quality";

const tabs: { key: AdminArea; label: string; icon: typeof Gauge; description: string }[] = [
  { key: "overview", label: "运营概览", icon: Gauge, description: "今日运营与服务脉搏" },
  { key: "knowledge", label: "知识内容", icon: BookOpen, description: "景区资料与问答内容" },
  { key: "digital-human", label: "数字人形象", icon: UserRound, description: "形象、声音、人设与发布" },
  { key: "feedback", label: "游客感受", icon: MessageSquareText, description: "文字反馈与处理闭环" },
  { key: "quality", label: "质量报告", icon: ShieldCheck, description: "回答正确度与响应速度" }
];

type ApiEnvelope<T> = T | { ok: boolean; data: T; message?: string; detail?: string };

async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  const payload = await response.json() as ApiEnvelope<T> & { message?: string; detail?: string };
  if (!response.ok || (payload && typeof payload === "object" && "ok" in payload && payload.ok === false)) {
    throw new Error(payload?.message || payload?.detail || `请求失败：${path}`);
  }
  if (payload && typeof payload === "object" && "data" in payload) return payload.data;
  return payload as T;
}

function jsonRequest(method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown): RequestInit {
  return {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  };
}

function profilePayload(profile: DigitalHumanProfile) {
  return {
    profile_key: profile.profile_key,
    name: profile.name,
    persona: profile.persona,
    driver_provider: profile.driver_provider,
    avatar_asset_url: profile.avatar_asset_url,
    clothing_asset_url: profile.clothing_asset_url || "",
    clothing_version: profile.clothing_version || "",
    voice: profile.voice,
    source_video_url: profile.source_video_url || "",
    source_video_kind: profile.source_video_kind || "still_image_fallback",
    opentalking_avatar_id: profile.opentalking_avatar_id || "",
    prewarm_status: profile.prewarm_status || "unavailable"
  };
}

function profileVersionPayload(profile: DigitalHumanProfile) {
  const { profile_key: _profileKey, ...version } = profilePayload(profile);
  return version;
}

export function AdminConsole() {
  const [active, setActive] = useState<AdminArea>("overview");
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [dashboard, setDashboard] = useState<DashboardMetrics | null>(null);
  const [overview, setOverview] = useState<CompetitionOverview | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [profiles, setProfiles] = useState<DigitalHumanProfile[]>([]);
  const [feedback, setFeedback] = useState<VisitorFeedback[]>([]);
  const [latestQuality, setLatestQuality] = useState<QualityRun | null>(null);
  const [latestE2ELatency, setLatestE2ELatency] = useState<E2ELatencyReport | null>(null);
  const [qualityHistory, setQualityHistory] = useState<QualityRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [previewMessage, setPreviewMessage] = useState("");
  const activeTab = useMemo(() => tabs.find((tab) => tab.key === active) || tabs[0], [active]);

  const refreshOverview = useCallback(async () => {
    const [nextHealth, nextDashboard, legacyReport] = await Promise.all([
      apiGet<Health>("/api/health").catch(() => null),
      apiGet<DashboardMetrics | null>("/api/admin/dashboard").catch(() => null),
      apiGet<{ average_rating?: number | null }>("/api/admin/reports/feelings").catch(() => null)
    ]);
    setHealth(nextHealth);
    setDashboard(nextDashboard);
    try {
      setOverview(await adminRequest<CompetitionOverview>("/api/admin/competition/overview"));
    } catch {
      setOverview({
        today_questions: nextDashboard?.today_questions ?? nextDashboard?.live_questions ?? 0,
        active_visitors: nextDashboard?.live_visitors ?? 0,
        average_rating: legacyReport?.average_rating ?? nextDashboard?.live_average_rating ?? null,
        knowledge: { indexed: nextHealth?.counts?.chunks || 0 },
        provenance: ["实时交互数据", "示例景区数据", "本地自测数据"]
      });
    }
  }, []);

  const refreshKnowledge = useCallback(async () => {
    try {
      setDocuments(await adminRequest<KnowledgeDocument[]>("/api/admin/competition/knowledge/documents"));
    } catch {
      const legacy = await apiGet<{ sources?: { id: number; name: string; file_type: string; imported_at: string }[] }>("/api/admin/sources").catch(() => ({ sources: [] }));
      setDocuments((legacy.sources || []).map((source) => ({ id: source.id, title: source.name, name: source.name, source_type: source.file_type, status: "published", index_status: "ready", updated_at: source.imported_at })));
    }
  }, []);

  const refreshProfiles = useCallback(async () => {
    try {
      const listed = await adminRequest<DigitalHumanProfile[]>("/api/admin/competition/digital-human/profiles");
      if (listed.length) {
        setProfiles(listed);
        return;
      }
      const activeProfile = await adminRequest<DigitalHumanProfile | null>("/api/admin/competition/digital-human/active").catch(() => null);
      setProfiles(activeProfile ? [activeProfile] : []);
    } catch {
      const legacy = await apiGet<{ id?: number; name?: string; voice?: string; persona?: string }>("/api/admin/digital-human").catch(() => null);
      setProfiles(legacy ? [{ id: legacy.id, profile_key: "legacy-guide", name: legacy.name || "灵境导游", voice: legacy.voice || "gentle", persona: legacy.persona || "景区数字人导游", driver_provider: "legacy_mp4", avatar_asset_url: "/assets/generated/avatar-guide-v2.png", source_video_kind: "still_image_fallback", prewarm_status: "unavailable", status: "published", is_active: true }] : []);
    }
  }, []);

  const refreshFeedback = useCallback(async () => {
    try {
      setFeedback(await adminRequest<VisitorFeedback[]>("/api/admin/competition/feedback"));
    } catch {
      const logs = await apiGet<LogItem[]>("/api/admin/logs").catch(() => []);
      setFeedback(logs.filter((item) => item.rating || item.note).map((item) => ({ id: item.id, log_id: item.id, rating: item.rating, text: item.note || item.question, sentiment: item.feeling || undefined, status: "new", management_note: "", recommendation: "", created_at: item.created_at })));
    }
  }, []);

  const refreshQuality = useCallback(async () => {
    const [latest, history, e2eLatency] = await Promise.all([
      adminRequest<QualityRun | null>("/api/admin/competition/quality-runs/latest").catch(() => null),
      adminRequest<QualityRun[]>("/api/admin/competition/quality-runs").catch(() => []),
      adminRequest<E2ELatencyReport | null>("/api/admin/competition/quality-runs/e2e-latency/latest").catch(() => null)
    ]);
    setLatestQuality(latest);
    setQualityHistory(history);
    setLatestE2ELatency(e2eLatency);
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshOverview(), refreshKnowledge(), refreshProfiles(), refreshFeedback(), refreshQuality()]);
  }, [refreshFeedback, refreshKnowledge, refreshOverview, refreshProfiles, refreshQuality]);

  useEffect(() => {
    setBusy(true);
    refreshAll().catch((error) => setNotice(error instanceof Error ? error.message : "运营服务正在连接")).finally(() => setBusy(false));
  }, [refreshAll]);

  async function perform<T>(action: () => Promise<T>, success: string): Promise<T | undefined> {
    setBusy(true);
    setNotice("");
    try {
      const result = await action();
      setNotice(success);
      return result;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "操作没有完成，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  async function createKnowledge(value: { title: string; content: string; source_name: string }) {
    await perform(async () => {
      await adminRequest("/api/admin/competition/knowledge/documents", jsonRequest("POST", value));
      await refreshKnowledge();
    }, "知识内容已创建并进入索引队列。");
  }

  async function updateKnowledge(id: KnowledgeDocument["id"], value: { title: string; content: string }) {
    await perform(async () => {
      await adminRequest(`/api/admin/competition/knowledge/documents/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
      await refreshKnowledge();
    }, "知识内容已保存。");
  }

  async function deleteKnowledge(id: KnowledgeDocument["id"]) {
    await perform(async () => {
      await adminRequest(`/api/admin/competition/knowledge/documents/${id}`, { method: "DELETE" });
      await refreshKnowledge();
    }, "知识内容已删除。");
  }

  async function reindexKnowledge(id: KnowledgeDocument["id"]) {
    await perform(async () => {
      await adminRequest(`/api/admin/competition/knowledge/documents/${id}/reindex`, jsonRequest("POST", {}));
      await refreshKnowledge();
    }, "这份内容已经更新到问答依据中。");
  }

  async function rebuildAllKnowledgeIndexes() {
    await apiPost("/api/admin/rebuild");
    const afterPackageRebuild = await adminRequest<KnowledgeDocument[]>("/api/admin/competition/knowledge/documents");
    for (const document of afterPackageRebuild.filter((item) => item.document_kind === "managed_document" && item.editable !== false)) {
      await adminRequest(`/api/admin/competition/knowledge/documents/${document.id}/reindex`, jsonRequest("POST", {}));
    }
    await refreshKnowledge();
  }

  async function rebuildKnowledge() {
    await perform(rebuildAllKnowledgeIndexes, "基础资料与运营知识已全部重建索引。");
  }

  function uploadKnowledge(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    void perform(async () => {
      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);
        await apiUpload("/api/admin/sources/upload", formData);
      }
      await rebuildAllKnowledgeIndexes();
    }, `已上传 ${files.length} 份资料并同步知识库。`);
  }

  async function saveProfile(profile: DigitalHumanProfile): Promise<DigitalHumanProfile | undefined> {
    return perform(async () => {
      const saved = profile.id
        ? await adminRequest<DigitalHumanProfile>(`/api/admin/competition/digital-human/profiles/${profile.id}/versions`, jsonRequest("POST", profileVersionPayload(profile)))
        : await adminRequest<DigitalHumanProfile>("/api/admin/competition/digital-human/profiles", jsonRequest("POST", profilePayload(profile)));
      await refreshProfiles();
      return saved;
    }, "数字人草稿已保存为新版本。");
  }

  async function uploadProfileAsset(kind: DigitalHumanAssetKind, file: File, profile: DigitalHumanProfile): Promise<DigitalHumanAssetResult | undefined> {
    return perform(async () => {
      const formData = new FormData();
      formData.append("asset_kind", kind);
      formData.append("file", file);
      formData.append("prepare_avatar", kind === "avatar_image" || kind === "neutral_source_video" ? "true" : "false");
      formData.append("display_name", profile.name);
      return adminRequest<DigitalHumanAssetResult>("/api/admin/competition/assets", { method: "POST", body: formData });
    }, kind === "avatar_image" ? "形象照片已上传，讲解画面已自动准备。" : "数字人素材已上传。");
  }

  async function previewProfile(profile: DigitalHumanProfile) {
    if (!profile.id) return setPreviewMessage("请先保存草稿，再生成预览。");
    await perform(async () => {
      const result = await adminRequest<{ preview?: { message?: string }; profile?: DigitalHumanProfile }>(`/api/admin/competition/digital-human/profiles/${profile.id}/preview`, jsonRequest("POST", { sample_text: "欢迎来到灵山胜境" }));
      setPreviewMessage(result.preview?.message || `已生成 ${result.profile?.name || profile.name} 的草稿预览。`);
    }, "数字人预览已更新。");
  }

  async function voicePreview(profile: DigitalHumanProfile, text: string) {
    await perform(async () => {
      const synthesisRequest = profile.id
        ? (await adminRequest<{ status: string; synthesis_request: { text: string; voice: string } }>(`/api/admin/competition/digital-human/profiles/${profile.id}/voice-preview`, jsonRequest("POST", { text }))).synthesis_request
        : { text, voice: profile.voice };
      const audio = await apiPost<{ audio_url?: string | null }>("/api/tts/synthesize", synthesisRequest);
      if (audio.audio_url) {
        const player = new Audio(audio.audio_url.startsWith("http") ? audio.audio_url : `${API_BASE}${audio.audio_url}`);
        await player.play();
      } else {
        throw new Error("声音暂时没有生成，请稍后重试。");
      }
      setPreviewMessage("正在播放当前选择的讲解声音。");
    }, "声音试听已播放。");
  }

  async function publishProfile(profile: DigitalHumanProfile): Promise<DigitalHumanProfile | undefined> {
    return perform(async () => {
      const saved = profile.id
        ? await adminRequest<DigitalHumanProfile>(`/api/admin/competition/digital-human/profiles/${profile.id}/versions`, jsonRequest("POST", profileVersionPayload(profile)))
        : await adminRequest<DigitalHumanProfile>("/api/admin/competition/digital-human/profiles", jsonRequest("POST", profilePayload(profile)));
      if (!saved.id) throw new Error("新版本未返回可发布的 ID。");
      const published = await adminRequest<DigitalHumanProfile>(`/api/admin/competition/digital-human/profiles/${saved.id}/publish`, jsonRequest("POST", {}));
      await refreshProfiles();
      return published;
    }, "数字人配置已发布，游客端将读取当前版本。");
  }

  async function updateFeedback(id: number, value: Partial<VisitorFeedback>) {
    await perform(async () => {
      await adminRequest(`/api/admin/competition/feedback/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: value.status, recommendation: value.recommendation, management_note: value.management_note }) });
      await refreshFeedback();
    }, value.status === "resolved" ? "游客反馈已完成处理。" : "游客反馈已进入跟进。");
  }

  async function createQualityRun() {
    await perform(async () => {
      await adminRequest("/api/admin/competition/quality-runs/run", jsonRequest("POST", {}));
      await refreshQuality();
    }, "固定题集已经测试完成；该结果用于本机检查，不替代比赛官方评审。");
  }

  return (
    <main className={navigationOpen ? "admin-shell navigation-open" : "admin-shell"}>
      <aside className="admin-sidebar">
        <a className="admin-brand" href="/" aria-label="返回游客端">
          <img src="/assets/generated/app-icon-v2.png" alt="" />
          <span><b>灵境导游</b><small>景区运营中心</small></span>
        </a>
        <nav className="admin-tabs" role="tablist" aria-label="管理区域" aria-orientation="vertical">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return <button id={`admin-tab-${tab.key}`} className={active === tab.key ? "active" : ""} key={tab.key} type="button" role="tab" aria-selected={active === tab.key} aria-controls={`admin-panel-${tab.key}`} onClick={() => { setActive(tab.key); setNavigationOpen(false); }}><Icon size={20} /><span><b>{tab.label}</b><small>{tab.description}</small></span></button>;
          })}
        </nav>
        <div className="admin-sidebar-foot"><span><i className={health?.ok ? "ready" : ""} />服务状态</span><a href="/">进入游客端 <ChevronLeft size={17} /></a></div>
      </aside>

      <section className="admin-main">
        <header className="admin-header">
          <button className="mobile-nav-button" type="button" onClick={() => setNavigationOpen((value) => !value)} aria-label={navigationOpen ? "关闭管理导航" : "打开管理导航"}><Menu size={21} /></button>
          <div><span>灵山胜境 · 运营工作台</span><h1>{activeTab.label}</h1></div>
          <div className="admin-header-actions"><span className="source-badge">{active === "quality" ? "本地自测数据" : active === "overview" || active === "feedback" ? "实时交互数据" : "示例景区数据"}</span><button className="secondary-action" type="button" disabled={busy} onClick={() => void perform(refreshAll, "运营数据已刷新。")}>{busy ? <BarChart3 size={18} /> : <RefreshCcw size={18} />}刷新</button></div>
        </header>
        {notice ? <div className="admin-notice" role="status" aria-live="polite">{notice}</div> : null}

        <section id="admin-panel-overview" role="tabpanel" aria-labelledby="admin-tab-overview" hidden={active !== "overview"}><OverviewPanel overview={overview} dashboard={dashboard} health={health} onOpen={setActive} /></section>
        <section id="admin-panel-knowledge" role="tabpanel" aria-labelledby="admin-tab-knowledge" hidden={active !== "knowledge"}><KnowledgePanel documents={documents} busy={busy} onCreate={createKnowledge} onUpdate={updateKnowledge} onDelete={deleteKnowledge} onReindex={reindexKnowledge} onRebuild={rebuildKnowledge} onUpload={uploadKnowledge} /></section>
        <section id="admin-panel-digital-human" role="tabpanel" aria-labelledby="admin-tab-digital-human" hidden={active !== "digital-human"}><DigitalHumanPanel profiles={profiles} busy={busy} previewMessage={previewMessage} onAssetUpload={uploadProfileAsset} onVoicePreview={voicePreview} onPublish={publishProfile} /></section>
        <section id="admin-panel-feedback" role="tabpanel" aria-labelledby="admin-tab-feedback" hidden={active !== "feedback"}><FeedbackPanel feedback={feedback} busy={busy} onUpdate={updateFeedback} /></section>
        <section id="admin-panel-quality" role="tabpanel" aria-labelledby="admin-tab-quality" hidden={active !== "quality"}><QualityPanel latest={latestQuality} e2eLatency={latestE2ELatency} history={qualityHistory} busy={busy} onRun={createQualityRun} /></section>
      </section>
    </main>
  );
}
