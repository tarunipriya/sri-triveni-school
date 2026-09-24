"""Shapes of the data the API sends back (validated by Pydantic)."""
import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


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


# ---------------------------------------------------------------------
# Payments and receipts
# ---------------------------------------------------------------------
# Money: more than 0, at most 2 digits after the decimal point (paise)
Money = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


class PaymentItemIn(BaseModel):
    due_id: int
    amount: Money


class PaymentCreate(BaseModel):
    """What the accountant sends to record a fee payment."""
    enrollment_id: int
    mode: Literal["cash", "upi", "bank", "cheque"]
    reference_no: str | None = Field(default=None, max_length=50)
    paid_on: dt.date | None = None       # empty means "today"
    collected_by: int                    # user id (there is no login yet)
    items: list[PaymentItemIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check_reference_no(self) -> "PaymentCreate":
        # Treat "   " the same as no reference at all
        if self.reference_no is not None:
            self.reference_no = self.reference_no.strip() or None
        if self.mode in ("upi", "cheque") and self.reference_no is None:
            raise ValueError(f"reference_no is required for {self.mode} payments")
        return self


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1)
    cancelled_by: int                    # user id

    @model_validator(mode="after")
    def check_reason(self) -> "CancelRequest":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason must not be empty")
        return self


class ReceiptItem(BaseModel):
    due_id: int
    term: str
    fee_type: str
    amount: Decimal


class Receipt(BaseModel):
    school_name: str
    payment_id: int
    academic_year: str
    receipt_no: int
    date: dt.date
    student_name: str
    admission_no: str
    class_name: str
    roll_no: int
    items: list[ReceiptItem]
    total: Decimal
    mode: str
    reference_no: str | None
    collected_by: str                    # name of the staff member
    status: str                          # 'valid' or 'cancelled'
    cancel_reason: str | None
    # Everything the student still owed for the year right after this payment
    pending_balance_after_payment: Decimal
