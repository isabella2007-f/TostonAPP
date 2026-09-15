from enum import IntEnum
from fastapi import HTTPException


class EstadoPedido(IntEnum):
    PENDIENTE              = 1   # nuevo pedido del cliente
    CONFIRMADO             = 4   # aceptado por el admin/empleado
    CANCELADO              = 5   # cancelado (estado final)
    ENTREGADO              = 8   # entregado al cliente o recogido en tienda
    EN_CAMINO              = 9   # domicilio en tránsito
    LISTO                  = 11  # terminado, esperando entrega o recogida ("Completada" en la BD)
    PREPARANDO             = 13  # en cocina / producción  ("En proceso" en la BD)
    FECHA_PROPUESTA        = 16  # admin propuso fecha; cliente debe aceptar o rechazar
    FECHA_RECHAZADA        = 17  # cliente rechazó la fecha; admin propone de nuevo
    PARCIALMENTE_ENTREGADO = 18  # grupo A entregado, grupo B de producción pendiente
    ESCALADO_A_ADMIN       = 19  # cliente pidió hablar directamente con el admin (canal de excepción)
    ESPERANDO_PAGO         = 20  # fecha aprobada (o sin producción): esperando comprobante/anticipo
    # prompt-pedidos-2, 3.4: contraoferta final del cliente (fecha propia +
    # motivo obligatorio) tras rechazar la del admin. Congela el pedido —no se
    # puede editar más— hasta que el admin la acepte o la rechace en definitiva.
    FECHA_PROPUESTA_FINAL  = 21
    # prompt-pedidos-2, 3.7: cobro en efectivo fallido (en tienda, o tras un
    # domicilio que no se pudo entregar y ya volvió a la tienda). El stock
    # sigue reservado; desde acá se reintenta, se cambia a domicilio o se
    # cancela (definitivo si pasaron 48h).
    RETENIDO_EN_TIENDA     = 22
    # prompt-pedidos-2, 3.7: el domiciliario no pudo cobrar/entregar y va de
    # vuelta a la tienda. Al confirmar el regreso físico pasa a RETENIDO_EN_TIENDA.
    EN_RUTA_RETORNO        = 23


ESTADOS_FINALES = frozenset({EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO})

# Todos los estados no finales (pedido aún procesable)
ESTADOS_ACTIVOS = frozenset({
    EstadoPedido.PENDIENTE,
    EstadoPedido.CONFIRMADO,
    EstadoPedido.PREPARANDO,
    EstadoPedido.LISTO,
    EstadoPedido.EN_CAMINO,
    EstadoPedido.FECHA_PROPUESTA,
    EstadoPedido.FECHA_RECHAZADA,
    EstadoPedido.PARCIALMENTE_ENTREGADO,
    EstadoPedido.ESCALADO_A_ADMIN,
    EstadoPedido.ESPERANDO_PAGO,
    EstadoPedido.FECHA_PROPUESTA_FINAL,
    EstadoPedido.RETENIDO_EN_TIENDA,
    EstadoPedido.EN_RUTA_RETORNO,
})

