import calendar
import csv
import hashlib
import io
import logging
import smtplib
from functools import lru_cache
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from cryptography.fernet import InvalidToken
from email_validator import EmailNotValidError, validate_email
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .database import SessionLocal, get_db
from .migrations import run_migrations
from .email_defaults import ANNIVERSARY_BODY, ANNIVERSARY_SUBJECT, BIRTHDAY_BODY, BIRTHDAY_SUBJECT
from .models import AppSetting, Contact, SendLog
from .scheduler import configure_schedule, start_scheduler, stop_scheduler
from .security import (csrf_token, decrypt_secret, encrypt_secret, login_limiter,
                       require_auth, valid_credentials, validate_csrf)
from .services.dispatch import dispatch_daily, retry_log, smtp_config_from_settings
from .services.email_templates import ALLOWED_MARKERS, validate_message_template
from .services.latex import LatexError, available_templates, compile_image, save_template_source, template_source
from .services.mailer import SMTPConfig, send_card, test_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
MONTH_NAMES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
               "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
CONTACT_SORTS = {
    "name": (Contact.first_name, Contact.last_name, Contact.id),
    "birth": (Contact.birth_date, Contact.first_name, Contact.last_name, Contact.id),
    "anniversary": (Contact.anniversary_date, Contact.first_name, Contact.last_name, Contact.id),
}
CONTACT_CSV_COLUMNS = ("id", "first_name", "last_name", "birth_day", "birth_month",
                       "birth_date", "anniversary_date", "active")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path("data").mkdir(exist_ok=True)
    if len(settings.app_secret) < 32 or settings.app_secret.startswith("change-me"):
        logging.warning("APP_SECRET es débil; configure al menos 32 caracteres aleatorios")
    if len(settings.admin_password) < 16 or settings.admin_password.startswith("change-me"):
        logging.warning("ADMIN_PASSWORD es débil; configure al menos 16 caracteres")
    run_migrations()
    with SessionLocal() as db:
        if not db.get(AppSetting, 1):
            db.add(AppSetting(id=1))
            db.commit()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, same_site="lax",
                   https_only=settings.session_https_only, max_age=8 * 60 * 60)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def page(request: Request, name: str, **context):
    require_auth(request)
    context.update({"request": request, "csrf": csrf_token(request), "app_name": settings.app_name,
                    "timezone": settings.timezone})
    return templates.TemplateResponse(name, context)


def flash_redirect(path: str, message: str, kind: str = "success"):
    return RedirectResponse(f"{path}?message={quote(message)}&kind={kind}", status_code=303)


def format_day_month(value: date | None) -> str:
    if not value:
        return "—"
    return f"{value.day} de {MONTH_NAMES[value.month - 1]}"


def years_since(start: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - start.year
    if (today.month, today.day) < (start.month, start.day):
        years -= 1
    return max(0, years)


def format_anniversary(value: date | None) -> str:
    if not value:
        return "—"
    years = years_since(value)
    label = "año" if years == 1 else "años"
    return f"{format_day_month(value)} de {value.year} ({years} {label})"


templates.env.filters["day_month"] = format_day_month
templates.env.filters["anniversary"] = format_anniversary


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.app_name})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    client_key = request.client.host if request.client else "unknown"
    if login_limiter.is_blocked(client_key):
        return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.app_name,
                                            "error": "Demasiados intentos. Prueba de nuevo más tarde."}, status_code=429)
    if not valid_credentials(username, password):
        login_limiter.record_failure(client_key)
        return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.app_name,
                                            "error": "Credenciales incorrectas"}, status_code=401)
    login_limiter.clear(client_key)
    request.session.clear()
    request.session["authenticated"] = True
    csrf_token(request)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    require_auth(request)
    validate_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = {
        "contacts": db.scalar(select(func.count()).select_from(Contact)) or 0,
        "active": db.scalar(select(func.count()).select_from(Contact).where(Contact.active.is_(True))) or 0,
        "sent": db.scalar(select(func.count()).select_from(SendLog).where(SendLog.status == "sent")) or 0,
        "failed": db.scalar(select(func.count()).select_from(SendLog).where(SendLog.status == "failed")) or 0,
    }
    recent = db.scalars(select(SendLog).order_by(SendLog.sent_at.desc()).limit(8)).all()
    upcoming = _upcoming_events(db, date.today(), 30)[:8]
    config = db.get(AppSetting, 1)
    return page(request, "dashboard.html", stats=stats, recent=recent, upcoming=upcoming, config=config)


