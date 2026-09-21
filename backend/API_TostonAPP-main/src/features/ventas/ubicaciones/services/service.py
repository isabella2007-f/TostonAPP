"""Módulo Ubicaciones — jerarquía Departamento → Ciudad → Barrio, estado en
cascada, y la FUNCIÓN ÚNICA de cálculo del precio del domicilio.

`precio_domicilio_final(db, id_barrio, fecha)` es reutilizada por:
  - el checkout (`gestion_ventas.crear_venta`, `pedidos.editar_pedido`)
  - el endpoint de cobertura (este módulo)
  - la vista del cliente (a través del endpoint de cobertura)

El resultado se CONGELA como snapshot en `Domicilios` al crear el pedido y no
se recalcula nunca. Reemplaza la constante `COSTO_DOMICILIO = Decimal("5000")`.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, and_, case
from sqlalchemy.orm import Session, selectinload

from src.shared.services.models import (
    Departamento, Ciudad, Barrio, OfertaDomicilio, OfertaXBarrio,
    Usuario, Domicilio,
)
from .schemas import normalizar_nombre, validar_nombre_barrio
from src.shared.services.enums import TipoOfertaDomicilio

_BOGOTA = ZoneInfo("America/Bogota")

# Un domicilio no puede costar más que esto: aun con recargos apilados, arriba de
# este valor es casi seguro un error de configuración. Es el "techo", simétrico
# al "piso" de 0 (domicilio gratis). Constante de negocio del backend.
TECHO_DOMICILIO = 50_000

ACTIVO, INACTIVO = 1, 2


def _now() -> datetime:
    """Hora actual en Colombia (naive), consistente con gestion_ventas / domicilios."""
    return datetime.now(_BOGOTA).replace(tzinfo=None)


def _parse_csv_int(v) -> list[int]:
    if not v:
        return []
    out = []
    for parte in str(v).split(","):
        parte = parte.strip()
        if parte.isdigit():
            out.append(int(parte))
    return out


def _to_csv(valores) -> str | None:
    vals = sorted({int(x) for x in (valores or [])})
    return ",".join(str(x) for x in vals) if vals else None


def _clamp(precio: Decimal) -> Decimal:
    return max(Decimal(0), min(precio, Decimal(TECHO_DOMICILIO)))


# ─────────────────────────────────────────
# ESTADO EN CASCADA
# ─────────────────────────────────────────

def estado_efectivo_barrio(db: Session, barrio: Barrio) -> tuple[bool, str | None]:
    """(disponible_para_domicilio, motivo_si_inactivo).

    Estado efectivo = Estado propio activo Y ciudad activa Y departamento activo.
    El motivo nombra al ancestro que lo bloquea (para que la UI lo explique).
    """
    ciudad = barrio.ciudad or db.query(Ciudad).filter(Ciudad.ID_Ciudad == barrio.ID_Ciudad).first()
    depto = None
    if ciudad:
        depto = ciudad.departamento or db.query(Departamento).filter(
            Departamento.ID_Departamento == ciudad.ID_Departamento
        ).first()

    if depto and depto.Estado != ACTIVO:
        return False, f"Inactivo por el departamento {depto.Nombre}"
    if ciudad and ciudad.Estado != ACTIVO:
        return False, f"Inactivo por la ciudad {ciudad.Nombre}"
    if barrio.Estado != ACTIVO:
        return False, "El barrio está inactivo"
    return True, None


def estado_efectivo_ciudad(db: Session, ciudad: Ciudad) -> tuple[bool, str | None]:
    depto = ciudad.departamento or db.query(Departamento).filter(
        Departamento.ID_Departamento == ciudad.ID_Departamento
    ).first()
    if depto and depto.Estado != ACTIVO:
        return False, f"Inactivo por el departamento {depto.Nombre}"
    if ciudad.Estado != ACTIVO:
        return False, "La ciudad está inactiva"
    return True, None


# ─────────────────────────────────────────
# CÁLCULO DEL PRECIO DEL DOMICILIO — función única
# ─────────────────────────────────────────

def _ofertas_aplicables(db: Session, id_barrio: int, fecha: datetime) -> list[OfertaDomicilio]:
    """Ofertas activas asociadas al barrio que aplican en la fecha dada
    (zona horaria America/Bogota), ordenadas por ID ascendente (determinista)."""
    iso_wd = fecha.isoweekday()   # 1=Lunes … 7=Domingo
    dia_mes = fecha.day
    rows = (
        db.query(OfertaDomicilio)
        .join(OfertaXBarrio, OfertaXBarrio.ID_Oferta == OfertaDomicilio.ID_Oferta)
        .filter(OfertaXBarrio.ID_Barrio == id_barrio, OfertaDomicilio.Estado == ACTIVO)
        .order_by(OfertaDomicilio.ID_Oferta.asc())
        .all()
    )
    aplicables = []
    for of in rows:
        dias_sem = _parse_csv_int(of.Dias_Semana)
        dias_mes = _parse_csv_int(of.Dias_Mes)
        if not dias_sem and not dias_mes:
            continue
        # Si hay días de semana Y de mes, aplica cuando coincide CUALQUIERA (OR).
        if (iso_wd in dias_sem) or (dia_mes in dias_mes):
            aplicables.append(of)
    return aplicables


def precio_domicilio_final(db: Session, id_barrio: int, fecha: datetime | None = None) -> dict:
    """Precio del domicilio para un barrio en una fecha, con ofertas aplicadas.

    Devuelve el dict que se congela como snapshot en `Domicilios.Desglose_Ofertas`:
        {
          "base": int,
          "final": int,
          "techo_aplicado": bool,   # el resultado se topó en TECHO_DOMICILIO
          "piso_aplicado": bool,    # el resultado se topó en 0 (domicilio gratis)
          "ofertas": [ {id, nombre, tipo, valor, efecto}, ... ]   # efecto en pesos, con signo
        }

    Acumulación:
      1. RECARGOS primero: cada uno en pesos (orden ID asc, clamp al techo tras
         cada paso), luego cada porcentaje compuesto en secuencia.
      2. DESCUENTOS después: cada uno en pesos (orden ID asc, clamp a 0 tras cada
         paso), luego cada porcentaje compuesto en secuencia.
      Redondeo ROUND_HALF_UP tras cada paso de porcentaje.

    NO valida cobertura — quien llama decide si un barrio sin estado efectivo
    activo es un error (checkout) o solo "no disponible" (cobertura). Las ofertas
    solo se aplican si el barrio tiene cobertura.
    """
    barrio = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not barrio:
        raise HTTPException(status_code=404, detail="Barrio no encontrado")

    fecha = fecha or _now()
    base = int(barrio.Precio or 0)
    disponible, _ = estado_efectivo_barrio(db, barrio)

    ofertas = _ofertas_aplicables(db, id_barrio, fecha) if disponible else []
    recargos = [o for o in ofertas if o.Tipo == TipoOfertaDomicilio.RECARGO]
    descuentos = [o for o in ofertas if o.Tipo != TipoOfertaDomicilio.RECARGO]

    precio = Decimal(base)
    desglose: list[dict] = []
    techo_aplicado = False
    piso_aplicado = False

    def _aplicar(grupo: list[OfertaDomicilio], signo: int) -> None:
        nonlocal precio, techo_aplicado, piso_aplicado
        # 1) pesos, uno a uno en orden ID (con clamp tras cada uno: el desglose
        #    siempre suma exacto aunque un descuento lleve el precio a 0).
        for of in grupo:
            monto = of.Monto_Pesos
            if monto is None:
                continue
            antes = precio
            precio = _clamp(precio + signo * Decimal(int(monto)))
            if precio == Decimal(TECHO_DOMICILIO) and antes < Decimal(TECHO_DOMICILIO):
                techo_aplicado = True
            if precio == 0 and antes > 0:
                piso_aplicado = True
            desglose.append({
                "id": of.ID_Oferta, "nombre": of.Nombre,
                "tipo": ("recargo_pesos" if signo > 0 else "descuento_pesos"),
                "valor": int(monto), "efecto": int(precio - antes),
            })
        # 2) porcentajes compuestos en secuencia (orden ID), redondeo por paso.
        for of in grupo:
            pct = of.Porcentaje
            if pct is None:
                continue
            antes = precio
            factor = (Decimal(100) + signo * Decimal(int(pct))) / Decimal(100)
            precio = _clamp((antes * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if precio == Decimal(TECHO_DOMICILIO) and antes < Decimal(TECHO_DOMICILIO):
                techo_aplicado = True
            if precio == 0 and antes > 0:
                piso_aplicado = True
            desglose.append({
                "id": of.ID_Oferta, "nombre": of.Nombre,
                "tipo": ("recargo_pct" if signo > 0 else "descuento_pct"),
                "valor": int(pct), "efecto": int(precio - antes),
            })

    _aplicar(recargos, +1)
    _aplicar(descuentos, -1)

    return {
        "base": base,
        "final": int(precio),
        "techo_aplicado": techo_aplicado,
        "piso_aplicado": piso_aplicado,
        "ofertas": desglose,
    }


def resolver_domicilio(db: Session, id_barrio: int, fecha: datetime | None = None) -> dict:
    """Para `crear_venta` / `editar_pedido`: valida cobertura y devuelve todo lo
    que se congela en el `Domicilio`. Lanza HTTPException 400 si el barrio no
    tiene cobertura de domicilio (estado efectivo inactivo o no existe)."""
    barrio = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not barrio:
        raise HTTPException(status_code=400, detail="El barrio de entrega no existe.")
    disponible, motivo = estado_efectivo_barrio(db, barrio)
    if not disponible:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No hacemos domicilios en ese barrio por ahora ({motivo}). "
                "Elige un barrio con cobertura o recoge tu pedido en la tienda."
            ),
        )
    calc = precio_domicilio_final(db, id_barrio, fecha)
    ciudad = barrio.ciudad
    depto = ciudad.departamento if ciudad else None
    return {
        "id_barrio": id_barrio,
        "barrio": barrio.Nombre,
        "ciudad": ciudad.Nombre if ciudad else None,
        "departamento": depto.Nombre if depto else None,
        "base": calc["base"],
        "final": calc["final"],
        "desglose": calc,
    }


def cobertura_barrio(db: Session, id_barrio: int, fecha: datetime | None = None) -> dict:
    """Endpoint de cobertura (solo lectura, no lanza): dado un barrio dice si
    está disponible para domicilio y su precio ya con ofertas del día."""
    barrio = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not barrio:
        return {"id_barrio": id_barrio, "disponible": False,
                "motivo": "El barrio no existe.", "base": None, "final": None, "desglose": None}
    disponible, motivo = estado_efectivo_barrio(db, barrio)
    calc = precio_domicilio_final(db, id_barrio, fecha)
    ciudad = barrio.ciudad
    depto = ciudad.departamento if ciudad else None
    return {
        "id_barrio": id_barrio,
        "barrio": barrio.Nombre,
        "ciudad": ciudad.Nombre if ciudad else None,
        "departamento": depto.Nombre if depto else None,
        "disponible": disponible,
        "motivo": motivo,
        "base": calc["base"],
        "final": calc["final"] if disponible else None,
        "desglose": calc if disponible else None,
    }


def barrio_legible(db: Session, id_barrio: int | None) -> dict | None:
    """Datos legibles de un barrio para el perfil del cliente (dato guía)."""
    if not id_barrio:
        return None
    barrio = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not barrio:
        return None
    disponible, motivo = estado_efectivo_barrio(db, barrio)
    ciudad = barrio.ciudad
    depto = ciudad.departamento if ciudad else None
    return {
        "ID_Barrio": id_barrio,
        "nombre": barrio.Nombre,
        "ciudad": ciudad.Nombre if ciudad else None,
        "departamento": depto.Nombre if depto else None,
        "disponible": disponible,
        "motivo": motivo,
    }


# ─────────────────────────────────────────
# LECTURA DE LA JERARQUÍA
# ─────────────────────────────────────────

def listar_departamentos(db: Session) -> list[dict]:
    rows = db.query(Departamento).order_by(Departamento.Nombre.asc()).all()
    return [
        {"ID_Departamento": d.ID_Departamento, "Nombre": d.Nombre, "Estado": d.Estado,
         "estado_efectivo": d.Estado == ACTIVO}
        for d in rows
    ]


def resumen(db: Session) -> dict:
    """Contadores del catálogo para la tira de tarjetas del panel.

    `con cobertura` = barrio activo Y su ciudad activa Y su departamento activo
    (mismo criterio que `estado_efectivo`). Los precios promedian solo sobre esos
    barrios: son los que de verdad se pueden cobrar hoy.
    """
    deps_total = db.query(func.count(Departamento.ID_Departamento)).scalar() or 0
    deps_act = (
        db.query(func.count(Departamento.ID_Departamento))
        .filter(Departamento.Estado == ACTIVO).scalar() or 0
    )
    ciu_total = db.query(func.count(Ciudad.ID_Ciudad)).scalar() or 0
    barr_total = db.query(func.count(Barrio.ID_Barrio)).scalar() or 0

    n_cob, p_min, p_max, p_avg = (
        db.query(
            func.count(Barrio.ID_Barrio), func.min(Barrio.Precio),
            func.max(Barrio.Precio), func.avg(Barrio.Precio),
        )
        .join(Ciudad, Ciudad.ID_Ciudad == Barrio.ID_Ciudad)
        .join(Departamento, Departamento.ID_Departamento == Ciudad.ID_Departamento)
        .filter(
            Barrio.Estado == ACTIVO, Ciudad.Estado == ACTIVO,
            Departamento.Estado == ACTIVO,
        )
        .one()
    )

    ofertas_total = db.query(func.count(OfertaDomicilio.ID_Oferta)).scalar() or 0
    ofertas_act = (
        db.query(func.count(OfertaDomicilio.ID_Oferta))
        .filter(OfertaDomicilio.Estado == ACTIVO).scalar() or 0
    )

    return {
        "departamentos": int(deps_total),
        "departamentos_activos": int(deps_act),
        "ciudades": int(ciu_total),
        "barrios": int(barr_total),
        "barrios_con_cobertura": int(n_cob or 0),
        "precio_min": int(p_min) if p_min is not None else 0,
        "precio_max": int(p_max) if p_max is not None else 0,
        "precio_promedio": int(round(float(p_avg))) if p_avg is not None else 0,
        "ofertas": int(ofertas_total),
        "ofertas_activas": int(ofertas_act),
    }


def listar_ciudades(db: Session, id_departamento: int | None = None,
                    solo_activas: bool = False) -> list[dict]:
    q = db.query(Ciudad).options(selectinload(Ciudad.departamento))
    if id_departamento:
        q = q.filter(Ciudad.ID_Departamento == id_departamento)
    rows = q.order_by(Ciudad.Nombre.asc()).all()
    out = []
    for c in rows:
        efectivo, motivo = estado_efectivo_ciudad(db, c)
        if solo_activas and not efectivo:
            continue
        out.append({
            "ID_Ciudad": c.ID_Ciudad, "ID_Departamento": c.ID_Departamento,
            "Nombre": c.Nombre, "departamento": c.departamento.Nombre if c.departamento else None,
            "Estado": c.Estado, "estado_efectivo": efectivo, "motivo_inactivo": motivo,
        })
    return out


def listar_barrios(
    db: Session, *, pagina: int = 1, por_pagina: int = 20,
    id_ciudad: int | None = None, id_departamento: int | None = None,
    texto: str | None = None, estado_efectivo: str | None = None,
    es_base: bool | None = None, solo_disponibles: bool = False,
) -> dict:
    """Listado paginado server-side de barrios con su estado efectivo y el
    motivo si está inactivo por un ancestro. `estado_efectivo`: 'activo' | 'inactivo'.

    El estado efectivo, el motivo y el filtro por estado se resuelven en SQL
    (G-4): así la paginación es exacta (no devuelve páginas cortas por filtrar
    en Python después de traer la página) y no hay recorrido fila por fila.
    """
    efectivo_expr = and_(
        Barrio.Estado == ACTIVO, Ciudad.Estado == ACTIVO, Departamento.Estado == ACTIVO,
    )
    motivo_expr = case(
        (Departamento.Estado != ACTIVO,
         ("Inactivo por el departamento " + Departamento.Nombre)),
        (Ciudad.Estado != ACTIVO,
         ("Inactivo por la ciudad " + Ciudad.Nombre)),
        (Barrio.Estado != ACTIVO, "El barrio está inactivo"),
        else_=None,
    )

    q = (
        db.query(
            Barrio.ID_Barrio, Barrio.ID_Ciudad, Barrio.Nombre, Barrio.Precio, Barrio.Es_Base,
            Barrio.Estado, Ciudad.Nombre.label("ciudad"), Departamento.Nombre.label("departamento"),
            efectivo_expr.label("efectivo"), motivo_expr.label("motivo"),
        )
        .join(Ciudad, Ciudad.ID_Ciudad == Barrio.ID_Ciudad)
        .join(Departamento, Departamento.ID_Departamento == Ciudad.ID_Departamento)
    )
    if id_ciudad:
        q = q.filter(Barrio.ID_Ciudad == id_ciudad)
    if id_departamento:
        q = q.filter(Ciudad.ID_Departamento == id_departamento)
    if es_base is not None:
        q = q.filter(Barrio.Es_Base == es_base)
    if texto:
        termino = f"%{_escape_like(texto)}%"
        q = q.filter(
            Barrio.Nombre.ilike(termino, escape="\\")
            | Ciudad.Nombre.ilike(termino, escape="\\")
            | Departamento.Nombre.ilike(termino, escape="\\")
        )
    if estado_efectivo == "activo" or solo_disponibles:
        q = q.filter(efectivo_expr)
    elif estado_efectivo == "inactivo":
        q = q.filter(~efectivo_expr)

    total = q.count()
    filas = (
        q.order_by(Departamento.Nombre.asc(), Ciudad.Nombre.asc(), Barrio.Nombre.asc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    barrios = [
        {
            "ID_Barrio": r.ID_Barrio, "ID_Ciudad": r.ID_Ciudad, "Nombre": r.Nombre,
            "ciudad": r.ciudad, "departamento": r.departamento,
            "Precio": int(r.Precio or 0), "Es_Base": bool(r.Es_Base),
            "Estado": r.Estado, "estado_efectivo": bool(r.efectivo), "motivo_inactivo": r.motivo,
        }
        for r in filas
    ]
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "barrios": barrios}


def _escape_like(s: str) -> str:
    """Neutraliza los comodines de LIKE en el texto de búsqueda del usuario."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contar_referencias(db: Session, id_barrio: int) -> dict:
    return {
        "pedidos": db.query(func.count(Domicilio.ID_Domicilio))
                     .filter(Domicilio.ID_Barrio == id_barrio).scalar() or 0,
        "usuarios": db.query(func.count(Usuario.ID_Usuario))
                      .filter(Usuario.ID_Barrio == id_barrio).scalar() or 0,
        "ofertas": db.query(func.count(OfertaXBarrio.ID_Oferta))
                     .filter(OfertaXBarrio.ID_Barrio == id_barrio).scalar() or 0,
    }


