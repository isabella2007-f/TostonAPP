from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


# ── Producto dentro de una venta ──
class ProductoVentaInput(BaseModel):
    ID_Producto: int = Field(..., gt=0)
    Cantidad:    int = Field(..., gt=0)


# ── Domicilio opcional al crear venta ──
class DomicilioVentaInput(BaseModel):
    Direccion_entrega:    str
    # Barrio de entrega: determina el precio del domicilio. Obligatorio cuando
    # hay domicilio (el backend lo valida en crear_venta). Municipio y
    # departamento se DERIVAN del barrio; el texto que llegue es solo respaldo.
    ID_Barrio:            Optional[int]      = None
    Municipio_entrega:    Optional[str]      = None
    Departamento_entrega: Optional[str]      = None
    Observaciones:        Optional[str]      = None
    Fecha_entrega:        Optional[datetime] = None
    ID_Empleado:          Optional[int]      = None  # repartidor


# ── Crear venta ──
class VentaCreate(BaseModel):
    ID_Usuario:             int
    Metodo_Pago:            str                              # "Efectivo", "Transferencia", "Contra entrega", "Mixto"
    # Solo con Metodo_Pago = "Mixto": cuánto del pedido se paga en efectivo.
    # En pesos, no en porcentaje: el cliente pone la plata que tiene encima
    # ("$3.500 de $22.500"), que casi nunca cae en un porcentaje redondo.
    # El backend lo recorta al total real; el resto va por transferencia.
    pago_efectivo_monto:      Optional[Decimal]  = None
    A_Nombre_De:            Optional[str]       = None
    productos:              list[ProductoVentaInput]
    codigo_descuento:       Optional[str]       = None
    usar_credito:           bool                = False
    # Cuanto saldo a favor aplicar. None = todo lo que alcance, que es como se
    # comportaba antes: el checkout solo sabia decir si o no.
    credito_monto:          Optional[Decimal]   = None
    domicilio:              Optional[DomicilioVentaInput] = None
    comprobante_pago:         Optional[str]       = None
    Fecha_entrega_esperada:   Optional[datetime]  = None
    creado_por_admin:         bool                = False
    requiere_anticipo:        bool                = False
    anticipo_monto:           Optional[float]     = None
    anticipo_metodo_pago:     Optional[str]       = None
    anticipo_comprobante_url: Optional[str]       = None
    anticipo_registrado:      bool                = False
    # El cliente eligió pagar el total ahora (no solo el 50%). El servidor lo
    # usa para marcar pago_final_registrado=1 sin comparar montos exactos,
    # evitando fallos por diferencias de redondeo entre el total del cliente
    # (JS) y el total del servidor (Decimal).
    pagar_todo:               bool                = False
    # Respuesta a "¿Quiere que le enviemos todo junto el domingo?"
    # None = no se preguntó aún; True = sí; False = no.
    envio_completo_domingo:   Optional[bool]      = None


# ── Registrar pago del saldo final al entregar ──
class PagoFinalCreate(BaseModel):
    monto:           float
    metodo_pago:     str            # "Efectivo" | "Transferencia"
    comprobante_url: Optional[str]  = None  # requerido solo para Transferencia


# ── Cambiar estado de venta ──
class VentaEstado(BaseModel):
    Estado: int


# ── Proponer fecha de entrega ──
class FechaEntregaInput(BaseModel):
    fecha_entrega: datetime
    # Justificación opcional de la contraoferta (3.4, hallazgo #4): por qué
    # esa fecha, para que el cliente tenga contexto al decidir.
    motivo: Optional[str] = None


# ── Respuesta de producto en venta ──
class ProductoVentaResponse(BaseModel):
    ID_Producto:     int
    nombre_producto: Optional[str]    = None
    Cantidad:        int
    precio_unitario: Optional[Decimal] = None
    subtotal:        Optional[Decimal] = None
    imagen:          Optional[str]     = None
    # Unidades pedidas por encima del stock (preorden) y stock actual del producto
    cantidad_preorden: int = 0
    stock_disponible:  int = 0


