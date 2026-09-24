"""Fee endpoints."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import get_conn
from app.schemas import FeeLine, StudentFees

router = APIRouter(prefix="/students", tags=["fees"])

STUDENT_SQL = text("""
    SELECT e.id AS enrollment_id, s.admission_no, s.full_name AS student_name,
           c.name AS class_name, e.roll_no, y.name AS academic_year
    FROM enrollments e
    JOIN students s        ON s.id = e.student_id
    JOIN sections sec      ON sec.id = e.section_id
    JOIN classes c         ON c.id = sec.class_id
    JOIN academic_years y  ON y.id = e.academic_year_id
    WHERE e.id = :enrollment_id
""")

# Balances come from the due_balances view: they are CALCULATED, never stored.
FEE_LINES_SQL = text("""
    SELECT t.name AS term, f.name AS fee_type, b.payable, b.paid, b.balance
    FROM due_balances b
    JOIN terms t     ON t.id = b.term_id
    JOIN fee_heads f ON f.id = b.fee_head_id
    WHERE b.enrollment_id = :enrollment_id
    ORDER BY t.term_no, f.id
""")


@router.get("/{enrollment_id}/fees", response_model=StudentFees)
def get_student_fees(enrollment_id: int, conn: Connection = Depends(get_conn)) -> StudentFees:
    """Everything a student owes: per term and fee type, plus totals."""
    student = conn.execute(STUDENT_SQL, {"enrollment_id": enrollment_id}).mappings().first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student enrollment not found")

    rows = conn.execute(FEE_LINES_SQL, {"enrollment_id": enrollment_id}).mappings().all()
    lines = [FeeLine(**row) for row in rows]

    return StudentFees(
        **student,
        lines=lines,
        total_payable=sum((line.payable for line in lines), Decimal("0")),
        total_paid=sum((line.paid for line in lines), Decimal("0")),
        total_pending=sum((line.balance for line in lines), Decimal("0")),
    )
