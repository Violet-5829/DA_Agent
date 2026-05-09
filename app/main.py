import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import text

from app.agent.graph import AgentState, agent_graph
from app.config import settings
from app.database.connection import close_engine, get_engine
from app.database.metadata import format_metadata_for_prompt, load_metadata
from app.models.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse
from app.utils.logging import RequestIDMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("da_agent")

_metadata: dict = {}
_metadata_prompt: str = ""
_db_connected: bool = False

_conversations: dict[str, list] = defaultdict(list)
_conversation_last_access: dict[str, float] = {}
MAX_HISTORY = 20
CONVERSATION_TTL = 3600  # 1 小时未访问则清理


def _evict_stale_conversations():
    """清理过期的对话历史。"""
    now = time.time()
    stale = [
        cid for cid, ts in _conversation_last_access.items()
        if now - ts > CONVERSATION_TTL
    ]
    for cid in stale:
        del _conversations[cid]
        del _conversation_last_access[cid]
    if stale:
        logger.debug("清理了 %d 个过期对话", len(stale))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时连接数据库并加载元数据，关闭时断开连接。"""
    global _metadata, _metadata_prompt, _db_connected
    logger.info("正在启动 DA Agent...")
    if settings.database_url:
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            _db_connected = True
            _metadata = await load_metadata()
            _metadata_prompt = format_metadata_for_prompt(_metadata)
            logger.info(
                "数据库已连接，加载了 %d 张表: %s",
                len(_metadata),
                list(_metadata.keys()),
            )
        except Exception as e:
            logger.error("数据库连接失败: %s", e)
            _db_connected = False
    yield
    await close_engine()
    logger.info("正在关闭 DA Agent...")


app = FastAPI(
    title="数据分析 Agent",
    description="基于自然语言的 MySQL 数据分析接口",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """重定向到 Swagger 文档页。"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        db_connected=_db_connected,
        tables_loaded=len(_metadata),
        metadata_summary={
            table: [{"column": c["column"], "type": c["type"]} for c in cols]
            for table, cols in _metadata.items()
        },
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    """对话接口：运行 LangGraph Agent 并返回结构化响应。"""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())[:8]
    conversation_id = req.conversation_id or request_id

    _evict_stale_conversations()
    _conversation_last_access[conversation_id] = time.time()

    logger.info("[%s] 对话请求: %s", request_id, req.question[:100])

    history = _conversations[conversation_id]
    history.append(HumanMessage(content=req.question))

    if len(history) > MAX_HISTORY:
        del history[: len(history) - MAX_HISTORY]

    initial_state: AgentState = {
        "messages": history,
        "metadata_prompt": _metadata_prompt,
        "reasoning_trace": [],
        "sql": None,
        "sql_result": None,
        "chart_url": None,
        "answer": None,
        "error": None,
    }

    try:
        result = await agent_graph.ainvoke(initial_state)
    except Exception as e:
        logger.exception("[%s] Agent 处理出错", request_id)
        history.append(AIMessage(content=f"错误: {e}"))
        return ChatResponse(
            answer=f"抱歉，处理出错：{e}",
            request_id=request_id,
            reasoning_trace=[{"step": "error", "detail": str(e)}]
            if settings.reasoning_trace_enabled
            else None,
        )

    answer = result.get("answer", "未能生成回答。")
    sql = result.get("sql")
    chart_url = result.get("chart_url")
    trace = result.get("reasoning_trace", [])

    history.append(AIMessage(content=answer))

    logger.info("[%s] 响应已生成，推理步骤: %d", request_id, len(trace))

    return ChatResponse(
        answer=answer,
        sql_or_code=sql,
        chart_url=chart_url,
        reasoning_trace=trace if settings.reasoning_trace_enabled else None,
        request_id=request_id,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())[:8]
    logger.exception("[%s] 未处理错误", request_id)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=str(exc),
            detail=type(exc).__name__,
            request_id=request_id,
        ).model_dump(),
    )
