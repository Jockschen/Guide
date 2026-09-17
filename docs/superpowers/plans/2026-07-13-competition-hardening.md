# 赛题验收硬化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复当前验收绿线，并把真实语音问答的首个可见口型响应变成可自动测量、可持续优化的比赛证据。

**Architecture:** 先修复反馈双表一致性和 Edge TTS 契约漂移，再增加一条严格的比赛验收入口。问答链路采用“本地 FAQ 快速命中 + Qwen 流式首句”双路径，首句立即进入 TTS 与已预热 WebRTC session；后台规格缺口在核心链路稳定后用现有 profile、dashboard 和 feedback 模型补齐。

**Tech Stack:** FastAPI、SQLite、Python unittest、Next.js 15、React 19、TypeScript、Node 审计脚本、Qwen OpenAI 兼容 API、Edge/Vivo TTS、OpenTalking WebRTC。

## Global Constraints

- 不新增 GPS，不扩展与赛题验收无关的页面。
- 事实回答必须受本地资料约束；资料不足时明确返回“资料包中未提供”。
- 比赛验收不得把 mock、预录视频或浏览器朗读计入真实链路达标结果。
- 准确率报告必须保留 `official_evaluation=false`，除非存在赛事官方证据。
- 完整首响应口径为“游客停止说话或提交文本 -> 首个有效音节且浏览器出现可见口型变化”。
- 目标为预热状态下至少 30 次运行 `P95 < 5000 ms`；冷启动单独报告。
- 当前目录不是有效 Git 仓库；每个任务以最小补丁和独立验证代替提交步骤。

---

### Task 1: 修复游客反馈双表一致性

**Files:**
- Modify: `backend/server/admin_competition.py:672-760`
- Test: `backend/tests/test_admin_competition_closure.py:488-558`

**Interfaces:**
- Consumes: `TextFeedbackCreate(log_id, rating, text, sentiment, topics)`、SQLite `qa_logs` 与 `feedback`。
- Produces: `_sync_feedback_to_qa_log(conn, ...)` 与 `_backfill_legacy_feedback(conn)`；文字反馈实时更新 `qa_logs.rating/feeling/note`，历史评分只回填一次。

- [ ] **Step 1: 运行现有失败测试并确认 RED**

  Run: `.\.venv\Scripts\python.exe -m unittest backend.tests.test_admin_competition_closure.AdminCompetitionClosureTests.test_text_feedback_keeps_realtime_dashboard_rating_in_sync backend.tests.test_admin_competition_closure.AdminCompetitionClosureTests.test_legacy_ratings_are_backfilled_once_into_management_feedback`

  Expected: `rating None != 2` 与反馈列表长度 `0 != 1`。

- [ ] **Step 2: 增加边界回归测试**

  在同一测试类加入：重复读取不会重复回填；不存在的 `log_id` 不会更新其他问答；已解决反馈不会被错误复用。

- [ ] **Step 3: 运行新增测试并确认 RED**

  Expected: 新增测试因缺少同步/回填行为失败。

- [ ] **Step 4: 实现最小双表同步**

  `rating <= 2 -> 待改进`、`rating >= 4 -> 满意`、其余为 `一般`；`note` 使用游客文字。回填使用 `NOT EXISTS` 按 `log_id` 去重，并在列表查询事务内完成。

- [ ] **Step 5: 运行反馈测试并确认 GREEN**

  Run: `.\.venv\Scripts\python.exe -m unittest backend.tests.test_admin_competition_closure`

  Expected: 全部通过。

### Task 2: 对齐 Edge TTS 验收契约

**Files:**
- Modify: `scripts/audit-goal-acceptance.mjs:57-127`
- Modify: `backend/tests/test_pipeline.py:61`
- Test: `backend/tests/test_voice.py`

**Interfaces:**
- Consumes: `voice.py` 中 `TTS_PROVIDERS={"edge", ...}` 与 `.env.example` 中 `TTS_PROVIDER=edge`。
- Produces: 审计脚本和后端测试接受 Edge，但不降低真实音频就绪检查。

- [ ] **Step 1: 运行现有失败命令并确认 RED**

  Run: `npm run goal-audit`

  Expected: `.env.example 缺少：TTS_PROVIDER=cosyvoice`。

  Run: `.\.venv\Scripts\python.exe -m unittest backend.tests.test_pipeline.PipelineTests.test_pipeline_check_covers_knowledge_tts_and_lipsync`

  Expected: `edge` 不在允许集合。

