import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, case
from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from decimal import Decimal

logger = logging.getLogger(__name__)

from src.shared.services.models import OrdenProduccion, Producto, Insumo, FichaTecnica, FichaTecnicaInsumo, Estado, Venta, LoteProducto, LoteCompra, UnidadMedida, DetalleCompra, Compra

# Estado de compra Anulada: sus líneas ya no valen como referencia de precio.
_COMPRA_ANULADA = 12
from src.shared.services.notificaciones_utils import notificar_stock_insumo, notificar_stock_producto
from .schemas import OrdenCreate, OrdenUpdate

# Hora local de Colombia (UTC-5). Se guarda naïve en BD, igual que el resto del proyecto.
_TZ_LOCAL = timezone(timedelta(hours=-5))


def _ahora_local() -> datetime:
    return datetime.now(_TZ_LOCAL).replace(tzinfo=None)


# ══ Unidades ═══════════════════════════════════════════════════════════════
#
# Una sola tabla para todo el módulo. Antes había dos, y no decían lo mismo:
# la de consumo de insumos comparaba los símbolos tal cual venían escritos
# —así que una ficha con "gr", "G" o un insumo en "Kg" hacía fallar la orden
# con "no se puede convertir"— y usaba la libra internacional (453,592 g)
# mientras la de costos usaba la del mercado colombiano (500 g). La misma
# receta costaba una cosa y consumía otra.
#
# La familia dice qué se puede convertir con qué; el factor lleva a la unidad
# base de esa familia (g, ml, unidad).

_FAMILIA: dict[str, str] = {
    "mg": "masa", "g": "masa", "kg": "masa", "lb": "masa", "t": "masa",
    "ml": "volumen", "l": "volumen",
    "taza": "volumen", "cucharada": "volumen", "cucharadita": "volumen",
    "unidad": "conteo",
}

# Convención de mercado colombiano: lb = 500 g (NO 453.592)
_FACTOR: dict[str, Decimal] = {
    "mg":     Decimal("0.001"),
    "g":      Decimal("1"),
    "kg":     Decimal("1000"),
    "lb":     Decimal("500"),
    "t":      Decimal("1000000"),
    "ml":     Decimal("1"),
    "l":      Decimal("1000"),
    # Medidas de cocina, en ml
    "taza":         Decimal("240"),
    "cucharada":    Decimal("15"),
    "cucharadita":  Decimal("5"),
    "unidad": Decimal("1"),
}

# Cómo escribe la gente las mismas unidades. Sin esto, que una ficha diga "gr"
# y el insumo esté en "Kg" bastaba para que la orden no arrancara.
_ALIAS: dict[str, str] = {
    "gr": "g", "grs": "g", "gramo": "g", "gramos": "g",
    "kgs": "kg", "kilo": "kg", "kilos": "kg",
    "kilogramo": "kg", "kilogramos": "kg",
    "mgs": "mg", "miligramo": "mg", "miligramos": "mg",
    "lbs": "lb", "libra": "lb", "libras": "lb",
    "ton": "t", "tonelada": "t", "toneladas": "t",
    "lt": "l", "lts": "l", "litro": "l", "litros": "l",
    "mls": "ml", "mililitro": "ml", "mililitros": "ml",
    "u": "unidad", "un": "unidad", "und": "unidad", "unds": "unidad",
    "uds": "unidad", "ud": "unidad", "unidades": "unidad",
    "tazas": "taza",
    "cucharadas": "cucharada",
    "cucharaditas": "cucharadita",
    "cda": "cucharada", "cdas": "cucharada",
    "cdta": "cucharadita", "cdtas": "cucharadita",
}

# Las medidas de cocina son de volumen, pero en la panadería se usan para
# pesar: "una taza de harina". El módulo ya hacía esa equivalencia (1 ml ≈ 1 g)
# y se conserva, limitada a estas medidas: convertir litros a kilos en general
# sería inventar una densidad.
_MEDIDAS_DE_COCINA = frozenset({"taza", "cucharada", "cucharadita"})


def _norm(simbolo: str) -> str:
    """Deja el símbolo en su forma canónica: "Kg", "kilos" y "KG" son "kg"."""
    u = (simbolo or "").strip().lower().rstrip(".")
    return _ALIAS.get(u, u)


def _convertir(cantidad: float, desde: str, hasta: str) -> float:
    """Pasa `cantidad` de una unidad a otra. 400 si no son compatibles."""
    d, h = _norm(desde), _norm(hasta)
    if d == h or not d or not h:
        return cantidad

    fam_d, fam_h = _FAMILIA.get(d), _FAMILIA.get(h)
    factor_d, factor_h = _FACTOR.get(d), _FACTOR.get(h)
    compatibles = (
        fam_d is not None and fam_h is not None
        and (fam_d == fam_h
             or (d in _MEDIDAS_DE_COCINA or h in _MEDIDAS_DE_COCINA)
             and {fam_d, fam_h} <= {"masa", "volumen"})
    )
    if not compatibles or factor_d is None or factor_h is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No se puede convertir de '{desde}' a '{hasta}'. "
                "Revisa las unidades en la ficha técnica."
            ),
        )
    return float(Decimal(str(cantidad)) * factor_d / factor_h)


# ── Costo de producción con conversión a unidad base ────────────
def _costo_un_insumo(
    precio: Decimal,
    unidad_insumo: str,
    cantidad_ficha: Decimal,
    unidad_ficha: str,
) -> tuple[Decimal, str | None]:
    """
    Aplica la fórmula de conversión a unidad base:
      valor_base    = precio / factor(unidad_insumo)
      cantidad_base = cantidad_ficha * factor(unidad_ficha)
      costo         = cantidad_base * valor_base

    Devuelve (costo, error). error es None cuando el cálculo es válido.
    """
    ui = _norm(unidad_insumo)
    uf = _norm(unidad_ficha)

    familia_i = _FAMILIA.get(ui)
    familia_f = _FAMILIA.get(uf)

    if not familia_i:
        return Decimal("0"), f"Unidad de compra '{unidad_insumo}' desconocida"
    if not familia_f:
        return Decimal("0"), f"Unidad en ficha '{unidad_ficha}' desconocida"
    if familia_i != familia_f:
        return Decimal("0"), (
            f"Unidades incompatibles: insumo comprado en '{unidad_insumo}' ({familia_i}) "
            f"vs ficha pide '{unidad_ficha}' ({familia_f})"
        )

    valor_base    = precio / _FACTOR[ui]
    cantidad_base = cantidad_ficha * _FACTOR[uf]
    return cantidad_base * valor_base, None


