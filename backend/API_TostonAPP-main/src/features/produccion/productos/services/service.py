import re
from sqlalchemy import case
from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from src.shared.services.models import Producto, CategoriaProducto, ProductoImagen, FichaTecnica, FichaTecnicaInsumo, Insumo, OrdenProduccion, VentaXProducto, DevolucionDetalle, LoteProducto, Venta, UnidadMedida, Salida
from .schemas import ProductoCreate, ProductoUpdate, FichaTecnicaInput


def _calcular_estado(stock: int, stock_minimo: int) -> tuple[int, str]:
    """Retorna el ID de estado y su etiqueta según el stock.
    Reglas: 0 → 15 Agotado, 0 < stock <= minimo → 14 Stock bajo, >minimo → 1 Activo.
    """
    if stock == 0:
        return 15, "Agotado"
    elif stock <= stock_minimo:
        return 14, "Stock bajo"
    else:
        return 1, "Activo"


def _formato_producto(producto: Producto, db: Session) -> dict:
    """Construye el dict de respuesta con categoría, imágenes y ficha técnica."""
    # Usa relaciones ya cargadas (eager) — sin queries extra al llamar desde obtener_productos.
    # Al llamar desde obtener_producto (single), SQLAlchemy hace lazy load normal (1 producto = OK).
    categoria = producto.categoria
    imagenes  = producto.imagenes

    # Ficha más reciente del listado ya cargado
    fichas_ord = sorted(
        producto.fichas_tecnicas,
        key=lambda f: f.Fecha_Creacion or datetime.min,
        reverse=True,
    )
    ficha = fichas_ord[0] if fichas_ord else None

    stock        = producto.Stock or 0
    stock_minimo = getattr(producto, "Stock_Minimo", 0) or 0
    estado_id, estado_label = _calcular_estado(stock, stock_minimo)

    hoy = datetime.utcnow()
    # Lote más próximo a vencer del listado ya cargado
    lotes_validos = [
        l for l in producto.lotes_producto
        if l.Fecha_Vencimiento and l.Estado == 1 and (l.Cantidad or 0) > 0
    ]
    proximo_lote_prod = (
        min(lotes_validos, key=lambda l: l.Fecha_Vencimiento)
        if lotes_validos else None
    )
    proximo_venc_prod = None
    dias_para_vencer_prod = None
    if proximo_lote_prod and proximo_lote_prod.Fecha_Vencimiento:
        proximo_venc_prod = proximo_lote_prod.Fecha_Vencimiento.strftime("%Y-%m-%d")
        dias_para_vencer_prod = (proximo_lote_prod.Fecha_Vencimiento - hoy).days

    # Lo que las órdenes en proceso ya tienen apartado de estos insumos. Sin
    # esto el panel compara la receta contra el stock a secas y da luz verde a
    # una orden que el servidor va a rechazar por insumo comprometido.
    from src.features.produccion.ordenes_produccion.services.service import (
        insumos_reservados,
    )
    _apartado = insumos_reservados(
        db, [fi.ID_Insumo for fi in (ficha.insumos_ficha if ficha else [])]
    )

    return {
        "ID_Producto":      producto.ID_Producto,
        "nombre":           producto.nombre,
        "ID_Categoria":     producto.ID_Categoria,
        "nombre_categoria": categoria.Nombre_Categoria if categoria else None,
        "icono_categoria":  categoria.Icono if categoria else None,
        "Precio_venta":     producto.Precio_venta,
        "Stock":            stock,
        "Stock_Minimo":     stock_minimo,
        "Estado":           estado_id,
        "estado_label":     estado_label,
        "Publicado":           getattr(producto, "Publicado", 0) or 0,
        "Requiere_Produccion": getattr(producto, "Requiere_Produccion", 0) or 0,
        "Descripcion_Corta": getattr(producto, "Descripcion_Corta", None),
        "Descripcion_Larga": getattr(producto, "Descripcion_Larga", None),
        "Fecha_Creacion":    getattr(producto, "Fecha_Creacion", None),
        "proximo_vencimiento": proximo_venc_prod,
        "dias_para_vencer":    dias_para_vencer_prod,
        "imagenes": [
            {"ID_Producto_Img": img.ID_Producto_Img, "url": img.imagen}
            for img in imagenes
        ],
        "ficha_tecnica": {
            "ID_Ficha":       ficha.ID_Ficha,
            "Version":        ficha.Version,
            "Observaciones":  ficha.Observaciones,
            "Procedimiento":  ficha.Procedimiento,
            "Estado":         ficha.Estado,
            "Fecha_Creacion":   ficha.Fecha_Creacion,
            "Dias_Vida_Util":   getattr(ficha, "Dias_Vida_Util", None),
            "Vida_Util_Unidad": getattr(ficha, "Vida_Util_Unidad", None),
            "insumos": [
                {
                    "ID_Ficha_Insumo":  fi.ID_Ficha_Insumo,
                    "ID_Insumo":        fi.ID_Insumo,
                    "nombre_insumo":    fi.insumo.Nombre if fi.insumo else None,
                    "ID_Categoria":     fi.insumo.ID_Categoria if fi.insumo else None,
                    "nombre_categoria": (fi.insumo.categoria.Nombre_Categoria if fi.insumo and fi.insumo.categoria else None),
                    "Cantidad":         fi.Cantidad,
                    "Unidad":           fi.Unidad,
                    "Stock_Actual":     float(fi.insumo.Stock_Actual or 0) if fi.insumo else None,
                    # La unidad en que está medido el insumo, que casi nunca es
                    # la de la ficha: la receta pide gramos y el depósito lo
                    # guarda en kilos. Sin ella no se pueden comparar.
                    "simbolo_unidad":   (fi.insumo.unidad_medida.Simbolo
                                         if fi.insumo and fi.insumo.unidad_medida else None),
                    "Stock_Disponible": (
                        round(float(fi.insumo.Stock_Actual or 0)
                              - _apartado.get(fi.ID_Insumo, 0.0), 4)
                        if fi.insumo else None
                    ),
                }
                for fi in (ficha.insumos_ficha if ficha else [])
            ],
        } if ficha else None,
    }


