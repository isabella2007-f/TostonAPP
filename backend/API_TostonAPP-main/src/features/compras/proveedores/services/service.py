from sqlalchemy.orm import Session
from sqlalchemy import distinct, func
from fastapi import HTTPException

from src.shared.services.models import Proveedor, SujetoDerecho, Compra, DetalleCompra, Insumo, Estado
from .schemas import ProveedorCreate, ProveedorUpdate


def _formato_proveedor(proveedor: Proveedor, db: Session) -> dict:
    sujeto = db.query(SujetoDerecho).filter(
        SujetoDerecho.ID_Sujeto_Derecho == proveedor.Sujeto_Derecho
    ).first()

    total_compras = db.query(Compra).filter(
        Compra.ID_Proveedor == proveedor.ID_Proveedor
    ).count()

    ultima = (
        db.query(Compra)
        .filter(Compra.ID_Proveedor == proveedor.ID_Proveedor)
        .order_by(Compra.Fecha_Compra.desc())
        .first()
    )
    ultima_fecha  = ultima.Fecha_Compra if ultima else None
    ultima_estado = None
    if ultima:
        estado_obj    = db.query(Estado).filter(Estado.ID_Estados == ultima.Estado).first()
        ultima_estado = estado_obj.Estado if estado_obj else None

    insumo_ids = (
        db.query(distinct(DetalleCompra.ID_Insumo))
        .join(Compra, Compra.ID_Compra == DetalleCompra.ID_Compra)
        .filter(
            Compra.ID_Proveedor == proveedor.ID_Proveedor,
            DetalleCompra.ID_Insumo != None,
        )
        .all()
    )
    ids_lista = [id_ins for (id_ins,) in insumo_ids]
    ins_map   = {i.ID_Insumo: i for i in db.query(Insumo).filter(Insumo.ID_Insumo.in_(ids_lista)).all()} if ids_lista else {}
    insumos_provistos = [ins_map[iid].Nombre for iid in ids_lista if iid in ins_map]

    return {
        "ID_Proveedor":         proveedor.ID_Proveedor,
        "Sujeto_Derecho":       proveedor.Sujeto_Derecho,
        "nombre_sujeto":        sujeto.Sujeto_Derecho if sujeto else None,
        "NIT":                  proveedor.NIT,
        "Cedula":               proveedor.Cedula,
        "Responsable":          proveedor.Responsable,
        "Direccion":            proveedor.Direccion,
        "Municipio":            proveedor.Municipio,
        "Departamento":         proveedor.Departamento,
        "Telefono":             proveedor.Telefono,
        "Correo":               proveedor.Correo,
        "total_compras":        total_compras,
        "ultima_compra_fecha":  ultima_fecha,
        "ultima_compra_estado": ultima_estado,
        "insumos_provistos":    insumos_provistos,
    }


