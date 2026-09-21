"""CRUD de las ofertas de domicilio (2ª pestaña del módulo Ubicaciones).

Funcionalidad INDEPENDIENTE del módulo congelado `configuracion/descuentos`.
Solo afecta el precio del domicilio, nunca el subtotal de productos ni otros
descuentos. El motor de acumulación vive en `service.precio_domicilio_final`.
"""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from src.shared.services.models import (
    Barrio, Ciudad, OfertaDomicilio, OfertaXBarrio,
)
from .service import _now, _parse_csv_int, _to_csv, precio_domicilio_final
from src.shared.services.enums import TipoOfertaDomicilio

ACTIVO, INACTIVO = 1, 2


def _formato_oferta(db: Session, of: OfertaDomicilio) -> dict:
    barrios = (
        db.query(Barrio, Ciudad.Nombre.label("ciudad"))
        .join(OfertaXBarrio, OfertaXBarrio.ID_Barrio == Barrio.ID_Barrio)
        .join(Ciudad, Ciudad.ID_Ciudad == Barrio.ID_Ciudad)
        .filter(OfertaXBarrio.ID_Oferta == of.ID_Oferta)
        .order_by(Ciudad.Nombre.asc(), Barrio.Nombre.asc())
        .all()
    )
    return {
        "ID_Oferta": of.ID_Oferta,
        "Nombre": of.Nombre,
        "Tipo": of.Tipo,
        "Monto_Pesos": of.Monto_Pesos,
        "Porcentaje": of.Porcentaje,
        "Dias_Semana": _parse_csv_int(of.Dias_Semana),
        "Dias_Mes": _parse_csv_int(of.Dias_Mes),
        "Estado": of.Estado,
        "Fecha_Creacion": of.Fecha_Creacion,
        "barrios": [
            {"ID_Barrio": b.ID_Barrio, "Nombre": b.Nombre, "ciudad": ciudad}
            for b, ciudad in barrios
        ],
    }


def _validar_barrios(db: Session, ids: list[int]) -> None:
    existentes = {
        r[0] for r in db.query(Barrio.ID_Barrio).filter(Barrio.ID_Barrio.in_(ids)).all()
    }
    faltan = [i for i in ids if i not in existentes]
    if faltan:
        raise HTTPException(status_code=400, detail=f"Barrio(s) inexistente(s): {faltan}")


