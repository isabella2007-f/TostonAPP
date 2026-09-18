from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import func, or_, case
from src.shared.services.models import (
    Compra, DetalleCompra, LoteCompra, Insumo, Proveedor, Estado, UnidadMedida,
)
from src.shared.services.notificaciones_utils import notificar_stock_insumo
from .schemas import (
    CompraCreate, calcular_total_compra, validar_rango_total, TOTAL_MIN, TOTAL_MAX,
)


ESTADO_PENDIENTE  = 3
ESTADO_COMPLETADA = 11
ESTADO_ANULADA    = 12

LOTE_PENDIENTE = 3
LOTE_ACTIVO    = 1
LOTE_ANULADO   = 12


# ─────────────────────────────────────────
# HELPERS DE STOCK
# ─────────────────────────────────────────

def _actualizar_estado_insumo(insumo: Insumo) -> None:
    stock  = insumo.Stock_Actual or 0
    minimo = insumo.Stock_Minimo or 0
    if stock == 0:
        insumo.Estado = 15
    elif stock <= minimo:
        insumo.Estado = 14
    else:
        insumo.Estado = 1


# Símbolos de unidad de conteo: solo admiten cantidades enteras (no 2.5 uds.)
_UNIDADES_CONTEO = {"uds", "und", "u", "unidad", "unidades", "ud"}


def _validar_cantidades_por_unidad(db: Session, detalles) -> None:
    """Un insumo cuya unidad es de conteo solo admite cantidad entera."""
    ids = {d.ID_Insumo for d in detalles if d.ID_Insumo}
    if not ids:
        return
    insumos = {i.ID_Insumo: i for i in db.query(Insumo).filter(Insumo.ID_Insumo.in_(ids)).all()}
    unidad_ids = {i.Unidad_Medida for i in insumos.values() if i.Unidad_Medida}
    simbolos = {}
    if unidad_ids:
        for u in db.query(UnidadMedida).filter(UnidadMedida.ID_Unidad_Medida.in_(unidad_ids)).all():
            simbolos[u.ID_Unidad_Medida] = (u.Simbolo or "").strip().lower().rstrip(".")
    for d in detalles:
        ins = insumos.get(d.ID_Insumo)
        if not ins:
            continue
        if simbolos.get(ins.Unidad_Medida, "") in _UNIDADES_CONTEO:
            cant = Decimal(str(d.Cantidad or 0))
            if cant != cant.to_integral_value():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"'{ins.Nombre}' se compra por unidad: la cantidad debe ser un "
                        f"número entero (recibido {cant:g})."
                    ),
                )


