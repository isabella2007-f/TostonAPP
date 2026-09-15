from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from src.shared.services.database import get_db
from src.features.auth.services.dependencies import (
    requiere_permiso, permiso_o_cliente, obtener_usuario_actual,
)
from .schemas import (
    PedidoResponse, PedidoListResponse, PedidoUpdate, RegistroCobro, PedidoClienteEdit, PedidoPago,
    CambioADomicilio,
)
from .service import (
    obtener_pedidos, obtener_pedido, confirmar_pedido, cancelar_pedido,
    editar_pedido, editar_mi_pedido, aprobar_comprobante, rechazar_comprobante, registrar_cobro_pedido,
    pagar_pedido, pagar_saldo_pedido, aprobar_comprobante_saldo, rechazar_comprobante_saldo,
    marcar_retenido_en_tienda, reintentar_pago_retenido, cambiar_a_domicilio_retenido,
    cancelar_retenido_en_tienda, avisar_puede_recoger, avisar_enviar_a_entregar,
)
from src.features.ventas.gestion_ventas.services.schemas import (
    RechazoComprobante, VentaCreate, VentaResponse,
)
from src.features.ventas.gestion_ventas.services.service import crear_venta

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])


@router.post("/", response_model=VentaResponse, status_code=201)
def crear(
    datos:  VentaCreate,
    db:     Session = Depends(get_db),
    actual: dict    = Depends(permiso_o_cliente("crear_pedidos")),
):
    """
    Crea un pedido (una venta es un pedido; no son módulos separados).
    El cliente solo puede crear pedidos a su propio nombre; el mostrador
    (empleado/admin) puede hacerlo a nombre de un tercero.
    """
    if actual.get("tipo") == "cliente":
        datos.ID_Usuario = actual["registro"].ID_Usuario
        # El domicilio no trae su propia fecha de entrega: si el pedido
        # necesita producción, hereda la fecha límite que el cliente puso
        # (Fecha_entrega_esperada); `crear_venta` la valida.
        if datos.domicilio is not None:
            datos.domicilio.Fecha_entrega = None
    return crear_venta(db, datos)


@router.get("/", response_model=PedidoListResponse)
def listar_pedidos(
    pagina:     int           = Query(1, ge=1),
    por_pagina: int           = Query(10, ge=1, le=100),
    busqueda:   Optional[str] = Query(None),
    estado:     Optional[int] = Query(None),
    db:         Session       = Depends(get_db),
    _:          dict          = Depends(requiere_permiso("ver_pedidos"))
):
    """Lista pedidos. Sin 'estado' devuelve activos; con 'estado=8' devuelve entregados, etc."""
    return obtener_pedidos(db, pagina, por_pagina, busqueda, estado)


@router.get("/{id_venta}", response_model=PedidoResponse)
def ver_pedido(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("ver_pedidos"))
):
    """Retorna el detalle de un pedido pendiente."""
    return obtener_pedido(db, id_venta)


