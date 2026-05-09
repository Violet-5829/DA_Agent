# 数据分析 Agent

基于自然语言的 MySQL 数据分析服务。用户用中文提问，Agent 自动查询数据库、生成图表、总结结论。提供 **ChatGPT 风格聊天界面**和 **API 文档**两种使用方式。

## 界面预览

| 路径 | 说明 |
|------|------|
| `http://localhost:8000` | 聊天界面（面向普通用户，零门槛） |
| `http://localhost:8000/docs` | API 文档（面向开发者，自定义主题） |

## 架构

```
┌──────────────┐   HTTP POST /chat   ┌──────────────────┐   asyncmy   ┌─────────────┐
│  聊天界面     │ ──────────────────> │   FastAPI 应用    │───────────>│   MySQL     │
│  (index.html) │ <────────────────── │   (端口 8000)     │<───────────│  (只读)     │
└──────────────┘   JSON 响应          └──────────────────┘            └─────────────┘
                                              │
                                        ┌─────┴──────┐
                                        │  LangGraph   │
                                        │  5 节点循环   │
                                        └──────────────┘

Agent 流程:
  analyze ──> execute ──> chart ──> finalize
     │            │           │
     ├── clarify ─┴───────────┘
     └── summarize (闲聊直接回复)

1. analyze:    LLM 解析意图 → 澄清 / 查询 / 图表 / 闲聊回复
2. execute:    校验并执行 SQL（SELECT-only，白名单）
3. chart:      matplotlib 生成图表 PNG → static/
4. finalize:   LLM 用中文总结结果
```

### 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Agent 编排 | **LangGraph** | 显式状态机 + 条件分支，支持查询/澄清/图表/闲聊多意图路由 |
| LLM 集成 | **LangChain** | ChatOpenAI 封装、消息历史管理 |
| Web 框架 | **FastAPI** | 异步原生、自动 OpenAPI、静态文件服务 |
| 数据库驱动 | **asyncmy** | 高性能异步 MySQL，兼容 SQLAlchemy 2.0 |
| 前端 | **纯 HTML/CSS/JS** | 零依赖，单文件聊天界面 |

## 快速开始

### 环境要求
- Python 3.11+
- MySQL 数据库（只读账号）
- DeepSeek API Key（或任意 OpenAI 兼容端点）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# MySQL（必填，建议只读账号）
DATABASE_URL=mysql+asyncmy://用户名:密码@主机:3306/数据库名?charset=utf8mb4

# DeepSeek API（OpenAI 兼容）
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

### 3. 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- 聊天界面：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 4. 测试

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"总共有多少用户？"}'
```

响应：

```json
{
  "answer": "根据查询结果，共有 50,000 名用户...",
  "sql_or_code": "SELECT COUNT(*) AS total FROM netflix_users",
  "chart_url": "/static/chart_abc123.png",
  "reasoning_trace": [
    {"step":"analyze","llm_output":"..."},
    {"step":"plan","intent":"query","sql":"SELECT COUNT(*)..."},
    {"step":"execute","rows_returned":1},
    {"step":"summarize","answer_preview":"根据查询结果..."}
  ],
  "request_id": "a1b2c3d4"
}
```

## API 参考

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 聊天界面主页 |
| `/health` | GET | 数据库状态、已加载表 |
| `/chat` | POST | 发送问题，返回结构化分析 |
| `/docs` | GET | 自定义主题 API 文档 |
| `/openapi.json` | GET | OpenAPI 规范 |

## Docker

```bash
docker-compose up --build
```

### 容器连接宿主机 MySQL

- **Windows / macOS**：主机名用 `host.docker.internal`
- **Linux**：用 `host.docker.internal`（Docker 20.10+）或 `172.17.0.1`

```env
DATABASE_URL=mysql+asyncmy://root:pass@host.docker.internal:3306/mydb?charset=utf8mb4
```

## 安全机制

所有 LLM 生成的 SQL 经 `app/utils/security.py` 双重校验后再执行：

1. **语句检查**：仅允许 `SELECT` / `WITH` (CTE)
2. **关键词拦截**：正则拦截 DROP/INSERT/UPDATE/DELETE/ALTER/CREATE/EXEC 等 16 个危险关键词
3. **表白名单**：提取 FROM/JOIN 子句表名，逐一比对 `ALLOWED_TABLES`
4. **CTE 兼容**：WITH 子句定义的 CTE 名称自动排除，不参与白名单检查

## 配置参考

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | 是 | — | MySQL 连接串（asyncmy 驱动） |
| `DEEPSEEK_API_KEY` | 是 | — | LLM API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | LLM 端点 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-chat` | 模型 ID |
| `ALLOWED_DATABASES` | 是 | — | 允许的数据库（逗号分隔） |
| `ALLOWED_TABLES` | 是 | — | 允许的表（逗号分隔） |
| `DEBUG` | 否 | `false` | 调试日志 |
| `REASONING_TRACE_ENABLED` | 否 | `true` | 响应中包含推理追踪 |

## 运行测试

```bash
pytest -v
```

## 项目结构

```
DA_Agent/
├── app/
│   ├── main.py              # FastAPI 入口，聊天界面 + API 文档
│   ├── config.py            # 环境变量配置（pydantic-settings）
│   ├── agent/
│   │   ├── graph.py         # LangGraph 5 节点状态机
│   │   └── prompts.py       # 系统提示词（含元数据注入）
│   ├── database/
│   │   ├── connection.py    # asyncmy 异步连接池
│   │   ├── metadata.py      # INFORMATION_SCHEMA 元数据加载
│   │   └── executor.py      # 安全 SQL 执行器
│   ├── models/
│   │   └── schemas.py       # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── llm.py           # DeepSeek（ChatOpenAI）封装
│   │   └── chart.py         # matplotlib 图表生成
│   └── utils/
│       ├── logging.py       # Request ID 中间件
│       └── security.py      # SQL 白名单校验器
├── static/
│   ├── index.html           # ChatGPT 风格聊天界面
│   ├── swagger-custom.css   # API 文档自定义主题
│   └── swagger-ui-bundle.js # Swagger UI 本地化
├── tests/
│   ├── test_security.py     # SQL 校验测试
│   └── test_agent.py        # Agent 路由逻辑测试
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```
