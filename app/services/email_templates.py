import re


ALLOWED_MARKERS = {"NOMBRE", "APELLIDO", "AÑOS", "FECHA"}


def validate_message_template(value: str, *, subject: bool = False,
                              allowed_markers: set[str] | None = None) -> str:
    value = value.strip()
    if not value:
        raise ValueError("La plantilla no puede estar vacía")
    if subject and ("\n" in value or "\r" in value):
        raise ValueError("El asunto debe ocupar una sola línea")
    limit = 200 if subject else 5000
    if len(value) > limit:
        raise ValueError(f"La plantilla supera el límite de {limit} caracteres")
    markers = set(re.findall(r"\{\{([^{}]+)\}\}", value))
    permitted = allowed_markers if allowed_markers is not None else ALLOWED_MARKERS
    unknown = markers - permitted
    if unknown:
        raise ValueError(f"Marcadores no permitidos: {', '.join(sorted(unknown))}")
    return value


def render_message_template(value: str, context: dict[str, object]) -> str:
    for key in ALLOWED_MARKERS:
        value = value.replace("{{" + key + "}}", str(context.get(key, "")))
    return value
