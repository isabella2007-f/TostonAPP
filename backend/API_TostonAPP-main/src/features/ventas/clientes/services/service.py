from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime

from src.shared.services.models import Usuario
from src.features.auth.services.service import hashear_contrasena
from .schemas import ClienteCreate, ClienteUpdate


def _formato_cliente(cliente: Usuario) -> dict:
    return {
        "ID_Usuario":     cliente.ID_Usuario,
        "Cedula":         cliente.Cedula,
        "Tipo_Documento": getattr(cliente, "Tipo_Documento", None),
        "Nombre":         cliente.Nombre,
        "Apellidos":      cliente.Apellidos,
        "Correo":         cliente.Correo,
        "Telefono":       cliente.Telefono,
        "Fecha_creacion": cliente.Fecha_creacion,
        "Estado":         cliente.Estado,
        "Direccion":      cliente.Direccion,
        "Departamento":   cliente.Departamento,
        "Municipio":      cliente.Municipio,
        # El barrio guardado del cliente. De él sale el precio del domicilio,
        # así que sin esto el panel tiene que volver a preguntarlo al armar un
        # pedido a nombre de alguien que ya lo tiene puesto.
        "ID_Barrio":      getattr(cliente, "ID_Barrio", None),
        # Cómo llegar a su casa. Es lo que lee el domiciliario; si no viaja,
        # el pedido que arma el personal sale sin indicaciones.
        "Indicaciones":   getattr(cliente, "Indicaciones", None),
        "Auto_Eliminado": bool(getattr(cliente, "Auto_Eliminado", 0)),
        "tiene_foto":     cliente.Foto_perfil is not None,
    }


def obtener_clientes(db: Session, pagina: int = 1, por_pagina: int = 10, busqueda: str = None) -> dict:
    # Solo usuarios con rol Cliente (ID_Rol=3). Excluye admins, empleados y domiciliarios.
    ROL_CLIENTE = 3
    query = db.query(Usuario).filter(Usuario.ID_Rol == ROL_CLIENTE)

    if busqueda:
        termino = f"%{busqueda}%"
        query = query.filter(
            Usuario.Nombre.ilike(termino)      |
            Usuario.Apellidos.ilike(termino)   |
            Usuario.Correo.ilike(termino)      |
            Usuario.Cedula.ilike(termino)      |
            Usuario.Municipio.ilike(termino)   |
            Usuario.Departamento.ilike(termino)
        )

    total    = query.count()
    offset   = (pagina - 1) * por_pagina
    clientes = query.offset(offset).limit(por_pagina).all()

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "clientes": [_formato_cliente(c) for c in clientes]}


def obtener_cliente(db: Session, id_usuario: int) -> dict:
    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return _formato_cliente(cliente)


def crear_cliente(db: Session, datos: ClienteCreate) -> dict:
    if datos.Contrasena != datos.Confirmar_Contrasena:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")

    if db.query(Usuario).filter(Usuario.Correo == datos.Correo).first():
        raise HTTPException(status_code=400, detail="Correo ya registrado")

    nuevo = Usuario(
        Cedula             = datos.Cedula,
        Tipo_Documento     = datos.Tipo_Documento,
        Nombre             = datos.Nombre,
        Apellidos          = datos.Apellidos,
        Correo             = datos.Correo,
        Contrasena         = hashear_contrasena(datos.Contrasena),
        Telefono           = datos.Telefono,
        Fecha_creacion     = datos.Fecha_creacion or datetime.now(),
        Estado             = datos.Estado,
        Direccion          = datos.Direccion,
        Departamento       = datos.Departamento,
        Municipio          = datos.Municipio,
        ID_Rol             = 3,
        Correo_Verificado  = 1,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return _formato_cliente(nuevo)


def editar_cliente(db: Session, id_usuario: int, datos: ClienteUpdate) -> dict:
    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    campos = datos.model_dump(exclude_none=True)

    nuevo_correo = campos.get("Correo")
    if nuevo_correo and nuevo_correo != cliente.Correo:
        if db.query(Usuario).filter(
            Usuario.Correo == nuevo_correo, Usuario.ID_Usuario != id_usuario
        ).first():
            raise HTTPException(status_code=400, detail="Correo ya registrado")

    nueva_cedula = campos.get("Cedula")
    if nueva_cedula and nueva_cedula != cliente.Cedula:
        if db.query(Usuario).filter(
            Usuario.Cedula == nueva_cedula, Usuario.ID_Usuario != id_usuario
        ).first():
            raise HTTPException(status_code=400, detail="Cédula ya registrada")

    for campo, valor in campos.items():
        setattr(cliente, campo, valor)

    # Editar una cuenta que su dueño eliminó = recuperarla.
    if getattr(cliente, "Auto_Eliminado", 0):
        cliente.Auto_Eliminado = 0

    db.commit()
    db.refresh(cliente)
    return _formato_cliente(cliente)


def cambiar_estado(db: Session, id_usuario: int, nuevo_estado: int) -> dict:
    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cliente.Estado = nuevo_estado
    if nuevo_estado == 1 and getattr(cliente, "Auto_Eliminado", 0):
        cliente.Auto_Eliminado = 0
    db.commit()
    db.refresh(cliente)
    return _formato_cliente(cliente)


def subir_foto(db: Session, id_usuario: int, url: str) -> dict:
    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    cliente.Foto_perfil = url
    db.commit()
    db.refresh(cliente)
    return _formato_cliente(cliente)


def eliminar_cliente(db: Session, id_usuario: int) -> dict:
    cliente = db.query(Usuario).filter(Usuario.ID_Usuario == id_usuario).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    db.delete(cliente)
    db.commit()
    return {"mensaje": f"Cliente {id_usuario} eliminado correctamente"}