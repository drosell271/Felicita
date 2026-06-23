import smtplib
import ssl
from html import escape
from email.utils import make_msgid
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    security: str
    sender_email: str
    sender_name: str = "Equipo"


def _connect(config: SMTPConfig):
    context = ssl.create_default_context()
    if config.security == "ssl":
        server = smtplib.SMTP_SSL(config.host, config.port, timeout=15, context=context)
    else:
        server = smtplib.SMTP(config.host, config.port, timeout=15)
        server.ehlo()
        if config.security == "starttls":
            server.starttls(context=context)
            server.ehlo()
    if config.username:
        server.login(config.username, config.password)
    return server


def test_connection(config: SMTPConfig) -> None:
    with _connect(config) as server:
        server.noop()


def send_card(config: SMTPConfig, recipient: str, subject: str, body: str, image: bytes, filename: str) -> None:
    message = EmailMessage()
    message["From"] = f"{config.sender_name} <{config.sender_email}>"
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    image_cid = make_msgid(domain="felicita.local")
    html_body = escape(body).replace("\n", "<br>")
    message.add_alternative(
        f"""<!doctype html><html><body style="margin:0;background:#f2f2f7;padding:32px 12px">
        <div style="max-width:640px;margin:auto;background:#fafafe;padding:32px;color:#111817;font-family:Georgia,serif;line-height:1.6">
        <div style="border-left:4px solid #ff7f2a;padding-left:18px;margin-bottom:28px">{html_body}</div>
        <img src="cid:{image_cid[1:-1]}" alt="Tarjeta de felicitación" style="display:block;width:100%;height:auto;border:0">
        <p style="margin:24px 0 0;font:11px sans-serif;letter-spacing:.12em;color:#6b716f">FELICITA · CORRESPONDENCIA AUTOMÁTICA</p>
        </div></body></html>""",
        subtype="html",
    )
    message.get_payload()[-1].add_related(
        image, maintype="image", subtype="png", cid=image_cid, filename=filename, disposition="inline"
    )
    with _connect(config) as server:
        server.send_message(message)
