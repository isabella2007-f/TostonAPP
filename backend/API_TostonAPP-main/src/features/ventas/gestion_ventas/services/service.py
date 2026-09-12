from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo

_BOGOTA = ZoneInfo("America/Bogota")


def _now():
    return datetime.now(_BOGOTA).replace(tzinfo=None)

from sqlalchemy import func, case
from src.shared.services.models import (
    Venta, VentaXProducto, DetalleVenta, Producto, ProductoImagen, Usuario,
    Estado, Domicilio, CreditoCliente, MovimientoCredito,
    Descuento, DescuentoXUsuario, DescuentoXVenta, OrdenProduccion, FichaTecnica,
    LoteProducto, HistorialFechasPropuestas, GrupoEnvio, GrupoEnvioItem,
)

# Margen mínimo en días entre la fecha del envío anticipado y hoy
MARGEN_MINIMO_DIAS_ENVIO_ANTICIPADO = 1


def _imagen_producto(db: Session, id_producto: int) -> str | None:
    """URL de la primera imagen del producto (o None). Usa Producto_Imagenes."""
    img = db.query(ProductoImagen).filter(
        ProductoImagen.ID_Producto == id_producto
    ).first()
    return img.imagen if img else None
from src.shared.services.notificaciones_utils import notificar, descartar_notificacion, notificar_stock_producto
from src.features.ventas.pedidos.services.estados import (
    EstadoPedido, ESTADOS_STOCK_DESCONTADO_PICKUP, validar_transicion,
)
from .schemas import VentaCreate, DomicilioVentaInput
from src.shared.services.observaciones_utils import observaciones_limpias
from src.shared.services.pagos_utils import (
    cobro_efectivo_pendiente, comprobante_sin_aprobar,
)
# El precio del domicilio ya NO es una constante: sale de Barrios.Precio ajustado
# por las ofertas activas del barrio ese día (función única del módulo
# Ubicaciones) y se CONGELA como snapshot en Domicilios al crear el pedido.
from src.features.ventas.ubicaciones.services.service import resolver_domicilio

# Porcentaje del pedido que el cliente debe anticipar cuando pide MÁS unidades de
# las que hay en stock (pedido especial / preorden). Regla de negocio del backend:
# nunca se toma del request, el cliente no puede alterarla.
PORCENTAJE_ANTICIPO_SOBRE_STOCK = Decimal("0.50")

#: Estado con el que queda un domicilio cancelado (catálogo de Estados).
#:
#: Lo usa la división de entregas para retirar del tablero el domicilio
#: original, que después de dividir ya no es un viaje sino una plantilla.
ESTADO_DOMICILIO_CANCELADO = 5

# Monto a partir del cual un pedido por encargo pide anticipo. Por debajo el
# trámite le cuesta más al cliente de lo que protege al negocio: un pedido chico
# que no se recoge se le vende al siguiente que entre.
UMBRAL_ANTICIPO = Decimal("100000")


def _pide_anticipo(necesita_produccion: bool, total_pedido) -> bool:
    """Si este pedido tiene que dejar anticipo antes de entrar a producción.

    Dos condiciones, las dos necesarias:

    - Hay que FABRICAR algo. Fabricar es lo único que arriesga plata por
      adelantado: se compran insumos y se ocupa el horno antes de tener nada que
      cobrar, y si el cliente no aparece, ese gasto ya se hizo. Lo que sale del
      stock del día no arriesga nada: el producto ya existe y se le vende al
      siguiente.
    - Y el pedido pesa (más de UMBRAL_ANTICIPO). Por debajo de eso la pérdida
      posible no justifica pedirle a nadie que transfiera por adelantado.

    `necesita_produccion` es el mismo criterio con el que se abren las órdenes
    de producción (`_productos_producibles`): se le pide anticipo exactamente al
    pedido al que se le va a abrir una orden, ni a uno más.
    """
    return bool(necesita_produccion) and Decimal(str(total_pedido)) > UMBRAL_ANTICIPO


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
    """La fecha límite que pide el cliente no puede ser imposible: ni en el
    pasado, ni hoy si ya se cerró por hoy (`_fecha_minima_entrega`)."""
    if not fecha_entrega:
        raise HTTPException(status_code=400, detail="Selecciona para cuándo necesitas tu pedido")
    fecha_date = fecha_entrega.date() if hasattr(fecha_entrega, "date") else fecha_entrega
    minima = _fecha_minima_entrega(db)
    if fecha_date < minima:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha más próxima disponible para tu pedido es {minima.isoformat()}",
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
    """
    if monto <= 0:
        return
    credito = db.query(CreditoCliente).filter(
        CreditoCliente.ID_Usuario == id_usuario
    ).first()
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
    """
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
        precio   = producto.Precio_venta if producto else Decimal("0")
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

    # El domicilio "del pedido" es el que NO pertenece a un grupo de envío
    # (ID_Grupo IS NULL). Tras dividir el pedido pueden coexistir ese row de
    # referencia y uno por grupo; `venta.domicilios[0]` caía en cualquiera.
    domicilio = next(
        (d for d in venta.domicilios if d.ID_Grupo is None),
        venta.domicilios[0] if venta.domicilios else None,
    )
    dom_por_grupo = {
        d.ID_Grupo: d for d in venta.domicilios
        if d.ID_Grupo is not None and d.Estado != 5   # excluye los cancelados
    }
    subtotal_bruto = sum(p["subtotal"] for p in productos)

    # Quién lo lleva. Se busca en el domicilio del pedido y, si ahí no hay,
    # en los de los grupos: al dividir la entrega el repartidor se asigna al
    # domicilio DEL GRUPO y la fila de referencia se queda sin empleado, así
    # que un pedido dividido y en camino se veía como "Sin asignar".
    dom_con_repartidor = next(
        (d for d in ([domicilio] if domicilio else []) + list(venta.domicilios)
         if d is not None and d.ID_Empleado and d.Estado != 5),
        None,
    )
    domiciliario = None
    id_repartidor = dom_con_repartidor.ID_Empleado if dom_con_repartidor else None
    if dom_con_repartidor:
        emp = dom_con_repartidor.empleado
        if emp:
            domiciliario = f"{emp.Nombre} {emp.Apellidos}"

    ordenes_pendientes = sum(
        1 for o in venta.ordenes_produccion
        if o.Estado not in (11, 5)
    )
    ordenes_en_espera = sum(
        1 for o in venta.ordenes_produccion
        if o.Estado == 1
    )

    return {
        "ID_Venta":           venta.ID_Venta,
        "ID_Usuario":         venta.ID_Usuario,
        "nombre_cliente":     f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
        "correo_cliente":     usuario.Correo    if usuario else None,
        "telefono_cliente":   usuario.Telefono  if usuario else None,
        "Total":              venta.Total,
        "subtotal_bruto":     subtotal_bruto,
        "credito_aplicado":   credito_aplicado,
        "descuento_aplicado": descuento_aplicado,
        "Estado":             venta.Estado,
        "estado_label":       _label_estado(db, venta.Estado) if venta.Estado else None,
        "Metodo_Pago":            venta.Metodo_Pago,
        "monto_efectivo":         getattr(venta, "Monto_Efectivo", None),
        "monto_transferencia":    getattr(venta, "Monto_Transferencia", None),
        "Fecha_Venta":            venta.Fecha_Venta,
        "Fecha_pedido":           venta.Fecha_pedido,
        "Fecha_entrega":          getattr(venta, "Fecha_entrega", None),
        "Fecha_entrega_esperada": venta.Fecha_entrega_esperada,
        "productos":              productos,
        "comprobante_pago":             venta.Comprobante_Pago,
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
        "nombre_domiciliario":          domiciliario,
        "ID_Empleado":                  id_repartidor,
        "ordenes_produccion_pendientes": ordenes_pendientes,
        "ordenes_en_espera":             ordenes_en_espera,
        "requiere_produccion":           requiere_produccion,
        # Pedido especial por encima del stock + anticipo del 50% (calculado y
        # verificado en backend al crear la venta).
        "sobre_stock":             bool(getattr(venta, "Sobre_Stock", 0)),
        "anticipo_requerido":      getattr(venta, "Anticipo_Requerido", None),
        "anticipo_pagado":         getattr(venta, "Anticipo_Pagado", None),
        "requiere_anticipo":       bool(getattr(venta, "Requiere_Anticipo", 0)),
        "anticipo_monto":          getattr(venta, "Anticipo_Monto", None),
        "anticipo_metodo_pago":    getattr(venta, "Anticipo_Metodo_Pago", None),
        "anticipo_comprobante_url": getattr(venta, "Anticipo_Comprobante_Url", None),
        "anticipo_registrado":       bool(getattr(venta, "Anticipo_Registrado", 0)),
        "pago_final_registrado":     bool(getattr(venta, "Pago_Final_Registrado", 0)),
        "pago_final_monto":          getattr(venta, "Pago_Final_Monto", None),
        "pago_final_metodo_pago":    getattr(venta, "Pago_Final_Metodo_Pago", None),
        "pago_final_comprobante_url": getattr(venta, "Pago_Final_Comprobante_Url", None),
        "pago_final_fecha":          getattr(venta, "Pago_Final_Fecha", None),
        "estado_pago":               getattr(venta, "Estado_Pago", "pendiente"),
        "motivo_rechazo_comprobante": getattr(venta, "Motivo_Rechazo_Comprobante", None),
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
        "grupos_envio": [
            _formato_grupo(g, dom_por_grupo.get(g.ID_Grupo)) for g in venta.grupos_envio
        ] if venta.grupos_envio else [],
        # Suma de los domicilios que de verdad paga el pedido: si está dividido,
        # uno por cada grupo a domicilio (activo); si no, el snapshot único.
        "costo_domicilio_total": _costo_domicilio_total(venta, domicilio, dom_por_grupo),
    }


