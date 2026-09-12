from decimal import Decimal
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException

from src.shared.services.models import (
    Venta, Estado, DetalleVenta, Domicilio,
    VentaXProducto, Producto, DescuentoXVenta,
    GrupoEnvio, GrupoEnvioItem, Barrio,
)
from src.features.ventas.gestion_ventas.services.service import (
    _formato_venta, _now, cambiar_estado as _gv_cambiar_estado,
    _abonar_credito, _avanzar_tras_pago_aprobado, _validar_fecha_entrega_esperada,
)
from src.features.ventas.ubicaciones.services.service import resolver_domicilio
from src.features.ventas.domicilios.services.estados import EstadoDomicilio
from src.features.ventas.pedidos.services.estados import EstadoPedido, ESTADOS_ACTIVOS


def obtener_pedidos(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None,
    estado: int = None,
) -> dict:
    """
    Lista ventas. Sin 'estado' devuelve solo los activos; con 'estado' filtra por ese valor exacto.
    """
    from src.shared.services.models import Usuario

    if estado is not None:
        query = db.query(Venta).filter(Venta.Estado == estado)
    else:
        query = db.query(Venta).filter(Venta.Estado.in_(ESTADOS_ACTIVOS))

    if busqueda:
        from sqlalchemy import cast, String as SAString
        termino      = f"%{busqueda}%"
        usuarios_ids = (
            db.query(Usuario.ID_Usuario)
            .filter(
                Usuario.Nombre.ilike(termino) |
                Usuario.Apellidos.ilike(termino)
            )
            .subquery()
        )
        query = query.filter(
            Venta.ID_Usuario.in_(usuarios_ids) |
            Venta.Metodo_Pago.ilike(termino) |
            cast(Venta.ID_Venta, SAString).ilike(termino)
        )

    total   = query.count()
    offset  = (pagina - 1) * por_pagina
    pedidos = (
        query
        .options(
            selectinload(Venta.usuario),
            selectinload(Venta.productos)
                .selectinload(VentaXProducto.producto)
                .selectinload(Producto.imagenes),
            selectinload(Venta.detalle),
            selectinload(Venta.domicilios)
                .selectinload(Domicilio.empleado),
            selectinload(Venta.domicilios)
                .selectinload(Domicilio.barrio),
            selectinload(Venta.ordenes_produccion),
            selectinload(Venta.grupos_envio)
                .selectinload(GrupoEnvio.items),
        )
        .order_by(Venta.Fecha_pedido.desc())
        .offset(offset)
        .limit(por_pagina)
        .all()
    )

    venta_ids = [p.ID_Venta for p in pedidos]
    dxv_map = {}
    if venta_ids:
        for row in db.query(DescuentoXVenta).filter(
            DescuentoXVenta.ID_Venta.in_(venta_ids)
        ).all():
            dxv_map.setdefault(row.ID_Venta, row)

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "pedidos":    [_formato_venta(p, db, dxv_map=dxv_map) for p in pedidos],
    }


