# Plantillas

## Tipos

Las tarjetas están en:

```text
latex_templates/birthday/
latex_templates/anniversary/
```

Cada carpeta contiene tres `.tex`. En cada envío se selecciona una plantilla aleatoria del tipo correspondiente.

## Marcadores

Marcadores disponibles:

- `{{NOMBRE}}`
- `{{APELLIDO}}`
- `{{FECHA}}`
- `{{AÑOS}}` solo en aniversarios

Las plantillas de cumpleaños no deben usar `{{AÑOS}}`.

## Estilo corporativo

La paleta y los mensajes secundarios compartidos están en:

```text
latex_templates/brand.tex
```

Ahí se definen macros de color, texto secundario y elementos comunes. Cambiar ese archivo invalida la caché de previews.

## Validación rápida

La vía más fiable para validar plantillas es reconstruir y abrir la vista Plantillas:

```bash
docker compose up --build -d
```

También puedes ejecutar tests:

```bash
.venv\Scripts\python -m pytest -q
```

## Reglas prácticas

- Mantén todas las imágenes generadas en una sola página.
- Evita paquetes LaTeX que no estén instalados en el `Dockerfile`.
- Si añades un paquete nuevo, actualiza el `Dockerfile`.
- No insertes datos personales sin pasar por marcadores; el backend los escapa antes de renderizar.
