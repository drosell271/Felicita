from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .email_defaults import ANNIVERSARY_BODY, ANNIVERSARY_SUBJECT, BIRTHDAY_BODY, BIRTHDAY_SUBJECT


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date | None] = mapped_column(Date)
    anniversary_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (CheckConstraint("birth_date IS NOT NULL OR anniversary_date IS NOT NULL"),)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int | None] = mapped_column(Integer)
    smtp_username: Mapped[str | None] = mapped_column(String(255))
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text)
    smtp_security: Mapped[str] = mapped_column(String(10), default="starttls")
    sender_email: Mapped[str | None] = mapped_column(String(320))
    company_recipient_email: Mapped[str | None] = mapped_column(String(320))
    sender_name: Mapped[str] = mapped_column(String(100), default="Equipo")
    send_time: Mapped[str] = mapped_column(String(5), default="09:00")
    birthday_subject_template: Mapped[str] = mapped_column(String(200), default=BIRTHDAY_SUBJECT)
    birthday_body_template: Mapped[str] = mapped_column(Text, default=BIRTHDAY_BODY)
    anniversary_subject_template: Mapped[str] = mapped_column(String(200), default=ANNIVERSARY_SUBJECT)
    anniversary_body_template: Mapped[str] = mapped_column(Text, default=ANNIVERSARY_BODY)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("smtp_security IN ('starttls', 'ssl', 'none')"),
        CheckConstraint("smtp_port IS NULL OR smtp_port BETWEEN 1 AND 65535"),
    )


class SendLog(Base):
    __tablename__ = "send_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    contact_name: Mapped[str] = mapped_column(String(201))
    recipient_email: Mapped[str] = mapped_column(String(320))
    event_type: Mapped[str] = mapped_column(String(20))
    event_date: Mapped[date] = mapped_column(Date)
    template_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("contact_id", "event_type", "event_date", name="uq_contact_event_day"),
        CheckConstraint("event_type IN ('birthday', 'anniversary')"),
        CheckConstraint("status IN ('processing', 'sent', 'failed')"),
    )
