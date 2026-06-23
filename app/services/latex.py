import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import get_settings


class LatexError(RuntimeError):
    pass


def escape_latex(value: object) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def available_templates(event_type: str) -> list[str]:
    folder = get_settings().templates_dir / event_type
    return sorted(path.stem for path in folder.glob("*.tex"))


def template_source(event_type: str, name: str) -> str:
    if not re.fullmatch(r"[a-z0-9_-]+", name) or event_type not in {"birthday", "anniversary"}:
        raise LatexError("Nombre de plantilla no válido")
    path = get_settings().templates_dir / event_type / f"{name}.tex"
    if not path.is_file():
        raise LatexError("La plantilla no existe")
    return path.read_text(encoding="utf-8")


def render_source(source: str, context: dict[str, object]) -> str:
    for key, value in context.items():
        source = source.replace("{{" + key + "}}", escape_latex(value))
    unresolved = re.findall(r"\{\{[^}]+\}\}", source)
    if unresolved:
        raise LatexError(f"Marcadores sin resolver: {', '.join(unresolved)}")
    return source


def _compile_in(temp: Path, event_type: str, name: str, context: dict[str, object]) -> Path:
    if not shutil.which("latexmk"):
        raise LatexError("latexmk no está instalado; use el contenedor Docker")
    source = template_source(event_type, name)
    if event_type == "birthday" and "{{AÑOS}}" in source:
        raise LatexError("Las plantillas de cumpleaños no pueden mostrar la edad")
    rendered = render_source(source, context)
    tex_path = temp / "card.tex"
    tex_path.write_text(rendered, encoding="utf-8")
    brand_path = get_settings().templates_dir / "brand.tex"
    if not brand_path.is_file():
        raise LatexError("No se encontró la paleta corporativa brand.tex")
    shutil.copy2(brand_path, temp / "brand.tex")
    try:
        result = subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "card.tex"],
            cwd=temp, capture_output=True, text=True, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LatexError("La compilación LaTeX superó 60 segundos") from exc
    pdf_path = temp / "card.pdf"
    if result.returncode != 0 or not pdf_path.exists():
        excerpt = (result.stdout + result.stderr)[-3000:]
        raise LatexError(f"Falló la compilación LaTeX:\n{excerpt}")
    return pdf_path


def _work_directory():
    work_root = get_settings().latex_work_dir
    work_root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=work_root)


def compile_pdf(event_type: str, name: str, context: dict[str, object]) -> bytes:
    with _work_directory() as temp_dir:
        return _compile_in(Path(temp_dir), event_type, name, context).read_bytes()


def compile_image(event_type: str, name: str, context: dict[str, object]) -> bytes:
    if not shutil.which("pdftoppm"):
        raise LatexError("pdftoppm no está instalado; reconstruya el contenedor Docker")
    with _work_directory() as temp_dir:
        temp = Path(temp_dir)
        pdf_path = _compile_in(temp, event_type, name, context)
        try:
            result = subprocess.run(
                ["pdftoppm", "-png", "-singlefile", "-r", "180", str(pdf_path), "card"],
                cwd=temp, capture_output=True, text=True, timeout=30, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LatexError("La conversión de la tarjeta a imagen superó 30 segundos") from exc
        image_path = temp / "card.png"
        if result.returncode != 0 or not image_path.exists():
            raise LatexError(f"Falló la conversión a PNG: {(result.stderr or result.stdout)[-1000:]}")
        return image_path.read_bytes()
