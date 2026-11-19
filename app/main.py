"""API HTTP para recomendaciones de categoría y entidad pública de DenuPe."""
from contextlib import asynccontextmanager
import os

from .middleware import RequestProtectionMiddleware

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .predictor import cargar_modelo, sugerir_categoria
from .entidades import sugerir_entidad, cargar_directorio, listar_entidades_disponibles, resolver_distrito_por_punto, catalogo_distrital_por_categoria
from .schemas import DenunciaEntrada, SugerenciaSalida, EntidadEntrada, EntidadSalida, EntidadesDisponiblesSalida


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
    departamento: str | None = Query(default=None, min_length=2, max_length=80),
    provincia: str | None = Query(default=None, min_length=2, max_length=80),
    distrito: str | None = Query(default=None, min_length=2, max_length=80),
    latitud: float | None = Query(default=None, ge=-90, le=90),
    longitud: float | None = Query(default=None, ge=-180, le=180),
):
    """Devuelve las ocho rutas de competencia; GPS prevalece sobre el distrito del cliente."""
    if (latitud is None) != (longitud is None):
        raise HTTPException(status_code=422, detail="latitud y longitud deben enviarse juntas")
    if latitud is not None:
        try:
            territorio = resolver_distrito_por_punto(latitud, longitud)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif departamento and provincia and distrito:
        territorio = {"departamento": departamento, "provincia": provincia, "distrito": distrito}
    else:
        raise HTTPException(status_code=422, detail="Envía latitud y longitud GPS, o departamento, provincia y distrito.")
    try:
        return catalogo_distrital_por_categoria(territorio["departamento"], territorio["provincia"], territorio["distrito"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/territorio/resolver-distrito", tags=["Catálogo territorial"])
def resolver_territorio(
    latitud: float = Query(ge=-90, le=90),
    longitud: float = Query(ge=-180, le=180),
):
    """Resuelve el distrito administrativo exacto de un punto GPS."""
    try:
        return resolver_distrito_por_punto(latitud, longitud)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/ia/sugerir-entidad",
    response_model=EntidadSalida,
    tags=["Derivación inteligente"],
)
def predecir_entidad(denuncia: EntidadEntrada) -> EntidadSalida:
    """Devuelve una entidad pública verificada o la bandeja interna de revisión."""
    return sugerir_entidad(denuncia)

@app.get(
    "/api/entidades/disponibles",
    response_model=EntidadesDisponiblesSalida,
    tags=["Catálogo de instituciones"],
)
def entidades_disponibles(
    categoria: str = Query(min_length=2, max_length=80),
    departamento: str = Query(min_length=2, max_length=80),
    provincia: str = Query(min_length=2, max_length=80),
    distrito: str = Query(min_length=2, max_length=80),
    latitud: float | None = Query(default=None, ge=-90, le=90),
    longitud: float | None = Query(default=None, ge=-180, le=180),
) -> EntidadesDisponiblesSalida:
    """Lista entidades verificadas o el destino interno de revisión como respaldo."""
    if (latitud is None) != (longitud is None):
        raise HTTPException(status_code=422, detail="latitud y longitud deben enviarse juntas")
    items = listar_entidades_disponibles(
        categoria, departamento, provincia, distrito, latitud, longitud
    )
    tiene_revision = any(item.get("tipo") == "revision_competencia" for item in items)
    motivo = (
        "No se identificó una institución pública específica. Puedes asignar la denuncia a la bandeja interna de revisión de competencia."
        if tiene_revision else
        "Selecciona una institución con competencia validada para esta denuncia."
    )
    return EntidadesDisponiblesSalida(entidades=items, motivo=motivo)
