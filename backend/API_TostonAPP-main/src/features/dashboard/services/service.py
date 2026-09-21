from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.shared.services.models import (
    Devolucion, Producto, Usuario, Venta, VentaXProducto,
)

# La BD guarda timestamps naïve en hora de Colombia (UTC-5, sin horario de verano).
# Offset fijo en vez de ZoneInfo para no depender de tzdata en Windows.
_TZ_COL = timezone(timedelta(hours=-5))

# Estados reales de un pedido (tabla Estados / ventas.pedidos.estados.py)
ESTADO_NOMBRE = {
    1:  "Pendiente",
    4:  "Confirmado",
    5:  "Cancelado",
    8:  "Entregado",
    9:  "En camino",
    11: "Completada",
    13: "En proceso",
    16: "Fecha propuesta",
}
ESTADO_KEY = {
    1:  "pendiente",
    4:  "confirmado",
    5:  "cancelado",
    8:  "entregado",
    9:  "en_camino",
    11: "completada",
    13: "en_proceso",
    16: "fecha_propuesta",
}

# "Flujo de ventas" y "Resumen general" muestran todos los estados vivos.
ESTADOS_FLUJO = tuple(ESTADO_KEY.keys())
# El resto de tarjetas cuentan solo pedidos entregados o completados (listos).
ESTADOS_COMPLETADO = (8, 11)
# Estado de una devolución aprobada.
DEVOLUCION_APROBADA = 6

MESES_ABBR = ["ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic"]


def _ahora() -> datetime:
    return datetime.now(_TZ_COL).replace(tzinfo=None)


def _fecha_fin_del_dia(fecha: datetime) -> datetime:
    return fecha.replace(hour=23, minute=59, second=59, microsecond=999999)


def _inicio_del_dia(fecha: datetime) -> datetime:
    return fecha.replace(hour=0, minute=0, second=0, microsecond=0)


# ─────────────────────────────────────────────────────────────
# Rangos y granularidad
# ─────────────────────────────────────────────────────────────

def _rango_fechas(periodo: str, inicio: datetime | None, fin: datetime | None):
    """Devuelve (inicio, fin, inicio_anterior, fin_anterior).

    El periodo anterior es siempre el bloque inmediatamente previo de la MISMA
    duración. Ninguna fecha puede superar el instante actual. Un rango custom con
    las fechas invertidas se corrige automáticamente (no se bloquea la consulta).
    """
    ahora = _ahora()

    if periodo == "custom" and inicio is not None and fin is not None:
        if fin < inicio:
            inicio, fin = fin, inicio
        inicio = _inicio_del_dia(inicio)
        fin = _fecha_fin_del_dia(fin)
    elif periodo == "semana":
        inicio = _inicio_del_dia(ahora - timedelta(days=ahora.weekday()))
        fin = ahora
    elif periodo == "mes":
        inicio = _inicio_del_dia(ahora.replace(day=1))
        fin = ahora
    else:  # "hoy" (o "custom" sin fechas)
        inicio = _inicio_del_dia(ahora)
        fin = ahora

    # Nunca hacia el futuro
    if fin > ahora:
        fin = ahora
    if inicio > ahora:
        inicio = _inicio_del_dia(ahora)

    dur = (fin - inicio) + timedelta(microseconds=1)
    inicio_ant = inicio - dur
    fin_ant = inicio - timedelta(microseconds=1)
    return inicio, fin, inicio_ant, fin_ant


def _granularidad(periodo: str, inicio: datetime, fin: datetime) -> str:
    if periodo == "hoy":
        return "hora"
    if periodo == "semana":
        return "dia"
    if periodo == "mes":
        return "semana"
    dias = (fin - inicio).days + 1
    if dias < 14:
        return "dia"
    if dias < 60:            # 2 semanas – <2 meses
        return "semana"
    if dias < 730:           # 2 meses – <2 años
        return "mes"
    return "anio"             # 2 años o más


def _label_hora(dt: datetime) -> str:
    h = dt.hour
    if h == 0:
        return "12am"
    if h < 12:
        return f"{h}am"
    if h == 12:
        return "12pm"
    return f"{h - 12}pm"


