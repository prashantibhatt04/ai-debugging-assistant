import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

class Settings:
    ENV: str = os.getenv("ENV", "development")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4.1-mini")
    RATE_LIMIT: str = os.getenv("RATE_LIMIT", "5/minute")
    HISTORY_FILE: str = os.getenv("HISTORY_FILE", "history.json")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Create a single settings instance
settings = Settings()

# Validate required config
if not settings.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in environment variables")

IS_PRODUCTION = settings.ENV == "production"
IS_DEVELOPMENT = settings.ENV == "development"