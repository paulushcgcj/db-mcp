"""db-mcp: MCP server for multi-database access with LLM permission gating.

Tools:
  list_connections   list configured DB connections
  list_tables        list tables/views in a connection
  describe_table     describe columns, PKs, FKs, indexes
  query              execute read-only SQL (SELECT etc.)
  preview_mutation   preview a write/destructive query, get confirmation token
  execute_mutation   execute after user confirms (requires token)
"""

import os
import secrets
import time
from typing import Any, NamedTuple

from mcp.server.fastmcp import FastMCP
from sqlalchemy import inspect as sa_inspect, text

from db_mcp.classifier import classify
from db_mcp.connections import ConnectionManager

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "db-mcp",
    instructions="""
You have access to one or more databases via db-mcp.

## Rules you MUST follow

1. **Read queries** (`SELECT`, `EXPLAIN`, `SHOW`, `DESCRIBE`): use `query` directly.

2. **Write/destructive queries** (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, etc.):
   - Call `preview_mutation` first.
   - **Show the full preview to the user.**
   - **Explicitly ask**: "Do you confirm running this [type] query on `<connection>`?"
   - Only call `execute_mutation` after the user says **yes**.
   - Never pass `confirmed=true` or call `execute_mutation` without explicit user approval.

3. Use `list_connections` when the user doesn't specify a connection.
4. Use `list_tables` + `describe_table` to explore schema before writing queries.
""",
)

_db = ConnectionManager()
_MAX_ROWS = int(os.getenv("DB_MAX_ROWS", "500"))


class _PendingToken(NamedTuple):
    connection: str
    sql: str
    expires_at: float