def detalle_barrio(db: Session, id_barrio: int) -> dict:
    b = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not b:
        raise HTTPException(status_code=404, detail="Barrio no encontrado")
    efectivo, motivo = estado_efectivo_barrio(db, b)
    ciudad = b.ciudad
    depto = ciudad.departamento if ciudad else None
    refs = _contar_referencias(db, id_barrio)
    ofertas_activas = [
        {"ID_Oferta": o.ID_Oferta, "Nombre": o.Nombre, "Tipo": o.Tipo,
         "Monto_Pesos": o.Monto_Pesos, "Porcentaje": o.Porcentaje,
         "Dias_Semana": _parse_csv_int(o.Dias_Semana), "Dias_Mes": _parse_csv_int(o.Dias_Mes)}
        for o in (
            db.query(OfertaDomicilio)
            .join(OfertaXBarrio, OfertaXBarrio.ID_Oferta == OfertaDomicilio.ID_Oferta)
            .filter(OfertaXBarrio.ID_Barrio == id_barrio, OfertaDomicilio.Estado == ACTIVO)
            .order_by(OfertaDomicilio.ID_Oferta.asc())
            .all()
        )
    ]
    return {
        "ID_Barrio": b.ID_Barrio, "ID_Ciudad": b.ID_Ciudad, "Nombre": b.Nombre,
        "ciudad": ciudad.Nombre if ciudad else None,
        "departamento": depto.Nombre if depto else None,
        "Precio": int(b.Precio or 0), "Es_Base": bool(b.Es_Base),
        "Estado": b.Estado, "estado_efectivo": efectivo, "motivo_inactivo": motivo,
        "ofertas_activas": ofertas_activas,
        "referencias": refs,
        "puede_eliminar": (not b.Es_Base) and sum(refs.values()) == 0,
    }


