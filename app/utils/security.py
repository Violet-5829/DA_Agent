import re

FORBIDDEN_KEYWORDS = [
    r"\bDROP\b", r"\bTRUNCATE\b", r"\bINSERT\b", r"\bUPDATE\b",
    r"\bDELETE\b", r"\bALTER\b", r"\bCREATE\b", r"\bREPLACE\b",
    r"\bGRANT\b", r"\bREVOKE\b", r"\bEXEC\b", r"\bEXECUTE\b",
    r"\bCALL\b", r"\bLOAD\b", r"\bIMPORT\b", r"\bRENAME\b",
]

FORBIDDEN_PATTERN = re.compile("|".join(FORBIDDEN_KEYWORDS), re.IGNORECASE)
TABLE_REF_PATTERN = re.compile(r"(?:FROM|JOIN)\s+`?(\w+)`?", re.IGNORECASE)


class SQLSecurityError(Exception):
    """SQL 校验失败时抛出。"""


def _extract_cte_names(sql: str) -> set[str]:
    cte_names = set()
    with_match = re.match(r"WITH\s+(.+?)(?=\bSELECT\b)", sql, re.IGNORECASE | re.DOTALL)
    if with_match:
        for m in re.finditer(r"(\w+)\s+AS\s*\(", with_match.group(1), re.IGNORECASE):
            cte_names.add(m.group(1))
    return cte_names


def validate_sql(sql: str, allowed_tables: list[str]) -> None:
    """校验 SQL 是否为仅 SELECT 语句且只访问白名单表。"""
    upper = sql.upper().strip()

    if not upper.startswith("SELECT") and not upper.startswith("WITH"):
        raise SQLSecurityError("仅允许 SELECT 和 WITH (CTE) 查询")

    if FORBIDDEN_PATTERN.search(sql):
        raise SQLSecurityError("SQL 包含禁止的写入/DDL 关键词")

    cte_names = _extract_cte_names(sql)
    tables = set()
    for match in TABLE_REF_PATTERN.finditer(sql):
        t = match.group(1)
        if t.lower() not in {n.lower() for n in cte_names}:
            tables.add(t)

    if not tables:
        raise SQLSecurityError("未能识别 SQL 查询中的表名")

    for table in tables:
        if table not in allowed_tables:
            raise SQLSecurityError(
                f"表 '{table}' 不在允许的白名单中。"
                f"允许的表: {', '.join(allowed_tables)}"
            )
