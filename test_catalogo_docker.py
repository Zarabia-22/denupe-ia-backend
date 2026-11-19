from pathlib import Path

import pytest

from app.entidades import _leer_lista


ROOT = Path(__file__).resolve().parent


def test_dockerfile_includes_required_entity_catalog():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY data ./data" in dockerfile


def test_required_entity_catalog_fails_when_missing(tmp_path):
    missing_catalog = tmp_path / "entidades_publicas.json"

    with pytest.raises(RuntimeError, match="Falta el directorio obligatorio"):
        _leer_lista(missing_catalog, required=True)


def test_optional_catalog_can_be_missing(tmp_path):
    optional_catalog = tmp_path / "comisarias_pnp_referencia.json"

    assert _leer_lista(optional_catalog) == []


def test_entity_catalog_is_present_and_valid_json():
    catalog_path = ROOT / "data" / "entidades_publicas.json"
    assert catalog_path.is_file()

    records = _leer_lista(catalog_path, required=True)
    assert records
