"""Contrato JSON público del servicio de IA."""
from pydantic import BaseModel, ConfigDict, Field


class DenunciaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str = Field(min_length=5, max_length=100)
    descripcion: str = Field(min_length=10, max_length=500)


class SugerenciaSalida(BaseModel):
    sugerida: bool = Field(description="Si es falso se conserva la selección manual")
    categoria: str | None = None
    confianza_modelo: float | None = Field(default=None, ge=0, le=1)
    cobertura_vocabulario: float = Field(ge=0, le=1)
    motivo: str | None = None