def _costo_domicilio_total(venta, domicilio, dom_por_grupo) -> int:
    """Un domicilio por viaje: total de domicilio que refleja `Venta.Total`."""
    if venta.grupos_envio:
        # Pedido dividido: uno por cada grupo a domicilio no cancelado (0, 1 o 2).
        return sum(
            int(d.Precio_Domicilio_Final or 0)
            for d in dom_por_grupo.values()
            if d.Estado != 5
        )
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
    # Un pedido dividido tiene varios: la fila de referencia (sin grupo) y una
    # por grupo. El repartidor se asigna a la del grupo, así que quedarse con
    # una cualquiera —la última que devolviera la consulta— hacía que la tabla
    # dijera "Sin asignar" en pedidos que ya iban en camino. Gana el que tiene
    # repartidor; entre iguales, el de referencia.
    domicilios = {}
    for d in db.query(Domicilio).filter(Domicilio.ID_Venta.in_(venta_ids)).all():
        if d.Estado == 5:                      # cancelado: no cuenta
            continue
        actual = domicilios.get(d.ID_Venta)
        if actual is None:
            domicilios[d.ID_Venta] = d
        elif d.ID_Empleado and not actual.ID_Empleado:
            domicilios[d.ID_Venta] = d
        elif d.ID_Grupo is None and not actual.ID_Empleado:
            domicilios[d.ID_Venta] = d

    # Batch 8: repartidores
    emp_ids = list({d.ID_Empleado for d in domicilios.values() if d.ID_Empleado})
    repartidores = {u.ID_Usuario: u for u in
                    db.query(Usuario).filter(Usuario.ID_Usuario.in_(emp_ids)).all()} if emp_ids else {}

    # Batch 9: grupos de envío — solo estado/tipo, sin ítems ni eager-load
    grupos_rows = db.query(GrupoEnvio).filter(GrupoEnvio.ID_Venta.in_(venta_ids)).all()
    grupos_por_venta: dict = {}
    grupo_ids = []
    for g in grupos_rows:
        grupos_por_venta.setdefault(g.ID_Venta, []).append(g)
        grupo_ids.append(g.ID_Grupo)

    # Batch 10: estado del domicilio por grupo (para mostrar En camino/Entregado real)
    dom_estado_por_grupo: dict = {}
    if grupo_ids:
        for d in db.query(Domicilio).filter(
            Domicilio.ID_Grupo.in_(grupo_ids),
            Domicilio.Estado != 5,
        ).all():
            dom_estado_por_grupo[d.ID_Grupo] = d.Estado

    # Batch 11: órdenes pendientes por venta (COUNT total + en espera=Pendiente)
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
        domiciliario       = (f"{repartidor.Nombre} {repartidor.Apellidos}"
                              if repartidor else None)

        # requiere_fecha_propuesta: usa el snapshot guardado al crear la venta,
        # no el stock actual (que puede haber cambiado después del pedido).
        rfp = bool(getattr(venta, "Sobre_Stock", 0)) or bool(getattr(venta, "Necesita_Produccion", 0))

        result.append({
            "ID_Venta":           venta.ID_Venta,
            "ID_Usuario":         venta.ID_Usuario,
            "nombre_cliente":     f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
            "correo_cliente":     usuario.Correo   if usuario else None,
            "telefono_cliente":   usuario.Telefono if usuario else None,
            "Total":              venta.Total,
            "subtotal_bruto":     subtotal_bruto,
            "credito_aplicado":   credito_aplicado,
            "descuento_aplicado": descuento_aplicado,
            "Estado":             venta.Estado,
            "estado_label":       _label_estado(db, venta.Estado) if venta.Estado else None,
            "Metodo_Pago":            venta.Metodo_Pago,
            "monto_efectivo":         getattr(venta, "Monto_Efectivo", None),
            "monto_transferencia":    getattr(venta, "Monto_Transferencia", None),
            "Fecha_Venta":            venta.Fecha_Venta,
            "Fecha_pedido":           venta.Fecha_pedido,
            "Fecha_entrega":          getattr(venta, "Fecha_entrega", None),
            "Fecha_entrega_esperada": venta.Fecha_entrega_esperada,
            "productos":              prods_list,
            "comprobante_pago":             venta.Comprobante_Pago,
            "tiene_domicilio":              dom is not None,
            "ID_Domicilio":                 dom.ID_Domicilio        if dom else None,
            "direccion_entrega":            dom.Direccion_entrega    if dom else None,
            "municipio_entrega":            dom.Municipio_entrega    if dom else None,
            "departamento_entrega":         dom.Departamento_entrega if dom else None,
            "observaciones_domicilio":      observaciones_limpias(dom.Observaciones) if dom else None,
            "nombre_domiciliario":          domiciliario,
            "ID_Empleado":                  dom.ID_Empleado if dom else None,
            "ordenes_produccion_pendientes": ordenes_counts.get(venta.ID_Venta, 0),
            "ordenes_en_espera":             ordenes_espera.get(venta.ID_Venta, 0),
            "requiere_produccion":           requiere_produccion,
            "sobre_stock":             bool(getattr(venta, "Sobre_Stock", 0)),
            "anticipo_requerido":      getattr(venta, "Anticipo_Requerido", None),
            "anticipo_pagado":         getattr(venta, "Anticipo_Pagado", None),
            "requiere_anticipo":       bool(getattr(venta, "Requiere_Anticipo", 0)),
            "anticipo_monto":          getattr(venta, "Anticipo_Monto", None),
            "anticipo_metodo_pago":    getattr(venta, "Anticipo_Metodo_Pago", None),
            "anticipo_comprobante_url": getattr(venta, "Anticipo_Comprobante_Url", None),
            "anticipo_registrado":       bool(getattr(venta, "Anticipo_Registrado", 0)),
            "pago_final_registrado":     bool(getattr(venta, "Pago_Final_Registrado", 0)),
            "pago_final_monto":          getattr(venta, "Pago_Final_Monto", None),
            "pago_final_metodo_pago":    getattr(venta, "Pago_Final_Metodo_Pago", None),
            "pago_final_comprobante_url": getattr(venta, "Pago_Final_Comprobante_Url", None),
            "pago_final_fecha":          getattr(venta, "Pago_Final_Fecha", None),
            "estado_pago":               getattr(venta, "Estado_Pago", "pendiente"),
            "motivo_rechazo_comprobante": getattr(venta, "Motivo_Rechazo_Comprobante", None),
            "requiere_fecha_propuesta": rfp,
            "fecha_rechazada":  getattr(venta, "Fecha_Rechazada", None),
            "intentos_rechazo": int(getattr(venta, "intentos_rechazo", 0) or 0),
        # A partir de este número de rechazos, el frontend resalta con más
        # énfasis el canal de excepción (hablar con el admin) — no bloquea ni
        # cancela nada por sí solo, es puramente informativo.
        "resaltar_canal_excepcion": int(getattr(venta, "intentos_rechazo", 0) or 0) >= LIMITE_INTENTOS_RECHAZO,
            "envio_completo_domingo": (
                None if getattr(venta, "Envio_Completo_Domingo", None) is None
                else bool(venta.Envio_Completo_Domingo)
            ),
            # Resumen liviano de grupos para el listado. El detalle completo
            # (con ítems y snapshot de domicilio) llega por _formato_venta.
            "grupos_envio": [],
            "grupos_resumen": [
                {
                    "tipo":            g.Tipo,
                    "estado":          g.Estado,
                    "tipo_entrega":    g.Tipo_Entrega,
                    "domicilio_estado": dom_estado_por_grupo.get(g.ID_Grupo),
                }
                for g in grupos_por_venta.get(venta.ID_Venta, [])
            ],
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
            selectinload(Venta.grupos_envio)
                .selectinload(GrupoEnvio.items),
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
            selectinload(Venta.grupos_envio)
                .selectinload(GrupoEnvio.items),
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
        Comprobante_Pago       = datos.comprobante_pago,
        Estado_Pago            = _estado_pago_inicial,
    )
    db.add(nueva_venta)
    db.flush()

    notificar(
        db, "pedido_nuevo", "Nuevo pedido recibido",
        f"El pedido #{nueva_venta.ID_Venta} está esperando ser procesado",
        nueva_venta.ID_Venta, "/ventas/pedidos",
    )

    for p in datos.productos:
        db.add(VentaXProducto(
            ID_Venta          = nueva_venta.ID_Venta,
            ID_Producto       = p.ID_Producto,
            Cantidad          = p.Cantidad,
            Cantidad_Preorden = preorden_por_producto.get(p.ID_Producto, 0),
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

    # Pago mixto: el reparto se hace sobre el total ya cerrado (con domicilio,
    # descuentos y saldo a favor aplicados), no sobre lo que declaró el cliente.
    if _es_mixto(datos.Metodo_Pago):
        nueva_venta.Monto_Efectivo, nueva_venta.Monto_Transferencia = _partir_pago_mixto(
            nueva_venta.Total, datos.pago_efectivo_monto
        )

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
        anticipo_obligatorio = _pide_anticipo(necesita_produccion, total_pedido)
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

            # El pedido creado por el personal en el mostrador se cobra en el acto:
            # queda marcado como sobre stock, pero no se le exige el anticipo online.
            if not datos.creado_por_admin and anticipo_pagado < anticipo_requerido and not tiene_soporte:
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
            nueva_venta.Anticipo_Pagado    = anticipo_pagado
            # Cuando el flujo de anticipo explícito no se activa (solo ítems de
            # producción sobre stock) pero el cliente sí aportó respaldo de pago,
            # registrar igual para que el panel muestre el monto correcto.
            if not datos.requiere_anticipo and tiene_soporte:
                nueva_venta.Anticipo_Registrado = 1
                nueva_venta.Anticipo_Monto      = anticipo_requerido
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
            nueva_venta.Anticipo_Monto           = datos.anticipo_monto
            nueva_venta.Anticipo_Metodo_Pago     = datos.anticipo_metodo_pago
            nueva_venta.Anticipo_Comprobante_Url = datos.anticipo_comprobante_url
            nueva_venta.Anticipo_Registrado      = 1 if datos.anticipo_registrado else 0
            nueva_venta.Estado_Pago              = "anticipo_pagado" if datos.anticipo_registrado else "pendiente"
            # El cliente eligió pagar el total completo ahora. Se usa la bandera
            # explícita (pagar_todo) en vez de comparar montos: la diferencia de
            # redondeo entre el total del cliente (JS) y el servidor (Decimal) puede
            # dejar el pedido en "anticipo_pagado" aunque el cliente pagara todo.
            _pago_total = getattr(datos, "pagar_todo", False)
            if datos.anticipo_registrado and (
                _pago_total
                or (datos.anticipo_monto is not None and float(datos.anticipo_monto) >= float(nueva_venta.Total or 0))
            ):
                nueva_venta.Pago_Final_Registrado = 1
                nueva_venta.Estado_Pago           = "pagado_completo"
    else:
        # ── Pedido del cliente: sin anticipo ni comprobante al crear ────────
        # Con producción: queda "Pendiente de Aprobación" (Estado ya nace en
        # PENDIENTE) con la fecha obligatoria ya validada arriba. El anticipo
        # (si aplica) se pide después de que el admin apruebe esa fecha, no acá.
        if necesita_produccion:
            # Puede terminar pidiendo anticipo una vez se apruebe la fecha
            # (`_avanzar_tras_fecha_confirmada`); si ya se sabe que el método
            # mixto no serviría para eso, se corta acá en vez de dejarlo pasar
            # y fallar más adelante.
            if _mixto_bloqueado_por_anticipo(datos.Metodo_Pago, _pide_anticipo(True, nueva_venta.Total)):
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Este pedido puede requerir anticipo una vez se apruebe la fecha de "
                        "entrega, y el método mixto no sirve para anticipar. Elige Efectivo o "
                        "Transferencia."
                    ),
                )
        else:
            # Sin producción: no hay nada que aprobar en planta. Va directo a
            # Esperando Pago (transferencia/mixto) o En Alistamiento (efectivo);
            # el comprobante se adjunta después, ya no aquí.
            if _es_transferencia(datos.Metodo_Pago) or _es_mixto(datos.Metodo_Pago):
                nueva_venta.Estado = EstadoPedido.ESPERANDO_PAGO
            else:
                nueva_venta.Estado = EstadoPedido.CONFIRMADO
                # Como al confirmar cualquier pedido sin domicilio: reservar
                # (descontar) el stock de lo que se recoge en tienda. Sin
                # déficit alguno (necesita_produccion es False), sale la
                # línea completa — no hay preorden que esperar.
                if not datos.domicilio:
                    _descontar_stock_venta(db, nueva_venta.ID_Venta, PARTE_TODO)

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
        IVA         = Decimal("0"),
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
    # Si pasó las 3 validaciones anteriores, se guarda el pago
    # y se marca la venta como completamente pagada.
    venta.Pago_Final_Monto           = datos.monto
    venta.Pago_Final_Metodo_Pago     = datos.metodo_pago
    venta.Pago_Final_Comprobante_Url = datos.comprobante_url
    venta.Pago_Final_Fecha           = _now()
    venta.Pago_Final_Registrado      = 1
    venta.Estado_Pago                = "pagado_completo"

    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


_VENTANA_PROTECCION = timedelta(minutes=10)


def cambiar_estado(db: Session, id_venta: int, nuevo_estado: int) -> dict:
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    # Durante los primeros 10 minutos el pedido es exclusivo del cliente para
    # que pueda modificarlo o cancelarlo sin que un empleado lo procese antes.
    if venta.Fecha_Venta and (datetime.utcnow() - venta.Fecha_Venta) < _VENTANA_PROTECCION:
        mins_restantes = int((_VENTANA_PROTECCION - (datetime.utcnow() - venta.Fecha_Venta)).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=400,
            detail=f"Este pedido está en período de edición del cliente ({mins_restantes} min restantes). Espera antes de procesarlo.",
        )

    tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == id_venta).first() is not None

    # Valida que la transición esté permitida por la máquina de estados
    validar_transicion(venta.Estado, nuevo_estado, tiene_domicilio)

    # No se puede cancelar el pedido completo si al menos un grupo ya fue entregado.
    # En ese caso solo se puede cancelar el grupo pendiente individualmente.
    if nuevo_estado == EstadoPedido.CANCELADO:
        grupos_entregados = db.query(GrupoEnvio).filter(
            GrupoEnvio.ID_Venta == id_venta,
            GrupoEnvio.Estado == "entregado",
        ).count()
        if grupos_entregados > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se puede cancelar el pedido completo porque al menos un grupo "
                    "ya fue entregado. Cancelá únicamente el grupo que sigue pendiente."
                ),
            )

    # Confirmar es aceptar el pedido: no se acepta un pago que nadie revisó.
    # El comprobante lo sube el cliente y lo aprueba el admin; si se confirma
    # antes, el pedido entra a producción y se despacha contra una imagen que
    # después puede resultar falsa o de otro monto.
    if nuevo_estado == EstadoPedido.CONFIRMADO and comprobante_sin_aprobar(venta):
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

    # Entregar es cerrar la venta: no se cierra sin decir qué pasó con la
    # plata que se cobra en mano. Con domicilio la recibe el repartidor y en
    # tienda la recibe quien atiende el mostrador; en los dos casos, marcar
    # el pedido como entregado sin registrar ese cobro deja la venta cerrada
    # y el efectivo sin rastro. Registrarlo también es declarar que NO se
    # pudo cobrar (con motivo): lo que no vale es entregar sin decirlo.
    if nuevo_estado == EstadoPedido.ENTREGADO and cobro_efectivo_pendiente(venta):
        raise HTTPException(
            status_code=400,
            detail=(
                "Registrá el cobro en efectivo antes de marcar el pedido como "
                "entregado: este pedido se paga (total o en parte) en mano."
            ),
        )

    # Bloquear paso a ENTREGADO si el pedido requiere anticipo y el saldo no fue registrado.
    # No afecta pedidos donde Requiere_Anticipo == 0 (flujo normal sin anticipo).
    if nuevo_estado == EstadoPedido.ENTREGADO and getattr(venta, "Requiere_Anticipo", 0):
        if not getattr(venta, "Pago_Final_Registrado", 0):
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
    _soporte_pago = venta.Comprobante_Pago or getattr(venta, "Anticipo_Comprobante_Url", None)
    _hay_transferencia = (
        "transfer" in _metodo
        or ("mixto" in _metodo and float(venta.Monto_Transferencia or 0) > 0)
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

    # Al cancelar: restaurar stock si ya fue descontado
    # - pickup: stock se descuenta en CONFIRMADO; se restaura desde confirmado/preparando/listo
    # - domicilio: stock se descuenta en ENTREGADO; no aplica al cancelar (nunca llegó)
    if nuevo_estado == EstadoPedido.CANCELADO:
        stock_descontado = (
            not tiene_domicilio and venta.Estado in ESTADOS_STOCK_DESCONTADO_PICKUP
        )
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
        _anticipo = Decimal(str(getattr(venta, "Anticipo_Monto", None) or 0))
        if (getattr(venta, "Anticipo_Registrado", 0) and _anticipo > 0
                and anticipo_vuelve_solo(db, id_venta)):
            _abonar_credito(db, venta.ID_Usuario, _anticipo, id_venta)

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


def proponer_fecha(db: Session, id_venta: int, fecha_entrega, id_admin: int | None = None) -> dict:
    """Admin propone una fecha de entrega.
    Válido en ventas Pendientes, Fecha propuesta, Fecha rechazada o Escalado a admin.
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
    # La fecha propuesta no puede ser en el pasado
    hoy = _now().date()
    fecha_propuesta_date = fecha_entrega.date() if hasattr(fecha_entrega, "date") else fecha_entrega
    if fecha_propuesta_date < hoy:
        raise HTTPException(
            status_code=400,
            detail="La fecha de entrega propuesta no puede ser en el pasado",
        )
    descartar_notificacion(db, "produccion_requerida", id_venta)
    descartar_notificacion(db, "pedido_sobre_stock",   id_venta)
    venta.Estado = EstadoPedido.FECHA_PROPUESTA
    venta.Fecha_entrega_esperada = fecha_entrega
    _guardar_historial_fecha(db, id_venta, "propuesta", fecha_entrega, id_usuario=id_admin)
    notificar(
        db, "fecha_propuesta", "Fecha de entrega propuesta",
        f"El administrador propuso una fecha de entrega para tu pedido #{id_venta}",
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

    anticipo_obligatorio = _pide_anticipo(True, venta.Total)
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
    _tiene_domicilio = db.query(Domicilio).filter(Domicilio.ID_Venta == venta.ID_Venta).first() is not None
    if not _tiene_domicilio:
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


def aprobar_fecha_directa(db: Session, id_venta: int, actual: dict) -> dict:
    """Admin aprueba en 1 clic la fecha que el cliente pidió al hacer el
    pedido (Camino A). A diferencia de `proponer_fecha`, no cambia la fecha ni
    pasa por 'Fecha propuesta': el cliente ya la puso, el admin solo confirma
    que la planta puede cumplirla.
    """
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.Estado != EstadoPedido.PENDIENTE:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede aprobar un pedido 'Pendiente de Aprobación'",
        )
    if not requiere_fecha_propuesta(db, venta):
        raise HTTPException(status_code=400, detail="Este pedido no requiere aprobación de fecha")
    if not venta.Fecha_entrega_esperada:
        raise HTTPException(status_code=400, detail="El pedido no tiene una fecha para aprobar")

    id_admin = getattr(actual.get("registro"), "ID_Usuario", None)
    descartar_notificacion(db, "produccion_requerida", id_venta)
    descartar_notificacion(db, "pedido_sobre_stock",   id_venta)
    _avanzar_tras_fecha_confirmada(db, venta, venta.Fecha_entrega_esperada, id_usuario=id_admin)
    _guardar_historial_fecha(db, id_venta, "aceptada", venta.Fecha_entrega_esperada, id_usuario=id_admin)

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

    _guardar_historial_fecha(db, id_venta, "aceptada", venta.Fecha_entrega_esperada, id_usuario=id_usuario)
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


def rechazar_fecha(db: Session, id_venta: int, actual: dict, motivo: str | None = None) -> dict:
    """El cliente rechaza la contraoferta de fecha, con una causa opcional.

    Reabre la negociación: vuelve a 'Pendiente de Aprobación' con la fecha en
    blanco, para que el admin apruebe una fecha o proponga otra. No hay tope
    que cancele ni escale solo — `intentos_rechazo` solo sirve para que el
    frontend resalte con más énfasis el canal de excepción a partir de cierto
    número; cancelar o pedir hablar con el admin sigue siendo decisión del
    cliente (`solicitar_escalado` / cancelar el pedido).
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

    fecha_anterior = venta.Fecha_entrega_esperada
    venta.Fecha_Rechazada = _now()
    venta.Fecha_entrega_esperada = None
    venta.intentos_rechazo = (int(getattr(venta, "intentos_rechazo", 0) or 0)) + 1
    venta.Estado = EstadoPedido.PENDIENTE

    _guardar_historial_fecha(db, id_venta, "rechazada", fecha_anterior, motivo, id_usuario=id_usuario)
    descartar_notificacion(db, "fecha_rechazada", id_venta)
    notificar(
        db, "fecha_rechazada", "Fecha rechazada por el cliente",
        f"El cliente rechazó la fecha del pedido #{id_venta}"
        + (f" ({motivo}). " if motivo else ". ")
        + "Aprobá una nueva fecha o proponé otra.",
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
    """Devuelve el crédito aplicado al crear una venta (si lo hubo)."""
    detalle = db.query(DetalleVenta).filter(DetalleVenta.ID_Venta == venta.ID_Venta).first()
    if detalle and detalle.Descuento and detalle.Descuento > 0:
        credito = db.query(CreditoCliente).filter(
            CreditoCliente.ID_Usuario == venta.ID_Usuario
        ).first()
        if credito:
            credito.Saldo       += detalle.Descuento
            credito.Fecha_Update = _now()
            db.add(MovimientoCredito(
                ID_Credito    = credito.ID_Credito,
                ID_Devolucion = None,
                ID_Venta      = venta.ID_Venta,
                Tipo          = "recarga",
                Monto         = detalle.Descuento,
                Fecha         = _now(),
            ))


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
    if fecha_date < hoy:
        raise HTTPException(status_code=400, detail="La fecha acordada no puede ser en el pasado")

    id_admin = getattr(actual.get("registro"), "ID_Usuario", None)
    _avanzar_tras_fecha_confirmada(db, venta, fecha_acordada, id_usuario=id_admin)
    _guardar_historial_fecha(db, id_venta, "propuesta", fecha_acordada, id_usuario=id_admin)
    notificar(
        db, "fecha_propuesta", "Fecha de entrega acordada por el administrador",
        f"El administrador acordó una fecha de entrega para tu pedido #{id_venta}",
        id_venta, "/ventas/pedidos",
    )
    db.commit()
    db.refresh(venta)
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
    _anticipo = Decimal(str(getattr(venta, "Anticipo_Monto", None) or 0))
    if (getattr(venta, "Anticipo_Registrado", 0) and _anticipo > 0
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


# ── Feature "Grupos de envío" ──────────────────────────────────────────────

def _items_listos_venta(db: Session, id_venta: int) -> dict[int, int]:
    """Cantidad de unidades listas por producto del pedido.

    Retorna {id_producto: cantidad_lista} para cada línea del pedido.

    - Sin OP (estaba en stock): todas las unidades listas.
    - OP completada (Estado 11): todas las unidades listas.
    - OP activa: las unidades cubiertas por stock (Cantidad - Cantidad_Preorden)
      son listas ahora; las restantes (Cantidad_Preorden) siguen en producción.
      Si Cantidad_Preorden == Cantidad, cantidad_lista = 0.
    """
    items = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
    ordenes = db.query(OrdenProduccion).filter(OrdenProduccion.ID_Venta == id_venta).all()
    estado_por_producto = {o.ID_Producto: o.Estado for o in ordenes}

    resultado: dict[int, int] = {}
    for item in items:
        if item.ID_Producto not in estado_por_producto:
            resultado[item.ID_Producto] = item.Cantidad
        elif estado_por_producto[item.ID_Producto] == 11:
            resultado[item.ID_Producto] = item.Cantidad
        else:
            preorden = item.Cantidad_Preorden or 0
            resultado[item.ID_Producto] = max(0, item.Cantidad - preorden)
    return resultado


def _formato_grupo(grupo: GrupoEnvio, dom: Domicilio | None = None) -> dict:
    """`dom`: el `Domicilio` de este grupo (si `Tipo_Entrega == 'domicilio'`).
    Un domicilio por viaje: cada grupo a domicilio trae su propio snapshot."""
    return {
        "id_grupo":             grupo.ID_Grupo,
        "tipo":                 grupo.Tipo,
        "fecha":                grupo.Fecha_Entrega,
        "tipo_entrega":         grupo.Tipo_Entrega,
        "estado":               grupo.Estado,
        "domicilio_estado":     dom.Estado if dom else None,
        "productos":            [{"id_producto": i.ID_Producto, "cantidad": i.Cantidad} for i in grupo.items],
        "direccion_entrega":    dom.Direccion_entrega     if dom else None,
        "municipio_entrega":    dom.Municipio_entrega     if dom else None,
        "departamento_entrega": dom.Departamento_entrega  if dom else None,
        "domicilio_con_repartidor": bool(dom and dom.ID_Empleado),
        "barrio_entrega":         (dom.barrio.Nombre if (dom and dom.barrio) else None),
        "precio_domicilio_base":  dom.Precio_Domicilio_Base  if dom else None,
        "precio_domicilio_final": dom.Precio_Domicilio_Final if dom else None,
        "desglose_domicilio":     dom.Desglose_Ofertas       if dom else None,
    }


def obtener_items_listos(db: Session, id_venta: int, actual: dict) -> dict:
    """Devuelve qué productos del pedido ya están listos y cuáles no.

    Solo el cliente dueño del pedido o un empleado/admin pueden consultarlo.
    """
    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if actual["tipo"] == "cliente" and venta.ID_Usuario != actual["registro"].ID_Usuario:
        raise HTTPException(status_code=403, detail="No puedes consultar pedidos de otros clientes")

    todos_items = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
    listos = _items_listos_venta(db, id_venta)

    prod_ids = [i.ID_Producto for i in todos_items]
    productos_map = {p.ID_Producto: p for p in
                     db.query(Producto).filter(Producto.ID_Producto.in_(prod_ids)).all()} if prod_ids else {}

    resultado_listos = []
    resultado_pendientes = []
    for item in todos_items:
        nombre = getattr(productos_map.get(item.ID_Producto), "nombre", "") or ""
        cant_lista = listos.get(item.ID_Producto, 0)
        cant_pendiente = item.Cantidad - cant_lista
        if cant_lista > 0:
            resultado_listos.append({"id_producto": item.ID_Producto, "nombre": nombre, "cantidad": cant_lista})
        if cant_pendiente > 0:
            resultado_pendientes.append({"id_producto": item.ID_Producto, "nombre": nombre, "cantidad": cant_pendiente})

    return {
        "id_venta": id_venta,
        "listos":     resultado_listos,
        "pendientes": resultado_pendientes,
    }


def _via_grupo(direccion_req, venta, cliente, db):
    """La vía / complemento (texto libre) de un grupo a domicilio.

    Prioridad: payload → domicilio original de la venta → dirección del perfil.
    Municipio y departamento ya NO salen de acá: los deriva el barrio (snapshot).
    """
    if direccion_req:
        return direccion_req
    dom_orig = db.query(Domicilio).filter(
        Domicilio.ID_Venta == venta.ID_Venta,
        Domicilio.ID_Grupo.is_(None),
    ).first()
    if dom_orig and dom_orig.Direccion_entrega:
        return dom_orig.Direccion_entrega
    if cliente and cliente.Direccion:
        return cliente.Direccion
    return None


def _domicilio_grupo_kwargs(db, id_barrio_pref, dom_orig, fecha, direccion_txt, venta, cliente):
    """Un domicilio por viaje: snapshot PROPIO del domicilio de un grupo.

    Barrio: el del payload o, si no llega, el del domicilio original del pedido.
    Precio: `resolver_domicilio` con la fecha de entrega de ESE grupo (valida
    cobertura y aplica las ofertas de ese día). Devuelve (kwargs_Domicilio, final).
    """
    id_barrio = id_barrio_pref or (dom_orig.ID_Barrio if dom_orig else None)
    if not id_barrio:
        raise HTTPException(
            status_code=400,
            detail="Elige el barrio de entrega del grupo que recibes a domicilio.",
        )
    snap = resolver_domicilio(db, id_barrio, fecha)   # valida cobertura → 400
    return dict(
        ID_Venta             = venta.ID_Venta,
        Estado               = 3,   # PENDIENTE
        Fecha_asignacion     = _now(),
        Direccion_entrega    = _via_grupo(direccion_txt, venta, cliente, db),
        Municipio_entrega    = snap["ciudad"],
        Departamento_entrega = snap["departamento"],
        ID_Barrio              = snap["id_barrio"],
        Precio_Domicilio_Base  = snap["base"],
        Precio_Domicilio_Final = snap["final"],
        Desglose_Ofertas       = snap["desglose"],
    ), int(snap["final"])


def crear_grupos_envio(
    db: Session,
    id_venta: int,
    fecha_anticipada,
    tipo_entrega_a: str | None,
    tipo_entrega_b: str | None,
    actual: dict,
    direccion_a: str | None = None,
    id_barrio_a: int | None = None,
    direccion_b: str | None = None,
    id_barrio_b: int | None = None,
) -> dict:
    """Registra la preferencia de entrega anticipada del cliente.

    Caso A (división): algunos productos listos, otros en producción →
      Grupo A (anticipado, items listos, fecha elegida) + Grupo B (programado,
      items en producción, fecha aceptada original).

    Caso B (todo listo): todos los productos ya están listos → solo Grupo A
      (anticipado, todos los items, fecha elegida). No se crea Grupo B.

    Validaciones comunes:
    - Solo el cliente dueño del pedido, en estado CONFIRMADO/PREPARANDO/LISTO
    - No se pueden crear grupos si ya existen para esta venta
    - Debe haber al menos un producto en el pedido
    - fecha_anticipada >= hoy + MARGEN_MINIMO_DIAS_ENVIO_ANTICIPADO
    - fecha_anticipada < Fecha_entrega_esperada
    """
    es_admin = actual["tipo"] in ("admin", "empleado")
    es_cliente = actual["tipo"] == "cliente"
    if not es_admin and not es_cliente:
        raise HTTPException(status_code=403, detail="Acción no permitida para este tipo de usuario")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if es_cliente and venta.ID_Usuario != actual["registro"].ID_Usuario:
        raise HTTPException(status_code=403, detail="No puedes modificar pedidos de otros clientes")

    estados_validos = (EstadoPedido.CONFIRMADO, EstadoPedido.PREPARANDO, EstadoPedido.LISTO)
    if venta.Estado not in estados_validos:
        raise HTTPException(
            status_code=400,
            detail="Solo se puede solicitar entrega anticipada después de aceptar la fecha propuesta",
        )

    if db.query(GrupoEnvio).filter(GrupoEnvio.ID_Venta == id_venta).count() > 0:
        raise HTTPException(status_code=400, detail="Este pedido ya tiene grupos de envío creados")

    if not venta.Fecha_entrega_esperada:
        raise HTTPException(
            status_code=400,
            detail="Debe acordarse una fecha de entrega antes de poder dividir el pedido",
        )

    todos_items = db.query(VentaXProducto).filter(VentaXProducto.ID_Venta == id_venta).all()
    listos = _items_listos_venta(db, id_venta)  # {id_producto: cantidad_lista}

    if not todos_items:
        raise HTTPException(status_code=400, detail="El pedido no tiene productos")
    if not any(v > 0 for v in listos.values()):
        raise HTTPException(status_code=400, detail="Ningún producto está listo todavía; no se puede solicitar entrega anticipada")

    hoy = _now().date()
    min_fecha = hoy + timedelta(days=MARGEN_MINIMO_DIAS_ENVIO_ANTICIPADO)
    fecha_anticipada_date = fecha_anticipada.date() if hasattr(fecha_anticipada, "date") else fecha_anticipada
    if fecha_anticipada_date < min_fecha:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha de envío anticipado debe ser al menos {MARGEN_MINIMO_DIAS_ENVIO_ANTICIPADO} día(s) a partir de hoy",
        )

    fecha_programada = venta.Fecha_entrega_esperada
    if fecha_programada and fecha_anticipada_date >= (fecha_programada.date() if hasattr(fecha_programada, "date") else fecha_programada):
        raise HTTPException(
            status_code=400,
            detail="La fecha de envío anticipado debe ser anterior a la fecha de entrega acordada",
        )

    grupo_a = GrupoEnvio(
        ID_Venta=id_venta, Tipo="anticipado",
        Fecha_Entrega=fecha_anticipada, Tipo_Entrega=tipo_entrega_a, Estado="pendiente",
    )
    db.add(grupo_a)
    db.flush()
    hay_pendientes = False
    for item in todos_items:
        cant_lista = listos.get(item.ID_Producto, 0)
        cant_pendiente = item.Cantidad - cant_lista
        if cant_lista > 0:
            db.add(GrupoEnvioItem(ID_Grupo=grupo_a.ID_Grupo, ID_Venta=id_venta, ID_Producto=item.ID_Producto, Cantidad=cant_lista))
        if cant_pendiente > 0:
            hay_pendientes = True

    grupo_b = None
    if hay_pendientes:
        grupo_b = GrupoEnvio(
            ID_Venta=id_venta, Tipo="programado",
            Fecha_Entrega=fecha_programada, Tipo_Entrega=tipo_entrega_b, Estado="pendiente",
        )
        db.add(grupo_b)
        db.flush()
        for item in todos_items:
            cant_pendiente = item.Cantidad - listos.get(item.ID_Producto, 0)
            if cant_pendiente > 0:
                db.add(GrupoEnvioItem(ID_Grupo=grupo_b.ID_Grupo, ID_Venta=id_venta, ID_Producto=item.ID_Producto, Cantidad=cant_pendiente))

    # Un domicilio por viaje. Cada grupo que se entrega a domicilio paga su
    # PROPIO domicilio, con snapshot propio (su barrio + ofertas de SU fecha de
    # entrega). Se recalcula el aporte del domicilio a `Venta.Total`: sale el que
    # se congeló al crear el pedido (dom_orig) y entran los de los grupos.
    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == venta.ID_Usuario).first()
    dom_orig = db.query(Domicilio).filter(
        Domicilio.ID_Venta == id_venta, Domicilio.ID_Grupo.is_(None),
    ).first()
    costo_domicilio_anterior = int(dom_orig.Precio_Domicilio_Final or 0) if dom_orig else 0
    costo_domicilio_grupos = 0

    if tipo_entrega_a == "domicilio":
        kw_a, final_a = _domicilio_grupo_kwargs(
            db, id_barrio_a, dom_orig, grupo_a.Fecha_Entrega, direccion_a, venta, cliente
        )
        db.add(Domicilio(ID_Grupo=grupo_a.ID_Grupo, **kw_a))
        costo_domicilio_grupos += final_a

    if grupo_b and tipo_entrega_b == "domicilio":
        kw_b, final_b = _domicilio_grupo_kwargs(
            db, id_barrio_b, dom_orig, grupo_b.Fecha_Entrega, direccion_b, venta, cliente
        )
        db.add(Domicilio(ID_Grupo=grupo_b.ID_Grupo, **kw_b))
        costo_domicilio_grupos += final_b

    venta.Total = (
        (venta.Total or Decimal("0"))
        - Decimal(costo_domicilio_anterior)
        + Decimal(costo_domicilio_grupos)
    )

    # El domicilio original deja de ser un viaje: su precio acaba de salir del
    # total y los productos los llevan los grupos. La fila se conserva —de ella
    # salen la dirección que heredan los grupos y este mismo precio— pero
    # cancelada, o queda en el tablero una entrega que nadie va a tomar nunca y
    # que igual cuenta como domicilio del día.
    if dom_orig:
        dom_orig.Estado = ESTADO_DOMICILIO_CANCELADO
        dom_orig.ID_Empleado = None

    venta.Envio_Completo_Domingo = 0
    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


def _recalcular_estado_pedido(venta: Venta, grupos: list) -> "EstadoPedido | None":
    """Deriva el estado de cabecera del pedido desde los estados de sus grupos de envío.

    Solo aplica cuando el pedido tiene grupos (entrega dividida). Retorna el nuevo
    EstadoPedido, o None si todavía no hay evento de despacho que lo determine.
    """
    if not grupos:
        return None

    estados = {g.Estado for g in grupos}

    if estados == {"entregado"}:
        return EstadoPedido.ENTREGADO

    if estados == {"enviado"}:
        return EstadoPedido.EN_CAMINO

    # Todos los grupos terminaron cancelados sin ninguna entrega
    if estados <= {"cancelado"}:
        return EstadoPedido.CANCELADO

    # Al menos un grupo fue despachado (enviado o entregado) pero no todos están entregados
    if estados & {"enviado", "entregado"}:
        return EstadoPedido.PARCIALMENTE_ENTREGADO

    return None  # todos pendientes — el estado lo sigue manejando _sync_venta_por_ordenes


def actualizar_estado_grupo(
    db: Session,
    id_venta: int,
    id_grupo: int,
    nuevo_estado: str,
    actual: dict,
) -> dict:
    """Admin avanza el estado de un grupo de envío (pendiente→enviado→entregado)."""
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    grupo = db.query(GrupoEnvio).filter(
        GrupoEnvio.ID_Grupo == id_grupo,
        GrupoEnvio.ID_Venta == id_venta,
    ).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo de envío no encontrado")

    FLUJO_ESTADOS = {"pendiente": "enviado", "enviado": "entregado"}
    if nuevo_estado not in ("enviado", "entregado"):
        raise HTTPException(status_code=400, detail="Estado inválido: usa 'enviado' o 'entregado'")
    if FLUJO_ESTADOS.get(grupo.Estado) != nuevo_estado:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede pasar de '{grupo.Estado}' a '{nuevo_estado}'",
        )

    # Grupo programado: puede tener OPs abiertas para sus productos. Se valida
    # directo contra OrdenProduccion filtrada por los productos de ESTE grupo,
    # sin usar _items_listos_venta() (su pool es global a la venta y contiene
    # también las unidades del grupo anticipado, produciendo falsos negativos).
    # Grupo anticipado: por construcción siempre está cubierto; no se valida.
    if grupo.Tipo == "programado" and nuevo_estado == "enviado":
        ids_prod = [i.ID_Producto for i in
                    db.query(GrupoEnvioItem).filter(GrupoEnvioItem.ID_Grupo == id_grupo).all()]
        if ids_prod and db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == id_venta,
            OrdenProduccion.ID_Producto.in_(ids_prod),
            OrdenProduccion.Estado.notin_([11, 5]),
        ).count() > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "El grupo programado aún tiene producción pendiente. "
                    "Completá las órdenes de producción antes de marcarlo como enviado."
                ),
            )

    # Al entregar un grupo tienda programado: misma validación directa contra OP.
    # Anticipado tienda: sin validación (ídem arriba). Domicilio: valida en
    # domicilios/service.py cambiar_estado(), no aquí.
    if nuevo_estado == "entregado" and grupo.Tipo_Entrega == "tienda" and grupo.Tipo == "programado":
        ids_prod_e = [i.ID_Producto for i in
                      db.query(GrupoEnvioItem).filter(GrupoEnvioItem.ID_Grupo == id_grupo).all()]
        if ids_prod_e and db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == id_venta,
            OrdenProduccion.ID_Producto.in_(ids_prod_e),
            OrdenProduccion.Estado.notin_([11, 5]),
        ).count() > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "La producción de este grupo aún no está completada. "
                    "Completá las órdenes de producción antes de marcarlo como entregado."
                ),
            )

    # Al entregar: validar pago completo del pedido (el pago nunca se divide).
    if nuevo_estado == "entregado":
        if cobro_efectivo_pendiente(venta):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Registrá el cobro en efectivo antes de marcar el grupo como entregado: "
                    "este pedido se paga (total o en parte) en mano."
                ),
            )
        if getattr(venta, "Requiere_Anticipo", 0) and not getattr(venta, "Pago_Final_Registrado", 0):
            raise HTTPException(
                status_code=400,
                detail="Debe registrar el pago final antes de marcar el grupo como entregado",
            )
        _metodo_v = (venta.Metodo_Pago or "").strip().lower()
        _soporte_v = venta.Comprobante_Pago or getattr(venta, "Anticipo_Comprobante_Url", None)
        _hay_transf_v = (
            "transfer" in _metodo_v
            or ("mixto" in _metodo_v and float(venta.Monto_Transferencia or 0) > 0)
        )
        if _hay_transf_v and not _soporte_v:
            raise HTTPException(
                status_code=400,
                detail="Se requiere comprobante de pago para marcar el grupo como entregado",
            )

    grupo.Estado = nuevo_estado

    # Sincronizar estado de cabecera desde los grupos
    grupos = db.query(GrupoEnvio).filter(GrupoEnvio.ID_Venta == id_venta).all()
    nuevo = _recalcular_estado_pedido(venta, grupos)
    if nuevo is not None:
        venta.Estado = nuevo
        if nuevo == EstadoPedido.ENTREGADO and not getattr(venta, "Fecha_entrega", None):
            venta.Fecha_entrega = _now()

    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


