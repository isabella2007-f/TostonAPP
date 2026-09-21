from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

_BOGOTA = ZoneInfo("America/Bogota")


def _now():
    return datetime.now(_BOGOTA).replace(tzinfo=None)

from sqlalchemy import func, case
from src.shared.services.models import (
    Venta, VentaXProducto, DetalleVenta, Producto, ProductoImagen, Usuario,
    Estado, Domicilio, CreditoCliente, MovimientoCredito,
    Descuento, DescuentoXUsuario, DescuentoXVenta, OrdenProduccion, FichaTecnica,
    LoteProducto, HistorialFechasPropuestas,
)

# Margen mínimo en días entre la fecha del envío anticipado y hoy
MARGEN_MINIMO_DIAS_ENVIO_ANTICIPADO = 1

# Rango de fechas de entrega permitido para pedidos.
# Espejo en frontend: DIAS_MIN_PRODUCCION / MESES_MAX_PEDIDO en utils/horario.js.
DIAS_MIN_PRODUCCION = 1
MESES_MAX_PEDIDO    = 6


def _imagen_producto(db: Session, id_producto: int) -> str | None:
    """URL de la primera imagen del producto (o None). Usa Producto_Imagenes."""
    img = db.query(ProductoImagen).filter(
        ProductoImagen.ID_Producto == id_producto
    ).first()
    return img.imagen if img else None
from src.shared.services.notificaciones_utils import notificar, descartar_notificacion, notificar_stock_producto
from src.shared.services.enums import TipoAccionFecha
from src.features.ventas.pedidos.services.estados import (
    EstadoPedido, validar_transicion,
)
from .schemas import VentaCreate, DomicilioVentaInput
from src.shared.services.observaciones_utils import observaciones_limpias
from src.shared.services.pagos_utils import (
    cobro_efectivo_pendiente, comprobante_sin_aprobar, es_pago_mixto,
    obtener_pago, pago_o_nuevo, tipo_cobro_efectivo,
    ESTADOS_RESUELTOS_OK, TIPO_ANTICIPO, TIPO_SALDO,
)
# El precio del domicilio ya NO es una constante: sale de Barrios.Precio ajustado
# por las ofertas activas del barrio ese día (función única del módulo
# Ubicaciones) y se CONGELA como snapshot en Domicilios al crear el pedido.
from src.features.ventas.ubicaciones.services.service import resolver_domicilio

# Porcentaje del pedido que el cliente debe anticipar cuando pide MÁS unidades de
# las que hay en stock (pedido especial / preorden). Regla de negocio del backend:
# nunca se toma del request, el cliente no puede alterarla.
PORCENTAJE_ANTICIPO_SOBRE_STOCK = Decimal("0.50")

# Los precios de venta al público ya incluyen IVA del 19%.
# Para extraerlo: base = precio / 1.19;  iva = precio - base.
_IVA_DIVISOR = Decimal("1.19")


def _desglosar_iva(monto_con_iva: Decimal) -> tuple[Decimal, Decimal]:
    """Extrae la base y el IVA de un monto que ya incluye el 19%.

    Retorna (base, iva) con redondeo al centavo.
    La suma base + iva siempre es igual al monto original.
    """
    base = (monto_con_iva / _IVA_DIVISOR).quantize(Decimal("0.01"))
    iva  = monto_con_iva - base
    return base, iva

#: Estado con el que queda un domicilio cancelado (catálogo de Estados).
#:
#: Lo usa la división de entregas para retirar del tablero el domicilio
#: original, que después de dividir ya no es un viaje sino una plantilla.
ESTADO_DOMICILIO_CANCELADO = 5

# Monto a partir del cual un pedido por encargo pide anticipo. Por debajo el
# trámite le cuesta más al cliente de lo que protege al negocio: un pedido chico
# que no se recoge se le vende al siguiente que entre.
UMBRAL_ANTICIPO = Decimal("100000")


def _pide_anticipo(total_pedido) -> bool:
    """Si este pedido tiene que dejar anticipo antes de avanzar.

    Puramente por monto: a partir de UMBRAL_ANTICIPO, sin importar si el
    pedido necesita producción o sale del stock del día. Antes solo se le
    pedía anticipo al pedido que había que fabricar; ahora un pedido grande
    arriesga plata del negocio (mercancía aparte, tiempo de preparación,
    domicilio) aunque no haya que hornear nada, así que el monto por sí solo
    ya lo justifica.
    """
    return Decimal(str(total_pedido)) > UMBRAL_ANTICIPO


def _calcular_anticipo(total_pedido: Decimal, credito_aplicado: Decimal) -> Decimal:
    """Cuánto hay que anticipar por un pedido que supera el stock.

    Se calcula sobre lo que QUEDA por pagar, es decir con el saldo a favor ya
    descontado: si el cliente puso plata suya, esa plata ya respalda el pedido y
    no tiene sentido volver a exigir la mitad del total bruto sobre lo demás.
    Es la cuenta que muestran el checkout de la web y la app, y este servidor
    tiene que pedir exactamente lo mismo que se le mostró al cliente.

    Redondea hacia arriba al peso, como el checkout: nunca se cobra de menos.
    """
    por_pagar = max(Decimal("0"), total_pedido - credito_aplicado)
    return (por_pagar * PORCENTAJE_ANTICIPO_SOBRE_STOCK).quantize(
        Decimal("1"), rounding=ROUND_CEILING
    )


def _fecha_minima_entrega(db: Session):
    """Primer día en que se puede prometer una entrega.

    Hoy mismo, si todavía se puede recibir el pedido (día de atención y antes
    de la hora de cierre); si no, el próximo día de atención. Espejo en Python
    de `primeraFechaValida` (frontend, `utils/horario.js`) — la misma regla no
    puede vivir solo del lado del cliente.
    """
    from src.shared.services.models import ConfiguracionLanding
    cfg = db.query(ConfiguracionLanding).filter(ConfiguracionLanding.ID == 1).first()
    hora_cierre = (getattr(cfg, "hora_cierre", None) or "20:00")
    dias_csv    = (getattr(cfg, "dias_atencion", None) or "1,2,3,4,5,6,7")
    dias = {
        int(d) for d in dias_csv.split(",")
        if d.strip().isdigit() and 1 <= int(d) <= 7
    } or {1, 2, 3, 4, 5, 6, 7}

    ahora   = _now()
    hoy_iso = ahora.isoweekday()
    try:
        hh, mm = (hora_cierre.split(":") + ["0", "0"])[:2]
        cierre_minutos = int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        cierre_minutos = 20 * 60
    ahora_minutos = ahora.hour * 60 + ahora.minute

    if hoy_iso in dias and ahora_minutos < cierre_minutos:
        return ahora.date()

    for i in range(1, 8):
        d = ((hoy_iso - 1 + i) % 7) + 1
        if d in dias:
            return (ahora + timedelta(days=i)).date()
    return ahora.date()


def _validar_fecha_entrega_esperada(db: Session, fecha_entrega) -> None:
    """La fecha límite que pide el cliente no puede ser imposible: ni antes
    del margen de producción, ni más allá de MESES_MAX_PEDIDO meses."""
    if not fecha_entrega:
        raise HTTPException(status_code=400, detail="Selecciona para cuándo necesitas tu pedido")
    fecha_date = fecha_entrega.date() if hasattr(fecha_entrega, "date") else fecha_entrega
    hoy = _now().date()
    minima = max(_fecha_minima_entrega(db), hoy + timedelta(days=DIAS_MIN_PRODUCCION))
    if fecha_date < minima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha más próxima disponible para tu pedido es {minima.isoformat()}",
        )
    maxima = hoy + relativedelta(months=MESES_MAX_PEDIDO)
    if fecha_date > maxima:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La fecha de entrega no puede ser después del {maxima.isoformat()} "
                f"({MESES_MAX_PEDIDO} meses desde hoy)"
            ),
        )


def _es_transferencia(metodo: str | None) -> bool:
    return "transfer" in (metodo or "").strip().lower()


def _es_mixto(metodo: str | None) -> bool:
    """Pedido repartido entre efectivo y transferencia.

    Lleva las dos cargas: comprobante por la parte transferida (se paga al
    hacer el pedido) y cobro en mano por la parte en efectivo (se recoge al
    entregar). Las reglas de abajo lo tratan como los dos a la vez.
    """
    return "mixto" in (metodo or "").strip().lower()


def _mixto_bloqueado_por_anticipo(metodo: str | None, pide_anticipo: bool) -> bool:
    """True si el pedido pide anticipo y lo quieren pagar con el método mixto.

    El anticipo existe para respaldar lo que hay que producir ANTES de
    entregarlo. La parte en efectivo de un mixto se cobra AL ENTREGAR, o sea
    después de producir: no respalda nada. Y su comprobante cubre solo la parte
    transferida, que puede quedar muy por debajo del 50% exigido.

    Solo se le cierra el mixto al pedido que de verdad pide anticipo
    (`_pide_anticipo`). Antes se le cerraba a cualquiera que superara el stock,
    aunque no tuviera que anticipar nada.
    """
    return _es_mixto(metodo) and bool(pide_anticipo)


def _partir_pago_mixto(total: Decimal, monto_efectivo) -> tuple[Decimal, Decimal]:
    """Reparte el total entre efectivo y transferencia.

    El cliente dice cuánta plata va a poner en efectivo —la que tiene encima,
    que casi nunca es un porcentaje redondo— y el resto se transfiere. El monto
    se recorta contra el total REAL calculado aquí: nadie puede declarar que
    paga en efectivo más de lo que vale el pedido, ni un monto negativo.
    """
    pedido = Decimal(str(monto_efectivo or 0))
    efectivo = max(Decimal("0"), min(pedido, total)).quantize(Decimal("0.01"))
    return efectivo, total - efectivo


def _productos_no_publicados(lineas: list[dict]) -> list[str]:
    """Nombres de los productos del pedido que ya no están en la tienda.

    El carrito vive en el dispositivo del cliente, así que un producto que el
    admin desactiva desaparece del catálogo pero sigue en el carrito de quien
    lo había agregado antes. Sin este control el pedido entraba igual y el
    negocio quedaba comprometido a vender algo que había sacado de la venta.
    """
    return [l["nombre"] for l in lineas if not l.get("publicado")]


def _evaluar_lineas_pedido(db: Session, productos_input) -> tuple[list[dict], Decimal]:
    """Valida los productos contra el stock REAL y calcula el subtotal.

    Bloquea la fila de cada producto con with_for_update(): dos pedidos
    simultáneos del mismo producto se serializan, así no pueden leer el mismo
    stock y creer ambos que les alcanza (condición de carrera del punto 9).

    Cada línea devuelve cuántas unidades caben en stock y cuántas van por encima
    (preorden). El stock NO se toca aquí: el descuento real sigue ocurriendo al
    confirmar (tienda) o entregar (domicilio), como en el flujo actual.
    """
    lineas: list[dict] = []
    subtotal = Decimal("0")

    for p in productos_input:
        producto = (
            db.query(Producto)
            .filter(Producto.ID_Producto == p.ID_Producto)
            .with_for_update()
            .first()
        )
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto {p.ID_Producto} no encontrado")

        stock    = producto.Stock or 0
        cantidad = p.Cantidad
        preorden = max(0, cantidad - stock)

        precio    = producto.Precio_venta or Decimal("0")
        subtotal += precio * Decimal(str(cantidad))

        lineas.append({
            "ID_Producto": p.ID_Producto,
            "nombre":      producto.nombre,
            "cantidad":    cantidad,
            "stock":       stock,
            "preorden":    preorden,
            "precio":      precio,
            # Si el admin lo sacó de la tienda ya no se le puede vender al
            # cliente, aunque siga en su carrito. Lo decide quien llama.
            "publicado":   int(getattr(producto, "Publicado", 0) or 0),
        })

    return lineas, subtotal


_ESTADO_VENTA_LABEL = {
    1:  "Pendiente",
    4:  "Confirmado",
    5:  "Cancelado",
    8:  "Entregado",
    9:  "En camino",
    10: "Asignado",
    11: "Listo",
    13: "En producción",
    16: "Fecha propuesta",
    17: "Fecha rechazada",
    18: "Parcialmente entregado",
    19: "Escalado a admin",
    20: "Esperando pago",
    21: "Fecha propuesta final",
    22: "Retenido en tienda",
    23: "En ruta de retorno",
}

# Cuántas veces puede el cliente rechazar una fecha antes de que el pedido
# pase a ESCALADO_A_ADMIN para que un administrador lo gestione manualmente.
LIMITE_INTENTOS_RECHAZO = 3

def _label_estado(db: Session, id_estado: int) -> str:
    if id_estado in _ESTADO_VENTA_LABEL:
        return _ESTADO_VENTA_LABEL[id_estado]
    estado = db.query(Estado).filter(Estado.ID_Estados == id_estado).first()
    return estado.Estado if estado else None


def _descontar_fefo_producto(db: Session, id_producto: int, cantidad: int) -> None:
    """Descuenta `cantidad` de los lotes del producto en orden FEFO (vence primero = sale primero)."""
    from sqlalchemy import case as _case
    lotes = (
        db.query(LoteProducto)
        .filter(
            LoteProducto.ID_Producto == id_producto,
            LoteProducto.Cantidad    >  0,
        )
        .order_by(
            _case((LoteProducto.Fecha_Vencimiento.is_(None), 1), else_=0),
            LoteProducto.Fecha_Vencimiento.asc(),
        )
        .with_for_update()
        .all()
    )
    restante = int(cantidad)
    for lote in lotes:
        if restante <= 0:
            break
        disponible = int(lote.Cantidad or 0)
        tomar      = min(disponible, restante)
        lote.Cantidad = disponible - tomar
        restante -= tomar


def _restaurar_fefo_producto(db: Session, id_producto: int, cantidad: int) -> None:
    """Devuelve `cantidad` a los lotes del producto en orden FEFO inverso (último en vencer = primero en recibir)."""
    from sqlalchemy import case as _case
    lotes = (
        db.query(LoteProducto)
        .filter(LoteProducto.ID_Producto == id_producto)
        .order_by(
            _case((LoteProducto.Fecha_Vencimiento.is_(None), 0), else_=1),
            LoteProducto.Fecha_Vencimiento.desc(),
        )
        .with_for_update()
        .all()
    )
    restante = int(cantidad)
    for lote in lotes:
        if restante <= 0:
            break
        lote.Cantidad = (lote.Cantidad or 0) + restante
        restante = 0


# Qué parte de cada línea se descuenta del stock. Un pedido por encima del
# stock tiene dos mitades que salen del inventario en momentos distintos: lo
# que ya estaba en la vitrina y lo que hubo que hornear.
PARTE_DISPONIBLE = "disponible"   # lo que ya existía cuando se hizo el pedido
PARTE_PREORDEN   = "preorden"     # el faltante, que llega cuando cierra la orden
PARTE_TODO       = "todo"         # la línea completa


ORDEN_COMPLETADA = 11


def anticipo_vuelve_solo(db: Session, id_venta: int, id_productos=None) -> bool:
    """¿Se le abona el anticipo al cliente al cancelar, sin preguntarle a nadie?

    Solo mientras no se haya horneado. Si alguna orden de producción llegó a
    completarse, los insumos ya se gastaron y qué pasa con esa plata lo acuerdan
    el cliente y quien atiende: el sistema no decide por ellos.

    Antes se devolvía siempre —también después de hornear, con la panadería ya
    con el gasto encima— y las pruebas pedían lo contrario, que no volviera
    nunca, dejando al cliente que cancela a tiempo persiguiendo su plata.

    [id_productos] acota la pregunta a esos productos. Al cancelar UN grupo de
    envío, lo que importa es si se horneó lo de ESE grupo: que el otro grupo ya
    esté en el horno no tiene por qué congelarle al cliente la plata de este,
    donde no se gastó un solo insumo.
    """
    consulta = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Venta == id_venta,
        OrdenProduccion.Estado == ORDEN_COMPLETADA,
    )
    if id_productos is not None:
        # Un grupo sin productos no tiene nada horneado que reclamar.
        if not id_productos:
            return True
        consulta = consulta.filter(OrdenProduccion.ID_Producto.in_(id_productos))
    return consulta.first() is None


def _abonar_credito(db: Session, id_usuario: int, monto: Decimal, id_venta: int) -> None:
    """Le devuelve plata al cliente como saldo a favor.

    Crea la cuenta si no existía: al cliente que nunca había tenido saldo no
    se le devolvía nada, porque no había fila que sumarle.

    with_for_update() evita que dos abonos concurrentes al mismo cliente
    (ej. dos cancelaciones a la vez) lean el mismo Saldo y uno se pierda al
    escribir encima del otro.
    """
    if monto <= 0:
        return
    credito = db.query(CreditoCliente).filter(
        CreditoCliente.ID_Usuario == id_usuario
    ).with_for_update().first()
    if not credito:
        credito = CreditoCliente(
            ID_Usuario=id_usuario, Saldo=Decimal("0"), Fecha_Update=_now(),
        )
        db.add(credito)
        db.flush()
    credito.Saldo        += monto
    credito.Fecha_Update  = _now()
    db.add(MovimientoCredito(
        ID_Credito    = credito.ID_Credito,
        ID_Devolucion = None,
        ID_Venta      = id_venta,
        Tipo          = "recarga",
        Monto         = monto,
        Fecha         = _now(),
    ))