def _calcular_costo_detalle(
    db: Session,
    id_ficha: int,
    cantidad_orden: int,
    *,
    insumos_ficha=None,
    insumo_map=None,
    detalle_map=None,
    unidad_map=None,
) -> list[dict]:
    """
    Desglose de costo por insumo de la ficha.
    Cada entrada: { nombre, costo, error }
    Los kwargs opcionales aceptan datos pre-cargados (caso listado);
    cuando son None, usa db.query() exactamente como antes (caso op. individual).
    """
    if insumos_ficha is None:
        insumos_ficha = db.query(FichaTecnicaInsumo).filter(
            FichaTecnicaInsumo.ID_Ficha == id_ficha
        ).all()

    resultado = []
    for fi in insumos_ficha:
        if insumo_map is not None:
            insumo = insumo_map.get(fi.ID_Insumo)
        else:
            insumo = db.query(Insumo).filter(Insumo.ID_Insumo == fi.ID_Insumo).first()
        nombre = insumo.Nombre if insumo else f"Insumo #{fi.ID_Insumo}"

        if detalle_map is not None:
            detalle_compra = detalle_map.get(fi.ID_Insumo)
        else:
            detalle_compra = (
                db.query(DetalleCompra)
                .join(Compra, Compra.ID_Compra == DetalleCompra.ID_Compra)
                .filter(DetalleCompra.ID_Insumo == fi.ID_Insumo,
                        Compra.Estado != _COMPRA_ANULADA)
                .order_by(DetalleCompra.ID_Detalle_Compra.desc())
                .first()
            )
        if not detalle_compra or not detalle_compra.Precio_Und:
            resultado.append({"nombre": nombre, "costo": Decimal("0"), "error": "Sin precio de compra registrado"})
            continue

        precio = Decimal(str(detalle_compra.Precio_Und))

        unidad_medida = None
        if insumo and insumo.Unidad_Medida:
            if unidad_map is not None:
                unidad_medida = unidad_map.get(fi.ID_Insumo)
            else:
                unidad_medida = db.query(UnidadMedida).filter(
                    UnidadMedida.ID_Unidad_Medida == insumo.Unidad_Medida
                ).first()
        unidad_insumo = unidad_medida.Simbolo if unidad_medida else ""

        cantidad_total = Decimal(str(fi.Cantidad or 0)) * Decimal(str(cantidad_orden))
        costo, error = _costo_un_insumo(precio, unidad_insumo, cantidad_total, fi.Unidad or "")
        resultado.append({"nombre": nombre, "costo": costo, "error": error})

    return resultado


# ── FEFO: descontar lotes del que vence primero al último ────
def _descontar_fefo(db: Session, id_insumo: int, cantidad: float, nombre_insumo: str | None = None) -> None:
    """Descuenta `cantidad` del insumo consumiendo los lotes en orden FEFO.

    Bloquea las filas de lote (`with_for_update`) con un orden determinista
    (vencimiento, luego ID): dos órdenes que inician a la vez y comparten un
    insumo se serializan y no pueden descontar ambas sobre el mismo stock.
    """
    lotes = (
        db.query(LoteCompra)
        .filter(
            LoteCompra.ID_Insumo == id_insumo,
            LoteCompra.Cantidad_Actual > 0,
            LoteCompra.Estado == 1,
        )
        .order_by(
            case((LoteCompra.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteCompra.Fecha_Vencimiento.asc(),
            LoteCompra.ID_Lote_Compra.asc(),
        )
        .with_for_update()
        .all()
    )
    restante = float(cantidad)
    for lote in lotes:
        if restante <= 0:
            break
        disponible = float(lote.Cantidad_Actual or 0)
        tomar = min(disponible, restante)
        lote.Cantidad_Actual = round(disponible - tomar, 4)
        restante -= tomar

    if restante > 0.001:  # tolerancia para errores de punto flotante
        ref = f"«{nombre_insumo}»" if nombre_insumo else f"con ID {id_insumo}"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Los lotes activos del insumo {ref} no alcanzan para producir: "
                f"faltan {round(restante, 4)} unidades. Revisa el inventario por lotes "
                f"del insumo antes de iniciar la producción."
            ),
        )


ESTADO_PENDIENTE  = 1
ESTADO_EN_PROCESO = 13
ESTADO_COMPLETADA = 11
ESTADO_CANCELADA  = 5

# Nombres legibles de los estados operativos de una orden (la tabla Estados es
# compartida y para el ID 1 devuelve "Activo", que aquí significa "Pendiente").
_ORDEN_ESTADO_LABEL = {
    ESTADO_PENDIENTE:  "Pendiente",
    ESTADO_EN_PROCESO: "En proceso",
    ESTADO_COMPLETADA: "Completada",
    ESTADO_CANCELADA:  "Cancelada",
}

# Nombres legibles de los estados de un pedido (Venta), para explicar por qué la
# producción de una orden ligada a un pedido está o no habilitada.
_VENTA_ESTADO_LABEL = {
    1: "Pendiente", 4: "Confirmado", 5: "Cancelado", 8: "Entregado",
    9: "En camino", 10: "Asignado", 11: "Listo", 13: "En producción",
    16: "Fecha propuesta",
}


def _label_orden(estado: int) -> str:
    return _ORDEN_ESTADO_LABEL.get(estado, f"estado {estado}")


def _transiciones_texto(estado_actual: int) -> str:
    """Explica en lenguaje claro a qué estados se puede pasar desde el actual."""
    if estado_actual == ESTADO_PENDIENTE:
        return ("Desde «Pendiente» solo puede pasar a «En proceso» (iniciar la "
                "producción); para cancelarla se usa la acción «Anular».")
    if estado_actual == ESTADO_EN_PROCESO:
        return ("Desde «En proceso» solo puede pasar a «Completada» (finalizar la "
                "producción); para cancelarla se usa la acción «Anular».")
    return (f"Una orden «{_label_orden(estado_actual)}» es un estado final: ya no "
            f"admite cambios de estado.")

# Estados de venta que no se deben tocar (ya terminados)
_ESTADOS_VENTA_FINALES = {5, 8, 9}  # Cancelado, Entregado, En camino

