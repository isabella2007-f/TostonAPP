import re
import logging
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.shared.services.models import (
    Domicilio, Venta, Usuario, Estado, Producto, ProductoImagen,
    VentaXProducto, Rol, MensajeChat, OrdenProduccion,
    Barrio,
)
from src.shared.services.notificaciones_utils import notificar, notificar_stock_producto
from src.features.ventas.gestion_ventas.services.service import (
    _actualizar_estado_producto, _descontar_fefo_producto, _descontar_stock_venta,
    _faltantes_sin_cubrir,
    cambiar_estado as _cambiar_estado_venta,
)
from src.shared.services.observaciones_utils import observaciones_limpias
from src.shared.services.pagos_utils import (
    cobro_efectivo_pendiente, es_pago_efectivo, es_pago_mixto,
    saldo_final_pendiente,
)
from .estados import (
    EstadoDomicilio, ESTADO_DOM_A_VENTA, normalizar_estado, puede_reasignarse,
    validar_cambio,
)
from .schemas import DomicilioCreate, DomicilioUpdate

logger = logging.getLogger(__name__)

_BOGOTA = ZoneInfo("America/Bogota")


def _now():
    """Hora actual en Colombia (naive), consistente con gestion_ventas."""
    return datetime.now(_BOGOTA).replace(tzinfo=None)


def _imagen_producto(db: Session, id_producto: int) -> str | None:
    """URL de la primera imagen del producto (o None). Reutiliza Producto_Imagenes."""
    img = db.query(ProductoImagen).filter(
        ProductoImagen.ID_Producto == id_producto
    ).first()
    return img.imagen if img else None


def _label_estado(db: Session, id_estado: int) -> str:
    estado = db.query(Estado).filter(Estado.ID_Estados == id_estado).first()
    return estado.Estado if estado else None


def _formato_domicilio(dom: Domicilio, db: Session) -> dict:
    """Construye el dict con cliente, repartidor, estado y datos de la venta."""
    # Obtiene el cliente desde la venta
    venta   = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).first()
    cliente = db.query(Usuario).filter(
        Usuario.ID_Usuario == venta.ID_Usuario
    ).first() if venta else None

    # Obtiene el repartidor (ahora en la tabla Usuarios)
    repartidor = db.query(Usuario).filter(
        Usuario.ID_Usuario == dom.ID_Empleado
    ).first() if dom.ID_Empleado else None

    # Datos de la venta: total, metodo_pago y productos
    total       = float(venta.Total) if venta and venta.Total else 0.0
    metodo_pago = venta.Metodo_Pago or "" if venta else ""
    # Pago mixto: lo que hay que cobrar en mano no es el total.
    monto_efectivo = (
        float(venta.Monto_Efectivo)
        if venta and venta.Monto_Efectivo is not None else None
    )
    productos   = []
    if venta:
        items = db.query(VentaXProducto).filter(
            VentaXProducto.ID_Venta == venta.ID_Venta
        ).all()
        for item in items:
            prod   = db.query(Producto).filter(
                Producto.ID_Producto == item.ID_Producto
            ).first()
            precio = float(prod.Precio_venta) if prod and prod.Precio_venta else 0.0
            productos.append({
                "ID_Producto":     item.ID_Producto,
                "nombre_producto": prod.nombre if prod else "",
                "Cantidad":        item.Cantidad,
                "precio_unitario": precio,
                "subtotal":        precio * (item.Cantidad or 0),
                "imagen":          _imagen_producto(db, item.ID_Producto),
            })

    # El estado se normaliza al leer: las filas escritas por versiones viejas de
    # la app móvil traen otra numeración (ver estados.py).
    estado_canonico = normalizar_estado(dom.Estado, tiene_repartidor=bool(dom.ID_Empleado))

    return {
        "ID_Domicilio":         dom.ID_Domicilio,
        "ID_Venta":             dom.ID_Venta,
        "nombre_cliente":       f"{cliente.Nombre} {cliente.Apellidos}" if cliente else None,
        "ID_Empleado":          dom.ID_Empleado,
        "nombre_repartidor":    f"{repartidor.Nombre} {repartidor.Apellidos}" if repartidor else None,
        "Fecha_asignacion":     dom.Fecha_asignacion,
        "Fecha_entrega":        dom.Fecha_entrega,
        "Observaciones":        observaciones_limpias(dom.Observaciones),
        # Indicaciones de entrega tomadas del perfil del cliente (Usuarios.Indicaciones),
        # que es donde el cliente las registra. Separado de Observaciones (nota por-entrega).
        "indicaciones_cliente": cliente.Indicaciones if cliente else None,
        "Estado":               estado_canonico,
        "estado_label":         _label_estado(db, estado_canonico) if estado_canonico else None,
        "venta_estado":         venta.Estado if venta else None,
        "Direccion_entrega":    dom.Direccion_entrega,
        "Municipio_entrega":    dom.Municipio_entrega,
        "Departamento_entrega": dom.Departamento_entrega,
        # Snapshot del precio del domicilio (barrio + ofertas del día), congelado.
        "ID_Barrio":              dom.ID_Barrio,
        "barrio_entrega":         dom.barrio.Nombre if dom.barrio else None,
        "precio_domicilio_base":  dom.Precio_Domicilio_Base,
        "precio_domicilio_final": dom.Precio_Domicilio_Final,
        "desglose_domicilio":     dom.Desglose_Ofertas,
        "total":                total,
        "metodo_pago":          metodo_pago,
        "monto_efectivo":       monto_efectivo,
        "comprobante_pago":     venta.Comprobante_Pago if venta else None,
        "estado_pago":          venta.Estado_Pago if venta else None,
        "productos":            productos,
        "telefono_cliente":     cliente.Telefono if cliente else "",
        # Liquidación del efectivo cobrado por el repartidor
        "efectivo_liquidado":   bool(getattr(dom, "Efectivo_Liquidado", 0)),
        "fecha_liquidacion":    getattr(dom, "Fecha_Liquidacion", None),
        "id_liquidado_por":     getattr(dom, "ID_Liquidado_Por", None),
    }


