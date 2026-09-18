from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from src.shared.services.models import (
    Devolucion, DevolucionDetalle, DetalleVenta, Venta, VentaXProducto, Usuario,
    Producto, CreditoCliente, MovimientoCredito, Domicilio
)
from src.shared.services.notificaciones_utils import notificar, descartar_notificacion
from .schemas import DevolucionCreate, DevolucionResolucion, DevolucionUpdate

_BOGOTA = ZoneInfo("America/Bogota")


def _now():
    """Hora actual en Colombia (naive), consistente con los timestamps de entrega."""
    return datetime.now(_BOGOTA).replace(tzinfo=None)


# Estados globales (tabla Estados)
ESTADO_PENDIENTE = 3
ESTADO_APROBADA  = 6
ESTADO_RECHAZADA = 7

_ESTADO_LABELS = {
    ESTADO_PENDIENTE: "Pendiente",
    ESTADO_APROBADA:  "Reembolsada",
    ESTADO_RECHAZADA: "Rechazada",
}

# Estado de venta que permite devolución
VENTA_ENTREGADA = 8

# Plazo máximo para solicitar devolución: 48 horas desde la entrega.
# El mismo número que muestran la app y la web (kHorasLimiteDevolucion).
HORAS_LIMITE_DEVOLUCION = 48


