# Agent 优化建议

本文基于对当前 Agent 相关实现的梳理，给出可落地的优化方向。涉及代码：

- `backend/app/services/agent.py` — LangGraph ReAct Agent 装配
- `backend/app/services/ai_service.py` — 流式输出、思考模式
- `backend/app/tools/price_tools.py` — 4 个价格查询工具
- `backend/app/services/price_service.py` — 搜索 / 取价 / 排行的数据层
- `backend/app/core/prompts.py` — 系统提示词
- `backend/app/services/history.py` — 历史加载与摘要压缩

> 进度：**#1、#2、#3、#4 已完成**（见各条 ✅）。剩余 #5~#10 为后续可选优化。

---

## 高价值 · 准确性与可靠性

### 1. 用 Meilisearch 原生同义词替代硬编码别名表
> ✅ **已完成**：别名/同义词收敛为单一数据源 `app/core/aliases.py`。

**现状**：`price_service.py` 里 `_CATEGORY_ALIASES = {"马铃薯":"土豆","西红柿":"番茄"}` 写死在代码中。

**问题**：生鲜别名极多，硬编码不可维护，且与 Meilisearch 同义词配置**重复维护两份**。

**已落地**：发现 Meilisearch 同义词其实已在 `setup_index` 配置，真正问题是同一份别名在
`search_service.py` 和 `price_service.py` 各写一遍。新增 `app/core/aliases.py` 作为唯一数据源
（`SYNONYMS`），导出 `meili_synonyms()`（给搜索引擎）与 `alias_to_canonical()`（给分类锁定）。
两个机制有意分开（见代码注释），但共享同一份数据，以后加别名只改一处。

---

### 2. 服务端校验 `{#id=N}` 标记，防止幻觉链接
> ✅ **已完成**。

**现状**：系统提示词要求模型只用工具返回的真实 `product_id`，但服务端无任何兜底。

**问题**：模型一旦编造 ID，前端 `MessageList.vue` 会把 `{#id=N}` 渲染成指向不存在商品的链接。

**已落地**（`ai_service.py`）：`_collect_valid_ids` 收集本轮工具返回的 `product_id` ∪ 历史里出现过的
ID（历史也纳入，避免误删"第二个/刚才那个"的合法复用）；`_scrub_invalid_id_markers` 归一化
单/双括号为 `{#id=N}` 并剥离不可信 ID，**valid_ids 为空时 fail-open 只归一化不删除**。
清洗后的 content 随 `done` 事件回传，前端 `onDone` 以其为准；并修正了提示词的双括号问题。

---

### 3. 保留近期商品上下文，让"刚才那个/第二个"可靠
> ✅ **已完成**：`history.py` 重写为 token 预算滑动窗口。

**原问题**：`history.py` 的 `_truncate_ai` 把 AI 回复截断到 150 字，会切掉 `{#id=...}` 标记，
导致追问"第二个多少钱"时模型已无 ID 可复用；且 LLM 摘要有损、多一次调用。

**已落地**：去掉 150 字截断与 LLM 摘要，改为从最近往旧累加到 ~2500 token 的硬窗口、按"轮"对齐，
**完整保留 `{#id=N}` 标记 / 价格 / 品名**。这样只要上一轮在窗口内，ID 复用就可靠。
参数见 `history.py` 顶部（`MAX_CONTEXT_TOKENS` 等）。

---

## 高价值 · 延迟与成本

### 4. 重构"思考模式"的两段式调用
> ✅ **已完成**：通过 `ReasoningChatOpenAI` 子类，思考模式已合并为单次 Agent 流式。

**原问题**（旧 `_stream_with_thinking`）：先 `ainvoke` 跑一遍 Agent 收集工具数据（非流式），
再把工具输出塞进新 prompt 做第二次 LLM 调用。两次往返、延迟翻倍、phase1 无流式反馈、
phase2 丢失对话结构、思考是"事后解释"无法影响选工具、两套代码并行。