def obtener_productos(
    db: Session,
    pagina:     int = 1,
    por_pagina: int = 10,
    busqueda:   str = None,
    estado:     int = None,
    publicado:  int = None,
) -> dict:
    """Lista paginada con queries en lote. Evita N+1."""
    query = db.query(Producto)

    if estado is not None:
        query = query.filter(Producto.Estado == estado)

    if publicado is not None:
        query = query.filter(Producto.Publicado == publicado)

    if busqueda:
        termino = f"%{busqueda}%"
        query = query.join(
            CategoriaProducto,
            CategoriaProducto.ID_Categoria == Producto.ID_Categoria,
            isouter=True
        ).filter(
            Producto.nombre.ilike(termino) |
            CategoriaProducto.Nombre_Categoria.ilike(termino)
        )

    total  = query.count()
    offset = (pagina - 1) * por_pagina
    productos = (
        query
        .options(
            selectinload(Producto.categoria),
            selectinload(Producto.imagenes),
            selectinload(Producto.lotes_producto),
            selectinload(Producto.fichas_tecnicas)
                .selectinload(FichaTecnica.insumos_ficha)
                .selectinload(FichaTecnicaInsumo.insumo)
                .selectinload(Insumo.categoria),
        )
        .offset(offset)
        .limit(por_pagina)
        .all()
    )

    if not productos:
        return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "productos": []}

    prod_ids  = [p.ID_Producto for p in productos]
    cat_ids   = list({p.ID_Categoria for p in productos if p.ID_Categoria})

    # Batch 1: categorías
    categorias = {c.ID_Categoria: c for c in
                  db.query(CategoriaProducto)
                    .filter(CategoriaProducto.ID_Categoria.in_(cat_ids)).all()} if cat_ids else {}

    # Batch 2: imágenes agrupadas por producto
    imagenes_map: dict = {}
    for img in db.query(ProductoImagen).filter(ProductoImagen.ID_Producto.in_(prod_ids)).all():
        imagenes_map.setdefault(img.ID_Producto, []).append(img)

    # Batch 3: fichas técnicas (la más reciente por producto)
    fichas_raw = (
        db.query(FichaTecnica)
        .filter(FichaTecnica.ID_Producto.in_(prod_ids))
        .order_by(FichaTecnica.Fecha_Creacion.desc())
        .all()
    )
    fichas: dict = {}
    for f in fichas_raw:
        if f.ID_Producto not in fichas:
            fichas[f.ID_Producto] = f

    # Batch 4: insumos de fichas
    ficha_ids = [f.ID_Ficha for f in fichas.values()]
    fi_rows: dict = {}   # ficha_id → list[FichaTecnicaInsumo]
    insumo_fi_ids: set = set()
    if ficha_ids:
        for fi in db.query(FichaTecnicaInsumo).filter(FichaTecnicaInsumo.ID_Ficha.in_(ficha_ids)).all():
            fi_rows.setdefault(fi.ID_Ficha, []).append(fi)
            insumo_fi_ids.add(fi.ID_Insumo)

    # Batch 5: insumos para fichas
    insumos_fi: dict = {}
    cat_ins_ids: set = set()
    unidad_ins_ids: set = set()
    if insumo_fi_ids:
        for ins in db.query(Insumo).filter(Insumo.ID_Insumo.in_(list(insumo_fi_ids))).all():
            insumos_fi[ins.ID_Insumo] = ins
            if ins.ID_Categoria:
                cat_ins_ids.add(ins.ID_Categoria)
            if ins.Unidad_Medida:
                unidad_ins_ids.add(ins.Unidad_Medida)

    # Batch 5c: lo que las órdenes en proceso ya tienen apartado de estos
    # insumos, para que el panel compare contra lo que de verdad queda libre.
    from src.features.produccion.ordenes_produccion.services.service import (
        insumos_reservados,
    )
    apartado_fi = insumos_reservados(db, list(insumo_fi_ids))

    # Batch 5b: unidades de esos insumos, para poder comparar la receta con
    # el depósito (la ficha pide gramos, el insumo se guarda en kilos).
    unidades_fi: dict = {}
    if unidad_ins_ids:
        unidades_fi = {
            u.ID_Unidad_Medida: u
            for u in db.query(UnidadMedida).filter(
                UnidadMedida.ID_Unidad_Medida.in_(list(unidad_ins_ids))
            ).all()
        }

    # Batch 6: categorías de insumos
    from src.shared.services.models import CategoriaInsumo
    cats_insumo: dict = {}
    if cat_ins_ids:
        from src.shared.services.models import CategoriaInsumo as _CI
        cats_insumo = {c.ID_Categoria: c for c in
                       db.query(_CI).filter(_CI.ID_Categoria.in_(list(cat_ins_ids))).all()}

    # Batch 7: primer lote activo con vencimiento por producto
    hoy = datetime.utcnow()
    lotes_raw = (
        db.query(LoteProducto)
        .filter(
            LoteProducto.ID_Producto.in_(prod_ids),
            LoteProducto.Fecha_Vencimiento != None,
            LoteProducto.Estado == 1,
            LoteProducto.Cantidad > 0,
        )
        .order_by(LoteProducto.Fecha_Vencimiento.asc())
        .all()
    )
    primer_lote: dict = {}
    for lote in lotes_raw:
        if lote.ID_Producto not in primer_lote:
            primer_lote[lote.ID_Producto] = lote

    def _build(producto: Producto) -> dict:
        cat   = categorias.get(producto.ID_Categoria)
        ficha = fichas.get(producto.ID_Producto)
        lote  = primer_lote.get(producto.ID_Producto)
        imgs  = imagenes_map.get(producto.ID_Producto, [])

        stock        = producto.Stock or 0
        stock_minimo = getattr(producto, "Stock_Minimo", 0) or 0
        estado_id, estado_label = _calcular_estado(stock, stock_minimo)

        proximo_venc     = None
        dias_para_vencer = None
        if lote and lote.Fecha_Vencimiento:
            proximo_venc     = lote.Fecha_Vencimiento.strftime("%Y-%m-%d")
            dias_para_vencer = (lote.Fecha_Vencimiento - hoy).days

        ficha_dict = None
        if ficha:
            fis = fi_rows.get(ficha.ID_Ficha, [])
            ficha_dict = {
                "ID_Ficha":       ficha.ID_Ficha,
                "Version":        ficha.Version,
                "Observaciones":  ficha.Observaciones,
                "Procedimiento":  ficha.Procedimiento,
                "Estado":         ficha.Estado,
                "Fecha_Creacion":   ficha.Fecha_Creacion,
                "Dias_Vida_Util":   getattr(ficha, "Dias_Vida_Util", None),
                "Vida_Util_Unidad": getattr(ficha, "Vida_Util_Unidad", None),
                "insumos": [
                    {
                        "ID_Ficha_Insumo":  fi.ID_Ficha_Insumo,
                        "ID_Insumo":        fi.ID_Insumo,
                        "nombre_insumo":    insumos_fi[fi.ID_Insumo].Nombre if fi.ID_Insumo in insumos_fi else None,
                        "ID_Categoria":     insumos_fi[fi.ID_Insumo].ID_Categoria if fi.ID_Insumo in insumos_fi else None,
                        "nombre_categoria": (cats_insumo[insumos_fi[fi.ID_Insumo].ID_Categoria].Nombre_Categoria
                                             if fi.ID_Insumo in insumos_fi and insumos_fi[fi.ID_Insumo].ID_Categoria in cats_insumo
                                             else None),
                        "Cantidad":         fi.Cantidad,
                        "Unidad":           fi.Unidad,
                        "Stock_Actual":     float(insumos_fi[fi.ID_Insumo].Stock_Actual or 0) if fi.ID_Insumo in insumos_fi else None,
                        "simbolo_unidad":   (
                            unidades_fi[insumos_fi[fi.ID_Insumo].Unidad_Medida].Simbolo
                            if fi.ID_Insumo in insumos_fi
                            and insumos_fi[fi.ID_Insumo].Unidad_Medida in unidades_fi
                            else None
                        ),
                        "Stock_Disponible": (
                            round(float(insumos_fi[fi.ID_Insumo].Stock_Actual or 0)
                                  - apartado_fi.get(fi.ID_Insumo, 0.0), 4)
                            if fi.ID_Insumo in insumos_fi else None
                        ),
                    }
                    for fi in fis
                ],
            }

        return {
            "ID_Producto":      producto.ID_Producto,
            "nombre":           producto.nombre,
            "ID_Categoria":     producto.ID_Categoria,
            "nombre_categoria": cat.Nombre_Categoria if cat else None,
            "icono_categoria":  cat.Icono            if cat else None,
            "Precio_venta":     producto.Precio_venta,
            "Stock":            stock,
            "Stock_Minimo":     stock_minimo,
            "Estado":           estado_id,
            "estado_label":     estado_label,
            "Publicado":           getattr(producto, "Publicado",           0) or 0,
            "Requiere_Produccion": getattr(producto, "Requiere_Produccion", 0) or 0,
            "Descripcion_Corta":   getattr(producto, "Descripcion_Corta",  None),
            "Descripcion_Larga":   getattr(producto, "Descripcion_Larga",  None),
            "Fecha_Creacion":      getattr(producto, "Fecha_Creacion",     None),
            "proximo_vencimiento": proximo_venc,
            "dias_para_vencer":    dias_para_vencer,
            "imagenes": [
                {"ID_Producto_Img": img.ID_Producto_Img, "url": img.imagen}
                for img in imgs
            ],
            "ficha_tecnica": ficha_dict,
        }

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "productos":  [_build(p) for p in productos],
    }


