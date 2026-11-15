from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional, List
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Employee Work & Weekly Reporting System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # "development", "staging", "production", "test"
    ENABLE_DEMO_USERS: bool = True
    ENABLE_REMINDER_SCHEDULER: bool = True
    
    # Security
    JWT_SECRET_KEY: str = "supersecret_jwt_key_bharatrohan_development_change_in_production_123456"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "employee_reporting_db"
    
    # AI Summary API Configuration
    AI_PROVIDER: str = "auto"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    OPENAI_API_KEY: Optional[str] = None

    # Email / SMTP (optional — falls back to log-only if not set)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: str = "noreply@employee-reporting.local"

    # Deadline reminder day (lowercase weekday name, e.g. 'saturday')
    REMINDER_DAY: str = "saturday"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ]

    @model_validator(mode="after")
    def validate_production_and_security(self):
        env = self.ENVIRONMENT.lower()
        # Production security assertions
        if env == "production":
            # 1. Require strong non-default JWT secret
            insecure_defaults = [
                "supersecret_jwt_key_bharatrohan_development_change_in_production_123456",
                "secret", "change_me", "jwt_secret", "changeme", ""
            ]
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in insecure_defaults or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: In production, JWT_SECRET_KEY must be provided "
                    "via environment variable and must be a strong secret of at least 32 characters."
                )
            # 2. Strict CORS in production (no wildcard with credentials)
            if "*" in self.BACKEND_CORS_ORIGINS:
                raise ValueError(
                    "CORS CONFIGURATION ERROR: Wildcard origin '*' is forbidden in production when credentials are enabled. "
                    "Specify exact frontend domains in BACKEND_CORS_ORIGINS."
                )
            # 3. Disable demo users in production
            self.ENABLE_DEMO_USERS = False

        # In testing mode, disable background reminder loop and email sends
        if env == "test" or os.getenv("TESTING") == "1":
            self.ENABLE_REMINDER_SCHEDULER = False

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
