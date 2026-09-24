"""Shared test setup. Tests run against the demo database (fictional data)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


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