def obtener_pedido(db: Session, id_venta: int) -> dict:
    """Retorna un pedido por ID — sin filtro de estado para que admins puedan ver históricos."""
    pedido = (
        db.query(Venta)
        .options(
            selectinload(Venta.usuario),
            selectinload(Venta.productos)
                .selectinload(VentaXProducto.producto)
                .selectinload(Producto.imagenes),
            selectinload(Venta.detalle),
            selectinload(Venta.domicilios)
                .selectinload(Domicilio.empleado),
            selectinload(Venta.domicilios)
                .selectinload(Domicilio.barrio),
            selectinload(Venta.ordenes_produccion),
            selectinload(Venta.grupos_envio)
                .selectinload(GrupoEnvio.items),
        )
        .filter(Venta.ID_Venta == id_venta)
        .first()
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return _formato_venta(pedido, db)


def editar_pedido(db: Session, id_venta: int, datos: dict) -> dict:
    """
    Actualiza los campos editables de un pedido Pendiente:
    Metodo_Pago, montos, domicilio y su dirección.
    El cambio de estado se maneja por los endpoints /confirmar y /cancelar.
    """
    pedido = db.query(Venta).filter(
        Venta.ID_Venta == id_venta,
        Venta.Estado.in_(ESTADOS_ACTIVOS),
    ).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado o ya fue procesado")

    if datos.get("Metodo_Pago"):
        pedido.Metodo_Pago = datos["Metodo_Pago"].split(" ")[0].strip()

    if datos.get("Comprobante_Pago") is not None:
        pedido.Comprobante_Pago = datos["Comprobante_Pago"]
        # Si cambia a Transferencia con comprobante y el pago no está ya confirmado,
        # marcar como pendiente de validación para que el admin lo apruebe.
        _metodo_actual = (pedido.Metodo_Pago or datos.get("Metodo_Pago") or "").strip().lower()
        _estado_pago_no_final = (getattr(pedido, "Estado_Pago", None) or "pendiente") not in (
            "pagado_completo", "efectivo_recibido", "anticipo_pagado",
        )
        if "transfer" in _metodo_actual and datos["Comprobante_Pago"] and _estado_pago_no_final:
            pedido.Estado_Pago = "pendiente_validacion"

    if datos.get("Total") is not None:
        pedido.Total = datos["Total"]

    detalle = db.query(DetalleVenta).filter(DetalleVenta.ID_Venta == id_venta).first()
    if detalle:
        if datos.get("Descuento") is not None:
            detalle.Descuento = datos["Descuento"]
        if datos.get("Subtotal") is not None:
            detalle.SubTotal = datos["Subtotal"]

    # Registrar anticipo (cuando el admin confirma que ya recibió el 50%)
    if datos.get("Anticipo_Registrado"):
        pedido.Anticipo_Registrado = 1
        if datos.get("Anticipo_Monto") is not None:
            pedido.Anticipo_Monto = datos["Anticipo_Monto"]
        if datos.get("Anticipo_Metodo_Pago"):
            pedido.Anticipo_Metodo_Pago = datos["Anticipo_Metodo_Pago"]
        if datos.get("Anticipo_Comprobante_Url"):
            pedido.Anticipo_Comprobante_Url = datos["Anticipo_Comprobante_Url"]
        _ep = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
        if _ep not in ("pagado_completo", "efectivo_recibido"):
            pedido.Estado_Pago = "anticipo_pagado"

    quiere_domicilio = datos.get("Domicilio")
    domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first()
    tenia_domicilio = domicilio is not None
    # Precio del domicilio hoy congelado en el pedido (0 si no tenía).
    precio_anterior = int(domicilio.Precio_Domicilio_Final or 0) if domicilio else 0
    precio_nuevo = precio_anterior

    if quiere_domicilio is True:
        if domicilio is None:
            # El domicilio nace igual que el que crea el checkout: en el
            # estado PENDIENTE de la tabla global (3). Acá se usaba
            # EstadoPedido.PENDIENTE, que vale 1 y no es un estado válido de
            # domicilio: el panel lo mostraba sin etiqueta.
            domicilio = Domicilio(
                ID_Venta         = id_venta,
                Estado           = int(EstadoDomicilio.PENDIENTE),
                Fecha_asignacion = _now(),
            )
            db.add(domicilio)
        if datos.get("Direccion_Entrega") is not None:
            domicilio.Direccion_entrega = datos["Direccion_Entrega"]
        if datos.get("Notas") is not None:
            domicilio.Observaciones = datos["Notas"]

        # Barrio de entrega: si llega un ID_Barrio distinto (o el domicilio aún
        # no tiene barrio), se RECALCULA el precio del domicilio y se congela el
        # snapshot nuevo. Sin ID_Barrio se conserva el snapshot actual (F-9: solo
        # se recalcula ante una edición explícita del barrio).
        id_barrio_nuevo = datos.get("ID_Barrio")
        if id_barrio_nuevo and int(id_barrio_nuevo) != (domicilio.ID_Barrio or 0):
            snap = resolver_domicilio(db, int(id_barrio_nuevo))
            domicilio.ID_Barrio              = snap["id_barrio"]
            domicilio.Municipio_entrega      = snap["ciudad"]
            domicilio.Departamento_entrega   = snap["departamento"]
            domicilio.Precio_Domicilio_Base  = snap["base"]
            domicilio.Precio_Domicilio_Final = snap["final"]
            domicilio.Desglose_Ofertas       = snap["desglose"]
            precio_nuevo = snap["final"]
        elif not domicilio.ID_Barrio:
            db.rollback()
            raise HTTPException(status_code=400, detail="Selecciona el barrio de entrega para el domicilio")
        # Sin cambio de barrio solo se toca el texto libre (dirección/notas).
        # Municipio y departamento SIEMPRE salen del barrio: no se aceptan del
        # request (G-1) — se derivan aquí por si el domicilio quedó sin ellos.
        if domicilio.ID_Barrio and not (domicilio.Municipio_entrega and domicilio.Departamento_entrega):
            _b = db.query(Barrio).filter(Barrio.ID_Barrio == domicilio.ID_Barrio).first()
            if _b and _b.ciudad:
                domicilio.Municipio_entrega = _b.ciudad.Nombre
                if _b.ciudad.departamento:
                    domicilio.Departamento_entrega = _b.ciudad.departamento.Nombre

    elif quiere_domicilio is False and domicilio is not None:
        db.delete(domicilio)
        precio_nuevo = 0

    # El costo del envío lo lleva el servidor, no el formulario. Se ajusta por
    # DIFERENCIA entre el snapshot nuevo y el anterior: pasar a domicilio suma el
    # precio del barrio, quitarlo lo resta, y repetir la misma edición no lo
    # duplica.
    if precio_nuevo != precio_anterior:
        pedido.Total = max(
            Decimal("0"),
            Decimal(str(pedido.Total or 0)) - Decimal(precio_anterior) + Decimal(precio_nuevo),
        )

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


def confirmar_pedido(db: Session, id_venta: int) -> dict:
    """
    Confirma el pedido → cambia estado a Confirmado (ID=4).
    Solo se puede confirmar desde Pendiente (1).

    Si el pedido pide más unidades de las que hay en stock, al confirmarlo se
    abren las órdenes de producción del faltante y queda En producción (13) en
    vez de Confirmado: pasa a Listo cuando esas órdenes se completan.

    Regla de negocio: pedidos con pago por transferencia no pueden confirmarse
    hasta que el comprobante haya sido aprobado (Estado_Pago = pagado_completo
    o anticipo_pagado para mixto).
    """
    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # La mayoría de los pedidos nuevos ya no pasan por acá: nacen directo en
    # Confirmado/Esperando pago (sin producción) o en Pendiente de Aprobación,
    # resuelto con aprobar-fecha/proponer-fecha (con producción). Si ya avanzó
    # de "Pendiente" —a mano o por ese otro camino— no hay nada que confirmar.
    if pedido.Estado != EstadoPedido.PENDIENTE:
        return _formato_venta(pedido, db)

    # Un "Pendiente de Aprobación" (necesita producción) no se confirma como un
    # pedido normal: confirmarlo es aprobar de una la fecha que trajo (Camino
    # A), igual que el botón "Aprobar" del panel.
    if getattr(pedido, "Necesita_Produccion", 0) and pedido.Fecha_entrega_esperada:
        from src.features.ventas.gestion_ventas.services.service import (
            _avanzar_tras_fecha_confirmada, _guardar_historial_fecha,
        )
        _avanzar_tras_fecha_confirmada(db, pedido, pedido.Fecha_entrega_esperada)
        _guardar_historial_fecha(db, id_venta, "aceptada", pedido.Fecha_entrega_esperada)
        db.commit()
        db.refresh(pedido)
        return _formato_venta(pedido, db)

    if _lleva_transferencia(pedido.Metodo_Pago):
        ep = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
        if ep not in {"pagado_completo", "anticipo_pagado"}:
            raise HTTPException(
                status_code=400,
                detail="El comprobante de transferencia debe ser aprobado antes de confirmar el pedido.",
            )

    return _gv_cambiar_estado(db, id_venta, EstadoPedido.CONFIRMADO)


def cancelar_pedido(db: Session, id_venta: int, actual: dict = None) -> dict:
    """
    Cancela el pedido. Delega en cambiar_estado() que:
    - Valida la transición con la máquina de estados
    - Restaura stock si el pedido pickup ya lo tenía descontado (desde CONFIRMADO en adelante)
    - Devuelve crédito si se usó al crear el pedido
    Si actual es un cliente, solo puede cancelar su propio pedido.
    """
    pedido = db.query(Venta).filter(
        Venta.ID_Venta == id_venta,
        Venta.Estado.in_(ESTADOS_ACTIVOS),
    ).first()
    if not pedido:
        raise HTTPException(
            status_code=404,
            detail="Pedido no encontrado o ya fue procesado"
        )

    _ESTADOS_CANCELABLES_CLIENTE = frozenset({
        EstadoPedido.PENDIENTE,
        EstadoPedido.FECHA_PROPUESTA,
        EstadoPedido.FECHA_RECHAZADA,
        EstadoPedido.ESCALADO_A_ADMIN,
    })

    if actual and actual.get("tipo") == "cliente":
        id_usuario = actual["registro"].ID_Usuario
        if pedido.ID_Usuario != id_usuario:
            raise HTTPException(status_code=403, detail="No puedes cancelar pedidos de otros clientes")
        if getattr(pedido, "Requiere_Anticipo", None):
            raise HTTPException(
                status_code=400,
                detail="Este pedido no puede cancelarse porque requiere anticipo. Si necesitas cancelarlo, escríbenos.",
            )
        if not _dentro_ventana_edicion(pedido):
            raise HTTPException(
                status_code=400,
                detail="Solo puedes cancelar tu pedido durante los primeros 10 minutos después de crearlo. Escríbenos si necesitas cancelarlo.",
            )
        if pedido.Estado not in _ESTADOS_CANCELABLES_CLIENTE:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este pedido ya está en producción y no puede cancelarse desde aquí. "
                    "Escríbenos y lo revisamos."
                ),
            )

    return _gv_cambiar_estado(db, id_venta, EstadoPedido.CANCELADO)


