"""App settings, read from environment variables or a .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where the PostgreSQL database lives
    database_url: str = "postgresql+psycopg://school:school@localhost:5432/school"

    # Printed at the top of every receipt
    school_name: str = "Sri Triveni High School"


settings = Settings()
