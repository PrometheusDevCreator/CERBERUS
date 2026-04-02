from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str
    SARAH_MODEL: str = "gpt-5.4"
    CLAUDE_MODEL: str = "claude-opus-4-6"
    DATABASE_URL: str
    PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
