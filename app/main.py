"""API HTTP para recomendaciones de categoría de DenuPe."""
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .predictor import cargar_modelo, sugerir_categoria
from .schemas import DenunciaEntrada, SugerenciaSalida


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fallar en el arranque si faltan los artefactos.
    cargar_modelo()
    yield


app = FastAPI(
    title="DenuPe · Servicio de IA",
    description="Sugiere categorías mediante TF-IDF y árbol de decisión. La elección definitiva corresponde al ciudadano.",
    version="1.0.0",
    lifespan=lifespan,
)

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
    return {"status": "ok", "modelo": "decision_tree_tfidf"}


@app.post(
    "/api/ia/sugerir-categoria",
    response_model=SugerenciaSalida,
    tags=["Predicción"],
)
def predecir(denuncia: DenunciaEntrada) -> SugerenciaSalida:
    return sugerir_categoria(denuncia.titulo, denuncia.descripcion)