TRANSICIONES: dict[int, frozenset[int]] = {
    # Pendiente = "Pendiente de Aprobación" cuando necesita producción. El admin
    # aprueba directo (→ Confirmado/Esperando Pago, decide el service) o
    # contraoferta (→ Fecha propuesta). Un rechazo-con-causa/edición reabre
    # aquí mismo (Pendiente → Pendiente, no es una transición nueva).
    EstadoPedido.PENDIENTE:       frozenset({EstadoPedido.CONFIRMADO, EstadoPedido.ESPERANDO_PAGO, EstadoPedido.FECHA_PROPUESTA, EstadoPedido.CANCELADO}),
    # confirmado → listo (saltar preparando) es válido si el pedido ya está listo de inmediato
    EstadoPedido.CONFIRMADO:      frozenset({EstadoPedido.PREPARANDO, EstadoPedido.LISTO, EstadoPedido.CANCELADO}),
    EstadoPedido.PREPARANDO:      frozenset({EstadoPedido.LISTO, EstadoPedido.CANCELADO}),
    # RETENIDO_EN_TIENDA (3.7): el cajero no pudo cobrar en efectivo.
    EstadoPedido.LISTO:           frozenset({EstadoPedido.EN_CAMINO, EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO, EstadoPedido.RETENIDO_EN_TIENDA}),
    # EN_RUTA_RETORNO (3.7): el domiciliario no pudo cobrar/entregar y vuelve.
    EstadoPedido.EN_CAMINO:       frozenset({EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO, EstadoPedido.EN_RUTA_RETORNO}),
    EstadoPedido.ENTREGADO:       frozenset(),
    EstadoPedido.CANCELADO:       frozenset(),
    # Fecha propuesta (contraoferta del admin): el cliente acepta (→ Confirmado/
    # Esperando Pago), hace su propia contraoferta final con motivo obligatorio
    # (→ Fecha propuesta final, 3.4), pide hablar con el admin (→ Escalado a
    # admin) o cancela. Ya no vuelve a Pendiente: esa vía la reemplaza la
    # propuesta final (antes era el único destino de `rechazar_fecha`).
    EstadoPedido.FECHA_PROPUESTA: frozenset({EstadoPedido.CONFIRMADO, EstadoPedido.ESPERANDO_PAGO, EstadoPedido.FECHA_PROPUESTA_FINAL, EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.CANCELADO}),
    # Propuesta final del cliente (3.4): el admin la acepta (sigue el flujo
    # normal) o la rechaza en definitiva (→ Escalado a admin, ofreciendo
    # cancelar o hablar con el admin — 3.4.1). El pedido queda congelado acá:
    # no admite otra edición ni otra contraoferta del cliente.
    EstadoPedido.FECHA_PROPUESTA_FINAL: frozenset({EstadoPedido.CONFIRMADO, EstadoPedido.ESPERANDO_PAGO, EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.CANCELADO}),
    # Ya no se llega aquí desde el flujo nuevo (queda por compatibilidad histórica).
    EstadoPedido.FECHA_RECHAZADA: frozenset({EstadoPedido.FECHA_PROPUESTA, EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.CANCELADO}),
    # Escalado (canal de excepción): admin acuerda manualmente (→ Confirmado/
    # Esperando Pago) o cancela.
    EstadoPedido.ESCALADO_A_ADMIN: frozenset({EstadoPedido.CONFIRMADO, EstadoPedido.ESPERANDO_PAGO, EstadoPedido.CANCELADO}),
    # Parcialmente entregado: cuando llega el grupo B queda Entregado
    EstadoPedido.PARCIALMENTE_ENTREGADO: frozenset({EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO}),
    # Esperando pago: al aprobarse el comprobante/anticipo, sigue el flujo de
    # producción/despacho normal; si se rechaza el comprobante se queda aquí.
    EstadoPedido.ESPERANDO_PAGO:  frozenset({EstadoPedido.CONFIRMADO, EstadoPedido.PREPARANDO, EstadoPedido.LISTO, EstadoPedido.CANCELADO}),
    # Retenido en tienda (3.7): reintentar cobro (→ Entregado, ya cobrado),
    # cambiar a domicilio (→ Listo, con domicilio recién asignado) o cancelar
    # en definitivo.
    EstadoPedido.RETENIDO_EN_TIENDA: frozenset({EstadoPedido.ENTREGADO, EstadoPedido.LISTO, EstadoPedido.CANCELADO}),
    # En ruta de retorno (3.7): al confirmar que el domiciliario ya volvió
    # físicamente a la tienda, pasa a Retenido en tienda (mismas 3 acciones).
    EstadoPedido.EN_RUTA_RETORNO: frozenset({EstadoPedido.RETENIDO_EN_TIENDA}),
}


def validar_transicion(actual: int, nuevo: int, tiene_domicilio: bool) -> None:
    """
    Lanza HTTPException 400 si la transición no está permitida.
    También valida reglas dependientes del tipo de pedido (domicilio vs recoger).
    """
    try:
        e_actual = EstadoPedido(actual)
    except ValueError:
        raise HTTPException(400, detail=f"Estado actual desconocido: {actual}")

    try:
        e_nuevo = EstadoPedido(nuevo)
    except ValueError:
        raise HTTPException(400, detail=f"Estado destino inválido: {nuevo}")

    permitidos = TRANSICIONES.get(e_actual, frozenset())
    if e_nuevo not in permitidos:
        raise HTTPException(
            400,
            detail=(
                f"No se puede pasar de '{e_actual.name.lower()}' "
                f"a '{e_nuevo.name.lower()}'"
            ),
        )

    # Reglas dependientes del tipo de pedido, solo desde LISTO
    if e_actual == EstadoPedido.LISTO:
        if e_nuevo == EstadoPedido.EN_CAMINO and not tiene_domicilio:
            raise HTTPException(
                400,
                detail="Solo pedidos con domicilio pueden pasar a 'en_camino'",
            )
        if e_nuevo == EstadoPedido.ENTREGADO and tiene_domicilio:
            raise HTTPException(
                400,
                detail="Un pedido con domicilio debe pasar por 'en_camino' antes de entregarse",
            )
        if e_nuevo == EstadoPedido.RETENIDO_EN_TIENDA and tiene_domicilio:
            raise HTTPException(
                400,
                detail="Solo pedidos de recogida en tienda pueden quedar retenidos",
            )
