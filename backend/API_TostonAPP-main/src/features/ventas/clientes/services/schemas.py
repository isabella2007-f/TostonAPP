from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

TIPOS_DOCUMENTO = ["CC", "CE", "NIT", "TI", "PP"]


class FotoUrlInput(BaseModel):
    url: str


class ClienteCreate(BaseModel):
    Cedula:               str
    Tipo_Documento:       str
    Nombre:               str
    Apellidos:            str
    Correo:               EmailStr
    Contrasena:           str
    Confirmar_Contrasena: str
    Telefono:             Optional[str]      = None
    Fecha_creacion:       Optional[datetime] = None
    Estado:               Optional[int]      = 1
    Direccion:            Optional[str]      = None
    Departamento:         Optional[str]      = None
    Municipio:            Optional[str]      = None


class ClienteUpdate(BaseModel):
    Cedula:         Optional[str]       = None
    Tipo_Documento: Optional[str]       = None
    Nombre:         Optional[str]       = None
    Apellidos:      Optional[str]       = None
    Correo:         Optional[EmailStr]  = None
    Telefono:       Optional[str]       = None
    Direccion:      Optional[str]       = None
    Departamento:   Optional[str]       = None
    Municipio:      Optional[str]       = None
    Estado:         Optional[int]       = None


class ClienteEstado(BaseModel):
    Estado: int


class ClienteResponse(BaseModel):
    ID_Usuario:      int                        # ← PK autoincremental
    Cedula:          Optional[str]      = None  # ← campo normal
    Tipo_Documento:  Optional[str]      = None
    Nombre:          str
    Apellidos:       str
    Correo:          str
    Telefono:        Optional[str]      = None
    Fecha_creacion:  Optional[datetime] = None
    Estado:          Optional[int]      = None
    Direccion:       Optional[str]      = None
    Departamento:    Optional[str]      = None
    Municipio:       Optional[str]      = None
    # Un campo que no esté declarado acá lo descarta Pydantic en silencio,
    # aunque el servicio lo devuelva. Pasó con el barrio: salía del servicio,
    # se perdía en el esquema, y el panel pedía "elige el barrio de entrega"
    # por un cliente que ya tenía el suyo guardado.
    ID_Barrio:       Optional[int]      = None
    Indicaciones:    Optional[str]      = None
    Auto_Eliminado:  Optional[bool]     = None
    tiene_foto:      bool               = False

    class Config:
        from_attributes = True


class ClienteListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    clientes:   list[ClienteResponse]