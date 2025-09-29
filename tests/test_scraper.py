"""Tests for the scraper normalisation helpers."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper import normalise_deal


def test_normalise_deal_handles_non_string_values() -> None:
    """Non-string or falsy values should normalise to empty strings."""

    raw = {
        "nombre": None,
        "sector": 101,
        "descripcion": "   ",
        "impacto_social": False,
        "fuente_datos": None,
        "tags": ["Agtech", None, 42],
    }

    normalised = normalise_deal(raw)

    assert normalised["nombre"] == ""
    assert normalised["sector"] == ""
    assert normalised["descripcion"] == ""
    assert normalised["impacto_social"] == ""
    assert normalised["fuente_datos"] == "unknown"
    assert normalised["tags"] == ["Agtech", "42"]
