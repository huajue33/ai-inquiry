# AI询价助手 - 项目方案

## 一、项目定位

基于对话式交互的B端采销AI询价助手，用户通过自然语言提问，AI返回结构化的价格信息、趋势分析和比价结果。

核心场景：
- "土豆今天多少钱" → 返回最新价格卡片
- "最近一周哪些菜涨价了" → 返回涨价排行+趋势图
- "天府山珍和小樵的蟹味菇哪个便宜" → 返回比价卡片

## 二、功能设计

### 2.1 自然语言询价

用户输入自然语言，AI识别意图并查询数据库返回结果。

| 意图类型 | 示例问题 | 返回内容 |
|---------|---------|---------|
| 单品询价 | "土豆多少钱"、"青小米椒最新价格" | 产品价格卡片（品名、品牌、规格、最新价、涨跌幅） |
| 分类询价 | "叶菜类今天什么价" | 该分类下产品价格列表 |
| 模糊询价 | "有没有便宜的茄子" | 按价格排序的茄子类产品列表 |

### 2.2 价格趋势分析

| 意图类型 | 示例问题 | 返回内容 |
|---------|---------|---------|
| 单品趋势 | "土豆最近一周价格走势" | 折线图卡片 |
| 涨跌排行 | "今天哪些菜涨价了" | 涨幅TOP列表卡片 |
| 分类趋势 | "调味品整体价格趋势" | 分类均价折线图 |
| 异常检测 | "最近有什么价格异常" | 异常波动产品列表 |

### 2.3 智能比价

| 意图类型 | 示例问题 | 返回内容 |
|---------|---------|---------|
| 品牌对比 | "天府山珍和小樵的菇类比一下" | 品牌比价表格卡片 |
| 品质对比 | "优质和统货的线茄差多少" | 品质差价对比卡片 |
| 时段对比 | "这周和上周的蔬菜价格对比" | 时段对比表格+涨跌标注 |

## 三、交互与原型设计

### 3.1 页面布局

```
┌────────────────────────────────────────────────────────┐
│  顶部栏: Logo "AI询价助手"          [通知] [用户]   │
├────────────────────────────────────────────────────────┤
│                                                        │
│   ┌──────────────────────────────────────────────┐    │
│   │  对话消息区（可滚动）                          │    │
│   │                                              │    │
│   │  [AI] 你好，我是询价助手，可以帮你查价格、     │    │
│   │       分析趋势、对比品牌...                    │    │
│   │                                              │    │
│   │  [用户] 土豆今天多少钱                        │    │
│   │                                              │    │
│   │  [AI] ┌─价格卡片──────────────────┐          │    │
│   │       │ 土豆  统货  斤             │          │    │
│   │       │ ¥2.50  ↑5%               │          │    │
│   │       │ [查看趋势] [加入对比]      │          │    │
│   │       └───────────────────────────┘          │    │
│   │                                              │    │
│   └──────────────────────────────────────────────┘    │
│                                                        │
│   ┌──────────────────────────────────────────────┐    │
│   │  快捷提问: [今日涨价TOP] [我关注的] [分类浏览] │    │
│   ├──────────────────────────────────────────────┤    │
│   │  输入框: 请输入你的问题...          [发送]     │    │
│   └──────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

### 3.2 结构化卡片类型

1. **价格卡片** - 单品最新价格展示
2. **列表卡片** - 多产品价格排行/筛选结果
3. **图表卡片** - 折线图(趋势)、柱状图(对比)
4. **比价表格卡片** - 多品牌/多品质横向对比
5. **异常提醒卡片** - 价格异动产品高亮展示
6. **追问选择卡片** - 搜索结果过多时，展示分组选项供用户点击细化

### 3.3 用户流程

```
登录 → 对话主界面
     → 输入问题 / 点击快捷提问
     → AI解析意图 → 查询数据 → 返回结构化卡片
     → 用户可在卡片上操作（查看详情/加入对比/设置关注）
```

## 四、架构设计

### 4.1 系统架构

```
┌──────────┐       ┌─────────────────────────────────────┐
│  Vue3    │──────▶│  Nginx (静态资源 + 反向代理)         │
│  前端    │       └────────────┬────────────────────────┘
└──────────┘                    │
                                ▼
                     ┌─────────────────────┐
                     │   FastAPI 后端       │
                     │   ├─ /api/chat      │ ← 对话入口
                     │   ├─ /api/prices    │ ← 价格数据
                     │   ├─ /api/auth      │ ← 认证
                     │   └─ AI Service     │ ← 意图识别+SQL生成
                     └───┬────────┬────────┘
                         │        │
                    ┌────┴──┐  ┌──────────────┐
                    │ MySQL │  │ 阿里云百炼    │
                    │       │  │ (通义千问)    │
                    └───────┘  └──────────────┘
