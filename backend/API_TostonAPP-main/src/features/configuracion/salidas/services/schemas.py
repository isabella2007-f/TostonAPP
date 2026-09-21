from pydantic import BaseModel, model_validator, ConfigDict
from typing import Optional, Literal
from datetime import datetime

from src.shared.services.enums import TipoSalida

class SalidaCreate(BaseModel):
    Tipo:        Literal[
        TipoSalida.VENCIMIENTO, TipoSalida.DANO, TipoSalida.AJUSTE,
        TipoSalida.CONSUMO, TipoSalida.DEVOLUCION,
    ]
    ID_Insumo:   Optional[int] = None
    ID_Producto: Optional[int] = None
    Cantidad:    int
    Motivo:      Optional[str] = None
    ID_Empleado: Optional[int] = None
    Fecha:       Optional[datetime] = None  # si no se envía, se usa _now() (zona Bogotá)

    @model_validator(mode="after")
    def validar_item_y_cantidad(self):
        if self.ID_Insumo is None and self.ID_Producto is None:
            raise ValueError("Debes especificar ID_Insumo o ID_Producto")
        if self.ID_Insumo is not None and self.ID_Producto is not None:
            raise ValueError("Solo puedes especificar ID_Insumo o ID_Producto, no ambos")
        if self.Cantidad < 0:
            raise ValueError("La cantidad no puede ser negativa.")
        if self.Cantidad == 0:
            raise ValueError("La cantidad debe ser mayor que 0.")
        return self


class SalidaResponse(BaseModel):
    ID_Salida:         int
    Tipo:              str
    ID_Insumo:         Optional[int] = None
    nombre_insumo:     Optional[str] = None
    ID_Producto:       Optional[int] = None
    nombre_producto:   Optional[str] = None
    nombre_categoria:  Optional[str] = None
    simbolo_unidad:    Optional[str] = None
    Cantidad:          int
    Motivo:            Optional[str] = None
    ID_Empleado:       Optional[int] = None
    nombre_empleado:   Optional[str] = None
    Fecha:             datetime
    Estado:            int
    estado_label:      Optional[str] = None
    ID_Anulado_Por:    Optional[int] = None
    nombre_anulado_por: Optional[str] = None
    Fecha_Anulacion:   Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SalidaListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    salidas:    list[SalidaResponse]