- [ ] **Step 2: 更新测试与静态审计契约**

  把 Edge 加入 TTS 允许集合；审计 `.env.example` 的默认值改为 `edge`，并检查 `EDGE_TTS_*`/session TTS 配置与 `voice.py` 的 Edge 实现。

- [ ] **Step 3: 运行目标测试并确认 GREEN**

  Run: `npm run goal-audit`

  Run: `.\.venv\Scripts\python.exe -m unittest backend.tests.test_pipeline backend.tests.test_voice`

  Expected: 全部通过。

### Task 3: 建立严格统一的 competition-check

**Files:**
- Create: `scripts/competition-check.mjs`
- Create: `scripts/test-competition-check.mjs`
- Modify: `package.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: 现有 `startup-audit`、`typecheck`、`copy-audit`、`flow-audit`、`admin-audit`、`goal-audit`、后端 unittest、`build`、strict `live-check`、冻结 QA、WebRTC 和 E2E 报告。
- Produces: `npm run competition-check`；任何 mock provider、服务未就绪、红测、过期或不完整性能报告都会非零退出。

- [ ] **Step 1: 编写命令编排测试**

  使用可注入命令执行器验证顺序、失败短路、`LIVE_CHECK_STRICT=1`、报告字段 `measurement_complete/within_target` 与 `official_evaluation` 边界。

- [ ] **Step 2: 运行测试并确认 RED**

  Run: `node scripts/test-competition-check.mjs`

  Expected: 模块或导出不存在。

- [ ] **Step 3: 实现静态与 live 两级模式**

  默认 `--static` 跑代码与测试；`--live` 追加真实服务、QA、WebRTC、E2E 检查。输出每个阶段的退出码与失败原因，不覆盖历史报告为“通过”。

- [ ] **Step 4: 运行脚本测试并确认 GREEN**

  Run: `node scripts/test-competition-check.mjs`

  Expected: 全部通过。

### Task 4: 增加本地 FAQ 快速通道

**Files:**
- Modify: `backend/server/retrieval.py`
- Modify: `backend/server/main.py:602-660`
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_retrieval.py`

**Interfaces:**
- Consumes: `faqs(question, answer, source_title, source_file)`。
- Produces: `match_faq(question, min_score) -> dict | None`；仅对高置信度事实问题直接返回资料答案，provider=`local-faq`，低置信度继续走 Qwen。

- [ ] **Step 1: 写精确命中、同义标点和低置信不命中的失败测试**

- [ ] **Step 2: 运行测试并确认 RED**

  Run: `.\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval backend.tests.test_pipeline`

- [ ] **Step 3: 实现保守匹配**

  规范化空白与标点，精确问题优先；模糊匹配必须同时满足核心实体与意图词，避免错误绕过 Qwen。

- [ ] **Step 4: 运行测试并确认 GREEN**

### Task 5: 增加 Qwen 首句流式接口

