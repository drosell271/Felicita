# Arquitectura

## Componentes

```text
app/
├── main.py              # Rutas HTTP, formularios y ciclo de vida FastAPI
├── scheduler.py         # Programación diaria APScheduler
├── models.py            # Modelo SQLAlchemy
├── migrations.py        # Ejecución de Alembic al arrancar
├── security.py          # Sesión, CSRF, login y cifrado de secretos
├── services/
│   ├── dispatch.py      # Selección de eventos, render y envío
│   ├── latex.py         # Render LaTeX, compilación PDF y conversión a PNG
│   ├── mailer.py        # SMTP y email HTML/texto
│   └── email_templates.py
├── templates/           # Vistas Jinja2
└── static/              # CSS, JS y favicon

latex_templates/
├── brand.tex            # Paleta y macros compartidas
├── birthday/            # Tres plantillas de cumpleaños
└── anniversary/         # Tres plantillas de aniversario

alembic/versions/
└── 0001_initial.py      # Migración inicial consolidada
```

## Flujo de envío

1. El scheduler ejecuta una comprobación diaria a la hora configurada.
2. `dispatch.py` busca contactos activos con cumpleaños o aniversario en la fecha actual.
3. Para cada evento crea o reutiliza un log `processing` para evitar duplicados.
4. Selecciona aleatoriamente una plantilla del tipo correspondiente.
5. Renderiza marcadores, compila LaTeX a PDF y convierte el resultado a PNG.
6. Construye el email con texto editable y tarjeta embebida como imagen.
7. Envía por SMTP al destinatario corporativo.
8. Marca el log como `sent` o `failed`.

## Decisiones actuales

- Los contactos no tienen email. Todas las tarjetas se envían al buzón corporativo.
- La fecha de nacimiento guarda solo día y mes usando el año neutro `2000`.
- La edad de cumpleaños no se calcula ni aparece en plantillas.
- `{{AÑOS}}` está permitido solo para aniversarios.
- Las plantillas se eligen siempre de forma aleatoria entre las tres disponibles.
- Las previews de plantillas se cachean en `data/template_previews` y se invalidan al cambiar el `.tex` o `brand.tex`.

## Base de datos

Tablas principales:

- `contacts`: nombre, apellido, nacimiento opcional, aniversario opcional y estado.
- `app_settings`: SMTP, destinatario corporativo, hora de envío y textos de email.
- `send_logs`: histórico y estado de cada intento de envío.

El proyecto está preparado para primer arranque con una única migración. Si ya existe una base antigua, conviene migrarla manualmente o recrearla.
