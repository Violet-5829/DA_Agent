# 数据分析 Agent

基于自然语言的 MySQL 数据分析后端服务。用户用自然语言提问，Agent 自动查询数据库、生成图表、总结结论 —— 全部通过 REST API 完成。

## 架构

```
┌─────────────┐     POST /chat      ┌──────────────────┐     ┌─────────────┐
│   客户端     │ ──────────────────> │   FastAPI 应用    │────>│   MySQL     │
│  (curl/App) │ <────────────────── │   (端口 8000)     │<────│  (只读)     │
└─────────────┘    JSON 响应        └──────────────────┘     └─────────────┘
                                          │
                                    ┌─────┴──────┐
                                    │  LangGraph   │
                                    │  Agent 循环   │
                                    └──────────────┘

Agent 流程（LangGraph 节点）:
  analyze ──> execute ──> chart ──> finalize
     │            │                    │
     └── clarify ─────────────────────┘

1. analyze:   LLM 解析意图，判断是否需要澄清，生成 SQL
2. execute:   校验并执行 SQL（仅 SELECT，白名单表）
3. chart:     生成 matplotlib 图表 PNG，保存至 static/
4. finalize:  LLM 用自然语言总结结果
```

### 技术选型

| 组件 | 选型 | 理由 |
|-----------|--------|-----|
| Agent 编排 | **LangGraph** | 显式状态机 + 条件分支 —— Agent 需要在"查询 vs 澄清 vs 图表"之间决策，图式控制流比 ReAct 循环更适合此场景。 |
| LLM 集成 | **LangChain** | 成熟的 ChatOpenAI 封装、内置工具抽象、消息历史工具 —— 避免重复造轮子。 |
| Web 框架 | **FastAPI** | 原生异步、自动生成 OpenAPI 文档、内置静态文件服务。 |
| 数据库驱动 | **asyncmy** | 高性能异步 MySQL 驱动，兼容 SQLAlchemy 2.0 异步引擎。 |

## 快速开始

### 环境要求
- Python 3.11+
- MySQL 数据库（只读账号）
- DeepSeek API Key（或其他 OpenAI 兼容的 LLM 端点）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入实际值：

```env
# MySQL（必填）—— 建议使用只读账号
DATABASE_URL=mysql+asyncmy://用户名:密码@主机:3306/数据库名?charset=utf8mb4

# DeepSeek API
DEEPSEEK_API_KEY=sk-your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 表白名单（逗号分隔）
ALLOWED_DATABASES=mydb
ALLOWED_TABLES=users,orders,products

# 可选
DEBUG=false
REASONING_TRACE_ENABLED=true
```

### 3. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 http://localhost:8000/docs 查看 Swagger 交互文档。

### 4. 测试接口

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "上个月有多少订单？"}'
```

响应示例：

```json
{
  "answer": "上个月共有 342 笔订单，总金额 56,230 元...",
  "sql_or_code": "SELECT COUNT(*) as order_count FROM orders WHERE created_at >= '2025-04-01'",
  "chart_url": null,
  "reasoning_trace": [
    {"step": "analyze", "llm_output": "..."},
    {"step": "plan", "intent": "query", "sql": "SELECT COUNT(*)..."},
    {"step": "execute", "sql": "SELECT COUNT(*)...", "rows_returned": 1},
    {"step": "summarize", "answer_preview": "上个月共有 342 笔订单..."}
  ],
  "request_id": "a1b2c3d4"
}
```

## Docker 部署

```bash
docker-compose up --build
```

服务启动后访问 `http://localhost:8000`。

### 容器内连接宿主机 MySQL

- **Windows / macOS**：`DATABASE_URL` 中的主机名使用 `host.docker.internal`
  ```
  DATABASE_URL=mysql+asyncmy://用户名:密码@host.docker.internal:3306/数据库名?charset=utf8mb4
  ```
- **Linux**：使用 `host.docker.internal`（Docker 20.10+）或 `172.17.0.1`（默认网桥网关）

### 连通性检查清单
1. 确保 MySQL 用户对白名单表具有 `SELECT` 权限
2. 确保 MySQL 绑定地址允许 Docker 连接（`0.0.0.0` 或包含 Docker 网络段）
3. 确保 `ALLOWED_DATABASES` 和 `ALLOWED_TABLES` 与实际库表名称完全一致
4. 配置好 `.env` 后即可使用，无需额外导入脚本