def plazo_vencido(fecha_ref, ahora=None):
    """¿Se le pasó el plazo a este pedido? Devuelve (vencido, horas).

    Sin fecha confiable no se vence nada: se prefiere aceptar la solicitud y
    que la revise una persona, antes que rechazar una devolución legítima
    porque a un pedido viejo le falta el timestamp de entrega.
    """
    if not fecha_ref:
        return False, 0
    transcurrido = (ahora or _now()) - fecha_ref
    horas = int(transcurrido.total_seconds() // 3600)
    return transcurrido > timedelta(hours=HORAS_LIMITE_DEVOLUCION), horas


def _formato_devolucion(dev: Devolucion, db: Session) -> dict:
    usuario  = db.query(Usuario).filter(Usuario.ID_Usuario == dev.ID_Usuario).first()
    detalles = db.query(DevolucionDetalle).filter(
        DevolucionDetalle.ID_Devolucion == dev.ID_Devolucion
    ).all()
    prod_ids = [d.ID_Producto for d in detalles if d.ID_Producto]
    prods    = {p.ID_Producto: p for p in db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()} if prod_ids else {}
    productos = [
        {
            "ID_Devolucion_Detalle": d.ID_Devolucion_Detalle,
            "ID_Producto":           d.ID_Producto,
            "nombre_producto":       prods[d.ID_Producto].nombre if d.ID_Producto in prods else None,
            "Cantidad":              d.Cantidad,
            "PrecioUnitario":        d.PrecioUnitario,
            "Subtotal":              d.Subtotal,
        }
        for d in detalles
    ]
    return {
        "ID_Devolucion":   dev.ID_Devolucion,
        "ID_Venta":        dev.ID_Venta,
        "ID_Usuario":      dev.ID_Usuario,
        "nombre_cliente":  f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
        "ID_DetalleVenta": dev.ID_DetalleVenta,
        "FechaDevolucion": dev.FechaDevolucion,
        "Motivo":          dev.Motivo,
        "Estado":          dev.Estado,
        "estado_label":    _ESTADO_LABELS.get(dev.Estado, "Desconocido"),
        "TotalDevuelto":   dev.TotalDevuelto,
        "FechaAprobacion": dev.FechaAprobacion,
        "FechaReembolso":  dev.FechaReembolso,
        "UsuarioAprueba":  dev.UsuarioAprueba,
        "Comentario":      dev.Comentario,
        "Comprobante_Imagen": dev.Comprobante_Imagen,
        "productos":       productos,
    }


def _batch_devoluciones(devoluciones: list, db: Session) -> list:
    if not devoluciones:
        return []
    dev_ids     = [d.ID_Devolucion for d in devoluciones]
    usuario_ids = list({d.ID_Usuario for d in devoluciones if d.ID_Usuario})

    usuarios_map = {u.ID_Usuario: u for u in db.query(Usuario).filter(Usuario.ID_Usuario.in_(usuario_ids)).all()} if usuario_ids else {}

    detalles_all = db.query(DevolucionDetalle).filter(DevolucionDetalle.ID_Devolucion.in_(dev_ids)).all()
    detalles_by_dev: dict = {}
    for d in detalles_all:
        detalles_by_dev.setdefault(d.ID_Devolucion, []).append(d)

    prod_ids = list({d.ID_Producto for d in detalles_all if d.ID_Producto})
    productos_map = {p.ID_Producto: p for p in db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()} if prod_ids else {}

    def _build(dev: Devolucion) -> dict:
        usuario  = usuarios_map.get(dev.ID_Usuario)
        detalles = detalles_by_dev.get(dev.ID_Devolucion, [])
        return {
            "ID_Devolucion":   dev.ID_Devolucion,
            "ID_Venta":        dev.ID_Venta,
            "ID_Usuario":      dev.ID_Usuario,
            "nombre_cliente":  f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
            "ID_DetalleVenta": dev.ID_DetalleVenta,
            "FechaDevolucion": dev.FechaDevolucion,
            "Motivo":          dev.Motivo,
            "Estado":          dev.Estado,
            "estado_label":    _ESTADO_LABELS.get(dev.Estado, "Desconocido"),
            "TotalDevuelto":   dev.TotalDevuelto,
            "FechaAprobacion": dev.FechaAprobacion,
            "FechaReembolso":  dev.FechaReembolso,
            "UsuarioAprueba":  dev.UsuarioAprueba,
            "Comentario":      dev.Comentario,
            "Comprobante_Imagen": dev.Comprobante_Imagen,
            "productos": [
                {
                    "ID_Devolucion_Detalle": d.ID_Devolucion_Detalle,
                    "ID_Producto":           d.ID_Producto,
                    "nombre_producto":       productos_map[d.ID_Producto].nombre if d.ID_Producto in productos_map else None,
                    "Cantidad":              d.Cantidad,
                    "PrecioUnitario":        d.PrecioUnitario,
                    "Subtotal":              d.Subtotal,
                }
                for d in detalles
            ],
        }

    return [_build(d) for d in devoluciones]


def _recargar_credito(db: Session, id_usuario: int, monto: Decimal, id_devolucion: int):
    """Recarga crédito al cliente cuando se aprueba la devolución."""
    credito = db.query(CreditoCliente).filter(
        CreditoCliente.ID_Usuario == id_usuario
    ).first()

    if not credito:
        credito = CreditoCliente(
            ID_Usuario   = id_usuario,
            Saldo        = Decimal("0"),
            Fecha_Update = _now(),
        )
        db.add(credito)
        db.flush()

    credito.Saldo        += monto
    credito.Fecha_Update  = _now()

    db.add(MovimientoCredito(
        ID_Credito    = credito.ID_Credito,
        ID_Devolucion = id_devolucion,
        ID_Venta      = None,
        Tipo          = "recarga",
        Monto         = monto,
        Fecha         = _now(),
    ))


def obtener_mis_devoluciones(
    db: Session,
    id_usuario: int,
    pagina: int = 1,
    por_pagina: int = 20,
) -> dict:
    """Retorna las devoluciones del cliente autenticado, más recientes primero."""
    query = (
        db.query(Devolucion)
        .filter(Devolucion.ID_Usuario == id_usuario)
        .order_by(Devolucion.FechaDevolucion.desc())
    )
    total        = query.count()
    offset       = (pagina - 1) * por_pagina
    devoluciones = query.offset(offset).limit(por_pagina).all()
    return {
        "total":        total,
        "pagina":       pagina,
        "por_pagina":   por_pagina,
        "devoluciones": _batch_devoluciones(devoluciones, db),
    }


def obtener_devoluciones(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 20,
    busqueda: str = None,
    estado: int = None,
    fecha_desde: str = None,
    fecha_hasta: str = None,
) -> dict:
    """Lista paginada para admin, más recientes primero. Filtra por nombre, estado y fechas."""
    query = db.query(Devolucion)

    if estado:
        query = query.filter(Devolucion.Estado == estado)

    if busqueda:
        termino      = f"%{busqueda}%"
        usuarios_ids = (
            db.query(Usuario.ID_Usuario)
            .filter(
                Usuario.Nombre.ilike(termino) |
                Usuario.Apellidos.ilike(termino)
            )
            .subquery()
        )
        query = query.filter(Devolucion.ID_Usuario.in_(usuarios_ids))

    if fecha_desde:
        try:
            desde = datetime.strptime(fecha_desde, "%Y-%m-%d")
            query = query.filter(Devolucion.FechaDevolucion >= desde)
        except ValueError:
            pass

    if fecha_hasta:
        try:
            hasta = datetime.strptime(fecha_hasta, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Devolucion.FechaDevolucion < hasta)
        except ValueError:
            pass

    query        = query.order_by(Devolucion.FechaDevolucion.desc())
    total        = query.count()
    offset       = (pagina - 1) * por_pagina
    devoluciones = query.offset(offset).limit(por_pagina).all()

    totales_por_estado = {
        label: db.query(Devolucion).filter(Devolucion.Estado == eid).count()
        for eid, label in _ESTADO_LABELS.items()
    }
    totales_por_estado["todos"] = sum(totales_por_estado.values())

    return {
        "total":              total,
        "pagina":             pagina,
        "por_pagina":         por_pagina,
        "devoluciones":       _batch_devoluciones(devoluciones, db),
        "totales_por_estado": totales_por_estado,
    }


def obtener_devolucion(db: Session, id_devolucion: int) -> dict:
    dev = db.query(Devolucion).filter(
        Devolucion.ID_Devolucion == id_devolucion
    ).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    return _formato_devolucion(dev, db)


def _precios_del_catalogo(db: Session, prod_ids: list[int]) -> dict:
    """Precio de venta real de cada producto, leído de la base.

    Lo que el cliente devuelve vale lo que vale en la panadería, no lo que
    diga el cuerpo de la petición.
    """
    if not prod_ids:
        return {}
    return {
        p.ID_Producto: Decimal(str(p.Precio_venta or 0))
        for p in db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()
    }


def _recortar_al_valor_de_la_venta(db: Session, id_venta: int, total: Decimal) -> Decimal:
    """Nunca se devuelve más de lo que se facturó en esa venta.

    El precio del catálogo es el de hoy; el pedido pudo comprarse con otro.
    Este tope evita que una subida de precios convierta una devolución en
    una ganancia.
    """
    detalle = db.query(DetalleVenta).filter(
        DetalleVenta.ID_Venta == id_venta
    ).first()
    facturado = Decimal(str(getattr(detalle, "SubTotal", None) or 0))
    if facturado <= 0:
        return total
    return min(total, facturado)


def crear_devolucion(db: Session, datos: DevolucionCreate) -> dict:
    """
    Crea una solicitud de devolución con las siguientes validaciones:
    1. La venta debe estar en estado Entregado (4).
    2. No debe existir ya una devolución Pendiente o Aprobada para la misma venta.
    3. Los productos a devolver deben pertenecer a la venta.
    4. La cantidad a devolver no puede superar la cantidad comprada.
    5. Se debe devolver al menos un producto.
    """
    # 1. Venta existe y está entregada
    venta = db.query(Venta).filter(Venta.ID_Venta == datos.ID_Venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    if venta.Estado != VENTA_ENTREGADA:
        raise HTTPException(
            status_code=400,
            detail="Solo puedes solicitar una devolución para pedidos ya entregados"
        )

    # 1b. Verificar plazo de devolución: 48 horas desde la entrega real.
    # Fuente del timestamp (en orden): domicilio entregado → venta.Fecha_entrega
    # → fallback a Fecha_pedido/Fecha_Venta para pedidos antiguos sin timestamp.
    domicilio = db.query(Domicilio).filter(
        Domicilio.ID_Venta == datos.ID_Venta,
        Domicilio.Estado.in_([8, 4])  # 8=Entregado web, 4=Entregado Flutter
    ).first()
    fecha_ref = (
        (domicilio.Fecha_entrega if domicilio and domicilio.Fecha_entrega else None)
        or getattr(venta, "Fecha_entrega", None)
        or venta.Fecha_pedido
        or venta.Fecha_Venta
    )
    vencido, horas = plazo_vencido(fecha_ref)
    if vencido:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El plazo para solicitar una devolución ha vencido. Las devoluciones "
                f"pueden solicitarse hasta {HORAS_LIMITE_DEVOLUCION} horas después de la "
                f"entrega (han pasado {horas} horas)."
            )
        )

    # 2. Bloquear solo si ya hay una devolución Pendiente para esta venta.
    #    Una aprobada no bloquea: permite devoluciones parciales en tandas.
    #    Una rechazada tampoco: el cliente puede reintentar dentro del plazo.
    pendiente = db.query(Devolucion).filter(
        Devolucion.ID_Venta == datos.ID_Venta,
        Devolucion.Estado == ESTADO_PENDIENTE,
    ).first()
    if pendiente:
        raise HTTPException(
            status_code=400,
            detail="Ya tienes una solicitud de devolución pendiente para este pedido. Espera a que sea revisada antes de enviar otra.",
        )

    # 3. Cliente existe
    if not db.query(Usuario).filter(Usuario.ID_Usuario == datos.ID_Usuario).first():
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # 4. Validar productos: deben estar en la venta y la cantidad no debe superarse
    if not datos.productos:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos un producto")

    for p in datos.productos:
        vxp = db.query(VentaXProducto).filter(
            VentaXProducto.ID_Venta    == datos.ID_Venta,
            VentaXProducto.ID_Producto == p.ID_Producto
        ).first()
        if not vxp:
            producto = db.query(Producto).filter(
                Producto.ID_Producto == p.ID_Producto
            ).first()
            nombre = producto.nombre if producto else str(p.ID_Producto)
            raise HTTPException(
                status_code=400,
                detail=f"El producto '{nombre}' no pertenece a este pedido"
            )

        # Cantidad ya comprometida en devoluciones Pendientes + Aprobadas para
        # este producto en esta venta. Las Rechazadas no cuentan: el cliente
        # puede reintentar esas unidades.
        ya_devuelto = int(
            db.query(func.coalesce(func.sum(DevolucionDetalle.Cantidad), 0))
            .join(Devolucion, DevolucionDetalle.ID_Devolucion == Devolucion.ID_Devolucion)
            .filter(
                Devolucion.ID_Venta      == datos.ID_Venta,
                Devolucion.Estado.in_([ESTADO_PENDIENTE, ESTADO_APROBADA]),
                DevolucionDetalle.ID_Producto == p.ID_Producto,
            )
            .scalar() or 0
        )
        restante = vxp.Cantidad - ya_devuelto
        if p.Cantidad > restante:
            producto = db.query(Producto).filter(
                Producto.ID_Producto == p.ID_Producto
            ).first()
            nombre = producto.nombre if producto else str(p.ID_Producto)
            if restante <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ya se devolvió la totalidad de '{nombre}' en este pedido"
                )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Solo puedes devolver hasta {restante} unidad{'es' if restante != 1 else ''} "
                    f"de '{nombre}' (ya se solicitó la devolución de {ya_devuelto})"
                )
            )

    # 5. Calcular total con el precio del CATÁLOGO, no con el del request.
    #
    # `PrecioUnitario` viene en el cuerpo que manda la pantalla y terminaba
    # tal cual en `TotalDevuelto`, que al aprobarse se abona como saldo a
    # favor: un pedido de $20.000 podía pedir la devolución de un millón y
    # el administrador solo veía una cifra que parecía legítima.
    #
    # La venta no guarda el precio unitario de cada línea, así que la mejor
    # fuente disponible es el precio actual del producto. Para que un cambio
    # de precio posterior tampoco devuelva de más, el total se recorta a lo
    # que se facturó en esa venta.
    precios = _precios_del_catalogo(db, [p.ID_Producto for p in datos.productos])
    lineas = [
        (p, precios.get(p.ID_Producto, Decimal("0")) * Decimal(str(p.Cantidad)))
        for p in datos.productos
    ]
    total = _recortar_al_valor_de_la_venta(
        db, datos.ID_Venta, sum((sub for _, sub in lineas), Decimal("0")),
    )

    nueva = Devolucion(
        ID_Venta           = datos.ID_Venta,
        ID_Usuario         = datos.ID_Usuario,
        ID_DetalleVenta    = datos.ID_DetalleVenta,
        Motivo             = datos.Motivo,
        Comentario         = datos.Comentario,
        Comprobante_Imagen = datos.Comprobante_Imagen,
        Estado             = ESTADO_PENDIENTE,
        TotalDevuelto      = total,
        FechaDevolucion    = _now(),
    )
    db.add(nueva)
    db.flush()

    for p, subtotal in lineas:
        db.add(DevolucionDetalle(
            ID_Devolucion  = nueva.ID_Devolucion,
            ID_Producto    = p.ID_Producto,
            Cantidad       = p.Cantidad,
            PrecioUnitario = precios.get(p.ID_Producto, Decimal("0")),
            Subtotal       = subtotal,
        ))

    notificar(
        db, "devolucion_pendiente", "Devolución pendiente",
        f"La devolución #{nueva.ID_Devolucion} requiere revisión",
        nueva.ID_Devolucion, f"/ventas/devoluciones/{nueva.ID_Devolucion}",
    )
    db.commit()
    db.refresh(nueva)
    return _formato_devolucion(nueva, db)


