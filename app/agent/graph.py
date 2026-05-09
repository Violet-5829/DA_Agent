import json
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

from app.agent.prompts import SYSTEM_PROMPT
from app.database.executor import execute_query
from app.services.chart import generate_bar_chart, generate_line_chart
from app.services.llm import get_llm

logger = logging.getLogger("da_agent")


class AgentState(TypedDict, total=False):
    messages: list
    metadata_prompt: str
    reasoning_trace: list[dict[str, Any]]
    sql: str | None
    sql_result: str | None
    chart_url: str | None
    answer: str | None
    error: str | None
    chart_type: str | None
    chart_config: dict[str, str] | None
    query_rows: list[dict] | None
    query_columns: list[str] | None


def _trace(state: AgentState, step: str, detail: dict[str, Any]) -> None:
    """向推理追踪中添加一个步骤。"""
    state["reasoning_trace"].append({"step": step, **detail})


async def analyze_node(state: AgentState) -> AgentState:
    """分析用户意图：澄清问题、查询数据或生成图表。"""
    llm = get_llm(temperature=0.0)
    metadata = state["metadata_prompt"]
    messages = state.get("messages", [])

    # 构造历史对话字符串
    history = ""
    for msg in messages[-6:]:  # 最近 3 轮对话
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content[:500] if hasattr(msg, "content") else str(msg)[:500]
        history += f"{role}: {content}\n"

    prompt = SYSTEM_PROMPT.format(metadata=metadata, history=history)

    full_messages = [
        SystemMessage(content=prompt),
        *messages[-6:],
    ]

    response = await llm.ainvoke(full_messages)
    content = response.content.strip()

    _trace(state, "analyze", {"llm_output": content[:500]})

    # 解析 LLM 返回的 JSON（处理 markdown 代码块）
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # 如果 LLM 没返回有效 JSON，当作直接回答处理
        state["answer"] = content
        state["error"] = None
        _trace(state, "analyze", {"note": "LLM 未返回有效 JSON，作为直接回答处理"})
        return state

    intent = parsed.get("intent", "query")

    if intent == "clarify":
        state["answer"] = parsed.get("clarify_question", "能否请你详细说明一下你的问题？")
        _trace(state, "clarify", {"question": state["answer"]})
        return state

    state["sql"] = parsed.get("sql")
    state["chart_type"] = parsed.get("chart_type")
    state["chart_config"] = parsed.get("chart_config")

    _trace(state, "plan", {"intent": intent, "sql": state.get("sql", "")[:200]})

    return state


def route_after_analyze(state: AgentState) -> Literal["execute", "finalize"]:
    """路由：有 SQL 待执行则到 execute 节点，否则直接 finalize。"""
    if state.get("answer"):  # 已有回答（澄清或错误）
        return "finalize"
    if state.get("sql"):
        return "execute"
    return "finalize"


async def execute_node(state: AgentState) -> AgentState:
    """执行已校验的 SQL 查询。"""
    sql = state["sql"]
    if not sql:
        state["error"] = "没有可执行的 SQL 查询"
        return state

    try:
        result = await execute_query(sql)
        state["sql_result"] = result.to_markdown_table()
        # 保存结构化数据供图表生成使用
        state["query_rows"] = result.to_dicts()
        state["query_columns"] = result.columns
        _trace(state, "execute", {
            "sql": sql[:200],
            "rows_returned": result.row_count,
        })
    except Exception as e:
        logger.error("SQL 执行失败: %s", e)
        state["error"] = str(e)
        _trace(state, "execute", {"error": str(e)})

    return state


def route_after_execute(state: AgentState) -> Literal["chart", "finalize"]:
    """路由：如果需要图表且有数据，则生成图表。"""
    if state.get("error"):
        return "finalize"
    chart_type = state.get("chart_type")
    if chart_type and state.get("query_rows") and len(state["query_rows"]) > 0:
        return "chart"
    return "finalize"


async def chart_node(state: AgentState) -> AgentState:
    """从查询结果生成图表。"""
    chart_type = state.get("chart_type", "bar")
    chart_config = state.get("chart_config", {})
    rows = state.get("query_rows", [])
    columns = state.get("query_columns", [])

    if not rows or not columns:
        state["error"] = "没有可用于生成图表的数据"
        return state

    try:
        labels_col = chart_config.get("labels_col", columns[0])
        values_col = chart_config.get("values_col", columns[1] if len(columns) > 1 else columns[0])

        labels = [str(row.get(labels_col, "")) for row in rows]
        values = [float(row.get(values_col, 0) or 0) for row in rows]

        title = chart_config.get("title", "图表")

        if chart_type == "line":
            url = generate_line_chart(labels, values, title, xlabel=labels_col, ylabel=values_col)
        else:
            url = generate_bar_chart(labels, values, title, xlabel=labels_col, ylabel=values_col)

        state["chart_url"] = url
        _trace(state, "chart", {"chart_type": chart_type, "url": url, "data_points": len(labels)})
    except Exception as e:
        logger.error("图表生成失败: %s", e)
        state["error"] = f"图表生成失败: {e}"
        _trace(state, "chart", {"error": str(e)})

    return state


async def finalize_node(state: AgentState) -> AgentState:
    """生成最终自然语言回答。"""
    llm = get_llm(temperature=0.3)

    sql_result = state.get("sql_result", "")
    chart_url = state.get("chart_url", "")
    error = state.get("error", "")
    messages = state.get("messages", [])

    if error:
        state["answer"] = f"处理过程中遇到错误：{error}"
        return state

    if state.get("answer"):  # 已有回答（澄清或直接回复）
        return state

    last_question = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_question = msg.content[:300]
            break

    summary_prompt = f"""请根据用户的问题和数据查询结果，用中文写一段清晰简洁的分析总结。

用户问题：{last_question}

查询结果：
{sql_result[:2000]}

{"已生成图表: " + chart_url if chart_url else "未生成图表。"}

请用中文写出有帮助的分析。如果结果是表格形式，请描述关键发现。保持简洁。"""

    response = await llm.ainvoke([HumanMessage(content=summary_prompt)])
    state["answer"] = response.content.strip()
    _trace(state, "summarize", {"answer_preview": state["answer"][:200]})

    return state


def build_graph() -> CompiledStateGraph:
    """构建并编译 LangGraph Agent。"""
    builder = StateGraph(AgentState)

    builder.add_node("analyze", analyze_node)
    builder.add_node("execute", execute_node)
    builder.add_node("chart", chart_node)
    builder.add_node("finalize", finalize_node)

    builder.set_entry_point("analyze")

    builder.add_conditional_edges("analyze", route_after_analyze, {
        "execute": "execute",
        "finalize": "finalize",
    })

    builder.add_conditional_edges("execute", route_after_execute, {
        "chart": "chart",
        "finalize": "finalize",
    })

    builder.add_edge("chart", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


# 单例图实例
agent_graph = build_graph()
