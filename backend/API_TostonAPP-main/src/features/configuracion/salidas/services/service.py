from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from zoneinfo import ZoneInfo

from src.shared.services.models import Salida, Insumo, Producto, Usuario, Estado, CategoriaInsumo, CategoriaProducto, LoteCompra, LoteProducto, UnidadMedida
from src.shared.services.notificaciones_utils import notificar_stock_insumo, notificar_stock_producto
from src.shared.services.enums import TipoSalida
from .schemas import SalidaCreate

_BOGOTA = ZoneInfo("America/Bogota")

def _now():
    return datetime.now(_BOGOTA).replace(tzinfo=None)

ESTADO_ACTIVO  = 1
ESTADO_ANULADA = 12


# ─────────────────────────────────────────
# HELPERS DE STOCK
# ─────────────────────────────────────────

def _actualizar_estado_insumo(insumo: Insumo) -> None:
    stock   = insumo.Stock_Actual or 0
    minimo  = insumo.Stock_Minimo or 0
    if stock == 0:
        insumo.Estado = 15      # Agotado
    elif stock <= minimo:
        insumo.Estado = 14      # Stock bajo
    else:
        insumo.Estado = 1       # Activo


def _actualizar_estado_producto(producto: Producto) -> None:
    stock   = producto.Stock or 0
    minimo  = getattr(producto, "Stock_Minimo", 0) or 0
    if stock == 0:
        producto.Estado = 15    # Agotado
    elif stock <= minimo:
        producto.Estado = 14    # Stock bajo
    else:
        producto.Estado = 1     # Activo


# ─────────────────────────────────────────
# FORMATO DE RESPUESTA
# ─────────────────────────────────────────

def _formato_salida(salida: Salida, db: Session) -> dict:
    insumo   = db.query(Insumo).filter(Insumo.ID_Insumo == salida.ID_Insumo).first() \
               if salida.ID_Insumo else None
    producto = db.query(Producto).filter(Producto.ID_Producto == salida.ID_Producto).first() \
               if salida.ID_Producto else None
    empleado    = db.query(Usuario).filter(Usuario.ID_Usuario == salida.ID_Empleado).first() \
                  if salida.ID_Empleado else None
    anulado_por = db.query(Usuario).filter(Usuario.ID_Usuario == salida.ID_Anulado_Por).first() \
                  if getattr(salida, "ID_Anulado_Por", None) else None
    estado      = db.query(Estado).filter(Estado.ID_Estados == salida.Estado).first()

    cat_nombre = None
    if insumo and insumo.ID_Categoria:
        cat = db.query(CategoriaInsumo).filter(CategoriaInsumo.ID_Categoria == insumo.ID_Categoria).first()
        cat_nombre = cat.Nombre_Categoria if cat else None
    elif producto and producto.ID_Categoria:
        cat = db.query(CategoriaProducto).filter(CategoriaProducto.ID_Categoria == producto.ID_Categoria).first()
        cat_nombre = cat.Nombre_Categoria if cat else None

    simbolo_unidad = None
    if insumo and insumo.Unidad_Medida:
        um = db.query(UnidadMedida).filter(UnidadMedida.ID_Unidad_Medida == insumo.Unidad_Medida).first()
        simbolo_unidad = um.Simbolo if um else None

    return {
        "ID_Salida":          salida.ID_Salida,
        "Tipo":               salida.Tipo,
        "ID_Insumo":          salida.ID_Insumo,
        "nombre_insumo":      insumo.Nombre if insumo else None,
        "ID_Producto":        salida.ID_Producto,
        "nombre_producto":    producto.nombre if producto else None,
        "nombre_categoria":   cat_nombre,
        "simbolo_unidad":     simbolo_unidad,
        "Cantidad":           salida.Cantidad,
        "Motivo":             salida.Motivo,
        "ID_Empleado":        salida.ID_Empleado,
        "nombre_empleado":    f"{empleado.Nombre} {empleado.Apellidos}" if empleado else None,
        "Fecha":              salida.Fecha,
        "Estado":             salida.Estado,
        "estado_label":       estado.Estado if estado else None,
        "ID_Anulado_Por":     getattr(salida, "ID_Anulado_Por", None),
        "nombre_anulado_por": f"{anulado_por.Nombre} {anulado_por.Apellidos}" if anulado_por else None,
        "Fecha_Anulacion":    getattr(salida, "Fecha_Anulacion", None),
    }


# ─────────────────────────────────────────
# HELPERS FEFO DE LOTES
# ─────────────────────────────────────────