# La fecha por la que un domicilio cae en un día u otro.
#
# `Fecha_asignacion` es, pese al nombre, la fecha en que se CREÓ el domicilio:
# nadie la toca al asignarle repartidor. Filtrando por ella, el historial del
# repartidor perdía justo las entregas que le importan —la que cerró hoy de un
# pedido de ayer no aparecía en "Hoy"— y su panel se contradecía solo: el
# resumen decía 2 entregas hoy y el historial le mostraba 1.
#
# Un domicilio cerrado pertenece al día en que se entregó; uno abierto, al día
# en que entró. Es la misma regla que ya usaba la app móvil por su cuenta.
FECHA_DEL_DOMICILIO = func.coalesce(Domicilio.Fecha_entrega, Domicilio.Fecha_asignacion)


def obtener_repartidores(db: Session) -> list:
    """Usuarios cuyo rol contiene 'domiciliario'."""
    repartidores = (
        db.query(Usuario)
        .join(Rol, Usuario.ID_Rol == Rol.ID_Rol)
        .filter(Rol.Rol.ilike("%domiciliario%"))
        .all()
    )
    return [
        {"id": u.ID_Usuario, "nombre": f"{u.Nombre} {u.Apellidos}"}
        for u in repartidores
    ]


# Estados canónicos del domicilio (ver estados.py). Antes se contaba el 13,
# que es "En producción" del PEDIDO y no un estado de domicilio, y las
# entregas solo miraban el 8, dejando fuera el 4 que escribían las versiones
# viejas de la app móvil: el repartidor veía menos entregas de las hechas.
ESTADOS_ACTIVOS = [
    int(EstadoDomicilio.PENDIENTE),
    int(EstadoDomicilio.ASIGNADO),
    int(EstadoDomicilio.EN_CAMINO),
]
ESTADOS_ENTREGADOS = [int(EstadoDomicilio.ENTREGADO), 4]


def obtener_resumen_dia(db: Session, id_empleado: int) -> dict:
    """Lo que el repartidor hizo hoy.

    `total_hoy` contaba los domicilios CREADOS hoy, que no es nada que al
    repartidor le sirva: quedaba al lado de "Entregados hoy" bajo una etiqueta
    que promete plata ("Total del día") y mostraba otro conteo. Ahora es lo que
    dice ser: los pesos que movió en las entregas que cerró hoy.

    `efectivo_hoy` es la parte de eso que recibió en mano —en un mixto, solo la
    mitad en efectivo—, que es la plata que tiene encima y de la que responde.
    """
    hoy_inicio = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    hoy_fin    = hoy_inicio + timedelta(days=1)

    base = db.query(Domicilio).filter(Domicilio.ID_Empleado == id_empleado)

    activos = base.filter(Domicilio.Estado.in_(ESTADOS_ACTIVOS)).count()

    entregas_hoy = base.filter(
        Domicilio.Estado.in_(ESTADOS_ENTREGADOS),
        Domicilio.Fecha_entrega >= hoy_inicio,
        Domicilio.Fecha_entrega < hoy_fin,
    ).all()

    total_hoy    = Decimal("0")
    efectivo_hoy = Decimal("0")
    ventas = _ventas_de(db, entregas_hoy)
    for dom in entregas_hoy:
        venta = ventas.get(dom.ID_Venta)
        if not venta:
            continue
        total_hoy    += Decimal(str(venta.Total or 0))
        efectivo_hoy += _cobrado_en_mano(venta)

    return {
        "activos":        activos,
        "entregados_hoy": len(entregas_hoy),
        "total_hoy":      float(total_hoy),
        "efectivo_hoy":   float(efectivo_hoy),
    }