def _bucket_edges(inicio: datetime, fin: datetime, gran: str) -> list[dict]:
    """Lista de buckets [{start, end, label}] que cubren [inicio, fin]."""
    edges: list[dict] = []
    eps = timedelta(microseconds=1)

    if gran == "hora":
        cur = inicio.replace(minute=0, second=0, microsecond=0)
        while cur <= fin:
            nxt = cur + timedelta(hours=1)
            edges.append({"start": cur, "end": min(nxt - eps, fin), "label": _label_hora(cur)})
            cur = nxt
    elif gran in ("dia", "semana"):
        step = timedelta(days=1) if gran == "dia" else timedelta(weeks=1)
        cur = _inicio_del_dia(inicio)
        while cur <= fin:
            nxt = cur + step
            edges.append({"start": cur, "end": min(nxt - eps, fin), "label": cur.strftime("%d/%m")})
            cur = nxt
    elif gran == "mes":
        cur = _inicio_del_dia(inicio).replace(day=1)
        while cur <= fin:
            y, m = (cur.year + 1, 1) if cur.month == 12 else (cur.year, cur.month + 1)
            nxt = cur.replace(year=y, month=m)
            edges.append({
                "start": cur,
                "end": min(nxt - eps, fin),
                "label": f"{MESES_ABBR[cur.month - 1]} {cur.year % 100:02d}",
            })
            cur = nxt
    else:  # anio
        cur = _inicio_del_dia(inicio).replace(month=1, day=1)
        while cur <= fin:
            nxt = cur.replace(year=cur.year + 1)
            edges.append({"start": cur, "end": min(nxt - eps, fin), "label": str(cur.year)})
            cur = nxt

    return edges


# ─────────────────────────────────────────────────────────────
# Consultas base
# ─────────────────────────────────────────────────────────────

def _fecha_mas_antigua(db: Session) -> datetime | None:
    return db.query(func.min(Venta.Fecha_pedido)).scalar()


def _ventas_con_devolucion(db: Session) -> set[int]:
    """IDs de ventas con una devolución aprobada — dejan de contar como ingreso."""
    filas = db.query(Devolucion.ID_Venta).filter(
        Devolucion.Estado == DEVOLUCION_APROBADA,
        Devolucion.ID_Venta.isnot(None),
    ).distinct().all()
    return {f[0] for f in filas}


def _fetch_ventas_completadas(db: Session, desde: datetime, hasta: datetime, excluidas: set[int]):
    """(ID_Venta, Fecha_Venta, Total) de ventas entregadas/completadas sin devolución."""
    q = db.query(Venta.ID_Venta, Venta.Fecha_Venta, Venta.Total).filter(
        Venta.Fecha_Venta >= desde,
        Venta.Fecha_Venta <= hasta,
        Venta.Estado.in_(ESTADOS_COMPLETADO),
    )
    if excluidas:
        q = q.filter(~Venta.ID_Venta.in_(excluidas))
    return q.all()


def _sum_count(rows, lo: datetime, hi: datetime) -> tuple[Decimal, int]:
    total = Decimal(0)
    n = 0
    for _vid, fv, tot in rows:
        if fv is not None and lo <= fv <= hi:
            total += Decimal(str(tot or 0))
            n += 1
    return total, n


def _contar_clientes_nuevos(db: Session, lo: datetime, hi: datetime) -> int:
    return db.query(Usuario).filter(
        Usuario.ID_Rol == 3,                       # 3 = Cliente (ver auth.dependencies)
        Usuario.Fecha_creacion >= lo,
        Usuario.Fecha_creacion <= hi,
    ).count()


def _variacion(actual, anterior) -> tuple[float | None, bool | None, bool]:
    """Devuelve (variacion_pct, subiendo, sin_base).

    Si el periodo anterior es 0 el cambio porcentual es indefinido (no hay base
    con qué dividir): `variacion_pct=None`, `sin_base=True`. `subiendo` solo marca
    color/dirección: True si ahora hay valor (subió desde nada), None si sigue en 0.
    """
    if not anterior or float(anterior) == 0:
        return (None, True, True) if actual else (None, None, True)
    pct = ((float(actual) - float(anterior)) / float(anterior)) * 100
    return round(pct, 2), pct >= 0, False


def _tarjeta(actual, anterior, comparar: bool) -> dict:
    if not comparar:
        return {"valor": actual, "variacion_pct": None, "subiendo": None, "sin_base": False}
    pct, sube, sin_base = _variacion(actual, anterior)
    return {"valor": actual, "variacion_pct": pct, "subiendo": sube, "sin_base": sin_base}


# ─────────────────────────────────────────────────────────────
# Gráficas
# ─────────────────────────────────────────────────────────────

def _indice_bucket(buckets: list[dict], momento: datetime) -> int:
    """Índice del bucket que contiene `momento`, o -1. Los buckets son contiguos
    y están ordenados, así que basta con recorrerlos una vez."""
    for i, b in enumerate(buckets):
        if b["start"] <= momento <= b["end"]:
            return i
    return -1


