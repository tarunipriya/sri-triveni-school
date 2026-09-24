"""Database connection shared by all API endpoints."""
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from app.config import settings

# One engine for the whole app; it keeps a pool of reusable connections.
engine = create_engine(settings.database_url, pool_pre_ping=True)


def get_conn() -> Iterator[Connection]:
    """Give each request its own connection, and return it to the pool afterwards."""
    with engine.connect() as conn:
        yield conn


@contextmanager
def transaction(conn: Connection) -> Iterator[None]:
    """Run a block of database work as ONE transaction: all of it is saved, or none of it.

    If the block finishes normally, the changes are committed (saved).
    If an error is raised inside the block, everything is rolled back (undone).
    Do ALL the queries of a request inside this block.

    Tests wrap each test in an outer transaction that is rolled back at the end,
    so the demo data never changes. In that case we use a SAVEPOINT (a transaction
    inside the transaction) instead, which behaves the same way for our code.
    """
    if conn.in_transaction():
        with conn.begin_nested():
            yield
    else:
        with conn.begin():
            yield