def _ventas_de(db: Session, domicilios: list) -> dict:
    """Las ventas de esos domicilios, en una sola consulta."""
    ids = [d.ID_Venta for d in domicilios if d.ID_Venta]
    if not ids:
        return {}
    return {v.ID_Venta: v for v in db.query(Venta).filter(Venta.ID_Venta.in_(ids)).all()}


def _cobrado_en_mano(venta) -> Decimal:
    """Cuánta plata de esta venta pasó por las manos del repartidor.

    En un pedido mixto solo la parte en efectivo: el resto se transfirió antes
    de que el repartidor saliera. Y si quedó registrado que NO se pudo cobrar,
    no cuenta: no la tiene.
    """
    if (getattr(venta, "Estado_Pago", None) or "").strip() == "no_recibido":
        return Decimal("0")
    if not es_pago_efectivo(venta.Metodo_Pago):
        return Decimal("0")
    if es_pago_mixto(venta.Metodo_Pago):
        return Decimal(str(getattr(venta, "Monto_Efectivo", None) or 0))
    return Decimal(str(venta.Total or 0))


def obtener_domicilios(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None,
    estado: int = None,
    id_empleado: int = None,
    fecha_inicio: datetime = None,
    fecha_fin: datetime = None,
) -> dict:
    """Lista paginada. Busca por nombre de cliente o repartidor. Filtra por estado o empleado asignado."""
    query = db.query(Domicilio)

    if id_empleado:
        query = query.filter(Domicilio.ID_Empleado == id_empleado)

    if estado:
        query = query.filter(Domicilio.Estado == estado)

    # Ver FECHA_DEL_DOMICILIO: el rango se mide contra el día al que el
    # domicilio pertenece de verdad, no contra el día en que se creó.
    if fecha_inicio:
        query = query.filter(FECHA_DEL_DOMICILIO >= fecha_inicio)

    if fecha_fin:
        query = query.filter(FECHA_DEL_DOMICILIO < fecha_fin)

    if busqueda:
        termino = f"%{busqueda}%"

        # IDs de clientes que coinciden
        clientes_ids = (
            db.query(Venta.ID_Venta)
            .join(Usuario, Usuario.ID_Usuario == Venta.ID_Usuario)
            .filter(
                Usuario.Nombre.ilike(termino) |
                Usuario.Apellidos.ilike(termino)
            )
            .subquery()
        )

        # IDs de repartidores que coinciden (en Usuarios)
        repartidores_ids = (
            db.query(Usuario.ID_Usuario)
            .filter(
                Usuario.Nombre.ilike(termino) |
                Usuario.Apellidos.ilike(termino)
            )
            .subquery()
        )

        query = query.filter(
            Domicilio.ID_Venta.in_(clientes_ids) |
            Domicilio.ID_Empleado.in_(repartidores_ids) |
            Domicilio.Direccion_entrega.ilike(termino)
        )

    total      = query.count()
    offset     = (pagina - 1) * por_pagina
    domicilios = query.order_by(FECHA_DEL_DOMICILIO.desc()).offset(offset).limit(por_pagina).all()

    if not domicilios:
        return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "domicilios": []}

    venta_ids = list({d.ID_Venta for d in domicilios if d.ID_Venta})
    emp_ids   = list({d.ID_Empleado for d in domicilios if d.ID_Empleado})

    # Batch 1: ventas
    ventas_map = {v.ID_Venta: v for v in
                  db.query(Venta).filter(Venta.ID_Venta.in_(venta_ids)).all()} if venta_ids else {}

    # Batch 2: clientes (desde las ventas)
    cli_ids  = list({v.ID_Usuario for v in ventas_map.values() if v.ID_Usuario})
    todos_emp_ids = list(set(cli_ids) | set(emp_ids))
    usuarios_map = {u.ID_Usuario: u for u in
                    db.query(Usuario).filter(Usuario.ID_Usuario.in_(todos_emp_ids)).all()} if todos_emp_ids else {}

    # Batch 3: Estados
    estado_ids = list({d.Estado for d in domicilios if d.Estado})
    estados_map = {e.ID_Estados: e for e in
                   db.query(Estado).filter(Estado.ID_Estados.in_(estado_ids)).all()} if estado_ids else {}

    # Batch 4: VentaXProducto agrupado por venta
    vxp_all = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta.in_(venta_ids)).all() if venta_ids else []
    vxp_by_venta: dict = {}
    prod_ids: set = set()
    for vxp in vxp_all:
        vxp_by_venta.setdefault(vxp.ID_Venta, []).append(vxp)
        if vxp.ID_Producto:
            prod_ids.add(vxp.ID_Producto)

    # Batch 5: productos e imágenes
    productos_map: dict = {}
    imagenes_map:  dict = {}
    if prod_ids:
        for p in db.query(Producto).filter(Producto.ID_Producto.in_(list(prod_ids))).all():
            productos_map[p.ID_Producto] = p
        for img in db.query(ProductoImagen).filter(ProductoImagen.ID_Producto.in_(list(prod_ids))).all():
            if img.ID_Producto not in imagenes_map:
                imagenes_map[img.ID_Producto] = img.imagen

    # Batch 6: nombre del barrio del snapshot (solo el nombre; el precio ya está
    # congelado en cada Domicilio).
    barrio_ids = list({d.ID_Barrio for d in domicilios if d.ID_Barrio})
    barrios_map = {b.ID_Barrio: b.Nombre for b in
                   db.query(Barrio).filter(Barrio.ID_Barrio.in_(barrio_ids)).all()} if barrio_ids else {}

    def _build_domicilio(dom: Domicilio) -> dict:
        venta      = ventas_map.get(dom.ID_Venta)
        cliente    = usuarios_map.get(venta.ID_Usuario) if venta else None
        repartidor = usuarios_map.get(dom.ID_Empleado)  if dom.ID_Empleado else None
        # Igual que en _formato_domicilio: se normaliza el estado leído.
        estado_canonico = normalizar_estado(
            dom.Estado, tiene_repartidor=bool(dom.ID_Empleado)
        )
        estado_obj = estados_map.get(estado_canonico)

        total_v    = float(venta.Total) if venta and venta.Total else 0.0
        metodo     = venta.Metodo_Pago or "" if venta else ""
        monto_efec = (
            float(venta.Monto_Efectivo)
            if venta and venta.Monto_Efectivo is not None else None
        )

        prods = []
        if venta:
            for item in vxp_by_venta.get(venta.ID_Venta, []):
                prod   = productos_map.get(item.ID_Producto)
                precio = float(prod.Precio_venta) if prod and prod.Precio_venta else 0.0
                prods.append({
                    "ID_Producto":     item.ID_Producto,
                    "nombre_producto": prod.nombre if prod else "",
                    "Cantidad":        item.Cantidad,
                    "precio_unitario": precio,
                    "subtotal":        precio * (item.Cantidad or 0),
                    "imagen":          imagenes_map.get(item.ID_Producto),
                })

        return {
            "ID_Domicilio":         dom.ID_Domicilio,
            "ID_Venta":             dom.ID_Venta,
            "nombre_cliente":       f"{cliente.Nombre} {cliente.Apellidos}" if cliente else None,
            "ID_Empleado":          dom.ID_Empleado,
            "nombre_repartidor":    f"{repartidor.Nombre} {repartidor.Apellidos}" if repartidor else None,
            "Fecha_asignacion":     dom.Fecha_asignacion,
            "Fecha_entrega":        dom.Fecha_entrega,
            "Observaciones":        observaciones_limpias(dom.Observaciones),
            "indicaciones_cliente": cliente.Indicaciones if cliente else None,
            "Estado":               estado_canonico,
            "estado_label":         estado_obj.Estado if estado_obj else None,
            "venta_estado":         venta.Estado if venta else None,
            "Direccion_entrega":    dom.Direccion_entrega,
            "Municipio_entrega":    dom.Municipio_entrega,
            "Departamento_entrega": dom.Departamento_entrega,
            "ID_Barrio":              dom.ID_Barrio,
            "barrio_entrega":         barrios_map.get(dom.ID_Barrio),
            "precio_domicilio_base":  dom.Precio_Domicilio_Base,
            "precio_domicilio_final": dom.Precio_Domicilio_Final,
            "desglose_domicilio":     dom.Desglose_Ofertas,
            "total":                total_v,
            "metodo_pago":          metodo,
            "monto_efectivo":       monto_efec,
            # El listado se había quedado sin estado_pago mientras el detalle sí
            # lo devolvía: la tabla de Gestión de domicilios lo leía como
            # "sin cobrar" aunque el cobro estuviera registrado, así que no
            # dejaba marcar la entrega.
            "estado_pago":          venta.Estado_Pago if venta else None,
            "comprobante_pago":     venta.Comprobante_Pago if venta else None,
            "productos":            prods,
            "telefono_cliente":     cliente.Telefono if cliente else "",
        }

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "domicilios": [_build_domicilio(d) for d in domicilios],
    }