def _next_occurrence(value: date, today: date) -> date:
    day = value.day
    if value.month == 2 and value.day == 29 and not calendar.isleap(today.year):
        day = 28
    candidate = date(today.year, value.month, day)
    if candidate < today:
        year = today.year + 1
        day = 29 if value.month == 2 and value.day == 29 and calendar.isleap(year) else (28 if value.month == 2 and value.day == 29 else value.day)
        candidate = date(year, value.month, day)
    return candidate


def _upcoming_events(db: Session, today: date, days: int) -> list[dict]:
    limit_date = today + timedelta(days=days)
    events = []
    for contact in db.scalars(select(Contact).where(Contact.active.is_(True))).all():
        for event_type, value in (("birthday", contact.birth_date), ("anniversary", contact.anniversary_date)):
            if value:
                occurrence = _next_occurrence(value, today)
                if occurrence <= limit_date:
                    events.append({"contact": contact, "event_type": event_type, "date": occurrence,
                                   "days": (occurrence - today).days})
    return sorted(events, key=lambda item: (item["date"], item["contact"].last_name))


@app.get("/contacts", response_class=HTMLResponse)
def contacts_page(request: Request, q: str = "", active: str = "all",
                  sort: str = "name", direction: str = "asc",
                  page_number: int = Query(1, alias="page", ge=1), db: Session = Depends(get_db)):
    query = select(Contact)
    count_query = select(func.count()).select_from(Contact)
    filters = []
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(or_(Contact.first_name.ilike(pattern), Contact.last_name.ilike(pattern)))
    if active in {"true", "false"}:
        filters.append(Contact.active.is_(active == "true"))
    if filters:
        query = query.where(*filters); count_query = count_query.where(*filters)
    total = db.scalar(count_query) or 0
    pages = max(1, (total + settings.page_size - 1) // settings.page_size)
    page_number = min(page_number, pages)
    sort = sort if sort in CONTACT_SORTS else "name"
    direction = direction if direction in {"asc", "desc"} else "asc"
    sort_columns = CONTACT_SORTS[sort]
    order_by = [column.desc() if direction == "desc" else column.asc() for column in sort_columns]
    contacts = db.scalars(query.order_by(*order_by)
                          .offset((page_number - 1) * settings.page_size).limit(settings.page_size)).all()
    base_params = f"q={quote(q)}&active={active}&sort={sort}&direction={direction}"
    sort_links = {}
    for key in CONTACT_SORTS:
        next_direction = "desc" if sort == key and direction == "asc" else "asc"
        sort_links[key] = f"?q={quote(q)}&active={active}&sort={key}&direction={next_direction}&page=1"
    return page(request, "contacts.html", contacts=contacts, q=q, active_filter=active,
                current_page=page_number, pages=pages, total=total, sort=sort,
                direction=direction, base_params=base_params, sort_links=sort_links)


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, status_filter: str = Query("all", alias="status"),
              page_number: int = Query(1, alias="page", ge=1), db: Session = Depends(get_db)):
    query = select(SendLog); count_query = select(func.count()).select_from(SendLog)
    if status_filter in {"sent", "failed", "processing"}:
        query = query.where(SendLog.status == status_filter)
        count_query = count_query.where(SendLog.status == status_filter)
    total = db.scalar(count_query) or 0
    pages = max(1, (total + settings.page_size - 1) // settings.page_size)
    page_number = min(page_number, pages)
    logs = db.scalars(query.order_by(SendLog.sent_at.desc()).offset((page_number - 1) * settings.page_size)
                      .limit(settings.page_size)).all()
    return page(request, "logs.html", logs=logs, status_filter=status_filter,
                current_page=page_number, pages=pages, total=total)


@app.post("/logs/{log_id}/retry")
def retry_send_log(log_id: int, request: Request, csrf: str = Form(...)):
    require_auth(request); validate_csrf(request, csrf)
    try:
        sent = retry_log(log_id)
    except ValueError as exc:
        return flash_redirect("/logs", str(exc), "error")
    return flash_redirect("/logs", "Reintento completado" if sent else "El reintento volvió a fallar",
                          "success" if sent else "error")


def _contact_values(first_name, last_name, birth_day, birth_month, anniversary_date, active):
    try:
        if bool(birth_day) != bool(birth_month):
            raise ValueError("indique el día y el mes de nacimiento")
        # SQLite sigue usando DATE; el año 2000 es un valor neutro y permite el 29 de febrero.
        birth = date(2000, int(birth_month), int(birth_day)) if birth_day else None
        anniversary = date.fromisoformat(anniversary_date) if anniversary_date else None
    except ValueError as exc:
        raise HTTPException(422, f"Datos de contacto no válidos: {exc}") from exc
    if not first_name.strip() or not last_name.strip() or (not birth and not anniversary):
        raise HTTPException(422, "Nombre, apellido y al menos una fecha son obligatorios")
    if len(first_name.strip()) > 60 or len(last_name.strip()) > 60:
        raise HTTPException(422, "Nombre y apellido admiten un máximo de 60 caracteres")
    if anniversary and anniversary > date.today():
        raise HTTPException(422, "La fecha de aniversario no puede estar en el futuro")
    return dict(first_name=first_name.strip(), last_name=last_name.strip(),
                birth_date=birth, anniversary_date=anniversary, active=active == "on")


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "si", "sí", "on", "activo", "activa"}:
        return True
    if normalized in {"0", "false", "no", "off", "inactivo", "inactiva"}:
        return False
    raise ValueError(f"estado activo no válido: {value}")