def _flujo_ventas(db: Session, inicio: datetime, fin: datetime, buckets: list[dict]) -> list[dict]:
    filas = db.query(Venta.Fecha_pedido, Venta.Estado).filter(
        Venta.Fecha_pedido >= inicio,
        Venta.Fecha_pedido <= fin,
        Venta.Estado.in_(ESTADOS_FLUJO),
    ).all()

    segs = [{k: 0 for k in ESTADO_KEY.values()} for _ in buckets]
    for fp, est in filas:
        if fp is None or est not in ESTADO_KEY:
            continue
        i = _indice_bucket(buckets, fp)
        if i >= 0:
            segs[i][ESTADO_KEY[est]] += 1
    return [{"etiqueta": b["label"], **segs[i]} for i, b in enumerate(buckets)]


def _ventas_tiempo(rows, buckets: list[dict], dur: timedelta,
                   earliest: datetime | None, comparar: bool) -> list[dict]:
    actual = [Decimal(0)] * len(buckets)
    anterior = [Decimal(0)] * len(buckets)
    for _vid, fv, tot in rows:
        if fv is None:
            continue
        monto = Decimal(str(tot or 0))
        i = _indice_bucket(buckets, fv)
        if i >= 0:
            actual[i] += monto
        elif comparar:
            j = _indice_bucket(buckets, fv + dur)   # ¿cae en la ventana "anterior" de algún bucket?
            if j >= 0:
                anterior[j] += monto

    out = []
    for i, b in enumerate(buckets):
        ant = None
        if comparar and (earliest is None or b["start"] - dur >= earliest):
            # Solo se compara si la ventana anterior completa está dentro del historial;
            # si arranca antes del primer dato, ese punto sería parcial y engañoso.
            ant = anterior[i]
        out.append({"etiqueta": b["label"], "actual": actual[i], "anterior": ant})
    return out


def _productos_top(db: Session, inicio: datetime, fin: datetime,
                   excluidas: set[int], limite: int | None = 5) -> list[dict]:
    q = (
        db.query(
            VentaXProducto.ID_Producto,
            func.sum(VentaXProducto.Cantidad).label("cantidad"),
        )
        .join(Venta, Venta.ID_Venta == VentaXProducto.ID_Venta)
        .filter(
            Venta.Fecha_Venta >= inicio,
            Venta.Fecha_Venta <= fin,
            Venta.Estado.in_(ESTADOS_COMPLETADO),
        )
    )
    if excluidas:
        q = q.filter(~VentaXProducto.ID_Venta.in_(excluidas))

    resultados = q.group_by(VentaXProducto.ID_Producto).order_by(
        func.sum(VentaXProducto.Cantidad).desc()
    )
    if limite:
        resultados = resultados.limit(limite)
    resultados = resultados.all()

    if not resultados:
        return []

    total = sum(int(r.cantidad or 0) for r in resultados) or 1
    prod_ids = [r.ID_Producto for r in resultados]
    prod_map = {
        p.ID_Producto: p
        for p in db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()
    }

    return [
        {
            "ID_Producto": r.ID_Producto,
            "nombre": prod_map[r.ID_Producto].nombre if r.ID_Producto in prod_map else f"Producto {r.ID_Producto}",
            "cantidad": int(r.cantidad or 0),
            "ingresos": Decimal(str(prod_map[r.ID_Producto].Precio_venta or 0)) * int(r.cantidad or 0)
            if r.ID_Producto in prod_map else Decimal(0),
            "porcentaje": round((int(r.cantidad or 0) / total) * 100, 1),
        }
        for r in resultados
    ]


def _recortar_top(productos: list[dict], n: int) -> list[dict]:
    """Top-N del ranking ya ordenado, con el porcentaje recalculado sobre el
    subconjunto (para que las tajadas de la torta sumen 100%)."""
    top = productos[:n]
    total = sum(p["cantidad"] for p in top) or 1
    return [{**p, "porcentaje": round((p["cantidad"] / total) * 100, 1)} for p in top]


# ─────────────────────────────────────────────────────────────
# Detalle a nivel de fila
# ─────────────────────────────────────────────────────────────

