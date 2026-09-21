"""Schemas del módulo Ubicaciones (jerarquía Departamento → Ciudad → Barrio +
ofertas de domicilio).

Toda regla de negocio se revalida en `service.py` / `ofertas.py`; estos schemas
son la primera barrera y la que da los mensajes de campo al frontend.
"""
import re
import unicodedata
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.shared.services.enums import TipoOfertaDomicilio

# ─────────────────────────────────────────
# Validadores compartidos
# ─────────────────────────────────────────

_PALABRA = r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+"
_NOMBRE_BARRIO_RE = re.compile(rf"^{_PALABRA}( {_PALABRA})*$")

# Precio del domicilio y montos de oferta: entero COP, 0 .. 9 999 999 (7 díg).
PRECIO_MAX = 9_999_999


def validar_nombre_barrio(v: str) -> str:
    """1–35 chars; letras (con tildes y ñ), números y espacios simples internos;
    sin empezar/terminar con espacio, sin espacios dobles, sin símbolos."""
    if not isinstance(v, str):
        raise ValueError("El nombre del barrio es obligatorio")
    if not (1 <= len(v) <= 35):
        raise ValueError("El nombre del barrio debe tener entre 1 y 35 caracteres")
    if not _NOMBRE_BARRIO_RE.match(v):
        raise ValueError(
            "El nombre solo admite letras, números y espacios simples internos "
            "(sin empezar o terminar con espacio, sin espacios dobles ni símbolos)"
        )
    return v


def normalizar_nombre(v: str) -> str:
    """Clave de comparación de duplicados: sin tildes, en minúsculas, espacios
    colapsados. 'Manrique', 'manrique' y 'mánrique' colapsan al mismo valor."""
    s = unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def validar_nombre_generico(v: str, campo: str, largo: int) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{campo} es obligatorio")
    v = v.strip()
    if len(v) > largo:
        raise ValueError(f"{campo} no puede superar {largo} caracteres")
    return v


# ─────────────────────────────────────────
# Jerarquía — listados
# ─────────────────────────────────────────

class DepartamentoOut(BaseModel):
    ID_Departamento: int
    Nombre: str
    Estado: int
    estado_efectivo: bool = True


class CiudadOut(BaseModel):
    ID_Ciudad: int
    ID_Departamento: int
    Nombre: str
    departamento: Optional[str] = None
    Estado: int
    estado_efectivo: bool = True
    motivo_inactivo: Optional[str] = None


class BarrioOut(BaseModel):
    ID_Barrio: int
    ID_Ciudad: int
    Nombre: str
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    Precio: int
    Es_Base: bool
    Estado: int
    estado_efectivo: bool = True
    motivo_inactivo: Optional[str] = None


class BarrioListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    barrios: list[BarrioOut]


class BarrioDetalle(BarrioOut):
    ofertas_activas: list = []
    referencias: dict = {}          # {pedidos, usuarios, ofertas} — para explicar por qué no se puede eliminar
    puede_eliminar: bool = False


# ─────────────────────────────────────────
# Crear / editar barrio
# ─────────────────────────────────────────

class BarrioCreate(BaseModel):
    ID_Ciudad: int = Field(..., gt=0)
    Nombre: str
    Precio: int = Field(..., ge=0, le=PRECIO_MAX)

    @field_validator("Nombre")
    @classmethod
    def _nombre(cls, v):
        return validar_nombre_barrio(v)


class BarrioUpdate(BaseModel):
    # Un barrio Es_Base solo deja editar Precio; uno creado, Nombre y Precio.
    # El service aplica la restricción según Es_Base.
    Nombre: Optional[str] = None
    Precio: Optional[int] = Field(None, ge=0, le=PRECIO_MAX)

    @field_validator("Nombre")
    @classmethod
    def _nombre(cls, v):
        if v is None:
            return v
        return validar_nombre_barrio(v)


class EstadoInput(BaseModel):
    Estado: int = Field(..., ge=1, le=2)   # 1=Activo 2=Inactivo


class AccionMasivaInput(BaseModel):
    # nivel + id del padre. 'departamentos' (global), 'ciudades' (de un depto),
    # 'barrios' (de una ciudad).
    nivel: str
    id_padre: Optional[int] = None
    Estado: int = Field(..., ge=1, le=2)

    @field_validator("nivel")
    @classmethod
    def _nivel(cls, v):
        if v not in ("departamentos", "ciudades", "barrios"):
            raise ValueError("nivel debe ser 'departamentos', 'ciudades' o 'barrios'")
        return v


