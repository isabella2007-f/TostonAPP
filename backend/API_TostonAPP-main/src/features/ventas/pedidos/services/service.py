from decimal import Decimal
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException

from src.shared.services.models import (
    Venta, Estado, DetalleVenta, Domicilio,
    VentaXProducto, Producto, DescuentoXVenta,
    Barrio,
)
from src.features.ventas.gestion_ventas.services.service import (
    _formato_venta, _now, cambiar_estado as _gv_cambiar_estado,
    _abonar_credito, _avanzar_tras_pago_aprobado, _validar_fecha_entrega_esperada,
    _evaluar_cierre_ventana,
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
        )
        .order_by(Venta.Fecha_pedido.desc())
        .offset(offset)
        .limit(por_pagina)
        .all()
    )

    # 3.6: la lista es el lugar más realista donde un admin "toca" pedidos que
    # llevan rato esperando — se evalúa el cierre de ventana por cada fila de
    # esta página. Ya es no-op tras la primera vez (Stock_Reservado) así que
    # el costo real es solo en la página donde el pedido cruza el minuto 10.
    for p in pedidos:
        _evaluar_cierre_ventana(db, p)

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
        )
        .filter(Venta.ID_Venta == id_venta)
        .first()
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    _evaluar_cierre_ventana(db, pedido)
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

    El comprobante de transferencia NUNCA se exige acá (3.2): para el cliente
    siempre queda diferido al mecanismo de Esperando Pago (`pagar_pedido` /
    `aprobar_comprobante`), sin importar si el pedido necesita producción.
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

    # Bloquear si el cliente todavía está dentro de su ventana de edición.
    if pedido.Fecha_Venta and (_now() - pedido.Fecha_Venta) < _VENTANA_EDICION:
        mins_restantes = int((_VENTANA_EDICION - (_now() - pedido.Fecha_Venta)).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=400,
            detail=f"Este pedido está en período de edición del cliente ({mins_restantes} min restantes). Espera antes de procesarlo.",
        )

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
        EstadoPedido.FECHA_PROPUESTA_FINAL,
        EstadoPedido.FECHA_RECHAZADA,
        EstadoPedido.ESCALADO_A_ADMIN,
        EstadoPedido.ESPERANDO_PAGO,
    })

    if actual and actual.get("tipo") == "cliente":
        id_usuario = actual["registro"].ID_Usuario
        if pedido.ID_Usuario != id_usuario:
            raise HTTPException(status_code=403, detail="No puedes cancelar pedidos de otros clientes")
        # Bloquea por lo PAGADO, no por lo exigido (prompt-pedidos-2, 3.4): con
        # el chequeo viejo (Requiere_Anticipo) ningún pedido que superara el
        # umbral podía cancelarse jamás, así hubiera pagado o no.
        if getattr(pedido, "Anticipo_Registrado", None):
            raise HTTPException(
                status_code=400,
                detail="Este pedido no puede cancelarse porque ya se registró el anticipo. Si necesitas cancelarlo, escríbenos.",
            )
        if pedido.Estado not in _ESTADOS_CANCELABLES_CLIENTE:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este pedido ya está en proceso y no puede cancelarse desde aquí. "
                    "Escríbenos y lo revisamos."
                ),
            )
        # La ventana de 10 minutos protege el arrepentimiento inmediato tras
        # crear el pedido (Pendiente); en negociación de fecha o escalado el
        # cliente puede cancelar en cualquier momento — esos estados solo se
        # alcanzan bastante después de los 10 minutos, así que exigir la
        # ventana ahí bloqueaba la cancelación siempre, contradiciendo 3.4.
        if pedido.Estado == EstadoPedido.PENDIENTE and not _dentro_ventana_edicion(pedido):
            raise HTTPException(
                status_code=400,
                detail="Solo puedes cancelar tu pedido durante los primeros 10 minutos después de crearlo. Escríbenos si necesitas cancelarlo.",
            )

    return _gv_cambiar_estado(db, id_venta, EstadoPedido.CANCELADO)


_ESTADOS_PAGO_BLOQUEADO_EDICION = {"efectivo_recibido", "pagado_completo", "no_recibido"}