def obtener_domicilio(db: Session, id_domicilio: int) -> dict:
    dom = db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first()
    if not dom:
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")
    return _formato_domicilio(dom, db)


def _avisar_asignacion(db: Session, dom: Domicilio) -> None:
    """Avisa la asignación de un domicilio a su repartidor.

    - Push en tiempo real al celular del domiciliario. Es la ÚNICA notificación
      push que recibe: no le llegan las del panel (stock, pedidos nuevos,
      devoluciones...).
    - Notificación en el panel para que quede registrada la asignación (el
      repartidor solo ve en su lista las de sus propios domicilios).

    Best-effort: si Firebase falla, la asignación igual queda hecha."""
    try:
        from src.shared.services.fcm_service import notificar_asignacion_domicilio_push
        direccion = ", ".join(
            p for p in [dom.Direccion_entrega, dom.Municipio_entrega] if p
        )
        notificar_asignacion_domicilio_push(
            id_empleado = dom.ID_Empleado,
            id_venta    = dom.ID_Venta,
            direccion   = direccion,
            db          = db,
        )

        repartidor = db.query(Usuario).filter(
            Usuario.ID_Usuario == dom.ID_Empleado
        ).first()
        nombre = f"{repartidor.Nombre} {repartidor.Apellidos}" if repartidor else "un repartidor"
        notificar(
            db, "domicilio_asignado", "Domicilio asignado",
            f"El pedido #{dom.ID_Venta} fue asignado a {nombre}",
            dom.ID_Venta, "/ventas/domicilios",
        )

        # Y al cliente, que es quien va a abrirle la puerta. Era la única
        # novedad de su pedido que no recibía.
        from src.shared.services.fcm_service import (
            notificar_repartidor_asignado_push,
        )
        venta = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).first()
        if venta is not None:
            notificar_repartidor_asignado_push(
                id_usuario_cliente = venta.ID_Usuario,
                id_venta           = dom.ID_Venta,
                repartidor         = nombre,
                db                 = db,
            )
        db.commit()
    except Exception as e:
        logger.error(f"FCM: no se pudo avisar la asignación del domicilio {dom.ID_Domicilio}: {e}")


