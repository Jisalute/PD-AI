from typing import Iterable, Optional


def _quote_identifier(name: str) -> str:
    return f"`{name}`"


def build_select_list(fields: Iterable[str]) -> str:
    return ", ".join(_quote_identifier(field) for field in fields)


def build_dynamic_select(
    cursor,
    table_name: str,
    where_clause: Optional[str] = None,
    select_fields: Optional[Iterable[str]] = None,
) -> str:
    select_sql = "*" if not select_fields else build_select_list(select_fields)
    sql = f"SELECT {select_sql} FROM {_quote_identifier(table_name)}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    return sql
