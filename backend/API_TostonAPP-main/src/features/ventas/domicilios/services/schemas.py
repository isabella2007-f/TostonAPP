from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime


# -- Crear domicilio --
class DomicilioCreate(BaseModel):
    ID_Venta:             int
    ID_Empleado:          Optional[int] = None
    Direccion_entrega:    str
    Municipio_entrega:    str
    Departamento_entrega: str
    Observaciones:        Optional[str] = None
    Fecha_entrega:        Optional[datetime] = None


# -- Editar domicilio --
class DomicilioUpdate(BaseModel):
    Direccion_entrega:    Optional[str]      = None
    Municipio_entrega:    Optional[str]      = None
    Departamento_entrega: Optional[str]      = None
    Observaciones:        Optional[str]      = None
    Fecha_entrega:        Optional[datetime] = None


# -- Asignar repartidor --
class AsignarRepartidor(BaseModel):
    ID_Empleado: int


# -- Cambiar estado --
class DomicilioEstado(BaseModel):
    Estado:        int
    Observaciones: Optional[str] = None  # comentario del repartidor al cambiar estado


# -- Respuesta de un domicilio --
class DomicilioResponse(BaseModel):
    ID_Domicilio:         int
    ID_Venta:             Optional[int]      = None
    nombre_cliente:       Optional[str]      = None
    ID_Empleado:          Optional[int]      = None
    nombre_repartidor:    Optional[str]      = None
    Fecha_asignacion:     Optional[datetime] = None
    Fecha_entrega:        Optional[datetime] = None
    Observaciones:        Optional[str]      = None
    # Una por autor. Sin declararlas acá, Pydantic las descarta aunque el
    # servicio las devuelva.
    observaciones_admin:      Optional[str]  = None
    observaciones_repartidor: Optional[str]  = None
    indicaciones_cliente: Optional[str]      = None
    Estado:               Optional[int]      = None
    estado_label:         Optional[str]      = None
    Direccion_entrega:    Optional[str]      = None
    Municipio_entrega:    Optional[str]      = None
    Departamento_entrega: Optional[str]      = None
    # Snapshot del precio del domicilio (barrio + ofertas del día), congelado
    ID_Barrio:              Optional[int]    = None
    barrio_entrega:         Optional[str]    = None
    precio_domicilio_base:  Optional[int]    = None
    precio_domicilio_final: Optional[int]    = None
    desglose_domicilio:     Optional[dict]   = None
    total:                Optional[float]    = None
    metodo_pago:          Optional[str]      = None
    # Pago mixto: lo que hay que cobrar en mano (el resto ya vino por transferencia)
    monto_efectivo:       Optional[float]    = None
    estado_pago:          Optional[str]      = None
    # Anticipo: cuánto se pagó por adelantado y si ya fue registrado.
    anticipo_monto:       Optional[float]    = None
    anticipo_registrado:  Optional[bool]     = None
    productos:            Optional[List[Any]] = None
    telefono_cliente:     Optional[str]      = None
    # Estado de la venta asociada y comprobante de pago. El servicio ya los
    # construía; sin declararlos aquí Pydantic los descartaba y el panel no
    # podía mostrarlos.
    venta_estado:         Optional[int]      = None
    comprobante_pago:     Optional[str]      = None

    class Config:
        from_attributes = True


# -- Respuesta paginada --
class DomicilioListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    domicilios: list[DomicilioResponse]


# -- Chat --
class MensajeCreate(BaseModel):
    Contenido: str


class MensajeResponse(BaseModel):
    ID_Mensaje:       int
    ID_Domicilio:     int
    Tipo_Remitente:   str
    ID_Remitente:     int
    Nombre_Remitente: Optional[str] = None
    Contenido:        str
    Fecha:            Optional[datetime] = None


# -- Registrar cobro en efectivo (domiciliario) --
class RegistroPagoEfectivo(BaseModel):
    recibido: bool
    monto:    Optional[float] = None   # requerido si recibido=True; debe ser exacto
    motivo:   Optional[str]  = None    # requerido si recibido=False; min 10 caracteres

    @field_validator("monto")
    @classmethod
    def monto_positivo(cls, v):
        if v is not None and v <= 0:
            raise ValueError("El monto debe ser mayor a 0")
        return v

    @field_validator("motivo")
    @classmethod
    def motivo_minimo(cls, v):
        if v is not None and len(v.strip()) < 10:
            raise ValueError("El motivo debe tener al menos 10 caracteres")
        return v