# Estado del PEDIDO cuando su producción termina: Listo para despachar
# (EstadoPedido.LISTO). Coincide con ESTADO_COMPLETADA de las órdenes, pero son
# tablas distintas: se nombra aparte para que quede claro a qué se refiere.
ESTADO_VENTA_LISTO      = 11
ESTADO_VENTA_CONFIRMADO = 4
ESTADO_VENTA_FECHA_PROPUESTA = 16
# Estados del PEDIDO desde los que se gestiona la producción de su orden a
# mano (iniciar, completar) y desde los que terminar de hornear sí lo mueve.
#
# "Fecha propuesta" NO está: mientras el pedido espera que el cliente acepte
# o rechace la fecha, su orden queda bloqueada para el admin igual que si
# siguiera Pendiente (ver el chequeo de bloqueo manual en `cambiar_estado`).
# Si se completara solo con la fecha propuesta, el pedido saltaría a Listo
# sin que el cliente haya decidido nada; quien lo mueve es su respuesta en
# `aceptar_fecha`.
_ESTADOS_VENTA_PRODUCIENDO = {ESTADO_VENTA_CONFIRMADO, ESTADO_EN_PROCESO}


def _plan_de_insumos(db: Session, orden, *, bloquear: bool = False) -> list:
    """Qué insumo y cuánto hace falta para esta orden, en la unidad del insumo.

    La receta pide gramos y el depósito guarda kilos: acá se hace esa cuenta
    una sola vez, y la usan tanto la validación al iniciar como el descuento al
    completar. Antes cada una la repetía por su lado.

    Con `bloquear` se toman las filas de insumo con `with_for_update()` en orden
    de ID: dos órdenes que comparten un insumo se serializan y no pueden ambas
    pasar la validación sobre el mismo saldo.
    """
    if not orden.ID_Ficha:
        raise HTTPException(
            status_code=400,
            detail="El producto debe tener una ficha técnica asignada antes de iniciar la producción",
        )
    insumos_ficha = db.query(FichaTecnicaInsumo).filter(
        FichaTecnicaInsumo.ID_Ficha == orden.ID_Ficha
    ).all()
    if not insumos_ficha:
        raise HTTPException(
            status_code=400,
            detail="La ficha técnica no tiene insumos registrados. Agrégalos antes de iniciar producción.",
        )

    ids_insumo = [fi.ID_Insumo for fi in insumos_ficha]
    consulta = db.query(Insumo).filter(Insumo.ID_Insumo.in_(ids_insumo)).order_by(
        Insumo.ID_Insumo.asc()
    )
    if bloquear:
        consulta = consulta.with_for_update()
    insumos_map = {i.ID_Insumo: i for i in consulta.all()}

    unidad_ids = {i.Unidad_Medida for i in insumos_map.values() if i.Unidad_Medida}
    unidades_map = (
        {
            u.ID_Unidad_Medida: u
            for u in db.query(UnidadMedida).filter(
                UnidadMedida.ID_Unidad_Medida.in_(unidad_ids)
            ).all()
        }
        if unidad_ids else {}
    )

    plan = []
    for fi in insumos_ficha:
        insumo = insumos_map.get(fi.ID_Insumo)
        if not insumo:
            raise HTTPException(status_code=404, detail=f"Insumo ID {fi.ID_Insumo} no encontrado")
        unidad_ins = unidades_map.get(insumo.Unidad_Medida)
        simbolo = unidad_ins.Simbolo if unidad_ins else None
        necesario = _convertir(
            float(fi.Cantidad or 0) * orden.Cantidad,
            fi.Unidad or simbolo,
            simbolo,
        )
        plan.append((insumo, simbolo, necesario))
    return plan


def insumos_reservados(db: Session, ids_insumo, excluir_orden: int = None) -> dict:
    """Cuánto de cada insumo está apartado por órdenes que ya arrancaron.

    Una orden En proceso pisa sus insumos aunque todavía no se hayan
    descontado: la harina de esa producción ya tiene dueño. Sin esto, dos
    órdenes de 2 kg podían arrancar las dos con 2 kg en bodega, y la segunda se
    quedaba a medias en la mesa de trabajo.

    Se calcula sobre las órdenes mismas, no sobre una columna aparte: así no
    hay reservas que queden colgadas si algo se cae a mitad de camino.
    """
    ids = list(ids_insumo or [])
    if not ids:
        return {}

    filas = (
        db.query(OrdenProduccion, FichaTecnicaInsumo, Insumo, UnidadMedida)
        .join(FichaTecnicaInsumo, FichaTecnicaInsumo.ID_Ficha == OrdenProduccion.ID_Ficha)
        .join(Insumo, Insumo.ID_Insumo == FichaTecnicaInsumo.ID_Insumo)
        .outerjoin(UnidadMedida, UnidadMedida.ID_Unidad_Medida == Insumo.Unidad_Medida)
        .filter(
            OrdenProduccion.Estado == ESTADO_EN_PROCESO,
            FichaTecnicaInsumo.ID_Insumo.in_(ids),
        )
    )
    if excluir_orden is not None:
        filas = filas.filter(OrdenProduccion.ID_Orden_Produccion != excluir_orden)

    reservado: dict = {}
    for orden_otra, fi, _insumo, unidad in filas.all():
        simbolo = unidad.Simbolo if unidad else None
        try:
            cantidad = _convertir(
                float(fi.Cantidad or 0) * (orden_otra.Cantidad or 0),
                fi.Unidad or simbolo,
                simbolo,
            )
        except HTTPException:
            # Ficha con unidades que no se pueden leer: esa orden no llegó a
            # arrancar por su cuenta, así que tampoco aparta nada.
            continue
        reservado[fi.ID_Insumo] = reservado.get(fi.ID_Insumo, 0.0) + cantidad
    return reservado


