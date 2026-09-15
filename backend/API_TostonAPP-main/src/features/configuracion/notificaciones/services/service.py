from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime

from src.shared.services.models import Notificacion, Venta, Devolucion


def _sincronizar_stock(db: Session) -> None:
    """Genera notifs para insumos/productos con stock bajo que aún no tienen una notif activa.
    Usa 3 queries en total (batch) en vez de N+1 para evitar lentitud con latencia de BD remota.
    """
    from src.shared.services.models import Insumo, Producto

    insumos   = db.query(Insumo).filter(Insumo.Estado.in_([14, 15])).all()
    productos = db.query(Producto).filter(Producto.Estado.in_([14, 15])).all()

    tipos = [
        "stock_agotado_insumo", "stock_minimo_insumo",
        "stock_agotado_producto", "stock_minimo_producto",
    ]

    # IDs que siguen con problema de stock
    insumo_ids_mal   = {i.ID_Insumo   for i in insumos}
    producto_ids_mal = {p.ID_Producto for p in productos}

    # Limpiar notificaciones (leídas o no) cuyo problema ya se resolvió
    # Si el stock vuelve a caer, se crea una nueva notificación
    todas = db.query(Notificacion).filter(Notificacion.Tipo.in_(tipos)).all()
    for n in todas:
        if n.Tipo in ("stock_agotado_insumo", "stock_minimo_insumo") and n.Referencia_ID not in insumo_ids_mal:
            db.delete(n)
        elif n.Tipo in ("stock_agotado_producto", "stock_minimo_producto") and n.Referencia_ID not in producto_ids_mal:
            db.delete(n)
    if todas:
        db.flush()

    if not insumos and not productos:
        return

    # Existentes = cualquier notif para ítems que aún tienen el problema, leída,
    # sin leer o descartada. Que esté descartada es justamente lo que evita que
    # vaciar el panel devuelva la misma alerta dos segundos después; si el stock
    # se recompone, la fila se borra arriba y una nueva caída crea una nueva.
    existentes = {
        (n.Tipo, n.Referencia_ID)
        for n in db.query(Notificacion.Tipo, Notificacion.Referencia_ID)
                   .filter(Notificacion.Tipo.in_(tipos))
                   .all()
    }

    ahora  = datetime.now()
    nuevas = []

    for ins in insumos:
        tipo = "stock_agotado_insumo" if ins.Estado == 15 else "stock_minimo_insumo"
        if (tipo, ins.ID_Insumo) not in existentes:
            titulo  = "Insumo agotado" if ins.Estado == 15 else "Stock mínimo de insumo"
            mensaje = (
                f"El insumo '{ins.Nombre}' se ha agotado"
                if ins.Estado == 15
                else f"El insumo '{ins.Nombre}' tiene stock bajo ({ins.Stock_Actual or 0} unidades)"
            )
            nuevas.append(Notificacion(
                Tipo=tipo, Titulo=titulo, Mensaje=mensaje,
                Referencia_ID=ins.ID_Insumo,
                Ruta=f"/compras/insumos/{ins.ID_Insumo}",
                Fecha=ahora, Leida=False,
            ))

    for prod in productos:
        tipo = "stock_agotado_producto" if prod.Estado == 15 else "stock_minimo_producto"
        if (tipo, prod.ID_Producto) not in existentes:
            titulo  = "Producto agotado" if prod.Estado == 15 else "Stock mínimo de producto"
            mensaje = (
                f"El producto '{prod.nombre}' se ha agotado"
                if prod.Estado == 15
                else f"El producto '{prod.nombre}' tiene stock bajo ({prod.Stock or 0} unidades)"
            )
            nuevas.append(Notificacion(
                Tipo=tipo, Titulo=titulo, Mensaje=mensaje,
                Referencia_ID=prod.ID_Producto,
                Ruta=f"/produccion/productos/{prod.ID_Producto}",
                Fecha=ahora, Leida=False,
            ))

    if nuevas:
        db.add_all(nuevas)
        db.commit()


def obtener_notificaciones(db: Session) -> dict:
    _sincronizar_stock(db)
    notificaciones = (
        db.query(Notificacion)
        .filter(Notificacion.Descartada == False)  # noqa: E712
        .order_by(Notificacion.Leida.asc(), Notificacion.Fecha.desc())
        .all()
    )
    total_no_leidas = sum(1 for n in notificaciones if not n.Leida)
    return {
        "total":           len(notificaciones),
        "total_no_leidas": total_no_leidas,
        "notificaciones":  notificaciones,
    }


