from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from datetime import datetime
from decimal import Decimal

from src.shared.services.enums import TipoDescuento

TIPOS_DESCUENTO = set(TipoDescuento.TODOS)


# ── Crear descuento ──
class DescuentoCreate(BaseModel):
    Nombre:        str
    Tipo:          str                                               # ver TipoDescuento
    Codigo:        Optional[str]       = None                       # solo cupones
    Porcentaje:    Decimal             = Field(gt=0, le=100)        # 0 < x <= 100
    Meses_Minimos: Optional[int]       = None                       # solo antigüedad
    Fecha_Inicio:  datetime
    Fecha_Fin:     Optional[datetime]  = None
    Usos_Max:      Optional[int]       = None                       # null = ilimitado

    @model_validator(mode="after")
    def validar_descuento(self):
        if self.Tipo not in TIPOS_DESCUENTO:
            raise ValueError(f"Tipo de descuento inválido. Opciones: {', '.join(sorted(TIPOS_DESCUENTO))}")
        if self.Fecha_Fin is not None and self.Fecha_Fin <= self.Fecha_Inicio:
            raise ValueError("Fecha_Fin debe ser posterior a Fecha_Inicio")
        if self.Tipo == TipoDescuento.CUPON and not self.Codigo:
            raise ValueError("Los cupones deben tener un Codigo")
        if self.Tipo == TipoDescuento.ANTIGUEDAD and not self.Meses_Minimos:
            raise ValueError("Los descuentos por antigüedad deben tener Meses_Minimos")
        return self


# ── Editar descuento ──
class DescuentoUpdate(BaseModel):
    Nombre:        Optional[str]       = None
    Porcentaje:    Optional[Decimal]   = Field(default=None, gt=0, le=100)
    Meses_Minimos: Optional[int]       = None
    Fecha_Inicio:  Optional[datetime]  = None
    Fecha_Fin:     Optional[datetime]  = None
    Usos_Max:      Optional[int]       = None

    @model_validator(mode="after")
    def validar_fechas(self):
        if self.Fecha_Inicio is not None and self.Fecha_Fin is not None:
            if self.Fecha_Fin <= self.Fecha_Inicio:
                raise ValueError("Fecha_Fin debe ser posterior a Fecha_Inicio")
        return self


# ── Activar/desactivar ──
class DescuentoEstado(BaseModel):
    Estado: int


# ── Asignar descuento de emisión a usuarios ──
class AsignarDescuento(BaseModel):
    usuarios_ids: list[int]             # lista de ID_Usuario


# ── Respuesta de asignación ──
class AsignacionResponse(BaseModel):
    ID_Descuento:     int
    ID_Usuario:       int
    nombre_usuario:   Optional[str]      = None
    Usado:            bool               = False
    Fecha_Asignacion: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Respuesta de un descuento ──
class DescuentoResponse(BaseModel):
    ID_Descuento:  int
    Nombre:        str
    Tipo:          str
    Codigo:        Optional[str]     = None
    Porcentaje:    Decimal
    Meses_Minimos: Optional[int]     = None
    Fecha_Inicio:  Optional[datetime] = None
    Fecha_Fin:     Optional[datetime] = None
    Usos_Max:      Optional[int]     = None
    Usos_Actuales: int               = 0
    Estado:        Optional[int]     = None
    estado_label:  Optional[str]     = None
    total_asignados: int             = 0     # cuántos usuarios lo tienen asignado

    class Config:
        from_attributes = True


# ── Respuesta paginada descuentos ──
class DescuentoListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    descuentos: list[DescuentoResponse]


# ── Filtros para historial de créditos ──
class FiltroCreditos(BaseModel):
    ID_Usuario:   Optional[int]      = None
    Tipo:         Optional[str]      = None   # "recarga" o "uso"
    Monto_Min:    Optional[Decimal]  = None
    Monto_Max:    Optional[Decimal]  = None
    Fecha_Inicio: Optional[datetime] = None
    Fecha_Fin:    Optional[datetime] = None


# ── Respuesta de un movimiento de crédito ──
class MovimientoResponse(BaseModel):
    ID_Movimiento:  int
    ID_Usuario:     Optional[int]     = None
    nombre_cliente: Optional[str]     = None
    Tipo:           str               # "recarga" o "uso"
    Monto:          Decimal
    Fecha:          Optional[datetime] = None
    origen:         Optional[str]     = None  # "Devolución #3" o "Venta #12"

    class Config:
        from_attributes = True


# ── Respuesta paginada historial ──
class MovimientoListResponse(BaseModel):
    total:       int
    pagina:      int
    por_pagina:  int
    movimientos: list[MovimientoResponse]