def obtener_producto(db: Session, id_producto: int) -> dict:
    """Retorna un producto por ID o lanza 404."""
    producto = db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return _formato_producto(producto, db)


def obtener_lotes_producto(db: Session, id_producto: int) -> dict:
    """Retorna todos los lotes de producción de un producto.

    Cada lote se enriquece (3.16 / 3.17 — Opción A, sin libro de movimientos):
    - `orden_produccion`: la orden que lo creó (nº, fecha, cantidad, costo, pedido).
    - `cantidad_producida`: unidades con que nació el lote (= Cantidad de la orden).
    - `cantidad_restante`: unidades que quedan hoy.
    - `consumido`: producida − restante − vencido_sin_usar (vendido / usado en salidas).
    - `vencido_sin_usar`: cuánto se dio de baja al vencer el lote (salida de vencimiento).
    No se puede desglosar venta por venta: ese dato no se registra por lote.
    """
    hoy = datetime.utcnow()
    lotes = (
        db.query(LoteProducto)
        .filter(LoteProducto.ID_Producto == id_producto)
        .order_by(
            case((LoteProducto.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteProducto.Fecha_Vencimiento.asc(),
        )
        .all()
    )
    if not lotes:
        return {"lotes": [], "total": 0}

    orden_ids = list({l.ID_Orden_Produccion for l in lotes if l.ID_Orden_Produccion})
    ordenes = {
        o.ID_Orden_Produccion: o
        for o in db.query(OrdenProduccion).filter(OrdenProduccion.ID_Orden_Produccion.in_(orden_ids)).all()
    } if orden_ids else {}

    # Salidas por vencimiento de este producto → cuánto se venció sin usar, por lote.
    venc_por_lote: dict = {}
    for s in (
        db.query(Salida)
        .filter(Salida.ID_Producto == id_producto, Salida.Tipo == "vencimiento", Salida.Estado == 1)
        .all()
    ):
        m = re.match(r"Lote #(\d+)\b", s.Motivo or "")
        if m:
            venc_por_lote[int(m.group(1))] = venc_por_lote.get(int(m.group(1)), 0) + float(s.Cantidad or 0)

    resultado = []
    for l in lotes:
        fv = l.Fecha_Vencimiento
        fp = l.Fecha_Produccion
        vencido = bool(fv and fv < hoy)
        dias = (fv - hoy).days if fv else None
        orden = ordenes.get(l.ID_Orden_Produccion)

        restante  = float(l.Cantidad or 0)
        producida = float(orden.Cantidad) if (orden and orden.Cantidad is not None) else restante
        vencido_sin_usar = venc_por_lote.get(l.ID_Lote_Producto)
        if vencido_sin_usar is None:
            # Lote vencido que el job de bajas aún no procesó: lo que queda es lo que se venció.
            vencido_sin_usar = restante if vencido else 0.0
        consumido = producida - restante - vencido_sin_usar
        if consumido < 0:
            consumido = 0.0

        orden_fecha = None
        if orden:
            f = orden.Fecha_Creacion or orden.Fecha_inicio
            orden_fecha = f.strftime("%Y-%m-%d") if f else None

        resultado.append({
            "id":                 l.ID_Lote_Producto,
            "numero_lote":        l.Numero_Lote,
            "cantidad":           l.Cantidad,
            "cantidad_producida": producida,
            "cantidad_restante":  restante,
            "consumido":          consumido,
            "vencido_sin_usar":   vencido_sin_usar,
            "fecha_produccion":   fp.strftime("%Y-%m-%d") if fp else None,
            "fecha_vencimiento":  fv.strftime("%Y-%m-%d") if fv else None,
            "vencido":            vencido,
            "dias_para_vencer":   dias,
            "estado":             l.Estado,
            "orden_produccion": {
                "id":       orden.ID_Orden_Produccion,
                "fecha":    orden_fecha,
                "cantidad": orden.Cantidad,
                "costo":    float(orden.Costo) if orden.Costo is not None else None,
                "id_venta": orden.ID_Venta,
            } if orden else None,
        })
    return {"lotes": resultado, "total": len(resultado)}


def verificar_puede_eliminar_producto(db: Session, id_producto: int) -> dict:
    """Verifica si el producto puede eliminarse revisando registros dependientes."""
    ordenes = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Producto == id_producto
    ).count()
    if ordenes > 0:
        return {
            "ok": False,
            "razon": f"Este producto tiene {ordenes} orden(es) de producción asociada(s). Elimínalas primero desde Gestión de Órdenes.",
        }

    # Solo bloquear si hay pedidos ACTIVOS (pendiente, en proceso, confirmado, en camino)
    # Los pedidos completados o cancelados no impiden eliminar el producto
    ESTADOS_ACTIVOS_VENTA = (1, 4, 9, 13)
    ventas_activas = (
        db.query(VentaXProducto)
        .join(Venta, Venta.ID_Venta == VentaXProducto.ID_Venta)
        .filter(
            VentaXProducto.ID_Producto == id_producto,
            Venta.Estado.in_(ESTADOS_ACTIVOS_VENTA),
        )
        .count()
    )
    if ventas_activas > 0:
        return {
            "ok": False,
            "razon": f"Este producto está en {ventas_activas} pedido(s) activo(s) y no puede eliminarse.",
        }

    devoluciones = db.query(DevolucionDetalle).filter(
        DevolucionDetalle.ID_Producto == id_producto
    ).count()
    if devoluciones > 0:
        return {
            "ok": False,
            "razon": f"Este producto tiene {devoluciones} devolución(es) asociada(s) y no puede eliminarse.",
        }

    return {"ok": True}


def crear_producto(db: Session, datos: ProductoCreate) -> dict:
    """Crea el producto, calcula estado automático y crea ficha técnica si viene."""
    duplicado = db.query(Producto).filter(
        Producto.nombre == datos.nombre,
        Producto.ID_Categoria == datos.ID_Categoria,
    ).first()
    if duplicado:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un producto con ese nombre en esta categoría.",
        )

    estado_id, _ = _calcular_estado(datos.Stock, datos.Stock_Minimo)

    nuevo = Producto(
        nombre            = datos.nombre,
        ID_Categoria      = datos.ID_Categoria,
        Precio_venta      = datos.Precio_venta,
        Stock             = datos.Stock,
        Stock_Minimo      = datos.Stock_Minimo,
        Estado            = estado_id,
        Publicado         = datos.Publicado or 0,
        Descripcion_Corta = datos.Descripcion_Corta,
        Descripcion_Larga = datos.Descripcion_Larga,
        Fecha_Creacion    = datetime.now(),
    )
    db.add(nuevo)
    db.flush()  # obtiene el ID sin hacer commit aún

    # Crea la ficha técnica si viene en el body
    if datos.ficha_tecnica:
        ficha = FichaTecnica(
            ID_Producto      = nuevo.ID_Producto,
            ID_Categoria     = datos.ID_Categoria,
            Version          = datos.ficha_tecnica.Version or "1.0",
            Observaciones    = datos.ficha_tecnica.Observaciones,
            Procedimiento    = datos.ficha_tecnica.Procedimiento,
            Estado           = estado_id,
            Fecha_Creacion   = datetime.now(),
            Dias_Vida_Util   = datos.ficha_tecnica.Dias_Vida_Util,
            Vida_Util_Unidad = datos.ficha_tecnica.Vida_Util_Unidad,
        )
        db.add(ficha)

    db.commit()
    db.refresh(nuevo)
    return _formato_producto(nuevo, db)