def _sync_venta_por_ordenes(
    db: Session,
    id_venta: int,
    id_orden_actual: int,
    nuevo_estado_orden: int,
) -> None:
    """
    Mantiene el estado del pedido (Venta) coherente con sus órdenes de producción.

    Reglas:
    - Si TODAS las órdenes vinculadas están Completadas o Canceladas
      → el pedido queda Listo (11): ya está fabricado y es el estado desde el
        que se entrega en tienda o se asigna domiciliario.
    - Si hay alguna orden activa (Pendiente o En proceso)
      → el pedido pasa/permanece en En producción (13).
    - Nunca toca pedidos en estado final (Cancelado/Entregado/En camino).

    Antes, al terminar la producción el pedido volvía a Pendiente (1). Eso
    rompía el flujo de fecha propuesta: el pedido perdía el Confirmado que
    había ganado cuando el cliente aceptó la fecha y, al quedar Pendiente, el
    panel volvía a ofrecer "Proponer fecha" sobre un pedido cuya fecha el
    cliente YA había aceptado.
    """
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta or venta.Estado in _ESTADOS_VENTA_FINALES:
        return

    otras = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Venta == id_venta,
        OrdenProduccion.ID_Orden_Produccion != id_orden_actual,
    ).all()

    # Incluir el estado que tendrá la orden actual tras este cambio
    estados = [o.Estado for o in otras] + [nuevo_estado_orden]
    terminadas = {ESTADO_COMPLETADA, ESTADO_CANCELADA}

    todas_terminadas  = all(e in terminadas for e in estados)
    # Cancelar no es fabricar: si ninguna orden se completó, no hay producto.
    alguna_completada = any(e == ESTADO_COMPLETADA for e in estados)

    if todas_terminadas:
        # Solo se mueve si el pedido ya venía confirmado o en producción: si
        # alguien creó una orden suelta sobre un pedido que aún esperaba
        # confirmación o fecha del cliente, no se salta ese paso.
        if venta.Estado in _ESTADOS_VENTA_PRODUCIENDO:
            # Se fabricó algo → Listo para despachar.
            # Todas canceladas → no se fabricó nada: vuelve a Confirmado para
            # que el admin decida (reprogramar producción, surtir de stock o
            # cancelar). Marcarlo Listo diría que hay producto cuando no lo hay.
            venta.Estado = (
                ESTADO_VENTA_LISTO if alguna_completada else ESTADO_VENTA_CONFIRMADO
            )
    elif (venta.Estado in _ESTADOS_VENTA_PRODUCIENDO
          and venta.Estado != ESTADO_EN_PROCESO):
        # Hay órdenes activas y el pedido aún no refleja "En producción".
        # Solo se mueve el pedido que ya está confirmado: la orden de un pedido
        # que sigue Pendiente (se abrió al dejar el anticipo) no puede saltarse
        # la confirmación del admin.
        venta.Estado = ESTADO_EN_PROCESO


def _actualizar_estado_insumo(insumo: Insumo) -> None:
    stock  = insumo.Stock_Actual or 0
    minimo = insumo.Stock_Minimo or 0
    if stock == 0:
        insumo.Estado = 15
    elif stock <= minimo:
        insumo.Estado = 14
    else:
        insumo.Estado = 1


def _actualizar_estado_producto(producto: Producto) -> None:
    stock  = producto.Stock or 0
    minimo = getattr(producto, "Stock_Minimo", 0) or 0
    if stock == 0:
        producto.Estado = 15
    elif stock <= minimo:
        producto.Estado = 14
    else:
        producto.Estado = 1


def _label_estado(db: Session, id_estado: int) -> str:
    """Obtiene el nombre del estado desde la tabla Estados."""
    estado = db.query(Estado).filter(Estado.ID_Estados == id_estado).first()
    return estado.Estado if estado else None


def _ficha_vigente(db: Session, id_producto: int) -> FichaTecnica | None:
    """Ficha técnica que debe usar una orden nueva o pendiente del producto.

    Prefiere la ficha activa (Estado=1); si no hay ninguna activa, la última
    registrada. Las órdenes ya iniciadas conservan el ID_Ficha con el que
    arrancaron (snapshot): al editar una ficha con órdenes en proceso se crea
    una versión nueva y la anterior queda congelada para ellas.
    """
    base = db.query(FichaTecnica).filter(FichaTecnica.ID_Producto == id_producto)
    return (
        base.filter(FichaTecnica.Estado == 1).order_by(FichaTecnica.ID_Ficha.desc()).first()
        or base.order_by(FichaTecnica.ID_Ficha.desc()).first()
    )


def _precio_ultimo_lote(db: Session, id_insumo: int) -> Decimal:
    """Precio unitario del insumo en su compra más reciente."""
    detalle = (
        db.query(DetalleCompra)
        .join(Compra, Compra.ID_Compra == DetalleCompra.ID_Compra)
        .filter(DetalleCompra.ID_Insumo == id_insumo,
                Compra.Estado != _COMPRA_ANULADA)
        .order_by(DetalleCompra.ID_Detalle_Compra.desc())
        .first()
    )
    return Decimal(str(detalle.Precio_Und)) if (detalle and detalle.Precio_Und) else Decimal("0")


def _calcular_costo(db: Session, id_ficha, id_insumo, cantidad: int) -> Decimal:
    """
    Costo total: suma los costos válidos del desglose (ignora los que tienen error).
    Sin ficha, usa precio del último lote × cantidad (insumo directo).
    """
    if id_ficha:
        desglose = _calcular_costo_detalle(db, id_ficha, cantidad)
        return sum((d["costo"] for d in desglose if d["error"] is None), Decimal("0"))

    if id_insumo:
        return _precio_ultimo_lote(db, id_insumo) * Decimal(str(cantidad))

    return Decimal("0")