# ─────────────────────────────────────────
# CREAR / EDITAR / ELIMINAR BARRIO
# ─────────────────────────────────────────

def _nombre_duplicado(db: Session, id_ciudad: int, nombre: str, excluir_id: int | None = None) -> bool:
    """Compara ignorando tildes y mayúsculas dentro de la misma ciudad."""
    objetivo = normalizar_nombre(nombre)
    q = db.query(Barrio).filter(Barrio.ID_Ciudad == id_ciudad)
    if excluir_id:
        q = q.filter(Barrio.ID_Barrio != excluir_id)
    return any(normalizar_nombre(b.Nombre) == objetivo for b in q.all())


def crear_barrio(db: Session, datos) -> dict:
    ciudad = db.query(Ciudad).filter(Ciudad.ID_Ciudad == datos.ID_Ciudad).first()
    if not ciudad:
        raise HTTPException(status_code=404, detail="La ciudad seleccionada no existe")
    if _nombre_duplicado(db, datos.ID_Ciudad, datos.Nombre):
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un barrio con ese nombre en {ciudad.Nombre}",
        )
    nuevo = Barrio(
        ID_Ciudad=datos.ID_Ciudad, Nombre=datos.Nombre.strip(),
        Precio=int(datos.Precio), Es_Base=False, Estado=ACTIVO,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return detalle_barrio(db, nuevo.ID_Barrio)


def editar_barrio(db: Session, id_barrio: int, datos) -> dict:
    b = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not b:
        raise HTTPException(status_code=404, detail="Barrio no encontrado")

    cambios = {}
    if datos.Precio is not None and int(datos.Precio) != int(b.Precio or 0):
        cambios["Precio"] = int(datos.Precio)

    if datos.Nombre is not None:
        nombre_limpio = datos.Nombre.strip()
        if b.Es_Base and normalizar_nombre(nombre_limpio) != normalizar_nombre(b.Nombre):
            raise HTTPException(
                status_code=400,
                detail="Un barrio del catálogo base solo permite cambiar el precio y el estado",
            )
        if nombre_limpio != b.Nombre:
            if _nombre_duplicado(db, b.ID_Ciudad, nombre_limpio, excluir_id=id_barrio):
                raise HTTPException(status_code=409, detail="Ya existe un barrio con ese nombre en esta ciudad")
            cambios["Nombre"] = nombre_limpio

    if not cambios:
        # "No se hicieron cambios": el router no debería llegar acá si el
        # frontend compara antes, pero es la barrera real.
        raise HTTPException(status_code=422, detail="No se hicieron cambios")

    for campo, valor in cambios.items():
        setattr(b, campo, valor)
    db.commit()
    db.refresh(b)
    return detalle_barrio(db, id_barrio)


def eliminar_barrio(db: Session, id_barrio: int) -> dict:
    b = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not b:
        raise HTTPException(status_code=404, detail="Barrio no encontrado")
    if b.Es_Base:
        raise HTTPException(status_code=400, detail="Los barrios del catálogo base no se pueden eliminar, solo desactivar")
    refs = _contar_referencias(db, id_barrio)
    if sum(refs.values()) > 0:
        partes = []
        if refs["pedidos"]:
            partes.append(f"{refs['pedidos']} pedido(s)/domicilio(s)")
        if refs["usuarios"]:
            partes.append(f"{refs['usuarios']} cliente(s) lo tienen en su perfil")
        if refs["ofertas"]:
            partes.append(f"{refs['ofertas']} oferta(s) de domicilio")
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede eliminar: lo referencian {', '.join(partes)}. "
                "Desactívalo en su lugar."
            ),
        )
    db.delete(b)
    db.commit()
    return {"mensaje": "Barrio eliminado"}