**根因**：`langchain-openai` 的 `ChatOpenAI` 基类只解析 OpenAI 官方字段，**故意不提取**第三方的
`reasoning_content`（文档明确建议"用 provider-specific subclass"）。原生 openai SDK 能拿到，
经 LangChain 解析层被过滤——所以工具调用正常（`tool_calls` 是标准字段），唯独思考拿不到。
（注：与版本无关，本地 langchain-openai 1.2.2 仍如此，是设计取舍。）

**解决方案（已落地）**：
- `agent.py` 新增 `ReasoningChatOpenAI(ChatOpenAI)`，重写 `_convert_chunk_to_generation_chunk`，
  把流式 chunk 里的 `reasoning_content` 透出到 `additional_kwargs`。
- `get_agents(model, enable_thinking)` 按是否思考构建不同 LLM（思考时用 ReasoningChatOpenAI + `enable_thinking`）。
- `ai_service` 把 `_stream_normal` / `_stream_with_thinking` 合并为单个 `_stream`：同一次流式里
  从 `additional_kwargs.reasoning_content` 取思考 → `thinking_token`，`content` → `token`，工具事件照常。
- 仅当模型支持思考时才开启（`model_supports_thinking`）。

**验证**：单次 `chat_stream` 实测同时产出 thinking_token / token / tool_start / tool_end / done，
且 `{#id=N}` 链接正确保留。延迟从两次往返降为一次，思考可影响工具选择，代码合并为一套。

> 另注（实测发现）：本地环境实际为 langchain-openai 1.2.2 / langchain 0.3.27，与
> `requirements.txt` 锁定的 0.2.9 / 0.3.7 **不一致**。建议先对齐版本，避免"本地正常、线上异常"。

---

### 5. 模型路由（便宜模型选工具，强模型做总结）
**现状**：工具选择与最终措辞全程使用主模型（如 qwen3.5-plus）。

**建议**：按问题复杂度路由——工具选择/检索决策用轻量模型（qwen-turbo），
最终措辞用强模型；简单查询直接走 lite 模型。降低成本与首字延迟。

---

## 中价值 · 健壮性

### 6. 显式设置 `recursion_limit` 与工具调用上限
**现状**：`create_react_agent` 默认递归上限 25。

**建议**：显式调小（如 8~10），并在提示词已有"不重复调用相同参数"约束的基础上，
增加服务端的相同参数去重兜底，避免模型空转拖长响应。

---

### 7. LLM / API 瞬时失败重试
**现状**：工具层错误以结构化 JSON 返回（良好），但上游百炼偶发 5xx/超时无重试。

**建议**：对模型调用加指数退避重试（1~2 次），降低偶发失败率。

---

## 中价值 · 可观测性

### 8. 接入 tracing 并建立小型评测集
**现状**：仅 token 用量落库，看不到 Agent 的决策链（为何选某工具、为何搜偏）。

**建议**：
- 接入 LangSmith / OpenLLMetry 等，可视化调试 Agent 决策。
- 沉淀 20~30 条典型询价 case 作回归集，改提示词/换模型时量化效果，而非凭感觉。

---

## 锦上添花

### 9. 多品牌对比的可靠性
**现状**：靠提示词约束模型"挑不同品牌代表"，容易翻车（结果全是同品牌不同规格）。

**建议**：在服务端实现"按品牌去重取代表"，或新增 `compare_brands` 工具，
把这件事从"求模型自觉"变成"代码保证"。

### 10. ASR 自定义热词
**建议**：Paraformer 实时识别支持自定义热词词表，把生鲜专业品名注册进去，
可明显提升专业词识别率。

---

## 落地优先级建议

| 优先级 | 项 | 类型 | 改动量 |
|---|---|---|---|
| P0 | #2 防幻觉链接 | 可靠性 | 小 |
| P0 | #1 Meilisearch 同义词 | 准确性 | 小~中 |
| P1 | #4 思考模式重构 | 延迟 | 中 |
| P1 | #3 保留商品上下文 | 准确性 | 中 |
| P2 | #5 模型路由 / #6 递归上限 / #7 重试 | 成本/健壮性 | 小~中 |
| P3 | #8 可观测性 / #9 品牌对比 / #10 ASR 热词 | 体验/质量 | 中 |