def _batch_proveedores(proveedores: list, db: Session) -> list:
    if not proveedores:
        return []
    prov_ids   = [p.ID_Proveedor for p in proveedores]
    sujeto_ids = list({p.Sujeto_Derecho for p in proveedores if p.Sujeto_Derecho})

    sujetos_map = {s.ID_Sujeto_Derecho: s for s in db.query(SujetoDerecho).filter(SujetoDerecho.ID_Sujeto_Derecho.in_(sujeto_ids)).all()} if sujeto_ids else {}

    count_rows = (db.query(Compra.ID_Proveedor, func.count(Compra.ID_Compra).label("total"))
        .filter(Compra.ID_Proveedor.in_(prov_ids)).group_by(Compra.ID_Proveedor).all())
    compras_count = {r.ID_Proveedor: r.total for r in count_rows}

    ultima_id_rows = (db.query(func.max(Compra.ID_Compra).label("max_id"), Compra.ID_Proveedor)
        .filter(Compra.ID_Proveedor.in_(prov_ids)).group_by(Compra.ID_Proveedor).all())
    ultima_id_by_prov = {r.ID_Proveedor: r.max_id for r in ultima_id_rows}
    uc_ids = [v for v in ultima_id_by_prov.values() if v]
    ultimas_map = {c.ID_Proveedor: c for c in db.query(Compra).filter(Compra.ID_Compra.in_(uc_ids)).all()} if uc_ids else {}

    estado_ids  = list({c.Estado for c in ultimas_map.values() if c.Estado})
    estados_map = {e.ID_Estados: e for e in db.query(Estado).filter(Estado.ID_Estados.in_(estado_ids)).all()} if estado_ids else {}

    insumo_rows = (db.query(Compra.ID_Proveedor, DetalleCompra.ID_Insumo)
        .join(DetalleCompra, DetalleCompra.ID_Compra == Compra.ID_Compra)
        .filter(Compra.ID_Proveedor.in_(prov_ids), DetalleCompra.ID_Insumo != None)
        .distinct().all())
    insumos_by_prov: dict = {}
    all_insumo_ids: set = set()
    for row in insumo_rows:
        insumos_by_prov.setdefault(row.ID_Proveedor, set()).add(row.ID_Insumo)
        all_insumo_ids.add(row.ID_Insumo)
    insumos_map = {i.ID_Insumo: i for i in db.query(Insumo).filter(Insumo.ID_Insumo.in_(list(all_insumo_ids))).all()} if all_insumo_ids else {}

    def _build(prov: Proveedor) -> dict:
        sujeto  = sujetos_map.get(prov.Sujeto_Derecho)
        ultima  = ultimas_map.get(prov.ID_Proveedor)
        u_est   = estados_map.get(ultima.Estado) if ultima and ultima.Estado else None
        iids    = insumos_by_prov.get(prov.ID_Proveedor, set())
        return {
            "ID_Proveedor":         prov.ID_Proveedor,
            "Sujeto_Derecho":       prov.Sujeto_Derecho,
            "nombre_sujeto":        sujeto.Sujeto_Derecho if sujeto else None,
            "NIT":                  prov.NIT,
            "Cedula":               prov.Cedula,
            "Responsable":          prov.Responsable,
            "Direccion":            prov.Direccion,
            "Municipio":            prov.Municipio,
            "Departamento":         prov.Departamento,
            "Telefono":             prov.Telefono,
            "Correo":               prov.Correo,
            "total_compras":        compras_count.get(prov.ID_Proveedor, 0),
            "ultima_compra_fecha":  ultima.Fecha_Compra if ultima else None,
            "ultima_compra_estado": u_est.Estado if u_est else None,
            "insumos_provistos":    [insumos_map[iid].Nombre for iid in iids if iid in insumos_map],
        }

    return [_build(p) for p in proveedores]


def obtener_proveedores(
    db: Session,
    pagina: int = 1,
    por_pagina: int = 10,
    busqueda: str = None
) -> dict:
    query = db.query(Proveedor)

    if busqueda:
        termino = f"%{busqueda}%"
        query = query.filter(
            Proveedor.Responsable.ilike(termino) |
            Proveedor.NIT.ilike(termino) |
            Proveedor.Cedula.ilike(termino) |
            Proveedor.Correo.ilike(termino) |
            Proveedor.Telefono.ilike(termino)
        )

    total       = query.count()
    offset      = (pagina - 1) * por_pagina
    proveedores = query.offset(offset).limit(por_pagina).all()

    return {
        "total":       total,
        "pagina":      pagina,
        "por_pagina":  por_pagina,
        "proveedores": _batch_proveedores(proveedores, db),
    }


def obtener_proveedor(db: Session, id_proveedor: int) -> dict:
    proveedor = db.query(Proveedor).filter(
        Proveedor.ID_Proveedor == id_proveedor
    ).first()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return _formato_proveedor(proveedor, db)


def crear_proveedor(db: Session, datos: ProveedorCreate) -> dict:
    if datos.Correo and db.query(Proveedor).filter(
        Proveedor.Correo == datos.Correo
    ).first():
        raise HTTPException(status_code=400, detail="Ya existe un proveedor con ese correo")

    nuevo = Proveedor(
        Sujeto_Derecho = datos.Sujeto_Derecho,
        NIT            = datos.NIT,
        Cedula         = datos.Cedula,
        Responsable    = datos.Responsable,
        Direccion      = datos.Direccion,
        Municipio      = datos.Municipio,
        Departamento   = datos.Departamento,
        Telefono       = datos.Telefono,
        Correo         = datos.Correo,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return _formato_proveedor(nuevo, db)


def editar_proveedor(db: Session, id_proveedor: int, datos: ProveedorUpdate) -> dict:
    proveedor = db.query(Proveedor).filter(
        Proveedor.ID_Proveedor == id_proveedor
    ).first()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    for campo, valor in datos.model_dump(exclude_none=True).items():
        setattr(proveedor, campo, valor)

    db.commit()
    db.refresh(proveedor)
    return _formato_proveedor(proveedor, db)


def eliminar_proveedor(db: Session, id_proveedor: int) -> dict:
    proveedor = db.query(Proveedor).filter(
        Proveedor.ID_Proveedor == id_proveedor
    ).first()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    total_compras = db.query(Compra).filter(Compra.ID_Proveedor == id_proveedor).count()
    if total_compras > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar: el proveedor tiene {total_compras} compra(s) registrada(s)"
        )

    db.delete(proveedor)
    db.commit()
    return {"mensaje": f"Proveedor {id_proveedor} eliminado correctamente"}
