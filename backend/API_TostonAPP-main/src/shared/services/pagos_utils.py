"""Cómo se paga un pedido y qué falta por cobrar o por aprobar.

Espeja `frontend/src/utils/metodosPago.js` (web) y `lib/utils/metodos_pago.dart`
(app móvil). Las tres capas tienen que contestar lo mismo: si la app le muestra
al repartidor el botón de cobrar y el servidor no exige ese cobro, el pedido se
entrega sin la plata; y al revés, si el servidor exige algo que la app no sabe
pedir, el repartidor se queda trabado sin entender por qué.

Antes cada módulo preguntaba por su cuenta con `.lower()` y `in`, y el pedido
mixto no coincidía con ninguna de las preguntas: llevaba comprobante Y efectivo
en mano, pero se leía como si no llevara ninguno de los dos.

Desde la migración a `Pagos` (ver `models.py`), el monto/método/comprobante/
estado de cada "pata" del pago vive en su propia fila (`Tipo='anticipo'` |
`'saldo'`) en vez de en columnas sueltas de `Ventas`. Este módulo también es
el punto único para leer/crear esas filas — nadie hace `db.query(Pago)...`
por su cuenta fuera de acá.
"""
import re
from src.shared.services.models import Pago

_RE_MIXTO         = re.compile(r"mixto", re.IGNORECASE)
_RE_TRANSFERENCIA = re.compile(r"transf|nequi|daviplata|bancol|qr", re.IGNORECASE)
_RE_EFECTIVO      = re.compile(r"efectiv|contra|cash", re.IGNORECASE)

TIPO_ANTICIPO = "anticipo"
TIPO_SALDO    = "saldo"

# Estados de una fila de Pagos que cuentan como "resuelto a favor del negocio"
# (comprobante aprobado, o efectivo físicamente recibido).
ESTADOS_RESUELTOS_OK = frozenset({"aprobado", "recibido"})


def es_pago_mixto(metodo: str | None) -> bool:
    """El pedido se reparte entre efectivo y transferencia.

    Lleva las dos cargas a la vez —comprobante por lo transferido, plata en
    mano por lo demás—, así que las dos preguntas de abajo le dicen que sí.
    """
    return bool(_RE_MIXTO.search(metodo or ""))


def es_pago_transferencia(metodo: str | None) -> bool:
    """¿Hay un comprobante que revisar?"""
    return bool(_RE_TRANSFERENCIA.search(metodo or "")) or es_pago_mixto(metodo)


def es_pago_efectivo(metodo: str | None) -> bool:
    """¿Hay plata que cobrar en mano?"""
    return bool(_RE_EFECTIVO.search(metodo or "")) or es_pago_mixto(metodo)


# Estados en los que el cobro en mano ya quedó resuelto: o entró la plata, o el
# repartidor declaró por qué no entró (con motivo, que queda auditado).
#
# `anticipo_pagado` NO entra: en un pedido mixto significa que se aprobó la
# transferencia, y la parte en efectivo sigue sin cobrarse. Contarlo como
# resuelto es lo que dejaba entregar sin recibir la plata.
COBRO_RESUELTO = frozenset({
    "efectivo_recibido",
    "no_recibido",
    "pagado_completo",
})

# Estados en los que el comprobante ya pasó por el admin.
COMPROBANTE_APROBADO = frozenset({
    "pagado_completo",
    "anticipo_pagado",
})


def _estado_pago(venta) -> str:
    return (getattr(venta, "Estado_Pago", None) or "pendiente").strip()


def obtener_pago(db, id_venta: int, tipo: str) -> "Pago | None":
    """La fila de Pagos de esta venta para esa pata (`anticipo` | `saldo`), o
    None si todavía no existe."""
    return db.query(Pago).filter(Pago.ID_Venta == id_venta, Pago.Tipo == tipo).first()


def pago_o_nuevo(db, id_venta: int, tipo: str, metodo_pago: str) -> "Pago":
    """Devuelve la fila existente de esa pata, o crea una nueva en blanco
    (Estado='pendiente') si es la primera vez que se toca. Hace `flush()` para
    que la fila tenga `ID_Pago` de una, pero no hace commit — eso lo decide
    quien llama."""
    pago = obtener_pago(db, id_venta, tipo)
    if pago is None:
        pago = Pago(
            ID_Venta=id_venta, Tipo=tipo, Metodo_Pago=metodo_pago,
            Estado="pendiente", Intentos_Rechazo=0,
        )
        db.add(pago)
        db.flush()
    return pago


