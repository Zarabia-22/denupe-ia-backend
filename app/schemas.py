"""Contrato JSON público del servicio de IA."""
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DenunciaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str = Field(min_length=5, max_length=100)
    descripcion: str = Field(min_length=10, max_length=500)

    @field_validator("titulo", "descripcion")
    @classmethod
    def texto_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El texto no puede contener únicamente espacios")
        return value


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
    latitud: float | None = Field(default=None, ge=-90, le=90)
    longitud: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("categoria", "departamento", "provincia", "distrito", "titulo", "descripcion")
    @classmethod
    def normalizar_textos(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede contener únicamente espacios")
        return value

    @field_validator("latitud", "longitud")
    @classmethod
    def coordenada_finita(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("La coordenada debe ser un número finito")
        return value

    @model_validator(mode="after")
    def coordenadas_completas(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("latitud y longitud deben enviarse juntas")
        return self


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

class EntidadesDisponiblesSalida(BaseModel):
    """Catálogo completo de entidades registradas para el distrito detectado por GPS."""
    entidades: list[EntidadPublica] = Field(default_factory=list)
    motivo: str = "Se muestran las entidades registradas para el distrito, sin filtrar por categoría."