def _parse_csv_date(value: str, require_year: bool) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
        return parsed if require_year else date(2000, parsed.month, parsed.day)
    except ValueError:
        pass
    normalized = value.lower().replace(" de ", "/").replace(".", "/").replace("-", "/")
    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    if len(parts) == 2 and not require_year:
        day, month = int(parts[0]), _csv_month_number(parts[1])
        return date(2000, month, day)
    if len(parts) == 3:
        first, second, third = parts
        if len(first) == 4:
            year, month, day = int(first), _csv_month_number(second), int(third)
        else:
            day, month, year = int(first), _csv_month_number(second), int(third)
        parsed = date(year, month, day)
        return parsed if require_year else date(2000, parsed.month, parsed.day)
    raise ValueError(f"fecha no válida: {value}")


def _csv_month_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    normalized = value.strip().lower()
    if normalized in MONTH_NAMES:
        return MONTH_NAMES.index(normalized) + 1
    raise ValueError(f"mes no válido: {value}")


def _contact_values_from_csv(row: dict[str, str], active_default: bool = True) -> dict:
    birth_day = (row.get("birth_day") or "").strip()
    birth_month = (row.get("birth_month") or "").strip()
    birth_date = (row.get("birth_date") or "").strip()
    if birth_date and not birth_day and not birth_month:
        parsed_birth = _parse_csv_date(birth_date, require_year=False)
        birth_day = str(parsed_birth.day) if parsed_birth else ""
        birth_month = str(parsed_birth.month) if parsed_birth else ""
    anniversary = _parse_csv_date(row.get("anniversary_date") or "", require_year=True)
    active = "on" if _parse_bool(row.get("active"), default=active_default) else ""
    return _contact_values(row.get("first_name") or "", row.get("last_name") or "",
                           birth_day, birth_month, anniversary.isoformat() if anniversary else "", active)


