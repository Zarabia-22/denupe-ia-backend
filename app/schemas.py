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


class EntidadEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categoria: str = Field(min_length=2, max_length=80)
    departamento: str = Field(min_length=2, max_length=80)
    provincia: str = Field(min_length=2, max_length=80)
    distrito: str = Field(min_length=2, max_length=80)
    titulo: str = Field(min_length=5, max_length=100)
    descripcion: str = Field(min_length=10, max_length=500)


class EntidadPublica(BaseModel):
    id: str
    nombre: str
    tipo: str
    direccion: str | None = None
    telefono: str | None = None
    sitio_web: str | None = None
    ambito: dict[str, str]


class EntidadSalida(BaseModel):
    sugerida: bool
    entidad: EntidadPublica | None = None
    motivo: str