_ESTADOS_PAGO_BLOQUEADO_EDICION = {"efectivo_recibido", "pagado_completo", "no_recibido"}

_ESTADOS_FINALES = frozenset({EstadoPedido.CANCELADO, EstadoPedido.ENTREGADO})

_VENTANA_EDICION = timedelta(minutes=10)


def _dentro_ventana_edicion(venta: Venta) -> bool:
    """True si el pedido fue creado hace menos de 10 minutos."""
    if not venta.Fecha_Venta:
        return False
    return datetime.utcnow() - venta.Fecha_Venta < _VENTANA_EDICION


def _reabrir_pedido_produccion(db: Session, pedido: Venta, productos_nuevos, fecha_nueva) -> None:
    """Recalcula el pedido tras un ajuste de cantidades y/o de la fecha límite
    deseada, y lo deja 'Pendiente de Aprobación' para que el admin lo revise
    de nuevo (Camino A/B) — es la vía "editar" para reabrir la negociación de
    fecha, alternativa a "rechazar con causa" (`rechazar_fecha`); se pueden
    combinar las dos.

    No agrega productos nuevos: `productos_nuevos` (si viene) debe traer
    exactamente los mismos ID_Producto que ya estaban en el pedido, solo con
    otra Cantidad. Reevalúa contra el stock real con la misma función que usa
    el checkout (`_evaluar_lineas_pedido`), para no duplicar las reglas de
    preorden y de qué es fabricable.
    """
    from types import SimpleNamespace
    from src.features.ventas.gestion_ventas.services.service import (
        _evaluar_lineas_pedido, _productos_producibles,
    )

    era_fecha_propuesta = pedido.Estado == EstadoPedido.FECHA_PROPUESTA

    if productos_nuevos is not None:
        items_actuales = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == pedido.ID_Venta).all()
        ids_actuales = {it.ID_Producto for it in items_actuales}
        ids_nuevos   = {int(p["ID_Producto"]) for p in productos_nuevos}
        if ids_nuevos != ids_actuales:
            raise HTTPException(
                status_code=400,
                detail="Solo puedes ajustar la cantidad de los productos que ya pediste, no agregar ni quitar líneas.",
            )

        productos_input = [
            SimpleNamespace(ID_Producto=int(p["ID_Producto"]), Cantidad=int(p["Cantidad"]))
            for p in productos_nuevos
        ]
        lineas, subtotal_bruto = _evaluar_lineas_pedido(db, productos_input)
        preorden_por_producto = {l["ID_Producto"]: l["preorden"] for l in lineas}
        sobre_stock = any(l["preorden"] > 0 for l in lineas)

        prod_ids    = [l["ID_Producto"] for l in lineas]
        producibles = _productos_producibles(db, prod_ids)
        sin_produccion_con_deficit = [
            l for l in lineas if l["ID_Producto"] not in producibles and l["preorden"] > 0
        ]
        if sin_produccion_con_deficit:
            detalle = "; ".join(
                f"{l['nombre']}: disponible {l['stock']}, pediste {l['cantidad']}"
                for l in sin_produccion_con_deficit
            )
            raise HTTPException(
                status_code=400,
                detail=f"No hay stock suficiente y estos productos no se fabrican por encargo: {detalle}",
            )
        necesita_produccion = any(
            l["ID_Producto"] in producibles and l["preorden"] > 0 for l in lineas
        )

        cantidades = {l["ID_Producto"]: l["cantidad"] for l in lineas}
        for it in items_actuales:
            it.Cantidad          = cantidades[it.ID_Producto]
            it.Cantidad_Preorden = preorden_por_producto.get(it.ID_Producto, 0)

        detalle_venta = db.query(DetalleVenta).filter(DetalleVenta.ID_Venta == pedido.ID_Venta).first()
        subtotal_anterior = Decimal(str(detalle_venta.SubTotal or 0)) if detalle_venta else Decimal("0")
        diferencia = subtotal_bruto - subtotal_anterior
        pedido.Total = max(Decimal("0"), Decimal(str(pedido.Total or 0)) + diferencia)
        if detalle_venta:
            detalle_venta.SubTotal = subtotal_bruto

        pedido.Necesita_Produccion = 1 if necesita_produccion else 0
        pedido.Sobre_Stock         = 1 if sobre_stock else 0

    if fecha_nueva is not None:
        _validar_fecha_entrega_esperada(db, fecha_nueva)
        pedido.Fecha_entrega_esperada = fecha_nueva

    if not getattr(pedido, "Necesita_Produccion", 0):
        raise HTTPException(
            status_code=400,
            detail="Con estas cantidades el pedido ya no necesita producción: cancélalo y haz uno nuevo.",
        )

    pedido.Estado = EstadoPedido.PENDIENTE
    if era_fecha_propuesta:
        pedido.intentos_rechazo = (int(getattr(pedido, "intentos_rechazo", 0) or 0)) + 1


