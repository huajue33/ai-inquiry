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

### 5. 模型路由（按问题复杂度选模型）
> ✅ **已完成**（方案 B：下拉新增「自动」档）。

**背景**：已有前端模型选择器，"后端把同一次请求路由到不同模型"会与用户显式选择冲突，
且 `create_agent` 单图只用一个 LLM、按节点换模型需自写 StateGraph（成本大于收益）。
故采用更契合现状的方案。

**已落地**（`core/models.py`）：
- 下拉新增伪模型 `auto`（"自动"），由 `get_available_models` 注入首位。
- `route_model(requested, message)`：选 `auto` 时按轻量启发式 `_is_simple_query` 路由——
  寒暄/元问题（短且命中关键词）→ lite 模型，其余 → 主模型；选了具体模型则原样尊重。
- 偏保守：除明显闲聊外一律按复杂处理，绝不把真实询价降级到弱模型。
- `ai_service.chat_stream` 改用 `route_model`；思考是否生效再按实际路由到的模型判定。
- 另：标题生成（`title_service`）本就用 lite 模型，辅助调用已走便宜模型。

**备注**：`auto` 非默认项（默认仍是配置的主模型），用户可主动选择；如需默认走 auto
可再调整。前端无需改动（auto 选项由后端下发自动流转）。

---

## 中价值 · 健壮性

### 6. 限制工具调用次数与 `recursion_limit`
> ✅ **已完成**。

**原问题**：查询库中不存在的商品（如"大豆油"）时，模型反复换词重试 `search_products`，
撞上 langgraph 默认递归上限 25 并抛原始报错给用户。

**已落地**：
- 工具层：`search_products` 单次请求内限调用 `MAX_SEARCH_CALLS=5` 次，超限直接返回
  `search_limit` 错误（短路，不查 DB），引导模型停止重试、直接回答"未找到相关商品"。
- Agent：`astream_events` 显式设 `recursion_limit=15`（兜底）。
- 兜底：捕获 `GraphRecursionError`，给用户干净的"未找到"提示而非原始报错，并作为正常回答持久化。
- 提示词：补充"多次无结果不要反复换词重试"。

---

### 7. LLM / API 瞬时失败重试
> ✅ **已完成**。

**原问题**：上游百炼偶发连接错误/429/5xx/超时，缺少显式重试。

**已落地**：给所有模型客户端显式设 `max_retries=llm_max_retries`（默认 3，配置项可调）——
利用 OpenAI SDK 内置的**指数退避重试**，覆盖 `ChatOpenAI`/`ReasoningChatOpenAI`（agent）、
`AsyncOpenAI`（ASR 共用）与标题生成客户端。
- 重试发生在请求/连接建立阶段，对瞬时错误自动退避，**不会在流式中途重复 token**；
  流式开始后的中断属于少数情况，仍按错误处理（避免重复输出的复杂度）。

---

## 中价值 · 可观测性

### 8. 可观测性：本地结构化决策日志
> ✅ **已完成（日志方案，不引入 LangSmith/外部服务）**；评测集暂缓。

**原问题**：仅 token 用量落库，看不到 Agent 的决策链（为何选某工具、为何搜偏、为何走网络）。

**已落地**：每轮对话收尾打一条结构化 `[agent-trace]` INFO 日志（`ai_service._log_trace`），含：
用户、模型、是否思考、是否联网回退、**各工具调用的参数 + 结果状态（ok/empty/error:code）**、
token、耗时、outcome（ok/empty/recursion_limit/error）。全本地、无外部依赖、价格数据不外泄。
`main.py` 配 `logging.basicConfig(INFO)` 确保日志可见（`docker compose logs -f backend`）。

示例：
```
[agent-trace] user=3 model=qwen3.5-plus thinking=False web=False \
  tools=[search_products({'keyword':'土豆'})->ok, get_latest_prices({'product_ids':[10001]})->ok] \
  tokens=1234 dur=2100ms outcome=ok
```

**未做**：评测集（20~30 条回归 case）本质是测试，按"非必要不加测试"原则暂缓；
LangSmith 因价格数据外泄考量未采用（如需深度调试可临时用环境变量开启，不入代码）。

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

| 优先级 | 项 | 类型 | 改动量 | 状态 |
|---|---|---|---|---|
| P0 | #2 防幻觉链接 | 可靠性 | 小 | ✅ 已完成 |
| P0 | #1 Meilisearch 同义词 | 准确性 | 小~中 | ✅ 已完成 |
| P1 | #4 思考模式重构 | 延迟 | 中 | ✅ 已完成 |
| P1 | #3 保留商品上下文 | 准确性 | 中 | ✅ 已完成 |
| P2 | #5 模型路由（自动档） | 成本 | 小~中 | ✅ 已完成 |
| P2 | #6 工具调用上限 / 递归上限 | 健壮性 | 小 | ✅ 已完成 |
| P2 | #7 LLM 重试 | 健壮性 | 小 | ✅ 已完成 |
| P3 | #8 可观测性（本地日志） | 体验/质量 | 小 | ✅ 已完成 |
| P3 | #9 品牌对比 / #10 ASR 热词 | 体验/质量 | 中 | ⬜ 待办 |
