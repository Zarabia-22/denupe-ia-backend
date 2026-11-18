"""Pruebas del recomendador territorial de entidades públicas."""
import json

from app.entidades import cargar_directorio, sugerir_entidad, DIRECTORIO_PATH
from app.schemas import EntidadEntrada


def entrada(**cambios):
    datos = {
        "categoria": "Limpieza y residuos",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "titulo": "Basura acumulada en la avenida",
        "descripcion": "Hay bolsas de residuos y desperdicios sin recoger en la vía pública.",
    }
    datos.update(cambios)
    return EntidadEntrada(**datos)


def test_sin_entidades_registradas_se_abstiene():
    cargar_directorio.cache_clear()
    salida = sugerir_entidad(entrada())
    assert salida.sugerida is False
    assert salida.entidad is None
    assert salida.motivo


def test_recomienda_entidad_solo_con_coincidencia_territorial_y_tematica(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-miraflores",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "categorias": ["Limpieza y residuos"],
        "palabras_clave": ["residuos", "basura", "desperdicios"],
        "habilitada_recomendacion": True,
        "direccion": None,
        "telefono": None,
        "sitio_web": None,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is True
    assert salida.entidad["nombre"] == "Municipalidad Distrital de Miraflores"
    assert salida.entidad["ambito"]["distrito"] == "Miraflores"
    cargar_directorio.cache_clear()


def test_no_recomienda_entidad_de_otro_distrito(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-surco",
        "nombre": "Municipalidad de Santiago de Surco",
        "tipo": "municipalidad",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Santiago de Surco",
        "categorias": ["Limpieza y residuos"],
        "palabras_clave": ["residuos", "basura"],
        "habilitada_recomendacion": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is False
    assert salida.entidad is None
    cargar_directorio.cache_clear()



def test_comisaria_historica_no_se_recomienda_automaticamente(tmp_path, monkeypatch):
    catalogo = [{
        "id": "pnp-6000",
        "nombre": "Comisaría PNP Callao",
        "tipo": "comisaria_pnp",
        "departamento": "Callao",
        "provincia": "Callao",
        "distrito": "Callao",
        "categorias": ["Seguridad ciudadana"],
        "palabras_clave": ["robo", "asalto"],
        "habilitada_recomendacion": False,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-existe.json")
    cargar_directorio.cache_clear()

    denuncia = entrada(
        categoria="Seguridad ciudadana",
        departamento="Callao",
        provincia="Callao",
        distrito="Callao",
        titulo="Robo en la vía pública",
        descripcion="Reporto un robo ocurrido cerca de mi domicilio.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None
    cargar_directorio.cache_clear()


def test_recomienda_municipalidad_para_limpieza_y_residuos(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-miraflores",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad_distrital",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "categorias": ["Limpieza y residuos", "Alumbrado público"],
        "categorias_habilitadas": ["Limpieza y residuos", "Parques y áreas verdes"],
        "palabras_clave": ["residuos", "basura", "desperdicios"],
        "verificado_competencias": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-existe.json")
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is True
    assert salida.entidad["nombre"] == "Municipalidad Distrital de Miraflores"
    cargar_directorio.cache_clear()


def test_categoria_sin_competencia_verificada_no_se_recomienda(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-miraflores",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad_distrital",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "categorias": ["Limpieza y residuos", "Alumbrado público"],
        "categorias_habilitadas": ["Limpieza y residuos", "Parques y áreas verdes"],
        "palabras_clave": ["luminaria", "poste", "alumbrado"],
        "verificado_competencias": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-existe.json")
    cargar_directorio.cache_clear()

    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Poste sin iluminación",
        descripcion="La luminaria de la calle no funciona desde ayer.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None
    cargar_directorio.cache_clear()