## API 参考

| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/health` | GET | 数据库连接状态、已加载的表 |
| `/chat` | POST | 发送问题，获取结构化分析结果 |
| `/docs` | GET | Swagger 交互文档 |

### POST /chat

**请求：**
```json
{
  "question": "显示销售额最高的 5 个产品",
  "conversation_id": "可选，之前对话的 ID"
}
```

**成功响应 (200)：**
```json
{
  "answer": "销售额最高的 5 个产品是...",
  "sql_or_code": "SELECT product_name, SUM(amount) ...",
  "chart_url": "/static/chart_abc123.png",
  "reasoning_trace": [...],
  "request_id": "a1b2c3d4"
}
```

**错误响应 (500)：**
```json
{
  "error": "表 'secret' 不在允许的白名单中。允许的表: users, orders, products",
  "detail": "SQLSecurityError",
  "request_id": "a1b2c3d4"
}
```

## 安全机制：SQL 执行模型

所有面向用户的 SQL 在执行前均经过 `app/utils/security.py` 校验：

1. **语句检查**：仅允许 `SELECT` 和 `WITH` (CTE) 查询
2. **关键词拦截**：通过正则拦截 `DROP`、`TRUNCATE`、`INSERT`、`UPDATE`、`DELETE`、`ALTER`、`CREATE`、`EXEC`、`GRANT`、`REVOKE`、`CALL`、`LOAD`、`IMPORT`、`RENAME`
3. **表白名单**：提取 `FROM`/`JOIN` 子句中的表名，逐一校验是否在 `ALLOWED_TABLES` 内
4. **CTE 兼容**：`WITH` 子句中定义的 CTE 名称自动排除，不参与白名单校验

## 更换 LLM 模型

编辑 `.env`：

```env
# 使用 DeepSeek Reasoner 模型
DEEPSEEK_MODEL=deepseek-reasoner

# 或使用任意 OpenAI 兼容端点
DEEPSEEK_BASE_URL=https://your-proxy.com/v1
DEEPSEEK_MODEL=your-model-id
```

LLM 客户端 (`app/services/llm.py`) 基于 LangChain 的 `ChatOpenAI`，兼容所有 OpenAI 格式的 API。

## 配置参考

| 变量 | 必填 | 默认值 | 说明 |
|----------|----------|---------|-------------|
| `DATABASE_URL` | 是 | — | MySQL 连接串（asyncmy 驱动） |
| `DEEPSEEK_API_KEY` | 是 | — | LLM API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | LLM 端点地址 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-chat` | 模型 ID |
| `ALLOWED_DATABASES` | 是 | — | 允许的数据库名（逗号分隔） |
| `ALLOWED_TABLES` | 是 | — | 允许的表名（逗号分隔） |
| `DEBUG` | 否 | `false` | 开启调试日志 |
| `REASONING_TRACE_ENABLED` | 否 | `true` | 响应中是否包含推理追踪 |

## 运行测试

```bash
pytest -v
```

测试覆盖：
- SQL 安全校验器（合法/非法查询、白名单校验）
- Agent 图结构与路由逻辑

## 项目结构

```
DA_Agent/
├── app/
│   ├── main.py              # FastAPI 入口，端点定义
│   ├── config.py            # 环境变量配置
│   ├── agent/
│   │   ├── graph.py         # LangGraph 状态机
│   │   ├── tools.py         # LangChain 工具（SQL、图表）
│   │   └── prompts.py       # 系统提示词模板
│   ├── database/
│   │   ├── connection.py    # 异步 MySQL 连接池
│   │   ├── metadata.py      # INFORMATION_SCHEMA 元数据加载
│   │   └── executor.py      # 安全 SQL 执行器
│   ├── models/
│   │   └── schemas.py       # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── llm.py           # DeepSeek（ChatOpenAI）封装
│   │   └── chart.py         # Matplotlib 图表生成
│   └── utils/
│       ├── logging.py       # Request ID 中间件
│       └── security.py      # SQL 白名单校验器
├── static/                  # 生成的图表 PNG 文件
├── tests/
│   ├── test_security.py     # SQL 校验测试
│   └── test_agent.py        # Agent 图测试
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```
