"""Agent 图结构与路由逻辑测试。"""
import pytest
from langchain_core.messages import HumanMessage

from app.agent.graph import AgentState, build_graph
from app.agent.prompts import SYSTEM_PROMPT


def test_graph_compiles():
    """验证图编译后包含所有预期节点。"""
    graph = build_graph()
    node_names = list(graph.get_graph().nodes.keys())
    assert "analyze" in node_names
    assert "execute" in node_names
    assert "chart" in node_names
    assert "finalize" in node_names


def test_agent_state_schema():
    """验证 AgentState 包含所有必需的字段。"""
    fields = AgentState.__annotations__
    assert "messages" in fields
    assert "metadata_prompt" in fields
    assert "reasoning_trace" in fields
    assert "sql" in fields
    assert "sql_result" in fields
    assert "chart_url" in fields
    assert "answer" in fields
    assert "error" in fields


def test_prompt_has_metadata_placeholder():
    """验证系统提示词模板包含元数据占位符。"""
    assert "{metadata}" in SYSTEM_PROMPT
    assert "{history}" in SYSTEM_PROMPT


def test_graph_routing_with_answer():
    """当已有回答时（澄清场景），路由应指向 finalize。"""
    from app.agent.graph import route_after_analyze

    state: AgentState = {
        "messages": [HumanMessage(content="test")],
        "metadata_prompt": "",
        "reasoning_trace": [],
        "sql": None,
        "sql_result": None,
        "chart_url": None,
        "answer": "Please clarify your question",
        "error": None,
    }
    assert route_after_analyze(state) == "finalize"


def test_graph_routing_with_sql():
    """当存在 SQL 时，路由应指向 execute。"""
    from app.agent.graph import route_after_analyze

    state: AgentState = {
        "messages": [HumanMessage(content="test")],
        "metadata_prompt": "",
        "reasoning_trace": [],
        "sql": "SELECT * FROM users LIMIT 10",
        "sql_result": None,
        "chart_url": None,
        "answer": None,
        "error": None,
    }
    assert route_after_analyze(state) == "execute"


def test_graph_routing_chart():
    """当设置了 chart_type 且有数据时，路由应指向 chart。"""
    from app.agent.graph import route_after_execute

    state: AgentState = {
        "messages": [],
        "metadata_prompt": "",
        "reasoning_trace": [],
        "sql": "SELECT * FROM users",
        "sql_result": "| id | name |\n| --- | --- |\n| 1 | Alice |",
        "chart_url": None,
        "answer": None,
        "error": None,
        "chart_type": "bar",
        "query_rows": [{"id": 1, "name": "Alice"}],
        "query_columns": ["id", "name"],
    }
    assert route_after_execute(state) == "chart"


def test_graph_routing_no_data_no_chart():
    """当设置了 chart_type 但无数据时，不应路由到 chart。"""
    from app.agent.graph import route_after_execute

    state: AgentState = {
        "messages": [],
        "metadata_prompt": "",
        "reasoning_trace": [],
        "sql": "SELECT * FROM users",
        "sql_result": None,
        "chart_url": None,
        "answer": None,
        "error": "Connection failed",
        "chart_type": "bar",
    }
    assert route_after_execute(state) == "finalize"