# ─────────────────────────────────────────
# CAMBIO DE ESTADO (individual + masivo)
# ─────────────────────────────────────────

def cambiar_estado_departamento(db: Session, id_departamento: int, nuevo_estado: int) -> dict:
    d = db.query(Departamento).filter(Departamento.ID_Departamento == id_departamento).first()
    if not d:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    d.Estado = nuevo_estado
    db.commit()
    return {"ID_Departamento": id_departamento, "Estado": nuevo_estado}


def cambiar_estado_ciudad(db: Session, id_ciudad: int, nuevo_estado: int) -> dict:
    c = db.query(Ciudad).filter(Ciudad.ID_Ciudad == id_ciudad).first()
    if not c:
        raise HTTPException(status_code=404, detail="Ciudad no encontrada")
    if nuevo_estado == ACTIVO:
        depto = c.departamento or db.query(Departamento).filter(
            Departamento.ID_Departamento == c.ID_Departamento).first()
        if depto and depto.Estado != ACTIVO:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede activar: el departamento {depto.Nombre} está inactivo",
            )
    c.Estado = nuevo_estado
    db.commit()
    return {"ID_Ciudad": id_ciudad, "Estado": nuevo_estado}


def cambiar_estado_barrio(db: Session, id_barrio: int, nuevo_estado: int) -> dict:
    b = db.query(Barrio).filter(Barrio.ID_Barrio == id_barrio).first()
    if not b:
        raise HTTPException(status_code=404, detail="Barrio no encontrado")
    if nuevo_estado == ACTIVO:
        ciudad = b.ciudad or db.query(Ciudad).filter(Ciudad.ID_Ciudad == b.ID_Ciudad).first()
        efectivo, motivo = estado_efectivo_ciudad(db, ciudad) if ciudad else (False, "sin ciudad")
        if not efectivo:
            raise HTTPException(status_code=400, detail=f"No se puede activar: {motivo}")
    b.Estado = nuevo_estado
    db.commit()
    return {"ID_Barrio": id_barrio, "Estado": nuevo_estado}


