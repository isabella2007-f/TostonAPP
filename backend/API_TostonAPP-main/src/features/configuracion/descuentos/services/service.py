from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from decimal import Decimal

from src.shared.services.models import (
    Descuento, DescuentoXUsuario, MovimientoCredito,
    CreditoCliente, Usuario, Estado
)
from src.shared.services.enums import TipoDescuento
from .schemas import DescuentoCreate, DescuentoUpdate, FiltroCreditos


def _label_estado(db: Session, id_estado: int) -> str:
    estado = db.query(Estado).filter(Estado.ID_Estados == id_estado).first()
    return estado.Estado if estado else None


def _formato_descuento(desc: Descuento, db: Session) -> dict:
    total_asignados = db.query(DescuentoXUsuario).filter(
        DescuentoXUsuario.ID_Descuento == desc.ID_Descuento
    ).count()

    return {
        "ID_Descuento":   desc.ID_Descuento,
        "Nombre":         desc.Nombre,
        "Tipo":           desc.Tipo,
        "Codigo":         desc.Codigo,
        "Porcentaje":     desc.Porcentaje,
        "Meses_Minimos":  desc.Meses_Minimos,
        "Fecha_Inicio":   desc.Fecha_Inicio,
        "Fecha_Fin":      desc.Fecha_Fin,
        "Usos_Max":       desc.Usos_Max,
        "Usos_Actuales":  desc.Usos_Actuales,
        "Estado":         desc.Estado,
        "estado_label":   _label_estado(db, desc.Estado) if desc.Estado else None,
        "total_asignados": total_asignados,
    }


# ─────────────────────────────────────────
# CRUD DESCUENTOS
# ─────────────────────────────────────────

def obtener_descuentos(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None,
    tipo: str = None
) -> dict:
    query = db.query(Descuento)

    if busqueda:
        termino = f"%{busqueda}%"
        query = query.filter(
            Descuento.Nombre.ilike(termino) |
            Descuento.Codigo.ilike(termino)
        )
    if tipo:
        query = query.filter(Descuento.Tipo == tipo)

    total     = query.count()
    offset    = (pagina - 1) * por_pagina
    descuentos = query.offset(offset).limit(por_pagina).all()

    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "descuentos": [_formato_descuento(d, db) for d in descuentos],
    }


def obtener_descuento(db: Session, id_descuento: int) -> dict:
    desc = db.query(Descuento).filter(Descuento.ID_Descuento == id_descuento).first()
    if not desc:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")
    return _formato_descuento(desc, db)


def crear_descuento(db: Session, datos: DescuentoCreate) -> dict:
    # Valida código único si es cupón
    if datos.Tipo == TipoDescuento.CUPON and datos.Codigo:
        if db.query(Descuento).filter(Descuento.Codigo == datos.Codigo).first():
            raise HTTPException(status_code=400, detail="Ya existe un cupón con ese código")

    # Valida campos requeridos por tipo
    if datos.Tipo == TipoDescuento.CUPON and not datos.Codigo:
        raise HTTPException(status_code=400, detail="Los cupones requieren un código")
    if datos.Tipo == TipoDescuento.ANTIGUEDAD and not datos.Meses_Minimos:
        raise HTTPException(status_code=400, detail="Los descuentos por antigüedad requieren Meses_Minimos")

    nuevo = Descuento(
        Nombre        = datos.Nombre,
        Tipo          = datos.Tipo,
        Codigo        = datos.Codigo,
        Porcentaje    = datos.Porcentaje,
        Meses_Minimos = datos.Meses_Minimos,
        Fecha_Inicio  = datos.Fecha_Inicio,
        Fecha_Fin     = datos.Fecha_Fin,
        Usos_Max      = datos.Usos_Max,
        Usos_Actuales = 0,
        Estado        = 1,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return _formato_descuento(nuevo, db)


def editar_descuento(db: Session, id_descuento: int, datos: DescuentoUpdate) -> dict:
    desc = db.query(Descuento).filter(Descuento.ID_Descuento == id_descuento).first()
    if not desc:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")

    for campo, valor in datos.model_dump(exclude_none=True).items():
        setattr(desc, campo, valor)

    db.commit()
    db.refresh(desc)
    return _formato_descuento(desc, db)


def cambiar_estado(db: Session, id_descuento: int, nuevo_estado: int) -> dict:
    desc = db.query(Descuento).filter(Descuento.ID_Descuento == id_descuento).first()
    if not desc:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")

    desc.Estado = nuevo_estado
    db.commit()
    db.refresh(desc)
    return _formato_descuento(desc, db)


def eliminar_descuento(db: Session, id_descuento: int) -> dict:
    desc = db.query(Descuento).filter(Descuento.ID_Descuento == id_descuento).first()
    if not desc:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")

    # Elimina asignaciones antes de eliminar el descuento
    db.query(DescuentoXUsuario).filter(
        DescuentoXUsuario.ID_Descuento == id_descuento
    ).delete()

    db.delete(desc)
    db.commit()
    return {"mensaje": f"Descuento {id_descuento} eliminado correctamente"}


# ─────────────────────────────────────────
# ASIGNACIONES (solo tipo emision)
# ─────────────────────────────────────────

def asignar_a_usuarios(db: Session, id_descuento: int, usuarios_ids: list[int]) -> dict:
    """Asigna masivamente un descuento de emisión a una lista de usuarios."""
    desc = db.query(Descuento).filter(Descuento.ID_Descuento == id_descuento).first()
    if not desc:
        raise HTTPException(status_code=404, detail="Descuento no encontrado")
    if desc.Tipo != TipoDescuento.EMISION:
        raise HTTPException(status_code=400, detail="Solo los descuentos de emisión se asignan manualmente")

    asignados   = 0
    ya_tenian   = 0

    for id_usuario in usuarios_ids:
        # Verifica que el usuario existe
        if not db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first():
            continue

        # Evita duplicados
        existe = db.query(DescuentoXUsuario).filter(
            DescuentoXUsuario.ID_Descuento == id_descuento,
            DescuentoXUsuario.ID_Usuario   == id_usuario
        ).first()

        if existe:
            ya_tenian += 1
            continue

        db.add(DescuentoXUsuario(
            ID_Descuento     = id_descuento,
            ID_Usuario       = id_usuario,
            Usado            = False,
            Fecha_Asignacion = datetime.now(),
        ))
        asignados += 1

    db.commit()
    return {
        "mensaje":   f"{asignados} usuarios asignados correctamente",
        "asignados": asignados,
        "ya_tenian": ya_tenian,
    }


def ver_asignaciones(db: Session, id_descuento: int, pagina: int = 1, por_pagina: int = 10) -> dict:
    """Lista los usuarios que tienen asignado un descuento de emisión."""
    query = db.query(DescuentoXUsuario).filter(
        DescuentoXUsuario.ID_Descuento == id_descuento
    )
    total  = query.count()
    offset = (pagina - 1) * por_pagina
    asigs  = query.offset(offset).limit(por_pagina).all()

    resultado = []
    for a in asigs:
        usuario = db.query(Usuario).filter(Usuario.ID_Usuario == a.ID_Usuario).first()
        resultado.append({
            "ID_Descuento":     a.ID_Descuento,
            "ID_Usuario":       a.ID_Usuario,
            "nombre_usuario":   f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
            "Usado":            a.Usado,
            "Fecha_Asignacion": a.Fecha_Asignacion,
        })

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "asignaciones": resultado}


