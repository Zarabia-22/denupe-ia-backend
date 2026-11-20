from scripts.auditoria_directorio_entidades import auditar


def entidad(**extra):
    base = {
        "id": "mun-150122",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad_distrital",
        "codigo_ubigeo": "150122",
        "fuente": "INEI",
        "fuente_url": "https://www.gob.pe/inei",
        "verificado_nombre": True,
        "verificado_competencias": True,
        "categorias_habilitadas": ["Limpieza y residuos"],
    }
    base.update(extra)
    return base


def test_directorio_valido_y_cobertura_solo_categoria_habilitada():
    resultado = auditar([entidad()])
    assert resultado["valido"] is True
    assert resultado["distritos_con_entidad"] == 1
    assert resultado["cobertura_por_categoria"] == {"Limpieza y residuos": 1}


def test_no_infiere_que_municipalidad_cubre_ocho_categorias():
    registro = entidad(categorias_habilitadas=[])
    resultado = auditar([registro])
    assert resultado["valido"] is True
    assert resultado["cobertura_por_categoria"] == {}


def test_rechaza_categoria_sin_competencia_verificada():
    resultado = auditar([entidad(verificado_competencias=False)])
    assert resultado["valido"] is False
    assert any("sin verificaciones" in e for e in resultado["errores"])


def test_rechaza_ubigeo_invalido():
    resultado = auditar([entidad(codigo_ubigeo="123")])
    assert resultado["valido"] is False
    assert any("UBIGEO inválido" in e for e in resultado["errores"])


def test_rechaza_ids_duplicados():
    resultado = auditar([entidad(), entidad(nombre="Otra municipalidad")])
    assert resultado["valido"] is False
    assert any("id duplicado" in e for e in resultado["errores"])


def test_rechaza_categoria_desconocida():
    resultado = auditar([entidad(categorias_habilitadas=["Categoría inventada"])])
    assert resultado["valido"] is False
    assert any("categorías desconocidas" in e for e in resultado["errores"])
