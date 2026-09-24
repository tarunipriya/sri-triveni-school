"""Shapes of the data the API sends back (validated by Pydantic)."""
from decimal import Decimal

from pydantic import BaseModel


class FeeLine(BaseModel):
    term: str
    fee_type: str
    payable: Decimal   # amount after concession
    paid: Decimal      # sum of VALID payments only (cancelled ones are ignored)
    balance: Decimal   # payable - paid, calculated by the database view


class StudentFees(BaseModel):
    enrollment_id: int
    admission_no: str
    student_name: str
    class_name: str
    roll_no: int
    academic_year: str
    lines: list[FeeLine]
    total_payable: Decimal
    total_paid: Decimal
    total_pending: Decimal
