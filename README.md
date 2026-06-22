# db-mcp

MCP server that gives LLM agents read access to any database, with built-in gates for writes.

## Why db-mcp

LLMs handle read-only database work: schema exploration, query writing, data analysis. A stray `DELETE` or `DROP` from an agent can wipe production data. db-mcp draws a hard line: reads go through, writes require the agent to show you exactly what it plans to do and wait for your explicit approval.

## Features

- **Read queries** run immediately: `SELECT`, `EXPLAIN`, `SHOW`, `DESCRIBE`, and `WITH` (when safe).
- **Write and destructive queries** go through a two-step confirmation: the agent previews the change, you approve it.
- **Token-bound execution.** Approval tokens encode the exact SQL and connection. Swap the query or target a different database, and the server rejects it.
- **Named connections** via `DB_<NAME>=<url>` environment variables. No config files to manage.
- **Any SQLAlchemy-compatible database:** PostgreSQL, SQLite, Oracle, MySQL, SQL Server, Snowflake, or whatever you install the driver for.

## Supported databases

| Database    | URL format                                        | Extra install          |
|-------------|---------------------------------------------------|------------------------|
| PostgreSQL  | `postgresql://user:pass@host:5432/db`             | included               |
| SQLite      | `sqlite:///./path/to/file.db`                     | included (built-in)    |
| Oracle      | `oracle+oracledb://user:pass@host:1521/service`   | `[oracle]`             |
| MySQL       | `mysql+pymysql://user:pass@host:3306/db`          | `[mysql]`              |
| SQL Server  | `mssql+pyodbc://user:pass@host/db?driver=...`     | `[mssql]`              |
| Snowflake   | `snowflake://user:pass@account/db/schema`         | `snowflake-sqlalchemy` |

Any other database works too. Install the right SQLAlchemy driver and use its URL format.

## Quick start

```bash
# Install
uv sync

# Run with a local SQLite database
DB_LOCAL=sqlite:///./test.db uv run db-mcp
```

The server starts and your LLM tool can list tables, describe schemas, and run read queries against `local`.

## Configure your connections

Set `DB_<NAME>=<url>` environment variables. The part after `DB_` (lowercased) is the name you reference in prompts.

```bash
DB_PROD=postgresql://user:pass@db.internal:5432/production
DB_LOCAL=sqlite:///./dev.db
DB_MAX_ROWS=1000   # optional, default 500
```

Put these in a `.env` file if you run the server manually.

## Connect your IDE

<details>
<summary><strong>VS Code Copilot</strong></summary>

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

</details>

<details>
<summary><strong>OpenCode</strong></summary>

Add to `~/.config/opencode/config.json` or `.opencode.json` in your project:

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

</details>

## Tools

| Tool               | Description                                              |
|--------------------|----------------------------------------------------------|
| `list_connections` | List all configured DB connections                       |
| `list_tables`      | List tables and views in a connection                    |
| `describe_table`   | Show columns, PK, FKs, indexes for a table               |
| `query`            | Execute read-only SQL (SELECT, EXPLAIN, etc.)            |
| `preview_mutation` | Preview a write/destructive query, get a confirmation token |
| `execute_mutation` | Execute after you confirm (requires token from above)    |

## How writes get approved

Every write or destructive query follows the same flow:

```
Agent calls preview_mutation(connection, sql)
  → Server returns a preview of the change + a one-time token (5-minute TTL)

Agent shows you the preview:
  "This will DELETE 42 rows from orders. Do you confirm?"

You say yes.

Agent calls execute_mutation(connection, sql, token)
  → Server validates the token, executes, and consumes it.
```

The token binds the connection name and the exact SQL to the approval. If the agent tries to run different SQL or target a different connection, the server rejects the token. Tokens expire after 5 minutes and can only be used once.

## Custom drivers

Install any SQLAlchemy-compatible driver and use its URL dialect:

```bash
# Example: Snowflake
uv pip install snowflake-sqlalchemy

# Then set:
DB_SNOW=snowflake://user:pass@account/database/schema
```

The SQLAlchemy dialect registry resolves the driver from the URL prefix.

## Environment reference

| Variable       | Default | Description                                      |
|----------------|---------|--------------------------------------------------|
| `DB_<NAME>`    | —       | Connection URL for a named database              |
| `DB_MAX_ROWS`  | `500`   | Max rows returned per `query` call               |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR guidelines.

## License

[GPL-3.0](LICENSE)