def editar_mi_pedido(db: Session, id_venta: int, datos: dict, actual: dict) -> dict:
    """
    El cliente puede cambiar Metodo_Pago y/o tipo de entrega en cualquier estado activo.
    Bloqueado si: pedido en estado final, pago ya cobrado, o ya tiene grupos de envío.
    Cambio Recogida→Domicilio: suma el costo del domicilio al Total y crea el registro.
    Cambio Domicilio→Recogida: verifica que no haya repartidor asignado, resta el costo
    del domicilio del Total, devuelve crédito si el anticipo supera el nuevo total.
    """
    from decimal import Decimal

    pedido = db.query(Venta).filter(
        Venta.ID_Venta == id_venta,
    ).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # Dos puntos de entrada quedan fuera de la ventana de 10 minutos, que existe
    # para el arrepentimiento inmediato tras crear el pedido, no para esto:
    # - Reabrir la negociación de fecha (rechazar-con-causa + editar), habilitada
    #   deliberadamente por la contraoferta del admin.
    # - Adjuntar el comprobante de un pedido 'Esperando Pago': puede necesitar
    #   más de 10 minutos (abrir el banco, transferir, tomar la captura).
    _reabre_negociacion = pedido.Estado in (EstadoPedido.PENDIENTE, EstadoPedido.FECHA_PROPUESTA)
    _fuera_de_ventana_ok = _reabre_negociacion or pedido.Estado == EstadoPedido.ESPERANDO_PAGO

    if actual.get("tipo") == "cliente":
        if pedido.ID_Usuario != actual["registro"].ID_Usuario:
            raise HTTPException(status_code=403, detail="No puedes editar pedidos de otros clientes")
        if getattr(pedido, "Requiere_Anticipo", None):
            raise HTTPException(
                status_code=400,
                detail="Este pedido no puede editarse porque requiere anticipo. Si necesitas un cambio, escríbenos.",
            )
        if not _fuera_de_ventana_ok and not _dentro_ventana_edicion(pedido):
            raise HTTPException(
                status_code=400,
                detail="Solo puedes editar tu pedido durante los primeros 10 minutos después de crearlo. Escríbenos si necesitas un cambio.",
            )

    if pedido.Estado in _ESTADOS_FINALES:
        raise HTTPException(status_code=400, detail="Este pedido ya fue completado y no puede editarse")

    estado_pago = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
    if estado_pago in _ESTADOS_PAGO_BLOQUEADO_EDICION:
        raise HTTPException(
            status_code=400,
            detail="El pago de este pedido ya fue registrado. Contacta un empleado para realizar cambios.",
        )

    # ── Reabrir negociación: ajustar cantidades y/o la fecha límite deseada ──
    # Solo mientras el pedido espera aprobación de planta o tiene una
    # contraoferta de fecha. No agrega productos nuevos: solo cambia la
    # cantidad de líneas que ya estaban en el pedido.
    productos_nuevos = datos.get("productos")
    fecha_nueva       = datos.get("Fecha_entrega_esperada")
    if productos_nuevos is not None or fecha_nueva is not None:
        if not _reabre_negociacion:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Solo se pueden editar cantidades o la fecha mientras el pedido está "
                    "pendiente de aprobación o tiene una fecha propuesta."
                ),
            )
        _reabrir_pedido_produccion(db, pedido, productos_nuevos, fecha_nueva)

    grupos = db.query(GrupoEnvio).filter(GrupoEnvio.ID_Venta == id_venta).all()
    if grupos:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este pedido ya fue dividido en grupos de envío. "
                "El tipo de entrega se maneja por grupo desde el panel."
            ),
        )

    if datos.get("Metodo_Pago"):
        nuevo_metodo = datos["Metodo_Pago"].strip()
        # Mixto no puede usarse cuando el pedido exige anticipo del 50%
        if "mixto" in nuevo_metodo.lower() and pedido.Requiere_Anticipo:
            raise HTTPException(
                status_code=400,
                detail="El método mixto no está disponible para pedidos que requieren anticipo del 50%.",
            )
        pedido.Metodo_Pago = nuevo_metodo

    # Guardar comprobante si se subió uno nuevo
    comprobante_nuevo = datos.get("Comprobante_Pago")
    if comprobante_nuevo:
        pedido.Comprobante_Pago = comprobante_nuevo
        # Si no viene cambio de método, actualizar Estado_Pago aquí para que
        # el admin pueda ver y aprobar el comprobante. El bloque de Metodo_Pago
        # lo sobreescribiría si ambos llegan juntos, por lo que solo corre cuando
        # Metodo_Pago no está en el request.
        if not datos.get("Metodo_Pago"):
            _metodo_actual = (pedido.Metodo_Pago or "").strip()
            _ep_actual = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
            _estados_finales_pago = {"pagado_completo", "efectivo_recibido", "anticipo_pagado"}
            if _lleva_transferencia(_metodo_actual) and _ep_actual not in _estados_finales_pago:
                pedido.Estado_Pago = "pendiente_validacion"

    # Actualizar Estado_Pago y montos según el método de pago resultante
    if datos.get("Metodo_Pago"):
        metodo_resultante = (pedido.Metodo_Pago or "").strip()
        estado_pago_actual = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
        if _lleva_transferencia(metodo_resultante):
            if comprobante_nuevo or pedido.Comprobante_Pago:
                pedido.Estado_Pago = "pendiente_validacion"
            else:
                pedido.Estado_Pago = "pendiente"
        else:
            # Cambio a Efectivo puro: resetear estado y limpiar montos mixto
            if estado_pago_actual not in _ESTADOS_PAGO_BLOQUEADO_EDICION:
                pedido.Estado_Pago = "pendiente"
            pedido.Monto_Efectivo = None
            pedido.Monto_Transferencia = None

    # Repartir montos cuando el método es Mixto
    if _es_mixto(pedido.Metodo_Pago) and datos.get("Monto_Efectivo") is not None:
        total_actual = pedido.Total or Decimal(0)
        monto_ef = Decimal(str(datos["Monto_Efectivo"] or 0))
        efectivo = max(Decimal("0"), min(monto_ef, total_actual))
        pedido.Monto_Efectivo = efectivo
        pedido.Monto_Transferencia = total_actual - efectivo

    quiere_domicilio = datos.get("quiere_domicilio")  # True | False | None
    domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first()
    tenia_domicilio = domicilio is not None

    if quiere_domicilio is True and not tenia_domicilio:
        id_barrio = datos.get("ID_Barrio")
        if not id_barrio:
            raise HTTPException(status_code=400, detail="Selecciona el barrio de entrega para el domicilio")
        snap = resolver_domicilio(db, int(id_barrio))
        costo = Decimal(snap["final"])
        nuevo_domicilio = Domicilio(
            ID_Venta              = id_venta,
            Estado                = int(EstadoDomicilio.PENDIENTE),
            Fecha_asignacion      = _now(),
            ID_Barrio             = snap["id_barrio"],
            Municipio_entrega     = snap["ciudad"],
            Departamento_entrega  = snap["departamento"],
            Precio_Domicilio_Base  = snap["base"],
            Precio_Domicilio_Final = snap["final"],
            Desglose_Ofertas       = snap["desglose"],
            Direccion_entrega      = datos.get("Direccion_Entrega") or "",
            Observaciones          = datos.get("Notas"),
        )
        db.add(nuevo_domicilio)
        pedido.Total = (pedido.Total or Decimal(0)) + costo

    elif quiere_domicilio is False and tenia_domicilio:
        if domicilio.ID_Empleado is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Ya se asignó un repartidor para este pedido. "
                    "Contacta a un empleado para cambiar el tipo de entrega."
                ),
            )
        costo_dom = Decimal(domicilio.Precio_Domicilio_Final or 0)
        nuevo_total = max(Decimal(0), (pedido.Total or Decimal(0)) - costo_dom)
        anticipo = Decimal(pedido.Anticipo_Monto or 0)
        if anticipo > nuevo_total > 0:
            exceso = anticipo - nuevo_total
            _abonar_credito(db, pedido.ID_Usuario, exceso, id_venta)
        domicilio.Estado = int(EstadoDomicilio.CANCELADO)
        pedido.Total = nuevo_total

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


