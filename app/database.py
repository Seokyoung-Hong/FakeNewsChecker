"""Future database bootstrap module placeholder.

Keep this file import-safe and lightweight during prototype phase. It only
contains forward-looking abstractions and does not create real DB connections.
"""

from __future__ import annotations


class DatabaseConfig:
    """Configuration structure for future database wiring."""

    url: str = "sqlite:///./fakenews.db"


class DatabaseUnavailable(RuntimeError):
    """Raised when persistence primitives are used without implementation."""


def get_db_session() -> None:
    """Return a future DB session object.

    This stays a placeholder until SQLAlchemy-backed persistence is implemented.
    """

    raise DatabaseUnavailable(
        "Database persistence is not enabled in the prototype skeleton."
    )


__all__ = ["DatabaseConfig", "DatabaseUnavailable", "get_db_session"]
