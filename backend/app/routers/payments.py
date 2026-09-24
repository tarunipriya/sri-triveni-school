"""Fee payments and receipts: record a payment, show a receipt, cancel a payment."""
import datetime as dt
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import settings
from app.db import get_conn, transaction
from app.schemas import CancelRequest, PaymentCreate, Receipt, ReceiptItem

router = APIRouter(tags=["payments"])


# ---------------------------------------------------------------------
# SQL used by the endpoints
# ---------------------------------------------------------------------
ENROLLMENT_SQL = text("SELECT academic_year_id FROM enrollments WHERE id = :enrollment_id")

ACTIVE_USER_SQL = text("SELECT 1 FROM users WHERE id = :user_id AND is_active")

# Make sure the year has a counter row (does nothing if it already exists)
ENSURE_COUNTER_SQL = text("""
    INSERT INTO receipt_counters (academic_year_id, last_receipt_no)
    VALUES (:year_id, 0)
    ON CONFLICT (academic_year_id) DO NOTHING
""")

# FOR UPDATE locks this row until our transaction ends. Any other request that
# wants a receipt number for the same year has to WAIT here until we are done.
LOCK_COUNTER_SQL = text("""
    SELECT last_receipt_no FROM receipt_counters
    WHERE academic_year_id = :year_id
    FOR UPDATE
""")

UPDATE_COUNTER_SQL = text("""
    UPDATE receipt_counters SET last_receipt_no = :receipt_no
    WHERE academic_year_id = :year_id
""")

# Balances come from the due_balances view: they are CALCULATED, never stored.
DUE_BALANCES_SQL = text("""
    SELECT due_id, enrollment_id, balance FROM due_balances
    WHERE due_id = ANY(:due_ids)
""")

INSERT_PAYMENT_SQL = text("""
    INSERT INTO payments (academic_year_id, receipt_no, enrollment_id, amount,
                          mode, reference_no, paid_on, collected_by)
    VALUES (:year_id, :receipt_no, :enrollment_id, :amount,
            :mode, :reference_no, :paid_on, :collected_by)
    RETURNING id
""")

INSERT_ITEM_SQL = text("""
    INSERT INTO payment_items (payment_id, due_id, amount)
    VALUES (:payment_id, :due_id, :amount)
""")

LOCK_PAYMENT_SQL = text("""
    SELECT id, receipt_no, status FROM payments WHERE id = :payment_id FOR UPDATE
""")

CANCEL_PAYMENT_SQL = text("""
    UPDATE payments
    SET status = 'cancelled', cancel_reason = :reason,
        cancelled_by = :cancelled_by, cancelled_at = NOW()
    WHERE id = :payment_id
""")

AUDIT_SQL = text("""
    INSERT INTO audit_log (user_id, action, table_name, record_id, new_data)
    VALUES (:user_id, :action, 'payments', :record_id, CAST(:new_data AS JSONB))
""")

FIND_RECEIPT_SQL = text("""
    SELECT p.id FROM payments p
    JOIN academic_years y ON y.id = p.academic_year_id
    WHERE p.receipt_no = :receipt_no
      AND (y.name = :academic_year OR (CAST(:academic_year AS TEXT) IS NULL AND y.is_current))
""")

RECEIPT_HEADER_SQL = text("""
    SELECT p.id AS payment_id, y.name AS academic_year, p.receipt_no, p.paid_on AS date,
           s.full_name AS student_name, s.admission_no, c.name AS class_name, e.roll_no,
           p.amount AS total, p.mode, p.reference_no, u.full_name AS collected_by,
           p.status, p.cancel_reason, p.enrollment_id
    FROM payments p
    JOIN academic_years y ON y.id = p.academic_year_id
    JOIN enrollments e    ON e.id = p.enrollment_id
    JOIN students s       ON s.id = e.student_id
    JOIN sections sec     ON sec.id = e.section_id
    JOIN classes c        ON c.id = sec.class_id
    JOIN users u          ON u.id = p.collected_by
    WHERE p.id = :payment_id
""")

RECEIPT_ITEMS_SQL = text("""
    SELECT pi.due_id, t.name AS term, f.name AS fee_type, pi.amount
    FROM payment_items pi
    JOIN student_dues d ON d.id = pi.due_id
    JOIN terms t        ON t.id = d.term_id
    JOIN fee_heads f    ON f.id = d.fee_head_id
    WHERE pi.payment_id = :payment_id
    ORDER BY t.term_no, f.id
""")

# Pending balance right after this payment: everything payable for the year,
# minus all VALID payments up to and including this one (payment ids grow over
# time). For a brand-new payment this equals the sum of the due_balances view.
# A reprinted old receipt still shows the balance as it was on that day.
BALANCE_AFTER_SQL = text("""
    SELECT
      (SELECT COALESCE(SUM(d.amount - d.concession), 0)
       FROM student_dues d WHERE d.enrollment_id = :enrollment_id)
      -
      (SELECT COALESCE(SUM(pi.amount), 0)
       FROM payment_items pi
       JOIN payments p     ON p.id = pi.payment_id
       JOIN student_dues d ON d.id = pi.due_id
       WHERE d.enrollment_id = :enrollment_id
         AND p.status = 'valid'
         AND p.id <= :payment_id)
""")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def check_active_user(conn: Connection, user_id: int) -> None:
    if conn.execute(ACTIVE_USER_SQL, {"user_id": user_id}).first() is None:
        raise bad_request(f"User {user_id} does not exist or is not active")