def tipo_cobro_efectivo(venta) -> str:
    """A qué fila de Pagos apunta un cobro en efectivo (domicilio, tienda,
    contra entrega, retenido-en-tienda): `'saldo'` si ya existe una pata
    previa por transferencia (anticipo exigido, o pedido mixto — la
    transferencia se paga al hacer el pedido); `'anticipo'` si el efectivo es
    el único pago de este pedido (pedido simple en efectivo, sin anticipo)."""
    if getattr(venta, "Requiere_Anticipo", 0) or es_pago_mixto(venta.Metodo_Pago):
        return TIPO_SALDO
    return TIPO_ANTICIPO


def cobro_efectivo_pendiente(db, venta) -> bool:
    """¿Queda plata por recibir en mano en este pedido?"""
    if not es_pago_efectivo(venta.Metodo_Pago):
        return False
    # Si el crédito del cliente cubre todo el total, no hay efectivo pendiente
    # sin importar el Metodo_Pago original registrado.
    descuento = float(getattr(venta, "Descuento", 0) or 0)
    total     = float(getattr(venta, "Total",    0) or 0)
    if total > 0 and descuento >= total:
        return False
    if _estado_pago(venta) in COBRO_RESUELTO:
        return False
    # En un mixto el efectivo tiene su propio registro (fila 'saldo'): el
    # admin puede cobrarlo antes de que se apruebe el comprobante, y ahí el
    # estado queda en "anticipo_pagado" aunque la plata ya haya entrado.
    if es_pago_mixto(venta.Metodo_Pago):
        saldo = obtener_pago(db, venta.ID_Venta, TIPO_SALDO)
        if saldo and saldo.Estado in ESTADOS_RESUELTOS_OK:
            return False
    return True


def saldo_final_pendiente(db, venta) -> bool:
    """¿Este pedido pidió anticipo y todavía debe el resto?

    El anticipo es la mitad: cubre los insumos, no el pedido. Entregar con solo
    esa mitad registrada es despachar la mercancía y quedarse esperando el
    resto, que es justo lo que el anticipo existe para evitar.

    No aplica a los pedidos normales, ni cuando el cliente decidió pagar todo
    por adelantado, ni cuando su saldo a favor cubre lo que faltaba.
    """
    pago_anticipo = obtener_pago(db, venta.ID_Venta, TIPO_ANTICIPO)
    anticipo = float(pago_anticipo.Monto or 0) if pago_anticipo else 0.0
    if anticipo <= 0:
        return False
    # Si ni el anticipo entró, el pedido ni siquiera llegó hasta acá: de eso se
    # encarga la validación general del estado de pago.
    if not pago_anticipo or not pago_anticipo.Monto:
        return False
    pago_saldo = obtener_pago(db, venta.ID_Venta, TIPO_SALDO)
    if pago_saldo and pago_saldo.Estado in ESTADOS_RESUELTOS_OK:
        return False
    if _estado_pago(venta) == "pagado_completo":
        return False
    total     = float(getattr(venta, "Total", 0) or 0)
    descuento = float(getattr(venta, "Descuento", 0) or 0)
    # Pagó todo por adelantado, o el saldo a favor tapó la diferencia.
    if total > 0 and (anticipo + descuento) >= total:
        return False
    return True


def comprobante_sin_aprobar(db, venta) -> bool:
    """¿Hay un comprobante adjunto que el admin todavía no aprobó?

    Se mira la fila `anticipo` (que es la que cubre tanto el anticipo como el
    total sin producción, o la mitad transferida de un mixto) porque es la
    única que `aprobar_comprobante` sabe aprobar: exigir otra cosa dejaría el
    pedido sin salida.
    """
    if not es_pago_transferencia(venta.Metodo_Pago):
        return False
    pago_anticipo = obtener_pago(db, venta.ID_Venta, TIPO_ANTICIPO)
    if not pago_anticipo or not (pago_anticipo.Comprobante_Url or "").strip():
        return False
    return _estado_pago(venta) not in COMPROBANTE_APROBADO