def _formato_orden(
    orden: OrdenProduccion,
    db: Session,
    *,
    estados_map=None,
    detalle_compra_map=None,
) -> dict:
    """Construye el dict de respuesta con nombres legibles.

    estados_map y detalle_compra_map son opcionales: cuando se pasan (desde
    obtener_ordenes) se usan datos pre-cargados en memoria sin queries adicionales.
    Cuando son None (cambiar_estado, crear_orden, editar_orden, obtener_orden)
    el comportamiento es IDÉNTICO al original: lazy-load de relationships + db.query().
    """
    # Relationship attributes: lazy-load en op. individuales, eager-load en listado
    producto = orden.producto
    insumo   = orden.insumo
    ficha    = orden.ficha if orden.ID_Ficha else None
    lote     = orden.lote

    # Estado label
    if estados_map is not None:
        estado_label = estados_map.get(orden.Estado) if orden.Estado else None
    else:
        estado_label = _label_estado(db, orden.Estado) if orden.Estado else None
    # La tabla Estados es compartida: Estado=1 es "Activo" para insumos/productos
    # pero en producción significa "Pendiente"
    if orden.Estado == 1:
        estado_label = "Pendiente"

    # Cálculo de costo
    if orden.ID_Ficha:
        if detalle_compra_map is not None and ficha:
            insumos_ficha_lista = ficha.insumos_ficha
            insumo_map_local = {fi.ID_Insumo: fi.insumo for fi in insumos_ficha_lista}
            unidad_map_local = {
                fi.ID_Insumo: fi.insumo.unidad_medida
                for fi in insumos_ficha_lista
                if fi.insumo and fi.insumo.Unidad_Medida
            }
            desglose = _calcular_costo_detalle(
                db, orden.ID_Ficha, orden.Cantidad,
                insumos_ficha=insumos_ficha_lista,
                insumo_map=insumo_map_local,
                detalle_map=detalle_compra_map,
                unidad_map=unidad_map_local,
            )
        else:
            desglose = _calcular_costo_detalle(db, orden.ID_Ficha, orden.Cantidad)

        costo_calculado = sum((d["costo"] for d in desglose if d["error"] is None), Decimal("0"))
        costo_detalle = [
            {"nombre": d["nombre"], "costo": float(d["costo"]), "error": d["error"]}
            for d in desglose
        ]
    else:
        costo_calculado = _calcular_costo(db, None, orden.ID_Insumo, orden.Cantidad)
        costo_detalle = []

    costo = costo_calculado if costo_calculado > 0 else (orden.Costo or Decimal("0"))

    # Estado del pedido que generó la orden (si lo hay): el frontend lo usa para
    # explicar por qué el cambio manual de estado está o no habilitado.
    venta_rel = orden.venta if orden.ID_Venta else None
    venta_estado = venta_rel.Estado if venta_rel else None
    venta_estado_label = (
        _VENTA_ESTADO_LABEL.get(venta_estado)
        or (_label_estado(db, venta_estado) if venta_estado else None)
    )

    return {
        "ID_Orden_Produccion": orden.ID_Orden_Produccion,
        "ID_Venta":            orden.ID_Venta,
        "venta_estado":        venta_estado,
        "venta_estado_label":  venta_estado_label,
        "ID_Producto":         orden.ID_Producto,
        "nombre_producto":     producto.nombre if producto else None,
        "ID_Insumo":           orden.ID_Insumo,
        "nombre_insumo":       insumo.Nombre if insumo else None,
        "stock_insumo":        insumo.Stock_Actual if insumo else None,
        "ID_Ficha":            orden.ID_Ficha,
        "version_ficha":       ficha.Version if ficha else None,
        "Cantidad":            orden.Cantidad,
        "Fecha_Creacion":      orden.Fecha_Creacion,
        "Fecha_inicio":        orden.Fecha_inicio,
        "Fecha_Entrega":       orden.Fecha_Entrega,
        "Fecha_fin":           orden.Fecha_fin,
        "Estado":              orden.Estado,
        "estado_label":        estado_label,
        "Costo":               float(costo),
        "costo_detalle":       costo_detalle,
        "lote": {
            "ID_Lote_Producto":  lote.ID_Lote_Producto,
            "Numero_Lote":       lote.Numero_Lote,
            "Fecha_Produccion":  lote.Fecha_Produccion,
            "Fecha_Vencimiento": lote.Fecha_Vencimiento,
            "Cantidad":          lote.Cantidad,
        } if lote else None,
    }


def obtener_ordenes(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None,
    id_venta: int = None,
) -> dict:
    """Lista paginada con queries en lote. Evita N+1."""
    query = db.query(OrdenProduccion)

    if id_venta is not None:
        query = query.filter(OrdenProduccion.ID_Venta == id_venta)

    if busqueda:
        termino = f"%{busqueda}%"
        productos_ids = (
            db.query(Producto.ID_Producto)
            .filter(Producto.nombre.ilike(termino))
            .subquery()
        )
        query = query.filter(OrdenProduccion.ID_Producto.in_(productos_ids))

    total  = query.count()
    offset = (pagina - 1) * por_pagina
    ordenes = (
        query
        .options(
            selectinload(OrdenProduccion.producto),
            selectinload(OrdenProduccion.insumo),
            selectinload(OrdenProduccion.venta),
            selectinload(OrdenProduccion.ficha)
                .selectinload(FichaTecnica.insumos_ficha)
                .selectinload(FichaTecnicaInsumo.insumo)
                .selectinload(Insumo.unidad_medida),
            selectinload(OrdenProduccion.lote),
        )
        .offset(offset)
        .limit(por_pagina)
        .all()
    )

    if not ordenes:
        return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "ordenes": []}

    # Pre-batch: label de cada estado en una sola query (evita N+1 en _formato_orden)
    estados_map = {e.ID_Estados: e.Estado for e in db.query(Estado).all()}

    # Pre-batch: DetalleCompra más reciente por insumo (para el cálculo de costo)
    all_insumo_ids = set()
    for o in ordenes:
        if o.ficha:
            for fi in o.ficha.insumos_ficha:
                all_insumo_ids.add(fi.ID_Insumo)

    detalle_compra_map = {}
    if all_insumo_ids:
        subq = (
            db.query(
                DetalleCompra.ID_Insumo,
                func.max(DetalleCompra.ID_Detalle_Compra).label("max_id"),
            )
            .join(Compra, Compra.ID_Compra == DetalleCompra.ID_Compra)
            .filter(DetalleCompra.ID_Insumo.in_(all_insumo_ids),
                    Compra.Estado != _COMPRA_ANULADA)
            .group_by(DetalleCompra.ID_Insumo)
            .subquery()
        )
        detalles = (
            db.query(DetalleCompra)
            .join(subq, DetalleCompra.ID_Detalle_Compra == subq.c.max_id)
            .all()
        )
        detalle_compra_map = {d.ID_Insumo: d for d in detalles}

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "ordenes":    [
            _formato_orden(o, db, estados_map=estados_map, detalle_compra_map=detalle_compra_map)
            for o in ordenes
        ],
    }


def obtener_orden(db: Session, id_orden: int) -> dict:
    """Retorna una orden por ID o lanza 404."""
    orden = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Orden_Produccion == id_orden
    ).first()
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return _formato_orden(orden, db)


