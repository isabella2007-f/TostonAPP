from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from src.shared.services.database import get_db
from src.features.auth.services.dependencies import (
    requiere_permiso, permiso_o_cliente, obtener_usuario_actual,
)
from .schemas import (
    VentaCreate, VentaEstado, VentaResponse, VentaListResponse,
    FechaEntregaInput, PagoFinalCreate, EnvioCompletoDomingoInput,
    RechazarFechaInput, AcuerdoManualInput, RechazarPagoFinalInput,
)
from .service import (
    obtener_ventas, obtener_venta, obtener_mi_venta, crear_venta, cambiar_estado,
    obtener_mis_ventas, obtener_mi_credito, obtener_credito_cliente,
    proponer_fecha, aceptar_fecha, rechazar_fecha, aprobar_fecha_directa, solicitar_escalado,
    registrar_pago_final, aprobar_pago_final, rechazar_pago_final,
    guardar_envio_completo_domingo,
    resolver_escalado_acuerdo_manual, resolver_escalado_cancelar,
)

router = APIRouter(prefix="/ventas", tags=["Gestión de Ventas"])


@router.get("/mi-credito")
def ver_mi_credito(
    db:     Session = Depends(get_db),
    actual: dict    = Depends(obtener_usuario_actual),
):
    """Retorna el saldo de crédito disponible del cliente autenticado."""
    return obtener_mi_credito(db, actual)


@router.get("/credito-cliente/{id_usuario}")
def ver_credito_cliente(
    id_usuario: int,
    db:         Session = Depends(get_db),
    _:          dict    = Depends(requiere_permiso("ver_pedidos")),
):
    """Retorna el saldo de crédito de un cliente específico (uso admin)."""
    return obtener_credito_cliente(db, id_usuario)


@router.get("/mis-ventas", response_model=VentaListResponse)
def mis_ventas(
    pagina:     int           = Query(1, ge=1),
    por_pagina: int           = Query(10, ge=1, le=100),
    db:         Session       = Depends(get_db),
    actual:     dict          = Depends(obtener_usuario_actual),
):
    """Retorna las ventas del cliente autenticado (todos los estados)."""
    return obtener_mis_ventas(db, actual, pagina, por_pagina)


@router.get("/", response_model=VentaListResponse)
def listar_ventas(
    pagina:      int           = Query(1, ge=1),
    por_pagina:  int           = Query(10, ge=1, le=100),
    busqueda:    Optional[str] = Query(None),
    id_usuario:  Optional[int] = Query(None),
    estado:      Optional[int] = Query(None),
    db:          Session       = Depends(get_db),
    _:           dict          = Depends(requiere_permiso("ver_pedidos"))
):
    """Lista paginada de ventas. Filtra por id_usuario, estado o busca por nombre."""
    return obtener_ventas(db, pagina, por_pagina, busqueda, id_usuario, estado)


@router.get("/mis-ventas/{id_venta}", response_model=VentaResponse)
def ver_mi_venta(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """Retorna el detalle de una venta propia del cliente autenticado."""
    return obtener_mi_venta(db, id_venta, actual)


@router.get("/{id_venta}", response_model=VentaResponse)
def ver_venta(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("ver_pedidos"))
):
    """Retorna el detalle completo de una venta con productos, crédito y descuento."""
    return obtener_venta(db, id_venta)


@router.post("/", response_model=VentaResponse, status_code=201)
def registrar_venta(
    datos:  VentaCreate,
    db:     Session = Depends(get_db),
    actual: dict    = Depends(permiso_o_cliente("crear_pedidos"))
):
    """
    Crea una venta aplicando el flujo completo:
    1. Valida stock de productos
    2. Aplica crédito del cliente si usar_credito=true
    3. Aplica descuento si queda saldo
    4. Descuenta stock automáticamente
    5. Crea domicilio si se incluye en el body
    """
    if actual.get("tipo") == "cliente":
        # El pedido queda a nombre de quien lo hace, no de quien diga el
        # cuerpo. Con el ID libre, un cliente podía mandar el de otro y el
        # pedido se creaba a nombre de esa persona Y se pagaba con SU saldo
        # a favor (`usar_credito` lo toma del ID del pedido), con la
        # dirección de entrega que eligiera el atacante. El mostrador sí
        # puede vender a nombre de un tercero: por eso solo se fuerza aquí.
        datos.ID_Usuario = actual["registro"].ID_Usuario
        # El domicilio no trae su propia fecha de entrega: si el pedido
        # necesita producción, hereda la fecha límite que el cliente puso más
        # abajo (Fecha_entrega_esperada); `crear_venta` la valida.
        if datos.domicilio is not None:
            datos.domicilio.Fecha_entrega = None
    return crear_venta(db, datos)


