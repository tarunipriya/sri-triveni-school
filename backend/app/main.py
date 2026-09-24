"""Entry point of the backend API."""
from fastapi import FastAPI

from app.routers import fees

app = FastAPI(
    title="Sri Triveni High School API",
    description="School management system backend (demo with fictional data).",
    version="0.1.0",
)

app.include_router(fees.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Simple check that the API is running."""
    return {"status": "ok"}