def crear_orden(db: Session, datos: OrdenCreate) -> dict:
    """Crea la orden (nace Pendiente) y calcula el costo automáticamente."""

    # Verifica que el producto existe
    if not db.query(Producto).filter(Producto.ID_Producto == datos.ID_Producto).first():
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # Verifica insumo solo si viene explícito
    if datos.ID_Insumo and not db.query(Insumo).filter(Insumo.ID_Insumo == datos.ID_Insumo).first():
        raise HTTPException(status_code=404, detail="Insumo no encontrado")

    # Un producto sin ficha técnica no se puede fabricar (ni manual ni automáticamente).
    ficha = _ficha_vigente(db, datos.ID_Producto)
    if not ficha:
        raise HTTPException(
            status_code=400,
            detail="El producto no tiene ficha técnica. Créala en Gestión de Productos antes de generar una orden de producción.",
        )
    # La orden se engancha a la ficha vigente del producto; el ID_Ficha del
    # request se ignora (la fuente de verdad es el producto).
    id_ficha = ficha.ID_Ficha

    ahora        = _ahora_local()
    fecha_inicio = datos.Fecha_inicio or ahora

    costo = _calcular_costo(db, id_ficha, datos.ID_Insumo, datos.Cantidad)

    nueva = OrdenProduccion(
        ID_Producto    = datos.ID_Producto,
        ID_Insumo      = datos.ID_Insumo,
        ID_Ficha       = id_ficha,
        Cantidad       = datos.Cantidad,
        Fecha_Creacion = ahora,
        Fecha_inicio   = fecha_inicio,
        Fecha_Entrega  = datos.Fecha_Entrega,
        Estado         = ESTADO_PENDIENTE,
        Costo          = costo,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return _formato_orden(nueva, db)


def editar_orden(db: Session, id_orden: int, datos: OrdenUpdate) -> dict:
    """Edita la orden. Solo se permite mientras está Pendiente (regla validada en backend)."""
    orden = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Orden_Produccion == id_orden
    ).with_for_update().first()
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # Una orden generada por un pedido no se edita por separado: sus datos
    # (producto, cantidad, fechas) los define el pedido. Editarla aquí la
    # desincronizaría de la línea del pedido.
    if orden.ID_Venta:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La orden #{id_orden} se generó a partir del pedido #{orden.ID_Venta} "
                f"y no se edita de forma independiente. Gestiónala desde el pedido en "
                f"Gestión de Pedidos."
            ),
        )

    # 3.6 — En proceso / Completada / Cancelada no admiten edición de ningún campo.
    if orden.Estado != ESTADO_PENDIENTE:
        etiqueta = _label_estado(db, orden.Estado) or orden.Estado
        raise HTTPException(
            status_code=400,
            detail=f"No se puede editar una orden en estado '{etiqueta}'. Solo las órdenes pendientes son editables.",
        )

    cambios = datos.model_dump(exclude_unset=True)
    hoy = _ahora_local().date()

    # Fecha de inicio: se puede dejar como está (aunque ya sea pasada); si se
    # cambia, no puede quedar antes de hoy ni antes de la original de la orden.
    if datos.Fecha_inicio is not None:
        nueva_inicio = datos.Fecha_inicio.date()
        original     = orden.Fecha_inicio.date() if orden.Fecha_inicio else None
        if nueva_inicio != original:
            if nueva_inicio < hoy:
                raise HTTPException(status_code=400, detail="La fecha de inicio no puede ser anterior a hoy")
            if original and nueva_inicio < original:
                raise HTTPException(
                    status_code=400,
                    detail="La fecha de inicio no puede ser anterior a la fecha de inicio original de la orden",
                )

    # Producto: si cambia, se re-engancha la ficha vigente del nuevo producto.
    if "ID_Producto" in cambios and datos.ID_Producto and datos.ID_Producto != orden.ID_Producto:
        if not db.query(Producto).filter(Producto.ID_Producto == datos.ID_Producto).first():
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        nueva_ficha = _ficha_vigente(db, datos.ID_Producto)
        if not nueva_ficha:
            raise HTTPException(
                status_code=400,
                detail="El producto no tiene ficha técnica. Créala en Gestión de Productos antes de asignarlo a una orden.",
            )
        orden.ID_Producto = datos.ID_Producto
        orden.ID_Ficha    = nueva_ficha.ID_Ficha
        orden.ID_Insumo   = None

    if "ID_Insumo" in cambios and datos.ID_Insumo is not None:
        if not db.query(Insumo).filter(Insumo.ID_Insumo == datos.ID_Insumo).first():
            raise HTTPException(status_code=404, detail="Insumo no encontrado")
        orden.ID_Insumo = datos.ID_Insumo

    if datos.Cantidad is not None:
        orden.Cantidad = datos.Cantidad
    if datos.Fecha_inicio is not None:
        orden.Fecha_inicio = datos.Fecha_inicio
    if datos.Fecha_Entrega is not None:
        orden.Fecha_Entrega = datos.Fecha_Entrega

    # 3.8 — una orden pendiente siempre apunta a la ficha vigente del producto.
    if orden.ID_Producto:
        vigente = _ficha_vigente(db, orden.ID_Producto)
        if vigente:
            orden.ID_Ficha = vigente.ID_Ficha

    # Entrega nunca antes del inicio (con los valores ya aplicados).
    if orden.Fecha_inicio and orden.Fecha_Entrega and orden.Fecha_Entrega.date() < orden.Fecha_inicio.date():
        raise HTTPException(
            status_code=400,
            detail="La fecha de entrega no puede ser anterior a la fecha de inicio",
        )

    orden.Costo = _calcular_costo(db, orden.ID_Ficha, orden.ID_Insumo, orden.Cantidad)

    db.commit()
    db.refresh(orden)
    return _formato_orden(orden, db)