_ESTADOS_PAGO_YA_COBRADO = {"efectivo_recibido", "pagado_completo", "anticipo_pagado"}


def _es_mixto(metodo: str | None) -> bool:
    """Pedido repartido entre efectivo y transferencia."""
    return "mixto" in (metodo or "").strip().lower()


def _lleva_transferencia(metodo: str | None) -> bool:
    """¿Hay un comprobante que revisar? Transferencia pura o mixto."""
    _m = (metodo or "").strip().lower()
    return "transfer" in _m or "mixto" in _m


# El mixto se cobra en dos pasos —el comprobante de la parte transferida y la
# plata en mano— y cada uno puede caer primero. Estos son los estados desde los
# que todavía falta el otro paso.
_ESTADOS_MIXTO_A_MEDIAS = {"pendiente", "pendiente_validacion", "comprobante_rechazado"}


def registrar_cobro_pedido(db: Session, id_venta: int, datos, id_usuario_actual: int) -> dict:
    """
    Admin/empleado registra cobro en efectivo para un pedido (contra entrega o en tienda).
    Estado_Pago → 'efectivo_recibido' o 'no_recibido'.
    """
    from datetime import datetime, timezone

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    estado_pago = (getattr(venta, "Estado_Pago", None) or "pendiente").strip()
    mixto       = _es_mixto(venta.Metodo_Pago)
    # En un mixto, "anticipo_pagado" solo dice que UNA de las dos mitades entró.
    # El efectivo se puede seguir cobrando mientras no esté marcado su registro.
    efectivo_ya_registrado = bool(getattr(venta, "Pago_Final_Registrado", 0))
    if estado_pago in _ESTADOS_PAGO_YA_COBRADO and not (mixto and not efectivo_ya_registrado):
        raise HTTPException(status_code=409, detail="El cobro ya fue registrado para este pedido")

    if not datos.recibido:
        venta.Estado_Pago = "no_recibido"
    elif mixto:
        # La plata en mano se marca en su propio registro, para saber cuál de
        # las dos mitades entró y no tener que adivinarlo desde el estado.
        venta.Pago_Final_Registrado  = 1
        venta.Pago_Final_Monto       = venta.Monto_Efectivo
        venta.Pago_Final_Metodo_Pago = "Efectivo"
        venta.Pago_Final_Fecha       = datetime.now(timezone.utc).replace(tzinfo=None)
        # Queda saldado solo si el comprobante de la transferencia ya se aprobó.
        venta.Estado_Pago = (
            "anticipo_pagado" if estado_pago in _ESTADOS_MIXTO_A_MEDIAS
            else "pagado_completo"
        )
    else:
        venta.Estado_Pago = "efectivo_recibido"
    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