def editar_producto(db: Session, id_producto: int, datos: ProductoUpdate) -> dict:
    """Edita solo los campos enviados y recalcula el estado."""
    producto = db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    nombre_nuevo    = datos.nombre        if datos.nombre        is not None else producto.nombre
    categoria_nueva = datos.ID_Categoria  if datos.ID_Categoria  is not None else producto.ID_Categoria
    if nombre_nuevo != producto.nombre or categoria_nueva != producto.ID_Categoria:
        dup = db.query(Producto).filter(
            Producto.nombre       == nombre_nuevo,
            Producto.ID_Categoria == categoria_nueva,
            Producto.ID_Producto  != id_producto,
        ).first()
        if dup:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un producto con ese nombre en esta categoría.",
            )

    for campo, valor in datos.model_dump(exclude_none=True).items():
        setattr(producto, campo, valor)

    # Recalcula estado automáticamente
    stock        = producto.Stock or 0
    stock_minimo = getattr(producto, "Stock_Minimo", 0) or 0
    producto.Estado, _ = _calcular_estado(stock, stock_minimo)

    db.commit()
    db.refresh(producto)
    return _formato_producto(producto, db)


def agregar_imagenes(db: Session, id_producto: int, urls: list[str]) -> dict:
    """Recibe URLs de Cloudinary y las asocia al producto."""
    producto = db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    for url in urls:
        db.add(ProductoImagen(ID_Producto=id_producto, imagen=url))

    db.commit()
    return _formato_producto(producto, db)