def cambiar_estado(
    db: Session,
    id_orden: int,
    datos,
    *,
    origen_manual: bool = False,
    commit: bool = True,
) -> dict:
    """Cambia el estado de una orden.

    `datos` puede ser un int o un objeto con atributos Estado, Numero_Lote,
    Fecha_Vencimiento.

    - `origen_manual`: True cuando la petición llega por el endpoint (un usuario).
      Una orden generada por un pedido no se gestiona sola desde aquí: no se
      cancela a mano (la cancelación baja del pedido en cadena) y su avance
      (iniciar / completar) solo se habilita cuando el pedido ya salió de
      «Pendiente». Los llamadores internos (la cancelación en cadena desde
      ventas) usan el valor por defecto (False).
    - `commit`: False cuando el llamador maneja la transacción (cascada de
      cancelación del pedido) para que todo cierre en un solo commit.
    """
    # compat: si pasaron solo un int
    if isinstance(datos, int):
        nuevo_estado = datos
        lote_info = {}
    else:
        nuevo_estado = datos.Estado
        lote_info = {
            'Numero_Lote': getattr(datos, 'Numero_Lote', None),
            'Fecha_Vencimiento': getattr(datos, 'Fecha_Vencimiento', None),
        }
    try:
        orden = db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Orden_Produccion == id_orden
        ).with_for_update().first()
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")

        if orden.Estado == nuevo_estado:
            return _formato_orden(orden, db)

        # ── Órdenes generadas por un pedido: su gestión manual está atada al pedido ──
        if origen_manual and orden.ID_Venta:
            venta = db.query(Venta).filter(Venta.ID_Venta == orden.ID_Venta).first()
            venta_estado = venta.Estado if venta else None
            venta_label  = _VENTA_ESTADO_LABEL.get(venta_estado, "desconocido")

            # La cancelación de una orden ligada a un pedido baja siempre del
            # pedido, nunca a mano desde aquí (ni desde "Anular").
            if nuevo_estado == ESTADO_CANCELADA:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"El estado de la orden #{id_orden} lo controla el pedido "
                        f"#{orden.ID_Venta}: una orden generada por un pedido no se "
                        f"cancela por separado. Para cancelarla, cancela el pedido "
                        f"#{orden.ID_Venta} desde Gestión de Pedidos y la orden se "
                        f"cancelará en cadena."
                    ),
                )

            # El avance manual (iniciar, completar) solo se habilita cuando el
            # pedido ya entró en producción. Mientras siga «Pendiente» —esperando
            # confirmación o que el cliente acepte la fecha— la orden queda
            # bloqueada: primero se mueve el pedido.
            if venta_estado not in _ESTADOS_VENTA_PRODUCIENDO:
                if venta_estado == 1:
                    detalle = (
                        f"La orden #{id_orden} pertenece al pedido #{orden.ID_Venta}, "
                        f"que todavía está «Pendiente». Confirma el pedido en Gestión "
                        f"de Pedidos para poder iniciar y gestionar su producción."
                    )
                elif venta_estado in _ESTADOS_VENTA_FINALES:
                    detalle = (
                        f"La orden #{id_orden} pertenece al pedido #{orden.ID_Venta}, "
                        f"que está «{venta_label}»: su producción ya no se gestiona."
                    )
                else:
                    detalle = (
                        f"La orden #{id_orden} pertenece al pedido #{orden.ID_Venta} "
                        f"(actualmente «{venta_label}»). Su producción se habilita "
                        f"cuando el pedido está confirmado o en producción."
                    )
                raise HTTPException(status_code=400, detail=detalle)

        elif origen_manual and nuevo_estado == ESTADO_CANCELADA:
            # Orden suelta (sin pedido): cancelar es "Anular", no "cambiar estado".
            raise HTTPException(
                status_code=400,
                detail=(
                    "Para cancelar una orden se usa la acción «Anular» (el botón con "
                    "el ícono de prohibido), no el cambio de estado."
                ),
            )

        # Mapa de transiciones válidas — cualquier otra combinación es un error
        _TRANSICIONES_VALIDAS = {
            ESTADO_PENDIENTE:  {ESTADO_EN_PROCESO, ESTADO_CANCELADA},
            ESTADO_EN_PROCESO: {ESTADO_COMPLETADA, ESTADO_CANCELADA},
            ESTADO_COMPLETADA: set(),
            ESTADO_CANCELADA:  set(),
        }
        if nuevo_estado not in _TRANSICIONES_VALIDAS.get(orden.Estado, set()):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La orden #{id_orden} está «{_label_orden(orden.Estado)}» y desde "
                    f"ese estado no puede pasar a «{_label_orden(nuevo_estado)}». "
                    f"{_transiciones_texto(orden.Estado)}"
                ),
            )

        # Al iniciar (13=En proceso): validar ficha, descontar todos los insumos de la receta
        if nuevo_estado == ESTADO_EN_PROCESO and orden.Estado == ESTADO_PENDIENTE:
            # Mientras está Pendiente la orden usa la ficha vigente del producto
            # (que puede haber cambiado desde que se creó). A partir de aquí queda
            # congelada: el ID_Ficha con el que arranca es su snapshot.
            if orden.ID_Producto:
                ficha_auto = _ficha_vigente(db, orden.ID_Producto)
                if ficha_auto:
                    orden.ID_Ficha = ficha_auto.ID_Ficha

            if not orden.ID_Ficha:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "El producto no tiene ficha técnica y sin ella no se puede "
                        "iniciar la producción. Créala en Gestión de Productos."
                    ),
                )
            # Arrancar la orden APARTA los insumos; no los descuenta. El
            # descuento ocurre al completarla, que es cuando la harina de
            # verdad se convirtió en producto. Mientras tanto quedan pisados:
            # otra orden que los necesite no puede arrancar.
            plan = _plan_de_insumos(db, orden, bloquear=True)
            apartado = insumos_reservados(
                db, [i.ID_Insumo for i, _s, _n in plan], excluir_orden=id_orden,
            )
            for insumo, simbolo, necesario in plan:
                en_bodega = float(insumo.Stock_Actual or 0)
                reservado = apartado.get(insumo.ID_Insumo, 0.0)
                disponible = en_bodega - reservado
                if disponible + 1e-9 < necesario:
                    # Se distingue "no hay" de "lo tiene otra orden": mandar a
                    # comprar harina que está en el depósito no arregla nada.
                    if reservado > 0:
                        detalle = (
                            f"'{insumo.Nombre}' está apartado por otra orden en proceso: "
                            f"hacen falta {necesario:.4g} {simbolo}, hay {en_bodega:.4g} "
                            f"y {reservado:.4g} ya están comprometidos. "
                            "Completá o anulá esa orden primero."
                        )
                    else:
                        detalle = (
                            f"Stock insuficiente de '{insumo.Nombre}': necesario "
                            f"{necesario:.4g} {simbolo}, disponible {en_bodega:.4g} {simbolo}"
                        )
                    raise HTTPException(status_code=400, detail=detalle)

            if orden.ID_Venta:
                _sync_venta_por_ordenes(db, orden.ID_Venta, orden.ID_Orden_Produccion, ESTADO_EN_PROCESO)

        # Al completar (11=Completada): incrementar stock del producto y crear lote
        elif nuevo_estado == ESTADO_COMPLETADA and orden.Estado == ESTADO_EN_PROCESO:
            from dateutil.relativedelta import relativedelta

            # Completar es el momento en que la harina dejó de ser harina: acá
            # se descuenta de verdad, del stock y de los lotes (FEFO). Al
            # arrancar solo se había apartado.
            #
            # Se usa la ficha con la que arrancó la orden, no la vigente: si
            # alguien cambió la receta mientras se horneaba, se descuenta lo que
            # de verdad se usó.
            plan = _plan_de_insumos(db, orden, bloquear=True)
            for insumo, simbolo, necesario in plan:
                en_bodega = float(insumo.Stock_Actual or 0)
                if en_bodega + 1e-9 < necesario:
                    # Con los insumos apartados desde que arrancó, llegar acá
                    # significa que alguien movió el inventario por fuera.
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"No se puede completar: falta '{insumo.Nombre}'. "
                            f"La orden usa {necesario:.4g} {simbolo} y en el "
                            f"inventario quedan {en_bodega:.4g} {simbolo}. "
                            "Revisá si el stock se movió desde que arrancó."
                        ),
                    )
            for insumo, _simbolo, necesario in plan:
                _descontar_fefo(db, insumo.ID_Insumo, necesario)
                insumo.Stock_Actual = round(max(0.0, float(insumo.Stock_Actual or 0) - necesario), 4)
                _actualizar_estado_insumo(insumo)
                notificar_stock_insumo(db, insumo)

            producto = db.query(Producto).filter(
                Producto.ID_Producto == orden.ID_Producto
            ).with_for_update().first()
            if not producto:
                raise HTTPException(
                    status_code=404,
                    detail="El producto de esta orden ya no existe; no se puede completar la producción.",
                )
            producto.Stock = (producto.Stock or 0) + orden.Cantidad
            _actualizar_estado_producto(producto)
            notificar_stock_producto(db, producto)

            # Crear lote de producto. La vida útil sale de la ficha con la que
            # arrancó la orden (snapshot), no de la ficha actual del producto.
            hoy = _ahora_local()
            orden.Fecha_fin = hoy

            ficha = db.query(FichaTecnica).filter(
                FichaTecnica.ID_Ficha == orden.ID_Ficha
            ).first() if orden.ID_Ficha else None

            cantidad_vida = ficha.Dias_Vida_Util       if ficha and ficha.Dias_Vida_Util else None
            unidad_vida   = (ficha.Vida_Util_Unidad or 'dias') if ficha else 'dias'
            if cantidad_vida:
                if unidad_vida == 'meses':
                    fecha_vencimiento = hoy + relativedelta(months=cantidad_vida)
                elif unidad_vida == 'semanas':
                    fecha_vencimiento = hoy + timedelta(weeks=cantidad_vida)
                else:
                    fecha_vencimiento = hoy + timedelta(days=cantidad_vida)
            else:
                fecha_vencimiento = None

            numero_lote = lote_info.get('Numero_Lote') or f"LP-{orden.ID_Orden_Produccion}-{hoy.strftime('%Y%m%d')}"
            fecha_venc = lote_info.get('Fecha_Vencimiento') or fecha_vencimiento

            db.add(LoteProducto(
                ID_Orden_Produccion = orden.ID_Orden_Produccion,
                ID_Producto         = orden.ID_Producto,
                Numero_Lote         = numero_lote,
                Fecha_Produccion    = hoy,
                Fecha_Vencimiento   = fecha_venc,
                Cantidad            = orden.Cantidad,
                Estado              = 1,
            ))

            if orden.ID_Venta:
                _sync_venta_por_ordenes(db, orden.ID_Venta, orden.ID_Orden_Produccion, ESTADO_COMPLETADA)

        # Al cancelar (5): restaurar insumos si la orden estaba en proceso
        elif nuevo_estado == ESTADO_CANCELADA and orden.Estado == ESTADO_EN_PROCESO:
            # No hay insumos que devolver: arrancar solo los apartaba, y anular
            # la orden suelta esa reserva sola —se calcula sobre las órdenes en
            # proceso, y esta deja de serlo—. Antes acá se sumaba de vuelta al
            # inventario lo que se había descontado al arrancar; hacerlo ahora
            # crearía harina de la nada.
            if orden.ID_Venta:
                _sync_venta_por_ordenes(db, orden.ID_Venta, orden.ID_Orden_Produccion, ESTADO_CANCELADA)

        orden.Estado = nuevo_estado
        db.flush()
        if commit:
            db.commit()
        db.refresh(orden)
        return _formato_orden(orden, db)

    except Exception:
        # Deshacer lo que este cambio dejó a medias. Si el llamador maneja la
        # transacción (commit=False), es él quien hace el rollback.
        if commit:
            db.rollback()
        logger.exception(
            "Error en cambiar_estado id=%s nuevo_estado=%s", id_orden, nuevo_estado,
        )
        raise


def anular_orden(db: Session, id_orden: int) -> dict:
    """Anula una orden: la pasa al estado Cancelada conservando su historial.

    Reemplaza al borrado físico. Solo aplica a órdenes Pendiente o En proceso
    (si estaba En proceso se devuelven los insumos, como en cualquier cancelación).
    Las órdenes ligadas a un pedido se anulan cancelando el pedido, no aquí.
    """
    orden = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Orden_Produccion == id_orden
    ).with_for_update().first()
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    if orden.ID_Venta:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El estado de la orden #{id_orden} lo controla el pedido "
                f"#{orden.ID_Venta}. Para anularla, cancela el pedido #{orden.ID_Venta} "
                f"desde Gestión de Pedidos y la orden se cancelará en cadena."
            ),
        )
    if orden.Estado == ESTADO_CANCELADA:
        raise HTTPException(status_code=400, detail=f"La orden #{id_orden} ya está anulada.")
    if orden.Estado == ESTADO_COMPLETADA:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La orden #{id_orden} ya está «Completada» y no puede anularse: su "
                f"producto y su lote ya fueron generados."
            ),
        )

    return cambiar_estado(db, id_orden, ESTADO_CANCELADA)