def _descontar_fefo_insumo(db: Session, id_insumo: int, cantidad: int) -> None:
    from sqlalchemy import case as _case
    restante = cantidad
    lotes = (
        db.query(LoteCompra)
        .filter(
            LoteCompra.ID_Insumo      == id_insumo,
            LoteCompra.Cantidad_Actual > 0,
            LoteCompra.Estado          == ESTADO_ACTIVO,
        )
        .order_by(
            _case((LoteCompra.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteCompra.Fecha_Vencimiento.asc(),
        )
        .all()
    )
    for lote in lotes:
        if restante <= 0:
            break
        disponible = float(lote.Cantidad_Actual or 0)
        descontar  = min(restante, disponible)
        lote.Cantidad_Actual = disponible - descontar
        restante -= descontar


def _descontar_fefo_producto(db: Session, id_producto: int, cantidad: int) -> None:
    from sqlalchemy import case as _case
    restante = cantidad
    lotes = (
        db.query(LoteProducto)
        .filter(
            LoteProducto.ID_Producto == id_producto,
            LoteProducto.Cantidad    >  0,
            LoteProducto.Estado      == ESTADO_ACTIVO,
        )
        .order_by(
            _case((LoteProducto.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteProducto.Fecha_Vencimiento.asc(),
        )
        .all()
    )
    for lote in lotes:
        if restante <= 0:
            break
        disponible = lote.Cantidad or 0
        descontar  = min(restante, disponible)
        lote.Cantidad = disponible - descontar
        restante -= descontar


def _restaurar_fefo_insumo(db: Session, id_insumo: int, cantidad: int) -> None:
    from sqlalchemy import case as _case
    restante = cantidad
    lotes = (
        db.query(LoteCompra)
        .filter(
            LoteCompra.ID_Insumo == id_insumo,
            LoteCompra.Estado    == ESTADO_ACTIVO,
        )
        .order_by(
            _case((LoteCompra.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteCompra.Fecha_Vencimiento.desc(),
        )
        .all()
    )
    for lote in lotes:
        if restante <= 0:
            break
        espacio = float(lote.Cantidad_Inicial or 0) - float(lote.Cantidad_Actual or 0)
        if espacio <= 0:
            continue
        reponer = min(restante, espacio)
        lote.Cantidad_Actual = float(lote.Cantidad_Actual or 0) + reponer
        restante -= reponer


def _restaurar_fefo_producto(db: Session, id_producto: int, cantidad: int) -> None:
    from sqlalchemy import case as _case
    restante = cantidad
    lotes = (
        db.query(LoteProducto)
        .filter(
            LoteProducto.ID_Producto == id_producto,
            LoteProducto.Estado      == ESTADO_ACTIVO,
        )
        .order_by(
            _case((LoteProducto.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteProducto.Fecha_Vencimiento.desc(),
        )
        .all()
    )
    for lote in lotes:
        if restante <= 0:
            break
        lote.Cantidad = (lote.Cantidad or 0) + restante
        restante = 0


# ─────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────

def obtener_salidas(
    db:          Session,
    pagina:      int  = 1,
    por_pagina:  int  = 10,
    busqueda:    str  = None,
    tipo:        str  = None,
    estado:      int  = None,
    fecha_desde: str  = None,
    fecha_hasta: str  = None,
    id_insumo:   int  = None,
    id_producto: int  = None,
) -> dict:
    query = db.query(Salida)

    if tipo:
        query = query.filter(Salida.Tipo == tipo)
    if estado is not None:
        query = query.filter(Salida.Estado == estado)
    if fecha_desde:
        query = query.filter(Salida.Fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Salida.Fecha <= fecha_hasta)
    if id_insumo:
        query = query.filter(Salida.ID_Insumo == id_insumo)
    if id_producto:
        query = query.filter(Salida.ID_Producto == id_producto)

    if busqueda:
        termino      = f"%{busqueda}%"
        ids_insumo   = db.query(Insumo.ID_Insumo).filter(Insumo.Nombre.ilike(termino)).subquery()
        ids_producto = db.query(Producto.ID_Producto).filter(Producto.nombre.ilike(termino)).subquery()
        query = query.filter(
            Salida.Motivo.ilike(termino)         |
            Salida.ID_Insumo.in_(ids_insumo)     |
            Salida.ID_Producto.in_(ids_producto)
        )

    total   = query.count()
    offset  = (pagina - 1) * por_pagina
    salidas = query.order_by(Salida.Fecha.desc()).offset(offset).limit(por_pagina).all()

    if not salidas:
        return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "salidas": []}

    insumo_ids  = list({s.ID_Insumo   for s in salidas if s.ID_Insumo})
    prod_ids    = list({s.ID_Producto  for s in salidas if s.ID_Producto})
    emp_ids     = list({s.ID_Empleado  for s in salidas if s.ID_Empleado})
    anulado_ids = list({getattr(s, "ID_Anulado_Por", None) for s in salidas if getattr(s, "ID_Anulado_Por", None)})
    estado_ids  = list({s.Estado for s in salidas if s.Estado})

    insumos_map  = {i.ID_Insumo:   i for i in db.query(Insumo).filter(Insumo.ID_Insumo.in_(insumo_ids)).all()}   if insumo_ids  else {}
    productos_map = {p.ID_Producto: p for p in db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()} if prod_ids    else {}
    usuarios_ids = list(set(emp_ids) | set(anulado_ids))
    usuarios_map = {u.ID_Usuario:  u for u in db.query(Usuario).filter(Usuario.ID_Usuario.in_(usuarios_ids)).all()} if usuarios_ids else {}
    estados_map  = {e.ID_Estados:  e for e in db.query(Estado).filter(Estado.ID_Estados.in_(estado_ids)).all()}     if estado_ids  else {}

    cat_insumo_ids  = list({i.ID_Categoria for i in insumos_map.values()  if i.ID_Categoria})
    cat_prod_ids    = list({p.ID_Categoria for p in productos_map.values() if p.ID_Categoria})
    cats_insumo_map = {c.ID_Categoria: c for c in db.query(CategoriaInsumo).filter(CategoriaInsumo.ID_Categoria.in_(cat_insumo_ids)).all()}   if cat_insumo_ids else {}
    cats_prod_map   = {c.ID_Categoria: c for c in db.query(CategoriaProducto).filter(CategoriaProducto.ID_Categoria.in_(cat_prod_ids)).all()} if cat_prod_ids   else {}

    def _build(s: Salida) -> dict:
        insumo   = insumos_map.get(s.ID_Insumo)
        producto = productos_map.get(s.ID_Producto)
        empleado = usuarios_map.get(s.ID_Empleado)
        anulado  = usuarios_map.get(getattr(s, "ID_Anulado_Por", None))
        estado   = estados_map.get(s.Estado)
        if insumo and insumo.ID_Categoria:
            cat = cats_insumo_map.get(insumo.ID_Categoria)
        elif producto and producto.ID_Categoria:
            cat = cats_prod_map.get(producto.ID_Categoria)
        else:
            cat = None
        return {
            "ID_Salida":          s.ID_Salida,
            "Tipo":               s.Tipo,
            "ID_Insumo":          s.ID_Insumo,
            "nombre_insumo":      insumo.Nombre   if insumo   else None,
            "ID_Producto":        s.ID_Producto,
            "nombre_producto":    producto.nombre if producto else None,
            "nombre_categoria":   cat.Nombre_Categoria if cat else None,
            "Cantidad":           s.Cantidad,
            "Motivo":             s.Motivo,
            "ID_Empleado":        s.ID_Empleado,
            "nombre_empleado":    f"{empleado.Nombre} {empleado.Apellidos}" if empleado else None,
            "Fecha":              s.Fecha,
            "Estado":             s.Estado,
            "estado_label":       estado.Estado if estado else None,
            "ID_Anulado_Por":     getattr(s, "ID_Anulado_Por", None),
            "nombre_anulado_por": f"{anulado.Nombre} {anulado.Apellidos}" if anulado else None,
            "Fecha_Anulacion":    getattr(s, "Fecha_Anulacion", None),
        }

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "salidas":    [_build(s) for s in salidas],
    }


def obtener_salida(db: Session, id_salida: int) -> dict:
    salida = db.query(Salida).filter(Salida.ID_Salida == id_salida).first()
    if not salida:
        raise HTTPException(status_code=404, detail="Salida no encontrada")
    return _formato_salida(salida, db)


def crear_salida(db: Session, datos: SalidaCreate) -> dict:
    """
    Registra la salida y descuenta el stock en una sola transacción.
    Las notificaciones se envían después del commit para no romper atomicidad.
    Excepción: tipo 'devolución' solo crea el registro (el stock ya fue descontado
    en la venta original; el producto devuelto no puede reintegrarse al inventario
    por ser comida).
    """
    es_devolucion = (datos.Tipo or "").lower() == "devolución"

    if datos.ID_Insumo:
        insumo = db.query(Insumo).filter(Insumo.ID_Insumo == datos.ID_Insumo).first()
        if not insumo:
            raise HTTPException(status_code=404, detail="Insumo no encontrado")
        if not es_devolucion:
            stock_disponible = insumo.Stock_Actual or 0
            if stock_disponible == 0:
                raise HTTPException(
                    status_code=400,
                    detail="No se puede registrar la salida. El producto no tiene stock disponible."
                )
            if stock_disponible < datos.Cantidad:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente. Solo hay {stock_disponible} unidades disponibles."
                )
            insumo.Stock_Actual -= datos.Cantidad
            _actualizar_estado_insumo(insumo)
            _descontar_fefo_insumo(db, datos.ID_Insumo, datos.Cantidad)

    else:
        producto = db.query(Producto).filter(Producto.ID_Producto == datos.ID_Producto).first()
        if not producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        if not es_devolucion:
            stock_disponible = producto.Stock or 0
            if stock_disponible == 0:
                raise HTTPException(
                    status_code=400,
                    detail="No se puede registrar la salida. El producto no tiene stock disponible."
                )
            if stock_disponible < datos.Cantidad:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente. Solo hay {stock_disponible} unidades disponibles."
                )
            producto.Stock -= datos.Cantidad
            _actualizar_estado_producto(producto)
            _descontar_fefo_producto(db, datos.ID_Producto, datos.Cantidad)

    nueva = Salida(
        Tipo        = datos.Tipo,
        ID_Insumo   = datos.ID_Insumo,
        ID_Producto = datos.ID_Producto,
        Cantidad    = datos.Cantidad,
        Motivo      = datos.Motivo,
        ID_Empleado = datos.ID_Empleado,
        Fecha       = datos.Fecha or _now(),
        Estado      = ESTADO_ACTIVO,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)

    # Notificaciones fuera de la transacción principal (solo si hubo cambio de stock)
    if not es_devolucion:
        if nueva.ID_Insumo:
            insumo = db.query(Insumo).filter(Insumo.ID_Insumo == nueva.ID_Insumo).first()
            if insumo:
                notificar_stock_insumo(db, insumo)
        else:
            producto = db.query(Producto).filter(Producto.ID_Producto == nueva.ID_Producto).first()
            if producto:
                notificar_stock_producto(db, producto)

    return _formato_salida(nueva, db)


def anular_salida(db: Session, id_salida: int, id_anulado_por: int = None) -> dict:
    """
    Anula la salida (Estado=12) y restaura el stock descontado.
    Excepción: tipo 'devolución' nunca modificó el stock, así que tampoco lo restaura.
    """
    salida = db.query(Salida).filter(Salida.ID_Salida == id_salida).first()
    if not salida:
        raise HTTPException(status_code=404, detail="Salida no encontrada")
    if salida.Estado == ESTADO_ANULADA:
        raise HTTPException(status_code=400, detail="Esta salida ya fue anulada")

    es_devolucion = (salida.Tipo or "").lower() == TipoSalida.DEVOLUCION

    if not es_devolucion:
        if salida.ID_Insumo:
            insumo = db.query(Insumo).filter(Insumo.ID_Insumo == salida.ID_Insumo).first()
            if insumo:
                insumo.Stock_Actual = (insumo.Stock_Actual or 0) + salida.Cantidad
                _actualizar_estado_insumo(insumo)
                _restaurar_fefo_insumo(db, salida.ID_Insumo, salida.Cantidad)
        else:
            producto = db.query(Producto).filter(Producto.ID_Producto == salida.ID_Producto).first()
            if producto:
                producto.Stock = (producto.Stock or 0) + salida.Cantidad
                _actualizar_estado_producto(producto)
                _restaurar_fefo_producto(db, salida.ID_Producto, salida.Cantidad)

    salida.Estado = ESTADO_ANULADA
    if id_anulado_por:
        salida.ID_Anulado_Por  = id_anulado_por
        salida.Fecha_Anulacion = _now()
    db.commit()
    db.refresh(salida)

    # Notificaciones fuera de la transacción principal (solo si hubo cambio de stock)
    if not es_devolucion:
        if salida.ID_Insumo:
            insumo = db.query(Insumo).filter(Insumo.ID_Insumo == salida.ID_Insumo).first()
            if insumo:
                notificar_stock_insumo(db, insumo)
        else:
            producto = db.query(Producto).filter(Producto.ID_Producto == salida.ID_Producto).first()
            if producto:
                notificar_stock_producto(db, producto)

    return _formato_salida(salida, db)


def procesar_lotes_vencidos(db: Session) -> dict:
    """
    Detecta lotes de insumos y productos vencidos, registra una salida por vencimiento
    y descuenta el stock correspondiente. Marca los lotes como Anulados (Estado=12)
    para que no se reprocesen en llamadas futuras.
    """
    ahora = _now()
    salidas_creadas = []
    insumos_afectados = set()
    productos_afectados = set()

    # ── Insumos ──────────────────────────────────────────────
    lotes_insumo = (
        db.query(LoteCompra)
        .filter(
            LoteCompra.Fecha_Vencimiento != None,
            LoteCompra.Fecha_Vencimiento < ahora,
            LoteCompra.Estado == ESTADO_ACTIVO,
        )
        .order_by(LoteCompra.Fecha_Vencimiento.asc())
        .all()
    )

    # Batch: precargar insumos de todos los lotes vencidos
    li_insumo_ids = list({l.ID_Insumo for l in lotes_insumo if l.ID_Insumo})
    insumos_li    = {i.ID_Insumo: i for i in db.query(Insumo).filter(Insumo.ID_Insumo.in_(li_insumo_ids)).all()} if li_insumo_ids else {}

    for lote in lotes_insumo:
        insumo = insumos_li.get(lote.ID_Insumo)
        if not insumo:
            lote.Estado = ESTADO_ANULADA
            continue

        cantidad = min(lote.Cantidad_Actual or lote.Cantidad_Inicial or 0, insumo.Stock_Actual or 0)
        lote.Estado = ESTADO_ANULADA

        if cantidad > 0:
            insumo.Stock_Actual -= cantidad
            _actualizar_estado_insumo(insumo)
            db.add(Salida(
                Tipo        = TipoSalida.VENCIMIENTO,
                ID_Insumo   = insumo.ID_Insumo,
                ID_Producto = None,
                Cantidad    = cantidad,
                Motivo      = f"Lote #{lote.ID_Lote_Compra} vencido el {lote.Fecha_Vencimiento.strftime('%Y-%m-%d')}",
                ID_Empleado = None,
                Fecha       = ahora,
                Estado      = ESTADO_ACTIVO,
            ))
            salidas_creadas.append({"tipo": "insumo", "nombre": insumo.Nombre, "cantidad": cantidad})
            insumos_afectados.add(insumo.ID_Insumo)

    # ── Productos ─────────────────────────────────────────────
    lotes_producto = (
        db.query(LoteProducto)
        .filter(
            LoteProducto.Fecha_Vencimiento != None,
            LoteProducto.Fecha_Vencimiento < ahora,
            LoteProducto.Estado == ESTADO_ACTIVO,
            LoteProducto.Cantidad > 0,
        )
        .order_by(LoteProducto.Fecha_Vencimiento.asc())
        .all()
    )

    # Batch: precargar productos de todos los lotes vencidos
    lp_prod_ids  = list({l.ID_Producto for l in lotes_producto if l.ID_Producto})
    productos_lp = {p.ID_Producto: p for p in db.query(Producto).filter(Producto.ID_Producto.in_(lp_prod_ids)).all()} if lp_prod_ids else {}

    for lote in lotes_producto:
        producto = productos_lp.get(lote.ID_Producto)
        if not producto:
            lote.Estado = ESTADO_ANULADA
            lote.Cantidad = 0
            continue

        cantidad = lote.Cantidad
        lote.Cantidad = 0
        lote.Estado = ESTADO_ANULADA
        producto.Stock = max(0, (producto.Stock or 0) - cantidad)
        _actualizar_estado_producto(producto)
        db.add(Salida(
            Tipo        = TipoSalida.VENCIMIENTO,
            ID_Insumo   = None,
            ID_Producto = producto.ID_Producto,
            Cantidad    = cantidad,
            Motivo      = f"Lote #{lote.ID_Lote_Producto} vencido el {lote.Fecha_Vencimiento.strftime('%Y-%m-%d')}",
            ID_Empleado = None,
            Fecha       = ahora,
            Estado      = ESTADO_ACTIVO,
        ))
        salidas_creadas.append({"tipo": "producto", "nombre": producto.nombre, "cantidad": cantidad})
        productos_afectados.add(producto.ID_Producto)

    db.commit()

    # Notificaciones: reusar objetos ya cargados
    for id_ins in insumos_afectados:
        ins = insumos_li.get(id_ins)
        if ins:
            notificar_stock_insumo(db, ins)
    for id_prod in productos_afectados:
        prod = productos_lp.get(id_prod)
        if prod:
            notificar_stock_producto(db, prod)

    return {"procesados": len(salidas_creadas), "salidas": salidas_creadas}