@router.put("/{id_venta}", response_model=PedidoResponse)
def editar(
    id_venta: int,
    datos:    PedidoUpdate,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Actualiza campos editables de un pedido Pendiente (metodo_pago, montos, domicilio)."""
    return editar_pedido(db, id_venta, datos.model_dump())


@router.patch("/{id_venta}/confirmar", response_model=PedidoResponse)
def confirmar(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("cambiar_estado_pedidos"))
):
    """Confirma el pedido → estado Confirmado."""
    return confirmar_pedido(db, id_venta)


@router.patch("/{id_venta}/cancelar", response_model=PedidoResponse)
def cancelar(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("cancelar_pedidos"))
):
    """Cancela cualquier pedido pendiente (empleado / admin)."""
    return cancelar_pedido(db, id_venta)


@router.patch("/{id_venta}/cancelar-mi-pedido", response_model=PedidoResponse)
def cancelar_mi_pedido(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente cancela su propio pedido (permitido hasta que entre a producción)."""
    if actual.get("tipo") != "cliente":
        raise HTTPException(status_code=403, detail="Este endpoint es solo para clientes. Usa /cancelar.")
    return cancelar_pedido(db, id_venta, actual)


@router.patch("/{id_venta}/editar-mi-pedido", response_model=PedidoResponse)
def editar_mi_pedido_endpoint(
    id_venta: int,
    datos:    PedidoClienteEdit,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente cambia el método de pago y/o el tipo de entrega de su pedido."""
    return editar_mi_pedido(db, id_venta, datos.model_dump(exclude_none=True), actual)


@router.patch("/{id_venta}/pagar", response_model=PedidoResponse)
def pagar_pedido_endpoint(
    id_venta: int,
    datos:    PedidoPago,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente adjunta el comprobante de pago (o anticipo) de un pedido
    'Esperando Pago'. El admin lo aprueba/rechaza igual que cualquier otro
    comprobante."""
    return pagar_pedido(db, id_venta, datos.model_dump(), actual)


@router.patch("/{id_venta}/aprobar-comprobante", response_model=PedidoResponse)
def aprobar_comprobante_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Admin aprueba el comprobante de transferencia → Estado_Pago='pagado_completo'."""
    return aprobar_comprobante(db, id_venta)


@router.patch("/{id_venta}/rechazar-comprobante", response_model=PedidoResponse)
def rechazar_comprobante_endpoint(
    id_venta: int,
    datos:    RechazoComprobante,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Admin rechaza el comprobante → Estado_Pago='comprobante_rechazado'. El motivo queda en notificación."""
    registro = actual["registro"]
    return rechazar_comprobante(db, id_venta, datos.motivo, registro.ID_Usuario)


@router.patch("/{id_venta}/registrar-cobro", response_model=PedidoResponse)
def registrar_cobro_endpoint(
    id_venta: int,
    datos:    RegistroCobro,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Admin/empleado registra cobro en efectivo (contra entrega o en tienda) → Estado_Pago='efectivo_recibido'."""
    registro = actual["registro"]
    return registrar_cobro_pedido(db, id_venta, datos, registro.ID_Usuario)


@router.patch("/{id_venta}/pagar-saldo", response_model=PedidoResponse)
def pagar_saldo_endpoint(
    id_venta: int,
    datos:    PedidoPago,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente adjunta el comprobante del SALDO restante (segundo
    comprobante, 3.10), cuando ese resto se paga por transferencia."""
    return pagar_saldo_pedido(db, id_venta, datos.model_dump(), actual)


@router.patch("/{id_venta}/aprobar-comprobante-saldo", response_model=PedidoResponse)
def aprobar_comprobante_saldo_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Admin aprueba el comprobante del saldo restante → registra el pago final."""
    return aprobar_comprobante_saldo(db, id_venta)


@router.patch("/{id_venta}/rechazar-comprobante-saldo", response_model=PedidoResponse)
def rechazar_comprobante_saldo_endpoint(
    id_venta: int,
    datos:    RechazoComprobante,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Admin rechaza el comprobante del saldo restante. Al 3er rechazo el pedido se cancela solo."""
    registro = actual["registro"]
    return rechazar_comprobante_saldo(db, id_venta, datos.motivo, registro.ID_Usuario)


# ── 3.7: excepción de cobro en efectivo (recoger en tienda) ──

@router.patch("/{id_venta}/retener-en-tienda", response_model=PedidoResponse)
def marcar_retenido_en_tienda_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """El cajero no pudo cobrar en efectivo: el pedido pasa a 'Retenido en tienda'."""
    return marcar_retenido_en_tienda(db, id_venta)


@router.patch("/{id_venta}/reintentar-pago-retenido", response_model=PedidoResponse)
def reintentar_pago_retenido_endpoint(
    id_venta: int,
    datos:    RegistroCobro,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """El cliente volvió dentro de las 24h: el cajero registra el cobro y el pedido se entrega."""
    registro = actual["registro"]
    return reintentar_pago_retenido(db, id_venta, datos, registro.ID_Usuario)


@router.patch("/{id_venta}/cambiar-a-domicilio", response_model=PedidoResponse)
def cambiar_a_domicilio_endpoint(
    id_venta: int,
    datos:    CambioADomicilio,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Desde 'Retenido en tienda', cambia la entrega a domicilio."""
    registro = actual["registro"]
    return cambiar_a_domicilio_retenido(db, id_venta, datos, registro.ID_Usuario)


@router.patch("/{id_venta}/cancelar-retenido", response_model=PedidoResponse)
def cancelar_retenido_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Cancelación definitiva de un pedido 'Retenido en tienda' por falta de pago."""
    return cancelar_retenido_en_tienda(db, id_venta)


# ── 3.11: avisos de despacho ──

@router.patch("/{id_venta}/avisar-puede-recoger", response_model=PedidoResponse)
def avisar_puede_recoger_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Avisa al cliente que puede pasar a recoger su pedido en tienda."""
    return avisar_puede_recoger(db, id_venta)


@router.patch("/{id_venta}/avisar-enviar-a-entregar", response_model=PedidoResponse)
def avisar_enviar_a_entregar_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("cambiar_estado_pedidos")),
):
    """Avisa al domiciliario asignado que salga a entregar."""
    return avisar_enviar_a_entregar(db, id_venta)