def _detalle(db: Session, inicio: datetime, fin: datetime, excluidas: set[int],
             productos: list[dict] | None = None) -> dict:
    ventas = db.query(Venta).filter(
        Venta.Fecha_pedido >= inicio,
        Venta.Fecha_pedido <= fin,
        Venta.Estado.in_(ESTADOS_FLUJO),
    ).all()
    ids = [v.ID_Venta for v in ventas]

    lineas = (
        db.query(VentaXProducto).filter(VentaXProducto.ID_Venta.in_(ids)).all()
        if ids else []
    )
    prod_ids = {l.ID_Producto for l in lineas}
    prod_map = {
        p.ID_Producto: p
        for p in db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()
    } if prod_ids else {}

    user_ids = {v.ID_Usuario for v in ventas if v.ID_Usuario}
    user_map = {
        u.ID_Usuario: u
        for u in db.query(Usuario).filter(Usuario.ID_Usuario.in_(user_ids)).all()
    } if user_ids else {}

    lineas_por_venta: dict[int, list] = defaultdict(list)
    for l in lineas:
        lineas_por_venta[l.ID_Venta].append(l)

    ventas_detalle = []
    for v in ventas:
        u = user_map.get(v.ID_Usuario)
        cliente = f"{u.Nombre or ''} {u.Apellidos or ''}".strip() if u else "—"
        lineas_venta = []
        for l in lineas_por_venta.get(v.ID_Venta, []):
            p = prod_map.get(l.ID_Producto)
            # Precio al momento de la venta (snapshot). Fallback al precio
            # actual solo para líneas creadas antes de Precio_Unitario.
            if l.Precio_Unitario is not None:
                precio_linea = l.Precio_Unitario
            else:
                precio_linea = Decimal(str(p.Precio_venta or 0)) if p else Decimal(0)
            lineas_venta.append({
                "nombre": p.nombre if p else f"Producto {l.ID_Producto}",
                "cantidad": int(l.Cantidad or 0),
                "precio_unitario": precio_linea,
            })
        ventas_detalle.append({
            "ID_Venta": v.ID_Venta,
            "fecha_pedido": v.Fecha_pedido,
            "fecha_venta": v.Fecha_Venta,
            "cliente": cliente or "—",
            "metodo_pago": v.Metodo_Pago,
            "estado": ESTADO_NOMBRE.get(v.Estado, str(v.Estado)),
            "estado_id": v.Estado,
            "total": Decimal(str(v.Total or 0)),
            "tiene_devolucion": v.ID_Venta in excluidas,
            "productos": lineas_venta,
        })

    clientes = db.query(Usuario).filter(
        Usuario.ID_Rol == 3,
        Usuario.Fecha_creacion >= inicio,
        Usuario.Fecha_creacion <= fin,
    ).all()
    clientes_nuevos = [
        {
            "nombre": f"{c.Nombre or ''} {c.Apellidos or ''}".strip() or "—",
            "fecha": c.Fecha_creacion,
        }
        for c in clientes
    ]

    if productos is None:
        productos = _productos_top(db, inicio, fin, excluidas, limite=None)

    return {
        "ventas": ventas_detalle,
        "clientes_nuevos": clientes_nuevos,
        "productos": productos,
    }


# ─────────────────────────────────────────────────────────────
# Entradas públicas
# ─────────────────────────────────────────────────────────────

def _disponibilidad(db: Session, inicio, fin, inicio_ant, fin_ant):
    """Calcula qué se puede mostrar según el historial real de la BD.

    Devuelve (periodo_actual, comparacion, inicio_ant_efectivo, earliest).
    """
    earliest = _fecha_mas_antigua(db)

    if earliest is None:
        return (
            {"disponible": False, "parcial": False, "mensaje": "Aún no hay ventas registradas."},
            {"disponible": False, "parcial": False, "mensaje": "No hay periodo anterior disponible para comparar."},
            inicio_ant, earliest,
        )

    if fin < earliest:
        return (
            {"disponible": False, "parcial": False,
             "mensaje": f"No hay datos en el rango seleccionado; el historial empieza el {earliest:%d/%m/%Y}."},
            {"disponible": False, "parcial": False, "mensaje": "No hay periodo anterior disponible para comparar."},
            inicio_ant, earliest,
        )

    parcial_actual = inicio < earliest
    periodo_actual = {
        "disponible": True,
        "parcial": parcial_actual,
        "mensaje": (f"El historial empieza el {earliest:%d/%m/%Y}; se muestran los datos desde esa fecha."
                    if parcial_actual else None),
    }

    earliest_md = _inicio_del_dia(earliest)
    inicio_ant_ef = max(inicio_ant, earliest_md)
    if inicio_ant_ef > fin_ant:
        comparacion = {"disponible": False, "parcial": False,
                       "mensaje": "No hay periodo anterior disponible para comparar."}
    else:
        parcial_comp = inicio_ant_ef > inicio_ant
        comparacion = {
            "disponible": True,
            "parcial": parcial_comp,
            "mensaje": (f"El periodo anterior solo tiene historial desde el {earliest:%d/%m/%Y}; "
                        "la comparación es parcial." if parcial_comp else None),
        }

    return periodo_actual, comparacion, inicio_ant_ef, earliest