def _descontar_stock_venta(db: Session, id_venta: int, parte: str = PARTE_TODO) -> None:
    """Descuenta del stock lo vendido en la venta, bloqueando cada producto.

    with_for_update() evita que dos pedidos que se confirman/entregan a la vez
    lean el mismo stock y lo descuenten dos veces sobre el mismo valor.

    `parte` existe por el pedido que se recoge en tienda y pide más de lo que
    hay: su stock se descuenta AL CONFIRMAR, o sea antes de que la orden de
    producción exista. Descontando ahí la línea entera, el sobrante se perdía
    contra el tope de 0 y las unidades que después producía la orden se
    sumaban al stock y ya nunca salían: el cliente se llevaba 6 tortas y el
    inventario seguía mostrando las 4 horneadas para él.

    Ahora al confirmar sale lo que de verdad hay (PARTE_DISPONIBLE) y al
    entregar sale el faltante ya producido (PARTE_PREORDEN). El pedido a
    domicilio no se parte: su stock sale entero al entregar, cuando la
    producción ya cerró.

    PARTE_DISPONIBLE es idempotente por pedido (marca `Venta.Stock_Reservado`,
    3.6): puede dispararse antes de CONFIRMADO, de forma perezosa al cerrar la
    ventana de 10 minutos, así que el punto de entrada original (al confirmar)
    tiene que poder no-operar si ya se reservó antes, en vez de descontar dos
    veces. PARTE_PREORDEN y PARTE_TODO (entrega a domicilio) no lo necesitan:
    ocurren una sola vez, en ENTREGADO, protegidas por la máquina de estados.
    """
    if parte == PARTE_DISPONIBLE:
        venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).with_for_update().first()
        if venta and getattr(venta, "Stock_Reservado", 0):
            return
        if venta:
            venta.Stock_Reservado = 1

    items = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
    for item in items:
        preorden = item.Cantidad_Preorden or 0
        if parte == PARTE_DISPONIBLE:
            cantidad = max(0, (item.Cantidad or 0) - preorden)
        elif parte == PARTE_PREORDEN:
            cantidad = preorden
        else:
            cantidad = item.Cantidad or 0
        if cantidad <= 0:
            continue
        producto = (
            db.query(Producto)
            .filter(Producto.ID_Producto == item.ID_Producto)
            .with_for_update()
            .first()
        )
        if not producto:
            continue
        producto.Stock = max(0, (producto.Stock or 0) - cantidad)
        _actualizar_estado_producto(producto)
        notificar_stock_producto(db, producto)
        # Descontar también de los lotes FEFO para mantener el inventario por lote correcto
        _descontar_fefo_producto(db, item.ID_Producto, cantidad)


def _actualizar_estado_producto(producto: Producto) -> None:
    stock  = producto.Stock or 0
    minimo = getattr(producto, "Stock_Minimo", 0) or 0
    if stock == 0:
        producto.Estado = 15
    elif stock <= minimo:
        producto.Estado = 14
    else:
        producto.Estado = 1


def _formato_venta(venta: Venta, db: Session, *, dxv_map=None) -> dict:
    """Construye la respuesta completa de una venta.

    dxv_map: pre-cargado {id_venta: DescuentoXVenta} para el caso de listado;
    cuando es None usa db.query() igual que antes (op. individual sin cambio).
    Los demás sub-datos usan relationships: lazy-load en op. individuales,
    eager-load (selectinload) en listados — resultado idéntico.
    """
    usuario = venta.usuario

    productos = []
    requiere_produccion = False
    for v in venta.productos:
        producto = v.producto
        # Precio al momento de la venta (snapshot). Fallback al precio actual
        # solo para líneas creadas antes de que existiera Precio_Unitario.
        if v.Precio_Unitario is not None:
            precio = v.Precio_Unitario
        else:
            precio = producto.Precio_venta if producto else Decimal("0")
        if getattr(producto, "Requiere_Produccion", 0):
            requiere_produccion = True
        imagen = producto.imagenes[0].imagen if (producto and producto.imagenes) else None
        productos.append({
            "ID_Producto":     v.ID_Producto,
            "nombre_producto": producto.nombre if producto else None,
            "Cantidad":        v.Cantidad,
            "precio_unitario": precio,
            "subtotal":        precio * Decimal(str(v.Cantidad)),
            "imagen":          imagen,
            "cantidad_preorden": getattr(v, "Cantidad_Preorden", 0) or 0,
            "stock_disponible":  (producto.Stock or 0) if producto else 0,
        })

    detalle          = venta.detalle[0] if venta.detalle else None
    credito_aplicado = detalle.Descuento if detalle else Decimal("0")
    iva              = detalle.IVA if detalle else Decimal("0")

    if dxv_map is not None:
        dxv = dxv_map.get(venta.ID_Venta)
    else:
        dxv = db.query(DescuentoXVenta).filter(DescuentoXVenta.ID_Venta == venta.ID_Venta).first()
    descuento_aplicado = dxv.Monto_Aplicado if dxv else Decimal("0")

    domicilio = venta.domicilios[0] if venta.domicilios else None
    subtotal_bruto = sum(p["subtotal"] for p in productos)

    # Quién lo lleva.
    dom_con_repartidor = next(
        (d for d in ([domicilio] if domicilio else []) + list(venta.domicilios)
         if d is not None and d.ID_Empleado and d.Estado != 5),
        None,
    )
    domiciliario          = None
    cedula_domiciliario   = None
    celular_domiciliario  = None
    id_repartidor = dom_con_repartidor.ID_Empleado if dom_con_repartidor else None
    if dom_con_repartidor:
        emp = dom_con_repartidor.empleado
        if emp:
            domiciliario         = f"{emp.Nombre} {emp.Apellidos}"
            cedula_domiciliario  = getattr(emp, "Cedula",   None)
            celular_domiciliario = getattr(emp, "Telefono", None)

    ordenes_pendientes = sum(
        1 for o in venta.ordenes_produccion
        if o.Estado not in (11, 5)
    )
    ordenes_en_espera = sum(
        1 for o in venta.ordenes_produccion
        if o.Estado == 1
    )

    # Filas de Pagos de esta venta (como mucho una por Tipo — ver `Pago` en
    # models.py). `venta.pagos` ya viene cargada por relationship; se evita un
    # segundo `obtener_pago()` que dispararía una query aparte por venta.
    _pago_anticipo = next((p for p in venta.pagos if p.Tipo == TIPO_ANTICIPO), None)
    _pago_saldo    = next((p for p in venta.pagos if p.Tipo == TIPO_SALDO), None)
    _es_mixto_fmt  = es_pago_mixto(venta.Metodo_Pago)
    _motivo_rechazo_pago = None
    if _pago_saldo and _pago_saldo.Estado == "rechazado":
        _motivo_rechazo_pago = _pago_saldo.Motivo_Rechazo
    elif _pago_anticipo and _pago_anticipo.Estado == "rechazado":
        _motivo_rechazo_pago = _pago_anticipo.Motivo_Rechazo

    return {
        "ID_Venta":           venta.ID_Venta,
        "ID_Usuario":         venta.ID_Usuario,
        "nombre_cliente":          f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
        "correo_cliente":          usuario.Correo         if usuario else None,
        "telefono_cliente":        usuario.Telefono        if usuario else None,
        "cedula_cliente":          getattr(usuario, "Cedula",          None) if usuario else None,
        "tipo_documento_cliente":  getattr(usuario, "Tipo_Documento",  None) if usuario else None,
        "Total":              venta.Total,
        "subtotal_bruto":     subtotal_bruto,
        "credito_aplicado":   credito_aplicado,
        "descuento_aplicado": descuento_aplicado,
        "Estado":             venta.Estado,
        "estado_label":       _label_estado(db, venta.Estado) if venta.Estado else None,
        "Metodo_Pago":            venta.Metodo_Pago,
        "monto_efectivo":         (_pago_saldo.Monto if (_es_mixto_fmt and _pago_saldo) else None),
        "monto_transferencia":    (_pago_anticipo.Monto if (_es_mixto_fmt and _pago_anticipo) else None),
        "Fecha_Venta":            venta.Fecha_Venta,
        "Fecha_pedido":           venta.Fecha_pedido,
        "Fecha_entrega":          getattr(venta, "Fecha_entrega", None),
        "Fecha_entrega_esperada": venta.Fecha_entrega_esperada,
        "productos":              productos,
        "comprobante_pago":             _pago_anticipo.Comprobante_Url if _pago_anticipo else None,
        "tiene_domicilio":              domicilio is not None,
        "ID_Domicilio":                 domicilio.ID_Domicilio          if domicilio else None,
        "direccion_entrega":            domicilio.Direccion_entrega      if domicilio else None,
        "municipio_entrega":            domicilio.Municipio_entrega      if domicilio else None,
        "departamento_entrega":         domicilio.Departamento_entrega   if domicilio else None,
        # Precio del domicilio: snapshot congelado del barrio + ofertas del día.
        # No se recalcula aunque después cambie el precio del barrio o una oferta.
        "ID_Barrio":                    domicilio.ID_Barrio             if domicilio else None,
        "barrio_entrega":               (domicilio.barrio.Nombre if (domicilio and domicilio.barrio) else None),
        "precio_domicilio_base":        domicilio.Precio_Domicilio_Base  if domicilio else None,
        "precio_domicilio_final":       domicilio.Precio_Domicilio_Final if domicilio else None,
        "desglose_domicilio":           (domicilio.Desglose_Ofertas if domicilio else None),
        # Mismo filtro que en domicilios: el resumen del pedido mostraba la
        # línea [COBRO|...] pegada a las notas del cliente.
        "observaciones_domicilio":      observaciones_limpias(domicilio.Observaciones) if domicilio else None,
        "observaciones_admin":          observaciones_limpias(getattr(domicilio, "Observaciones_Admin", None)) if domicilio else None,
        "observaciones_repartidor":     observaciones_limpias(getattr(domicilio, "Observaciones_Repartidor", None)) if domicilio else None,
        "nombre_domiciliario":          domiciliario,
        "cedula_domiciliario":          cedula_domiciliario,
        "celular_domiciliario":         celular_domiciliario,
        "ID_Empleado":                  id_repartidor,
        "ordenes_produccion_pendientes": ordenes_pendientes,
        "ordenes_en_espera":             ordenes_en_espera,
        "requiere_produccion":           requiere_produccion,
        # Pedido especial por encima del stock + anticipo del 50% (calculado y
        # verificado en backend al crear la venta).
        "sobre_stock":             bool(getattr(venta, "Sobre_Stock", 0)),
        "anticipo_requerido":      getattr(venta, "Anticipo_Requerido", None),
        "anticipo_pagado":         (_pago_anticipo.Monto_Verificado_Creacion if _pago_anticipo else None),
        "requiere_anticipo":       bool(getattr(venta, "Requiere_Anticipo", 0)),
        "anticipo_monto":          (_pago_anticipo.Monto if _pago_anticipo else None),
        "anticipo_metodo_pago":    (_pago_anticipo.Metodo_Pago if _pago_anticipo else None),
        "anticipo_comprobante_url": (_pago_anticipo.Comprobante_Url if _pago_anticipo else None),
        "anticipo_registrado":       bool(_pago_anticipo and _pago_anticipo.Monto),
        "pago_final_registrado":     bool(_pago_saldo and _pago_saldo.Estado in ESTADOS_RESUELTOS_OK),
        "pago_final_monto":          (_pago_saldo.Monto if _pago_saldo else None),
        "pago_final_metodo_pago":    (_pago_saldo.Metodo_Pago if _pago_saldo else None),
        "pago_final_comprobante_url": (_pago_saldo.Comprobante_Url if _pago_saldo else None),
        "pago_final_fecha":          (_pago_saldo.Fecha_Resolucion if _pago_saldo else None),
        "estado_pago":               getattr(venta, "Estado_Pago", "pendiente"),
        "motivo_rechazo_comprobante": _motivo_rechazo_pago,
        # Segundo comprobante: el saldo restante tras el anticipo (3.10).
        "saldo_comprobante_url": (_pago_saldo.Comprobante_Url if _pago_saldo else None),
        "intentos_rechazo_comprobante_anticipo": int((_pago_anticipo.Intentos_Rechazo if _pago_anticipo else 0) or 0),
        "intentos_rechazo_comprobante_saldo":    int((_pago_saldo.Intentos_Rechazo if _pago_saldo else 0) or 0),
        # 3.7: marca de tiempo de cuándo entró a "Retenido en tienda", para
        # que el frontend calcule las ventanas de 24h/48h (evaluación
        # perezosa, sin scheduler — el backend valida lo mismo al actuar).
        "fecha_retenido_en_tienda": getattr(venta, "Fecha_Retenido_En_Tienda", None),
        # True solo en los pedidos a los que hay que proponerles fecha
        # (sobre stock o producción). Los normales no la necesitan.
        "requiere_fecha_propuesta": requiere_fecha_propuesta(db, venta),
        "fecha_rechazada": getattr(venta, "Fecha_Rechazada", None),
        "intentos_rechazo": int(getattr(venta, "intentos_rechazo", 0) or 0),
        # A partir de este número de rechazos, el frontend resalta con más
        # énfasis el canal de excepción (hablar con el admin) — no bloquea ni
        # cancela nada por sí solo, es puramente informativo.
        "resaltar_canal_excepcion": int(getattr(venta, "intentos_rechazo", 0) or 0) >= LIMITE_INTENTOS_RECHAZO,
        # None = no contestó, True = quiere todo junto el domingo, False = prefiere recibir lo disponible ya
        "envio_completo_domingo": (
            None if getattr(venta, "Envio_Completo_Domingo", None) is None
            else bool(venta.Envio_Completo_Domingo)
        ),
        # Suma de los domicilios que de verdad paga el pedido: el snapshot único.
        "costo_domicilio_total": _costo_domicilio_total(domicilio),
        "iva_total":     getattr(venta, "IVA_Total",     None),
        "subtotal_base": getattr(venta, "Subtotal_Base", None),
    }


def _costo_domicilio_total(domicilio) -> int:
    """Un domicilio por viaje: total de domicilio que refleja `Venta.Total`."""
    return int(domicilio.Precio_Domicilio_Final or 0) if domicilio else 0


def _aplicar_credito(
    db: Session,
    id_usuario: int,
    monto_restante: Decimal,
    id_venta: int,
    tope: Decimal | None = None,
) -> Decimal:
    # with_for_update() bloquea la fila de crédito hasta el commit de crear_venta:
    # evita que dos compras simultáneas gasten el mismo saldo (condición de carrera).
    credito = db.query(CreditoCliente).filter(
        CreditoCliente.ID_Usuario == id_usuario
    ).with_for_update().first()

    if not credito or credito.Saldo <= 0:
        return Decimal("0")

    # El monto usado se recalcula 100% en backend: min(saldo real, total real del
    # pedido). El cliente no puede manipular cuánto crédito se descuenta.
    credito_usado = min(credito.Saldo, monto_restante)

    # El cliente puede gastar solo una parte y guardar el resto para después.
    # Lo que llega del checkout es un tope, nunca un permiso: si pide más de lo
    # que tiene o más de lo que cuesta el pedido, manda el mínimo de arriba.
    if tope is not None:
        credito_usado = min(credito_usado, max(Decimal(str(tope)), Decimal("0")))

    if credito_usado <= 0:
        return Decimal("0")

    credito.Saldo       -= credito_usado
    credito.Fecha_Update = _now()

    db.add(MovimientoCredito(
        ID_Credito    = credito.ID_Credito,
        ID_Devolucion = None,
        ID_Venta      = id_venta,
        Tipo          = "uso",
        Monto         = credito_usado,
        Fecha         = _now(),
    ))
    return credito_usado


def _aplicar_descuento(
    db: Session,
    id_usuario: int,
    codigo: str,
    monto_restante: Decimal,
    id_venta: int
) -> Decimal:
    descuento = None

    if codigo:
        descuento = db.query(Descuento).filter(
            Descuento.Codigo == codigo,
            Descuento.Estado == 1,
        ).first()
        if descuento:
            if descuento.Fecha_Fin and descuento.Fecha_Fin < _now():
                raise HTTPException(status_code=400, detail="El cupón ha vencido")
            if descuento.Usos_Max and descuento.Usos_Actuales >= descuento.Usos_Max:
                raise HTTPException(status_code=400, detail="El cupón ha alcanzado su límite de usos")

    if not descuento:
        asignacion = db.query(DescuentoXUsuario).filter(
            DescuentoXUsuario.ID_Usuario == id_usuario,
            DescuentoXUsuario.Usado      == False,
        ).join(Descuento).filter(Descuento.Estado == 1).first()

        if asignacion:
            descuento = db.query(Descuento).filter(
                Descuento.ID_Descuento == asignacion.ID_Descuento
            ).first()

    if not descuento:
        usuario = db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first()
        if usuario and usuario.Fecha_creacion:
            meses     = (_now() - usuario.Fecha_creacion).days // 30
            descuento = (
                db.query(Descuento)
                .filter(
                    Descuento.Tipo          == "antiguedad",
                    Descuento.Meses_Minimos <= meses,
                    Descuento.Estado        == 1,
                )
                .order_by(Descuento.Porcentaje.desc())
                .first()
            )

    if not descuento:
        return Decimal("0")

    monto_descontado = (monto_restante * descuento.Porcentaje / 100).quantize(Decimal("0.01"))

    db.add(DescuentoXVenta(
        ID_Venta       = id_venta,
        ID_Descuento   = descuento.ID_Descuento,
        Monto_Aplicado = monto_descontado,
    ))

    descuento.Usos_Actuales += 1

    if descuento.Tipo == "emision":
        asignacion = db.query(DescuentoXUsuario).filter(
            DescuentoXUsuario.ID_Descuento == descuento.ID_Descuento,
            DescuentoXUsuario.ID_Usuario   == id_usuario,
        ).first()
        if asignacion:
            asignacion.Usado = True

    return monto_descontado