```

### 4.2 AI对话处理流程

```
用户输入 → FastAPI接收
        → 构造Prompt（系统提示词 + 数据库Schema + 用户问题）
        → 调用百炼API（通义千问，通过LangChain Agent）
        → LLM返回结构化JSON（意图 + SQL/查询参数）
        → 后端执行查询
        → 格式化结果为卡片数据
        → 返回前端渲染
```

### 4.3 LLM调用设计（Function Calling）

通过百炼（通义千问）的 Function Calling 能力，由 LangChain Agent 编排工具调用：

```python
tools = [
    {
        "name": "query_latest_price",
        "description": "查询产品最新价格",
        "parameters": {
            "product_name": "产品名称关键词",
            "brand": "品牌(可选)",
            "category": "分类名称(可选)",
            "quality": "品质等级(可选)",
            "spec": "规格(可选)"
        }
    },
    {
        "name": "query_price_trend",
        "description": "查询价格趋势",
        "parameters": {
            "product_id": "产品ID(精确查询时使用)",
            "product_name": "产品名称(模糊查询时使用)",
            "days": "天数，默认7"
        }
    },
    {
        "name": "query_price_ranking",
        "description": "查询涨跌排行",
        "parameters": {
            "direction": "rise/fall",
            "category": "分类(可选)",
            "limit": "数量，默认10"
        }
    },
    {
        "name": "compare_products",
        "description": "比较多个产品价格",
        "parameters": {
            "product_names": ["产品A", "产品B"],
            "compare_type": "brand/quality/period"
        }
    },
    {
        "name": "clarify_product",
        "description": "当搜索结果过多时，返回分类选项让用户进一步选择",
        "parameters": {
            "keyword": "用户搜索的关键词",
            "max_groups": "最多返回几组分类，默认5"
        }
    }
]
```

### 4.4 多结果追问机制

当用户输入模糊关键词（如"土豆"）匹配到大量产品时，采用分层过滤+追问策略：

```
用户输入 → SQL模糊搜索(LIKE + aliases)
        → 结果数量判断:
           ≤ 5条 → 直接返回价格卡片列表
           6-20条 → 按品牌/规格分组，返回摘要列表卡片
           > 20条 → 调用clarify_product，返回分类选择卡片，引导用户细化
```

**示例流程：**

```
用户: "土豆多少钱"
  → 搜到109条，触发追问

AI回复: "土豆品类较多，你需要哪种？"
  + 返回选择卡片:
    ┌─────────────────────────────┐
    │ 请选择土豆类型：              │
    │  [黄皮土豆(整袋)]  [去皮土豆] │
    │  [烧烤土豆(小个)]  [土豆粉]   │
    │  [七彩土豆]                   │
    └─────────────────────────────┘

用户: 点击"黄皮土豆" 或 输入"黄皮土豆 大个"
  → 缩小到3条，返回价格卡片列表
```

**分组规则（clarify_product工具逻辑）：**

1. 按 base_name 中的核心词提取分组（去皮土豆/黄皮土豆/烧烤土豆）
2. 每组显示该组产品数量和价格区间
3. 用户点击或输入后，带上分组条件再次查询

### 4.4 后端项目结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI入口
│   ├── config.py               # 配置(DB/百炼API Key/LangChain)
│   ├── database.py             # SQLAlchemy连接
│   │
│   ├── api/
│   │   ├── chat.py             # POST /api/chat 对话主接口
│   │   ├── auth.py             # 登录/token
│   │   └── prices.py           # 辅助价格查询接口
│   │
│   ├── services/
│   │   ├── ai_service.py       # LangChain Agent构建、工具注册、对话记忆
│   │   ├── price_service.py    # 价格查询/趋势/比价业务逻辑
│   │   └── permission_service.py # 数据权限过滤
│   │
│   ├── tools/                  # LangChain @tool 定义
│   │   ├── __init__.py
│   │   ├── price_tools.py      # query_latest_price, query_price_trend等
│   │   ├── compare_tools.py    # compare_products等
│   │   └── clarify_tools.py    # clarify_product 多结果追问
│   │
│   ├── models/                 # ORM模型
│   │   ├── product.py
│   │   ├── price.py
│   │   ├── category.py
│   │   └── user.py
│   │
│   ├── schemas/                # Pydantic模型
│   │   ├── chat.py             # ChatRequest/ChatResponse/CardData
│   │   └── price.py
│   │
│   └── core/
│       ├── security.py         # JWT
│       ├── prompts.py          # 系统提示词模板
│       └── memory.py           # LangChain对话记忆管理
│
├── requirements.txt
└── .env
```