def accion_masiva_estado(db: Session, datos) -> dict:
    """Activa/desactiva en bloque. Al ACTIVAR se respeta la regla de padre
    activo: un hijo no se activa si su padre está inactivo (se cuenta como omitido)."""
    nivel, nuevo, id_padre = datos.nivel, datos.Estado, datos.id_padre
    afectados, omitidos = 0, 0

    if nivel == "departamentos":
        for d in db.query(Departamento).all():
            if d.Estado != nuevo:
                d.Estado = nuevo
                afectados += 1

    elif nivel == "ciudades":
        q = db.query(Ciudad)
        if id_padre:
            q = q.filter(Ciudad.ID_Departamento == id_padre)
        for c in q.all():
            if nuevo == ACTIVO:
                depto = db.query(Departamento).filter(
                    Departamento.ID_Departamento == c.ID_Departamento).first()
                if depto and depto.Estado != ACTIVO:
                    omitidos += 1
                    continue
            if c.Estado != nuevo:
                c.Estado = nuevo
                afectados += 1

    elif nivel == "barrios":
        if not id_padre:
            raise HTTPException(status_code=400, detail="Falta la ciudad para la acción masiva de barrios")
        ciudad = db.query(Ciudad).filter(Ciudad.ID_Ciudad == id_padre).first()
        if not ciudad:
            raise HTTPException(status_code=404, detail="Ciudad no encontrada")
        for b in db.query(Barrio).filter(Barrio.ID_Ciudad == id_padre).all():
            if nuevo == ACTIVO:
                efectivo, _ = estado_efectivo_ciudad(db, ciudad)
                if not efectivo:
                    omitidos += 1
                    continue
            if b.Estado != nuevo:
                b.Estado = nuevo
                afectados += 1

    db.commit()
    return {"afectados": afectados, "omitidos": omitidos}