def _batch_ventas(ventas: list, db: Session) -> list:
    """Formatea una lista de ventas con queries en lote. Evita N+1."""
    if not ventas:
        return []

    venta_ids   = [v.ID_Venta   for v in ventas]
    usuario_ids = list({v.ID_Usuario for v in ventas if v.ID_Usuario})

    # Batch 0: filas de Pagos (anticipo/saldo) de estas ventas — como mucho
    # una por Tipo (ver `Pago` en models.py). Mismo patrón que `_formato_venta`.
    pagos_map: dict = {}
    if venta_ids:
        from src.shared.services.models import Pago
        for pg in db.query(Pago).filter(Pago.ID_Venta.in_(venta_ids)).all():
            pagos_map[(pg.ID_Venta, pg.Tipo)] = pg

    # Batch 1: clientes
    usuarios = {u.ID_Usuario: u for u in
                db.query(Usuario).filter(Usuario.ID_Usuario.in_(usuario_ids)).all()} if usuario_ids else {}

    # Batch 2: VentaXProducto
    vxp_all = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta.in_(venta_ids)).all()
    vxp_by_venta: dict = {}
    for vxp in vxp_all:
        vxp_by_venta.setdefault(vxp.ID_Venta, []).append(vxp)

    # Batch 3: productos
    prod_ids = list({v.ID_Producto for v in vxp_all if v.ID_Producto})
    productos = {p.ID_Producto: p for p in
                 db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()} if prod_ids else {}

    # Batch 4: primera imagen por producto
    imagenes_map: dict = {}
    if prod_ids:
        for img in db.query(ProductoImagen).filter(ProductoImagen.ID_Producto.in_(prod_ids)).all():
            if img.ID_Producto not in imagenes_map:
                imagenes_map[img.ID_Producto] = img.imagen

    # Batch 5: detalles de venta
    detalles = {d.ID_Venta: d for d in
                db.query(DetalleVenta).filter(DetalleVenta.ID_Venta.in_(venta_ids)).all()}

    # Batch 6: descuentos por venta
    dxvs = {d.ID_Venta: d for d in
            db.query(DescuentoXVenta).filter(DescuentoXVenta.ID_Venta.in_(venta_ids)).all()}

    # Batch 7: domicilios
    #
    # Gana el que tiene repartidor asignado; entre iguales, cualquiera.
    domicilios = {}
    for d in db.query(Domicilio).filter(Domicilio.ID_Venta.in_(venta_ids)).all():
        if d.Estado == 5:                      # cancelado: no cuenta
            continue
        actual = domicilios.get(d.ID_Venta)
        if actual is None:
            domicilios[d.ID_Venta] = d
        elif d.ID_Empleado and not actual.ID_Empleado:
            domicilios[d.ID_Venta] = d

    # Batch 8: repartidores
    emp_ids = list({d.ID_Empleado for d in domicilios.values() if d.ID_Empleado})
    repartidores = {u.ID_Usuario: u for u in
                    db.query(Usuario).filter(Usuario.ID_Usuario.in_(emp_ids)).all()} if emp_ids else {}

    # Batch 9: órdenes pendientes por venta (COUNT total + en espera=Pendiente)
    ordenes_rows = (
        db.query(
            OrdenProduccion.ID_Venta,
            func.count(OrdenProduccion.ID_Orden_Produccion).label("cnt"),
            func.sum(case((OrdenProduccion.Estado == 1, 1), else_=0)).label("espera"),
        )
        .filter(OrdenProduccion.ID_Venta.in_(venta_ids),
                OrdenProduccion.Estado.notin_([11, 5]))
        .group_by(OrdenProduccion.ID_Venta)
        .all()
    )
    ordenes_counts  = {row.ID_Venta: row.cnt    for row in ordenes_rows}
    ordenes_espera  = {row.ID_Venta: row.espera for row in ordenes_rows}

    result = []
    for venta in ventas:
        usuario    = usuarios.get(venta.ID_Usuario)
        vxp_list   = vxp_by_venta.get(venta.ID_Venta, [])
        detalle    = detalles.get(venta.ID_Venta)
        dxv        = dxvs.get(venta.ID_Venta)
        dom        = domicilios.get(venta.ID_Venta)
        repartidor = repartidores.get(dom.ID_Empleado) if dom and dom.ID_Empleado else None

        prods_list          = []
        requiere_produccion = False
        for v in vxp_list:
            prod  = productos.get(v.ID_Producto)
            precio = prod.Precio_venta if prod else Decimal("0")
            if getattr(prod, "Requiere_Produccion", 0):
                requiere_produccion = True
            prods_list.append({
                "ID_Producto":       v.ID_Producto,
                "nombre_producto":   prod.nombre if prod else None,
                "Cantidad":          v.Cantidad,
                "precio_unitario":   precio,
                "subtotal":          precio * Decimal(str(v.Cantidad)),
                "imagen":            imagenes_map.get(v.ID_Producto),
                "cantidad_preorden": getattr(v, "Cantidad_Preorden", 0) or 0,
                "stock_disponible":  (prod.Stock or 0) if prod else 0,
            })

        credito_aplicado   = detalle.Descuento        if detalle else Decimal("0")
        descuento_aplicado = dxv.Monto_Aplicado       if dxv     else Decimal("0")
        subtotal_bruto     = sum(p["subtotal"] for p in prods_list)
        domiciliario         = (f"{repartidor.Nombre} {repartidor.Apellidos}"
                                if repartidor else None)
        cedula_domiciliario  = (getattr(repartidor, "Cedula",   None) if repartidor else None)
        celular_domiciliario = (getattr(repartidor, "Telefono", None) if repartidor else None)

        # requiere_fecha_propuesta: usa el snapshot guardado al crear la venta,
        # no el stock actual (que puede haber cambiado después del pedido).
        rfp = bool(getattr(venta, "Sobre_Stock", 0)) or bool(getattr(venta, "Necesita_Produccion", 0))

        # Filas de Pagos de esta venta (mismo patrón que `_formato_venta`).
        _pago_anticipo = pagos_map.get((venta.ID_Venta, TIPO_ANTICIPO))
        _pago_saldo    = pagos_map.get((venta.ID_Venta, TIPO_SALDO))
        _es_mixto_bv   = es_pago_mixto(venta.Metodo_Pago)
        _motivo_rechazo_pago_bv = None
        if _pago_saldo and _pago_saldo.Estado == "rechazado":
            _motivo_rechazo_pago_bv = _pago_saldo.Motivo_Rechazo
        elif _pago_anticipo and _pago_anticipo.Estado == "rechazado":
            _motivo_rechazo_pago_bv = _pago_anticipo.Motivo_Rechazo

        result.append({
            "ID_Venta":           venta.ID_Venta,
            "ID_Usuario":         venta.ID_Usuario,
            "nombre_cliente":         f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
            "correo_cliente":         usuario.Correo         if usuario else None,
            "telefono_cliente":       usuario.Telefono        if usuario else None,
            "cedula_cliente":         getattr(usuario, "Cedula",         None) if usuario else None,
            "tipo_documento_cliente": getattr(usuario, "Tipo_Documento", None) if usuario else None,
            "Total":              venta.Total,
            "subtotal_bruto":     subtotal_bruto,
            "credito_aplicado":   credito_aplicado,
            "descuento_aplicado": descuento_aplicado,
            "Estado":             venta.Estado,
            "estado_label":       _label_estado(db, venta.Estado) if venta.Estado else None,
            "Metodo_Pago":            venta.Metodo_Pago,
            "monto_efectivo":         (_pago_saldo.Monto if (_es_mixto_bv and _pago_saldo) else None),
            "monto_transferencia":    (_pago_anticipo.Monto if (_es_mixto_bv and _pago_anticipo) else None),
            "Fecha_Venta":            venta.Fecha_Venta,
            "Fecha_pedido":           venta.Fecha_pedido,
            "Fecha_entrega":          getattr(venta, "Fecha_entrega", None),
            "Fecha_entrega_esperada": venta.Fecha_entrega_esperada,
            "productos":              prods_list,
            "comprobante_pago":             (_pago_anticipo.Comprobante_Url if _pago_anticipo else None),
            "tiene_domicilio":              dom is not None,
            "ID_Domicilio":                 dom.ID_Domicilio        if dom else None,
            "direccion_entrega":            dom.Direccion_entrega    if dom else None,
            "municipio_entrega":            dom.Municipio_entrega    if dom else None,
            "departamento_entrega":         dom.Departamento_entrega if dom else None,
            "observaciones_domicilio":      observaciones_limpias(dom.Observaciones) if dom else None,
            "observaciones_admin":          observaciones_limpias(getattr(dom, "Observaciones_Admin", None)) if dom else None,
            "observaciones_repartidor":     observaciones_limpias(getattr(dom, "Observaciones_Repartidor", None)) if dom else None,
            "nombre_domiciliario":          domiciliario,
            "cedula_domiciliario":          cedula_domiciliario,
            "celular_domiciliario":         celular_domiciliario,
            "ID_Empleado":                  dom.ID_Empleado if dom else None,
            "ordenes_produccion_pendientes": ordenes_counts.get(venta.ID_Venta, 0),
            "ordenes_en_espera":             ordenes_espera.get(venta.ID_Venta, 0),
            "requiere_produccion":           requiere_produccion,
            "sobre_stock":             bool(getattr(venta, "Sobre_Stock", 0)),
            "anticipo_requerido":      getattr(venta, "Anticipo_Requerido", None),
            "anticipo_pagado":         (_pago_anticipo.Monto_Verificado_Creacion if _pago_anticipo else None),
            "requiere_anticipo":       bool(getattr(venta, "Requiere_Anticipo", 0)),
            "anticipo_monto":          (_pago_anticipo.Monto if _pago_anticipo else None),
            "anticipo_metodo_pago":    (_pago_anticipo.Metodo_Pago if _pago_anticipo else None),
            "anticipo_comprobante_url": (_pago_anticipo.Comprobante_Url if _pago_anticipo else None),
            "anticipo_registrado":       bool(_pago_anticipo and _pago_anticipo.Monto),
            "pago_final_registrado":     bool(_pago_saldo and _pago_saldo.Estado in ESTADOS_RESUELTOS_OK),
            "pago_final_monto":          (_pago_saldo.Monto if _pago_saldo else None),
            "pago_final_metodo_pago":    (_pago_saldo.Metodo_Pago if _pago_saldo else None),
            "pago_final_comprobante_url": (_pago_saldo.Comprobante_Url if _pago_saldo else None),
            "pago_final_fecha":          (_pago_saldo.Fecha_Resolucion if _pago_saldo else None),
            "estado_pago":               getattr(venta, "Estado_Pago", "pendiente"),
            "motivo_rechazo_comprobante": _motivo_rechazo_pago_bv,
            "requiere_fecha_propuesta": rfp,
            "fecha_rechazada":  getattr(venta, "Fecha_Rechazada", None),
            "intentos_rechazo": int(getattr(venta, "intentos_rechazo", 0) or 0),
            "resaltar_canal_excepcion": int(getattr(venta, "intentos_rechazo", 0) or 0) >= LIMITE_INTENTOS_RECHAZO,
            "saldo_comprobante_url": (_pago_saldo.Comprobante_Url if _pago_saldo else None),
            "intentos_rechazo_comprobante_anticipo": int((_pago_anticipo.Intentos_Rechazo if _pago_anticipo else 0) or 0),
            "intentos_rechazo_comprobante_saldo":    int((_pago_saldo.Intentos_Rechazo if _pago_saldo else 0) or 0),
            "fecha_retenido_en_tienda": getattr(venta, "Fecha_Retenido_En_Tienda", None),
            "envio_completo_domingo": (
                None if getattr(venta, "Envio_Completo_Domingo", None) is None
                else bool(venta.Envio_Completo_Domingo)
            ),
            "iva_total":     getattr(venta, "IVA_Total",     None),
            "subtotal_base": getattr(venta, "Subtotal_Base", None),
        })

    return result


def obtener_ventas(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None,
    id_usuario: int = None,
    estado: int = None,
) -> dict:
    query = db.query(Venta)

    if id_usuario:
        query = query.filter(Venta.ID_Usuario == id_usuario)

    if estado:
        query = query.filter(Venta.Estado == estado)

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
        query = query.filter(Venta.ID_Usuario.in_(usuarios_ids))

    total  = query.count()
    offset = (pagina - 1) * por_pagina
    ventas = (
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
        .order_by(Venta.Fecha_Venta.desc())
        .offset(offset)
        .limit(por_pagina)
        .all()
    )

    venta_ids = [v.ID_Venta for v in ventas]
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
        "ventas":     [_formato_venta(v, db, dxv_map=dxv_map) for v in ventas],
    }


def obtener_mis_ventas(
    db: Session,
    actual: dict,
    pagina: int = 1,
    por_pagina: int = 10,
) -> dict:
    """Retorna todas las ventas del cliente autenticado (cualquier estado)."""
    if actual["tipo"] != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")

    id_usuario = actual["registro"].ID_Usuario
    query      = db.query(Venta).filter(Venta.ID_Usuario == id_usuario)
    total  = query.count()
    offset = (pagina - 1) * por_pagina
    ventas = (
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

    venta_ids = [v.ID_Venta for v in ventas]
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
        "ventas":     [_formato_venta(v, db, dxv_map=dxv_map) for v in ventas],
    }


def obtener_venta(db: Session, id_venta: int) -> dict:
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return _formato_venta(venta, db)


def obtener_mi_venta(db: Session, id_venta: int, actual: dict) -> dict:
    """Detalle de una venta propia del cliente autenticado."""
    if actual["tipo"] != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")
    id_usuario = actual["registro"].ID_Usuario
    venta = db.query(Venta).filter(
        Venta.ID_Venta   == id_venta,
        Venta.ID_Usuario == id_usuario,
    ).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return _formato_venta(venta, db)