def crear_domicilio(db: Session, datos: DomicilioCreate) -> dict:
    """Crea un domicilio. Si viene ID_Empleado el estado es Asignado, si no Pendiente."""
    venta = db.query(Venta).filter(Venta.ID_Venta == datos.ID_Venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == venta.ID_Usuario).first()
    if not cliente or not cliente.Telefono:
        raise HTTPException(
            status_code=400,
            detail="El cliente debe tener un número de teléfono registrado para recibir domicilios"
        )

    if datos.ID_Empleado:
        if not db.query(Usuario).filter(Usuario.ID_Usuario == datos.ID_Empleado).first():
            raise HTTPException(status_code=404, detail="Repartidor no encontrado")

    # Estado inicial según si viene repartidor o no (numeración canónica)
    estado_inicial = (
        EstadoDomicilio.ASIGNADO if datos.ID_Empleado else EstadoDomicilio.PENDIENTE
    )

    nuevo = Domicilio(
        ID_Venta             = datos.ID_Venta,
        ID_Empleado          = datos.ID_Empleado,
        Fecha_asignacion     = datetime.now(),
        Fecha_entrega        = datos.Fecha_entrega,
        Observaciones        = datos.Observaciones,
        Estado               = estado_inicial,
        Direccion_entrega    = datos.Direccion_entrega,
        Municipio_entrega    = datos.Municipio_entrega,
        Departamento_entrega = datos.Departamento_entrega,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    # Si nace con repartidor, avisarle al instante en su celular.
    if nuevo.ID_Empleado:
        _avisar_asignacion(db, nuevo)
    return _formato_domicilio(nuevo, db)


def editar_domicilio(db: Session, id_domicilio: int, datos: DomicilioUpdate) -> dict:
    dom = db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first()
    if not dom:
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")

    for campo, valor in datos.model_dump(exclude_none=True).items():
        setattr(dom, campo, valor)

    db.commit()
    db.refresh(dom)
    return _formato_domicilio(dom, db)


def asignar_repartidor(db: Session, id_domicilio: int, id_empleado: int) -> dict:
    """
    Asigna un repartidor al domicilio.
    Si estaba Pendiente, cambia automáticamente a Asignado.
    """
    dom = db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first()
    if not dom:
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")

    if not db.query(Usuario).filter(Usuario.ID_Usuario == id_empleado).first():
        raise HTTPException(status_code=404, detail="Repartidor no encontrado")

    cambia_repartidor = dom.ID_Empleado != id_empleado
    # Un domicilio pendiente pasa a Asignado al recibir repartidor. Si ya venía
    # en camino o entregado, la reasignación no lo hace retroceder.
    estado_previo = normalizar_estado(dom.Estado, tiene_repartidor=bool(dom.ID_Empleado))

    # Con el pedido ya en la calle, cambiarle el domiciliario deja al que salió
    # cargando algo que dejó de ser suyo. La regla vive acá y no solo en la
    # pantalla: la app móvil llama al mismo endpoint.
    if cambia_repartidor and not puede_reasignarse(estado_previo):
        raise HTTPException(
            status_code=400,
            detail=(
                "El domicilio ya va en camino: no se puede cambiar de domiciliario"
                if estado_previo == EstadoDomicilio.EN_CAMINO
                else "El domicilio ya está cerrado: no se puede cambiar de domiciliario"
            ),
        )

    try:
        dom.ID_Empleado = id_empleado
        if estado_previo == EstadoDomicilio.PENDIENTE:
            dom.Estado = int(EstadoDomicilio.ASIGNADO)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error asignando repartidor a domicilio {id_domicilio}: {e}")
        raise HTTPException(status_code=500, detail="Error al asignar el repartidor")

    # Aviso al celular del repartidor solo cuando la asignación es nueva.
    if cambia_repartidor:
        _avisar_asignacion(db, dom)

    try:
        db.refresh(dom)
        return _formato_domicilio(dom, db)
    except Exception as e:
        logger.error(f"Error formateando domicilio {id_domicilio} tras asignación: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar la respuesta")


def obtener_mensajes(db: Session, id_domicilio: int) -> list:
    """Lee el historial de chat desde BD."""
    msgs = (
        db.query(MensajeChat)
        .filter(MensajeChat.ID_Domicilio == id_domicilio)
        .order_by(MensajeChat.Fecha)
        .all()
    )
    return [
        {
            "ID_Mensaje":       m.ID_Mensaje,
            "ID_Domicilio":     m.ID_Domicilio,
            "Tipo_Remitente":   m.Tipo_Remitente,
            "ID_Remitente":     m.ID_Remitente,
            "Nombre_Remitente": m.Nombre_Remitente,
            "Contenido":        m.Contenido,
            "Fecha":            m.Fecha,
        }
        for m in msgs
    ]


def enviar_mensaje(
    db: Session,
    id_domicilio: int,
    contenido: str,
    tipo_remitente: str,
    id_remitente: int,
    nombre_remitente: str = None,
) -> dict:
    if not db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first():
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")

    nuevo = MensajeChat(
        ID_Domicilio     = id_domicilio,
        Tipo_Remitente   = tipo_remitente,
        ID_Remitente     = id_remitente,
        Nombre_Remitente = nombre_remitente,
        Contenido        = contenido.strip(),
        Fecha            = datetime.now(),
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {
        "ID_Mensaje":       nuevo.ID_Mensaje,
        "ID_Domicilio":     nuevo.ID_Domicilio,
        "Tipo_Remitente":   nuevo.Tipo_Remitente,
        "ID_Remitente":     nuevo.ID_Remitente,
        "Nombre_Remitente": nuevo.Nombre_Remitente,
        "Contenido":        nuevo.Contenido,
        "Fecha":            nuevo.Fecha,
    }


def cambiar_estado(db: Session, id_domicilio: int, nuevo_estado: int, observaciones: str = None) -> dict:
    """Cambia el estado del domicilio y lo refleja en la venta.

    El estado que llega se normaliza a la numeración canónica de la tabla
    `Estados` (ver estados.py), de modo que web y app móvil —incluidas versiones
    viejas que aún envían su propio numerado— acaben escribiendo lo mismo.
    """
    dom = db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first()
    if not dom:
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")

    tiene_repartidor = bool(dom.ID_Empleado)
    estado_actual = normalizar_estado(dom.Estado, tiene_repartidor=tiene_repartidor)
    # Al cambiar de estado, un 3 entrante significa "En camino" solo si venía de
    # una app vieja; con la numeración canónica 3 es Pendiente. Se resuelve con
    # el mismo criterio de lectura: si ya hay repartidor, es En camino.
    nuevo_estado = normalizar_estado(nuevo_estado, tiene_repartidor=tiene_repartidor)
    validar_cambio(estado_actual, nuevo_estado)

    _ESTADOS_PAGO_ENTREGA = {
        "efectivo_recibido", "pagado_completo", "anticipo_pagado",
        "no_recibido", "pendiente_validacion",
    }

    if nuevo_estado == EstadoDomicilio.EN_CAMINO and not dom.ID_Empleado:
        raise HTTPException(
            status_code=400,
            detail="Asigná un repartidor antes de marcar el domicilio como 'En camino'.",
        )

    if nuevo_estado in (EstadoDomicilio.EN_CAMINO, EstadoDomicilio.ENTREGADO) and dom.ID_Venta:
        ordenes_abiertas = db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == dom.ID_Venta,
            OrdenProduccion.Estado.notin_([11, 5]),
        ).count()
        if ordenes_abiertas > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "La producción de este pedido aún no está completada. "
                    "Completá la orden de producción antes de despacharlo."
                ),
            )
        faltantes = _faltantes_sin_cubrir(db, dom.ID_Venta, True)
        if faltantes:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Falta producto de {', '.join(faltantes)}: el pedido pidió más de lo "
                    "que había y ese faltante todavía no se fabricó ni se repuso."
                ),
            )

    # Validación de pago: aplica a todos los domicilios.
    # El pago nunca se divide — se revisa el estado del pedido completo.
    if nuevo_estado == EstadoDomicilio.ENTREGADO and dom.ID_Venta:
        venta_check = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).first()
        if venta_check:
            estado_pago = (getattr(venta_check, "Estado_Pago", None) or "pendiente").strip()
            if estado_pago not in _ESTADOS_PAGO_ENTREGA:
                raise HTTPException(
                    status_code=400,
                    detail="Debes registrar el cobro antes de marcar el pedido como entregado",
                )
            if cobro_efectivo_pendiente(venta_check):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Registrá el cobro en efectivo antes de entregar: este pedido "
                        "se paga (total o en parte) en mano."
                    ),
                )
            # El anticipo es la mitad: cubre los insumos, no el pedido. Con
            # solo esa mitad registrada se estaría entregando la mercancía y
            # quedándose esperando el resto.
            if saldo_final_pendiente(venta_check):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Falta cobrar el saldo de este pedido: solo entró el anticipo. "
                        "Registrá el pago final antes de entregar."
                    ),
                )

    if nuevo_estado == EstadoDomicilio.ENTREGADO:
        entregado_en = _now()
        dom.Fecha_entrega = entregado_en
        # Espeja el timestamp de entrega en la venta (fuente única para el plazo
        # de devoluciones, también en pedidos de recoger en tienda).
        if dom.ID_Venta:
            _venta_fe = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).first()
            if _venta_fe and not _venta_fe.Fecha_entrega:
                _venta_fe.Fecha_entrega = entregado_en

    if nuevo_estado in ESTADO_DOM_A_VENTA and dom.ID_Venta:
        # Propagar a la Venta. "Asignado" no la mueve: el pedido sigue Listo.
        venta = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).with_for_update().first()
        if venta:
            nuevo_estado_venta = ESTADO_DOM_A_VENTA[nuevo_estado]
            # Al entregar: descontar stock si aún no se había entregado.
            # with_for_update() en venta garantiza que dos requests concurrentes
            # no descuenten el stock dos veces (el segundo ve Estado==8 y no entra).
            if nuevo_estado_venta == 5 and venta.Estado != 5:
                # Cancelar desde el panel de reparto es cancelar el pedido
                # entero, y eso significa devolverle al cliente lo que puso: el
                # saldo a favor que gastó y el stock que se le había reservado.
                # Escribiendo el estado a mano, el mismo pedido cancelado desde
                # acá le costaba la plata al cliente y cancelado desde Gestión de
                # pedidos se la devolvía. Ahora los dos caminos hacen lo mismo.
                _cambiar_estado_venta(db, dom.ID_Venta, nuevo_estado_venta)
            elif nuevo_estado_venta == 8 and venta.Estado != 8:
                # El mismo descuento que hace gestion_ventas al entregar. Antes
                # este modulo lo repetia linea por linea, asi que cualquier
                # arreglo alla habia que acordarse de copiarlo aca.
                _descontar_stock_venta(db, dom.ID_Venta)
            venta.Estado = nuevo_estado_venta

    dom.Estado = nuevo_estado

    if observaciones is not None:
        dom.Observaciones = observaciones

    db.commit()
    db.refresh(dom)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        if dom.ID_Venta:
            venta_dom = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).first()
            if venta_dom:
                db_estado = ESTADO_DOM_A_VENTA.get(nuevo_estado, nuevo_estado)
                notificar_cambio_pedido_push(
                    id_usuario_cliente=venta_dom.ID_Usuario,
                    id_venta=dom.ID_Venta,
                    nuevo_estado=db_estado,
                    db=db,
                )
    except Exception:
        pass
    return _formato_domicilio(dom, db)