def load_receipt(conn: Connection, payment_id: int) -> Receipt:
    """Collect everything printed on a receipt for one payment."""
    header = dict(conn.execute(RECEIPT_HEADER_SQL, {"payment_id": payment_id}).mappings().one())
    enrollment_id = header.pop("enrollment_id")
    items = conn.execute(RECEIPT_ITEMS_SQL, {"payment_id": payment_id}).mappings().all()
    balance = conn.execute(
        BALANCE_AFTER_SQL, {"enrollment_id": enrollment_id, "payment_id": payment_id}
    ).scalar_one()
    return Receipt(
        school_name=settings.school_name,
        **header,
        items=[ReceiptItem(**item) for item in items],
        pending_balance_after_payment=balance,
    )


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------
@router.post("/payments", response_model=Receipt, status_code=201)
def create_payment(body: PaymentCreate, conn: Connection = Depends(get_conn)) -> Receipt:
    """Record a fee payment and return its receipt.

    Everything happens in ONE transaction: if any check fails, nothing is saved
    and no receipt number is used up.
    """
    with transaction(conn):
        # 1. The enrollment must exist; it tells us the academic year.
        year_id = conn.execute(ENROLLMENT_SQL, {"enrollment_id": body.enrollment_id}).scalar()
        if year_id is None:
            raise bad_request(f"Enrollment {body.enrollment_id} does not exist")

        check_active_user(conn, body.collected_by)

        due_ids = [item.due_id for item in body.items]
        if len(set(due_ids)) != len(due_ids):
            raise bad_request("Each due can appear only once in a payment")

        # 2. Lock this year's receipt counter. From here until COMMIT, no other
        #    payment for this year can run, so the balances we check below
        #    cannot change under our feet and nobody can take our number.
        conn.execute(ENSURE_COUNTER_SQL, {"year_id": year_id})
        last_no = conn.execute(LOCK_COUNTER_SQL, {"year_id": year_id}).scalar_one()

        # 3. Every due must belong to this enrollment, and nobody may overpay.
        balances = {
            row.due_id: row
            for row in conn.execute(DUE_BALANCES_SQL, {"due_ids": due_ids})
        }
        for item in body.items:
            due = balances.get(item.due_id)
            if due is None or due.enrollment_id != body.enrollment_id:
                raise bad_request(
                    f"Due {item.due_id} does not belong to enrollment {body.enrollment_id}"
                )
            if item.amount > due.balance:
                raise bad_request(
                    f"Amount {item.amount} for due {item.due_id} is more than "
                    f"its balance of {due.balance}"
                )

        # 4. Take the next receipt number and save the payment and its items.
        receipt_no = last_no + 1
        conn.execute(UPDATE_COUNTER_SQL, {"year_id": year_id, "receipt_no": receipt_no})
        total = sum(item.amount for item in body.items)
        payment_id = conn.execute(INSERT_PAYMENT_SQL, {
            "year_id": year_id,
            "receipt_no": receipt_no,
            "enrollment_id": body.enrollment_id,
            "amount": total,
            "mode": body.mode,
            "reference_no": body.reference_no,
            "paid_on": body.paid_on or dt.date.today(),
            "collected_by": body.collected_by,
        }).scalar_one()
        conn.execute(INSERT_ITEM_SQL, [
            {"payment_id": payment_id, "due_id": item.due_id, "amount": item.amount}
            for item in body.items
        ])
        conn.execute(AUDIT_SQL, {
            "user_id": body.collected_by,
            "action": "create",
            "record_id": str(payment_id),
            "new_data": json.dumps({"receipt_no": receipt_no, "amount": str(total)}),
        })

        return load_receipt(conn, payment_id)


@router.get("/receipts/{receipt_no}", response_model=Receipt)
def get_receipt(
    receipt_no: int,
    academic_year: str | None = None,
    conn: Connection = Depends(get_conn),
) -> Receipt:
    """Show a receipt. Receipt numbers restart every year, so you can pass
    ?academic_year=2026-27; without it, the current academic year is used."""
    payment_id = conn.execute(
        FIND_RECEIPT_SQL, {"receipt_no": receipt_no, "academic_year": academic_year}
    ).scalar()
    if payment_id is None:
        raise HTTPException(status_code=404, detail=f"Receipt {receipt_no} not found")
    return load_receipt(conn, payment_id)


@router.post("/payments/{payment_id}/cancel", response_model=Receipt)
def cancel_payment(
    payment_id: int, body: CancelRequest, conn: Connection = Depends(get_conn)
) -> Receipt:
    """Cancel a payment. It is never deleted: it stays in the books, marked
    'cancelled' with a reason, and stops counting towards the student's balance."""
    with transaction(conn):
        # Lock the payment row so two people cannot cancel it at the same time.
        payment = conn.execute(LOCK_PAYMENT_SQL, {"payment_id": payment_id}).first()
        if payment is None:
            raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
        if payment.status == "cancelled":
            raise HTTPException(
                status_code=409,
                detail=f"Payment {payment_id} (receipt {payment.receipt_no}) is already cancelled",
            )
        check_active_user(conn, body.cancelled_by)

        conn.execute(CANCEL_PAYMENT_SQL, {
            "payment_id": payment_id,
            "reason": body.reason,
            "cancelled_by": body.cancelled_by,
        })
        conn.execute(AUDIT_SQL, {
            "user_id": body.cancelled_by,
            "action": "cancel",
            "record_id": str(payment_id),
            "new_data": json.dumps({"receipt_no": payment.receipt_no, "reason": body.reason}),
        })

        return load_receipt(conn, payment_id)
