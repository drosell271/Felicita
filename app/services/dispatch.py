import logging
import random
from datetime import date
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..config import get_settings
from ..models import AppSetting, Contact, SendLog
from ..security import decrypt_secret
from ..email_defaults import ANNIVERSARY_BODY, ANNIVERSARY_SUBJECT, BIRTHDAY_BODY, BIRTHDAY_SUBJECT
from .email_templates import render_message_template
from .latex import available_templates, compile_image
from .mailer import SMTPConfig, send_card

logger = logging.getLogger(__name__)


def _years_since(start: date, today: date) -> int:
    return today.year - start.year


def _matches_today(value: date | None, today: date) -> bool:
    if not value:
        return False
    # El 29/02 se celebra el 28/02 en años no bisiestos.
    if value.month == 2 and value.day == 29 and today.month == 2 and today.day == 28:
        try:
            date(today.year, 2, 29)
        except ValueError:
            return True
    return (value.month, value.day) == (today.month, today.day)


def smtp_config_from_settings(settings: AppSetting) -> SMTPConfig:
    if not settings.smtp_host or not settings.smtp_port or not settings.sender_email:
        raise RuntimeError("Configuración SMTP incompleta")
    return SMTPConfig(settings.smtp_host, settings.smtp_port, settings.smtp_username or "",
                      decrypt_secret(settings.smtp_password_encrypted), settings.smtp_security,
                      settings.sender_email, settings.sender_name)


def dispatch_daily(run_date: date | None = None) -> None:
    today = run_date or datetime.now(ZoneInfo(get_settings().timezone)).date()
    with SessionLocal() as db:
        settings = db.get(AppSetting, 1)
        if not settings:
            logger.warning("No existe configuración de aplicación")
            return
        contacts = db.scalars(select(Contact).where(Contact.active.is_(True))).all()
        for contact in contacts:
            events = []
            if _matches_today(contact.birth_date, today):
                events.append(("birthday", contact.birth_date))
            if _matches_today(contact.anniversary_date, today):
                events.append(("anniversary", contact.anniversary_date))
            for event_type, start_date in events:
                try:
                    _dispatch_one(db, settings, contact, event_type, start_date, today)
                except Exception:
                    db.rollback()
                    logger.exception("Fallo no controlado en %s/%s; el lote continúa", contact.id, event_type)


def _dispatch_one(db, settings, contact, event_type, start_date, today):
    full_name = f"{contact.first_name} {contact.last_name}"
    recipient = settings.company_recipient_email or ""
    log = db.scalar(select(SendLog).where(SendLog.contact_id == contact.id,
                                          SendLog.event_type == event_type,
                                          SendLog.event_date == today))
    if log and log.status == "sent":
        logger.info("Envío ya completado: %s/%s/%s", contact.id, event_type, today)
        return False
    if log and log.status == "processing":
        stale_before = datetime.utcnow() - timedelta(minutes=get_settings().processing_stale_minutes)
        if log.sent_at and log.sent_at > stale_before:
            logger.info("Envío aún en proceso: %s/%s/%s", contact.id, event_type, today)
            return False
        log.status = "failed"
        log.error_message = "Proceso interrumpido; reintento automático"
    if log:
        log.status, log.error_message, log.sent_at = "processing", None, datetime.utcnow()
    else:
        log = SendLog(contact_id=contact.id, contact_name=full_name, recipient_email=recipient,
                      event_type=event_type, event_date=today, status="processing")
        db.add(log)
    if not recipient:
        log.status = "failed"
        log.error_message = "Falta configurar el destinatario corporativo"
        db.commit()
        logger.error("No se envió la felicitación de %s: destinatario no configurado", full_name)
        return False
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Otro proceso reservó el envío: %s/%s/%s", contact.id, event_type, today)
        return False
    try:
        choices = available_templates(event_type)
        template = random.choice(choices)
        years = _years_since(start_date, today) if event_type == "anniversary" else ""
        context = {"NOMBRE": contact.first_name, "APELLIDO": contact.last_name,
                   "AÑOS": years, "FECHA": today.strftime("%d/%m/%Y")}
        image = compile_image(event_type, template, context)
        if event_type == "birthday":
            subject_template = settings.birthday_subject_template or BIRTHDAY_SUBJECT
            body_template = settings.birthday_body_template or BIRTHDAY_BODY
        else:
            subject_template = settings.anniversary_subject_template or ANNIVERSARY_SUBJECT
            body_template = settings.anniversary_body_template or ANNIVERSARY_BODY
        subject = render_message_template(subject_template, context)
        body = render_message_template(body_template, context)
        send_card(smtp_config_from_settings(settings), recipient, subject, body, image, f"{event_type}-{today}.png")
        log.status, log.template_name = "sent", template
        return True
    except Exception as exc:
        logger.exception("Error enviando la felicitación de %s a %s", full_name, recipient or "destinatario no configurado")
        log.status, log.error_message = "failed", str(exc)[:4000]
        return False
    finally:
        db.add(log)
        db.commit()


def retry_log(log_id: int) -> bool:
    with SessionLocal() as db:
        log = db.get(SendLog, log_id)
        if not log or not log.contact_id:
            raise ValueError("Registro o contacto no disponible")
        contact = db.get(Contact, log.contact_id)
        settings = db.get(AppSetting, 1)
        if not contact or not settings:
            raise ValueError("Contacto o configuración no disponible")
        start_date = contact.birth_date if log.event_type == "birthday" else contact.anniversary_date
        if not start_date:
            raise ValueError("La fecha del evento ya no existe")
        log.status = "failed"
        db.commit()
        return _dispatch_one(db, settings, contact, log.event_type, start_date, log.event_date)
