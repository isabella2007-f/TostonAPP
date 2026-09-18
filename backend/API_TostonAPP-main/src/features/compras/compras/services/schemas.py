from pydantic import BaseModel, model_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal

METODOS_PAGO_COMPRA = {"Efectivo", "Transferencia", "Crédito", "Cheque"}

CANT_MAX   = Decimal("10000")
TOTAL_MIN  = Decimal("0")            # el mínimo permitido es 0 (>= 0)
TOTAL_MAX  = Decimal("50000000")
PORC_MAX   = Decimal("100")          # IVA y descuento son porcentajes: 0–100 (admiten decimales)
MONTO_MAX  = Decimal("99999999")     # transporte / otros costos: máx. 8 dígitos, pesos enteros


def _dec(v) -> Decimal:
    """Normaliza cualquier valor numérico (o None) a Decimal."""
    return Decimal(str(v if v is not None else 0))


def validar_comprobante(url) -> None:
    """El comprobante es una URL de Cloudinary (string plano). Rechaza cualquier
    otra cosa: nunca base64, nunca esquemas peligrosos."""
    if url is None or url == "":
        return
    if not isinstance(url, str) or len(url) > 500:
        raise ValueError("El comprobante debe ser una URL válida de máximo 500 caracteres")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("El comprobante debe ser una URL http(s) (imagen subida a Cloudinary)")


def calcular_total_compra(detalles, costo_transporte, iva_porcentaje,
                          descuento_porcentaje, otros_costos) -> Decimal:
    """Fuente única de la aritmética del total de una compra.

    `detalles` es cualquier iterable de objetos con `.Cantidad` y `.Precio_Und`
    (sirve tanto para los schemas de entrada como para los modelos ORM).
    """
    subtotal = sum((_dec(d.Precio_Und) * _dec(d.Cantidad) for d in detalles), Decimal("0"))
    iva_val  = subtotal * _dec(iva_porcentaje) / 100
    desc_val = subtotal * _dec(descuento_porcentaje) / 100
    total = subtotal + _dec(costo_transporte) + iva_val - desc_val + _dec(otros_costos)
    return total.quantize(Decimal("0.01"))


def validar_limites_compra(*, iva=None, descuento=None, transporte=None,
                           otros=None, fecha_compra=None, detalles=None) -> None:
    """Valida los límites de negocio comunes a crear y editar. Lanza ValueError."""
    # IVA y descuento son porcentajes (0–100); admiten decimales.
    if iva is not None and not (Decimal("0") <= _dec(iva) <= PORC_MAX):
        raise ValueError("El IVA debe estar entre 0 y 100%")
    if descuento is not None and not (Decimal("0") <= _dec(descuento) <= PORC_MAX):
        raise ValueError("El descuento debe estar entre 0 y 100%")
    # Transporte y otros costos son montos en pesos enteros, máx. 8 dígitos.
    for etiqueta, valor in (("transporte", transporte), ("otros costos", otros)):
        if valor is None:
            continue
        v = _dec(valor)
        if v < 0:
            raise ValueError(f"El valor de {etiqueta} no puede ser negativo")
        if v != v.to_integral_value():
            raise ValueError(f"El valor de {etiqueta} debe ser un número entero (pesos)")
        if v > MONTO_MAX:
            raise ValueError(f"El valor de {etiqueta} supera el máximo permitido de 8 dígitos")
    if fecha_compra is not None and fecha_compra.date() > datetime.now().date():
        raise ValueError("La fecha de compra no puede ser futura")
    for d in detalles or []:
        if d.Cantidad is None or d.Cantidad <= 0:
            raise ValueError(f"La cantidad del insumo {d.ID_Insumo} debe ser mayor a cero")
        if d.Cantidad > CANT_MAX:
            raise ValueError(
                f"La cantidad del insumo {d.ID_Insumo} supera el máximo permitido "
                f"({int(CANT_MAX):,} unidades por línea)"
            )
        if d.Precio_Und is None or d.Precio_Und <= 0:
            raise ValueError(f"El precio unitario del insumo {d.ID_Insumo} debe ser mayor a cero")


def validar_rango_total(total: Decimal) -> None:
    """El total ya calculado debe caer dentro de [TOTAL_MIN, TOTAL_MAX]."""
    if total < TOTAL_MIN:
        raise ValueError(f"El total de la compra (${total:,.0f} COP) no puede ser negativo")
    if total > TOTAL_MAX:
        raise ValueError(
            f"El total de la compra (${total:,.0f} COP) supera el máximo permitido "
            f"(${int(TOTAL_MAX):,} COP)"
        )


# ── Completar compra (body opcional) ──
class CompletarCompraInput(BaseModel):
    Fecha_Llegada: Optional[datetime] = None


# ── Detalle de un ítem dentro de la compra ──
class DetalleCompraInput(BaseModel):
    ID_Insumo:         int
    ID_Unidad_Compra:  Optional[int] = None   # unidad elegida en el formulario
    Cantidad:          Decimal   # Decimal para soportar kg, g, L, mL
    Precio_Und:        Decimal
    Notas:             Optional[str] = None
    Fecha_Vencimiento: Optional[datetime] = None  # para crear el LoteCompra