def actualizar_tipo_entrega_grupo(
    db: Session,
    id_venta: int,
    id_grupo: int,
    tipo_entrega: str,
    actual: dict,
    id_barrio: int | None = None,
    direccion: str | None = None,
) -> dict:
    """Cliente o admin cambia el tipo de entrega de un grupo (domicilio/tienda).

    Un domicilio por viaje: pasar un grupo A 'domicilio' le crea su propio
    `Domicilio` (snapshot de su barrio + ofertas de su fecha) y suma ese costo a
    `Venta.Total`; pasarlo a 'tienda' cancela ese `Domicilio` y lo resta.
    """
    if tipo_entrega not in ("domicilio", "tienda"):
        raise HTTPException(status_code=400, detail="El tipo de entrega debe ser 'domicilio' o 'tienda'")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if actual["tipo"] == "cliente" and venta.ID_Usuario != actual["registro"].ID_Usuario:
        raise HTTPException(status_code=403, detail="No puedes modificar pedidos de otros clientes")

    grupo = db.query(GrupoEnvio).filter(
        GrupoEnvio.ID_Grupo == id_grupo,
        GrupoEnvio.ID_Venta == id_venta,
    ).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo de envío no encontrado")
    if grupo.Estado in ("enviado", "entregado"):
        raise HTTPException(status_code=400, detail="No se puede cambiar el tipo de entrega de un grupo ya enviado o entregado")

    if tipo_entrega == grupo.Tipo_Entrega:
        return _formato_venta(venta, db)   # sin cambios

    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == venta.ID_Usuario).first()
    dom_orig = db.query(Domicilio).filter(
        Domicilio.ID_Venta == id_venta, Domicilio.ID_Grupo.is_(None),
    ).first()
    dom_grupo = db.query(Domicilio).filter(
        Domicilio.ID_Venta == id_venta, Domicilio.ID_Grupo == id_grupo,
    ).first()

    if tipo_entrega == "domicilio":
        kw, final = _domicilio_grupo_kwargs(
            db, id_barrio, dom_orig, grupo.Fecha_Entrega, direccion, venta, cliente
        )
        if dom_grupo:
            for campo, valor in kw.items():
                setattr(dom_grupo, campo, valor)
            dom_grupo.Estado = 3
        else:
            db.add(Domicilio(ID_Grupo=id_grupo, **kw))
        venta.Total = (venta.Total or Decimal("0")) + Decimal(final)
    else:  # → tienda
        if dom_grupo and dom_grupo.Estado != 5:
            venta.Total = (venta.Total or Decimal("0")) - Decimal(int(dom_grupo.Precio_Domicilio_Final or 0))
            dom_grupo.Estado = 5   # Cancelado

    grupo.Tipo_Entrega = tipo_entrega
    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)


