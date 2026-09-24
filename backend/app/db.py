"""Database connection shared by all API endpoints."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from app.config import settings

# One engine for the whole app; it keeps a pool of reusable connections.
engine = create_engine(settings.database_url, pool_pre_ping=True)


def get_conn() -> Iterator[Connection]:
    """Give each request its own connection, and return it to the pool afterwards."""
    with engine.connect() as conn:
        yield conn
