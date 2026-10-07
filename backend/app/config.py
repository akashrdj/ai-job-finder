import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./job_finder.db")

    # LLM Settings
    LLM_PROVIDER: str = Field(default="gemini") # "gemini", "anthropic", "openai", "mock"
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL: str = Field(default="gemini-3.6-flash")         # Light — company research, gap analysis
    GEMINI_MODEL_HEAVY: str = Field(default="gemini-3.7-flash")   # Heavy — cover letter, resume tailoring
    ANTHROPIC_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_MODEL: str = Field(default="meta-llama/llama-3.2-3b-instruct:free")

    # Ingestion & Matching
    INGESTION_INTERVAL_MINUTES: int = Field(default=15)
    MIN_MATCH_SCORE_FOR_DRAFTING: float = Field(default=60.0)

    # Two-Speed Pipeline & Volume Caps
    MAX_DRAFTS_PER_DAY: int = Field(default=10)         # Max cover letters + resume tailoring per day
    MAX_OUTREACH_PER_DAY: int = Field(default=5)         # Max cold emails / LinkedIn pitches per day
    DRAFTING_SCHEDULE_HOURS: str = Field(default="9,18")  # IST hours when slow lane runs (comma-separated)

    # Email Alerts (Optional)
    ENABLE_EMAIL_ALERTS: bool = Field(default=False)
    SMTP_HOST: str = Field(default="smtp.gmail.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    ALERT_RECIPIENT_EMAIL: str = Field(default="")

    # Job Aggregator APIs (Free Tiers)
    JSEARCH_API_KEY: str = Field(default="")      # Free from https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    ADZUNA_APP_ID: str = Field(default="")         # Free from https://developer.adzuna.com/
    ADZUNA_APP_KEY: str = Field(default="")

    # Optional Lead enrichment
    HUNTER_API_KEY: str = Field(default="")
    SNOV_CLIENT_ID: str = Field(default="")
    SNOV_CLIENT_SECRET: str = Field(default="")

    # Google Sheets Integration (Webhook or Service Account)
    GOOGLE_SHEET_WEBHOOK_URL: str = Field(default="")   # Recommended: Google Apps Script Webhook (no GCP IAM needed)
    GOOGLE_SERVICE_ACCOUNT_JSON: str = Field(default="")
    GOOGLE_SERVICE_ACCOUNT_FILE: str = Field(default="")
    GOOGLE_SHEET_ID: str = Field(default="")
    GOOGLE_SHEET_NAME: str = Field(default="AI Job Finder - Opportunities")
    MIN_FIT_SCORE_FOR_SHEET: float = Field(default=35.0)

    # App meta
    APP_NAME: str = "AI Job Finder & Application Drafter"
    DEBUG: bool = False

settings = Settings()
