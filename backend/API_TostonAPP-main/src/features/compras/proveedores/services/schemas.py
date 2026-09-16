from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Crear proveedor ──
class ProveedorCreate(BaseModel):
    Sujeto_Derecho: int
    NIT:            Optional[str] = None
    Cedula:         Optional[str] = None
    Responsable:    str
    Direccion:      Optional[str] = None
    Municipio:      Optional[str] = None
    Departamento:   Optional[str] = None
    Telefono:       Optional[str] = None
    Correo:         Optional[EmailStr] = None


# ── Editar proveedor ──
class ProveedorUpdate(BaseModel):
    Sujeto_Derecho: Optional[int] = None
    NIT:            Optional[str] = None
    Cedula:         Optional[str] = None
    Responsable:    Optional[str] = None
    Direccion:      Optional[str] = None
    Municipio:      Optional[str] = None
    Departamento:   Optional[str] = None
    Telefono:       Optional[str] = None
    Correo:         Optional[EmailStr] = None


# ── Respuesta de un proveedor ──
class ProveedorResponse(BaseModel):
    ID_Proveedor:          int
    Sujeto_Derecho:        Optional[int] = None
    nombre_sujeto:         Optional[str] = None
    NIT:                   Optional[str] = None
    Cedula:                Optional[str] = None
    Responsable:           str
    Direccion:             Optional[str] = None
    Municipio:             Optional[str] = None
    Departamento:          Optional[str] = None
    Telefono:              Optional[str] = None
    Correo:                Optional[str] = None
    total_compras:         int = 0
    ultima_compra_fecha:   Optional[datetime] = None
    ultima_compra_estado:  Optional[str] = None
    insumos_provistos:     List[str] = []

    class Config:
        from_attributes = True


# ── Respuesta paginada ──
class ProveedorListResponse(BaseModel):
    total:       int
    pagina:      int
    por_pagina:  int
    proveedores: list[ProveedorResponse]