# ── Respuesta de una venta ──
class VentaResponse(BaseModel):
    ID_Venta:               int
    ID_Usuario:             Optional[int]      = None
    nombre_cliente:         Optional[str]      = None
    # El service los arma desde hace rato, pero sin declararlos acá Pydantic
    # los borraba de la respuesta y las vistas mostraban el cliente sin datos
    # de contacto.
    correo_cliente:         Optional[str]      = None
    telefono_cliente:       Optional[str]      = None
    Total:                  Optional[Decimal]  = None
    subtotal_bruto:         Optional[Decimal]  = None
    credito_aplicado:       Optional[Decimal]  = None
    descuento_aplicado:     Optional[Decimal]  = None
    Estado:                 Optional[int]      = None
    estado_label:           Optional[str]      = None
    Metodo_Pago:            Optional[str]      = None
    Fecha_Venta:            Optional[datetime] = None
    Fecha_pedido:           Optional[datetime] = None
    Fecha_entrega:          Optional[datetime] = None
    Fecha_entrega_esperada: Optional[datetime] = None
    productos:              list[ProductoVentaResponse] = []
    tiene_domicilio:          bool               = False
    ID_Domicilio:             Optional[int]      = None
    direccion_entrega:        Optional[str]      = None
    municipio_entrega:        Optional[str]      = None
    departamento_entrega:     Optional[str]      = None
    # Precio del domicilio: snapshot congelado (barrio + ofertas del día).
    ID_Barrio:                Optional[int]      = None
    barrio_entrega:           Optional[str]      = None
    precio_domicilio_base:    Optional[int]      = None
    precio_domicilio_final:   Optional[int]      = None
    desglose_domicilio:       Optional[dict]     = None
    observaciones_domicilio:  Optional[str]      = None
    nombre_domiciliario:      Optional[str]      = None
    # Repartidor asignado. El panel lo usa como respaldo para resolver el
    # nombre contra su lista de empleados; sin declararlo acá, Pydantic lo
    # descartaba y ese camino no servía para nada.
    ID_Empleado:              Optional[int]      = None
    comprobante_pago:         Optional[str]      = None
    # Pago mixto: cuánto se paga de cada forma
    monto_efectivo:           Optional[Decimal]  = None
    monto_transferencia:      Optional[Decimal]  = None
    # Pedido especial por encima del stock: bandera y anticipo del 50%
    sobre_stock:            bool               = False
    anticipo_requerido:     Optional[Decimal]  = None
    anticipo_pagado:        Optional[Decimal]  = None
    # Anticipo general (pedidos > $50k creados por admin)
    requiere_anticipo:        bool               = False
    anticipo_monto:           Optional[Decimal]  = None
    anticipo_metodo_pago:     Optional[str]      = None
    anticipo_comprobante_url: Optional[str]      = None
    anticipo_registrado:      bool               = False
    # Pago final (saldo tras anticipo)
    pago_final_registrado:    bool               = False
    pago_final_monto:         Optional[Decimal]  = None
    pago_final_metodo_pago:   Optional[str]      = None
    pago_final_comprobante_url: Optional[str]    = None
    pago_final_fecha:         Optional[datetime] = None
    estado_pago:              Optional[str]      = None
    # Solo los pedidos sobre stock o de producción necesitan fecha propuesta
    requiere_fecha_propuesta:      bool             = False
    requiere_produccion:           bool             = False
    ordenes_produccion_pendientes: int              = 0
    ordenes_en_espera:             int              = 0
    # Respuesta del cliente a "¿Todo junto el domingo?"
    envio_completo_domingo:        Optional[bool]   = None
    # Negociación de fecha: cuándo rechazó la última propuesta y cuántas van.
    # Sin esto el pedido reaparecía idéntico a uno recién hecho.
    fecha_rechazada:               Optional[datetime] = None
    intentos_rechazo:              int              = 0
    # Segundo comprobante: el saldo restante tras el anticipo (3.10)
    saldo_comprobante_url:                    Optional[str] = None
    intentos_rechazo_comprobante_anticipo:    int           = 0
    intentos_rechazo_comprobante_saldo:       int           = 0
    fecha_retenido_en_tienda:                 Optional[datetime] = None
    class Config:
        from_attributes = True


# ── Respuesta paginada ──
class VentaListResponse(BaseModel):
    total:      int
    pagina:     int
    por_pagina: int
    ventas:     list[VentaResponse]


# ── Respuesta del cliente: ¿todo junto el domingo? ──
class EnvioCompletoDomingoInput(BaseModel):
    envio_completo_domingo: bool


# ── El cliente rechaza la fecha propuesta con su propia contraoferta final:
# fecha propia y motivo, los dos obligatorios (prompt-pedidos-2, 3.4) ──
class RechazarFechaInput(BaseModel):
    fecha_propuesta: datetime
    motivo: str


# ── Admin rechaza en definitivo la propuesta final del cliente; motivo opcional ──
class RechazarFechaFinalInput(BaseModel):
    motivo: Optional[str] = None


# ── Acuerdo manual admin para escalado ──
class AcuerdoManualInput(BaseModel):
    fecha_acordada: datetime


# ── Rechazar comprobante de transferencia ──
class RechazoComprobante(BaseModel):
    motivo: str


