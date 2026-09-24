# CLAUDE.md — project guide for Claude Code

## Project
Digital school management system for "Sri Triveni High School": fees, receipts, expenses,
salaries, attendance, marks, and later AI features (WhatsApp voice assistant for parents,
bill scanning, ask-your-data, MCP server, fee reminder agent).
This is a learning/demo project. ALL data is fictional.

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0 (Core, raw SQL with `text()`), psycopg 3
- PostgreSQL 16 (schema in backend/db/schema.sql, demo data in backend/db/seed_demo.sql)
- uv for dependencies, pytest for tests
- Frontend later: Next.js

## Run
- `docker compose up -d` (database), then in backend/: `uv sync`, `uv run uvicorn app.main:app --reload`
- Tests: `uv run pytest` (they run against the demo data)

## API endpoints
- `GET /health`
- `GET /students/{enrollment_id}/fees` — dues and balances (routers/fees.py)
- `POST /payments` — record a payment, returns the receipt (routers/payments.py)
- `GET /receipts/{receipt_no}?academic_year=` — receipt data; default is the current year
- `POST /payments/{payment_id}/cancel` — body `{reason, cancelled_by}`; never deletes

## How to write code here
- Write endpoints that change data inside `with transaction(conn):` (app/db.py), and do
  ALL the queries of the request inside that block.
- Business-rule errors: HTTP 400 with a clear `detail` message. Missing path resources: 404.
  Request-shape errors (Pydantic): 422. Conflicting state (e.g. already cancelled): 409.
- Tests that write data must use the `db` fixture (tests/conftest.py): it rolls back
  everything at the end, so the demo data never changes.

## Rules
1. Never delete payments or expenses. Cancel them with a reason (status = 'cancelled').
2. Balances are always calculated (see the `due_balances` view), never stored.
3. Receipt numbers are gap-free per academic year: lock `receipt_counters`, increment,
   and insert the payment in the same transaction.
4. Roll numbers live on `enrollments` (student + class + year), not on students.
5. AI features may only READ data through approved read-only queries; any change they
   suggest must be confirmed by a person.
6. Parents may only see their own children's data (check `student_parents`).
7. Write tests for every feature. Keep all tests passing.
8. Explain changes simply: the developer is learning.