# ─────────────────────────────────────────
# Ofertas de domicilio
# ─────────────────────────────────────────

class OfertaCreate(BaseModel):
    Nombre: str
    Tipo: str = TipoOfertaDomicilio.DESCUENTO      # 'descuento' | 'recargo'
    Monto_Pesos: Optional[int] = Field(None, ge=0, le=PRECIO_MAX)
    Porcentaje: Optional[int] = Field(None, ge=0, le=100)
    Dias_Semana: list[int] = []                   # 1..7 ISO (Lunes=1 … Domingo=7)
    Dias_Mes: list[int] = []                      # 1..31
    barrios: list[int] = []                       # 1..N ID_Barrio

    @field_validator("Nombre")
    @classmethod
    def _nombre(cls, v):
        return validar_nombre_generico(v, "El nombre de la oferta", 80)

    @field_validator("Tipo")
    @classmethod
    def _tipo(cls, v):
        if v not in TipoOfertaDomicilio.TODOS:
            raise ValueError("Tipo debe ser 'descuento' o 'recargo'")
        return v

    @field_validator("Dias_Semana")
    @classmethod
    def _dsem(cls, v):
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("Los días de la semana van de 1 (Lunes) a 7 (Domingo)")
        return sorted(set(v))

    @field_validator("Dias_Mes")
    @classmethod
    def _dmes(cls, v):
        if any(d < 1 or d > 31 for d in v):
            raise ValueError("Los días del mes van de 1 a 31")
        return sorted(set(v))

    @field_validator("barrios")
    @classmethod
    def _barrios(cls, v):
        return sorted(set(v))

    @model_validator(mode="after")
    def _reglas(self):
        if self.Monto_Pesos is None and self.Porcentaje is None:
            raise ValueError("La oferta debe tener descuento/recargo en pesos, en porcentaje, o ambos")
        if not self.Dias_Semana and not self.Dias_Mes:
            raise ValueError("La oferta debe aplicar en al menos un día de la semana o del mes")
        if not self.barrios:
            raise ValueError("La oferta debe aplicar en al menos un barrio")
        return self


class OfertaUpdate(BaseModel):
    Nombre: Optional[str] = None
    Tipo: Optional[str] = None
    Monto_Pesos: Optional[int] = Field(None, ge=0, le=PRECIO_MAX)
    Porcentaje: Optional[int] = Field(None, ge=0, le=100)
    Dias_Semana: Optional[list[int]] = None
    Dias_Mes: Optional[list[int]] = None
    barrios: Optional[list[int]] = None
    # Permitir borrar explícitamente uno de los montos: enviar el flag y no el valor.
    limpiar_pesos: bool = False
    limpiar_porcentaje: bool = False

    @field_validator("Nombre")
    @classmethod
    def _nombre(cls, v):
        if v is None:
            return v
        return validar_nombre_generico(v, "El nombre de la oferta", 80)

    @field_validator("Tipo")
    @classmethod
    def _tipo(cls, v):
        if v is not None and v not in TipoOfertaDomicilio.TODOS:
            raise ValueError("Tipo debe ser 'descuento' o 'recargo'")
        return v

    @field_validator("Dias_Semana")
    @classmethod
    def _dsem(cls, v):
        if v is None:
            return v
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("Los días de la semana van de 1 (Lunes) a 7 (Domingo)")
        return sorted(set(v))

    @field_validator("Dias_Mes")
    @classmethod
    def _dmes(cls, v):
        if v is None:
            return v
        if any(d < 1 or d > 31 for d in v):
            raise ValueError("Los días del mes van de 1 a 31")
        return sorted(set(v))

    @field_validator("barrios")
    @classmethod
    def _barrios(cls, v):
        if v is None:
            return v
        return sorted(set(v))


class OfertaOut(BaseModel):
    ID_Oferta: int
    Nombre: str
    Tipo: str
    Monto_Pesos: Optional[int] = None
    Porcentaje: Optional[int] = None
    Dias_Semana: list[int] = []
    Dias_Mes: list[int] = []
    Estado: int
    Fecha_Creacion: Optional[datetime] = None
    barrios: list = []          # [{ID_Barrio, Nombre, ciudad}]


class OfertaListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    ofertas: list[OfertaOut]