def editar_devolucion(db: Session, id_devolucion: int, datos: DevolucionUpdate) -> dict:
    """
    Permite al admin editar el motivo o agregar un comentario interno
    mientras la devolución esté Pendiente.
    """
    dev = db.query(Devolucion).filter(
        Devolucion.ID_Devolucion == id_devolucion
    ).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")

    if dev.Estado != ESTADO_PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden editar devoluciones en estado Pendiente"
        )

    if datos.Motivo is not None:
        datos_motivo = datos.Motivo.strip()
        if not datos_motivo:
            raise HTTPException(status_code=400, detail="El motivo no puede estar vacío")
        dev.Motivo = datos_motivo

    if datos.Comentario is not None:
        dev.Comentario = datos.Comentario.strip() or None

    db.commit()
    db.refresh(dev)
    return _formato_devolucion(dev, db)


def resolver_devolucion(db: Session, id_devolucion: int, datos: DevolucionResolucion) -> dict:
    """
    Aprueba (Estado=2) o rechaza (Estado=3) una devolución pendiente.
    Al aprobar, recarga automáticamente el crédito del cliente.
    """
    if datos.Estado not in {ESTADO_APROBADA, ESTADO_RECHAZADA}:
        raise HTTPException(
            status_code=400,
            detail="Estado inválido. Use 6 (Aprobada) o 7 (Rechazada)"
        )

    dev = db.query(Devolucion).filter(
        Devolucion.ID_Devolucion == id_devolucion
    ).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")

    if dev.Estado != ESTADO_PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail="Esta devolución ya fue resuelta"
        )

    dev.Estado          = datos.Estado
    dev.Comentario      = datos.Comentario
    dev.UsuarioAprueba  = datos.UsuarioAprueba
    dev.FechaAprobacion = _now()

    if datos.Estado == ESTADO_APROBADA:
        _recargar_credito(
            db            = db,
            id_usuario    = dev.ID_Usuario,
            monto         = Decimal(str(dev.TotalDevuelto)),
            id_devolucion = dev.ID_Devolucion,
        )
        dev.FechaReembolso = _now()

    descartar_notificacion(db, "devolucion_pendiente", id_devolucion)
    db.commit()
    db.refresh(dev)
    return _formato_devolucion(dev, db)