def eliminar_imagen(db: Session, id_imagen: int) -> dict:
    """Elimina una imagen por su ID."""
    imagen = db.query(ProductoImagen).filter(
        ProductoImagen.ID_Producto_Img == id_imagen
    ).first()
    if not imagen:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    db.delete(imagen)
    db.commit()
    return {"mensaje": f"Imagen {id_imagen} eliminada"}


# Estados de orden de producción que "congelan" la ficha: una orden En proceso
# (13) o Completada (11) siguió usando la receta con la que arrancó, aunque
# después se edite la ficha del producto.
_ESTADOS_ORDEN_CONGELAN_FICHA = (13, 11)


def _insumos_desde_payload(db: Session, id_ficha: int, insumos) -> None:
    """Reemplaza los insumos de una ficha con los del payload."""
    db.query(FichaTecnicaInsumo).filter(
        FichaTecnicaInsumo.ID_Ficha == id_ficha
    ).delete(synchronize_session=False)
    for ins in insumos:
        db.add(FichaTecnicaInsumo(
            ID_Ficha  = id_ficha,
            ID_Insumo = ins.ID_Insumo,
            Cantidad  = ins.Cantidad,
            Unidad    = ins.Unidad,
        ))


def gestionar_ficha(db: Session, id_producto: int, datos: FichaTecnicaInput) -> dict:
    """Crea o actualiza la ficha técnica de un producto.

    Si la ficha vigente ya está enganchada a órdenes de producción En proceso o
    Completadas, NO se muta: se crea una versión nueva y la anterior queda
    congelada como snapshot de esas órdenes. Las órdenes pendientes del producto
    se repuntan a la versión nueva. Si no hay órdenes que congelar, se edita
    in-place como antes.
    """
    producto = db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    ficha = db.query(FichaTecnica).filter(
        FichaTecnica.ID_Producto == id_producto
    ).order_by(FichaTecnica.Fecha_Creacion.desc()).first()

    campos = datos.model_dump(exclude_none=True, exclude={"insumos"})

    # ── Primera ficha del producto ────────────────────────────────────────────
    if not ficha:
        ficha = FichaTecnica(
            ID_Producto      = id_producto,
            ID_Categoria     = producto.ID_Categoria,
            Version          = datos.Version or "1.0",
            Observaciones    = datos.Observaciones,
            Procedimiento    = datos.Procedimiento,
            Estado           = 1,
            Fecha_Creacion   = datetime.now(),
            Dias_Vida_Util   = datos.Dias_Vida_Util,
            Vida_Util_Unidad = datos.Vida_Util_Unidad,
        )
        db.add(ficha)
        db.flush()
        if datos.insumos is not None:
            _insumos_desde_payload(db, ficha.ID_Ficha, datos.insumos)
        db.commit()
        db.refresh(producto)
        return _formato_producto(producto, db)

    congeladas = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Ficha == ficha.ID_Ficha,
        OrdenProduccion.Estado.in_(_ESTADOS_ORDEN_CONGELAN_FICHA),
    ).count()

    # ── Sin órdenes que congelar: edición in-place ────────────────────────────
    if congeladas == 0:
        for campo, valor in campos.items():
            setattr(ficha, campo, valor)
        if datos.insumos is not None:
            _insumos_desde_payload(db, ficha.ID_Ficha, datos.insumos)
        db.commit()
        db.refresh(producto)
        return _formato_producto(producto, db)

    # ── Fork: versión nueva; la anterior queda congelada ─────────────────────
    n_versiones = db.query(FichaTecnica).filter(
        FichaTecnica.ID_Producto == id_producto
    ).count()
    nueva = FichaTecnica(
        ID_Producto      = id_producto,
        ID_Categoria     = ficha.ID_Categoria,
        Version          = datos.Version or str(n_versiones + 1),
        Observaciones    = campos.get("Observaciones", ficha.Observaciones),
        Procedimiento    = campos.get("Procedimiento", ficha.Procedimiento),
        Estado           = 1,
        Fecha_Creacion   = datetime.now(),
        Dias_Vida_Util   = campos.get("Dias_Vida_Util", ficha.Dias_Vida_Util),
        Vida_Util_Unidad = campos.get("Vida_Util_Unidad", ficha.Vida_Util_Unidad),
    )
    db.add(nueva)
    db.flush()

    if datos.insumos is not None:
        for ins in datos.insumos:
            db.add(FichaTecnicaInsumo(
                ID_Ficha=nueva.ID_Ficha, ID_Insumo=ins.ID_Insumo,
                Cantidad=ins.Cantidad, Unidad=ins.Unidad,
            ))
    else:
        # Solo cambió metadata: la versión nueva clona los insumos actuales.
        for fi in db.query(FichaTecnicaInsumo).filter(
            FichaTecnicaInsumo.ID_Ficha == ficha.ID_Ficha
        ).all():
            db.add(FichaTecnicaInsumo(
                ID_Ficha=nueva.ID_Ficha, ID_Insumo=fi.ID_Insumo,
                Cantidad=fi.Cantidad, Unidad=fi.Unidad,
            ))

    ficha.Estado = 2   # inactiva; sigue existiendo para las órdenes que la usan

    # Las órdenes pendientes del producto pasan a la versión nueva.
    db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Producto == id_producto,
        OrdenProduccion.Estado == 1,   # Pendiente
    ).update({OrdenProduccion.ID_Ficha: nueva.ID_Ficha}, synchronize_session=False)

    db.commit()
    db.refresh(producto)
    return _formato_producto(producto, db)


