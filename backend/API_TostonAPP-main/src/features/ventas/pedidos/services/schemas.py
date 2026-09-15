from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


# ── Respuesta de un pedido (hereda la misma estructura que venta) ──
class PedidoResponse(BaseModel):
    ID_Venta:             int
    ID_Usuario:           Optional[int]     = None
    nombre_cliente:       Optional[str]     = None
    correo_cliente:       Optional[str]     = None
    telefono_cliente:     Optional[str]     = None
    Total:                Optional[Decimal] = None
    subtotal_bruto:       Optional[Decimal] = None
    credito_aplicado:     Optional[Decimal] = None
    descuento_aplicado:   Optional[Decimal] = None
    Estado:               Optional[int]     = None
    estado_label:         Optional[str]     = None
    Metodo_Pago:          Optional[str]     = None
    # Pago mixto: cuánto se paga de cada forma (null si no es mixto)
    monto_efectivo:       Optional[Decimal] = None
    monto_transferencia:  Optional[Decimal] = None
    Fecha_pedido:           Optional[datetime] = None
    Fecha_entrega_esperada: Optional[datetime] = None
    productos:              list               = []
    tiene_domicilio:              bool              = False
    ID_Domicilio:                 Optional[int]     = None
    direccion_entrega:            Optional[str]     = None
    municipio_entrega:            Optional[str]     = None
    departamento_entrega:         Optional[str]     = None
    # Precio del domicilio: snapshot congelado (barrio + ofertas del día)
    ID_Barrio:                    Optional[int]     = None
    barrio_entrega:               Optional[str]     = None
    precio_domicilio_base:        Optional[int]     = None
    precio_domicilio_final:       Optional[int]     = None
    desglose_domicilio:           Optional[dict]    = None
    comprobante_pago:             Optional[str]     = None
    nombre_domiciliario:          Optional[str]     = None
    ordenes_produccion_pendientes: int              = 0
    ordenes_en_espera:             int              = 0
    requiere_produccion:          bool              = False
    # Pedido especial por encima del stock: bandera y anticipo del 50%
    sobre_stock:                  bool              = False
    anticipo_requerido:           Optional[Decimal] = None
    anticipo_pagado:              Optional[Decimal] = None
    # Anticipo registrado manualmente por admin (pedidos > $50.000 o preorden)
    requiere_anticipo:            bool              = False
    anticipo_monto:               Optional[Decimal] = None
    anticipo_metodo_pago:         Optional[str]     = None
    anticipo_comprobante_url:     Optional[str]     = None
    anticipo_registrado:          bool              = False
    # Pago final
    pago_final_registrado:        bool              = False
    pago_final_monto:             Optional[Decimal] = None
    pago_final_metodo_pago:       Optional[str]     = None
    pago_final_comprobante_url:   Optional[str]     = None
    pago_final_fecha:             Optional[datetime] = None
    # Estado del pago y metadatos adicionales
    estado_pago:                       Optional[str]     = None
    motivo_rechazo_comprobante:        Optional[str]     = None
    fecha_rechazada:                   Optional[datetime] = None
    # Segundo comprobante: el saldo restante tras el anticipo (3.10)
    saldo_comprobante_url:                    Optional[str] = None
    intentos_rechazo_comprobante_anticipo:    int           = 0
    intentos_rechazo_comprobante_saldo:       int           = 0
    fecha_retenido_en_tienda:                 Optional[datetime] = None
    ID_Empleado:                  Optional[int]     = None
    observaciones_domicilio:      Optional[str]     = None
    Numero_Pedido:                Optional[str]     = None
    # Solo los pedidos sobre stock o de producción necesitan fecha propuesta
    requiere_fecha_propuesta:     bool              = False
    # Respuesta del cliente a "¿todo junto el domingo?" (None = sin responder)
    envio_completo_domingo:       Optional[bool]    = None

    class Config:
        from_attributes = True


# ── Registrar cobro en efectivo desde el panel admin ──
class RegistroCobro(BaseModel):
    recibido: bool
    monto:    Optional[float] = None
    motivo:   Optional[str]  = None


# ── 3.7: cambiar a domicilio un pedido "Retenido en tienda" ──
class CambioADomicilio(BaseModel):
    ID_Barrio:             int
    Direccion_entrega:     str
    Municipio_entrega:     Optional[str] = None
    Departamento_entrega:  Optional[str] = None
    Observaciones:         Optional[str] = None


# ── Actualización parcial de un pedido pendiente ──
class PedidoUpdate(BaseModel):
    Metodo_Pago:          Optional[str]   = None
    Domicilio:            Optional[bool]  = None
    Direccion_Entrega:    Optional[str]   = None
    # Barrio de entrega. Al cambiarlo se RECALCULA el precio del domicilio y se
    # ajusta el Total (edición explícita; ver zona de peligro del snapshot).
    # Municipio/Departamento se derivan del barrio, no se aceptan del request.
    ID_Barrio:            Optional[int]   = None
    Subtotal:             Optional[float] = None
    Descuento:            Optional[float] = None
    Total:                Optional[float] = None
    Notas:                Optional[str]   = None
    Comprobante_Pago:     Optional[str]   = None


# ── Línea de producto al reabrir la negociación de fecha (editar cantidad) ──
class ProductoEditInput(BaseModel):
    ID_Producto: int = Field(..., gt=0)
    Cantidad:    int = Field(..., gt=0)


# ── Edición del pedido por el propio cliente ──
class PedidoClienteEdit(BaseModel):
    Metodo_Pago:       Optional[str]   = None
    quiere_domicilio:  Optional[bool]  = None
    ID_Barrio:         Optional[int]   = None
    Direccion_Entrega: Optional[str]   = None
    Notas:             Optional[str]   = None
    # URL Cloudinary del comprobante; obligatorio al cambiar a Transferencia o Mixto
    Comprobante_Pago:  Optional[str]   = None
    # Para Mixto: cuánto paga en efectivo; el resto se carga a transferencia
    Monto_Efectivo:    Optional[float] = None
    # Reabrir la negociación de fecha ('Pendiente de Aprobación' / 'Fecha
    # propuesta'): ajustar cantidades de líneas ya existentes (no agrega
    # productos nuevos) y/o la fecha límite deseada.
    productos:              Optional[list[ProductoEditInput]] = None
    Fecha_entrega_esperada: Optional[datetime]                = None


# ── El cliente paga (o anticipa) un pedido 'Esperando Pago' ──
class PedidoPago(BaseModel):
    comprobante_url: str
    # Solo relevante si el pedido requiere anticipo (mínimo 50% del total,
    # siempre por transferencia); se ignora si no lo requiere.
    monto: Optional[float] = None


# ── Respuesta paginada ──
class PedidoListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    pedidos:    list[PedidoResponse]