def aprobar_comprobante(db: Session, id_venta: int) -> dict:
    """
    Admin aprueba el comprobante de transferencia.
    Estado_Pago: 'pendiente_validacion' → 'pagado_completo'.
    Solo aplica si el método de pago es Transferencia.
    """
    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # El mixto también trae comprobante: es el de su parte transferida. Antes
    # esta puerta solo dejaba pasar "Transferencia" y el admin no podía
    # aprobar ni rechazar el soporte de un pedido mixto.
    if not _lleva_transferencia(pedido.Metodo_Pago):
        raise HTTPException(status_code=400, detail="Este pedido no tiene pago por transferencia")

    if not pedido.Comprobante_Pago:
        raise HTTPException(status_code=400, detail="El pedido no tiene comprobante adjunto")

    estado_pago = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
    if estado_pago == "pagado_completo":
        raise HTTPException(status_code=409, detail="El comprobante ya fue aprobado")

    # En un mixto aprobar el comprobante salda solo la mitad transferida: falta
    # el efectivo, salvo que ya lo hayan cobrado.
    if _es_mixto(pedido.Metodo_Pago) and estado_pago in _ESTADOS_MIXTO_A_MEDIAS:
        pedido.Estado_Pago = "anticipo_pagado"
    else:
        pedido.Estado_Pago = "pagado_completo"

    # El pedido estaba Esperando Pago (el total, si no necesitaba producción;
    # el anticipo, si sí): con el comprobante ya aprobado, sigue el flujo de
    # producción/alistamiento normal.
    if pedido.Estado == EstadoPedido.ESPERANDO_PAGO:
        _avanzar_tras_pago_aprobado(db, pedido)

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


