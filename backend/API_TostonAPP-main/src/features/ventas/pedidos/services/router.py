from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from src.shared.services.database import get_db
from src.features.auth.services.dependencies import (
    requiere_permiso, permiso_o_cliente, obtener_usuario_actual,
)
from .schemas import PedidoResponse, PedidoListResponse, PedidoUpdate, RegistroCobro, PedidoClienteEdit, PedidoPago
from .service import (
    obtener_pedidos, obtener_pedido, confirmar_pedido, cancelar_pedido,
    editar_pedido, editar_mi_pedido, aprobar_comprobante, rechazar_comprobante, registrar_cobro_pedido,
    pagar_pedido,
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
    _:        dict    = Depends(requiere_permiso("editar_pedidos"))
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
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin aprueba el comprobante de transferencia → Estado_Pago='pagado_completo'."""
    return aprobar_comprobante(db, id_venta)


@router.patch("/{id_venta}/rechazar-comprobante", response_model=PedidoResponse)
def rechazar_comprobante_endpoint(
    id_venta: int,
    datos:    RechazoComprobante,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin rechaza el comprobante → Estado_Pago='comprobante_rechazado'. El motivo queda en notificación."""
    registro = actual["registro"]
    return rechazar_comprobante(db, id_venta, datos.motivo, registro.ID_Usuario)


@router.patch("/{id_venta}/registrar-cobro", response_model=PedidoResponse)
def registrar_cobro_endpoint(
    id_venta: int,
    datos:    RegistroCobro,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin/empleado registra cobro en efectivo (contra entrega o en tienda) → Estado_Pago='efectivo_recibido'."""
    registro = actual["registro"]
    return registrar_cobro_pedido(db, id_venta, datos, registro.ID_Usuario)