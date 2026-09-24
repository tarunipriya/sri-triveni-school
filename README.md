# Sri Triveni High School — Digital School Management System

A school management system that replaces handwritten record books with digital records
for fees, receipts, expenses, salaries, attendance and marks, with AI features planned
(WhatsApp voice assistant for parents, bill scanning, ask-your-data, fee reminders).

> **Demo project:** all students, parents, staff and payments are fictional.

## Current status
- Database schema: 27 tables with safety rules (PostgreSQL)
- Fictional demo school: 323 students, fees, payments, attendance, marks, salaries, expenses
- Backend API (FastAPI): see the endpoint list below
- Tests: 30 passing

## API endpoints
| Method | Path | What it does |
|---|---|---|
| GET  | `/health` | Check the API is running |
| GET  | `/students/{enrollment_id}/fees` | A student's dues, payments and balances per term and fee type |
| POST | `/payments` | Record a fee payment (one or more dues) and get the receipt back |
| GET  | `/receipts/{receipt_no}` | Show a receipt (optional `?academic_year=2026-27`, default: current year) |
| POST | `/payments/{payment_id}/cancel` | Cancel a payment with a reason (it is never deleted) |

Example: record a payment
```json
POST /payments
{
  "enrollment_id": 233,
  "mode": "upi",
  "reference_no": "UPI-123456",
  "paid_on": "2026-09-24",
  "collected_by": 2,
  "items": [{"due_id": 1920, "amount": "1000"}]
}
```
- `mode` is `cash`, `upi`, `bank` or `cheque`; `reference_no` is required for `upi` and `cheque`.
- `paid_on` is optional (default: today). `collected_by` is a user id (no login yet).
- Each amount must be more than 0 and not more than that due's current balance.
- Receipt numbers are gap-free per academic year.

Example: cancel a payment
```json
POST /payments/425/cancel
{"reason": "Wrong student selected", "cancelled_by": 2}
```

## Run it
Requirements: Docker Desktop, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Start the database (loads schema + demo data the first time)
docker compose up -d

# 2. Start the API
cd backend
uv sync
uv run uvicorn app.main:app --reload

# 3. Open the interactive API docs
#    http://localhost:8000/docs

# 4. Run the tests
uv run pytest
```

Tests never change the demo data: each test runs inside a database transaction
that is rolled back at the end (see the `db` fixture in `backend/tests/conftest.py`).

No Docker? Install PostgreSQL 16, create a user and database `school` (password `school`),
and load `backend/db/schema.sql` then `backend/db/seed_demo.sql` with `psql -f`.

## Project structure
```
backend/
  app/            FastAPI application
    main.py       app entry point, /health
    config.py     settings (database URL, school name)
    db.py         database connection + transaction() helper
    schemas.py    shapes of API requests and responses
    routers/      endpoints grouped by feature
      fees.py       student fee balances
      payments.py   payments, receipts, cancellations
  db/             schema.sql and seed_demo.sql
  scripts/        generate_demo_data.py (creates seed_demo.sql)
  tests/          pytest tests
docker-compose.yml  PostgreSQL for local development
```