def crear_venta(db: Session, datos: VentaCreate) -> dict:
    """
    Flujo completo de creación de venta:
    1. Valida cliente y productos
    2. Si hay domicilio → verifica que el cliente tenga teléfono registrado
    3. Calcula subtotal bruto
    4. Aplica crédito si el cliente lo desea
    5. Aplica descuento si queda saldo pendiente
    6. Descuenta stock de productos
    7. Crea domicilio si se solicitó
    """
    # Verifica cliente
    usuario = db.query(Usuario).filter(Usuario.ID_Usuario == datos.ID_Usuario).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Si el pedido incluye domicilio, el cliente debe tener teléfono registrado
    if datos.domicilio and not usuario.Telefono:
        raise HTTPException(
            status_code=400,
            detail="Debes registrar tu número de teléfono en tu perfil antes de solicitar un domicilio"
        )

    # ── Precio del domicilio: snapshot del barrio de entrega ────────────────
    # El precio (con ofertas del día) se resuelve y se CONGELA acá. Editar
    # después el precio del barrio o una oferta NO altera este pedido.
    # `resolver_domicilio` valida cobertura y lanza 400 si el barrio no está
    # disponible para domicilio (el frontend ya no deja llegar a este punto).
    snapshot_domicilio = None
    if datos.domicilio:
        if not datos.domicilio.ID_Barrio:
            raise HTTPException(status_code=400, detail="Selecciona el barrio de entrega")
        snapshot_domicilio = resolver_domicilio(db, datos.domicilio.ID_Barrio)

    # Valida productos contra el stock real (con bloqueo de fila) y calcula subtotal.
    # Pedir por encima del stock ya no se rechaza: se marca como preorden y más
    # abajo se le exige el anticipo del 50%.
    lineas, subtotal_bruto = _evaluar_lineas_pedido(db, datos.productos)
    preorden_por_producto = {l["ID_Producto"]: l["preorden"] for l in lineas}
    sobre_stock = any(l["preorden"] > 0 for l in lineas)

    # ── Nada que el admin haya sacado de la tienda ─────────────────────────
    # El personal sí puede vender en mostrador algo fuera del catálogo público;
    # el cliente solo compra lo publicado. Se avisa con el nombre para que
    # sepa exactamente qué sacar del carrito.
    if not datos.creado_por_admin:
        no_publicados = _productos_no_publicados(lineas)
        if no_publicados:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ya no está disponible: {', '.join(no_publicados)}. "
                    "Quítalo del carrito para continuar con el pedido."
                ),
            )

    ESTADO_PENDIENTE = 1

    _metodo_lower = (datos.Metodo_Pago or "").strip().lower()
    # Mixto también llega con comprobante: es el de la parte transferida.
    _lleva_transferencia = "transfer" in _metodo_lower or "mixto" in _metodo_lower
    _estado_pago_inicial = (
        "pendiente_validacion"
        if _lleva_transferencia and datos.comprobante_pago
        else "pendiente"
    )

    nueva_venta = Venta(
        ID_Usuario             = datos.ID_Usuario,
        Total                  = subtotal_bruto,
        Estado                 = ESTADO_PENDIENTE,
        Metodo_Pago            = datos.Metodo_Pago,
        Fecha_Venta            = _now(),
        Fecha_pedido           = _now(),
        Fecha_entrega_esperada = datos.Fecha_entrega_esperada,
        Estado_Pago            = _estado_pago_inicial,
    )
    db.add(nueva_venta)
    db.flush()

    notificar(
        db, "pedido_nuevo", "Nuevo pedido recibido",
        f"El pedido #{nueva_venta.ID_Venta} está esperando ser procesado",
        nueva_venta.ID_Venta, "/ventas/pedidos",
    )

    precios_por_producto = {l["ID_Producto"]: l.get("precio") for l in lineas}
    for p in datos.productos:
        db.add(VentaXProducto(
            ID_Venta          = nueva_venta.ID_Venta,
            ID_Producto       = p.ID_Producto,
            Cantidad          = p.Cantidad,
            Cantidad_Preorden = preorden_por_producto.get(p.ID_Producto, 0),
            Precio_Unitario   = precios_por_producto.get(p.ID_Producto),
        ))

    # Detectar productos fabricables con déficit. Mismo criterio que usan las
    # órdenes de producción: antes esto miraba solo `Requiere_Produccion` y el
    # snapshot decía "no necesita producción" en pedidos a los que después se
    # les abría una orden por el faltante.
    _producibles = _productos_producibles(db, [p.ID_Producto for p in datos.productos])
    necesita_produccion = any(
        l["ID_Producto"] in _producibles and l["preorden"] > 0 for l in lineas
    )

    # Productos sin ficha técnica ni bandera de producción: no se pueden fabricar.
    # Si el cliente pidió más de lo que hay, rechazar ya con info clara en vez de
    # crear un pedido que nadie puede cumplir.
    lineas_sin_produccion_con_deficit = [
        l for l in lineas
        if l["ID_Producto"] not in _producibles and l["preorden"] > 0
    ]
    if lineas_sin_produccion_con_deficit:
        detalle = "; ".join(
            f"{l['nombre']}: disponible {l['stock']}, pediste {l['cantidad']}"
            for l in lineas_sin_produccion_con_deficit
        )
        # La venta ya está volcada a la sesión: sin esto queda una fila a medio
        # crear, como pasa en los demás rechazos de esta función.
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"No hay stock suficiente y estos productos no se fabrican por encargo: {detalle}",
        )

    # El cliente que pide algo que hay que fabricar tiene que decir para cuándo
    # lo necesita: sin esa fecha el admin no tiene contra qué comparar la
    # capacidad de planta. No aplica al pedido que arma el personal en el
    # mostrador (ese nace Confirmado y el admin ya sabe para cuándo es).
    if not datos.creado_por_admin and necesita_produccion:
        _validar_fecha_entrega_esperada(db, datos.Fecha_entrega_esperada)

    nueva_venta.Necesita_Produccion = 1 if necesita_produccion else 0
    # Guardar la respuesta del cliente si ya viene en la creación del pedido.
    # Normalmente llega None (se pregunta en el detalle del pedido) pero se
    # acepta aquí también para no necesitar un PATCH inmediato.
    _envio = getattr(datos, "envio_completo_domingo", None)
    nueva_venta.Envio_Completo_Domingo = (None if _envio is None else (1 if _envio else 0))
    if necesita_produccion:
        notificar(
            db, "produccion_requerida", "Pedido requiere producción",
            f"El pedido #{nueva_venta.ID_Venta} incluye productos por encargo. Revisá y proponé una fecha de entrega.",
            nueva_venta.ID_Venta, "/ventas/pedidos",
        )

    monto_restante   = subtotal_bruto
    credito_aplicado = Decimal("0")

    if datos.usar_credito:
        credito_aplicado = _aplicar_credito(
            db, datos.ID_Usuario, monto_restante, nueva_venta.ID_Venta, datos.credito_monto
        )
        monto_restante  -= credito_aplicado

    descuento_aplicado = Decimal("0")
    if monto_restante > 0:
        descuento_aplicado = _aplicar_descuento(
            db, datos.ID_Usuario, datos.codigo_descuento, monto_restante, nueva_venta.ID_Venta
        )
        monto_restante -= descuento_aplicado

    nueva_venta.Total = max(monto_restante, Decimal("0"))

    # Precio del domicilio: el snapshot congelado del barrio (precio base +
    # ofertas del día, piso 0 / techo TECHO_DOMICILIO). Se suma una sola vez al
    # total; un pedido con grupos de envío NO vuelve a cobrarlo.
    costo_domicilio = Decimal(snapshot_domicilio["final"]) if snapshot_domicilio else Decimal("0")
    nueva_venta.Total += costo_domicilio

    # Extraer IVA del total final (precios ya incluyen 19%: base = total / 1.19).
    _base_total, _iva_total = _desglosar_iva(nueva_venta.Total)
    nueva_venta.Subtotal_Base = _base_total
    nueva_venta.IVA_Total     = _iva_total

    # Pago mixto: el reparto se hace sobre el total ya cerrado (con domicilio,
    # descuentos y saldo a favor aplicados), no sobre lo que declaró el cliente.
    # Dos filas de una vez: 'anticipo' es la mitad transferida (comprobante al
    # hacer el pedido), 'saldo' es la mitad en efectivo (se cobra al entregar).
    if _es_mixto(datos.Metodo_Pago):
        _monto_efectivo, _monto_transferencia = _partir_pago_mixto(
            nueva_venta.Total, datos.pago_efectivo_monto
        )
        _pago_anticipo = pago_o_nuevo(db, nueva_venta.ID_Venta, TIPO_ANTICIPO, "Transferencia")
        _pago_anticipo.Monto           = _monto_transferencia
        _pago_anticipo.Comprobante_Url = datos.comprobante_pago
        _pago_anticipo.Estado          = "pendiente_validacion" if datos.comprobante_pago else "pendiente"
        _pago_anticipo.Fecha_Registro  = _now()
        _pago_saldo = pago_o_nuevo(db, nueva_venta.ID_Venta, TIPO_SALDO, "Efectivo")
        _pago_saldo.Monto = _monto_efectivo
    else:
        # Pedido simple (una sola forma de pago): una fila 'anticipo' que
        # representa el único pago del pedido. El comprobante (si lo hay) se
        # adjunta acá; el monto final se ajusta más abajo según el flujo
        # (admin/cliente, con o sin anticipo exigido).
        _pago_anticipo = pago_o_nuevo(
            db, nueva_venta.ID_Venta, TIPO_ANTICIPO,
            "Transferencia" if _es_transferencia(datos.Metodo_Pago) else "Efectivo",
        )
        if datos.comprobante_pago:
            _pago_anticipo.Comprobante_Url = datos.comprobante_pago
            _pago_anticipo.Estado          = "pendiente_validacion"
            _pago_anticipo.Fecha_Registro  = _now()

    # Que el pedido supere el stock se registra siempre: es un hecho del pedido
    # y de él dependen la fecha propuesta y las órdenes de producción, pida o no
    # anticipo.
    nueva_venta.Sobre_Stock = 1 if sobre_stock else 0

    if datos.creado_por_admin:
        # ── ¿Este pedido pide anticipo? ──────────────────────────────────
        # Lo pide el pedido que hay que fabricar Y que pesa: ver `_pide_anticipo`.
        # Antes lo pedía cualquier pedido que superara el stock, aunque fueran dos
        # panes de $6.000 que se hornean igual el martes.
        #
        # TODO lo que se evalúa aquí sale de la BD (stock real, precios reales, crédito
        # realmente descontado). El request del cliente no puede declarar que ya pagó.
        #
        # Valor real del pedido antes de aplicar créditos (lo que cuesta).
        total_pedido         = subtotal_bruto - descuento_aplicado + costo_domicilio
        anticipo_obligatorio = _pide_anticipo(total_pedido)
        anticipo_requerido   = Decimal("0")

        # El pago mixto no sirve para anticipar: ver _mixto_bloqueado_por_anticipo.
        # Se decide acá abajo y no al entrar porque ahora depende del total ya
        # cerrado, con domicilio y descuentos incluidos.
        if _mixto_bloqueado_por_anticipo(datos.Metodo_Pago, anticipo_obligatorio):
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este pedido requiere anticipo, así que no se puede pagar con el "
                    "método mixto: la parte en efectivo se paga al recibir y el "
                    "anticipo tiene que estar cubierto antes. Págalo por "
                    "transferencia, o con tu saldo a favor si alcanza."
                ),
            )

        # El anticipo, si aplica, es siempre por transferencia (3.1): ni el
        # checkout ni el mostrador pueden dejarlo declarado en efectivo.
        if (
            anticipo_obligatorio
            and datos.anticipo_registrado
            and not _es_transferencia(datos.anticipo_metodo_pago)
        ):
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="El anticipo debe pagarse por transferencia (nunca en efectivo).",
            )

        if anticipo_obligatorio:
            anticipo_requerido = _calcular_anticipo(total_pedido, credito_aplicado)
            # Solo cuenta como pagado lo verificable en el servidor: el crédito
            # efectivamente descontado del libro mayor del cliente.
            anticipo_pagado    = credito_aplicado
            # Ningún pago fuera del crédito se puede verificar desde el servidor: ni
            # una transferencia (el comprobante es una imagen) ni un efectivo
            # entregado en el local. En los dos casos quien valida es el
            # administrador antes de confirmar el pedido.
            #
            # Se da por respaldado el anticipo cuando el checkout lo registró
            # (anticipo_registrado: crédito que lo cubre, efectivo confirmado o
            # comprobante adjunto) o cuando viene el comprobante del pedido pagado
            # por transferencia.
            #
            # Antes esta regla solo aceptaba comprobante_pago + método Transferencia,
            # así que rechazaba el flujo de anticipo del checkout: el comprobante
            # viaja en otro campo y el método del PEDIDO puede ser Efectivo cuando el
            # saldo se paga contra entrega. El cliente se quedaba sin forma de pasar.
            comprobante_pedido   = (datos.comprobante_pago or "").strip()
            comprobante_anticipo = (getattr(datos, "anticipo_comprobante_url", None) or "").strip()
            anticipo_declarado   = bool(getattr(datos, "anticipo_registrado", False))
            tiene_soporte = (
                anticipo_declarado
                or bool(comprobante_anticipo)
                # Solo transferencia PURA: el comprobante de un mixto respalda
                # unicamente la parte transferida, que puede quedar corta contra el
                # 50%. De todos modos el mixto ya se rechaza mas arriba; esto queda
                # para que la regla no dependa de ese unico control.
                or (_es_transferencia(datos.Metodo_Pago) and bool(comprobante_pedido))
            )

            # El mostrador también tiene que dejar el anticipo cubierto (3.1):
            # antes esta condición comparaba `creado_por_admin` contra sí misma
            # (siempre falsa acá adentro) y el mostrador podía crear cualquier
            # pedido grande sin anticipar nada.
            if anticipo_pagado < anticipo_requerido and not tiene_soporte:
                faltante = anticipo_requerido - anticipo_pagado
                # Se indica qué faltó exactamente: el rechazo por "no llegó nada" se
                # confundía con "el monto no alcanza", y no había forma de saber si
                # el problema estaba en el pago o en lo que envió la aplicación.
                if not datos.requiere_anticipo:
                    motivo = "el pedido llegó sin registro de anticipo"
                elif not anticipo_declarado and not comprobante_anticipo:
                    motivo = "no llegó el comprobante ni la confirmación del anticipo"
                else:
                    motivo = "el anticipo registrado no cubre el mínimo"
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Este pedido supera el stock disponible, por lo que requiere un anticipo "
                        f"del 50% (${anticipo_requerido:,.0f}). Te faltan ${faltante:,.0f}: págalo "
                        f"con tus créditos, o registra el anticipo indicando cómo lo pagaste. "
                        f"({motivo})"
                    ),
                )

            nueva_venta.Anticipo_Requerido = anticipo_requerido
            # Dato de auditoría puntual de este chequeo (nunca se vuelve a leer
            # en ningún otro lugar): cuánto del anticipo exigido quedó
            # verificado (crédito aplicado) en el momento de crear la venta.
            _pago_anticipo.Monto_Verificado_Creacion = anticipo_pagado
            # Cuando el flujo de anticipo explícito no se activa (solo ítems de
            # producción sobre stock) pero el cliente sí aportó respaldo de pago,
            # registrar igual para que el panel muestre el monto correcto.
            if not datos.requiere_anticipo and tiene_soporte:
                _pago_anticipo.Monto            = anticipo_requerido
                _pago_anticipo.Estado           = "aprobado"
                _pago_anticipo.Fecha_Resolucion = _now()
                nueva_venta.Estado_Pago         = "anticipo_pagado"

        # El aviso al panel lo dispara el faltante, no el anticipo: el admin tiene
        # que proponer fecha igual, cobre o no por adelantado.
        if sobre_stock:
            detalle_preorden = ", ".join(
                f"{l['nombre']}: {l['cantidad']} pedidas / {l['stock']} en stock"
                for l in lineas if l["preorden"] > 0
            )
            detalle_anticipo = (
                f"Anticipo requerido: ${anticipo_requerido:,.0f}. "
                if anticipo_obligatorio else ""
            )
            notificar(
                db, "pedido_sobre_stock", "Pedido por encima del stock",
                f"El pedido #{nueva_venta.ID_Venta} supera el stock ({detalle_preorden}). "
                f"{detalle_anticipo}Revisá y proponé una fecha de entrega.",
                nueva_venta.ID_Venta, "/ventas/pedidos",
            )

        # El anticipo que registró quien creó el pedido. La obligación la decide el
        # servidor —una app vieja sigue mandando el flag en pedidos que ya no lo
        # piden—, pero la plata que de verdad entró se guarda igual: si alguien pagó
        # por adelantado, el pedido tiene que mostrarlo y el saldo tiene que poder
        # cobrarse después (registrar_pago_final exige Requiere_Anticipo).
        if datos.requiere_anticipo:
            nueva_venta.Requiere_Anticipo        = (
                1 if (anticipo_obligatorio or datos.anticipo_registrado) else 0
            )
            _pago_anticipo.Monto           = datos.anticipo_monto
            _pago_anticipo.Metodo_Pago     = (
                "Transferencia" if _es_transferencia(datos.anticipo_metodo_pago) else "Efectivo"
            )
            # Colapsa con el comprobante general del pedido (decisión de diseño
            # aprobada): si el mostrador mandó los dos, manda el específico del
            # anticipo — es el que de verdad valida `aprobar_comprobante`.
            if datos.anticipo_comprobante_url:
                _pago_anticipo.Comprobante_Url = datos.anticipo_comprobante_url
            if datos.anticipo_registrado:
                _pago_anticipo.Estado           = "aprobado"
                _pago_anticipo.Fecha_Resolucion = _now()
            nueva_venta.Estado_Pago = "anticipo_pagado" if datos.anticipo_registrado else "pendiente"
            # El cliente eligió pagar el total completo ahora. Se usa la bandera
            # explícita (pagar_todo) en vez de comparar montos: la diferencia de
            # redondeo entre el total del cliente (JS) y el servidor (Decimal) puede
            # dejar el pedido en "anticipo_pagado" aunque el cliente pagara todo.
            _pago_total = getattr(datos, "pagar_todo", False)
            if datos.anticipo_registrado and (
                _pago_total
                or (datos.anticipo_monto is not None and float(datos.anticipo_monto) >= float(nueva_venta.Total or 0))
            ):
                _pago_saldo = pago_o_nuevo(db, nueva_venta.ID_Venta, TIPO_SALDO, _pago_anticipo.Metodo_Pago)
                _pago_saldo.Monto            = Decimal("0")
                _pago_saldo.Estado           = "aprobado"
                _pago_saldo.Fecha_Resolucion = _now()
                nueva_venta.Estado_Pago      = "pagado_completo"
    else:
        # ── Pedido del cliente: sin comprobante al crear (3.2) ───────────────
        # El anticipo (si el total lo exige — puramente por monto, 3.1) es
        # siempre por transferencia. Con producción se pide después de que el
        # admin apruebe/acuerde la fecha (`_avanzar_tras_fecha_confirmada`);
        # sin producción se decide de una vez, más abajo.
        anticipo_obligatorio = _pide_anticipo(nueva_venta.Total)
        if _mixto_bloqueado_por_anticipo(datos.Metodo_Pago, anticipo_obligatorio):
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este pedido requiere anticipo, así que no se puede pagar con el "
                    "método mixto. Elige Transferencia."
                ),
            )
        if anticipo_obligatorio and not _es_transferencia(datos.Metodo_Pago):
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Este pedido supera ${UMBRAL_ANTICIPO:,.0f}, así que requiere un anticipo "
                    f"del 50% por transferencia. Elige Transferencia como método de pago."
                ),
            )

        # Lo que hay que hornear se paga por transferencia, y solo por
        # transferencia. El efectivo se cobra al recibir —cuando el pedido ya
        # se produjo y la plata ya se gastó en insumos— y el mixto deja esa
        # misma parte para el final. Un pedido por encargo respalda con plata
        # antes de encender el horno.
        if necesita_produccion and not (
                _es_transferencia(datos.Metodo_Pago) or _es_mixto(datos.Metodo_Pago)):
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este pedido tiene productos por encargo: se paga por "
                    "transferencia. Elige Transferencia como método de pago."
                ),
            )

        if necesita_produccion:
            # Con producción: queda "Pendiente de Aprobación" (Estado ya nace
            # en PENDIENTE) con la fecha obligatoria ya validada arriba. El
            # anticipo, si aplica, se pide cuando el admin apruebe esa fecha.
            pass
        else:
            # Sin producción: no hay nada que aprobar en planta, pero el
            # pedido igual nace PENDIENTE y se queda ahí los 10 minutos del
            # cliente. Lo que se decide acá es cuánto habrá que pagar, no el
            # estado: a dónde va después lo resuelve `confirmar_pedido`, con
            # la misma regla, cuando el panel lo acepta.
            #
            # Adelantarlo a "Esperando pago" al crear le pedía al cliente el
            # comprobante de un pedido que nadie había aceptado todavía, y de
            # paso le quitaba su ventana: en ese estado la app ya no ofrecía
            # editar.
            if anticipo_obligatorio:
                nueva_venta.Anticipo_Requerido = _calcular_anticipo(nueva_venta.Total, Decimal("0"))
                nueva_venta.Requiere_Anticipo  = 1
            elif (_es_transferencia(datos.Metodo_Pago) or _es_mixto(datos.Metodo_Pago)) and nueva_venta.Total <= 0:
                # El crédito cubrió el total: no hace falta comprobante de
                # transferencia para algo que ya quedó en $0.
                nueva_venta.Estado_Pago = "pagado_completo"
                _pago_anticipo.Monto            = Decimal("0")
                _pago_anticipo.Estado           = "aprobado"
                _pago_anticipo.Fecha_Resolucion = _now()
                if not datos.domicilio:
                    _descontar_stock_venta(db, nueva_venta.ID_Venta, PARTE_TODO)
                    nueva_venta.Stock_Reservado = 1
            elif _es_transferencia(datos.Metodo_Pago) or _es_mixto(datos.Metodo_Pago):
                pass
            else:
                # Efectivo, con stock y sin producción: el pedido más simple
                # que existe. Se queda en PENDIENTE —el estado con el que
                # nace toda venta— durante los 10 minutos del cliente, y lo
                # confirma el panel después.
                #
                # Nacía en CONFIRMADO, y eso le quitaba al cliente su propia
                # ventana: 'Confirmado' no está entre los estados que puede
                # cancelar, así que el botón no existía desde el primer
                # segundo. Además dejaba sin uso a las dos piezas que el
                # sistema ya tiene para esto: la ventana de protección de
                # `cambiar_estado` (que impide que un empleado procese el
                # pedido antes de tiempo) y `_evaluar_cierre_ventana` (que
                # reserva el stock cuando el plazo cierra). Las dos
                # presuponen un pedido que todavía no está confirmado.
                #
                # El stock, por eso mismo, tampoco se aparta acá: lo aparta
                # el cierre de la ventana, o la confirmación —lo que ocurra
                # primero—. No tiene sentido apartar mercancía de un pedido
                # que el cliente todavía puede deshacer con un botón.
                pass

        if sobre_stock:
            detalle_preorden = ", ".join(
                f"{l['nombre']}: {l['cantidad']} pedidas / {l['stock']} en stock"
                for l in lineas if l["preorden"] > 0
            )
            notificar(
                db, "pedido_sobre_stock", "Pedido por encima del stock",
                f"El pedido #{nueva_venta.ID_Venta} supera el stock ({detalle_preorden}). "
                f"Revisá la fecha pedida: aprobala o proponé otra.",
                nueva_venta.ID_Venta, "/ventas/pedidos",
            )

    db.add(DetalleVenta(
        ID_Venta    = nueva_venta.ID_Venta,
        A_Nombre_De = datos.A_Nombre_De,
        IVA         = _desglosar_iva(subtotal_bruto)[1],
        Descuento   = credito_aplicado,
        SubTotal    = subtotal_bruto,
    ))

    # Cuando el admin crea el pedido directamente: nace en Confirmado (4).
    # Para pickup (sin domicilio): reserva stock de todos los productos.
    #   - Producción: reserva min(cantidad, stock); el déficit va a la OP.
    #   - Normal: reserva la cantidad completa.
    # Para domicilio: el stock se descuenta en ENTREGADO, igual que el flujo normal.
    if datos.creado_por_admin:
        nueva_venta.Estado = EstadoPedido.CONFIRMADO
        if not datos.domicilio:
            items_flush = db.query(VentaXProducto).filter(
                VentaXProducto.ID_Venta == nueva_venta.ID_Venta
            ).all()
            for item in items_flush:
                prod = db.query(Producto).filter(Producto.ID_Producto == item.ID_Producto).first()
                if not prod:
                    continue
                if getattr(prod, "Requiere_Produccion", 0):
                    # Para producción: reservar solo la porción que cubre el stock;
                    # el déficit (Cantidad_Preorden) lo fabrica la OP.
                    a_descontar = min(item.Cantidad or 0, prod.Stock or 0)
                else:
                    a_descontar = item.Cantidad or 0
                prod.Stock = max(0, (prod.Stock or 0) - a_descontar)
                _actualizar_estado_producto(prod)
                notificar_stock_producto(db, prod)
            # 3.6: mismo marcador que el resto de los caminos de reserva, para
            # que la cancelación sepa que ya hay stock descontado que restaurar.
            nueva_venta.Stock_Reservado = 1
        # Estas notificaciones ya no aplican: el admin las gestiona en el mismo acto
        descartar_notificacion(db, "pedido_nuevo",        nueva_venta.ID_Venta)
        descartar_notificacion(db, "produccion_requerida", nueva_venta.ID_Venta)

    if datos.domicilio:
        ESTADO_ASIGNADO = 10
        ESTADO_DOM_PENDIENTE = 3
        estado_dom = ESTADO_ASIGNADO if datos.domicilio.ID_Empleado else ESTADO_DOM_PENDIENTE
        # Si el domicilio no trae su propia fecha, usa la fecha_entrega_esperada del pedido
        fecha_dom = datos.domicilio.Fecha_entrega or datos.Fecha_entrega_esperada
        # Municipio y departamento se DERIVAN del barrio (fuente única); el texto
        # que mande el cliente es solo respaldo por si el barrio quedara sin
        # ciudad/departamento cargados.
        db.add(Domicilio(
            ID_Venta             = nueva_venta.ID_Venta,
            ID_Empleado          = datos.domicilio.ID_Empleado,
            Fecha_asignacion     = _now(),
            Fecha_entrega        = fecha_dom,
            Observaciones        = datos.domicilio.Observaciones,
            Estado               = estado_dom,
            Direccion_entrega    = datos.domicilio.Direccion_entrega,
            Municipio_entrega    = snapshot_domicilio["ciudad"] or datos.domicilio.Municipio_entrega,
            Departamento_entrega = snapshot_domicilio["departamento"] or datos.domicilio.Departamento_entrega,
            ID_Barrio              = snapshot_domicilio["id_barrio"],
            Precio_Domicilio_Base  = snapshot_domicilio["base"],
            Precio_Domicilio_Final = snapshot_domicilio["final"],
            Desglose_Ofertas       = snapshot_domicilio["desglose"],
        ))
        if not datos.domicilio.ID_Empleado:
            notificar(
                db, "domicilio_pendiente", "Domicilio sin repartidor",
                f"El pedido #{nueva_venta.ID_Venta} tiene domicilio sin repartidor asignado",
                nueva_venta.ID_Venta, "/ventas/domicilios",
            )

    # G-2: una sola transacción para todo el pedido. Antes había dos commit()
    # (venta+domicilio, luego órdenes de producción): si el segundo fallaba, la
    # venta quedaba creada sin sus órdenes y no había forma de cumplirla.
    db.flush()
    db.refresh(nueva_venta)

    # Órdenes de producción del faltante. Se abren solo cuando el pedido ya
    # está confirmado, porque el cliente no puede mandar a fabricar sin que un
    # administrador lo confirme primero. El pedido creado por el personal ya
    # nace en Confirmado, así que en ese caso sí se resuelven las órdenes al
    # crear la venta; en el flujo del cliente, la orden queda pendiente hasta
    # que se confirme el pedido.
    if datos.creado_por_admin:
        _ordenes = _crear_ordenes_produccion_para_venta(
            db, nueva_venta.ID_Venta, nueva_venta.Fecha_entrega_esperada
        )
        # Con producción pendiente el pedido NO está listo para despachar:
        # queda "En producción" hasta que se completen sus órdenes, momento en
        # que el módulo de producción lo pasa a Listo.
        if _ordenes > 0 and nueva_venta.Estado == EstadoPedido.CONFIRMADO:
            nueva_venta.Estado = EstadoPedido.PREPARANDO

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(nueva_venta)

    # El push a los administradores lo dispara notificar() al crear la
    # notificación del panel: así todas las alertas llegan por el mismo camino.

    # Si el pedido nació con repartidor asignado, avisarle en su celular.
    if datos.domicilio and datos.domicilio.ID_Empleado:
        try:
            from src.features.ventas.domicilios.services.service import _avisar_asignacion
            dom_creado = db.query(Domicilio).filter(
                Domicilio.ID_Venta == nueva_venta.ID_Venta
            ).first()
            if dom_creado:
                _avisar_asignacion(db, dom_creado)
        except Exception:
            pass

    return _formato_venta(nueva_venta, db)