### 4.5 前端项目结构

```
frontend/
├── src/
│   ├── App.vue
│   ├── main.ts
│   ├── router/index.ts
│   │
│   ├── views/
│   │   ├── ChatView.vue        # 主对话页面
│   │   └── LoginView.vue
│   │
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatInput.vue       # 输入框+快捷提问
│   │   │   ├── MessageList.vue     # 消息列表
│   │   │   ├── UserMessage.vue     # 用户消息气泡
│   │   │   └── AiMessage.vue       # AI消息(含卡片渲染)
│   │   │
│   │   ├── cards/
│   │   │   ├── PriceCard.vue       # 单品价格卡片
│   │   │   ├── PriceListCard.vue   # 价格列表卡片
│   │   │   ├── TrendChartCard.vue  # 趋势图表卡片
│   │   │   ├── CompareCard.vue     # 比价表格卡片
│   │   │   └── AlertCard.vue       # 异常提醒卡片
│   │   │
│   │   └── common/
│   │       └── NotificationBell.vue
│   │
│   ├── api/
│   │   ├── request.ts          # Axios封装
│   │   ├── chat.ts             # 对话接口
│   │   └── auth.ts
│   │
│   ├── stores/
│   │   ├── user.ts
│   │   └── chat.ts             # 对话历史状态
│   │
│   └── types/
│       └── card.ts             # 卡片类型定义
│
├── package.json
└── vite.config.ts
```

## 五、API设计

### 5.1 核心接口

| Method | Path | 描述 |
|--------|------|------|
| POST | /api/auth/login | 登录，返回JWT |
| POST | /api/chat | 对话主接口，接收用户消息，返回AI回复+卡片数据 |
| GET | /api/chat/history | 获取对话历史 |
| GET | /api/notifications/unread | 未读通知数 |

### 5.2 对话接口详细设计

**请求：**
```json
{
  "message": "土豆今天多少钱",
  "conversation_id": "uuid-xxx"
}
```

**响应：**
```json
{
  "reply": "为你查到以下土豆的最新价格：",
  "cards": [
    {
      "type": "price_card",
      "data": {
        "product_name": "[天府山珍]土豆 优质",
        "brand": "天府山珍",
        "spec": "斤",
        "price": 2.50,
        "unit": "元/斤",
        "change_pct": 5.0,
        "price_date": "2026-05-21"
      }
    }
  ],
  "suggestions": ["查看土豆价格趋势", "对比不同品牌土豆", "叶菜类今日价格"]
}
```

### 5.3 卡片类型定义

```typescript
type CardType = 
  | "price_card"        // 单品价格
  | "price_list"        // 价格列表
  | "trend_chart"       // 趋势折线图
  | "compare_table"     // 比价表格
  | "ranking_list"      // 涨跌排行
  | "alert_card"        // 异常提醒
  | "clarify_card"      // 追问选择卡片（多结果时引导用户细化）
```

## 六、权限设计

### 6.1 简化权限模型

聚焦AI助手场景，权限控制数据可见范围：

| 角色 | 数据范围 | 说明 |
|------|---------|------|
| 管理员 | 全部分类 | 可管理用户和权限 |
| 主管 | 全部分类 | 可查看所有数据 |
| 采购员 | 指定二级分类 | 只能查询被授权分类下的产品 |

### 6.2 权限过滤逻辑

AI工具函数执行查询时，自动注入分类过滤条件：

```python
def get_allucts_query(user, base_query):
    if user.role in ('管理员', '主管'):
        return base_query
    allowed_categories = get_user_categories(user.id)  # 二级分类ID列表
    leaf_ids = get_leaf_category_ids(allowed_categories)  # 展开为三级
    return base_query.filter(Product.category_id.in_(leaf_ids))
```

