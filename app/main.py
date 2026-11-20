"""API HTTP para recomendaciones de categoría y entidad pública de DenuPe."""
from contextlib import asynccontextmanager
import os

from .middleware import RequestProtectionMiddleware

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .predictor import cargar_modelo, sugerir_categoria
from .entidades import sugerir_entidad, cargar_directorio, listar_entidades_disponibles, resolver_distrito_por_punto, catalogo_distrital_por_categoria
from .schemas import DenunciaEntrada, SugerenciaSalida, EntidadEntrada, EntidadSalida, EntidadesDisponiblesSalida
from .insforge_catalog import InsForgeCatalogError, consultar_matriz_distrital, consultar_resolutor_categoria


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fallar en el arranque si faltan los artefactos del clasificador actual.
    cargar_modelo()
    cargar_directorio()
    yield


app = FastAPI(
    title="DenuPe · Servicio de IA",
    description="Sugiere categorías y entidades públicas responsables a partir de denuncias ciudadanas.",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestProtectionMiddleware)

# CORS no autentica una API. En Flutter nativo no hace falta CORS.
origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


@app.get("/health", tags=["Salud"])
def health():
    # Contrato existente conservado para Render y clientes de monitorización.
    return {"status": "ok", "modelo": "tfidf_logistic_regression_8"}


@app.get("/health/ready", tags=["Salud"])
def readiness():
    """Comprueba que el artefacto del modelo y el directorio local son utilizables."""
    modelo, vectorizador, metricas = cargar_modelo()
    entidades = cargar_directorio()
    return {
        "status": "ready",
        "modelo_version": metricas["version"],
        "categorias": len(modelo.classes_),
        "vocabulario": len(vectorizador.transformer_list[0][1].vocabulary_),
        "entidades_catalogo": len(entidades),
    }


@app.post(
    "/api/ia/sugerir-categoria",
    response_model=SugerenciaSalida,
    tags=["Predicción"],
)
def predecir(denuncia: DenunciaEntrada) -> SugerenciaSalida:
    return sugerir_categoria(denuncia.titulo, denuncia.descripcion)



@app.get("/api/territorio/catalogo-distrital", tags=["Catálogo territorial"])
def catalogo_territorial(
    latitud: float = Query(ge=-90, le=90),
    longitud: float = Query(ge=-180, le=180),
):
    """Devuelve la matriz nacional solo después de resolver el punto GPS."""
    try:
        territorio = resolver_distrito_por_punto(latitud, longitud)
        matriz = consultar_matriz_distrital(territorio["ubigeo"])
    except InsForgeCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **territorio,
        "categorias": matriz,
        "total_categorias": len(matriz),
        "categorias_con_entidad_relacionada": len(matriz),
        "fuente_catalogo": "InsForge: consultar_matriz_distrital_por_ubigeo",
    }


@app.get("/api/territorio/resolver-distrito", tags=["Catálogo territorial"])
def resolver_territorio(
    latitud: float = Query(ge=-90, le=90),
    longitud: float = Query(ge=-180, le=180),
):
    """Resuelve distrito por polígono y comprueba la matriz nacional."""
    try:
        territorio = resolver_distrito_por_punto(latitud, longitud)
        matriz = consultar_matriz_distrital(territorio["ubigeo"])
    except InsForgeCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**territorio, "catalogo_completo": len(matriz) == 8}


