# Felicita

Felicita es un panel web para automatizar felicitaciones corporativas de cumpleaños y aniversarios. Genera tarjetas desde plantillas LaTeX, las convierte a PNG y las envía al destinatario corporativo configurado por SMTP.

## Inicio rápido

```bash
cp .env.example .env
# Edita APP_SECRET y ADMIN_PASSWORD antes de arrancar.
docker compose up --build -d
```

Abre `http://localhost:8000` e inicia sesión con las credenciales de `.env`.

La base de datos SQLite y las cachés de trabajo viven en el volumen Docker `felicita_data`.

## Qué incluye

- Backend FastAPI con sesiones, CSRF y limitación básica de intentos de login.
- SQLite con una única migración inicial Alembic.
- Scheduler diario con APScheduler.
- 3 plantillas LaTeX de cumpleaños y 3 de aniversario.
- Previews cacheadas como PNG para que la pantalla de plantillas cargue rápido tras el primer render.
- Editor web para contactos, SMTP, hora de envío y textos de email.
- Envío a un único buzón corporativo; los contactos no almacenan email.
- Cumpleaños guardados solo con día y mes. No se calcula ni se muestra edad.

## Comandos útiles

```bash
# Arrancar / reconstruir
docker compose up --build -d

# Ver logs
docker compose logs -f felicita

# Ejecutar tests locales
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

## Documentación

- [Arquitectura](docs/architecture.md)
- [Operación](docs/operation.md)
- [Plantillas](docs/templates.md)

## Notas de producción

- Usa valores largos y únicos para `APP_SECRET` y `ADMIN_PASSWORD`.
- Si publicas la app detrás de HTTPS, configura `SESSION_HTTPS_ONLY=true`.
- No cambies `APP_SECRET` después de guardar SMTP: la contraseña SMTP se cifra con una clave derivada de ese secreto.
- Ejecuta un solo worker del backend mientras APScheduler viva dentro del proceso.
- Haz backup del volumen `felicita_data`, especialmente `/app/data/felicita.db`.