def eliminar_ficha(db: Session, id_producto: int) -> dict:
    """Elimina la ficha técnica vigente del producto y sus insumos."""
    ficha = db.query(FichaTecnica).filter(
        FichaTecnica.ID_Producto == id_producto
    ).order_by(FichaTecnica.Fecha_Creacion.desc()).first()
    if not ficha:
        raise HTTPException(status_code=404, detail="Ficha técnica no encontrada")

    if db.query(OrdenProduccion).filter(OrdenProduccion.ID_Ficha == ficha.ID_Ficha).count():
        raise HTTPException(
            status_code=400,
            detail="La ficha técnica está asociada a órdenes de producción y no puede eliminarse.",
        )

    db.query(FichaTecnicaInsumo).filter(
        FichaTecnicaInsumo.ID_Ficha == ficha.ID_Ficha
    ).delete(synchronize_session=False)
    db.delete(ficha)
    db.commit()
    return {"mensaje": "Ficha técnica eliminada"}


def eliminar_producto(db: Session, id_producto: int) -> dict:
    """Elimina el producto, sus imágenes y su ficha técnica."""
    producto = db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    check = verificar_puede_eliminar_producto(db, id_producto)
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check["razon"])

    db.query(ProductoImagen).filter(ProductoImagen.ID_Producto == id_producto).delete()
    fichas = db.query(FichaTecnica).filter(FichaTecnica.ID_Producto == id_producto).all()
    for f in fichas:
        db.query(FichaTecnicaInsumo).filter(FichaTecnicaInsumo.ID_Ficha == f.ID_Ficha).delete(synchronize_session=False)
        db.delete(f)

    db.delete(producto)
    db.commit()
    return {"mensaje": f"Producto {id_producto} eliminado correctamente"}