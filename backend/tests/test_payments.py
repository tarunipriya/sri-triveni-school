"""Tests for recording payments, showing receipts and cancelling payments.

Every test uses the `db` fixture, so everything it saves is rolled back
afterwards and the demo data never changes.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.conftest import enrollment_id_for

ACCOUNTANT = 2  # "Demo Accountant" in the demo data


def due_id_for(db, enrollment_id, term, fee_type):
    return db.execute(text("""
        SELECT d.id FROM student_dues d
        JOIN terms t     ON t.id = d.term_id
        JOIN fee_heads f ON f.id = d.fee_head_id
        WHERE d.enrollment_id = :e AND t.name = :term AND f.name = :fee_type
    """), {"e": enrollment_id, "term": term, "fee_type": fee_type}).scalar_one()


def last_receipt_no(db):
    return db.execute(text(
        "SELECT last_receipt_no FROM receipt_counters r "
        "JOIN academic_years y ON y.id = r.academic_year_id WHERE y.is_current"
    )).scalar_one()


def balance_of(client, enrollment_id, term, fee_type):
    data = client.get(f"/students/{enrollment_id}/fees").json()
    line = next(l for l in data["lines"] if l["term"] == term and l["fee_type"] == fee_type)
    return Decimal(line["balance"])


def total_pending(client, enrollment_id):
    return Decimal(client.get(f"/students/{enrollment_id}/fees").json()["total_pending"])


def pay(client, enrollment_id, items, mode="cash", **extra):
    body = {
        "enrollment_id": enrollment_id,
        "mode": mode,
        "collected_by": ACCOUNTANT,
        "items": [{"due_id": d, "amount": str(a)} for d, a in items],
        **extra,
    }
    return client.post("/payments", json=body)


@pytest.fixture
def pooja(db):
    """Pooja Varma, Class 7, roll 12: Term 1 Books balance is 2200 in the demo data."""
    return enrollment_id_for("Class 7", 12)


# ---------------------------------------------------------------------
# Recording payments
# ---------------------------------------------------------------------
def test_pay_1000_towards_pooja_books(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    before = last_receipt_no(db)

    response = pay(client, pooja, [(books, 1000)], paid_on="2026-09-24")
    assert response.status_code == 201, response.text
    receipt = response.json()

    assert receipt["receipt_no"] == before + 1
    assert last_receipt_no(db) == before + 1
    assert receipt["school_name"] == "Sri Triveni High School"
    assert receipt["student_name"] == "Pooja Varma"
    assert receipt["class_name"] == "Class 7"
    assert receipt["roll_no"] == 12
    assert receipt["date"] == "2026-09-24"
    assert receipt["status"] == "valid"
    assert receipt["mode"] == "cash"
    assert Decimal(receipt["total"]) == Decimal("1000")
    assert [(i["term"], i["fee_type"], Decimal(i["amount"])) for i in receipt["items"]] == [
        ("Term 1", "Books", Decimal("1000"))
    ]
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("1200")
    assert Decimal(receipt["pending_balance_after_payment"]) == total_pending(client, pooja)


def test_one_payment_can_cover_two_dues(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    uniform = due_id_for(db, pooja, "Term 1", "Uniform")
    pending_before = total_pending(client, pooja)

    response = pay(client, pooja, [(books, 500), (uniform, 1200)],
                   mode="upi", reference_no="UPI-123456")
    assert response.status_code == 201, response.text
    receipt = response.json()

    assert Decimal(receipt["total"]) == Decimal("1700")
    assert len(receipt["items"]) == 2
    assert receipt["reference_no"] == "UPI-123456"
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("1700")
    assert balance_of(client, pooja, "Term 1", "Uniform") == Decimal("0")
    assert Decimal(receipt["pending_balance_after_payment"]) == pending_before - 1700


def test_paid_on_defaults_to_today(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    receipt = pay(client, pooja, [(books, 100)]).json()
    today = db.execute(text("SELECT CURRENT_DATE")).scalar_one()
    assert receipt["date"] == today.isoformat()


def test_two_payments_get_consecutive_receipt_numbers(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    first = pay(client, pooja, [(books, 100)]).json()
    second = pay(client, pooja, [(books, 100)]).json()
    assert second["receipt_no"] == first["receipt_no"] + 1


# ---------------------------------------------------------------------
# Rejected payments
# ---------------------------------------------------------------------
def test_overpaying_a_due_is_rejected(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    before = last_receipt_no(db)

    response = pay(client, pooja, [(books, 2201)])
    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Amount 2201 for due {books} is more than its balance of 2200.00"
    )
    # Nothing was saved and no receipt number was used up
    assert last_receipt_no(db) == before
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("2200")


def test_paying_a_fully_paid_due_is_rejected(client, db, pooja):
    tuition = due_id_for(db, pooja, "Term 1", "Tuition")  # already paid in full
    response = pay(client, pooja, [(tuition, 1)])
    assert response.status_code == 400
    assert "more than its balance of 0.00" in response.json()["detail"]


def test_paying_another_students_due_is_rejected(client, db, pooja):
    other = enrollment_id_for("Class 7", 1)
    other_due = due_id_for(db, other, "Term 2", "Tuition")

    response = pay(client, pooja, [(other_due, 100)])
    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Due {other_due} does not belong to enrollment {pooja}"
    )


def test_one_bad_item_rejects_the_whole_payment(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    uniform = due_id_for(db, pooja, "Term 1", "Uniform")
    before = last_receipt_no(db)

    response = pay(client, pooja, [(books, 500), (uniform, 5000)])
    assert response.status_code == 400
    assert last_receipt_no(db) == before
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("2200")


@pytest.mark.parametrize("mode", ["upi", "cheque"])
def test_upi_and_cheque_need_a_reference_no(client, db, pooja, mode):
    books = due_id_for(db, pooja, "Term 1", "Books")
    for reference in (None, "   "):
        response = pay(client, pooja, [(books, 100)], mode=mode, reference_no=reference)
        assert response.status_code == 422
        assert f"reference_no is required for {mode} payments" in response.text


def test_unknown_enrollment_is_rejected(client, db):
    response = pay(client, 999999, [(1, 100)])
    assert response.status_code == 400
    assert response.json()["detail"] == "Enrollment 999999 does not exist"


def test_empty_items_are_rejected(client, db, pooja):
    response = pay(client, pooja, [])
    assert response.status_code == 422


@pytest.mark.parametrize("amount", ["0", "-50", "10.555"])
def test_bad_amounts_are_rejected(client, db, pooja, amount):
    books = due_id_for(db, pooja, "Term 1", "Books")
    response = pay(client, pooja, [(books, amount)])
    assert response.status_code == 422


def test_same_due_twice_is_rejected(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    response = pay(client, pooja, [(books, 100), (books, 100)])
    assert response.status_code == 400
    assert response.json()["detail"] == "Each due can appear only once in a payment"


def test_unknown_collector_is_rejected(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    response = pay(client, pooja, [(books, 100)], collected_by=999)
    assert response.status_code == 400
    assert response.json()["detail"] == "User 999 does not exist or is not active"


# ---------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------
def test_get_receipt_matches_the_payment(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    created = pay(client, pooja, [(books, 1000)]).json()

    response = client.get(f"/receipts/{created['receipt_no']}")
    assert response.status_code == 200
    assert response.json() == created

    by_year = client.get(f"/receipts/{created['receipt_no']}?academic_year=2026-27")
    assert by_year.json() == created


def test_old_receipt_shows_balance_as_it_was(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    first = pay(client, pooja, [(books, 1000)]).json()
    pay(client, pooja, [(books, 500)])

    reprinted = client.get(f"/receipts/{first['receipt_no']}").json()
    assert reprinted["pending_balance_after_payment"] == first["pending_balance_after_payment"]


def test_unknown_receipt_returns_404(client, db):
    response = client.get("/receipts/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Receipt 999999 not found"


# ---------------------------------------------------------------------
# Cancelling payments
# ---------------------------------------------------------------------
@pytest.mark.parametrize("reason", ["", "   "])
def test_cancelling_without_a_reason_is_rejected(client, db, pooja, reason):
    books = due_id_for(db, pooja, "Term 1", "Books")
    payment_id = pay(client, pooja, [(books, 1000)]).json()["payment_id"]

    response = client.post(f"/payments/{payment_id}/cancel",
                           json={"reason": reason, "cancelled_by": ACCOUNTANT})
    assert response.status_code == 422
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("1200")


def test_cancelling_restores_the_balance(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    receipt = pay(client, pooja, [(books, 1000)]).json()
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("1200")

    response = client.post(f"/payments/{receipt['payment_id']}/cancel",
                           json={"reason": "Wrong student selected", "cancelled_by": ACCOUNTANT})
    assert response.status_code == 200, response.text
    cancelled = response.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_reason"] == "Wrong student selected"
    assert cancelled["receipt_no"] == receipt["receipt_no"]
    assert balance_of(client, pooja, "Term 1", "Books") == Decimal("2200")

    # The payment is kept (never deleted), just marked cancelled
    status = db.execute(text("SELECT status FROM payments WHERE id = :id"),
                        {"id": receipt["payment_id"]}).scalar_one()
    assert status == "cancelled"


def test_cancelling_twice_is_rejected(client, db, pooja):
    books = due_id_for(db, pooja, "Term 1", "Books")
    payment_id = pay(client, pooja, [(books, 1000)]).json()["payment_id"]
    body = {"reason": "Duplicate entry", "cancelled_by": ACCOUNTANT}

    assert client.post(f"/payments/{payment_id}/cancel", json=body).status_code == 200
    again = client.post(f"/payments/{payment_id}/cancel", json=body)
    assert again.status_code == 409
    assert "already cancelled" in again.json()["detail"]


def test_cancelling_unknown_payment_returns_404(client, db):
    response = client.post("/payments/999999/cancel",
                           json={"reason": "Test", "cancelled_by": ACCOUNTANT})
    assert response.status_code == 404
