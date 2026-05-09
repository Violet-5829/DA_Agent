import logging

from sqlalchemy import text

from app.config import settings
from app.database.connection import get_session
from app.utils.security import validate_sql

logger = logging.getLogger("da_agent")


class QueryResult:
    """SQL 执行结果容器。"""

    def __init__(self, columns: list[str], rows: list[tuple], row_count: int):
        self.columns = columns
        self.rows = rows
        self.row_count = row_count

    def to_dicts(self) -> list[dict]:
        return [dict(zip(self.columns, row)) for row in self.rows]

    def to_markdown_table(self) -> str:
        if not self.rows:
            return "（空结果）"
        header = "| " + " | ".join(self.columns) + " |"
        sep = "|" + "|".join([" --- " for _ in self.columns]) + "|"
        body = "\n".join(
            "| " + " | ".join(str(v) for v in row) + " |" for row in self.rows
        )
        return f"{header}\n{sep}\n{body}"


async def execute_query(sql: str) -> QueryResult:
    """执行已校验的 SELECT 查询并返回结果。"""
    validate_sql(sql, settings.allowed_table_list)

    logger.info("正在执行 SQL: %s", sql[:200])

    async with await get_session() as session:
        result = await session.execute(text(sql))
        rows = result.fetchall()
        columns = list(result.keys())
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))