**Files:**
- Modify: `backend/server/qwen_client.py`
- Modify: `backend/server/main.py`
- Test: `backend/tests/test_qwen_client.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Qwen OpenAI 兼容 `chat/completions` SSE。
- Produces: `stream_qwen(...) -> Iterator[str]` 与 `/api/chat/stream` NDJSON 事件：`meta`、`delta`、`narration`、`done`、`error`。

- [ ] **Step 1: 写 SSE 分片解析失败测试**

  覆盖跨行分片、`[DONE]`、首句边界、异常回退、本地资料来源元数据。

- [ ] **Step 2: 运行测试并确认 RED**

- [ ] **Step 3: 实现复用 prompt 构造器的流式客户端**

  非流式 `call_qwen` 与流式调用共用 payload；首句以中文句号、问号、叹号或长度上限切分。

- [ ] **Step 4: 实现流式 API 与日志收尾**

  只有完整结束后写 `qa_logs`；中断仍返回可诊断 error 事件，不把半句写成完整答案。

- [ ] **Step 5: 运行 Qwen/API 测试并确认 GREEN**

### Task 6: 前端首句即播与 WebRTC 并行

**Files:**
- Modify: `lib/api.ts`
- Modify: `lib/types.ts`
- Modify: `components/TouristExperience.tsx:249-380`
- Test: `scripts/audit-tourist-flow.mjs`
- Test: `scripts/audit-goal-acceptance.mjs`

**Interfaces:**
- Consumes: `/api/chat/stream` 事件、现有 `/api/tts/synthesize`、`useOpenTalkingSession().enqueueAudio()`。
- Produces: 首句一到即调用 TTS 并 enqueue；后续文本继续渲染，后续句 TTS 与当前播放并行准备。

- [ ] **Step 1: 扩展流程审计使旧串行实现 RED**

  审计必须看到流式事件消费、first-sentence TTS、session 预连接和取消旧请求。

- [ ] **Step 2: 实现最小流式读取与取消控制**

  使用 `AbortController`；FAQ 非流式快速响应仍复用同一播放队列。

- [ ] **Step 3: 实现首段立即播报**

  第一段 TTS 完成后立即 enqueue；后续段只预取一段，避免无限并发和乱序。

- [ ] **Step 4: 运行类型检查和流程审计确认 GREEN**

  Run: `npm run typecheck`

  Run: `npm run flow-audit`

### Task 7: 自动化完整首响应基准

**Files:**
- Modify: `scripts/benchmark_e2e.py`
- Create: `backend/tests/test_benchmark_e2e.py`
- Modify: `docs/competition-requirements-audit.md`

**Interfaces:**
- Consumes: ASR 完成时间、FAQ/Qwen 首 token/首句、TTS 首段、session enqueue、浏览器首个可见口型时间。
- Produces: 30 次运行的 P50/P95/失败率、冷/热启动分组、`measurement_complete` 与 `within_target`。

- [ ] **Step 1: 写聚合统计和缺失阶段失败测试**

- [ ] **Step 2: 运行测试并确认 RED**

- [ ] **Step 3: 实现样本数组、分位数与严格完整性判断**

- [ ] **Step 4: 运行测试并确认 GREEN**

### Task 8: 补齐后台明确规格缺口

**Files:**
- Modify: `components/CompetitionPanels.tsx`
- Modify: `components/AdminConsole.tsx`
- Modify: `backend/server/admin_competition.py`
- Modify: `backend/server/main.py`
- Modify: `lib/types.ts`
- Test: `backend/tests/test_admin_competition_closure.py`
- Test: `scripts/audit-admin-competition.mjs`

**Interfaces:**
- Consumes: 已存在 `clothing_asset_url/clothing_version`、问答日志日期与 question groups、反馈文本与星级。
- Produces: 可见的服装/文化风格字段；`week_questions/week_visitors/hot_questions`；情感结果增加 `method=model|rule|rating` 与置信度，模型不可用时明确回退。

- [ ] **Step 1: 写 API/静态审计失败测试**

- [ ] **Step 2: 运行并确认 RED**

- [ ] **Step 3: 实现现有字段的可见配置与周统计**

- [ ] **Step 4: 实现可审计的情感分类接口与回退标识**

- [ ] **Step 5: 运行后台测试和审计确认 GREEN**

### Task 9: 全量验收

**Files:**
- Verify only; update reports/docs only from真实运行输出。

**Interfaces:**
- Produces: 当前版本的静态绿线与真实环境报告；无法运行的外部服务明确列为阻塞，不以历史报告替代。

- [ ] **Step 1: 全量静态验证**

  Run: `.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p test_*.py`

  Run: `npm run startup-audit`

  Run: `npm run copy-audit`

  Run: `npm run flow-audit`

  Run: `npm run admin-audit`

  Run: `npm run goal-audit`

  Run: `npm run typecheck`

  Run: `npm run build`

- [ ] **Step 2: 真实服务验证**

  启动比赛配置后运行 `npm run competition-check -- --live`，确认真实 ASR、TTS、Qwen、OpenTalking，无 mock。

- [ ] **Step 3: 性能与质量报告**

  30 次真实首响应基准必须给出 P50/P95/失败率；冻结 QA 与隐藏题集分别报告，本地结果不冒充官方结果。

- [ ] **Step 4: 最终演示视频人工验收**

  人工检查口型同步、语音自然度、表情配合、断网/重启降级和后台数据闭环。

## Self-Review

- Spec coverage: 覆盖当前红测、严格验收、FAQ 快速通道、Qwen 首句流式、首段 TTS/WebRTC、完整基准、后台四个明确缺口与最终人工评价。
- Intentional exclusions: GPS/弱定位、远程 FlashTalk/FlashHead、新页面扩展。
- Placeholder scan: 所有任务均给出具体文件、接口、命令和成功条件；实现细节以测试先行约束。
- Type consistency: 后端事件名与前端消费统一为 `meta/delta/narration/done/error`；性能报告统一使用 `measurement_complete/within_target`。
