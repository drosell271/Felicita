from alembic import command
from alembic.config import Config

from .config import get_settings


def run_migrations() -> None:
    """Actualiza el esquema SQLite al último estado versionado."""
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    command.upgrade(config, "head")
