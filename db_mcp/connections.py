"""Database connection manager.

Reads connection URLs from environment variables prefixed with DB_:
    DB_PROD=postgresql://user:pass@host:5432/mydb
    DB_LOCAL=sqlite:///./local.db
    DB_WAREHOUSE=oracle+oracledb://user:pass@host:1521/service

Connection names are the suffix after DB_, lowercased (e.g. DB_PROD -> 'prod').
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_PREFIX = "DB_"
_RESERVED = {"MAX_ROWS"}  # env vars that are config, not connections


def _load_urls() -> dict[str, str]:
    prefix_upper = _PREFIX.upper()
    return {
        key[len(_PREFIX) :].lower(): val
        for key, val in os.environ.items()
        if key.upper().startswith(prefix_upper)
        and key[len(_PREFIX) :].upper() not in _RESERVED
    }


class ConnectionManager:
    def __init__(self) -> None:
        self._urls: dict[str, str] = _load_urls()
        self._engines: dict[str, Engine] = {}

    def names(self) -> list[str]:
        """Return sorted list of configured connection names."""
        return sorted(self._urls.keys())

    def engine(self, name: str) -> Engine:
        """Return (cached) SQLAlchemy engine for the named connection."""
        key = name.lower()
        if key not in self._engines:
            if key not in self._urls:
                avail = (
                    ", ".join(f"'{n}'" for n in sorted(self._urls)) or "none configured"
                )
                raise ValueError(
                    f"Connection '{name}' not found. Available: {avail}\n"
                    f"Set DB_{name.upper()}=<connection_url> to add it."
                )
            self._engines[key] = create_engine(self._urls[key])
        return self._engines[key]