def descartar(db: Session, id_notificacion: int) -> dict:
    """Saca una notificación del panel.

    Igual que al vaciar: se marca, no se borra, para que una alerta de stock
    que sigue siendo cierta no vuelva a crearse sola.
    """
    notif = db.query(Notificacion).filter(
        Notificacion.ID_Notificacion == id_notificacion
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.Descartada = True
    notif.Leida = True
    db.commit()
    return {"mensaje": "Notificación eliminada"}


def marcar_leida(db: Session, id_notificacion: int):
    notif = db.query(Notificacion).filter(
        Notificacion.ID_Notificacion == id_notificacion
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.Leida = True
    db.commit()
    db.refresh(notif)
    return notif


def eliminar_notificacion(db: Session, id_notificacion: int) -> dict:
    """Saca una notificación del panel.

    Borrarla no alcanzaba: la de stock volvía a nacer en el siguiente listado
    mientras el insumo siguiera bajo. Se descarta, que es lo mismo para quien
    mira el panel y además se recuerda.
    """
    descartar(db, id_notificacion)
    return {"mensaje": f"Notificación {id_notificacion} eliminada"}


def limpiar_leidas(db: Session) -> dict:
    """Vacía el panel de notificaciones.

    Antes borraba solo las leídas, así que todo lo que el admin no había
    abierto seguía ahí: la pantalla las escondía y al recargar volvían.

    Se marcan como descartadas en vez de borrarlas. Las de stock hay que
    recordarlas: si la fila desaparece, `_sincronizar_stock` la vuelve a crear
    en el siguiente listado mientras el insumo siga bajo, y vaciar el panel no
    serviría de nada. Marcada, no se recrea; y si el stock se recompone y
    vuelve a caer, la fila vieja se borra y nace una nueva.
    """
    descartadas = (
        db.query(Notificacion)
        .filter(Notificacion.Descartada == False)  # noqa: E712
        .update({"Descartada": True, "Leida": True}, synchronize_session=False)
    )
    db.commit()
    return {"mensaje": f"{descartadas} notificaciones eliminadas"}


def obtener_notificaciones_cocina(db: Session) -> dict:
    """Notificaciones derivadas para el cocinero: pedidos pendientes de preparación."""
    from src.shared.services.models import Venta

    ventas = (
        db.query(Venta)
        .filter(Venta.Estado.in_([4, 13]))
        .order_by(Venta.Fecha_Venta.desc())
        .limit(20)
        .all()
    )
    notifs = []
    for v in ventas:
        if v.Estado == 4:
            tipo    = "pedido_nuevo"
            titulo  = f"Pedido por preparar — #{v.ID_Venta}"
            mensaje = "Pedido confirmado en espera de producción."
        else:
            tipo    = "pedido_en_produccion"
            titulo  = f"Pedido en producción — #{v.ID_Venta}"
            mensaje = "El pedido está en curso en cocina."
        notifs.append({
            "id_ref":   f"cocina_{v.ID_Venta}_{v.Estado}",
            "tipo":     tipo,
            "titulo":   titulo,
            "mensaje":  mensaje,
            "ruta":     "/admin/cocina",
            "fecha":    v.Fecha_Venta,
            "id_venta": v.ID_Venta,
        })
    return {"total": len(notifs), "notificaciones": notifs}


def obtener_notificaciones_domiciliario(db: Session, id_usuario: int) -> dict:
    """Notificaciones derivadas para el domiciliario: sus entregas asignadas o canceladas."""
    from src.shared.services.models import Domicilio
    from datetime import datetime, timedelta

    hace_7_dias = datetime.now() - timedelta(days=7)

    domicilios = (
        db.query(Domicilio)
        .filter(
            Domicilio.ID_Empleado == id_usuario,
            Domicilio.Estado.in_([9, 10, 5]),
            Domicilio.Fecha_asignacion >= hace_7_dias,
        )
        .order_by(Domicilio.Fecha_asignacion.desc())
        .limit(20)
        .all()
    )
    notifs = []
    for dom in domicilios:
        fecha = dom.Fecha_asignacion or dom.Fecha_entrega
        if dom.Estado == 5:
            notifs.append({
                "id_ref":  f"dom_{dom.ID_Domicilio}_cancelado",
                "tipo":    "pedido_cancelado",
                "titulo":  f"Entrega cancelada — #{dom.ID_Venta}",
                "mensaje": "Esta entrega fue cancelada.",
                "ruta":    "/admin/mis-entregas",
                "fecha":   fecha,
            })
        else:
            notifs.append({
                "id_ref":  f"dom_{dom.ID_Domicilio}_asignado",
                "tipo":    "domicilio_asignado",
                "titulo":  f"Nueva entrega asignada — #{dom.ID_Venta}",
                "mensaje": "Tienes una entrega pendiente. Revisa los detalles en tus entregas.",
                "ruta":    "/admin/mis-entregas",
                "fecha":   fecha,
            })
    notifs.sort(key=lambda x: x["fecha"] or datetime.min, reverse=True)
    return {"total": len(notifs), "notificaciones": notifs}


# ── Estado de venta → (tipo_notif, titulo, mensaje) ──────────
_VENTA_NOTIF = {
    4:  ("pedido_confirmado",    "Pedido confirmado",
         "Tu pedido fue confirmado y está siendo preparado."),
    5:  ("pedido_cancelado",     "Pedido cancelado",
         "Tu pedido fue cancelado. Contáctanos si tienes dudas."),
    8:  ("pedido_entregado",     "Pedido entregado",
         "Tu pedido fue entregado exitosamente. ¡Gracias por tu compra!"),
    9:  ("pedido_en_camino",     "Pedido en camino",
         "Tu domicilio está en camino."),
    13: ("pedido_en_produccion", "Pedido en producción",
         "Tu pedido está siendo preparado en cocina."),
    16: ("fecha_propuesta",      "Fecha de entrega propuesta", None),
    20: ("esperando_pago",       "Pago pendiente",
         "Tu pedido está aprobado. Sube tu comprobante o anticipo para continuar."),
}

_DEVOLUCION_NOTIF = {
    6: ("devolucion_aprobada",  "Devolución aprobada",
        "Tu solicitud de devolución fue aprobada. El crédito fue acreditado a tu cuenta."),
    7: ("devolucion_rechazada", "Devolución rechazada",
        "Tu solicitud de devolución fue rechazada. Revisa los detalles en tu historial."),
}


def obtener_notificaciones_cliente(db: Session, id_usuario: int) -> dict:
    """Genera notificaciones derivadas para un cliente basándose en sus ventas y devoluciones."""
    notifs = []

    ventas = (
        db.query(Venta)
        .filter(Venta.ID_Usuario == id_usuario, Venta.Estado.in_([4, 5, 8, 9, 13, 16, 20]))
        .order_by(Venta.Fecha_Venta.desc())
        .limit(15)
        .all()
    )
    for v in ventas:
        if v.Estado in _VENTA_NOTIF:
            tipo, titulo, mensaje_base = _VENTA_NOTIF[v.Estado]
            fecha_entrega_iso = None
            if v.Estado == 16 and v.Fecha_entrega_esperada:
                fecha_entrega_iso = v.Fecha_entrega_esperada.isoformat()
                fecha_fmt = v.Fecha_entrega_esperada.strftime("%d/%m/%Y")
                mensaje = f"Fecha propuesta: {fecha_fmt}. Acéptala o recházala desde tus pedidos."
            else:
                mensaje = mensaje_base or ""
            # Para estado 16 (fecha propuesta) el id_ref incluye la fecha para
            # que cada propuesta distinta genere una notificación nueva, aunque
            # el estado siga siendo 16 (re-propuesta tras rechazo del cliente).
            fecha_key = (
                f"_{v.Fecha_entrega_esperada.date().isoformat()}"
                if v.Estado == 16 and v.Fecha_entrega_esperada else ""
            )
            notifs.append({
                "id_ref":         f"venta_{v.ID_Venta}_{v.Estado}{fecha_key}",
                "tipo":           tipo,
                "titulo":         f"{titulo} — Pedido #{v.ID_Venta}",
                "mensaje":        mensaje,
                "id_venta":       v.ID_Venta,
                "fecha_entrega":  fecha_entrega_iso,
                "ruta":           "/cliente/pedidos",
                "fecha":          v.Fecha_Venta,
            })

    # Pedidos con comprobante rechazado (activos, no cancelados ni entregados)
    ventas_rechazadas = (
        db.query(Venta)
        .filter(
            Venta.ID_Usuario == id_usuario,
            Venta.Estado_Pago == "comprobante_rechazado",
            Venta.Estado.notin_([5, 8, 12]),
        )
        .order_by(Venta.Fecha_Venta.desc())
        .limit(5)
        .all()
    )
    for v in ventas_rechazadas:
        motivo = getattr(v, "Motivo_Rechazo_Comprobante", None) or ""
        mensaje = (
            f"Motivo: {motivo}"
            if motivo
            else "Sube un nuevo comprobante para continuar con tu pedido."
        )
        notifs.append({
            "id_ref":   f"venta_{v.ID_Venta}_comprobante_rechazado",
            "tipo":     "comprobante_rechazado",
            "titulo":   f"Comprobante rechazado — Pedido #{v.ID_Venta}",
            "mensaje":  mensaje,
            "id_venta": v.ID_Venta,
            "ruta":     "/cliente/pedidos",
            "fecha":    v.Fecha_Venta,
        })

    devs = (
        db.query(Devolucion)
        .filter(Devolucion.ID_Usuario == id_usuario, Devolucion.Estado.in_([6, 7]))
        .order_by(Devolucion.FechaAprobacion.desc())
        .limit(5)
        .all()
    )
    for d in devs:
        if d.Estado in _DEVOLUCION_NOTIF:
            tipo, titulo, mensaje = _DEVOLUCION_NOTIF[d.Estado]
            notifs.append({
                "id_ref":  f"dev_{d.ID_Devolucion}_{d.Estado}",
                "tipo":    tipo,
                "titulo":  titulo,
                "mensaje": mensaje,
                "ruta":    "/cliente/devoluciones",
                "fecha":   d.FechaAprobacion or d.FechaDevolucion,
            })

    notifs.sort(key=lambda x: x["fecha"] or datetime.min, reverse=True)
    return {"total": len(notifs), "notificaciones": notifs}
