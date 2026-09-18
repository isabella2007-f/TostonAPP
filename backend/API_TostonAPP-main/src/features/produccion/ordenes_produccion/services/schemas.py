from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any, List
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal


def _hoy_local() -> date:
    return datetime.now(timezone(timedelta(hours=-5))).date()


# ── Crear orden ──
class OrdenCreate(BaseModel):
    ID_Producto:   int
    ID_Insumo:     Optional[int] = None
    ID_Ficha:      Optional[int] = None
    Cantidad:      int = Field(gt=0, le=999, description="Entre 1 y 999")
    # Por defecto es hoy; el servicio la completa si no viene.
    Fecha_inicio:  Optional[datetime] = None
    Fecha_Entrega: datetime

    @model_validator(mode="after")
    def validar_fechas(self):
        hoy = _hoy_local()
        inicio = self.Fecha_inicio.date() if self.Fecha_inicio else hoy
        if inicio < hoy:
            raise ValueError("La Fecha_inicio no puede ser anterior a hoy")
        if self.Fecha_Entrega.date() < inicio:
            raise ValueError("La Fecha_Entrega no puede ser anterior a la Fecha_inicio")
        return self


# ── Editar orden ──
class OrdenUpdate(BaseModel):
    ID_Producto:   Optional[int]      = None
    ID_Insumo:     Optional[int]      = None
    ID_Ficha:      Optional[int]      = None
    Cantidad:      Optional[int]      = Field(default=None, gt=0, le=999, description="Entre 1 y 999")
    Fecha_inicio:  Optional[datetime] = None
    Fecha_Entrega: Optional[datetime] = None

    @model_validator(mode="after")
    def validar_fechas_update(self):
        if self.Fecha_inicio is not None and self.Fecha_Entrega is not None:
            if self.Fecha_Entrega.date() < self.Fecha_inicio.date():
                raise ValueError("La Fecha_Entrega no puede ser anterior a la Fecha_inicio")
        return self


# ── Cambiar estado ──
class OrdenEstado(BaseModel):
    Estado: int     # ID del estado en la tabla Estados
    Numero_Lote: Optional[str] = None
    Fecha_Vencimiento: Optional[date] = None


# ── Respuesta de una orden ──
class OrdenResponse(BaseModel):
    ID_Orden_Produccion: int
    ID_Venta:            Optional[int]      = None
    venta_estado:        Optional[int]      = None
    venta_estado_label:  Optional[str]      = None
    ID_Producto:         Optional[int]      = None
    nombre_producto:     Optional[str]      = None
    ID_Insumo:           Optional[int]      = None
    nombre_insumo:       Optional[str]      = None
    stock_insumo:        Optional[float]    = None
    ID_Ficha:            Optional[int]      = None
    version_ficha:       Optional[str]      = None
    Cantidad:            Optional[int]      = None
    Fecha_Creacion:      Optional[datetime] = None
    Fecha_inicio:        Optional[datetime] = None
    Fecha_Entrega:       Optional[datetime] = None
    Fecha_fin:           Optional[datetime] = None
    Estado:              Optional[int]      = None
    estado_label:        Optional[str]      = None
    Costo:               Optional[float]    = None
    costo_detalle:       Optional[List[Any]] = None
    lote:                Optional[Any]      = None
    advertencia_vencimiento: Optional[str] = None

    class Config:
        from_attributes = True


# ── Respuesta paginada ──
class OrdenListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    ordenes:    list[OrdenResponse]