def cancelar_grupo_pendiente(
    db: Session,
    id_venta: int,
    id_grupo: int,
    actual: dict,
) -> dict:
    """Admin cancela cualquiera de los grupos de envío de un pedido dividido.

    Devuelve al cliente el anticipo proporcional al valor del grupo cancelado:
      reembolso = anticipo_pagado × (valor_grupo / valor_total_del_pedido)

    Si tras la cancelación todos los grupos quedan en estado terminal
    (cancelado o entregado), la venta pasa a CANCELADO. Si al menos uno fue
    entregado, queda PARCIALMENTE_ENTREGADO.
    """
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    grupo = db.query(GrupoEnvio).filter(
        GrupoEnvio.ID_Grupo == id_grupo,
        GrupoEnvio.ID_Venta == id_venta,
    ).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo de envío no encontrado")
    if grupo.Estado == "entregado":
        raise HTTPException(status_code=400, detail="No se puede cancelar un grupo ya entregado")
    if grupo.Estado == "cancelado":
        raise HTTPException(status_code=400, detail="El grupo ya está cancelado")

    # Cancelar OPs de los productos en este grupo que aún no completaron
    prod_ids_b = {i.ID_Producto for i in grupo.items}
    from src.features.produccion.ordenes_produccion.services.service import (
        cambiar_estado as _cambiar_estado_orden,
    )
    for orden in db.query(OrdenProduccion).filter(
        OrdenProduccion.ID_Venta == id_venta,
        OrdenProduccion.ID_Producto.in_(prod_ids_b),
        OrdenProduccion.Estado.notin_([11, 5]),
    ).all():
        _cambiar_estado_orden(db, orden.ID_Orden_Produccion, 5, commit=False)

    # Calcular reembolso proporcional del anticipo.
    # Proporción = valor_bruto_grupo / valor_bruto_total (misma base para ambos,
    # sin descuentos ni domicilio, para que la suma de todos los reembolsos = anticipo).
    # IMPORTANTE: usa GrupoEnvioItem.Cantidad (cant. real del grupo), NO VentaXProducto.Cantidad
    # (que es el total del pedido y causaba reembolso del 100% en cada grupo).
    anticipo = Decimal(str(getattr(venta, "Anticipo_Monto", None) or 0))
    if anticipo > 0 and getattr(venta, "Anticipo_Registrado", 0):
        prod_map_grupo = {p.ID_Producto: p for p in db.query(Producto).filter(
            Producto.ID_Producto.in_(prod_ids_b)
        ).all()}
        valor_grupo = sum(
            (prod_map_grupo[item.ID_Producto].Precio_venta or Decimal("0"))
            * Decimal(str(item.Cantidad or 0))
            for item in grupo.items if item.ID_Producto in prod_map_grupo
        )
        todos_items = db.query(VentaXProducto).filter(
            VentaXProducto.ID_Venta == id_venta
        ).all()
        todos_prod_ids = {i.ID_Producto for i in todos_items}
        todos_prod_map = {p.ID_Producto: p for p in db.query(Producto).filter(
            Producto.ID_Producto.in_(todos_prod_ids)
        ).all()}
        total_bruto = sum(
            (todos_prod_map[i.ID_Producto].Precio_venta or Decimal("0"))
            * Decimal(str(i.Cantidad or 0))
            for i in todos_items if i.ID_Producto in todos_prod_map
        )
        if total_bruto > 0 and valor_grupo > 0:
            reembolso = (anticipo * (valor_grupo / total_bruto)).quantize(
                Decimal("1"), rounding=ROUND_CEILING
            )
            # Guardrail: nunca devolver más del anticipo total (por redondeo extremo)
            reembolso = min(reembolso, anticipo)
            # La misma regla que al cancelar el pedido entero, pero preguntada
            # por lo de ESTE grupo: lo que se hornee del otro no tiene por qué
            # congelarle al cliente la parte de este.
            if reembolso > 0 and anticipo_vuelve_solo(db, id_venta, prod_ids_b):
                _abonar_credito(db, venta.ID_Usuario, reembolso, id_venta)

    # Cancelar el domicilio asociado al grupo si existe y no está ya en estado
    # final, y quitar su costo del total (un domicilio por viaje: si el viaje no
    # ocurre, no se cobra).
    dom_grupo = db.query(Domicilio).filter(
        Domicilio.ID_Venta == id_venta,
        Domicilio.ID_Grupo == id_grupo,
        Domicilio.Estado.notin_([8, 5]),
    ).first()
    if dom_grupo:
        venta.Total = (venta.Total or Decimal("0")) - Decimal(int(dom_grupo.Precio_Domicilio_Final or 0))
        dom_grupo.Estado = 5  # Cancelado

    grupo.Estado = "cancelado"

    # Sincronizar estado de cabecera desde los grupos
    todos_grupos = db.query(GrupoEnvio).filter(GrupoEnvio.ID_Venta == id_venta).all()
    nuevo = _recalcular_estado_pedido(venta, todos_grupos)
    if nuevo is not None:
        venta.Estado = nuevo

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