def listar_ofertas(
    db: Session, *, pagina: int = 1, por_pagina: int = 20,
    texto: str | None = None, estado: int | None = None, tipo: str | None = None,
) -> dict:
    q = db.query(OfertaDomicilio)
    if estado is not None:
        q = q.filter(OfertaDomicilio.Estado == estado)
    if tipo in TipoOfertaDomicilio.TODOS:
        q = q.filter(OfertaDomicilio.Tipo == tipo)
    if texto:
        termino = "%" + texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        q = q.filter(OfertaDomicilio.Nombre.ilike(termino, escape="\\"))

    total = q.count()
    filas = (
        q.order_by(OfertaDomicilio.ID_Oferta.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    return {
        "total": total, "pagina": pagina, "por_pagina": por_pagina,
        "ofertas": [_formato_oferta(db, of) for of in filas],
    }


def obtener_oferta(db: Session, id_oferta: int) -> dict:
    of = db.query(OfertaDomicilio).filter(OfertaDomicilio.ID_Oferta == id_oferta).first()
    if not of:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")
    data = _formato_oferta(db, of)
    # Ejemplo de cálculo sobre el primer barrio afectado, para "ver detalle".
    if data["barrios"]:
        primer = data["barrios"][0]["ID_Barrio"]
        try:
            data["ejemplo_calculo"] = precio_domicilio_final(db, primer, _now())
        except HTTPException:
            data["ejemplo_calculo"] = None
    return data


def crear_oferta(db: Session, datos) -> dict:
    _validar_barrios(db, datos.barrios)
    of = OfertaDomicilio(
        Nombre=datos.Nombre.strip(),
        Tipo=datos.Tipo,
        Monto_Pesos=datos.Monto_Pesos,
        Porcentaje=datos.Porcentaje,
        Dias_Semana=_to_csv(datos.Dias_Semana),
        Dias_Mes=_to_csv(datos.Dias_Mes),
        Estado=ACTIVO,
        Fecha_Creacion=_now(),
    )
    db.add(of)
    db.flush()
    for id_barrio in datos.barrios:
        db.add(OfertaXBarrio(ID_Oferta=of.ID_Oferta, ID_Barrio=id_barrio))
    db.commit()
    db.refresh(of)
    return _formato_oferta(db, of)


def editar_oferta(db: Session, id_oferta: int, datos) -> dict:
    of = db.query(OfertaDomicilio).filter(OfertaDomicilio.ID_Oferta == id_oferta).first()
    if not of:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")

    hubo_cambio = False

    if datos.Nombre is not None and datos.Nombre.strip() != of.Nombre:
        of.Nombre = datos.Nombre.strip()
        hubo_cambio = True
    if datos.Tipo is not None and datos.Tipo != of.Tipo:
        of.Tipo = datos.Tipo
        hubo_cambio = True

    if datos.limpiar_pesos:
        if of.Monto_Pesos is not None:
            of.Monto_Pesos = None
            hubo_cambio = True
    elif datos.Monto_Pesos is not None and datos.Monto_Pesos != of.Monto_Pesos:
        of.Monto_Pesos = datos.Monto_Pesos
        hubo_cambio = True

    if datos.limpiar_porcentaje:
        if of.Porcentaje is not None:
            of.Porcentaje = None
            hubo_cambio = True
    elif datos.Porcentaje is not None and datos.Porcentaje != of.Porcentaje:
        of.Porcentaje = datos.Porcentaje
        hubo_cambio = True

    if datos.Dias_Semana is not None:
        nuevo = _to_csv(datos.Dias_Semana)
        if nuevo != of.Dias_Semana:
            of.Dias_Semana = nuevo
            hubo_cambio = True
    if datos.Dias_Mes is not None:
        nuevo = _to_csv(datos.Dias_Mes)
        if nuevo != of.Dias_Mes:
            of.Dias_Mes = nuevo
            hubo_cambio = True

    if datos.barrios is not None:
        _validar_barrios(db, datos.barrios)
        actuales = {
            r[0] for r in db.query(OfertaXBarrio.ID_Barrio)
            .filter(OfertaXBarrio.ID_Oferta == id_oferta).all()
        }
        objetivo = set(datos.barrios)
        if actuales != objetivo:
            db.query(OfertaXBarrio).filter(
                OfertaXBarrio.ID_Oferta == id_oferta,
                OfertaXBarrio.ID_Barrio.in_(actuales - objetivo),
            ).delete(synchronize_session=False)
            for id_barrio in objetivo - actuales:
                db.add(OfertaXBarrio(ID_Oferta=id_oferta, ID_Barrio=id_barrio))
            hubo_cambio = True

    # Reglas de coherencia tras aplicar los cambios.
    if of.Monto_Pesos is None and of.Porcentaje is None:
        db.rollback()
        raise HTTPException(status_code=422, detail="La oferta debe conservar descuento/recargo en pesos, en porcentaje, o ambos")
    if not of.Dias_Semana and not of.Dias_Mes:
        db.rollback()
        raise HTTPException(status_code=422, detail="La oferta debe aplicar en al menos un día de la semana o del mes")
    restantes = db.query(func.count(OfertaXBarrio.ID_Oferta)).filter(
        OfertaXBarrio.ID_Oferta == id_oferta).scalar() or 0
    if restantes == 0:
        db.rollback()
        raise HTTPException(status_code=422, detail="La oferta debe aplicar en al menos un barrio")

    if not hubo_cambio:
        db.rollback()
        raise HTTPException(status_code=422, detail="No se hicieron cambios")

    db.commit()
    db.refresh(of)
    return _formato_oferta(db, of)


def cambiar_estado_oferta(db: Session, id_oferta: int, nuevo_estado: int) -> dict:
    of = db.query(OfertaDomicilio).filter(OfertaDomicilio.ID_Oferta == id_oferta).first()
    if not of:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")
    of.Estado = nuevo_estado
    db.commit()
    return {"ID_Oferta": id_oferta, "Estado": nuevo_estado}


def eliminar_oferta(db: Session, id_oferta: int) -> dict:
    of = db.query(OfertaDomicilio).filter(OfertaDomicilio.ID_Oferta == id_oferta).first()
    if not of:
        raise HTTPException(status_code=404, detail="Oferta no encontrada")
    # Oferta_x_Barrio cae por cascade en el modelo. Los pedidos ya creados no se
    # tocan: guardan su desglose congelado, no una FK a la oferta.
    db.delete(of)
    db.commit()
    return {"mensaje": "Oferta eliminada"}