def _parse_fecha_limite(valor, *, fin_del_dia: bool):
    """Convierte 'YYYY-MM-DD' (o datetime) a datetime; None si no se puede."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        d = datetime.fromisoformat(str(valor).split("T")[0]).date()
    except ValueError:
        return None
    return datetime.combine(d, time.max if fin_del_dia else time.min)


# ─────────────────────────────────────────
# FORMATO DE RESPUESTA
# ─────────────────────────────────────────

def _formato_detalle(detalle: DetalleCompra) -> dict:
    # Usa los relationships: lazy-load en op. individual, eager en listado
    insumo        = detalle.insumo
    lote          = detalle.lote_compra
    unidad_compra = detalle.unidad_compra   # unidad con la que se registró la compra
    fecha_venc = lote.Fecha_Vencimiento.strftime("%Y-%m-%d") if lote and lote.Fecha_Vencimiento else None
    return {
        "ID_Detalle_Compra":   detalle.ID_Detalle_Compra,
        "ID_Insumo":           detalle.ID_Insumo,
        "nombre_insumo":       insumo.Nombre if insumo else None,
        "ID_Unidad_Medida":    insumo.Unidad_Medida if insumo else None,
        "ID_Unidad_Compra":    detalle.ID_Unidad_Compra,
        "simbolo_unidad_compra": unidad_compra.Simbolo if unidad_compra else (insumo.unidad_medida.Simbolo if insumo and insumo.unidad_medida else None),
        "ID_Lote_Compra":      detalle.ID_Lote_Compra,
        "Cantidad":            detalle.Cantidad,
        "Precio_Und":          detalle.Precio_Und,
        "Notas":               detalle.Notas,
        "Fecha_Vencimiento":   fecha_venc,
    }


def _formato_compra(compra: Compra, db: Session, *, estados_map=None) -> dict:
    # Usa relationships: lazy-load en op. individual, eager en listado
    proveedor = compra.proveedor
    detalles  = compra.detalles

    if estados_map is not None:
        estado_label = estados_map.get(compra.Estado)
    else:
        estado_obj   = db.query(Estado).filter(Estado.ID_Estados == compra.Estado).first()
        estado_label = estado_obj.Estado if estado_obj else None

    return {
        "ID_Compra":            compra.ID_Compra,
        "ID_Proveedor":         compra.ID_Proveedor,
        "nombre_proveedor":     proveedor.Responsable if proveedor else None,
        "Total_Pago":           compra.Total_Pago,
        "Fecha_Compra":         compra.Fecha_Compra,
        "Fecha_Llegada":        getattr(compra, "Fecha_Llegada", None),
        "Fecha_Anulada":        getattr(compra, "Fecha_Anulada", None),
        "Estado":               compra.Estado,
        "estado_label":         estado_label,
        "Metodo_Pago":          compra.Metodo_Pago,
        "Notas":                getattr(compra, "Notas", None),
        "Comprobante":          getattr(compra, "Comprobante", None),
        "Costo_Transporte":     getattr(compra, "Costo_Transporte", None),
        "IVA_Porcentaje":       getattr(compra, "IVA_Porcentaje", None),
        "Descuento_Porcentaje": getattr(compra, "Descuento_Porcentaje", None),
        "Otros_Costos":         getattr(compra, "Otros_Costos", None),
        "detalles":             [_formato_detalle(d) for d in detalles],
    }


# ─────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────

def obtener_compras(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None,
    id_proveedor: int = None,
    fecha_desde=None,
    fecha_hasta=None,
) -> dict:
    query = db.query(Compra)

    if id_proveedor:
        query = query.filter(Compra.ID_Proveedor == id_proveedor)

    if busqueda:
        termino       = f"%{busqueda.strip()}%"
        proveedor_ids = (
            db.query(Proveedor.ID_Proveedor)
            .filter(Proveedor.Responsable.ilike(termino))
            .subquery()
        )
        filtros = [
            Compra.Metodo_Pago.ilike(termino),
            Compra.ID_Proveedor.in_(proveedor_ids),
        ]
        if busqueda.strip().isdigit():
            filtros.append(Compra.ID_Compra == int(busqueda.strip()))
        query = query.filter(or_(*filtros))

    # Rango de fechas — se corrige automáticamente si vienen invertidas (no se bloquea)
    d_desde = _parse_fecha_limite(fecha_desde, fin_del_dia=False)
    d_hasta = _parse_fecha_limite(fecha_hasta, fin_del_dia=True)
    if d_desde and d_hasta and d_desde > d_hasta:
        d_desde, d_hasta = _parse_fecha_limite(fecha_hasta, fin_del_dia=False), \
                           _parse_fecha_limite(fecha_desde, fin_del_dia=True)
    if d_desde:
        query = query.filter(Compra.Fecha_Compra >= d_desde)
    if d_hasta:
        query = query.filter(Compra.Fecha_Compra <= d_hasta)

    total   = query.count()
    offset  = (pagina - 1) * por_pagina
    compras = (
        query
        .options(
            selectinload(Compra.proveedor),
            selectinload(Compra.detalles).selectinload(DetalleCompra.insumo),
            selectinload(Compra.detalles).selectinload(DetalleCompra.lote_compra),
        )
        # Orden por ID desc (más nueva primero) — coincide con el orden que aplica
        # el frontend, para que la paginación server-side no deje fuera la última.
        .order_by(Compra.ID_Compra.desc())
        .offset(offset)
        .limit(por_pagina)
        .all()
    )

    estados_map = {e.ID_Estados: e.Estado for e in db.query(Estado).all()}

    if not compras:
        return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "compras": []}

    compra_ids   = [c.ID_Compra   for c in compras]
    prov_ids     = list({c.ID_Proveedor for c in compras if c.ID_Proveedor})
    estado_ids   = list({c.Estado       for c in compras if c.Estado})

    # Batch 1: proveedores y estados
    proveedores = {p.ID_Proveedor: p for p in
                   db.query(Proveedor).filter(Proveedor.ID_Proveedor.in_(prov_ids)).all()} if prov_ids else {}
    estados     = {e.ID_Estados: e for e in
                   db.query(Estado).filter(Estado.ID_Estados.in_(estado_ids)).all()} if estado_ids else {}

    # Batch 2: detalles agrupados por compra
    detalles_all = db.query(DetalleCompra).filter(DetalleCompra.ID_Compra.in_(compra_ids)).all()
    detalles_por_compra: dict = {}
    insumo_ids: set = set()
    lote_ids:   set = set()
    for d in detalles_all:
        detalles_por_compra.setdefault(d.ID_Compra, []).append(d)
        if d.ID_Insumo:
            insumo_ids.add(d.ID_Insumo)
        if d.ID_Lote_Compra:
            lote_ids.add(d.ID_Lote_Compra)

    # Batch 3: insumos, lotes y unidades de compra
    insumos = {i.ID_Insumo: i for i in
               db.query(Insumo).filter(Insumo.ID_Insumo.in_(list(insumo_ids))).all()} if insumo_ids else {}
    lotes   = {l.ID_Lote_Compra: l for l in
               db.query(LoteCompra).filter(LoteCompra.ID_Lote_Compra.in_(list(lote_ids))).all()} if lote_ids else {}

    unidad_compra_ids = {d.ID_Unidad_Compra for d in detalles_all if d.ID_Unidad_Compra}
    unidades_compra   = {u.ID_Unidad_Medida: u for u in
                         db.query(UnidadMedida).filter(UnidadMedida.ID_Unidad_Medida.in_(unidad_compra_ids)).all()} if unidad_compra_ids else {}

    def _build_detalle(d: DetalleCompra) -> dict:
        ins  = insumos.get(d.ID_Insumo)
        lote = lotes.get(d.ID_Lote_Compra) if d.ID_Lote_Compra else None
        fv   = lote.Fecha_Vencimiento.strftime("%Y-%m-%d") if lote and lote.Fecha_Vencimiento else None
        uc   = unidades_compra.get(d.ID_Unidad_Compra) if d.ID_Unidad_Compra else None
        return {
            "ID_Detalle_Compra":     d.ID_Detalle_Compra,
            "ID_Insumo":             d.ID_Insumo,
            "nombre_insumo":         ins.Nombre if ins else None,
            "ID_Unidad_Medida":      ins.Unidad_Medida if ins else None,
            "ID_Unidad_Compra":      d.ID_Unidad_Compra,
            "simbolo_unidad_compra": uc.Simbolo if uc else None,
            "ID_Lote_Compra":        d.ID_Lote_Compra,
            "Cantidad":              d.Cantidad,
            "Precio_Und":            d.Precio_Und,
            "Notas":                 d.Notas,
            "Fecha_Vencimiento":     fv,
        }

    def _build_compra(c: Compra) -> dict:
        prov   = proveedores.get(c.ID_Proveedor)
        estado = estados.get(c.Estado)
        return {
            "ID_Compra":            c.ID_Compra,
            "ID_Proveedor":         c.ID_Proveedor,
            "nombre_proveedor":     prov.Responsable if prov else None,
            "Total_Pago":           c.Total_Pago,
            "Fecha_Compra":         c.Fecha_Compra,
            "Fecha_Llegada":        getattr(c, "Fecha_Llegada", None),
            "Fecha_Anulada":        getattr(c, "Fecha_Anulada", None),
            "Estado":               c.Estado,
            "estado_label":         estado.Estado if estado else None,
            "Metodo_Pago":          c.Metodo_Pago,
            "Notas":                getattr(c, "Notas", None),
            "Comprobante":          getattr(c, "Comprobante", None),
            "Costo_Transporte":     getattr(c, "Costo_Transporte", None),
            "IVA_Porcentaje":       getattr(c, "IVA_Porcentaje", None),
            "Descuento_Porcentaje": getattr(c, "Descuento_Porcentaje", None),
            "Otros_Costos":         getattr(c, "Otros_Costos", None),
            "detalles":             [_build_detalle(d) for d in detalles_por_compra.get(c.ID_Compra, [])],
        }

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "compras":    [_build_compra(c) for c in compras],
    }


def _lote_info(lote: LoteCompra, id_compra_origen, *, hoy) -> dict:
    inicial = lote.Cantidad_Inicial or 0
    actual  = lote.Cantidad_Actual if lote.Cantidad_Actual is not None else inicial
    consumido = inicial - actual
    fv = lote.Fecha_Vencimiento
    return {
        "id":                lote.ID_Lote_Compra,
        "id_compra":         id_compra_origen,
        "fecha_vencimiento": fv.strftime("%Y-%m-%d") if fv else None,
        "cantidad_inicial":  inicial,
        "cantidad_actual":   actual,
        "consumido":         consumido if consumido > 0 else 0,
        "estado":            lote.Estado,
        "vencido":           bool(fv and fv < hoy),
    }


def obtener_compra(db: Session, id_compra: int) -> dict:
    """Detalle completo de una compra. Enriquece cada insumo con su lote de
    origen (el que generó esta compra) y los demás lotes del mismo insumo (3.15)."""
    compra = (
        db.query(Compra)
        .options(
            selectinload(Compra.proveedor),
            selectinload(Compra.detalles).selectinload(DetalleCompra.insumo),
            selectinload(Compra.detalles).selectinload(DetalleCompra.lote_compra),
        )
        .filter(Compra.ID_Compra == id_compra)
        .first()
    )
    if not compra:
        raise HTTPException(status_code=404, detail="Compra no encontrada")

    resultado = _formato_compra(compra, db)

    insumo_ids = [d["ID_Insumo"] for d in resultado["detalles"] if d.get("ID_Insumo")]
    if not insumo_ids:
        return resultado

    hoy = datetime.utcnow()
    lotes = (
        db.query(LoteCompra)
        .filter(LoteCompra.ID_Insumo.in_(insumo_ids))
        .order_by(
            case((LoteCompra.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteCompra.Fecha_Vencimiento.asc(),
            LoteCompra.ID_Lote_Compra.asc(),
        )
        .all()
    )
    # Compra que originó cada lote (vía su DetalleCompra)
    origen_por_lote: dict = {}
    if lotes:
        lote_ids = [l.ID_Lote_Compra for l in lotes]
        for det in (
            db.query(DetalleCompra.ID_Lote_Compra, DetalleCompra.ID_Compra)
            .filter(DetalleCompra.ID_Lote_Compra.in_(lote_ids))
            .all()
        ):
            origen_por_lote.setdefault(det.ID_Lote_Compra, det.ID_Compra)

    lotes_por_insumo: dict = {}
    for l in lotes:
        lotes_por_insumo.setdefault(l.ID_Insumo, []).append(l)

    for d in resultado["detalles"]:
        id_ins  = d.get("ID_Insumo")
        id_lote = d.get("ID_Lote_Compra")
        grupo = lotes_por_insumo.get(id_ins, [])
        d["lote_origen"] = None
        d["otros_lotes"] = []
        for l in grupo:
            info = _lote_info(l, origen_por_lote.get(l.ID_Lote_Compra), hoy=hoy)
            if id_lote is not None and l.ID_Lote_Compra == id_lote:
                d["lote_origen"] = info
            else:
                d["otros_lotes"].append(info)

    return resultado


def crear_compra(db: Session, datos: CompraCreate) -> dict:
    """
    Registra una compra en estado Pendiente (3).
    El stock NO se aplica al crear — solo al confirmar con completar_compra().
    """
    proveedor = db.query(Proveedor).filter(
        Proveedor.ID_Proveedor == datos.ID_Proveedor
    ).first()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    _validar_cantidades_por_unidad(db, datos.detalles)

    total_pago = calcular_total_compra(
        datos.detalles, datos.Costo_Transporte, datos.IVA_Porcentaje,
        datos.Descuento_Porcentaje, datos.Otros_Costos,
    )

    nueva_compra = Compra(
        ID_Proveedor         = datos.ID_Proveedor,
        Total_Pago           = total_pago,
        Fecha_Compra         = datos.Fecha_Compra or datetime.now(),
        Estado               = ESTADO_PENDIENTE,
        Metodo_Pago          = datos.Metodo_Pago,
        Notas                = datos.Notas,
        Comprobante          = datos.Comprobante or None,
        Costo_Transporte     = datos.Costo_Transporte,
        IVA_Porcentaje       = datos.IVA_Porcentaje,
        Descuento_Porcentaje = datos.Descuento_Porcentaje,
        Otros_Costos         = datos.Otros_Costos,
    )
    db.add(nueva_compra)
    db.flush()

    for item in datos.detalles:
        insumo = db.query(Insumo).filter(Insumo.ID_Insumo == item.ID_Insumo).first()
        if not insumo:
            db.rollback()
            raise HTTPException(
                status_code=404,
                detail=f"Insumo con ID {item.ID_Insumo} no encontrado"
            )

        lote = LoteCompra(
            ID_Insumo         = item.ID_Insumo,
            Fecha_Vencimiento = item.Fecha_Vencimiento,
            Cantidad_Inicial  = item.Cantidad,
            Cantidad_Actual   = item.Cantidad,  # FEFO: se actualiza al descontar
            Estado            = LOTE_PENDIENTE,  # se activa al confirmar llegada
        )
        db.add(lote)
        db.flush()

        detalle = DetalleCompra(
            ID_Compra        = nueva_compra.ID_Compra,
            ID_Insumo        = item.ID_Insumo,
            ID_Lote_Compra   = lote.ID_Lote_Compra,
            ID_Unidad_Compra = item.ID_Unidad_Compra,
            Cantidad         = item.Cantidad,
            Precio_Und       = item.Precio_Und,
            Notas            = item.Notas,
        )
        db.add(detalle)

    db.commit()
    db.refresh(nueva_compra)
    return _formato_compra(nueva_compra, db)


def editar_compra(db: Session, id_compra: int, datos) -> dict:
    """
    Edita una compra.
    - Pendiente: proveedor, método, fecha, notas, gastos adicionales e insumos
      (se reconstruyen las líneas y sus lotes pendientes). Recalcula el total.
    - Completada: solo método, notas y fecha de llegada.
    - Anulada: no editable.
    """
    compra = (
        db.query(Compra)
        .filter(Compra.ID_Compra == id_compra)
        .with_for_update()
        .first()
    )
    if not compra:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    if compra.Estado == ESTADO_ANULADA:
        raise HTTPException(status_code=400, detail="No se puede editar una compra anulada")

    es_pendiente = compra.Estado == ESTADO_PENDIENTE

    # Campos que solo son editables mientras la compra está Pendiente: si llegan
    # sobre una compra Completada, se rechaza en vez de ignorarlos en silencio.
    if not es_pendiente:
        no_permitidos = [
            campo for campo, val in (
                ("proveedor",  datos.ID_Proveedor),
                ("fecha de compra", datos.Fecha_Compra),
                ("costo de transporte", datos.Costo_Transporte),
                ("IVA", datos.IVA_Porcentaje),
                ("descuento", datos.Descuento_Porcentaje),
                ("otros costos", datos.Otros_Costos),
                ("insumos", datos.detalles),
            ) if val is not None
        ]
        if no_permitidos:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Esta compra ya está completada; no se puede editar: "
                    + ", ".join(no_permitidos)
                    + ". Solo el método de pago, el comprobante, las notas y la fecha de llegada."
                ),
            )

    # Campos editables en cualquier estado no-anulado
    if datos.Metodo_Pago is not None:
        compra.Metodo_Pago = datos.Metodo_Pago
    # El método de pago es obligatorio: no se puede dejar una compra sin él.
    if not (compra.Metodo_Pago or "").strip():
        raise HTTPException(status_code=400, detail="El método de pago es obligatorio")
    if datos.Notas is not None:
        compra.Notas = datos.Notas
    if datos.Comprobante is not None:
        compra.Comprobante = datos.Comprobante or None
    # La fecha de llegada solo tiene sentido en una compra ya completada.
    if datos.Fecha_Llegada is not None and compra.Estado == ESTADO_COMPLETADA:
        compra.Fecha_Llegada = datos.Fecha_Llegada

    if es_pendiente:
        if datos.ID_Proveedor is not None:
            proveedor = db.query(Proveedor).filter(Proveedor.ID_Proveedor == datos.ID_Proveedor).first()
            if not proveedor:
                raise HTTPException(status_code=404, detail="Proveedor no encontrado")
            compra.ID_Proveedor = datos.ID_Proveedor
        if datos.Fecha_Compra is not None:
            compra.Fecha_Compra = datos.Fecha_Compra

        # Gastos adicionales — solo editables mientras está Pendiente
        if datos.Costo_Transporte is not None:
            compra.Costo_Transporte = datos.Costo_Transporte
        if datos.IVA_Porcentaje is not None:
            compra.IVA_Porcentaje = datos.IVA_Porcentaje
        if datos.Descuento_Porcentaje is not None:
            compra.Descuento_Porcentaje = datos.Descuento_Porcentaje
        if datos.Otros_Costos is not None:
            compra.Otros_Costos = datos.Otros_Costos

        # Insumos — se reconstruyen las líneas y sus lotes pendientes SOLO si
        # realmente cambiaron (nunca toca lotes ya activos).
        if datos.detalles is not None:
            if not datos.detalles:
                raise HTTPException(status_code=400, detail="La compra debe tener al menos un insumo")

            _validar_cantidades_por_unidad(db, datos.detalles)

            viejos = (
                db.query(DetalleCompra)
                .filter(DetalleCompra.ID_Compra == id_compra)
                .order_by(DetalleCompra.ID_Detalle_Compra)
                .all()
            )
            lotes_viejos = {}
            lv_ids = [d.ID_Lote_Compra for d in viejos if d.ID_Lote_Compra]
            if lv_ids:
                lotes_viejos = {
                    l.ID_Lote_Compra: l
                    for l in db.query(LoteCompra).filter(LoteCompra.ID_Lote_Compra.in_(lv_ids)).all()
                }

            def _fv_iso(fv):
                return fv.date().isoformat() if fv else None

            firma_nueva = [
                (it.ID_Insumo, Decimal(str(it.Cantidad)), Decimal(str(it.Precio_Und)), _fv_iso(it.Fecha_Vencimiento))
                for it in datos.detalles
            ]
            firma_vieja = [
                (
                    d.ID_Insumo,
                    Decimal(str(d.Cantidad or 0)),
                    Decimal(str(d.Precio_Und or 0)),
                    _fv_iso(lotes_viejos[d.ID_Lote_Compra].Fecha_Vencimiento
                            if d.ID_Lote_Compra in lotes_viejos else None),
                )
                for d in viejos
            ]

            if firma_nueva != firma_vieja:
                for d in viejos:
                    db.delete(d)
                db.flush()
                if lv_ids:
                    (db.query(LoteCompra)
                       .filter(LoteCompra.ID_Lote_Compra.in_(lv_ids),
                               LoteCompra.Estado == LOTE_PENDIENTE)
                       .delete(synchronize_session=False))

                for item in datos.detalles:
                    insumo = db.query(Insumo).filter(Insumo.ID_Insumo == item.ID_Insumo).first()
                    if not insumo:
                        db.rollback()
                        raise HTTPException(status_code=404, detail=f"Insumo con ID {item.ID_Insumo} no encontrado")
                    lote = LoteCompra(
                        ID_Insumo         = item.ID_Insumo,
                        Fecha_Vencimiento = item.Fecha_Vencimiento,
                        Cantidad_Inicial  = item.Cantidad,
                        Cantidad_Actual   = item.Cantidad,
                        Estado            = LOTE_PENDIENTE,
                    )
                    db.add(lote)
                    db.flush()
                    db.add(DetalleCompra(
                        ID_Compra        = id_compra,
                        ID_Insumo        = item.ID_Insumo,
                        ID_Lote_Compra   = lote.ID_Lote_Compra,
                        ID_Unidad_Compra = item.ID_Unidad_Compra,
                        Cantidad         = item.Cantidad,
                        Precio_Und       = item.Precio_Und,
                        Notas            = item.Notas,
                    ))
                db.flush()

    # Recalcular el total con el estado final de líneas + gastos
    detalles_finales = db.query(DetalleCompra).filter(DetalleCompra.ID_Compra == id_compra).all()
    total = calcular_total_compra(
        detalles_finales, compra.Costo_Transporte, compra.IVA_Porcentaje,
        compra.Descuento_Porcentaje, compra.Otros_Costos,
    )
    if total < TOTAL_MIN or total > TOTAL_MAX:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"El total resultante (${total:,.0f} COP) está fuera del rango permitido"
        )
    compra.Total_Pago = total

    db.commit()
    db.refresh(compra)
    return _formato_compra(compra, db)


def completar_compra(db: Session, id_compra: int, fecha_llegada=None) -> dict:
    """
    Confirma la llegada de la compra: aplica el stock de cada insumo y pasa a Completada (11).
    Solo puede completarse desde Pendiente (3).
    """
    compra = (
        db.query(Compra)
        .filter(Compra.ID_Compra == id_compra)
        .with_for_update()
        .first()
    )
    if not compra:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    if compra.Estado != ESTADO_PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede completar una compra en estado Pendiente"
        )

    # La fecha de llegada no puede ser futura ni anterior a la fecha de compra.
    if fecha_llegada is not None:
        fll = fecha_llegada.date() if isinstance(fecha_llegada, datetime) else fecha_llegada
        if fll > datetime.now().date():
            raise HTTPException(status_code=400, detail="La fecha de llegada no puede ser futura")
        if compra.Fecha_Compra and fll < compra.Fecha_Compra.date():
            raise HTTPException(
                status_code=400,
                detail="La fecha de llegada no puede ser anterior a la fecha de compra",
            )

    detalles = db.query(DetalleCompra).filter(DetalleCompra.ID_Compra == id_compra).all()

    # Batch: precargar insumos y lotes en 2 queries
    insumo_ids_d = [d.ID_Insumo      for d in detalles if d.ID_Insumo]
    lote_ids_d   = [d.ID_Lote_Compra for d in detalles if d.ID_Lote_Compra]
    insumos_map  = {i.ID_Insumo: i for i in db.query(Insumo).filter(Insumo.ID_Insumo.in_(insumo_ids_d)).all()} if insumo_ids_d else {}
    lotes_map    = {l.ID_Lote_Compra: l for l in db.query(LoteCompra).filter(LoteCompra.ID_Lote_Compra.in_(lote_ids_d)).all()} if lote_ids_d else {}

    # FEFO: el hint Insumo.ID_Lote_Compra apunta al lote de esta compra más próximo a vencer
    lote_hint_por_insumo: dict = {}
    for detalle in detalles:
        insumo = insumos_map.get(detalle.ID_Insumo)
        if insumo:
            insumo.Stock_Actual = (insumo.Stock_Actual or 0) + detalle.Cantidad
            _actualizar_estado_insumo(insumo)
        lote = lotes_map.get(detalle.ID_Lote_Compra) if detalle.ID_Lote_Compra else None
        if lote:
            lote.Estado = LOTE_ACTIVO
            if lote.Cantidad_Actual is None:
                lote.Cantidad_Actual = lote.Cantidad_Inicial
            actual = lote_hint_por_insumo.get(detalle.ID_Insumo)
            if actual is None or (
                lote.Fecha_Vencimiento is not None and (
                    actual.Fecha_Vencimiento is None
                    or lote.Fecha_Vencimiento < actual.Fecha_Vencimiento
                )
            ):
                lote_hint_por_insumo[detalle.ID_Insumo] = lote

    for id_insumo, lote in lote_hint_por_insumo.items():
        insumo = insumos_map.get(id_insumo)
        if insumo:
            insumo.ID_Lote_Compra = lote.ID_Lote_Compra

    compra.Estado = ESTADO_COMPLETADA
    compra.Fecha_Llegada = fecha_llegada or datetime.now()
    db.commit()
    db.refresh(compra)

    for detalle in detalles:
        insumo = insumos_map.get(detalle.ID_Insumo)
        if insumo:
            notificar_stock_insumo(db, insumo)
    db.commit()

    return _formato_compra(compra, db)


_TOL = Decimal("0.0001")


def anular_compra(db: Session, id_compra: int) -> dict:
    """
    Anula la compra conservando su historial (nunca DELETE físico).
    - Desde Pendiente (3): marca los lotes pendientes como Anulados (12), sin afectar stock.
    - Desde Completada (11): SOLO si el 100% de lo comprado sigue en stock —
      es decir, ningún lote de insumo generado por esta compra tuvo consumo
      (orden de producción, salida o cualquier descuento de stock). Si algo se
      consumió, la anulación se bloquea por completo (3.13).
    """
    compra = (
        db.query(Compra)
        .filter(Compra.ID_Compra == id_compra)
        .with_for_update()
        .first()
    )
    if not compra:
        raise HTTPException(status_code=404, detail="Compra no encontrada")
    if compra.Estado not in {ESTADO_PENDIENTE, ESTADO_COMPLETADA}:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden anular compras en estado Pendiente o Completada"
        )

    detalles = db.query(DetalleCompra).filter(DetalleCompra.ID_Compra == id_compra).all()

    # Batch: precargar insumos y lotes (con bloqueo de fila, orden determinista)
    insumo_ids_a = sorted({d.ID_Insumo      for d in detalles if d.ID_Insumo})
    lote_ids_a   = sorted({d.ID_Lote_Compra for d in detalles if d.ID_Lote_Compra})
    insumos_map  = {
        i.ID_Insumo: i for i in db.query(Insumo)
        .filter(Insumo.ID_Insumo.in_(insumo_ids_a))
        .order_by(Insumo.ID_Insumo.asc())
        .with_for_update().all()
    } if insumo_ids_a else {}
    lotes_map    = {
        l.ID_Lote_Compra: l for l in db.query(LoteCompra)
        .filter(LoteCompra.ID_Lote_Compra.in_(lote_ids_a))
        .order_by(LoteCompra.ID_Lote_Compra.asc())
        .with_for_update().all()
    } if lote_ids_a else {}

    if compra.Estado == ESTADO_COMPLETADA:
        # 3.13 — verificar lote por lote que NADA se haya consumido todavía.
        bloqueos = []
        for detalle in detalles:
            lote = lotes_map.get(detalle.ID_Lote_Compra) if detalle.ID_Lote_Compra else None
            if not lote:
                continue
            insumo   = insumos_map.get(detalle.ID_Insumo)
            nombre   = insumo.Nombre if insumo else f"insumo #{detalle.ID_Insumo}"
            inicial  = Decimal(str(lote.Cantidad_Inicial or 0))
            actual   = Decimal(str(lote.Cantidad_Actual if lote.Cantidad_Actual is not None else inicial))
            consumido = inicial - actual
            if consumido > _TOL:
                bloqueos.append(
                    f"'{nombre}' (lote #{lote.ID_Lote_Compra}): se consumieron "
                    f"{consumido:g} de {inicial:g} unidades ingresadas"
                )
            elif lote.Estado not in (LOTE_ACTIVO, LOTE_PENDIENTE):
                bloqueos.append(
                    f"'{nombre}' (lote #{lote.ID_Lote_Compra}): el lote ya no está activo "
                    f"(estado {lote.Estado}) y no puede revertirse"
                )
        if bloqueos:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se puede anular la compra #{}: parte de sus insumos ya fue "
                    "utilizada (producción, salida o descuento de stock). "
                    "Solo se puede anular si el 100% de lo comprado sigue disponible. "
                    "Detalle: {}".format(id_compra, "; ".join(bloqueos))
                ),
            )

        for detalle in detalles:
            lote = lotes_map.get(detalle.ID_Lote_Compra) if detalle.ID_Lote_Compra else None
            insumo = insumos_map.get(detalle.ID_Insumo)
            # El 100% del lote sigue en stock → restar exactamente lo que aportó.
            aporte = Decimal(str(lote.Cantidad_Inicial or 0)) if lote else Decimal(str(detalle.Cantidad or 0))
            if insumo:
                nuevo = Decimal(str(insumo.Stock_Actual or 0)) - aporte
                insumo.Stock_Actual = nuevo if nuevo > 0 else Decimal("0")
                _actualizar_estado_insumo(insumo)
            if lote:
                lote.Estado = LOTE_ANULADO
                lote.Cantidad_Actual = 0  # el lote revertido ya no aporta stock

        for detalle in detalles:
            insumo = insumos_map.get(detalle.ID_Insumo)
            if insumo:
                notificar_stock_insumo(db, insumo)

    elif compra.Estado == ESTADO_PENDIENTE:
        # Marcar lotes pendientes como anulados
        for detalle in detalles:
            lote = lotes_map.get(detalle.ID_Lote_Compra) if detalle.ID_Lote_Compra else None
            if lote and lote.Estado == LOTE_PENDIENTE:
                lote.Estado = LOTE_ANULADO

    compra.Estado = ESTADO_ANULADA
    compra.Fecha_Anulada = datetime.now()
    db.commit()
    db.refresh(compra)
    return _formato_compra(compra, db)