def registrar_pago_final(db: Session, id_venta: int, datos) -> dict:
    """Registra el cobro del saldo restante al momento de entrega.

    Precondiciones:
    - La venta debe existir y requerir anticipo (Requiere_Anticipo == 1).
    - La venta no puede estar ya en Entregado (8) ni en Cancelado (5).
    """
    from .schemas import PagoFinalCreate  # importación local para evitar circular

    # Buscar la venta; si no existe, no hay nada que registrar
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    # ── D1: Estado del pedido ──────────────────────────
    # Rechaza el registro si el pedido ya está en un estado final
    # (Entregado o Cancelado), donde no tiene sentido cobrar un saldo.
    if venta.Estado in (EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO):
        raise HTTPException(
            status_code=400,
            detail="El pedido no está en un estado válido para registrar el pago final",
        )

    # ── D2: ¿El pedido requiere anticipo? ──────────────
    # Solo los pedidos que exigieron anticipo (sobre stock o especiales)
    # pueden tener un "pago final" pendiente; los demás no aplican aquí.
    if not getattr(venta, "Requiere_Anticipo", 0):
        raise HTTPException(
            status_code=400,
            detail="Este pedido no requiere anticipo; el pago final no aplica",
        )

    # ── D3 (compuesta A AND B): Transferencia SIN comprobante ──
    # A: el método de pago es transferencia o digital
    # B: no se adjuntó comprobante_url
    # Si ambas se cumplen a la vez, se exige el comprobante antes de continuar.
    if datos.metodo_pago.lower() in ("transferencia", "digital") and not datos.comprobante_url:
        raise HTTPException(
            status_code=400,
            detail="Se requiere comprobante para pago por transferencia",
        )

    # ── Registro del pago final ────────────────────────
    # Registro directo por el admin/empleado (mostrador o al momento de la
    # entrega): se marca cobrado de una, sin paso de validación — a
    # diferencia del segundo comprobante que sube el propio cliente desde su
    # panel (`pagar_saldo_pedido` → `aprobar_comprobante_saldo` /
    # `rechazar_comprobante_saldo`, 3.10), que sí necesita esa revisión
    # porque nadie del negocio vio la plata entrar. `GestionPedidos.jsx`
    # llama a este endpoint y de inmediato marca el pedido Entregado,
    # asumiendo que `Pago_Final_Registrado` ya quedó en 1 acá.
    # "digital" no es un método reconocido por `es_pago_transferencia` (regex
    # de pagos_utils): se normaliza a 'Transferencia' en la fila de Pagos —
    # exige comprobante igual que transferencia (chequeo D3, arriba), es lo
    # que importa acá.
    _metodo_normalizado = (
        "Transferencia" if datos.metodo_pago.lower() in ("transferencia", "digital") else "Efectivo"
    )
    _pago_saldo = pago_o_nuevo(db, id_venta, TIPO_SALDO, _metodo_normalizado)
    _pago_saldo.Metodo_Pago     = _metodo_normalizado
    _pago_saldo.Monto           = datos.monto
    _pago_saldo.Comprobante_Url = datos.comprobante_url
    _pago_saldo.Fecha_Resolucion = _now()
    _pago_saldo.Estado           = "aprobado" if _metodo_normalizado == "Transferencia" else "recibido"
    venta.Estado_Pago            = "pagado_completo"

    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


_VENTANA_PROTECCION = timedelta(minutes=10)


def _saldo_transferencia_pendiente(db: Session, venta: Venta) -> bool:
    """True si el pedido tiene anticipo, el saldo se paga por transferencia y
    esa transferencia todavía no fue aprobada (3.10).

    No bloquea nada si el saldo es en efectivo: ese se cobra físicamente al
    entregar/recoger (3.11), no antes. Tampoco bloquea si el pedido no
    requiere anticipo (nada que anticipar, nada que despachar en dos partes).
    """
    if not getattr(venta, "Requiere_Anticipo", 0):
        return False
    if not _es_transferencia(venta.Metodo_Pago):
        return False
    pago_saldo = obtener_pago(db, venta.ID_Venta, TIPO_SALDO)
    return not bool(pago_saldo and pago_saldo.Estado in ESTADOS_RESUELTOS_OK)


# 3.6: mientras un pedido para recoger en tienda sigue en negociación (fecha,
# pago, etc.) sin llegar a CONFIRMADO, la porción que ya hay en vitrina no
# estaba apartada — otro pedido podía consumirla primero. Se reserva al
# cierre de la ventana de 10 min, evaluada perezosamente (sin scheduler) cada
# vez que alguien toca el pedido, en vez de esperar a CONFIRMADO.
def _evaluar_cierre_ventana(db: Session, pedido: Venta) -> None:
    """Si ya pasaron los 10 minutos y el pedido para recoger en tienda todavía
    no reservó su stock disponible, lo reserva ahora y abre la orden de
    producción del faltante (fila en BD, sin iniciarla) — sin cambiar el
    Estado del pedido, que sigue su curso normal de negociación/aprobación.

    Es un no-op si: ya se reservó antes (`Stock_Reservado`), el pedido es a
    domicilio (ese camino descuenta entero al entregar, no antes — no se
    toca), o el pedido ya llegó a un estado final.
    """
    if getattr(pedido, "Stock_Reservado", 0):
        return
    if pedido.Estado in (EstadoPedido.CANCELADO, EstadoPedido.ENTREGADO):
        return
    if not pedido.Fecha_Venta or (_now() - pedido.Fecha_Venta) < _VENTANA_PROTECCION:
        return
    tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == pedido.ID_Venta).first() is not None
    if tiene_domicilio:
        return

    _descontar_stock_venta(db, pedido.ID_Venta, PARTE_DISPONIBLE)
    # Fila en BD nada más: `_crear_ordenes_produccion_para_venta` no arranca
    # producción ni reserva insumos, y es idempotente (no duplica si ya existe).
    _crear_ordenes_produccion_para_venta(db, pedido.ID_Venta, pedido.Fecha_entrega_esperada)
    db.commit()
    db.refresh(pedido)