def _decode_csv_upload(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


@app.post("/contacts")
def create_contact(request: Request, first_name: str = Form(...), last_name: str = Form(...),
                   birth_day: str = Form(""), birth_month: str = Form(""), anniversary_date: str = Form(""),
                   active: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    db.add(Contact(**_contact_values(first_name, last_name, birth_day, birth_month, anniversary_date, active)))
    db.commit()
    return flash_redirect("/contacts", "Contacto creado")


@app.get("/contacts/export")
def export_contacts(request: Request, db: Session = Depends(get_db)):
    require_auth(request)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.DictWriter(output, fieldnames=CONTACT_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    contacts = db.scalars(select(Contact).order_by(Contact.first_name, Contact.last_name, Contact.id)).all()
    for contact in contacts:
        writer.writerow({
            "id": contact.id,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "birth_day": contact.birth_date.day if contact.birth_date else "",
            "birth_month": contact.birth_date.month if contact.birth_date else "",
            "birth_date": f"{contact.birth_date.day:02d}/{contact.birth_date.month:02d}" if contact.birth_date else "",
            "anniversary_date": contact.anniversary_date.isoformat() if contact.anniversary_date else "",
            "active": "true" if contact.active else "false",
        })
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=contactos.csv"})


@app.post("/contacts/import")
async def import_contacts(request: Request, csrf: str = Form(...), file: UploadFile = File(...),
                          db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    if not file.filename.lower().endswith(".csv"):
        return flash_redirect("/contacts", "El archivo debe ser CSV", "error")
    rows = list(csv.DictReader(io.StringIO(_decode_csv_upload(await file.read()))))
    if not rows:
        return flash_redirect("/contacts", "El CSV no contiene contactos", "error")
    created = updated = 0
    try:
        for index, row in enumerate(rows, start=2):
            row = {key.strip(): (value or "").strip() for key, value in row.items() if key}
            if not any(row.values()):
                continue
            contact_id = row.get("id")
            contact = db.get(Contact, int(contact_id)) if contact_id else None
            values = _contact_values_from_csv(row, active_default=contact.active if contact else True)
            if contact:
                for key, value in values.items():
                    setattr(contact, key, value)
                updated += 1
            else:
                db.add(Contact(**values))
                created += 1
    except (ValueError, HTTPException) as exc:
        db.rollback()
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return flash_redirect("/contacts", f"CSV no válido en la línea {index}: {detail}", "error")
    db.commit()
    return flash_redirect("/contacts", f"Importación completada: {created} creados, {updated} actualizados")


@app.post("/contacts/{contact_id}")
def update_contact(contact_id: int, request: Request, first_name: str = Form(...), last_name: str = Form(...),
                   birth_day: str = Form(""), birth_month: str = Form(""), anniversary_date: str = Form(""),
                   active: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    for key, value in _contact_values(first_name, last_name, birth_day, birth_month, anniversary_date, active).items():
        setattr(contact, key, value)
    db.commit()
    return flash_redirect("/contacts", "Contacto actualizado")


@app.post("/contacts/{contact_id}/delete")
def delete_contact(contact_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    contact = db.get(Contact, contact_id)
    if contact:
        db.delete(contact); db.commit()
    return flash_redirect("/contacts", "Contacto eliminado")


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    config = db.get(AppSetting, 1)
    return page(request, "settings.html", config=config,
                birthday_subject=config.birthday_subject_template or BIRTHDAY_SUBJECT,
                birthday_body=config.birthday_body_template or BIRTHDAY_BODY,
                anniversary_subject=config.anniversary_subject_template or ANNIVERSARY_SUBJECT,
                anniversary_body=config.anniversary_body_template or ANNIVERSARY_BODY)


@app.post("/settings/smtp")
def save_smtp(request: Request, smtp_host: str = Form(...), smtp_port: int = Form(...),
              smtp_username: str = Form(""), smtp_password: str = Form(""),
              smtp_security: str = Form(...), sender_email: str = Form(...),
              company_recipient_email: str = Form(...), sender_name: str = Form("Equipo"),
              csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    config = db.get(AppSetting, 1)
    try:
        password = smtp_password or decrypt_secret(config.smtp_password_encrypted)
    except InvalidToken:
        return flash_redirect("/settings", "No se pudo descifrar la contraseña; introdúcela de nuevo", "error")
    try:
        if smtp_security not in {"starttls", "ssl", "none"} or not (1 <= smtp_port <= 65535):
            raise ValueError("Puerto o cifrado no válido")
        if not smtp_host.strip() or not sender_name.strip():
            raise ValueError("Host y nombre de remitente son obligatorios")
        normalized_sender = validate_email(sender_email, check_deliverability=False).normalized
        normalized_recipient = validate_email(company_recipient_email, check_deliverability=False).normalized
    except (EmailNotValidError, ValueError) as exc:
        return flash_redirect("/settings", f"Configuración no válida: {exc}", "error")
    candidate = SMTPConfig(smtp_host.strip(), smtp_port, smtp_username.strip(), password, smtp_security,
                           normalized_sender, sender_name.strip())
    try:
        test_connection(candidate)
    except (OSError, smtplib.SMTPException) as exc:
        return flash_redirect("/settings", f"SMTP rechazado: {exc}", "error")
    config.smtp_host, config.smtp_port, config.smtp_username = candidate.host, candidate.port, candidate.username
    config.smtp_security, config.sender_email, config.sender_name = candidate.security, candidate.sender_email, candidate.sender_name
    config.company_recipient_email = normalized_recipient
    if smtp_password:
        config.smtp_password_encrypted = encrypt_secret(smtp_password)
    db.commit()
    return flash_redirect("/settings", "Conexión SMTP verificada y guardada")


@app.post("/settings/smtp/test")
def send_smtp_test(request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    config = db.get(AppSetting, 1)
    try:
        if not config.company_recipient_email:
            raise ValueError("Falta el destinatario corporativo")
        image = compile_image("birthday", available_templates("birthday")[0],
                              {"NOMBRE": "Equipo", "APELLIDO": "", "AÑOS": "", "FECHA": date.today().strftime("%d/%m/%Y")})
        send_card(smtp_config_from_settings(config), config.company_recipient_email,
                  "[PRUEBA] Felicita", "Este es un mensaje de prueba de la configuración SMTP.",
                  image, "felicita-prueba.png")
    except Exception as exc:
        logging.exception("Falló el email de prueba")
        return flash_redirect("/settings", f"No se pudo enviar la prueba: {str(exc)[:180]}", "error")
    return flash_redirect("/settings", "Email de prueba enviado")


@app.post("/settings/schedule")
def save_schedule(request: Request, send_time: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    try:
        hour, minute = map(int, send_time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "Hora no válida") from exc
    db.get(AppSetting, 1).send_time = f"{hour:02d}:{minute:02d}"
    db.commit(); configure_schedule()
    return flash_redirect("/settings", "Horario actualizado")


@app.post("/settings/emails")
def save_email_templates(request: Request,
                         birthday_subject: str = Form(...), birthday_body: str = Form(...),
                         anniversary_subject: str = Form(...), anniversary_body: str = Form(...),
                         csrf: str = Form(...), db: Session = Depends(get_db)):
    require_auth(request); validate_csrf(request, csrf)
    try:
        values = {
            "birthday_subject_template": validate_message_template(
                birthday_subject, subject=True, allowed_markers=ALLOWED_MARKERS - {"AÑOS"}),
            "birthday_body_template": validate_message_template(
                birthday_body, allowed_markers=ALLOWED_MARKERS - {"AÑOS"}),
            "anniversary_subject_template": validate_message_template(anniversary_subject, subject=True),
            "anniversary_body_template": validate_message_template(anniversary_body),
        }
    except ValueError as exc:
        return flash_redirect("/settings", str(exc), "error")
    config = db.get(AppSetting, 1)
    for field, value in values.items():
        setattr(config, field, value)
    db.commit()
    return flash_redirect("/settings", "Plantillas de email actualizadas")


@app.get("/templates", response_class=HTMLResponse)
def templates_page(request: Request, db: Session = Depends(get_db)):
    items = {kind: available_templates(kind) for kind in ("birthday", "anniversary")}
    preview_versions = {kind: {name: _preview_stamp(kind, name) for name in names} for kind, names in items.items()}
    return page(request, "templates.html", items=items, preview_versions=preview_versions)


@app.get("/templates/{event_type}/{name}/source")
def get_template_source(event_type: str, name: str, request: Request):
    require_auth(request)
    try: return JSONResponse({"source": template_source(event_type, name)})
    except LatexError as exc: raise HTTPException(404, str(exc)) from exc


@app.post("/templates/{event_type}/{name}/source")
def update_template_source(event_type: str, name: str, request: Request,
                           source: str = Form(...), csrf: str = Form(...)):
    require_auth(request); validate_csrf(request, csrf)
    if not source.strip():
        raise HTTPException(422, "La plantilla no puede estar vacía")
    try:
        save_template_source(event_type, name, source)
        _cached_preview.cache_clear()
        return JSONResponse({"message": "Plantilla guardada", "preview_version": _preview_stamp(event_type, name)})
    except LatexError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/templates/{event_type}/{name}/preview")
def preview_template(event_type: str, name: str, request: Request):
    require_auth(request)
    try:
        template_source(event_type, name)
        stamp = _preview_stamp(event_type, name)
        etag = f'"preview-{event_type}-{name}-{stamp}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=86400, immutable"})
        image = _cached_preview_file(event_type, name, stamp)
        return Response(image, media_type="image/png", headers={
            "Content-Disposition": "inline; filename=preview.png",
            "Cache-Control": "private, max-age=86400, immutable",
            "ETag": etag,
        })
    except LatexError as exc: raise HTTPException(500, str(exc)) from exc


def _preview_stamp(event_type: str, name: str) -> str:
    template_path = settings.templates_dir / event_type / f"{name}.tex"
    brand_path = settings.templates_dir / "brand.tex"
    raw = f"{template_path.stat().st_mtime_ns}:{brand_path.stat().st_mtime_ns}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def _cached_preview_file(event_type: str, name: str, stamp: str) -> bytes:
    cache_dir = settings.template_preview_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{event_type}-{name}-{stamp}.png"
    if cache_path.is_file():
        return cache_path.read_bytes()
    image = _cached_preview(event_type, name, stamp)
    cache_path.write_bytes(image)
    return image


@lru_cache(maxsize=12)
def _cached_preview(event_type: str, name: str, _stamp: str) -> bytes:
    return compile_image(event_type, name, {"NOMBRE": "Alex", "APELLIDO": "Rivera",
                                            "AÑOS": 12 if event_type == "anniversary" else "",
                                            "FECHA": date.today().strftime("%d/%m/%Y")})


@app.post("/dispatch/run")
def run_dispatch(request: Request, csrf: str = Form(...)):
    require_auth(request); validate_csrf(request, csrf)
    dispatch_daily()
    return flash_redirect("/", "Comprobación manual finalizada")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 303 and exc.headers and exc.headers.get("Location"):
        return RedirectResponse(exc.headers["Location"], status_code=303)
    if request.headers.get("accept", "").startswith("text/html"):
        return templates.TemplateResponse("error.html", {"request": request, "status": exc.status_code,
                                           "detail": exc.detail, "app_name": settings.app_name}, status_code=exc.status_code)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