def editar_grupo(
    db: Session,
    id_venta: int,
    id_grupo: int,
    nueva_fecha,
    nuevo_tipo_entrega: str | None,
    nueva_dir: str | None,
    nuevo_id_barrio: int | None,
    actual: dict,
) -> dict:
    """Admin edita fecha, tipo de entrega y/o barrio de un grupo pendiente.

    Bloqueado si el domicilio asociado ya tiene repartidor asignado (ID_Empleado
    no nulo), porque cambiar la dirección en ese punto afectaría una entrega
    ya en camino.

    Un domicilio por viaje: pasar el grupo a 'domicilio' le crea su propio
    `Domicilio` (snapshot del barrio + ofertas de su fecha) y suma ese costo a
    `Venta.Total`; pasarlo a 'tienda' cancela ese `Domicilio` y lo resta; cambiar
    el barrio de un grupo que ya va a domicilio vuelve a congelar el snapshot y
    ajusta `Venta.Total` por la diferencia.
    """
    if actual["tipo"] not in ("admin", "empleado"):
        raise HTTPException(status_code=403, detail="Solo disponible para administradores")

    venta = db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    grupo = db.query(GrupoEnvio).filter(
        GrupoEnvio.ID_Grupo == id_grupo,
        GrupoEnvio.ID_Venta == id_venta,
    ).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo de envío no encontrado")
    if grupo.Estado != "pendiente":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se puede editar un grupo en estado 'pendiente' (estado actual: '{grupo.Estado}')",
        )

    # Verificar que el domicilio asociado no tenga repartidor asignado.
    dom_grupo = db.query(Domicilio).filter(
        Domicilio.ID_Venta == id_venta,
        Domicilio.ID_Grupo == id_grupo,
        Domicilio.Estado.notin_([8, 5]),
    ).first()
    if dom_grupo and dom_grupo.ID_Empleado:
        raise HTTPException(
            status_code=400,
            detail="No se puede editar el grupo: el domicilio ya tiene un repartidor asignado",
        )

    tipo_anterior = grupo.Tipo_Entrega

    if nueva_fecha is not None:
        grupo.Fecha_Entrega = nueva_fecha
        if dom_grupo:
            dom_grupo.Fecha_entrega = nueva_fecha

    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == venta.ID_Usuario).first()
    dom_orig = db.query(Domicilio).filter(
        Domicilio.ID_Venta == id_venta, Domicilio.ID_Grupo.is_(None),
    ).first()
    fecha_grupo = nueva_fecha or grupo.Fecha_Entrega
    tipo_final = nuevo_tipo_entrega or tipo_anterior

    if nuevo_tipo_entrega is not None and nuevo_tipo_entrega != tipo_anterior:
        grupo.Tipo_Entrega = nuevo_tipo_entrega
        if nuevo_tipo_entrega == "domicilio":
            kw, final = _domicilio_grupo_kwargs(
                db, nuevo_id_barrio, dom_orig, fecha_grupo, nueva_dir, venta, cliente
            )
            if dom_grupo:
                for campo, valor in kw.items():
                    setattr(dom_grupo, campo, valor)
                dom_grupo.Estado = 3
            else:
                db.add(Domicilio(ID_Grupo=id_grupo, **kw))
            venta.Total = (venta.Total or Decimal("0")) + Decimal(final)
        elif nuevo_tipo_entrega == "tienda" and dom_grupo:
            venta.Total = (venta.Total or Decimal("0")) - Decimal(int(dom_grupo.Precio_Domicilio_Final or 0))
            dom_grupo.Estado = 5  # Cancelado

    elif tipo_final == "domicilio" and dom_grupo and (nuevo_id_barrio or nueva_dir):
        # Sigue a domicilio pero cambió el barrio o la vía → re-congelar snapshot.
        # Sin barrio nuevo se mantiene el del propio grupo (no el del pedido).
        final_anterior = int(dom_grupo.Precio_Domicilio_Final or 0)
        kw, final = _domicilio_grupo_kwargs(
            db, nuevo_id_barrio or dom_grupo.ID_Barrio, dom_orig,
            fecha_grupo, nueva_dir, venta, cliente
        )
        for campo, valor in kw.items():
            setattr(dom_grupo, campo, valor)
        dom_grupo.Estado = 3
        venta.Total = (venta.Total or Decimal("0")) - Decimal(final_anterior) + Decimal(final)

    db.commit()
    db.refresh(venta)
    return _formato_venta(venta, db)