def cambiar_estado(
    db: Session, id_venta: int, nuevo_estado: int, *, saltar_ventana_proteccion: bool = False
) -> dict:
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    _evaluar_cierre_ventana(db, venta)

    # Durante los primeros 10 minutos el pedido es exclusivo del cliente para
    # que pueda modificarlo o cancelarlo sin que un empleado lo procese antes.
    # `saltar_ventana_proteccion` es para cancelaciones que dispara el propio
    # sistema como consecuencia de una acción del cliente dentro del pedido
    # (p. ej. su 3er comprobante rechazado, prompt-pedidos-2 3.5/3.10): no es
    # un admin adelantándose, es el pedido cerrándose solo.
    if not saltar_ventana_proteccion and venta.Fecha_Venta and (_now() - venta.Fecha_Venta) < _VENTANA_PROTECCION:
        mins_restantes = int((_VENTANA_PROTECCION - (_now() - venta.Fecha_Venta)).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=400,
            detail=f"Este pedido está en período de edición del cliente ({mins_restantes} min restantes). Espera antes de procesarlo.",
        )

    tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first() is not None

    # Valida que la transición esté permitida por la máquina de estados
    validar_transicion(venta.Estado, nuevo_estado, tiene_domicilio)

    # Confirmar es aceptar el pedido: no se acepta un pago que nadie revisó.
    # El comprobante lo sube el cliente y lo aprueba el admin; si se confirma
    # antes, el pedido entra a producción y se despacha contra una imagen que
    # después puede resultar falsa o de otro monto.
    if nuevo_estado == EstadoPedido.CONFIRMADO and comprobante_sin_aprobar(db, venta):
        _estado_pago = (getattr(venta, "Estado_Pago", None) or "pendiente").strip()
        if _estado_pago == "comprobante_rechazado":
            raise HTTPException(
                status_code=400,
                detail=(
                    "El comprobante de este pedido fue rechazado. El cliente tiene que "
                    "enviar uno nuevo antes de poder confirmarlo."
                ),
            )
        raise HTTPException(
            status_code=400,
            detail=(
                "Aprobá el comprobante de pago antes de confirmar el pedido."
            ),
        )

    # El estado que se guarda al final. Casi siempre es el pedido, pero al
    # confirmar un pedido con faltante se desvía a "En producción": no se puede
    # dar por confirmado y listo algo que todavía hay que hornear.
    estado_a_guardar = nuevo_estado

    # Al confirmar: abrir la producción del faltante. Un pedido por encima del
    # stock (5 panes en bodega, 10 pedidos) tiene que fabricar la diferencia, y
    # hasta ahora eso solo ocurría si el cliente aceptaba una fecha propuesta:
    # confirmando el pedido derecho, el faltante nunca se mandaba a producir y
    # el pedido llegaba a Listo sin que existiera el producto.
    if nuevo_estado == EstadoPedido.CONFIRMADO:
        _creadas = _crear_ordenes_produccion_para_venta(
            db, id_venta, venta.Fecha_entrega_esperada
        )
        _abiertas = db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == id_venta,
            OrdenProduccion.Estado.notin_([11, 5]),
        ).count()
        if _creadas > 0 or _abiertas > 0:
            estado_a_guardar = EstadoPedido.PREPARANDO
        else:
            # No hay órdenes activas: puede que todas ya estuvieran completadas
            # antes de que el sync funcionara correctamente (pedidos "atascados").
            # Si existe al menos una orden completada, el producto ya está listo.
            _completadas = db.query(OrdenProduccion).filter(
                OrdenProduccion.ID_Venta == id_venta,
                OrdenProduccion.Estado == 11,
            ).count()
            if _completadas > 0:
                estado_a_guardar = EstadoPedido.LISTO

    # Bloquear paso a LISTO si hay órdenes de producción sin completar
    if nuevo_estado == EstadoPedido.LISTO:
        # Reintento idempotente: si un producto llegó al pedido sin ficha técnica
        # no se le abrió orden; cuando el admin la carga y vuelve a intentar
        # marcar Listo, aquí se abre la orden que faltaba (en vez de dejar el
        # pedido trabado sin forma de destrabarlo). Una orden que se canceló no
        # se reabre: respetar_canceladas.
        _crear_ordenes_produccion_para_venta(
            db, id_venta, venta.Fecha_entrega_esperada, respetar_canceladas=True
        )

        ordenes_incompletas = db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == id_venta,
            OrdenProduccion.Estado.notin_([11, 5]),
        ).count()
        if ordenes_incompletas > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se puede marcar como Listo: la producción de este pedido aún no está "
                    "completada. Completá la orden de producción primero."
                ),
            )
        # Y el faltante que nunca llegó a tener orden: el producto sin ficha
        # técnica no se puede fabricar, así que no se le abre ninguna y el
        # bloqueo de arriba no lo veía. Igual falta producto que entregar.
        faltantes = _faltantes_sin_cubrir(db, id_venta, tiene_domicilio)
        if faltantes:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No se puede marcar como Listo: falta producto de {', '.join(faltantes)}. "
                    "Completá su orden de producción —si el producto no tiene ficha técnica, "
                    "cargala primero para poder abrirla— o reponé el stock."
                ),
            )

    # Para salir a domicilio debe haber un repartidor asignado.
    if nuevo_estado == EstadoPedido.EN_CAMINO:
        domicilio_sin_rep = db.query(Domicilio).filter(
            Domicilio.ID_Venta == id_venta,
            Domicilio.ID_Empleado.is_(None),
        ).first()
        if domicilio_sin_rep:
            raise HTTPException(
                status_code=400,
                detail="Asigná un repartidor al domicilio antes de marcar el pedido como 'En camino'.",
            )
        # Segundo comprobante (3.10): si el saldo restante es por
        # transferencia, tiene que estar aprobado antes de despachar. Si es en
        # efectivo se cobra al entregar (3.11) y no bloquea acá. No bloquea
        # asignar/reasignar repartidor, que es un botón aparte.
        if _saldo_transferencia_pendiente(db, venta):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Falta aprobar el comprobante del saldo restante antes de enviar "
                    "este pedido a domicilio."
                ),
            )

    # Entregar es cerrar la venta: no se cierra sin decir qué pasó con la
    # plata que se cobra en mano. Con domicilio la recibe el repartidor y en
    # tienda la recibe quien atiende el mostrador; en los dos casos, marcar
    # el pedido como entregado sin registrar ese cobro deja la venta cerrada
    # y el efectivo sin rastro. Registrarlo también es declarar que NO se
    # pudo cobrar (con motivo): lo que no vale es entregar sin decirlo.
    if nuevo_estado == EstadoPedido.ENTREGADO and cobro_efectivo_pendiente(db, venta):
        raise HTTPException(
            status_code=400,
            detail=(
                "Registrá el cobro en efectivo antes de marcar el pedido como "
                "entregado: este pedido se paga (total o en parte) en mano."
            ),
        )

    # Bloquear paso a ENTREGADO si el pedido requiere anticipo y el saldo no fue registrado.
    # No afecta pedidos donde Requiere_Anticipo == 0 (flujo normal sin anticipo).
    _pago_anticipo_eg = obtener_pago(db, id_venta, TIPO_ANTICIPO)
    _pago_saldo_eg     = obtener_pago(db, id_venta, TIPO_SALDO)
    if nuevo_estado == EstadoPedido.ENTREGADO and getattr(venta, "Requiere_Anticipo", 0):
        if not (_pago_saldo_eg and _pago_saldo_eg.Estado in ESTADOS_RESUELTOS_OK):
            raise HTTPException(
                status_code=400,
                detail="Debe registrar el pago final antes de marcar el pedido como entregado",
            )

    # Comprobante obligatorio para marcar como entregado SOLO si el pago fue por
    # transferencia. Los pedidos en efectivo se cobran en mano y no tienen soporte.
    # Cuando el pedido lleva anticipo, el soporte del cliente puede estar guardado
    # como comprobante del anticipo: también cuenta, si no el pedido se queda sin
    # poder entregarse.
    _metodo = (venta.Metodo_Pago or "").strip().lower()
    _soporte_pago = _pago_anticipo_eg.Comprobante_Url if _pago_anticipo_eg else None
    _hay_transferencia = (
        "transfer" in _metodo
        or ("mixto" in _metodo and float((_pago_anticipo_eg.Monto if _pago_anticipo_eg else 0) or 0) > 0)
    )
    if nuevo_estado == EstadoPedido.ENTREGADO and _hay_transferencia and not _soporte_pago:
        raise HTTPException(
            status_code=400,
            detail="Se requiere comprobante de pago para marcar el pedido como entregado",
        )

    # Registrar el timestamp real de entrega (fuente para el plazo de devoluciones,
    # también en pedidos de recoger en tienda que no tienen domicilio).
    if nuevo_estado == EstadoPedido.ENTREGADO and not getattr(venta, "Fecha_entrega", None):
        venta.Fecha_entrega = _now()

    # Al confirmar un pedido SIN domicilio (recoger en tienda): se reserva lo
    # que hay en vitrina. El faltante todavía no existe —la orden de producción
    # recién se abre acá— y sale del stock al entregarlo.
    if nuevo_estado == EstadoPedido.CONFIRMADO and not tiene_domicilio:
        _descontar_stock_venta(db, id_venta, PARTE_DISPONIBLE)

    # Al entregar en tienda: sale el faltante, que para este momento la orden
    # ya horneó y sumó al stock (el pedido no llega a Listo si no).
    if nuevo_estado == EstadoPedido.ENTREGADO and not tiene_domicilio:
        _descontar_stock_venta(db, id_venta, PARTE_PREORDEN)

    # Al entregar un pedido CON domicilio: descontar stock. Acá sale entero,
    # porque nunca se descontó nada antes.
    if nuevo_estado == EstadoPedido.ENTREGADO and tiene_domicilio:
        _descontar_stock_venta(db, id_venta)

    # Al entregar un pedido SIN domicilio (recoger en tienda): retirar las
    # unidades producidas por OPs completadas. Cuando una OP finaliza, agrega
    # `Cantidad_Preorden` al stock general. Esas unidades se dan al cliente
    # aquí, así que hay que descontarlas. Solo aplica si la OP realmente completó.
    if nuevo_estado == EstadoPedido.ENTREGADO and not tiene_domicilio:
        for _it in db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all():
            _preorden = _it.Cantidad_Preorden or 0
            if not _preorden:
                continue
            _op_ok = db.query(OrdenProduccion).filter(
                OrdenProduccion.ID_Venta    == id_venta,
                OrdenProduccion.ID_Producto == _it.ID_Producto,
                OrdenProduccion.Estado      == 11,  # COMPLETADA
            ).first()
            if not _op_ok:
                continue
            _prod_op = (
                db.query(Producto)
                .filter(Producto.ID_Producto == _it.ID_Producto)
                .with_for_update()
                .first()
            )
            if _prod_op:
                _prod_op.Stock = max(0, (_prod_op.Stock or 0) - _preorden)
                _actualizar_estado_producto(_prod_op)
                notificar_stock_producto(db, _prod_op)
                _descontar_fefo_producto(db, _it.ID_Producto, _preorden)

    # Al cancelar: restaurar stock si ya fue descontado.
    # - pickup: se descuenta al reservarse (Stock_Reservado, 3.6) — eso puede
    #   pasar en CONFIRMADO/PREPARANDO/LISTO como siempre, o antes, de forma
    #   perezosa al cerrar la ventana de 10 min con el pedido aún en
    #   negociación. La marca es la fuente de verdad, ya no el Estado: un
    #   pedido puede estar en cualquier estado no-domicilio con el stock ya
    #   reservado.
    # - domicilio: stock se descuenta en ENTREGADO; no aplica al cancelar (nunca llegó)
    if nuevo_estado == EstadoPedido.CANCELADO:
        stock_descontado = not tiene_domicilio and bool(getattr(venta, "Stock_Reservado", 0))
        if stock_descontado:
            items = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
            for item in items:
                producto = (
                    db.query(Producto)
                    .filter(Producto.ID_Producto == item.ID_Producto)
                    .with_for_update()
                    .first()
                )
                if producto:
                    # Para producción solo se reservó la porción en stock (Cantidad - Cantidad_Preorden);
                    # el déficit nunca se tomó de aquí, sino que va a la OP.
                    if getattr(producto, "Requiere_Produccion", 0):
                        a_restaurar = (item.Cantidad or 0) - (item.Cantidad_Preorden or 0)
                    else:
                        a_restaurar = item.Cantidad or 0
                    producto.Stock = (producto.Stock or 0) + a_restaurar
                    _actualizar_estado_producto(producto)
                    notificar_stock_producto(db, producto)
                    if a_restaurar > 0:
                        _restaurar_fefo_producto(db, item.ID_Producto, a_restaurar)
            venta.Stock_Reservado = 0

        # Cerrar la producción que se abrió para este pedido. Cancelar el
        # pedido y dejar su orden viva llenaba el panel de producción de trabajo
        # para pedidos que ya no existen —y si la orden estaba en proceso, los
        # insumos quedaban gastados sin nada que los devolviera—. Se cancela por
        # el servicio de producción para que la devolución de insumos y los
        # lotes se hagan con las mismas reglas de siempre.
        #
        # El pedido queda marcado como cancelado ANTES de la cascada: así la
        # sincronización pedido↔orden que corre dentro de cada cancelación ve el
        # estado final y no intenta reabrir el pedido. Y las órdenes se cancelan
        # con commit=False para que todo (pedido + órdenes + insumos) cierre en
        # una sola transacción: si algo falla, no queda nada a medias.
        venta.Estado = EstadoPedido.CANCELADO
        from src.features.produccion.ordenes_produccion.services.service import (
            cambiar_estado as _cambiar_estado_orden,
        )
        ordenes_vivas = db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == id_venta,
            OrdenProduccion.Estado.notin_([11, 5]),   # completada / cancelada
        ).all()
        for _orden in ordenes_vivas:
            _cambiar_estado_orden(db, _orden.ID_Orden_Produccion, 5, commit=False)

        # Devolver crédito si se usó al crear el pedido
        detalle = db.query(DetalleVenta).filter(DetalleVenta.ID_Venta == id_venta).first()
        credito_devuelto = Decimal(str(getattr(detalle, "Descuento", None) or 0))
        if credito_devuelto > 0:
            _abonar_credito(db, venta.ID_Usuario, credito_devuelto, id_venta)

        # Devolver el anticipo registrado como saldo a favor, pero solo si no
        # se alcanzó a hornear: ahí la panadería no gastó nada y la plata del
        # cliente vuelve sola. Horneado, los insumos ya se fueron y qué pasa
        # con esa plata lo acuerdan el cliente y quien atiende.
        # NOTA: igual que antes de la migración, esto se dispara con solo
        # `Monto` declarado (no exige Estado='aprobado') — incluye el caso del
        # comprobante rechazado 3 veces que auto-cancela el pedido. Es
        # comportamiento preexistente, preservado tal cual; reportado como
        # hallazgo aparte, no se corrige en este refactor.
        _pago_anticipo_cnl = obtener_pago(db, id_venta, TIPO_ANTICIPO)
        _anticipo = Decimal(str(_pago_anticipo_cnl.Monto or 0)) if _pago_anticipo_cnl else Decimal("0")
        if (_pago_anticipo_cnl and _pago_anticipo_cnl.Monto and _anticipo > 0
                and anticipo_vuelve_solo(db, id_venta)):
            _abonar_credito(db, venta.ID_Usuario, _anticipo, id_venta)

        # Pedido mixto: si la mitad en efectivo ya se cobró (en tienda o al
        # domiciliario) antes de que la transferencia se rechazara la 3ra vez
        # y el pedido se cancelara solo, esa plata también se devuelve como
        # saldo a favor — regla nueva confirmada con el usuario (antes no
        # existía ningún camino que la devolviera).
        _pago_saldo_cnl = obtener_pago(db, id_venta, TIPO_SALDO)
        if (_pago_saldo_cnl and _pago_saldo_cnl.Estado in ESTADOS_RESUELTOS_OK
                and (_pago_saldo_cnl.Monto or 0) > 0):
            _abonar_credito(db, venta.ID_Usuario, Decimal(str(_pago_saldo_cnl.Monto)), id_venta)

    if venta.Estado == EstadoPedido.PENDIENTE:
        descartar_notificacion(db, "pedido_nuevo", id_venta)
    if nuevo_estado == EstadoPedido.CANCELADO:
        descartar_notificacion(db, "domicilio_pendiente",  id_venta)
        descartar_notificacion(db, "produccion_requerida", id_venta)
        # Cerrar el domicilio pendiente si la venta se cancela
        domicilio_abierto = db.query(Domicilio).filter(
            Domicilio.ID_Venta == id_venta,
            Domicilio.Estado.notin_([8, 5]),  # 8=Entregado, 5=Cancelado (ya finales)
        ).first()
        if domicilio_abierto:
            domicilio_abierto.Estado = 5  # Cancelado

    # Cerrar el domicilio cuando la venta se marca como entregada desde Gestión
    # de pedidos: si no, el domicilio se quedaba "En camino" para siempre y
    # seguía apareciendo como activo en Gestión de domicilios.
    if nuevo_estado == EstadoPedido.ENTREGADO:
        domicilio_pendiente = db.query(Domicilio).filter(
            Domicilio.ID_Venta == id_venta,
            Domicilio.Estado.notin_([8, 5]),
        ).first()
        if domicilio_pendiente:
            domicilio_pendiente.Estado = 8  # Entregado
            if not domicilio_pendiente.Fecha_entrega:
                domicilio_pendiente.Fecha_entrega = _now()

    venta.Estado = estado_a_guardar
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            # El estado real que quedó: Confirmado, o En producción si el pedido
            # arrancó fabricación al confirmarse.
            nuevo_estado=estado_a_guardar,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def obtener_mi_credito(db: Session, usuario_actual: dict) -> dict:
    """
    Retorna el saldo de crédito disponible del cliente autenticado.

    El saldo se recalcula desde el libro mayor de movimientos (recargas − usos),
    que es la fuente de verdad. Si el campo CreditoCliente.Saldo quedó
    desincronizado (p. ej. una recarga por devolución que no se reflejó en el
    campo), se corrige y persiste aquí para que tanto la app como el checkout
    usen el valor correcto.
    """
    registro   = usuario_actual.get("registro")
    id_usuario = registro.ID_Usuario if registro else None
    credito = db.query(CreditoCliente).filter(
        CreditoCliente.ID_Usuario == id_usuario
    ).first()

    if not credito:
        return {"saldo": 0.0, "id_usuario": id_usuario}

    # Balance real desde los movimientos (append-only = fuente de verdad).
    movs = db.query(MovimientoCredito).filter(
        MovimientoCredito.ID_Credito == credito.ID_Credito
    ).all()
    balance = Decimal("0")
    for m in movs:
        monto = Decimal(str(m.Monto or 0))
        tipo  = (m.Tipo or "").lower()
        if tipo == "recarga":
            balance += monto
        elif tipo == "uso":
            balance -= monto
    if balance < 0:
        balance = Decimal("0")

    saldo_guardado = credito.Saldo or Decimal("0")

    # Autocorrección: si hay movimientos y el campo Saldo quedó desfasado, se
    # alinea al balance del libro mayor y se persiste (idempotente).
    if movs and abs(Decimal(str(saldo_guardado)) - balance) > Decimal("0.01"):
        credito.Saldo        = balance
        credito.Fecha_Update = _now()
        db.commit()
        saldo_guardado = balance

    # Con movimientos usamos el balance recalculado; sin movimientos, el campo.
    saldo = float(balance) if movs else float(saldo_guardado)
    return {"saldo": saldo, "id_usuario": id_usuario}


