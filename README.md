# db-mcp

MCP server for multi-database access with LLM-gated write permissions.

- **Read queries** (SELECT, EXPLAIN, SHOW…) run instantly.
- **Write/destructive queries** (INSERT, UPDATE, DELETE, DROP, ALTER…) require the LLM to show a preview and get explicit user confirmation before executing.
- **Named connections** via `DB_<NAME>=<url>` env vars.
- **Extensible**: any SQLAlchemy-compatible database. Install the driver, use the right URL.

## Supported databases

| Database    | URL format                                        | Extra install          |
|-------------|---------------------------------------------------|------------------------|
| PostgreSQL  | `postgresql://user:pass@host:5432/db`             | included               |
| SQLite      | `sqlite:///./path/to/file.db`                     | included (built-in)    |
| Oracle      | `oracle+oracledb://user:pass@host:1521/service`   | `[oracle]`             |
| MySQL       | `mysql+pymysql://user:pass@host:3306/db`          | `[mysql]`              |
| SQL Server  | `mssql+pyodbc://user:pass@host/db?driver=...`     | `[mssql]`              |
| Any other   | Use the SQLAlchemy URL format + install the driver | custom                 |

## Quick start

```bash
# Clone / copy project
cd db-mcp

# Install (uv recommended)
uv sync

# Extras
uv pip install -e ".[oracle]"
uv pip install -e ".[mysql]"

# Test run
DB_LOCAL=sqlite:///./test.db uv run db-mcp
```

## Configuration

Set `DB_<NAME>=<url>` environment variables. The `<NAME>` part (lowercased) is
what you reference in prompts: *"use the **prod** connection"*.

```bash
# .env
DB_PROD=postgresql://user:pass@db.internal:5432/production
DB_LOCAL=sqlite:///./dev.db
DB_MAX_ROWS=1000   # optional, default 500
```

## VS Code Copilot

Add to `.vscode/mcp.json` (workspace) or `~/.vscode/mcp.json` (global):

```json
{
  "servers": {
    "db-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/db-mcp", "db-mcp"],
      "env": {
        "DB_PROD": "postgresql://user:pass@host:5432/mydb",
        "DB_LOCAL": "sqlite:///./local.db",
        "DB_MAX_ROWS": "500"
      }
    }
  }
}
```

## OpenCode

Add to `~/.config/opencode/config.json` (or `.opencode.json` in your project):

```json
{
  "mcp": {
    "db-mcp": {
      "type": "local",
      "command": ["uv", "run", "--project", "/absolute/path/to/db-mcp", "db-mcp"],
      "environment": {
        "DB_PROD": "postgresql://user:pass@host:5432/mydb",
        "DB_LOCAL": "sqlite:///./local.db",
        "DB_MAX_ROWS": "500"
      }
    }
  }
}
```

## Available tools

| Tool               | Description                                              |
|--------------------|----------------------------------------------------------|
| `list_connections` | List all configured DB connections                       |
| `list_tables`      | List tables and views in a connection                    |
| `describe_table`   | Show columns, PK, FKs, indexes for a table               |
| `query`            | Execute read-only SQL (SELECT, EXPLAIN, etc.)            |
| `preview_mutation` | Preview a write/destructive query → returns token        |
| `execute_mutation` | Execute after user confirms (requires token from above)  |

## How the confirmation flow works

```
LLM calls preview_mutation(connection, sql)
  → returns: preview + one-time token (expires in 5 min)

LLM shows preview to user:
  "This will DELETE 42 rows from orders. Do you confirm?"

User says: "yes"

LLM calls execute_mutation(connection, sql, token)
  → executes, consumes token
```

The token encodes `(connection, sql, expiry)`. If the LLM tries to swap the SQL
or use a different connection, the server rejects it. Tokens are single-use.

## Adding a custom driver

Install any SQLAlchemy-compatible driver and use its URL dialect:

```bash
# Example: Snowflake
uv pip install snowflake-sqlalchemy

# Then set:
DB_SNOW=snowflake://user:pass@account/database/schema
```

The SQLAlchemy dialect registry resolves the driver.

## Environment reference

| Variable       | Default | Description                                      |
|----------------|---------|--------------------------------------------------|
| `DB_<NAME>`    | —       | Connection URL for a named database              |
| `DB_MAX_ROWS`  | `500`   | Max rows returned per `query` call               |