@app.post(
    "/api/ia/sugerir-entidad",
    response_model=EntidadSalida,
    tags=["Derivación inteligente"],
)
def predecir_entidad(denuncia: EntidadEntrada) -> EntidadSalida:
    """GPS y matriz InsForge son requisitos previos a cualquier sugerencia."""
    if denuncia.latitud is None or denuncia.longitud is None:
        return EntidadSalida(sugerida=False, entidad=None,
            motivo="Primero registra la ubicación GPS. Sin coordenadas no se consulta ni asigna una entidad.")
    try:
        territorio = resolver_distrito_por_punto(denuncia.latitud, denuncia.longitud)
        consultar_matriz_distrital(territorio["ubigeo"])
        codigos = {
            "alumbrado público": "alumbrado", "seguridad ciudadana": "seguridad",
            "limpieza y residuos": "limpieza", "agua y saneamiento": "agua",
            "tránsito y transporte": "transito", "parques y áreas verdes": "areas_verdes",
            "vialidad e infraestructura": "infraestructura", "otros": "otros",
        }
        codigo = codigos.get(denuncia.categoria.casefold().strip())
        if not codigo:
            return EntidadSalida(sugerida=False, entidad=None, motivo="Categoría no reconocida por el catálogo territorial.")
        regla = consultar_resolutor_categoria(territorio["ubigeo"], codigo)
    except InsForgeCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        return EntidadSalida(sugerida=False, entidad=None, motivo=f"No se pudo validar el punto GPS: {exc}")
    if regla.get("requiere_gps") is not True or regla.get("asignar_solo_tras_gps") is not True:
        return EntidadSalida(sugerida=False, entidad=None, motivo="La regla territorial no permite una resolución sin GPS.")
    denuncia = denuncia.model_copy(update={
        "departamento": territorio["departamento"],
        "provincia": territorio["provincia"],
        "distrito": territorio["distrito"],
    })
    salida = sugerir_entidad(denuncia)
    if salida.entidad and salida.entidad.tipo == "revision_competencia":
        return EntidadSalida(sugerida=False, entidad=None,
            motivo=f"Se identificó el resolutor sectorial «{regla.get('entidad_nombre')}», pero falta verificar una entidad concreta para este punto. Mantén la selección manual.")
    return salida

@app.get(
    "/api/entidades/disponibles",
    response_model=EntidadesDisponiblesSalida,
    tags=["Catálogo de instituciones"],
)
def entidades_disponibles(
    categoria: str = Query(min_length=2, max_length=80),
    departamento: str | None = Query(default=None, min_length=2, max_length=80),
    provincia: str | None = Query(default=None, min_length=2, max_length=80),
    distrito: str | None = Query(default=None, min_length=2, max_length=80),
    latitud: float | None = Query(default=None, ge=-90, le=90),
    longitud: float | None = Query(default=None, ge=-180, le=180),
) -> EntidadesDisponiblesSalida:
    """Lista entidades verificadas o el destino interno de revisión como respaldo."""
    if (latitud is None) != (longitud is None):
        raise HTTPException(status_code=422, detail="latitud y longitud deben enviarse juntas")
    if latitud is None or longitud is None:
        raise HTTPException(status_code=422, detail="La ubicación GPS es obligatoria para consultar entidades.")
    try:
        territorio = resolver_distrito_por_punto(latitud, longitud)
        codigo_por_nombre = {
            "alumbrado público": "alumbrado", "seguridad ciudadana": "seguridad",
            "limpieza y residuos": "limpieza", "agua y saneamiento": "agua",
            "tránsito y transporte": "transito", "parques y áreas verdes": "areas_verdes",
            "vialidad e infraestructura": "infraestructura", "otros": "otros",
        }
        codigo = codigo_por_nombre.get(categoria.casefold().strip())
        if not codigo:
            raise HTTPException(status_code=422, detail="Categoría no reconocida.")
        consultar_resolutor_categoria(territorio["ubigeo"], codigo)
    except InsForgeCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo resolver el distrito por GPS: {exc}") from exc
    departamento = territorio["departamento"]
    provincia = territorio["provincia"]
    distrito = territorio["distrito"]
    items = listar_entidades_disponibles(categoria, departamento, provincia, distrito, latitud, longitud)
    tiene_revision = any(item.get("tipo") == "revision_competencia" for item in items)
    motivo = (
        "No se identificó una institución pública específica. Puedes asignar la denuncia a la bandeja interna de revisión de competencia."
        if tiene_revision else
        "Selecciona una institución con competencia validada para esta denuncia."
    )
    return EntidadesDisponiblesSalida(entidades=items, motivo=motivo)