def obtener_credito_cliente(db: Session, id_usuario: int) -> dict:
    """Retorna el saldo de crédito de cualquier cliente (uso admin)."""
    credito = db.query(CreditoCliente).filter(
        CreditoCliente.ID_Usuario == id_usuario
    ).first()
    if not credito:
        return {"saldo": 0.0, "id_usuario": id_usuario}
    return {"saldo": float(credito.Saldo or 0), "id_usuario": id_usuario}


# ── Feature "Fecha propuesta" ──────────────────────────────────────────────

def requiere_fecha_propuesta(db: Session, venta: Venta) -> bool:
    """True si el pedido necesita que el admin proponga una fecha de entrega.

    Usa el snapshot guardado en Necesita_Produccion (fijado al crear la venta)
    para evitar falsos positivos cuando el stock cambia después del pedido.
    """
    if bool(getattr(venta, "Sobre_Stock", 0)):
        return True
    return bool(getattr(venta, "Necesita_Produccion", 0))


def _guardar_historial_fecha(
    db: Session,
    id_venta: int,
    tipo_accion: str,
    fecha_propuesta=None,
    motivo_rechazo: str | None = None,
    id_usuario: int | None = None,
) -> None:
    """Registra un evento de negociación de fecha en el historial."""
    db.add(HistorialFechasPropuestas(
        ID_Venta        = id_venta,
        ID_Usuario      = id_usuario,
        Fecha_Propuesta = fecha_propuesta,
        Fecha_Accion    = _now(),
        Tipo_Accion     = tipo_accion,
        Motivo_Rechazo  = motivo_rechazo,
    ))


def proponer_fecha(
    db: Session, id_venta: int, fecha_entrega, id_admin: int | None = None,
    motivo: str | None = None,
) -> dict:
    """Admin propone una fecha de entrega (contraoferta, 3.4).
    Válido en ventas Pendientes, Fecha propuesta, Fecha rechazada o Escalado a admin.

    `motivo` es opcional: la justificación de por qué esa fecha (ej. "la
    panadería está a full esta semana"), para que el cliente tenga contexto
    al decidir si la acepta o propone la suya.
    """
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    estados_permitidos = (
        EstadoPedido.PENDIENTE,
        EstadoPedido.FECHA_PROPUESTA,
        EstadoPedido.FECHA_RECHAZADA,
        EstadoPedido.ESCALADO_A_ADMIN,
    )
    if venta.Estado not in estados_permitidos:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede proponer fecha en ventas Pendientes, Fecha propuesta, Fecha rechazada o Escalado a admin",
        )
    # La fecha propuesta es SOLO para los pedidos que no se pueden entregar de
    # inmediato: los que superan el stock disponible (preorden) y los que
    # incluyen productos por encargo con déficit.
    if not requiere_fecha_propuesta(db, venta):
        raise HTTPException(
            status_code=400,
            detail=(
                "Solo se propone fecha en pedidos que superan el stock disponible "
                "o que requieren producción"
            ),
        )
    # La fecha propuesta debe respetar el margen de producción y el techo máximo
    hoy = _now().date()
    fecha_propuesta_date = fecha_entrega.date() if hasattr(fecha_entrega, "date") else fecha_entrega
    minima = hoy + timedelta(days=DIAS_MIN_PRODUCCION)
    if fecha_propuesta_date < minima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha propuesta debe ser al menos {DIAS_MIN_PRODUCCION} días desde hoy (mínimo: {minima.isoformat()})",
        )
    maxima = hoy + relativedelta(months=MESES_MAX_PEDIDO)
    if fecha_propuesta_date > maxima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha propuesta no puede ser después del {maxima.isoformat()}",
        )
    descartar_notificacion(db, "produccion_requerida", id_venta)
    descartar_notificacion(db, "pedido_sobre_stock",   id_venta)
    venta.Estado = EstadoPedido.FECHA_PROPUESTA
    venta.Fecha_entrega_esperada = fecha_entrega
    _guardar_historial_fecha(
        db, id_venta, TipoAccionFecha.PROPUESTA, fecha_entrega,
        motivo_rechazo=(motivo.strip() if motivo else None), id_usuario=id_admin,
    )
    _mensaje_fecha = f"El administrador propuso una fecha de entrega para tu pedido #{id_venta}"
    if motivo:
        _mensaje_fecha += f". Motivo: {motivo.strip()}"
    notificar(
        db, "fecha_propuesta", "Fecha de entrega propuesta",
        _mensaje_fecha,
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=EstadoPedido.FECHA_PROPUESTA,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def _avanzar_tras_fecha_confirmada(db: Session, venta: Venta, fecha_entrega, id_usuario: int | None = None) -> None:
    """La fecha de entrega ya quedó acordada —aprobada tal cual (Camino A),
    aceptada por el cliente tras una contraoferta, o pactada por teléfono en
    un escalado— y decide a dónde avanza el pedido desde ahí.

    Si el pedido pesa lo suficiente para pedir anticipo (`_pide_anticipo`),
    queda en Esperando Pago: no se abre la orden de producción todavía, para
    no arriesgar insumos antes de que el cliente respalde el pedido con
    plata. Si no lo pide, sigue de una el mismo camino de producción/despacho
    que ya existía (`aceptar_fecha` original): abre las órdenes que falten,
    reserva stock de tienda y salta a Listo si no queda nada pendiente.

    No hace commit ni arma la respuesta — eso lo decide quien llama, que
    también dispara su propia notificación según el punto de entrada.
    """
    venta.Fecha_entrega_esperada = fecha_entrega
    venta.intentos_rechazo = 0

    anticipo_obligatorio = _pide_anticipo(venta.Total)
    if anticipo_obligatorio:
        venta.Anticipo_Requerido = _calcular_anticipo(venta.Total, Decimal("0"))
        venta.Requiere_Anticipo  = 1
        venta.Estado             = EstadoPedido.ESPERANDO_PAGO
        notificar(
            db, "fecha_propuesta", "Fecha aprobada — falta el anticipo",
            f"Tu pedido #{venta.ID_Venta} ya tiene fecha de entrega. Sube el comprobante de tu "
            f"anticipo (mínimo 50%, por transferencia) para que empecemos a producir.",
            venta.ID_Venta, "/ventas/pedidos",
        )
        return

    # Sin anticipo, pero por transferencia y sin pagar: tampoco se enciende
    # el horno todavía. Un encargo se respalda con plata antes de gastar
    # insumos, y eso vale para los de $60.000 igual que para los de
    # $200.000 —solo cambia cuánto se pide: el 50% arriba del umbral, el
    # total por debajo—.
    #
    # Antes solo esperaba pago el que superaba el umbral. El resto se iba
    # derecho a producción con la fecha recién acordada, y a nadie se le
    # llegaba a pedir el comprobante.
    if (_es_transferencia(venta.Metodo_Pago) or _es_mixto(venta.Metodo_Pago)
            and not getattr(venta, "Pago_Final_Registrado", 0)
            and Decimal(str(venta.Total or 0)) > 0):
        venta.Estado = EstadoPedido.ESPERANDO_PAGO
        notificar(
            db, "fecha_propuesta", "Fecha aprobada — falta tu pago",
            f"Tu pedido #{venta.ID_Venta} ya tiene fecha de entrega. Sube el comprobante "
            f"de tu transferencia para que empecemos a prepararlo.",
            venta.ID_Venta, "/ventas/pedidos",
        )
        return

    # Sin anticipo, pero por transferencia y sin pagar: tampoco se enciende
    # el horno todavía. Un encargo se respalda con plata antes de gastar
    # insumos, y eso vale para los de $60.000 igual que para los de
    # $200.000 —solo cambia cuánto se pide: el 50% arriba del umbral, el
    # total por debajo—.
    #
    # Antes solo esperaba pago el que superaba el umbral. El resto se iba
    # derecho a producción con la fecha recién acordada, y a nadie se le
    # llegaba a pedir el comprobante.
    if ((_es_transferencia(venta.Metodo_Pago) or _es_mixto(venta.Metodo_Pago))
            and not getattr(venta, "Pago_Final_Registrado", 0)
            and Decimal(str(venta.Total or 0)) > 0):
        venta.Estado = EstadoPedido.ESPERANDO_PAGO
        notificar(
            db, "fecha_propuesta", "Fecha aprobada — falta tu pago",
            f"Tu pedido #{venta.ID_Venta} ya tiene fecha de entrega. Sube el comprobante "
            f"de tu transferencia para que empecemos a prepararlo.",
            venta.ID_Venta, "/ventas/pedidos",
        )
        return

    _iniciar_produccion_o_despachar(db, venta, fecha_entrega)


def _iniciar_produccion_o_despachar(db: Session, venta: Venta, fecha_entrega) -> None:
    """La fecha (y el anticipo, si hacía falta) ya están resueltos: abre las
    órdenes de producción que falten, reserva stock de tienda, y decide entre
    Confirmado / En producción / Listo.

    Común a `_avanzar_tras_fecha_confirmada` (cuando el pedido no pedía
    anticipo) y a `_avanzar_tras_pago_aprobado` (cuando sí lo pedía y el admin
    ya aprobó el comprobante).
    """
    venta.Estado = EstadoPedido.CONFIRMADO
    _crear_ordenes_produccion_para_venta(db, venta.ID_Venta, fecha_entrega)
    _ordenes_abiertas = db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Venta == venta.ID_Venta,
        OrdenProduccion.Estado.notin_([11, 5]),   # completada / cancelada
    ).count()
    if _ordenes_abiertas > 0:
        venta.Estado = EstadoPedido.PREPARANDO

    # Reservar del stock la porción disponible para pedidos de recoger en tienda:
    # el déficit ya quedó cubierto por la OP; las unidades en stock se apartan ahora.
    # 3.6: si la reserva perezosa ya corrió al cerrarse la ventana de 10 min
    # (Stock_Reservado), esto no se repite — ya se descontó antes.
    _tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == venta.ID_Venta).first() is not None
    if not _tiene_domicilio and not getattr(venta, "Stock_Reservado", 0):
        for av in db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == venta.ID_Venta).all():
            en_stock_reservado = (av.Cantidad or 0) - (av.Cantidad_Preorden or 0)
            if en_stock_reservado <= 0:
                continue
            prod_av = (
                db.query(Producto)
                .filter(Producto.ID_Producto == av.ID_Producto)
                .with_for_update()
                .first()
            )
            if not prod_av or not getattr(prod_av, "Requiere_Produccion", 0):
                continue
            prod_av.Stock = max(0, (prod_av.Stock or 0) - en_stock_reservado)
            _actualizar_estado_producto(prod_av)
            notificar_stock_producto(db, prod_av)
        venta.Stock_Reservado = 1

    # La panadería pudo terminar de hornear mientras se negociaba la fecha (o
    # el pago). En ese caso ya no falta nada: queda Listo para despachar sin
    # pasar por un "Confirmado" en el que nadie tiene nada que hacer.
    if (venta.Estado == EstadoPedido.CONFIRMADO
            and not _faltantes_sin_cubrir(db, venta.ID_Venta, _tiene_domicilio)):
        venta.Estado = EstadoPedido.LISTO


def _avanzar_tras_pago_aprobado(db: Session, venta: Venta) -> None:
    """El admin aprobó el comprobante de un pedido que estaba Esperando Pago
    (el total de un pedido sin producción, o el anticipo de uno que sí la
    necesitaba). No hace commit — lo hace quien llama (`aprobar_comprobante`).

    Con producción, sigue el mismo camino que si nunca hubiera pedido
    anticipo (`_iniciar_produccion_o_despachar`). Sin producción, pasa a
    Confirmado (En Alistamiento) y, si es para recoger en tienda, descuenta el
    stock ahora — lo mismo que hace `cambiar_estado` al confirmar cualquier
    otro pedido sin domicilio.
    """
    if getattr(venta, "Necesita_Produccion", 0):
        _iniciar_produccion_o_despachar(db, venta, venta.Fecha_entrega_esperada)
        return

    venta.Estado = EstadoPedido.CONFIRMADO
    _tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == venta.ID_Venta).first() is not None
    if not _tiene_domicilio:
        _descontar_stock_venta(db, venta.ID_Venta, PARTE_TODO)
        venta.Stock_Reservado = 1


def aprobar_fecha_directa(db: Session, id_venta: int, actual: dict) -> dict:
    """Admin aprueba en 1 clic la fecha ya puesta en el pedido: la que el
    cliente pidió al hacerlo (Camino A, desde 'Pendiente de Aprobación'), o la
    que propuso como contraoferta final tras rechazar la del admin (3.4, desde
    'Fecha propuesta final'). En los dos casos no cambia la fecha ni pasa por
    'Fecha propuesta': el admin solo confirma que la planta puede cumplirla.
    """
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.Estado not in (EstadoPedido.PENDIENTE, EstadoPedido.FECHA_PROPUESTA_FINAL):
        raise HTTPException(
            status_code=400,
            detail="Solo se puede aprobar un pedido 'Pendiente de Aprobación' o con 'Fecha propuesta final'",
        )
    if not requiere_fecha_propuesta(db, venta):
        raise HTTPException(status_code=400, detail="Este pedido no requiere aprobación de fecha")
    if not venta.Fecha_entrega_esperada:
        raise HTTPException(status_code=400, detail="El pedido no tiene una fecha para aprobar")

    # Aprobar la fecha abre la orden de producción y reserva insumos contra
    # unas cantidades y un día concretos. Hacerlo mientras el cliente todavía
    # puede editar su pedido deja las dos cosas peleadas: agrega una torta o
    # pide otro día y la orden ya está abierta para lo anterior.
    #
    # Es la misma espera que exige `confirmar_pedido`, y el mismo motivo por
    # el que `cambiar_estado` tiene su ventana de protección — este camino no
    # pasaba por ahí porque asigna el estado directo.
    if venta.Fecha_Venta and (_now() - venta.Fecha_Venta) < _VENTANA_PROTECCION:
        minutos = int(
            (_VENTANA_PROTECCION - (_now() - venta.Fecha_Venta)).total_seconds() / 60
        ) + 1
        raise HTTPException(
            status_code=400,
            detail=(
                f"Este pedido está en período de edición del cliente "
                f"({minutos} min restantes). Espera antes de aprobar la fecha: "
                f"la orden de producción se abre con esta aprobación."
            ),
        )

    id_admin = getattr(actual.get("registro"), "ID_Usuario", None)
    descartar_notificacion(db, "produccion_requerida", id_venta)
    descartar_notificacion(db, "pedido_sobre_stock",   id_venta)
    _avanzar_tras_fecha_confirmada(db, venta, venta.Fecha_entrega_esperada, id_usuario=id_admin)
    _guardar_historial_fecha(db, id_venta, TipoAccionFecha.ACEPTADA, venta.Fecha_entrega_esperada, id_usuario=id_admin)

    notificar(
        db, "fecha_aceptada", "Pedido aprobado",
        f"El administrador aprobó la fecha de entrega de tu pedido #{id_venta}",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=venta.Estado,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def _productos_producibles(db: Session, prod_ids: list[int]) -> set[int]:
    """IDs de los productos que la panadería sí puede fabricar.

    Cuenta como producible el marcado con `Requiere_Produccion` y también el que
    tiene ficha técnica aunque nadie le haya puesto el flag: la ficha es la
    receta, y sin receta la orden ni siquiera se puede iniciar. Se mira la ficha
    además del flag porque al cargar el catálogo se olvida, y sin él el faltante
    de un pedido nunca llegaba a generar orden de producción.
    """
    if not prod_ids:
        return set()
    marcados = {
        pid for (pid,) in db.query(Producto.ID_Producto).filter(
            Producto.ID_Producto.in_(prod_ids),
            Producto.Requiere_Produccion != 0,
        ).all()
    }
    con_ficha = {
        pid for (pid,) in db.query(FichaTecnica.ID_Producto).filter(
            FichaTecnica.ID_Producto.in_(prod_ids)
        ).distinct().all()
    }
    return marcados | con_ficha


def _faltantes_sin_cubrir(db: Session, id_venta: int, tiene_domicilio: bool) -> list[str]:
    """Nombres de los productos del pedido cuyo faltante nadie fabricó ni repuso.

    Un pedido que pide más de lo que hay solo se despacha cuando ese faltante
    existe de verdad: porque su orden de producción se completó, o porque
    entretanto entró stock. El caso que se colaba es el producto que no se puede
    fabricar —sin ficha técnica y sin `Requiere_Produccion`—: no se le abre
    orden, así que no había nada que bloqueara el paso a Listo y el pedido
    quedaba listo para entregar un producto que no existe. También cubre la
    orden que se canceló sin fabricar nada.

    `tiene_domicilio` decide cuánto stock hace falta: en los pedidos de recoger
    en tienda el stock ya se descontó al confirmar y solo queda debiendo la
    preorden; en los de domicilio el descuento ocurre al entregar, así que
    todavía hace falta el pedido completo.
    """
    items = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
    pendientes: list[str] = []
    for item in items:
        preorden = item.Cantidad_Preorden or 0
        if preorden <= 0:
            continue  # la línea entraba en el stock del día; nada que cubrir
        fabricado = db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta    == id_venta,
            OrdenProduccion.ID_Producto == item.ID_Producto,
            OrdenProduccion.Estado      == 11,   # Completada
        ).first()
        if fabricado:
            continue
        producto  = db.query(Producto).filter(
            Producto.ID_Producto == item.ID_Producto
        ).first()
        necesario = (item.Cantidad or 0) if tiene_domicilio else preorden
        if producto and (producto.Stock or 0) >= necesario:
            continue  # entró stock entretanto: el faltante ya existe
        pendientes.append(producto.nombre if producto else f"producto #{item.ID_Producto}")
    return pendientes