# ─────────────────────────────────────────
# HISTORIAL DE CREDITOS (con filtros)
# ─────────────────────────────────────────

def obtener_historial_creditos(
    db: Session,
    filtros: FiltroCreditos,
    pagina: int = 1,
    por_pagina: int = 10
) -> dict:
    """
    Retorna el historial de movimientos de crédito con filtros.
    Requiere al menos un filtro para evitar traer miles de registros.
    """
    # Verifica que venga al menos un filtro
    filtros_activos = {k: v for k, v in filtros.model_dump().items() if v is not None}
    if not filtros_activos:
        raise HTTPException(
            status_code=400,
            detail="Debes aplicar al menos un filtro para consultar el historial"
        )

    query = db.query(MovimientoCredito)

    if filtros.Tipo:
        query = query.filter(MovimientoCredito.Tipo == filtros.Tipo)
    if filtros.Monto_Min:
        query = query.filter(MovimientoCredito.Monto >= filtros.Monto_Min)
    if filtros.Monto_Max:
        query = query.filter(MovimientoCredito.Monto <= filtros.Monto_Max)
    if filtros.Fecha_Inicio:
        query = query.filter(MovimientoCredito.Fecha >= filtros.Fecha_Inicio)
    if filtros.Fecha_Fin:
        query = query.filter(MovimientoCredito.Fecha <= filtros.Fecha_Fin)

    # Filtro por usuario: busca a través del crédito
    if filtros.ID_Usuario:
        credito = db.query(CreditoCliente).filter(
            CreditoCliente.ID_Usuario == filtros.ID_Usuario
        ).first()
        if credito:
            query = query.filter(MovimientoCredito.ID_Credito == credito.ID_Credito)
        else:
            return {"total": 0, "pagina": pagina, "por_pagina": por_pagina, "movimientos": []}

    total  = query.count()
    offset = (pagina - 1) * por_pagina
    movs   = query.order_by(MovimientoCredito.Fecha.desc()).offset(offset).limit(por_pagina).all()

    resultado = []
    for m in movs:
        # Obtiene el usuario desde el crédito
        credito = db.query(CreditoCliente).filter(
            CreditoCliente.ID_Credito == m.ID_Credito
        ).first()
        usuario = db.query(Usuario).filter(
            Usuario.ID_Usuario == credito.ID_Usuario
        ).first() if credito else None

        # Construye la etiqueta del origen
        origen = None
        if m.ID_Devolucion:
            origen = f"Devolución #{m.ID_Devolucion}"
        elif m.ID_Venta:
            origen = f"Venta #{m.ID_Venta}"

        resultado.append({
            "ID_Movimiento":  m.ID_Movimiento,
            "ID_Usuario":     credito.ID_Usuario if credito else None,
            "nombre_cliente": f"{usuario.Nombre} {usuario.Apellidos}" if usuario else None,
            "Tipo":           m.Tipo,
            "Monto":          m.Monto,
            "Fecha":          m.Fecha,
            "origen":         origen,
        })

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "movimientos": resultado}