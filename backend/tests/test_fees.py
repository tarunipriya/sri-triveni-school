"""Tests for GET /students/{enrollment_id}/fees against the demo data."""
from decimal import Decimal

from sqlalchemy import text

from app.db import engine
from tests.conftest import enrollment_id_for


def line(data, term, fee_type):
    return next(l for l in data["lines"] if l["term"] == term and l["fee_type"] == fee_type)


def test_pooja_varma_class7_roll12_balances(client):
    eid = enrollment_id_for("Class 7", 12)
    response = client.get(f"/students/{eid}/fees")
    assert response.status_code == 200
    data = response.json()

    assert data["student_name"] == "Pooja Varma"
    assert data["class_name"] == "Class 7"
    assert data["roll_no"] == 12
    assert Decimal(line(data, "Term 1", "Books")["balance"]) == Decimal("2200.00")
    assert Decimal(line(data, "Term 1", "Tuition")["balance"]) == Decimal("0")


def test_totals_match_the_lines(client):
    eid = enrollment_id_for("Class 7", 12)
    data = client.get(f"/students/{eid}/fees").json()
    lines = data["lines"]
    assert Decimal(data["total_payable"]) == sum(Decimal(l["payable"]) for l in lines)
    assert Decimal(data["total_paid"]) == sum(Decimal(l["paid"]) for l in lines)
    assert Decimal(data["total_pending"]) == sum(Decimal(l["balance"]) for l in lines)
    for l in lines:
        assert Decimal(l["balance"]) == Decimal(l["payable"]) - Decimal(l["paid"])


def test_cancelled_payments_are_not_counted(client):
    """A student whose payment was cancelled must not get credit for it."""
    with engine.connect() as conn:
        eid, cancelled_amount = conn.execute(text(
            "SELECT enrollment_id, amount FROM payments WHERE status = 'cancelled' LIMIT 1"
        )).one()
        valid_total = conn.execute(text(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE enrollment_id = :e AND status = 'valid'"
        ), {"e": eid}).scalar_one()

    data = client.get(f"/students/{eid}/fees").json()
    assert Decimal(data["total_paid"]) == valid_total


def test_unknown_student_returns_404(client):
    response = client.get("/students/999999/fees")
    assert response.status_code == 404
    assert response.json()["detail"] == "Student enrollment not found"
