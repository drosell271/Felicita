from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_empty_database_migrates_to_head(tmp_path):
    database = tmp_path / "test.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    inspector = inspect(engine)
    assert {"contacts", "app_settings", "send_logs", "alembic_version"} <= set(inspector.get_table_names())
    contact_columns = {column["name"] for column in inspector.get_columns("contacts")}
    assert "email" not in contact_columns
    columns = {column["name"] for column in inspector.get_columns("app_settings")}
    assert {"company_recipient_email", "birthday_body_template", "anniversary_body_template"} <= columns
    assert "default_birthday_template" not in columns
    assert "default_anniversary_template" not in columns