def _crear_ordenes_produccion_para_venta(
    db: Session, id_venta: int, fecha_entrega, *, respetar_canceladas: bool = False
) -> int:
    """Abre las órdenes de producción del faltante de un pedido.

    Por cada línea que pide más unidades de las que hay en stock
    (`Cantidad_Preorden`) se abre una orden por exactamente ese faltante: si hay
    5 panes de plátano y el cliente pide 10, la orden es por 5. Nace Pendiente y
    el pedido no puede pasar a Listo mientras siga abierta.

    Es idempotente: se puede llamar en cada punto del recorrido del pedido (al
    crearlo con el anticipo cubierto, al confirmarlo, al aceptar la fecha
    propuesta) y solo abre las que falten, nunca duplica la producción.

    - `respetar_canceladas`: cuando es True, un producto cuya orden ya fue
      cancelada tampoco vuelve a generar orden. Se usa al intentar marcar el
      pedido como Listo: ahí solo interesa abrir la orden que nunca existió
      (producto sin ficha al confirmar, ficha cargada después), no reabrir una
      que se canceló a propósito.

    Un producto sin ficha técnica no genera orden (no podría iniciarse): el
    pedido queda bloqueado para pasar a Listo hasta que se cargue la ficha.

    Devuelve cuántas creó, para que quien llama deje el pedido en el estado que
    corresponde: con producción pendiente el pedido no está listo para
    despachar, así que va "En producción" y no "Confirmado".
    """
    items_venta = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
    if not items_venta:
        return 0

    prod_ids = [item.ID_Producto for item in items_venta]
    req_ids  = _productos_producibles(db, prod_ids)
    if not req_ids:
        return 0

    # Productos que ya tienen orden para este pedido: llamar dos veces no puede
    # duplicar la producción. Por defecto una orden cancelada no bloquea (se
    # puede reintentar); con respetar_canceladas sí bloquea.
    _q_ya = db.query(OrdenProduccion.ID_Producto).filter(
        OrdenProduccion.ID_Venta == id_venta,
    )
    if not respetar_canceladas:
        _q_ya = _q_ya.filter(OrdenProduccion.Estado != 5)   # 5 = Cancelada
    ya_con_orden = {pid for (pid,) in _q_ya.all()}

    req_lista = list(req_ids)
    fichas_m: dict = {}
    # Se prefiere la ficha activa; si no hay, la última registrada (la misma que
    # el módulo de producción resuelve al iniciar la orden).
    for estado_ficha in (1, None):
        q = db.query(FichaTecnica).filter(FichaTecnica.ID_Producto.in_(req_lista))
        if estado_ficha is not None:
            q = q.filter(FichaTecnica.Estado == estado_ficha)
        for f in q.order_by(FichaTecnica.ID_Ficha.desc()).all():
            fichas_m.setdefault(f.ID_Producto, f)

    ahora = _now()
    creadas = 0
    for item in items_venta:
        if item.ID_Producto not in req_ids or item.ID_Producto in ya_con_orden:
            continue
        cantidad = item.Cantidad_Preorden or 0
        if cantidad <= 0:
            continue  # stock cubría todo; no se necesita producción
        ficha = fichas_m.get(item.ID_Producto)
        if not ficha:
            # Sin ficha técnica el producto no se puede fabricar: no se abre una
            # orden que nunca podría iniciarse. El pedido queda bloqueado para
            # pasar a Listo (ver _faltantes_sin_cubrir) hasta que se cargue la
            # ficha; al reintentar "marcar Listo" esta función se vuelve a correr.
            continue
        if not ficha.Dias_Vida_Util:
            # Sin vida útil configurada el lote resultante no tendría fecha de
            # vencimiento y no podría rastrearse. Mismo tratamiento que sin ficha.
            continue
        db.add(OrdenProduccion(
            ID_Venta       = id_venta,
            ID_Producto    = item.ID_Producto,
            ID_Insumo      = None,
            ID_Ficha       = ficha.ID_Ficha,
            Cantidad       = cantidad,
            Fecha_Creacion = ahora,
            Fecha_inicio   = ahora,
            Fecha_Entrega  = fecha_entrega or ahora,
            Estado         = 1,
            Costo          = Decimal("0"),
        ))
        # El producto ya quedó cubierto: si la venta trae la misma línea dos
        # veces no se abren dos órdenes por lo mismo.
        ya_con_orden.add(item.ID_Producto)
        creadas += 1

    return creadas


def aceptar_fecha(db: Session, id_venta: int, actual: dict) -> dict:
    """El cliente acepta la fecha que contraofreció el admin."""
    if actual["tipo"] != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")
    id_usuario = actual["registro"].ID_Usuario

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.ID_Usuario != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes aceptar pedidos de otros clientes")
    if venta.Estado != EstadoPedido.FECHA_PROPUESTA:
        raise HTTPException(status_code=400, detail="El pedido no está en estado 'Fecha propuesta'")

    _guardar_historial_fecha(db, id_venta, TipoAccionFecha.ACEPTADA, venta.Fecha_entrega_esperada, id_usuario=id_usuario)
    _avanzar_tras_fecha_confirmada(db, venta, venta.Fecha_entrega_esperada, id_usuario=id_usuario)

    notificar(
        db, "fecha_aceptada", "Fecha aceptada por el cliente",
        f"El cliente aceptó la fecha propuesta para el pedido #{id_venta}",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=venta.Estado,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def rechazar_fecha(db: Session, id_venta: int, actual: dict, fecha_propuesta_cliente, motivo: str) -> dict:
    """El cliente rechaza la contraoferta de fecha con su propia propuesta
    final: una fecha propia y un motivo, los dos obligatorios (prompt-pedidos-2,
    3.4). Ya no reabre la negociación de forma indefinida — antes volvía a
    'Pendiente de Aprobación' con la fecha en blanco y el ciclo podía repetirse
    sin límite. Ahora el pedido pasa a 'Fecha propuesta final' y queda
    congelado (sin más ediciones del cliente) hasta que el admin la acepte
    (`aprobar_fecha_directa`, que también sirve para este caso) o la rechace
    en definitivo (`rechazar_fecha_final`).
    """
    if actual["tipo"] != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")
    id_usuario = actual["registro"].ID_Usuario

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.ID_Usuario != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes rechazar pedidos de otros clientes")
    if venta.Estado != EstadoPedido.FECHA_PROPUESTA:
        raise HTTPException(status_code=400, detail="El pedido no está en estado 'Fecha propuesta'")
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=400, detail="Indica el motivo de tu contraoferta")
    if not fecha_propuesta_cliente:
        raise HTTPException(status_code=400, detail="Proponé la fecha en la que sí puedes recibir el pedido")

    hoy = _now().date()
    fecha_date = fecha_propuesta_cliente.date() if hasattr(fecha_propuesta_cliente, "date") else fecha_propuesta_cliente
    minima = hoy + timedelta(days=DIAS_MIN_PRODUCCION)
    if fecha_date < minima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha que propongas debe ser al menos {DIAS_MIN_PRODUCCION} días desde hoy (mínimo: {minima.isoformat()})",
        )
    maxima = hoy + relativedelta(months=MESES_MAX_PEDIDO)
    if fecha_date > maxima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha que propongas no puede ser después del {maxima.isoformat()}",
        )

    fecha_anterior = venta.Fecha_entrega_esperada
    venta.Fecha_Rechazada = _now()
    venta.Fecha_entrega_esperada = fecha_propuesta_cliente
    venta.intentos_rechazo = (int(getattr(venta, "intentos_rechazo", 0) or 0)) + 1
    venta.Estado = EstadoPedido.FECHA_PROPUESTA_FINAL

    _guardar_historial_fecha(db, id_venta, TipoAccionFecha.PROPUESTA_FINAL, fecha_propuesta_cliente, motivo.strip(), id_usuario=id_usuario)
    descartar_notificacion(db, "fecha_rechazada", id_venta)
    notificar(
        db, "fecha_rechazada", "El cliente propuso su fecha final",
        f"El cliente del pedido #{id_venta} rechazó la fecha propuesta y ofreció la suya "
        f"({motivo.strip()}). Acéptala o recházala en definitivo.",
        id_venta, "/ventas/pedidos",
    )

    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=venta.Estado,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def rechazar_fecha_final(db: Session, id_venta: int, actual: dict, motivo: str | None = None) -> dict:
    """Admin rechaza en definitivo la propuesta final del cliente (3.4). No
    hay otra ronda de contraofertas: pasa a 'Escalado a admin', el mismo
    estado y el mismo canal de excepción que `solicitar_escalado` — no uno
    nuevo — para que el cliente pueda cancelar o comunicarse directamente con
    el admin (3.4.1).
    """
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.Estado != EstadoPedido.FECHA_PROPUESTA_FINAL:
        raise HTTPException(status_code=400, detail="El pedido no está en estado 'Fecha propuesta final'")

    id_admin = getattr(actual.get("registro"), "ID_Usuario", None)
    venta.Estado = EstadoPedido.ESCALADO_A_ADMIN
    _guardar_historial_fecha(
        db, id_venta, TipoAccionFecha.RECHAZADA_FINAL, venta.Fecha_entrega_esperada, motivo, id_usuario=id_admin
    )
    notificar(
        db, "fecha_rechazada", "Tu propuesta de fecha fue rechazada",
        f"El administrador no pudo aceptar la fecha que propusiste para el pedido #{id_venta}"
        + (f" ({motivo.strip()}). " if motivo else ". ")
        + "Puedes cancelar el pedido o comunicarte directamente con nosotros.",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=venta.Estado,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def solicitar_escalado(db: Session, id_venta: int, actual: dict) -> dict:
    """El cliente pide hablar directamente con el admin (canal de excepción)
    en vez de seguir rechazando la contraoferta. Pasa a 'Escalado a admin':
    el admin lo resuelve con un clic tras la llamada, sin volver a pasar por
    el ciclo de propuesta/aceptación (`resolver_escalado_acuerdo_manual` /
    `resolver_escalado_cancelar`).
    """
    if actual["tipo"] != "cliente":
        raise HTTPException(status_code=403, detail="Solo disponible para clientes")
    id_usuario = actual["registro"].ID_Usuario

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.ID_Usuario != id_usuario:
        raise HTTPException(status_code=403, detail="No puedes escalar pedidos de otros clientes")
    if venta.Estado != EstadoPedido.FECHA_PROPUESTA:
        raise HTTPException(status_code=400, detail="El pedido no está en estado 'Fecha propuesta'")

    venta.Estado = EstadoPedido.ESCALADO_A_ADMIN
    notificar(
        db, "fecha_rechazada", "Cliente pide hablar directamente",
        f"El cliente del pedido #{id_venta} prefiere acordar la fecha de entrega por teléfono.",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=venta.Estado,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def _devolver_credito_venta(db: Session, venta: Venta) -> None:
    """Devuelve el crédito aplicado al crear una venta (si lo hubo).
    Delega en `_abonar_credito` (mismo mecanismo que cualquier otra
    devolución de saldo a favor, en vez de reescribir el crédito/movimiento
    acá — hallazgo #6)."""
    detalle = db.query(DetalleVenta).filter(DetalleVenta.ID_Venta == venta.ID_Venta).first()
    if detalle and detalle.Descuento and detalle.Descuento > 0:
        _abonar_credito(db, venta.ID_Usuario, Decimal(str(detalle.Descuento)), venta.ID_Venta)


def resolver_escalado_acuerdo_manual(
    db: Session, id_venta: int, fecha_acordada, actual: dict
) -> dict:
    """Admin acuerda una fecha manualmente con el cliente escalado.
    El pedido pasa directamente al flujo de producción/confirmación.
    Resetea intentos_rechazo.
    """
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.Estado != EstadoPedido.ESCALADO_A_ADMIN:
        raise HTTPException(status_code=400, detail="El pedido no está en estado 'Escalado a admin'")

    hoy = _now().date()
    fecha_date = fecha_acordada.date() if hasattr(fecha_acordada, "date") else fecha_acordada
    minima = hoy + timedelta(days=DIAS_MIN_PRODUCCION)
    if fecha_date < minima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha acordada debe ser al menos {DIAS_MIN_PRODUCCION} días desde hoy (mínimo: {minima.isoformat()})",
        )
    maxima = hoy + relativedelta(months=MESES_MAX_PEDIDO)
    if fecha_date > maxima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha acordada no puede ser después del {maxima.isoformat()}",
        )

    id_admin = getattr(actual.get("registro"), "ID_Usuario", None)
    _avanzar_tras_fecha_confirmada(db, venta, fecha_acordada, id_usuario=id_admin)
    _guardar_historial_fecha(db, id_venta, TipoAccionFecha.PROPUESTA, fecha_acordada, id_usuario=id_admin)
    notificar(
        db, "fecha_propuesta", "Fecha de entrega acordada por el administrador",
        f"El administrador acordó una fecha de entrega para tu pedido #{id_venta}",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    try:
        from src.shared.services.fcm_service import notificar_cambio_pedido_push
        notificar_cambio_pedido_push(
            id_usuario_cliente=venta.ID_Usuario,
            id_venta=id_venta,
            nuevo_estado=venta.Estado,
            db=db,
        )
    except Exception:
        pass
    return _formato_venta(venta, db)


def resolver_escalado_cancelar(db: Session, id_venta: int, actual: dict) -> dict:
    """Admin cancela el pedido escalado y devuelve el crédito usado."""
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.Estado != EstadoPedido.ESCALADO_A_ADMIN:
        raise HTTPException(status_code=400, detail="El pedido no está en estado 'Escalado a admin'")

    venta.Estado = EstadoPedido.CANCELADO
    _devolver_credito_venta(db, venta)

    # Si se pagó anticipo, abonarlo como saldo a favor. La devolución en efectivo
    # o transferencia la gestiona el admin fuera del sistema; el registro en
    # CreditoCliente asegura que quede trazabilidad y que el cliente pueda usarlo
    # en el próximo pedido si lo prefiere.
    _pago_anticipo_esc = obtener_pago(db, id_venta, TIPO_ANTICIPO)
    _anticipo = Decimal(str(_pago_anticipo_esc.Monto or 0)) if _pago_anticipo_esc else Decimal("0")
    if (_pago_anticipo_esc and _pago_anticipo_esc.Monto and _anticipo > 0
            and anticipo_vuelve_solo(db, id_venta)):
        _abonar_credito(db, venta.ID_Usuario, _anticipo, id_venta)

    # Cancelar OPs abiertas (defensivo: no debería haber ninguna en ESCALADO_A_ADMIN,
    # pero si por algún estado corrupto las hay, hay que cerrarlas igual).
    from src.features.produccion.ordenes_produccion.services.service import (
        cambiar_estado as _cambiar_estado_orden,
    )
    for _orden in db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Venta == id_venta,
        OrdenProduccion.Estado.notin_([11, 5]),
    ).all():
        _cambiar_estado_orden(db, _orden.ID_Orden_Produccion, 5, commit=False)

    notificar(
        db, "fecha_rechazada", "Pedido cancelado por el administrador",
        f"Tu pedido #{id_venta} fue cancelado por el administrador tras múltiples rechazos de fecha.",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


def guardar_envio_completo_domingo(
    db: Session, id_venta: int, valor: bool, actual: dict
) -> dict:
    """Registra la respuesta a '¿Todo el pedido junto el domingo?'.

    Puede ser el propio cliente o un admin/empleado (quien registra la
    decisión en nombre del cliente desde el panel de gestión).
    No bloquea ningún estado: se puede actualizar en cualquier momento.
    """
    es_admin = actual["tipo"] in ("admin", "empleado")
    if actual["tipo"] not in ("cliente", "admin", "empleado"):
        raise HTTPException(status_code=403, detail="Acción no permitida")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if not es_admin and venta.ID_Usuario != actual["registro"].ID_Usuario:
        raise HTTPException(status_code=403, detail="No puedes modificar pedidos de otros clientes")

    venta.Envio_Completo_Domingo = 1 if valor else 0
    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)

