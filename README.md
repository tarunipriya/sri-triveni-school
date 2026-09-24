# Sri Triveni High School — Digital School Management System

A school management system that replaces handwritten record books with digital records
for fees, receipts, expenses, salaries, attendance and marks, with AI features planned
(WhatsApp voice assistant for parents, bill scanning, ask-your-data, fee reminders).

> **Demo project:** all students, parents, staff and payments are fictional.

## Current status
- Database schema: 27 tables with safety rules (PostgreSQL)
- Fictional demo school: 323 students, fees, payments, attendance, marks, salaries, expenses
- Backend API (FastAPI): `GET /health`, `GET /students/{enrollment_id}/fees`
- Tests: 5 passing

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

## Project structure
```
backend/
  app/            FastAPI application
    main.py       app entry point, /health
    config.py     settings (database URL)
    db.py         database connection
    schemas.py    shapes of API responses
    routers/      endpoints grouped by feature (fees.py)
  db/             schema.sql and seed_demo.sql
  scripts/        generate_demo_data.py (creates seed_demo.sql)
  tests/          pytest tests
docker-compose.yml  PostgreSQL for local development
```
