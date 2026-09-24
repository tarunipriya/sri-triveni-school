"""Shared test setup. Tests run against the demo database (fictional data)."""
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import engine, get_conn
from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db() -> Iterator[Connection]:
    """A database connection whose changes are ALL undone when the test ends.

    1. Open a connection and start a transaction ("outer").
    2. Tell the app to use THIS connection for every request in the test.
       The app's own transactions become savepoints inside our outer one.
    3. After the test, roll back the outer transaction: every payment,
       receipt number and cancellation made by the test disappears,
       so the demo data is exactly as it was before.
    """
    conn = engine.connect()
    outer = conn.begin()
    app.dependency_overrides[get_conn] = lambda: conn
    try:
        yield conn
    finally:
        app.dependency_overrides.pop(get_conn, None)
        outer.rollback()
        conn.close()


def enrollment_id_for(class_name: str, roll_no: int) -> int:
    """Look up a student's enrollment id by class and roll number."""
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT e.id FROM enrollments e
                JOIN sections sec ON sec.id = e.section_id
                JOIN classes c    ON c.id = sec.class_id
                WHERE c.name = :class_name AND e.roll_no = :roll_no
            """),
            {"class_name": class_name, "roll_no": roll_no},
        ).scalar_one()
