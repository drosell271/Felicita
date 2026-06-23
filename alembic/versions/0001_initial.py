"""Esquema inicial consolidado."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("anniversary_date", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("birth_date IS NOT NULL OR anniversary_date IS NOT NULL"),
    )
    op.create_index("ix_contacts_active", "contacts", ["active"])
    op.create_table("app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_username", sa.String(255), nullable=True),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=True),
        sa.Column("smtp_security", sa.String(10), nullable=False, server_default="starttls"),
        sa.Column("sender_email", sa.String(320), nullable=True),
        sa.Column("company_recipient_email", sa.String(320), nullable=True),
        sa.Column("sender_name", sa.String(100), nullable=False, server_default="Equipo"),
        sa.Column("send_time", sa.String(5), nullable=False, server_default="09:00"),
        sa.Column("birthday_subject_template", sa.String(200), nullable=False,
                  server_default="¡Feliz cumpleaños, {{NOMBRE}}!"),
        sa.Column("birthday_body_template", sa.Text(), nullable=False,
                  server_default="Hola {{NOMBRE}}, hoy celebramos tu día."),
        sa.Column("anniversary_subject_template", sa.String(200), nullable=False,
                  server_default="¡Feliz aniversario, {{NOMBRE}}!"),
        sa.Column("anniversary_body_template", sa.Text(), nullable=False,
                  server_default="Hola {{NOMBRE}}, hoy celebramos {{AÑOS}} años de camino compartido."),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("smtp_security IN ('starttls', 'ssl', 'none')"),
        sa.CheckConstraint("smtp_port IS NULL OR smtp_port BETWEEN 1 AND 65535"),
    )
    op.create_table("send_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("contact_name", sa.String(201), nullable=False),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("template_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("contact_id", "event_type", "event_date", name="uq_contact_event_day"),
        sa.CheckConstraint("event_type IN ('birthday', 'anniversary')"),
        sa.CheckConstraint("status IN ('processing', 'sent', 'failed')"),
    )
    op.create_index("ix_send_logs_contact_id", "send_logs", ["contact_id"])
    op.create_index("ix_send_logs_status", "send_logs", ["status"])
    op.execute("INSERT INTO app_settings (id) VALUES (1)")


def downgrade() -> None:
    op.drop_index("ix_send_logs_status", table_name="send_logs")
    op.drop_index("ix_send_logs_contact_id", table_name="send_logs")
    op.drop_table("send_logs")
    op.drop_table("app_settings")
    op.drop_index("ix_contacts_active", table_name="contacts")
    op.drop_table("contacts")
