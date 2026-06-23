from datetime import date
from pathlib import Path

from app.services.dispatch import _matches_today, _years_since
from app.services.latex import escape_latex, render_source, validate_template_source
from app.services.email_templates import render_message_template, validate_message_template
from app.services.email_templates import ALLOWED_MARKERS
from app.email_defaults import BIRTHDAY_BODY
from app.main import _contact_values, _contact_values_from_csv, _next_occurrence, format_anniversary, format_day_month, years_since
import pytest


def test_latex_escapes_user_input():
    assert escape_latex("Ana & Co_#1") == r"Ana \& Co\_\#1"
    assert render_source("Hola {{NOMBRE}}", {"NOMBRE": "A&B"}) == r"Hola A\&B"


def test_year_calculation():
    assert _years_since(date(2010, 6, 22), date(2026, 6, 22)) == 16


def test_leap_day_policy():
    assert _matches_today(date(2000, 2, 29), date(2025, 2, 28))
    assert not _matches_today(date(2000, 2, 29), date(2024, 2, 28))


def test_email_templates_validate_and_render():
    template = validate_message_template("Hola {{NOMBRE}}, celebramos {{AÑOS}} años")
    assert render_message_template(template, {"NOMBRE": "Ana", "AÑOS": 8}) == "Hola Ana, celebramos 8 años"
    with pytest.raises(ValueError):
        validate_message_template("Hola {{MARCADOR_DESCONOCIDO}}")
    assert "{{AÑOS}}" not in BIRTHDAY_BODY
    with pytest.raises(ValueError):
        validate_message_template("Cumples {{AÑOS}}", allowed_markers=ALLOWED_MARKERS - {"AÑOS"})


def test_template_catalog_contracts():
    root = Path("latex_templates")
    birthdays = list((root / "birthday").glob("*.tex"))
    anniversaries = list((root / "anniversary").glob("*.tex"))
    assert len(birthdays) == len(anniversaries) == 3
    for path in birthdays:
        source = path.read_text(encoding="utf-8")
        assert "{{NOMBRE}}" in source
        assert "{{AÑOS}}" not in source
        assert "ANIVERSARIO" not in source
        assert r"\input{brand.tex}" in source
        assert r"\birthdayMessage" in source
    for path in anniversaries:
        source = path.read_text(encoding="utf-8")
        assert "{{NOMBRE}}" in source
        assert "{{AÑOS}}" in source
        assert "CUMPLEAÑOS" not in source
        assert r"\input{brand.tex}" in source
        assert r"\anniversaryMessage" in source


def test_next_occurrence_handles_leap_day():
    assert _next_occurrence(date(2000, 2, 29), date(2025, 2, 27)) == date(2025, 2, 28)
    assert _next_occurrence(date(2000, 2, 29), date(2025, 3, 1)) == date(2026, 2, 28)


def test_birth_date_uses_neutral_year():
    values = _contact_values("Ana", "López", "29", "2", "", "on")
    assert values["birth_date"] == date(2000, 2, 29)
    with pytest.raises(Exception):
        _contact_values("Ana", "López", "31", "2", "", "on")


def test_contact_date_display_formats():
    assert format_day_month(date(2000, 6, 24)) == "24 de junio"
    assert years_since(date(2000, 6, 24), date(2026, 6, 23)) == 25
    assert years_since(date(2000, 6, 24), date(2026, 6, 24)) == 26
    assert format_anniversary(None) == "—"


def test_contact_values_from_csv_accepts_bulk_formats():
    values = _contact_values_from_csv({
        "first_name": "Ana",
        "last_name": "López",
        "birth_date": "24/06",
        "anniversary_date": "24.06.2000",
        "active": "no",
    })
    assert values["birth_date"] == date(2000, 6, 24)
    assert values["anniversary_date"] == date(2000, 6, 24)
    assert values["active"] is False


def test_template_source_marker_validation():
    validate_template_source("anniversary", "Hola {{NOMBRE}}, {{AÑOS}} años")
    with pytest.raises(Exception):
        validate_template_source("birthday", "Hola {{NOMBRE}}, {{AÑOS}} años")
    with pytest.raises(Exception):
        validate_template_source("anniversary", "Hola {{DESCONOCIDO}}")