def pagar_pedido(db: Session, id_venta: int, datos: dict, actual: dict) -> dict:
    """El cliente adjunta el comprobante de pago mientras su pedido está
    'Esperando Pago': el anticipo (si necesitó aprobación de fecha) o el
    total (si no necesitaba producción).

    No avanza el estado por sí solo — lo hace `aprobar_comprobante` cuando el
    admin revisa y aprueba el comprobante, igual que cualquier otro pedido por
    transferencia.
    """
    if actual.get("tipo") != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.ID_Usuario != actual["registro"].ID_Usuario:
        raise HTTPException(status_code=403, detail="No puedes pagar pedidos de otros clientes")
    if pedido.Estado != EstadoPedido.ESPERANDO_PAGO:
        raise HTTPException(status_code=400, detail="Este pedido no está esperando pago")

    comprobante_url = (datos.get("comprobante_url") or "").strip()
    if not comprobante_url:
        raise HTTPException(status_code=400, detail="Adjunta el comprobante de la transferencia")

    if getattr(pedido, "Requiere_Anticipo", 0):
        minimo = Decimal(str(pedido.Anticipo_Requerido or 0))
        monto  = Decimal(str(datos.get("monto") or 0))
        if monto < minimo:
            raise HTTPException(
                status_code=400,
                detail=f"El anticipo mínimo es ${minimo:,.0f} (50% del pedido).",
            )
        pedido.Anticipo_Monto           = monto
        pedido.Anticipo_Metodo_Pago     = "Transferencia"
        pedido.Anticipo_Comprobante_Url = comprobante_url
        pedido.Anticipo_Registrado      = 1
        if monto >= Decimal(str(pedido.Total or 0)):
            pedido.Pago_Final_Registrado = 1

    pedido.Comprobante_Pago = comprobante_url
    pedido.Estado_Pago      = "pendiente_validacion"

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


def rechazar_comprobante(db: Session, id_venta: int, motivo: str, id_usuario_actual: int) -> dict:
    """
    Admin rechaza el comprobante de transferencia.
    Estado_Pago → 'comprobante_rechazado'. El comprobante NO se elimina.
    El motivo se notifica al cliente; no se guarda en columna nueva.
    """
    from src.shared.services.notificaciones_utils import notificar

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if not _lleva_transferencia(pedido.Metodo_Pago):
        raise HTTPException(status_code=400, detail="Este pedido no tiene pago por transferencia")

    if not pedido.Comprobante_Pago:
        raise HTTPException(status_code=400, detail="El pedido no tiene comprobante adjunto")

    estado_pago = (getattr(pedido, "Estado_Pago", None) or "pendiente").strip()
    if estado_pago == "comprobante_rechazado":
        raise HTTPException(status_code=409, detail="El comprobante ya fue rechazado")

    pedido.Estado_Pago = "comprobante_rechazado"
    pedido.Motivo_Rechazo_Comprobante = motivo.strip()

    notificar(
        db,
        "comprobante_rechazado",
        f"Comprobante rechazado — Pedido #{id_venta}",
        f"Motivo: {motivo}",
        id_venta,
        "/ventas/pedidos",
    )

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)