# ── Editar compra ──
class CompraUpdate(BaseModel):
    ID_Proveedor:         Optional[int]      = None
    Metodo_Pago:          Optional[str]      = None
    Fecha_Compra:         Optional[datetime] = None
    Notas:                Optional[str]      = None
    Comprobante:          Optional[str]      = None
    Fecha_Llegada:        Optional[datetime] = None
    Costo_Transporte:     Optional[Decimal]  = None
    IVA_Porcentaje:       Optional[Decimal]  = None
    Descuento_Porcentaje: Optional[Decimal]  = None
    Otros_Costos:         Optional[Decimal]  = None
    detalles:             Optional[list[DetalleCompraInput]] = None

    @model_validator(mode="after")
    def validar(self):
        # Distingue "no enviado" (queda como está) de "enviado vacío" (borrar el método) → obligatorio.
        if self.Metodo_Pago is not None:
            if not self.Metodo_Pago.strip():
                raise ValueError("El método de pago es obligatorio")
            if self.Metodo_Pago not in METODOS_PAGO_COMPRA:
                raise ValueError(f"Método de pago inválido. Opciones: {', '.join(sorted(METODOS_PAGO_COMPRA))}")
        validar_comprobante(self.Comprobante)
        validar_limites_compra(
            iva=self.IVA_Porcentaje, descuento=self.Descuento_Porcentaje,
            transporte=self.Costo_Transporte, otros=self.Otros_Costos,
            fecha_compra=self.Fecha_Compra, detalles=self.detalles,
        )
        return self


# ── Crear compra ──
class CompraCreate(BaseModel):
    ID_Proveedor:         int
    Metodo_Pago:          str                       # ver METODOS_PAGO_COMPRA
    Fecha_Compra:         Optional[datetime] = None # si no se envía, se usa datetime.now()
    Notas:                Optional[str]     = None
    Comprobante:          Optional[str]     = None  # URL Cloudinary (opcional, aunque sea transferencia)
    Costo_Transporte:     Optional[Decimal] = None
    IVA_Porcentaje:       Optional[Decimal] = None
    Descuento_Porcentaje: Optional[Decimal] = None
    Otros_Costos:         Optional[Decimal] = None
    detalles:             list[DetalleCompraInput]

    @model_validator(mode="after")
    def validar_campos(self):
        if not self.Metodo_Pago or not self.Metodo_Pago.strip():
            raise ValueError("El método de pago es obligatorio")
        if self.Metodo_Pago not in METODOS_PAGO_COMPRA:
            opciones = ", ".join(sorted(METODOS_PAGO_COMPRA))
            raise ValueError(f"Método de pago inválido. Opciones: {opciones}")
        if not self.detalles:
            raise ValueError("La compra debe tener al menos un ítem en detalles")

        validar_comprobante(self.Comprobante)
        validar_limites_compra(
            iva=self.IVA_Porcentaje, descuento=self.Descuento_Porcentaje,
            transporte=self.Costo_Transporte, otros=self.Otros_Costos,
            fecha_compra=self.Fecha_Compra, detalles=self.detalles,
        )

        # Recalcular total en el backend — no confiar en el valor enviado por el frontend
        total = calcular_total_compra(
            self.detalles, self.Costo_Transporte, self.IVA_Porcentaje,
            self.Descuento_Porcentaje, self.Otros_Costos,
        )
        validar_rango_total(total)
        return self


# ── Lote de insumo (para el detalle de compra: 3.15) ──
class LoteCompraInfo(BaseModel):
    id:               int
    id_compra:        Optional[int]     = None   # compra que originó el lote
    fecha_vencimiento: Optional[str]    = None
    cantidad_inicial: Optional[Decimal] = None
    cantidad_actual:  Optional[Decimal] = None
    consumido:        Optional[Decimal] = None
    estado:           Optional[int]     = None
    vencido:          bool              = False


# ── Respuesta de un detalle ──
class DetalleCompraResponse(BaseModel):
    ID_Detalle_Compra:     int
    ID_Insumo:             Optional[int]     = None
    nombre_insumo:         Optional[str]     = None
    ID_Unidad_Medida:      Optional[int]     = None
    ID_Unidad_Compra:      Optional[int]     = None
    simbolo_unidad_compra: Optional[str]     = None
    ID_Lote_Compra:        Optional[int]     = None
    Cantidad:              Optional[Decimal]  = None
    Precio_Und:            Optional[Decimal] = None
    Notas:                 Optional[str]     = None
    Fecha_Vencimiento:     Optional[str]     = None
    # 3.15 — se pueblan solo en GET /compras/{id}
    lote_origen:      Optional[LoteCompraInfo]  = None
    otros_lotes:      list[LoteCompraInfo]      = []

    class Config:
        from_attributes = True


# ── Respuesta de una compra ──
class CompraResponse(BaseModel):
    ID_Compra:            int
    ID_Proveedor:         Optional[int]      = None
    nombre_proveedor:     Optional[str]      = None
    Total_Pago:           Optional[Decimal]  = None
    Fecha_Compra:         Optional[datetime] = None
    Fecha_Llegada:        Optional[datetime] = None
    Fecha_Anulada:        Optional[datetime] = None
    Estado:               Optional[int]      = None
    estado_label:         Optional[str]      = None
    Metodo_Pago:          Optional[str]      = None
    Notas:                Optional[str]      = None
    Comprobante:          Optional[str]      = None
    Costo_Transporte:     Optional[Decimal]  = None
    IVA_Porcentaje:       Optional[Decimal]  = None
    Descuento_Porcentaje: Optional[Decimal]  = None
    Otros_Costos:         Optional[Decimal]  = None
    detalles:             list[DetalleCompraResponse] = []

    class Config:
        from_attributes = True


# ── Respuesta paginada ──
class CompraListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    compras:    list[CompraResponse]
