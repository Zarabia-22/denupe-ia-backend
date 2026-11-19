"""API HTTP para recomendaciones de categoría y entidad pública de DenuPe."""
from contextlib import asynccontextmanager
import os

from .middleware import RequestProtectionMiddleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .predictor import cargar_modelo, sugerir_categoria
from .entidades import sugerir_entidad, cargar_directorio
from .schemas import DenunciaEntrada, SugerenciaSalida, EntidadEntrada, EntidadSalida


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


@app.post(
    "/api/ia/sugerir-entidad",
    response_model=EntidadSalida,
    tags=["Derivación inteligente"],
)
def predecir_entidad(denuncia: EntidadEntrada) -> EntidadSalida:
    """Recomienda una entidad solo si existe coincidencia territorial verificable."""
    return sugerir_entidad(denuncia)