_TOKEN_TTL = 300  # seconds
_tokens: dict[str, _PendingToken] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_table(cols: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Format rows as a Markdown table."""

    def cell(v: Any) -> str:
        return "NULL" if v is None else str(v).replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join([header, sep] + body)


def _purge_tokens() -> None:
    now = time.time()
    expired = [k for k, v in _tokens.items() if v.expires_at < now]
    for k in expired:
        del _tokens[k]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_connections() -> str:
    """List all database connections available via DB_<NAME> environment variables."""
    names = _db.names()
    if not names:
        return (
            "No connections configured.\n"
            "Set DB_<NAME>=<connection_url> environment variables, e.g.:\n"
            "  DB_PROD=postgresql://user:pass@host:5432/mydb\n"
            "  DB_LOCAL=sqlite:///./app.db"
        )
    lines = ["Available connections:"] + [f"  - {n}" for n in names]
    return "\n".join(lines)


@mcp.tool()
def list_tables(connection_name: str) -> str:
    """List all tables and views in the specified database connection."""
    engine = _db.engine(connection_name)
    insp = sa_inspect(engine)
    tables = sorted(insp.get_table_names())
    views = sorted(insp.get_view_names())

    lines: list[str] = [f"**{connection_name}**\n"]
    if tables:
        lines += ["**Tables:**"] + [f"  - {t}" for t in tables]
    if views:
        lines += ["\n**Views:**"] + [f"  - {v}" for v in views]
    if not tables and not views:
        lines.append("No tables or views found.")
    return "\n".join(lines)


@mcp.tool()
def describe_table(connection_name: str, table_name: str) -> str:
    """Describe columns, primary key, foreign keys, and indexes for a table."""
    engine = _db.engine(connection_name)
    insp = sa_inspect(engine)

    cols = insp.get_columns(table_name)
    pk = insp.get_pk_constraint(table_name)
    fks = insp.get_foreign_keys(table_name)
    idxs = insp.get_indexes(table_name)

    lines = [f"### `{connection_name}`.`{table_name}`\n", "**Columns:**"]
    for c in cols:
        nullable = "NULL" if c.get("nullable", True) else "NOT NULL"
        default = f" DEFAULT {c['default']}" if c.get("default") else ""
        lines.append(f"  - `{c['name']}` {c['type']} {nullable}{default}")

    if pk and pk.get("constrained_columns"):
        lines.append(f"\n**Primary Key:** {', '.join(pk['constrained_columns'])}")

    if fks:
        lines.append("\n**Foreign Keys:**")
        for fk in fks:
            lines.append(
                f"  - `{', '.join(fk['constrained_columns'])}` -> "
                f"`{fk['referred_table']}({', '.join(fk['referred_columns'])})`"
            )

    if idxs:
        lines.append("\n**Indexes:**")
        for idx in idxs:
            unique = " UNIQUE" if idx.get("unique") else ""
            lines.append(f"  - `{idx['name']}`{unique}: {idx['column_names']}")

    return "\n".join(lines)


@mcp.tool()
def query(connection_name: str, sql: str) -> str:
    """Execute a read-only SQL query on the specified connection."""
    kind = classify(sql)
    if kind != "safe":
        return (
            f"Query classified as **{kind}** -- blocked in `query`.\n\n"
            "Write operations require user confirmation:\n"
            "1. Call `preview_mutation` to get a preview + token\n"
            "2. Show preview to user, ask for confirmation\n"
            "3. Call `execute_mutation` only after user says yes"
        )

    engine = _db.engine(connection_name)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchmany(_MAX_ROWS + 1)
        cols = list(result.keys())

    truncated = len(rows) > _MAX_ROWS
    rows = rows[:_MAX_ROWS]

    if not rows:
        return "Query returned 0 rows."

    out = _fmt_table(cols, rows)
    if truncated:
        out += f"\n\nResults capped at {_MAX_ROWS} rows. Add `LIMIT` to your query."
    else:
        out += f"\n\n{len(rows)} row(s) returned."
    return out


@mcp.tool()
def preview_mutation(connection_name: str, sql: str) -> str:
    """Preview a write or destructive SQL statement and get a one-time confirmation token."""
    kind = classify(sql)
    if kind == "safe":
        return "This query is safe (read-only). Use `query` instead."

    _purge_tokens()
    token = secrets.token_urlsafe(16)
    _tokens[token] = _PendingToken(
        connection=connection_name.lower(),
        sql=sql.strip(),
        expires_at=time.time() + _TOKEN_TTL,
    )

    badge = {
        "mutation": "DATA MODIFICATION",
        "destructive": "DESTRUCTIVE -- POTENTIAL DATA LOSS",
        "unknown": "UNCLASSIFIED QUERY (treated as mutation)",
    }.get(kind, "UNKNOWN")

    return f"""**{badge}**

**Connection:** `{connection_name}`
**Query type:** {kind.upper()}

```sql
{sql.strip()}
```

**Confirmation token:** `{token}`
*(expires in 5 minutes, single-use)*

---
**YOU MUST show the above to the user and ask:**
> "Do you confirm running this {kind} query on `{connection_name}`?"

Only call `execute_mutation` after the user explicitly answers **yes**."""


@mcp.tool()
def execute_mutation(connection_name: str, sql: str, confirmation_token: str) -> str:
    """Execute a confirmed write or destructive SQL statement."""
    _purge_tokens()

    if confirmation_token not in _tokens:
        return (
            "Invalid or expired confirmation token.\n"
            "Call `preview_mutation` again and ask the user for confirmation."
        )

    pending = _tokens[confirmation_token]

    if time.time() > pending.expires_at:
        del _tokens[confirmation_token]
        return "Token expired. Call `preview_mutation` again."

    if pending.connection != connection_name.lower():
        return (
            f"Token was issued for connection `{pending.connection}`, "
            f"not `{connection_name}`. Call `preview_mutation` again."
        )

    if pending.sql != sql.strip():
        return (
            "SQL does not match what was previewed.\n"
            "Call `preview_mutation` again with the exact SQL you intend to run."
        )

    del _tokens[confirmation_token]

    engine = _db.engine(connection_name)
    with engine.begin() as conn:
        result = conn.execute(text(sql))
        affected = result.rowcount

    if affected >= 0:
        return f"Executed successfully. {affected} row(s) affected."
    return "Executed successfully."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
