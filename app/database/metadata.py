from sqlalchemy import text

from app.config import settings
from app.database.connection import get_session


async def load_metadata() -> dict[str, list[dict[str, str]]]:
    """从 INFORMATION_SCHEMA 加载白名单内所有表的列元数据。"""
    allowed_tables = settings.allowed_table_list
    allowed_dbs = settings.allowed_db_list

    if not allowed_tables:
        return {}

    # 解析 (库名, 表名) 对
    pairs: list[tuple[str, str]] = []
    table_keys: dict[str, str] = {}  # (db, table) → display_name
    for table in allowed_tables:
        if "." in table:
            db_name, table_name = table.split(".", 1)
        elif allowed_dbs:
            db_name = allowed_dbs[0]
            table_name = table
        else:
            continue
        pairs.append((db_name, table_name))
        table_keys[(db_name, table_name)] = table_name

    if not pairs:
        return {}

    # 单次查询替代 N 次循环
    placeholders = ", ".join([f"(:db_{i}, :tbl_{i})" for i in range(len(pairs))])
    params = {}
    for i, (db, tbl) in enumerate(pairs):
        params[f"db_{i}"] = db
        params[f"tbl_{i}"] = tbl

    sql = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        f"WHERE (TABLE_SCHEMA, TABLE_NAME) IN ({placeholders}) "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
    )

    metadata: dict[str, list[dict[str, str]]] = {}
    async with await get_session() as session:
        result = await session.execute(text(sql), params)
        for row in result.fetchall():
            key = table_keys.get((row[0], row[1]), row[1])
            if key not in metadata:
                metadata[key] = []
            metadata[key].append({
                "column": row[2],
                "type": row[3],
                "nullable": row[4] == "YES",
            })

    return metadata


def format_metadata_for_prompt(metadata: dict[str, list[dict[str, str]]]) -> str:
    """将元数据格式化为 LLM 系统提示词中的紧凑字符串。"""
    if not metadata:
        return "无可用的表元数据。"

    lines = []
    for table, cols in metadata.items():
        col_str = ", ".join(
            f"{c['column']} ({c['type']}{', nullable' if c['nullable'] else ''})"
            for c in cols
        )
        lines.append(f"  {table}: {col_str}")
    return "数据库表:\n" + "\n".join(lines)
