from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env first so settings below can be overridden from the environment.
load_dotenv()


class Settings(BaseSettings):
    """Runtime configuration; values come from environment or the .env file."""

    # Provider credentials are kept out of the repository; gateways expect
    # them to be injected via the environment.
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    redis_url: str = "redis://redis:6379/0"
    database_url: str = "postgresql+asyncpg://router:changeme@postgres:5432/llm_router"

    # Prompts scoring below/above these bounds map to cheap / best models.
    complexity_threshold_low: float = 0.3
    complexity_threshold_high: float = 0.7

    # Comma-separated provider names in preference order (first = cheapest).
    provider_preference_order: str = "openai,anthropic,local"

    log_level: str = "INFO"
    environment: str = "development"


settings = Settings()