@router.patch("/{id_venta}/estado", response_model=VentaResponse)
def actualizar_estado(
    id_venta: int,
    datos:    VentaEstado,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("editar_pedidos"))
):
    """Cambia el estado de la venta."""
    return cambiar_estado(db, id_venta, datos.Estado)


@router.patch("/{id_venta}/proponer-fecha", response_model=VentaResponse)
def proponer_fecha_endpoint(
    id_venta: int,
    datos:    FechaEntregaInput,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin propone una fecha de entrega para un pedido. Válido en Pendiente, Fecha propuesta,
    Fecha rechazada o Escalado a admin. La fecha no puede ser en el pasado.
    """
    id_admin = getattr(actual.get("registro"), "ID_Usuario", None) if isinstance(actual, dict) else None
    return proponer_fecha(db, id_venta, datos.fecha_entrega, id_admin=id_admin)


@router.patch("/{id_venta}/aceptar-fecha", response_model=VentaResponse)
def aceptar_fecha_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente acepta la fecha que contraofreció el admin."""
    return aceptar_fecha(db, id_venta, actual)


@router.patch("/{id_venta}/aprobar-fecha", response_model=VentaResponse)
def aprobar_fecha_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin aprueba en 1 clic la fecha que el cliente pidió al hacer el pedido
    (Camino A), sin pasar por 'Fecha propuesta'."""
    return aprobar_fecha_directa(db, id_venta, actual)


@router.patch("/{id_venta}/solicitar-escalado", response_model=VentaResponse)
def solicitar_escalado_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente pide hablar directamente con el admin (canal de excepción)
    en vez de seguir rechazando la fecha contraofrecida."""
    return solicitar_escalado(db, id_venta, actual)


@router.post("/{id_venta}/registrar-pago-final", response_model=VentaResponse)
def registrar_pago_final_endpoint(
    id_venta: int,
    datos:    PagoFinalCreate,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Registra el pago del saldo restante. Queda pendiente de validación por admin."""
    return registrar_pago_final(db, id_venta, datos)


@router.patch("/{id_venta}/aprobar-pago-final", response_model=VentaResponse)
def aprobar_pago_final_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin aprueba el comprobante del saldo final."""
    return aprobar_pago_final(db, id_venta)


@router.patch("/{id_venta}/rechazar-pago-final", response_model=VentaResponse)
def rechazar_pago_final_endpoint(
    id_venta: int,
    datos:    RechazarPagoFinalInput,
    db:       Session = Depends(get_db),
    _:        dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin rechaza el comprobante del saldo final. Tres rechazos cancelan el pedido."""
    return rechazar_pago_final(db, id_venta, datos.motivo)


@router.patch("/{id_venta}/envio-completo-domingo", response_model=VentaResponse)
def envio_completo_domingo_endpoint(
    id_venta: int,
    datos:    EnvioCompletoDomingoInput,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente responde si quiere recibir todo el pedido junto el domingo."""
    return guardar_envio_completo_domingo(db, id_venta, datos.envio_completo_domingo, actual)


@router.patch("/{id_venta}/rechazar-fecha", response_model=VentaResponse)
def rechazar_fecha_endpoint(
    id_venta: int,
    datos:    RechazarFechaInput = RechazarFechaInput(),
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(obtener_usuario_actual),
):
    """El cliente rechaza la fecha contraofrecida, con causa opcional →
    pedido vuelve a 'Pendiente de Aprobación' para que el admin apruebe otra
    fecha o proponga una nueva."""
    return rechazar_fecha(db, id_venta, actual, motivo=datos.motivo)


@router.patch("/{id_venta}/resolver-escalado-acuerdo", response_model=VentaResponse)
def resolver_escalado_acuerdo_endpoint(
    id_venta: int,
    datos:    AcuerdoManualInput,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin acuerda una fecha manualmente con el cliente escalado → pasa al flujo de producción."""
    return resolver_escalado_acuerdo_manual(db, id_venta, datos.fecha_acordada, actual)


@router.patch("/{id_venta}/resolver-escalado-cancelar", response_model=VentaResponse)
def resolver_escalado_cancelar_endpoint(
    id_venta: int,
    db:       Session = Depends(get_db),
    actual:   dict    = Depends(requiere_permiso("editar_pedidos")),
):
    """Admin cancela el pedido escalado y devuelve el crédito usado."""
    return resolver_escalado_cancelar(db, id_venta, actual)