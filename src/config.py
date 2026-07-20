from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    redis_url: str = "redis://redis:6379/0"
    database_url: str = "postgresql+asyncpg://router:changeme@postgres:5432/llm_router"

    complexity_threshold_low: float = 0.3
    complexity_threshold_high: float = 0.7

    provider_preference_order: str = "openai,anthropic,local"

    log_level: str = "INFO"
    environment: str = "development"


settings = Settings()