用户问"土豆多少钱"，如果该用户没有"根茎类"权限，AI会回复"你没有该分类的查看权限"。

## 七、数据库新增表

```sql
-- 用户表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    real_name VARCHAR(64) NOT NULL,
    role ENUM('admin', 'manager', 'buyer') NOT NULL DEFAULT 'buyer',
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 用户分类权限表
CREATE TABLE user_category_permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL COMMENT '二级分类ID',
    UNIQUE KEY uk_user_cat (user_id, category_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- 对话历史表
CREATE TABLE chat_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    conversation_id VARCHAR(36) NOT NULL,
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    cards_json JSON COMMENT '卡片数据',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_conv (user_id, conversation_id)
);

-- 通知表
CREATE TABLE notifications (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    title VARCHAR(128) NOT NULL,
    content VARCHAR(512) NOT NULL,
    is_read TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_read (user_id, is_read)
);
```

## 八、技术选型

| 层次 | 技术 | 说明 |
|------|------|------|
| 后端 | FastAPI | 异步，自带OpenAPI文档 |
| ORM | SQLAlchemy 2.0 | 映射已有表 |
| LLM框架 | LangChain | Agent/Tool抽象、对话记忆管理、链式调用 |
| LLM | 阿里云百炼 (通义千问) | 通过LangChain ChatOpenAI兼容接入 |
| 前端 | Vue 3 + TypeScript | Composition API |
| UI库 | Element Plus | 表格/表单/对话框 |
| 图表 | ECharts 5 | 折线图/柱状图 |
| 构建 | Vite | 快速HMR |
| 部署 | Docker Compose | Nginx + FastAPI + MySQL |

## 九、核心Prompt设计

### 9.1 百炼API调用方式（通过LangChain）

使用 LangChain 的 ChatOpenAI 兼容模式接入百炼：

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# 初始化百炼模型
llm = ChatOpenAI(
    api_key="sk-xxx",  # 百炼API Key
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-max"
)

# 定义工具
tools = [query_latest_price, query_price_trend, query_price_ranking, compare_products]

# 构建Agent
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
```

### 9.2 系统提示词

```python
SYSTEM_PROMPT = """你是一个B端采销询价助手。你可以帮助用户查询产品价格、分析价格趋势、对比不同产品价格。

数据库中有以下信息：
- 产品表：10194个产品，包含品名、品牌、规格、品质、分类
- 价格表：每日价格记录，包含价格值和单位
- 分类：三级分类体系（一级：蔬菜水果/调味品 → 二级24个 → 三级242个）

规则：
1. 用户问价格时，调用query_latest_price查询最新价格
2. 用户问趋势时，调用query_price_trend获取历史数据
3. 用户要比价时，调用compare_products进行对比
4. 当搜索结果超过20条时，调用clarify_product返回分组选项，引导用户细化需求
5. 当结果在6-20条时，按品牌/规格分组返回摘要列表
6. 回复要简洁专业，给出关键数据即可
7. 如果查询无结果，友好提示并给出建议
"""
```

## 十、开发计划

| 阶段 | 内容 | 预估工期 |
|------|------|---------|
| P1 | 后端框架搭建 + LangChain Agent + 百炼对接 + 基础询价工具 | 3天 |
| P2 | 前端对话界面 + 价格卡片渲染 | 3天 |
| P3 | 趋势分析 + 比价工具 + 图表卡片 | 3天 |
| P4 | 用户认证 + 权限过滤 | 2天 |
| P5 | 通知 + 对话历史 + 部署 | 2天 |
| **合计** | | **约2周** |

优先级：P1+P2先跑通对话询价闭环，再逐步叠加分析和比价能力。

## 十一、关于RAG

本项目**不需要RAG**。原因：

1. **数据全在结构化数据库中** - 产品、价格、分类都是MySQL表，用SQL查询即可精确获取
2. **多结果问题靠追问解决** - 用户搜"土豆"匹配109条，通过 clarify_product 工具按 base_name 分组后引导用户细化，比向量相似度更精准可控
3. **产品匹配靠SQL+别名** - LIKE搜索 + aliases字段 + 分类树已覆盖模糊匹配需求
4. **RAG适用场景不匹配** - RAG适合从大量非结构化文档中检索，本项目数据源是结构化的价格数据

如果未来需要扩展（比如加入采购政策文档问答、供应商合同条款查询），再引入RAG也不迟。