def _resumen_vacio() -> dict:
    cero = {"valor": Decimal(0), "variacion_pct": None, "subiendo": None}
    return {
        "total_ventas": dict(cero),
        "total_pedidos": dict(cero),
        "total_clientes": dict(cero),
        "ticket_promedio": dict(cero),
    }


def obtener_dashboard(db: Session, periodo: str = "hoy",
                      fecha_inicio: datetime | None = None,
                      fecha_fin: datetime | None = None) -> dict:
    if periodo not in ("hoy", "semana", "mes", "custom"):
        periodo = "hoy"

    inicio, fin, inicio_ant, fin_ant = _rango_fechas(periodo, fecha_inicio, fecha_fin)
    gran = _granularidad(periodo, inicio, fin)
    excluidas = _ventas_con_devolucion(db)
    periodo_actual, comparacion, inicio_ant_ef, earliest = _disponibilidad(
        db, inicio, fin, inicio_ant, fin_ant
    )

    buckets = _bucket_edges(inicio, fin, gran)
    dur = (fin - inicio) + timedelta(microseconds=1)

    if not periodo_actual["disponible"]:
        return {
            "periodo": periodo,
            "granularidad": gran,
            "rango": {"inicio": inicio, "fin": fin,
                      "inicio_anterior": inicio_ant, "fin_anterior": fin_ant},
            "periodo_actual": periodo_actual,
            "comparacion": comparacion,
            "resumen": _resumen_vacio(),
            "flujo_ventas": [{"etiqueta": b["label"], **{k: 0 for k in ESTADO_KEY.values()}} for b in buckets],
            "ventas_tiempo": [{"etiqueta": b["label"], "actual": Decimal(0), "anterior": None} for b in buckets],
            "productos_top": [],
            "detalle": None,
        }

    comparar = comparacion["disponible"]
    rows = _fetch_ventas_completadas(db, inicio_ant_ef, fin, excluidas)

    ventas_actual, pedidos_actual = _sum_count(rows, inicio, fin)
    ventas_ant, pedidos_ant = _sum_count(rows, inicio_ant_ef, fin_ant)
    ticket_actual = (ventas_actual / pedidos_actual) if pedidos_actual else Decimal(0)
    ticket_ant = (ventas_ant / pedidos_ant) if pedidos_ant else Decimal(0)
    clientes_actual = _contar_clientes_nuevos(db, inicio, fin)
    clientes_ant = _contar_clientes_nuevos(db, inicio_ant_ef, fin_ant) if comparar else 0

    resumen = {
        "total_ventas": _tarjeta(ventas_actual, ventas_ant, comparar),
        "total_pedidos": _tarjeta(Decimal(pedidos_actual), Decimal(pedidos_ant), comparar),
        "total_clientes": _tarjeta(Decimal(clientes_actual), Decimal(clientes_ant), comparar),
        "ticket_promedio": _tarjeta(round(ticket_actual, 2), round(ticket_ant, 2), comparar),
    }

    incluir_detalle = gran in ("hora", "dia", "semana")

    # En rangos cortos el detalle ya trae el ranking completo de productos; se
    # reutiliza para el top-5 en vez de repetir la agregación.
    if incluir_detalle:
        productos_full = _productos_top(db, inicio, fin, excluidas, limite=None)
        productos_top = _recortar_top(productos_full, 5)
        detalle = _detalle(db, inicio, fin, excluidas, productos_full)
    else:
        productos_top = _productos_top(db, inicio, fin, excluidas, limite=5)
        detalle = None

    return {
        "periodo": periodo,
        "granularidad": gran,
        "rango": {"inicio": inicio, "fin": fin,
                  "inicio_anterior": inicio_ant_ef if comparar else inicio_ant,
                  "fin_anterior": fin_ant},
        "periodo_actual": periodo_actual,
        "comparacion": comparacion,
        "resumen": resumen,
        "flujo_ventas": _flujo_ventas(db, inicio, fin, buckets),
        "ventas_tiempo": _ventas_tiempo(rows, buckets, dur, earliest, comparar),
        "productos_top": productos_top,
        "detalle": detalle,
    }


def obtener_detalle(db: Session, periodo: str = "hoy",
                    fecha_inicio: datetime | None = None,
                    fecha_fin: datetime | None = None) -> dict:
    if periodo not in ("hoy", "semana", "mes", "custom"):
        periodo = "hoy"
    inicio, fin, _ia, _fa = _rango_fechas(periodo, fecha_inicio, fecha_fin)
    excluidas = _ventas_con_devolucion(db)
    return _detalle(db, inicio, fin, excluidas)
