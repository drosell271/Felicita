from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Felicita"
    app_secret: str = "change-me-in-production"
    admin_username: str = "admin"
    admin_password: str = "change-me"
    database_url: str = "sqlite:///./data/felicita.db"
    timezone: str = "Europe/Madrid"
    session_https_only: bool = False
    login_max_attempts: int = 5
    login_window_minutes: int = 15
    processing_stale_minutes: int = 30
    page_size: int = 25
    templates_dir: Path = Path("latex_templates")
    latex_work_dir: Path = Path("data/latex")
    template_preview_cache_dir: Path = Path("data/template_previews")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