_ESTADOS_FINALES = frozenset({EstadoPedido.CANCELADO, EstadoPedido.ENTREGADO})

_VENTANA_EDICION = timedelta(minutes=10)

# Rechazos que tolera un mismo comprobante (el primero -anticipo o total sin
# producción-, o el segundo -saldo restante-) antes de cancelar el pedido
# solo. Los dos usan el mismo límite, pero cada uno cuenta aparte (ver
# Intentos_Rechazo_Comprobante_Anticipo / _Saldo en el modelo).
LIMITE_INTENTOS_COMPROBANTE = 3


def _dentro_ventana_edicion(venta: Venta) -> bool:
    """True si el pedido fue creado hace menos de 10 minutos.

    Se mide con `_now()` —hora de Bogotá, sin zona— porque es con ese mismo
    reloj con el que se escribió `Fecha_Venta` al crear el pedido. Restaba
    `utcnow()`, que acá son cinco horas más: un pedido recién hecho nacía con
    cinco horas de antigüedad y la ventana estaba vencida siempre, así que el
    cliente no podía cancelar ni corregir su pedido nunca.
    """
    if not venta.Fecha_Venta:
        return False
    return _now() - venta.Fecha_Venta < _VENTANA_EDICION


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

        # 3.6: una edición dentro de la ventana puede cruzar el umbral de
        # anticipo para arriba o para abajo — se recalcula sobre el total ya
        # ajustado. Todavía no hay nada pagado en este punto (el anticipo de
        # un pedido con producción recién se exige al aprobarse la fecha, ver
        # `_avanzar_tras_fecha_confirmada`), así que no hay que reconciliar
        # plata ya registrada, solo el requisito.
        from src.features.ventas.gestion_ventas.services.service import (
            _pide_anticipo, _calcular_anticipo,
        )
        if _pide_anticipo(pedido.Total):
            pedido.Requiere_Anticipo  = 1
            pedido.Anticipo_Requerido = _calcular_anticipo(pedido.Total, Decimal("0"))
        else:
            pedido.Requiere_Anticipo  = 0
            pedido.Anticipo_Requerido = Decimal("0")

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
        # Bloquea por lo PAGADO, no por lo exigido (mismo fix que
        # cancelar_pedido, prompt-pedidos-2 3.4): con el chequeo viejo
        # (Requiere_Anticipo) ningún pedido que superara el umbral podía
        # editarse jamás, ni siquiera para recalcular ese mismo umbral tras
        # ajustar cantidades dentro de la ventana (3.6).
        if getattr(pedido, "Anticipo_Registrado", None):
            raise HTTPException(
                status_code=400,
                detail="Este pedido no puede editarse porque ya se registró el anticipo. Si necesitas un cambio, escríbenos.",
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
        # Mismo registro que en el mixto: sin esto, un pedido con anticipo
        # cuyo saldo se cobra 100% en efectivo quedaba con Estado_Pago =
        # 'efectivo_recibido' pero Pago_Final_Registrado en 0, y el gate de
        # `cambiar_estado` hacia ENTREGADO (que exige Pago_Final_Registrado
        # en todo pedido con anticipo) lo bloqueaba para siempre.
        venta.Estado_Pago = "efectivo_recibido"
        if getattr(venta, "Requiere_Anticipo", 0):
            venta.Pago_Final_Registrado  = 1
            venta.Pago_Final_Monto       = datos.monto if datos.monto is not None else venta.Total
            venta.Pago_Final_Metodo_Pago = "Efectivo"
            venta.Pago_Final_Fecha       = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


def aprobar_comprobante(db: Session, id_venta: int) -> dict:
    """
    Admin aprueba el comprobante de transferencia.
    - Mixto o anticipo sin pago final registrado → 'anticipo_pagado'.
    - Anticipo con pago final ya registrado, o pago único → 'pagado_completo'.
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
    # En un pedido con anticipo, aprobar el comprobante confirma solo el anticipo
    # si aún no se registró el pago final completo.
    if _es_mixto(pedido.Metodo_Pago) and estado_pago in _ESTADOS_MIXTO_A_MEDIAS:
        pedido.Estado_Pago = "anticipo_pagado"
    elif getattr(pedido, "Requiere_Anticipo", 0) and not getattr(pedido, "Pago_Final_Registrado", 0):
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
    Admin rechaza el comprobante de transferencia (el primero: el anticipo de
    un pedido con producción, o el total de uno sin ella).
    Estado_Pago → 'comprobante_rechazado'. El comprobante NO se elimina.
    El motivo se notifica al cliente; no se guarda en columna nueva.

    Al 3er rechazo (LIMITE_INTENTOS_COMPROBANTE, 3.5) el pedido se cancela
    solo, reusando el mismo camino de cancelación que ya reversa stock/crédito
    (`cambiar_estado` → CANCELADO), sin duplicar esa lógica acá.
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
    pedido.Intentos_Rechazo_Comprobante_Anticipo = (
        int(getattr(pedido, "Intentos_Rechazo_Comprobante_Anticipo", 0) or 0) + 1
    )

    if pedido.Intentos_Rechazo_Comprobante_Anticipo >= LIMITE_INTENTOS_COMPROBANTE:
        pedido.Motivo_Rechazo_Comprobante = (
            f"Cancelado automáticamente: comprobante rechazado "
            f"{LIMITE_INTENTOS_COMPROBANTE} veces. Último motivo: {motivo.strip()}"
        )
        notificar(
            db,
            "comprobante_rechazado",
            f"Pedido cancelado — Pedido #{id_venta}",
            pedido.Motivo_Rechazo_Comprobante,
            id_venta,
            "/ventas/pedidos",
        )
        return _gv_cambiar_estado(db, id_venta, EstadoPedido.CANCELADO, saltar_ventana_proteccion=True)

    notificar(
        db,
        "comprobante_rechazado",
        f"Comprobante rechazado — Pedido #{id_venta}",
        f"Motivo: {motivo}. Intento {pedido.Intentos_Rechazo_Comprobante_Anticipo}/{LIMITE_INTENTOS_COMPROBANTE}.",
        id_venta,
        "/ventas/pedidos",
    )

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


# ── Segundo comprobante: el saldo restante tras el anticipo (3.10) ──────────
#
# Solo aplica cuando el pedido requirió anticipo Y el resto se paga por
# transferencia (si es en efectivo, se cobra físicamente al entregar/recoger,
# ver `registrar_cobro_pedido` y 3.11 — este flujo no interviene). Reusa el
# mismo mecanismo de 3 intentos que el primer comprobante (`rechazar_comprobante`),
# pero con su propio contador (Intentos_Rechazo_Comprobante_Saldo): son dos
# validaciones independientes en momentos distintos del pedido.


def _saldo_por_transferencia_aplica(pedido: Venta) -> str | None:
    """Si corresponde pedir el segundo comprobante, devuelve None. Si no
    corresponde, devuelve el motivo (para el 400)."""
    if not getattr(pedido, "Requiere_Anticipo", 0):
        return "Este pedido no tiene anticipo, no aplica un segundo comprobante"
    if not _lleva_transferencia(pedido.Metodo_Pago):
        return "El saldo de este pedido se cobra en efectivo, no por transferencia"
    if getattr(pedido, "Pago_Final_Registrado", 0):
        return "El saldo de este pedido ya fue registrado"
    return None


def pagar_saldo_pedido(db: Session, id_venta: int, datos: dict, actual: dict) -> dict:
    """El cliente adjunta el comprobante del SALDO restante (segundo
    comprobante), cuando ese resto se paga por transferencia. No avanza el
    estado por sí solo — lo hace `aprobar_comprobante_saldo`.
    """
    if actual.get("tipo") != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.ID_Usuario != actual["registro"].ID_Usuario:
        raise HTTPException(status_code=403, detail="No puedes pagar pedidos de otros clientes")
    if pedido.Estado in _ESTADOS_FINALES:
        raise HTTPException(status_code=400, detail="Este pedido ya fue completado")

    motivo_no_aplica = _saldo_por_transferencia_aplica(pedido)
    if motivo_no_aplica:
        raise HTTPException(status_code=400, detail=motivo_no_aplica)

    comprobante_url = (datos.get("comprobante_url") or "").strip()
    if not comprobante_url:
        raise HTTPException(status_code=400, detail="Adjunta el comprobante de la transferencia")

    pedido.Saldo_Comprobante_Url = comprobante_url
    pedido.Estado_Pago           = "saldo_pendiente_validacion"

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


def aprobar_comprobante_saldo(db: Session, id_venta: int) -> dict:
    """Admin aprueba el comprobante del saldo restante → registra el pago
    final (mismos campos Pago_Final_* que `registrar_pago_final`) y libera el
    despacho (ver el gate en `cambiar_estado`, 3.10)."""
    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    estado_pago = (getattr(pedido, "Estado_Pago", None) or "").strip()
    if estado_pago != "saldo_pendiente_validacion":
        raise HTTPException(status_code=400, detail="Este pedido no tiene un comprobante de saldo por aprobar")

    monto_adeudado = Decimal(str(pedido.Total or 0)) - Decimal(str(pedido.Anticipo_Monto or 0))
    pedido.Pago_Final_Monto           = max(Decimal("0"), monto_adeudado)
    pedido.Pago_Final_Metodo_Pago     = "Transferencia"
    pedido.Pago_Final_Comprobante_Url = pedido.Saldo_Comprobante_Url
    pedido.Pago_Final_Fecha           = _now()
    pedido.Pago_Final_Registrado      = 1
    pedido.Estado_Pago                = "pagado_completo"

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


def rechazar_comprobante_saldo(db: Session, id_venta: int, motivo: str, id_usuario_actual: int) -> dict:
    """Admin rechaza el comprobante del saldo restante. Al 3er rechazo el
    pedido se cancela solo, sin reembolsar el saldo: nunca se marcó como
    efectivamente pagado (Pago_Final_Registrado sigue en 0), así que la
    cascada de cancelación solo devuelve el anticipo -si corresponde-, nunca
    algo que no llegó a cobrarse."""
    from src.shared.services.notificaciones_utils import notificar

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    estado_pago = (getattr(pedido, "Estado_Pago", None) or "").strip()
    if estado_pago != "saldo_pendiente_validacion":
        raise HTTPException(status_code=400, detail="Este pedido no tiene un comprobante de saldo por aprobar")

    pedido.Estado_Pago = "saldo_comprobante_rechazado"
    pedido.Motivo_Rechazo_Comprobante = motivo.strip()
    pedido.Intentos_Rechazo_Comprobante_Saldo = (
        int(getattr(pedido, "Intentos_Rechazo_Comprobante_Saldo", 0) or 0) + 1
    )

    if pedido.Intentos_Rechazo_Comprobante_Saldo >= LIMITE_INTENTOS_COMPROBANTE:
        pedido.Motivo_Rechazo_Comprobante = (
            f"Cancelado automáticamente: comprobante de saldo rechazado "
            f"{LIMITE_INTENTOS_COMPROBANTE} veces. Último motivo: {motivo.strip()}"
        )
        notificar(
            db,
            "comprobante_rechazado",
            f"Pedido cancelado — Pedido #{id_venta}",
            pedido.Motivo_Rechazo_Comprobante,
            id_venta,
            "/ventas/pedidos",
        )
        return _gv_cambiar_estado(db, id_venta, EstadoPedido.CANCELADO, saltar_ventana_proteccion=True)

    notificar(
        db,
        "comprobante_rechazado",
        f"Comprobante de saldo rechazado — Pedido #{id_venta}",
        f"Motivo: {motivo}",
        id_venta,
        "/ventas/pedidos",
    )

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


# ── 3.7: excepción de cobro en efectivo ────────────────────────────────────
# Constantes fijas (no configurables desde el panel, per prompt-pedidos-2 2.4.1):
# 24h para reintentar el cobro en tienda antes de que solo quede cancelar;
# 48h totales desde que se entra a "Retenido en tienda" hasta que la
# cancelación por falta de pago deja de ofrecerse como sugerencia y pasa a
# ser obligatoria. Ambas se evalúan de forma perezosa (sin scheduler): se
# comparan contra Fecha_Retenido_En_Tienda cada vez que se toca el pedido.
_VENTANA_REINTENTO_RETENIDO  = timedelta(hours=24)
_VENTANA_LIMITE_RETENIDO     = timedelta(hours=48)


def marcar_retenido_en_tienda(db: Session, id_venta: int) -> dict:
    """El cajero no pudo cobrar en efectivo en tienda (recoger en tienda, sin
    domicilio): el pedido pasa a 'Retenido en tienda'. El producto no se
    entrega y el stock ya reservado se mantiene apartado."""
    from src.shared.services.notificaciones_utils import notificar

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.Estado != EstadoPedido.LISTO:
        raise HTTPException(status_code=400, detail="Solo se puede retener en tienda un pedido en estado 'Listo'")

    pedido.Estado                    = EstadoPedido.RETENIDO_EN_TIENDA
    pedido.Estado_Pago               = "no_recibido"
    pedido.Fecha_Retenido_En_Tienda  = _now()

    notificar(
        db, "pedido_retenido",
        f"Pedido retenido en tienda — Pedido #{id_venta}",
        "No se pudo registrar el cobro en efectivo. Tienes 24 horas para volver a pagarlo antes de que se cancele.",
        id_venta, "/cliente/pedidos",
    )
    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


def _dentro_ventana_reintento(pedido) -> bool:
    if not pedido.Fecha_Retenido_En_Tienda:
        return False
    return _now() - pedido.Fecha_Retenido_En_Tienda < _VENTANA_REINTENTO_RETENIDO


def _fuera_de_plazo_limite(pedido) -> bool:
    """A las 48h la cancelación deja de ser sugerida y pasa a ser obligatoria."""
    if not pedido.Fecha_Retenido_En_Tienda:
        return False
    return _now() - pedido.Fecha_Retenido_En_Tienda >= _VENTANA_LIMITE_RETENIDO


def _exigir_retenido_en_tienda(pedido) -> None:
    if pedido.Estado != EstadoPedido.RETENIDO_EN_TIENDA:
        raise HTTPException(status_code=400, detail="Este pedido no está retenido en tienda")


def reintentar_pago_retenido(db: Session, id_venta: int, datos, id_usuario_actual: int) -> dict:
    """El cliente vuelve dentro de las 24h y el cajero registra el cobro
    (efectivo o transferencia con comprobante ya aprobado a mano). Reusa
    `registrar_cobro_pedido` para no duplicar la validación de monto/mixto,
    y de ahí avanza directo a Entregado."""
    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    _exigir_retenido_en_tienda(pedido)

    if _fuera_de_plazo_limite(pedido):
        raise HTTPException(
            status_code=400,
            detail="Se cumplieron las 48 horas del plazo. Este pedido ya no admite reintento: cancélalo.",
        )
    if not _dentro_ventana_reintento(pedido):
        raise HTTPException(
            status_code=400,
            detail="Se cumplieron las 24 horas para reintentar el cobro. Sugerí cancelar el pedido.",
        )

    # Reabre el Estado_Pago para que registrar_cobro_pedido pueda volver a
    # evaluarlo (estaba en 'no_recibido', que ya cuenta como "ya cobrado" del
    # lado equivocado): el pedido no ha cobrado nada todavía.
    pedido.Estado_Pago = "pendiente"
    resultado = registrar_cobro_pedido(db, id_venta, datos, id_usuario_actual)

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if (getattr(pedido, "Estado_Pago", None) or "").strip() in _ESTADOS_PAGO_YA_COBRADO:
        pedido.Estado = EstadoPedido.ENTREGADO
        db.commit()
        db.refresh(pedido)
        resultado = _formato_venta(pedido, db)
    return resultado


def cambiar_a_domicilio_retenido(db: Session, id_venta: int, datos, id_usuario_actual: int) -> dict:
    """Desde 'Retenido en tienda', cambia la entrega a domicilio: recalcula el
    costo con `resolver_domicilio` (no se duplica el cálculo), lo suma al
    saldo pendiente y vuelve a la fase de despacho (3.9)."""
    from src.shared.services.notificaciones_utils import notificar

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    _exigir_retenido_en_tienda(pedido)
    if _fuera_de_plazo_limite(pedido):
        raise HTTPException(
            status_code=400,
            detail="Se cumplieron las 48 horas del plazo. Este pedido ya no admite cambios: cancélalo.",
        )

    ya_tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first()
    if ya_tiene_domicilio:
        raise HTTPException(status_code=400, detail="Este pedido ya tiene un domicilio asociado")
    if not datos.ID_Barrio:
        raise HTTPException(status_code=400, detail="Selecciona el barrio de entrega")

    snapshot = resolver_domicilio(db, datos.ID_Barrio)
    costo = Decimal(str(snapshot["final"] or 0))

    pedido.Total          = Decimal(str(pedido.Total or 0)) + costo
    pedido.Estado         = EstadoPedido.LISTO
    pedido.Estado_Pago    = "pendiente"
    pedido.Fecha_Retenido_En_Tienda = None

    nuevo_dom = Domicilio(
        ID_Venta             = id_venta,
        Fecha_asignacion     = None,
        Observaciones        = datos.Observaciones,
        Estado               = EstadoDomicilio.PENDIENTE,
        Direccion_entrega    = datos.Direccion_entrega,
        Municipio_entrega    = snapshot["ciudad"] or datos.Municipio_entrega,
        Departamento_entrega = snapshot["departamento"] or datos.Departamento_entrega,
        ID_Barrio              = snapshot["id_barrio"],
        Precio_Domicilio_Base  = snapshot["base"],
        Precio_Domicilio_Final = snapshot["final"],
        Desglose_Ofertas       = snapshot["desglose"],
    )
    db.add(nuevo_dom)

    notificar(
        db, "domicilio_pendiente", "Domicilio sin repartidor",
        f"El pedido #{id_venta} pasó a domicilio (venía retenido en tienda) y no tiene repartidor asignado",
        id_venta, "/ventas/domicilios",
    )
    notificar(
        db, "pedido_confirmado", f"Tu pedido #{id_venta} ahora es a domicilio",
        f"Se agregó el costo de envío (${costo:,.0f}) a tu saldo pendiente.",
        id_venta, "/cliente/pedidos",
    )

    db.commit()
    db.refresh(pedido)
    return _formato_venta(pedido, db)


# ── 3.11: avisos de despacho (no cambian de estado) ────────────────────────
def avisar_puede_recoger(db: Session, id_venta: int) -> dict:
    """Avisa al cliente que su pedido está listo para recoger en tienda.
    No cambia de estado: reusa `notificar()`, no duplica el mecanismo."""
    from src.shared.services.notificaciones_utils import notificar

    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.Estado != EstadoPedido.LISTO or db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first():
        raise HTTPException(status_code=400, detail="Este pedido no está listo para recoger en tienda")

    notificar(
        db, "pedido_confirmado", f"¡Tu pedido #{id_venta} está listo!",
        "Ya puedes pasar a recogerlo en tienda.",
        id_venta, "/cliente/pedidos",
    )
    db.commit()
    return _formato_venta(pedido, db)


def avisar_enviar_a_entregar(db: Session, id_venta: int) -> dict:
    """Avisa al domiciliario asignado que salga a entregar. No cambia de
    estado: el domiciliario marca 'En camino' desde su propio panel al salir
    (mismo mecanismo de siempre, no se duplica acá)."""
    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.Estado != EstadoPedido.LISTO:
        raise HTTPException(status_code=400, detail="Este pedido no está listo para despachar")

    dom = db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first()
    if not dom or not dom.ID_Empleado:
        raise HTTPException(status_code=400, detail="Este pedido no tiene domiciliario asignado")

    try:
        from src.shared.services.fcm_service import notificar_asignacion_domicilio_push
        notificar_asignacion_domicilio_push(dom.ID_Empleado, id_venta, dom.Direccion_entrega or "", db=db)
    except Exception:
        pass

    db.commit()
    return _formato_venta(pedido, db)


def cancelar_retenido_en_tienda(db: Session, id_venta: int) -> dict:
    """Cancelación definitiva desde 'Retenido en tienda' (por falta de pago:
    el cajero la sugiere a partir de las 24h, y es obligatoria a las 48h).
    Reusa cambiar_estado→CANCELADO: la misma cascada de reversión de stock,
    OPs y crédito que cualquier otra cancelación, sin duplicarla acá."""
    pedido = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    _exigir_retenido_en_tienda(pedido)
    return _gv_cambiar_estado(db, id_venta, EstadoPedido.CANCELADO, saltar_ventana_proteccion=True)
