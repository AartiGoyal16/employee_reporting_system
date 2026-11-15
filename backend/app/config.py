from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, field_validator
from typing import Optional, List, Union
import json
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Employee Work & Weekly Reporting System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # "development", "staging", "production", "test"
    ENABLE_DEMO_USERS: bool = True
    SEED_DEMO_ACCOUNTS: bool = True
    
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
    
    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:4173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return v

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

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