def registrar_pago_efectivo(
    db: Session,
    id_domicilio: int,
    datos,          # RegistroPagoEfectivo
    id_usuario_actual: int,
) -> dict:
    """
    Registra el cobro en efectivo hecho por el domiciliario.
    - recibido=True: monto obligatorio, debe coincidir exactamente con el total de la venta.
    - recibido=False: motivo obligatorio (≥10 chars). Estado_Pago → 'no_recibido'.
    - Idempotencia: si ya está 'efectivo_recibido' o 'no_recibido' → 409.
    - Auditoría: línea estructurada en Domicilio.Observaciones.
    """
    dom = db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first()
    if not dom:
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")

    if not dom.ID_Venta:
        raise HTTPException(status_code=400, detail="Este domicilio no tiene venta asociada")

    venta = db.query(Venta).filter(Venta.ID_Venta == dom.ID_Venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta asociada no encontrada")

    _metodo = (venta.Metodo_Pago or "").strip().lower()
    _pago_mixto = "mixto" in _metodo
    if "efectivo" not in _metodo and "contra entrega" not in _metodo and not _pago_mixto:
        raise HTTPException(
            status_code=400,
            detail="Este endpoint solo aplica a pedidos con método de pago Efectivo, Contra entrega o Mixto",
        )

    estado_pago_actual = (getattr(venta, "Estado_Pago", None) or "pendiente").strip()
    if estado_pago_actual in ("efectivo_recibido", "no_recibido", "pagado_completo"):
        raise HTTPException(
            status_code=409,
            detail=f"El cobro ya fue registrado (estado_pago='{estado_pago_actual}')",
        )

    if datos.recibido:
        if datos.monto is None:
            raise HTTPException(status_code=422, detail="El monto es obligatorio cuando recibido=true")
        # En un pedido mixto solo se cobra en mano la parte en efectivo; el
        # resto ya entró por transferencia al hacer el pedido.
        esperado = float(
            venta.Monto_Efectivo if _pago_mixto and venta.Monto_Efectivo is not None
            else (venta.Total or 0)
        )
        if round(datos.monto, 2) != round(esperado, 2):
            raise HTTPException(
                status_code=400,
                detail=f"El monto recibido ({datos.monto}) no coincide con lo que hay que cobrar ({esperado})",
            )
        venta.Estado_Pago = "efectivo_recibido"
        audit_value = f"monto:{datos.monto}"
    else:
        if not datos.motivo or len(datos.motivo.strip()) < 10:
            raise HTTPException(
                status_code=422,
                detail="El motivo es obligatorio y debe tener al menos 10 caracteres cuando recibido=false",
            )
        venta.Estado_Pago = "no_recibido"
        audit_value = f"motivo:{datos.motivo.strip()}"

    ts = _now().strftime("%Y-%m-%dT%H:%M:%S")
    audit_line = (
        f"[COBRO|{ts}|usuario:{id_usuario_actual}"
        f"|recibido:{str(datos.recibido).lower()}|{audit_value}]"
    )
    # Va a su propio campo: Observaciones es lo que el cliente escribe sobre
    # la entrega, y mezclarle las líneas [COBRO|...] las volvía ilegibles.
    auditoria = dom.Cobro_Auditoria or ""
    dom.Cobro_Auditoria = f"{auditoria}\n{audit_line}".strip()

    db.commit()
    db.refresh(dom)
    return _formato_domicilio(dom, db)


def listar_efectivo_pendiente(db: Session) -> list[dict]:
    """Lista los domicilios donde el repartidor cobró efectivo y aún no se liquidó."""
    from sqlalchemy import or_
    doms = (
        db.query(Domicilio)
        .join(Venta, Venta.ID_Venta == Domicilio.ID_Venta)
        .filter(
            Domicilio.Efectivo_Liquidado.in_([0, None]),
            Domicilio.Estado == int(EstadoDomicilio.ENTREGADO),
            or_(
                Venta.Metodo_Pago.ilike("%efectivo%"),
                Venta.Metodo_Pago.ilike("%mixto%"),
            ),
        )
        .all()
    )
    return [_formato_domicilio(d, db) for d in doms]


def liquidar_efectivo(db: Session, id_domicilio: int, id_usuario_actual: int) -> dict:
    """Admin registra que el efectivo cobrado por el repartidor fue entregado."""
    dom = db.query(Domicilio).filter(Domicilio.ID_Domicilio == id_domicilio).first()
    if not dom:
        raise HTTPException(status_code=404, detail="Domicilio no encontrado")

    if int(getattr(dom, "Efectivo_Liquidado", 0) or 0) == 1:
        raise HTTPException(status_code=409, detail="Este domicilio ya fue liquidado")

    dom.Efectivo_Liquidado = 1
    dom.Fecha_Liquidacion  = _now()
    dom.ID_Liquidado_Por   = id_usuario_actual

    db.commit()
    db.refresh(dom)
    return _formato_domicilio(dom, db)
