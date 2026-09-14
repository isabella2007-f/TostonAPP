from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Boolean, Text, JSON
from sqlalchemy.orm import relationship
from .database import Base


# ─────────────────────────────────────────
# ESTADOS
# ─────────────────────────────────────────

class Estado(Base):
    __tablename__ = "Estados"

    ID_Estados = Column(Integer, primary_key=True, index=True)
    Codigo     = Column(Integer)
    Estado     = Column(String(25))


# ─────────────────────────────────────────
# ROLES Y PERMISOS
# ─────────────────────────────────────────

class Rol(Base):
    __tablename__ = "Roles"

    ID_Rol = Column(Integer, primary_key=True, index=True)
    Rol    = Column(String(25))
    Estado = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Icono = Column(String(500), nullable=True)

    permisos  = relationship("RolXPermiso", back_populates="rol")


class Permiso(Base):
    __tablename__ = "Permisos"

    ID_Permiso  = Column(Integer, primary_key=True, index=True)
    # Ampliado de 25 a 60: `cambiar_estado_ubicaciones` (26 chars) no cabía.
    # Migración en src/main.py: ALTER TABLE Permisos MODIFY COLUMN Permiso VARCHAR(60).
    Permiso     = Column(String(60))
    Descripcion = Column(Text)

    roles = relationship("RolXPermiso", back_populates="permiso")


class RolXPermiso(Base):
    __tablename__ = "Rol_x_Permiso"

    ID_Rol     = Column(Integer, ForeignKey("Roles.ID_Rol"), primary_key=True)
    ID_Permiso = Column(Integer, ForeignKey("Permisos.ID_Permiso"), primary_key=True)

    rol     = relationship("Rol", back_populates="permisos")
    permiso = relationship("Permiso", back_populates="roles")


# ─────────────────────────────────────────
# USUARIOS Y EMPLEADOS
# ─────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "Usuarios"

    ID_Usuario     = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Cedula         = Column(String(20), nullable=True)
    Tipo_Documento = Column(String(5), nullable=True)
    ID_Rol         = Column(Integer, ForeignKey("Roles.ID_Rol"), nullable=True)
    Nombre         = Column(String(50))
    Apellidos      = Column(String(50))
    Correo         = Column(String(255), unique=True, index=True)
    Direccion      = Column(String(50))
    Municipio      = Column(String(25))
    Departamento   = Column(String(60))
    Indicaciones   = Column(String(255), nullable=True)
    Telefono       = Column(String(20))
    Foto_perfil    = Column(String(500), nullable=True)
    Fecha_creacion = Column(DateTime)
    Contrasena     = Column(String(255))
    Estado         = Column(Integer, ForeignKey("Estados.ID_Estados"))
    # 1 = el correo fue verificado mediante el enlace; 0 = pendiente de verificar.
    # Es independiente de Estado (que indica si la cuenta está activa/desactivada).
    Correo_Verificado = Column(Integer, default=0)
    # Token FCM para push notifications. Se persiste en BD para sobrevivir reinicios del servidor.
    FCM_Token      = Column(String(300), nullable=True)
    # Rate limiting de login persistido en BD para sobrevivir cold starts de Render.
    # Migración requerida: ALTER TABLE Usuarios ADD COLUMN Intentos_Login INT DEFAULT 0,
    #                                           ADD COLUMN Bloqueado_Hasta DATETIME NULL;
    Intentos_Login = Column(Integer, default=0, nullable=True)
    Bloqueado_Hasta = Column(DateTime, nullable=True)
    # 1 = la propia persona eliminó su cuenta (borrado lógico). Distingue este
    # caso de una cuenta desactivada por un admin, para poder recuperarla.
    Auto_Eliminado = Column(Integer, default=0, nullable=True)
    # Barrio de referencia del cliente (módulo Ubicaciones). Es SOLO dato guía:
    # no condiciona el domicilio, que se elige y confirma en el checkout.
    # Migración: ALTER TABLE Usuarios ADD COLUMN ID_Barrio INT NULL;
    ID_Barrio      = Column(Integer, ForeignKey("Barrios.ID_Barrio"), nullable=True)

    rol          = relationship("Rol", foreign_keys=[ID_Rol])
    barrio       = relationship("Barrio", foreign_keys=[ID_Barrio])
    ventas       = relationship("Venta", back_populates="usuario")
    devoluciones = relationship("Devolucion", back_populates="usuario")


class VerificacionEmail(Base):
    __tablename__ = "Verificaciones_Email"

    ID_Verificacion = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Usuario      = Column(Integer, ForeignKey("Usuarios.ID_Usuario"))
    Token           = Column(String(36), unique=True, index=True)
    Expira_En       = Column(DateTime)
    Usado           = Column(Boolean, default=False)

    usuario = relationship("Usuario", foreign_keys=[ID_Usuario])


# ─────────────────────────────────────────
# CATEGORIAS
# ─────────────────────────────────────────

class CategoriaProducto(Base):
    __tablename__ = "Categoria_Producto"

    ID_Categoria     = Column(Integer, primary_key=True, index=True)
    Nombre_Categoria = Column(String(100))
    Descripcion      = Column(Text)
    Estado           = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Icono            = Column(String(500), nullable=True)
    Fecha_Creacion   = Column(DateTime, nullable=True)

    productos       = relationship("Producto", back_populates="categoria")
    fichas_tecnicas = relationship("FichaTecnica", back_populates="categoria")


class CategoriaInsumo(Base):
    __tablename__ = "Categoria_Insumos"

    ID_Categoria     = Column(Integer, primary_key=True, index=True)
    Nombre_Categoria = Column(String(100))
    Descripcion      = Column(Text)
    Estado           = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Icono            = Column(String(500), nullable=True)
    Fecha_Creacion   = Column(DateTime)

    insumos = relationship("Insumo", back_populates="categoria")


# ─────────────────────────────────────────
# INSUMOS
# ─────────────────────────────────────────

class UnidadMedida(Base):
    __tablename__ = "Unidad_Medida"

    ID_Unidad_Medida = Column(Integer, primary_key=True, index=True)
    Simbolo          = Column(String(5))
    Unidad_Medida    = Column(String(25))

    insumos = relationship("Insumo", back_populates="unidad_medida")


class Insumo(Base):
    __tablename__ = "Insumos"

    ID_Insumo      = Column(Integer, primary_key=True, index=True)
    ID_Categoria   = Column(Integer, ForeignKey("Categoria_Insumos.ID_Categoria"))
    ID_Lote_Compra = Column(Integer, ForeignKey("Lote_Compra.ID_Lote_Compra"))
    Nombre         = Column(String(100))
    Unidad_Medida  = Column(Integer, ForeignKey("Unidad_Medida.ID_Unidad_Medida"))
    Stock_Actual   = Column(Numeric(10, 4))
    Stock_Minimo   = Column(Integer)
    Estado         = Column(Integer, ForeignKey("Estados.ID_Estados"))

    categoria       = relationship("CategoriaInsumo", back_populates="insumos")
    unidad_medida   = relationship("UnidadMedida", back_populates="insumos")
    lotes_compra    = relationship("LoteCompra", back_populates="insumo", foreign_keys="LoteCompra.ID_Insumo")
    detalle_compras = relationship("DetalleCompra", back_populates="insumo")
    ordenes         = relationship("OrdenProduccion", back_populates="insumo")


class LoteInsumo(Base):
    __tablename__ = "Lote_Insumos"

    ID_Lote           = Column(Integer, primary_key=True, index=True)
    Fecha_Vencimiento = Column(DateTime)
    Cantidad          = Column(Integer)


class LoteCompra(Base):
    __tablename__ = "Lote_Compra"

    ID_Lote_Compra    = Column(Integer, primary_key=True, index=True)
    ID_Insumo         = Column(Integer, ForeignKey("Insumos.ID_Insumo"))
    Fecha_Vencimiento = Column(DateTime)
    Cantidad_Inicial  = Column(Numeric(10, 4))
    Cantidad_Actual   = Column(Numeric(10, 4), nullable=True)
    Estado            = Column(Integer, ForeignKey("Estados.ID_Estados"))

    insumo          = relationship("Insumo", back_populates="lotes_compra", foreign_keys="[LoteCompra.ID_Insumo]")
    detalle_compras = relationship("DetalleCompra", back_populates="lote_compra")


# ─────────────────────────────────────────
# PROVEEDORES Y COMPRAS
# ─────────────────────────────────────────

class SujetoDerecho(Base):
    __tablename__ = "Sujeto_Derecho"

    ID_Sujeto_Derecho = Column(Integer, primary_key=True, index=True)
    Sujeto_Derecho    = Column(String(25))

    proveedores = relationship("Proveedor", back_populates="sujeto_derecho")


class Proveedor(Base):
    __tablename__ = "Proveedores"

    ID_Proveedor   = Column(Integer, primary_key=True, index=True)
    Sujeto_Derecho = Column(Integer, ForeignKey("Sujeto_Derecho.ID_Sujeto_Derecho"))
    Responsable    = Column(String(100))
    Direccion      = Column(String(50))
    Municipio      = Column(String(25))
    Departamento   = Column(String(60))
    Telefono       = Column(String(20))
    Correo         = Column(String(255))

    sujeto_derecho = relationship("SujetoDerecho", back_populates="proveedores")
    compras        = relationship("Compra", back_populates="proveedor")


class Compra(Base):
    __tablename__ = "Compras"

    ID_Compra            = Column(Integer, primary_key=True, index=True)
    ID_Proveedor         = Column(Integer, ForeignKey("Proveedores.ID_Proveedor"))
    Total_Pago           = Column(Numeric(30, 2))
    Fecha_Compra         = Column(DateTime)
    Fecha_Llegada        = Column(DateTime, nullable=True)  # fecha en que se completó la compra
    Fecha_Anulada        = Column(DateTime, nullable=True)  # fecha en que se anuló la compra
    Estado               = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Metodo_Pago          = Column(String(20))
    Notas                = Column(Text, nullable=True)
    Comprobante          = Column(String(500), nullable=True)  # URL Cloudinary del comprobante (pago por transferencia)
    Costo_Transporte     = Column(Numeric(30, 2), nullable=True)
    IVA_Porcentaje       = Column(Numeric(5, 2), nullable=True)
    Descuento_Porcentaje = Column(Numeric(5, 2), nullable=True)
    Otros_Costos         = Column(Numeric(30, 2), nullable=True)

    proveedor = relationship("Proveedor", back_populates="compras")
    detalles  = relationship("DetalleCompra", back_populates="compra")


class DetalleCompra(Base):
    __tablename__ = "Detalle_Compra"

    ID_Detalle_Compra = Column(Integer, primary_key=True, index=True)
    ID_Compra         = Column(Integer, ForeignKey("Compras.ID_Compra"))
    ID_Insumo         = Column(Integer, ForeignKey("Insumos.ID_Insumo"))
    ID_Lote_Compra    = Column(Integer, ForeignKey("Lote_Compra.ID_Lote_Compra"))
    Notas             = Column(Text)
    Cantidad          = Column(Numeric(10, 4))   # Numeric para soportar kg, g, L, mL
    Precio_Und        = Column(Numeric(30, 2))

    compra      = relationship("Compra", back_populates="detalles")
    insumo      = relationship("Insumo", back_populates="detalle_compras")
    lote_compra = relationship("LoteCompra", back_populates="detalle_compras")


# ─────────────────────────────────────────
# PRODUCTOS
# ─────────────────────────────────────────

class ProductoImagen(Base):
    __tablename__ = "Producto_Imagenes"

    ID_Producto_Img = Column(Integer, primary_key=True, index=True)
    ID_Producto     = Column(Integer, ForeignKey("Productos.ID_Producto"))
    imagen          = Column(String(500), nullable=True)

    producto = relationship("Producto", back_populates="imagenes", foreign_keys=[ID_Producto])


class Producto(Base):
    __tablename__ = "Productos"

    ID_Producto         = Column(Integer, primary_key=True, index=True)
    nombre              = Column(String(255))
    ID_Categoria        = Column(Integer, ForeignKey("Categoria_Producto.ID_Categoria"))
    Precio_venta        = Column(Numeric(30, 2))
    Stock               = Column(Integer)
    Stock_Minimo        = Column(Integer)
    Requiere_Produccion = Column(Integer, default=0, nullable=False)
    Estado              = Column(Integer, ForeignKey("Estados.ID_Estados"))
    ID_Orden_Produccion = Column(Integer, ForeignKey("Orden_Produccion.ID_Orden_Produccion"))
    Imagen              = Column(Integer, ForeignKey("Producto_Imagenes.ID_Producto_Img"))
    Publicado           = Column(Integer, default=0, nullable=True)
    Descripcion_Corta   = Column(String(255), nullable=True)
    Descripcion_Larga   = Column(String(2000), nullable=True)
    Fecha_Creacion      = Column(DateTime, nullable=True)

    categoria       = relationship("CategoriaProducto", back_populates="productos")
    fichas_tecnicas = relationship("FichaTecnica", back_populates="producto")
    imagenes        = relationship("ProductoImagen", back_populates="producto", foreign_keys="[ProductoImagen.ID_Producto]")
    lotes_producto  = relationship("LoteProducto",   back_populates="producto")
    ventas          = relationship("VentaXProducto", back_populates="producto")
    devoluciones    = relationship("DevolucionDetalle", back_populates="producto")


# ─────────────────────────────────────────
# PRODUCCION
# ─────────────────────────────────────────

class FichaTecnica(Base):
    __tablename__ = "Ficha_Tecnica"

    ID_Ficha        = Column(Integer, primary_key=True, index=True)
    ID_Producto     = Column(Integer, ForeignKey("Productos.ID_Producto"))
    Version         = Column(String(25))
    ID_Categoria    = Column(Integer, ForeignKey("Categoria_Producto.ID_Categoria"))
    Estado          = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Observaciones   = Column(Text)
    Procedimiento   = Column(Text)
    Fecha_Creacion  = Column(DateTime)
    Dias_Vida_Util   = Column(Integer, nullable=True)
    Vida_Util_Unidad = Column(String(10), nullable=True)

    producto      = relationship("Producto", back_populates="fichas_tecnicas")
    categoria     = relationship("CategoriaProducto", back_populates="fichas_tecnicas")
    ordenes       = relationship("OrdenProduccion", back_populates="ficha")
    insumos_ficha = relationship("FichaTecnicaInsumo", back_populates="ficha", cascade="all, delete-orphan")


class FichaTecnicaInsumo(Base):
    __tablename__ = "Ficha_Tecnica_Insumo"

    ID_Ficha_Insumo = Column(Integer, primary_key=True, autoincrement=True)
    ID_Ficha        = Column(Integer, ForeignKey("Ficha_Tecnica.ID_Ficha"), nullable=False)
    ID_Insumo       = Column(Integer, ForeignKey("Insumos.ID_Insumo"), nullable=False)
    Cantidad        = Column(Numeric(10, 2), nullable=True)
    Unidad          = Column(String(50), nullable=True)

    ficha  = relationship("FichaTecnica", back_populates="insumos_ficha")
    insumo = relationship("Insumo")


class OrdenProduccion(Base):
    __tablename__ = "Orden_Produccion"

    ID_Orden_Produccion = Column(Integer, primary_key=True, index=True)
    ID_Venta            = Column(Integer, ForeignKey("Ventas.ID_Venta"), nullable=True)
    ID_Producto         = Column(Integer, ForeignKey("Productos.ID_Producto"))
    ID_Insumo           = Column(Integer, ForeignKey("Insumos.ID_Insumo"), nullable=True)
    ID_Ficha            = Column(Integer, ForeignKey("Ficha_Tecnica.ID_Ficha"), nullable=True)
    Cantidad            = Column(Integer)
    Fecha_Creacion      = Column(DateTime, nullable=True)   # cuándo se registró la orden (automático)
    Fecha_inicio        = Column(DateTime)
    Fecha_Entrega       = Column(DateTime)
    Fecha_fin           = Column(DateTime, nullable=True)   # cuándo pasó a Completada (automático)
    Estado              = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Costo               = Column(Numeric(30, 2))

    producto = relationship("Producto", foreign_keys=[ID_Producto])
    insumo = relationship("Insumo", back_populates="ordenes")
    ficha  = relationship("FichaTecnica", back_populates="ordenes")
    venta  = relationship("Venta", back_populates="ordenes_produccion")
    lote   = relationship("LoteProducto", back_populates="orden", uselist=False)


class LoteProducto(Base):
    __tablename__ = "Lote_Producto"

    ID_Lote_Producto    = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Orden_Produccion = Column(Integer, ForeignKey("Orden_Produccion.ID_Orden_Produccion"))
    ID_Producto         = Column(Integer, ForeignKey("Productos.ID_Producto"))
    Numero_Lote         = Column(String(50))
    Fecha_Produccion    = Column(DateTime)
    Fecha_Vencimiento   = Column(DateTime, nullable=True)
    Cantidad            = Column(Integer)
    Estado              = Column(Integer, ForeignKey("Estados.ID_Estados"), default=1)

    orden    = relationship("OrdenProduccion", back_populates="lote")
    producto = relationship("Producto", back_populates="lotes_producto")


# ─────────────────────────────────────────
# VENTAS
# ─────────────────────────────────────────

class Venta(Base):
    __tablename__ = "Ventas"

    ID_Venta               = Column(Integer, primary_key=True, index=True)
    ID_Usuario             = Column(Integer, ForeignKey("Usuarios.ID_Usuario"))
    Total                  = Column(Numeric(30, 2))
    Estado                 = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Metodo_Pago            = Column(String(20))
    Fecha_Venta            = Column(DateTime)
    Fecha_pedido           = Column(DateTime)
    Fecha_entrega          = Column(DateTime, nullable=True)   # timestamp real de entrega
    Fecha_entrega_esperada = Column(DateTime, nullable=True)
    Comprobante_Pago       = Column(Text, nullable=True)
    # Pedido especial: alguna línea supera el stock disponible. Lo calcula el
    # backend al crear la venta; el cliente no puede enviarlo.
    Sobre_Stock            = Column(Integer, default=0, nullable=True)
    # Anticipo del 50% exigido por superar el stock y lo efectivamente cubierto
    # (créditos verificados en el libro mayor + transferencia con comprobante).
    Anticipo_Requerido     = Column(Numeric(30, 2), nullable=True)
    Anticipo_Pagado        = Column(Numeric(30, 2), nullable=True)
    # Anticipo del 50% por total > $50.000 (regla general de negocio)
    Requiere_Anticipo        = Column(Integer,      default=0,           nullable=True)
    Anticipo_Monto           = Column(Numeric(30, 2),                    nullable=True)
    Anticipo_Metodo_Pago     = Column(String(30),                        nullable=True)
    Anticipo_Comprobante_Url = Column(String(500),                       nullable=True)
    Anticipo_Registrado      = Column(Integer,      default=0,           nullable=True)
    Pago_Final_Registrado    = Column(Integer,      default=0,           nullable=True)
    Pago_Final_Monto         = Column(Numeric(30, 2),                    nullable=True)
    Pago_Final_Metodo_Pago   = Column(String(30),                        nullable=True)
    Pago_Final_Comprobante_Url = Column(String(500),                     nullable=True)
    Pago_Final_Fecha         = Column(DateTime,                          nullable=True)
    # Pago mixto (Metodo_Pago = "Mixto"): el pedido se reparte entre las dos
    # formas. La transferencia se paga al hacer el pedido y lleva comprobante;
    # el efectivo se cobra en mano al entregar. Los dos montos los calcula el
    # backend sobre el total real, el cliente solo propone la proporción.
    Monto_Efectivo           = Column(Numeric(30, 2),                    nullable=True)
    Monto_Transferencia      = Column(Numeric(30, 2),                    nullable=True)
    Estado_Pago              = Column(String(30),   default="pendiente", nullable=True)
    Motivo_Rechazo_Comprobante = Column(Text,                           nullable=True)
    Fecha_Rechazada          = Column(DateTime,                          nullable=True)
    # Guardado al crear la venta: True si algún producto de producción no tenía stock suficiente.
    # Usar este valor (snapshot) evita que el botón "proponer fecha" aparezca incorrectamente
    # cuando el stock cambia después de crear el pedido.
    Necesita_Produccion      = Column(Integer,      default=0,           nullable=True)
    # Respuesta del cliente a "¿Quiere que enviemos todo el pedido junto el domingo?"
    # NULL = no respondió todavía, 1 = sí, 0 = no.
    Envio_Completo_Domingo   = Column(Integer,                           nullable=True)
    # Cuántas veces el cliente ha rechazado fechas propuestas. No cancela ni
    # escala nada por sí solo; a partir de LIMITE_INTENTOS_RECHAZO el frontend
    # resalta con más énfasis el canal de excepción (hablar con el admin).
    intentos_rechazo         = Column(Integer,      default=0,           nullable=True)
    # Comprobantes de pago rechazados (anticipo + saldo final acumulados).
    # Al llegar a LIMITE_INTENTOS_RECHAZO el pedido se cancela automáticamente.
    intentos_rechazo_comprobante = Column(Integer,  default=0,           nullable=True)
    # Contraofertas de fecha que el admin ya hizo (máximo 1).
    contraoferta_admin_count = Column(Integer,      default=0,           nullable=True)
    # 1 cuando el admin ya usó su contraoferta: al cliente solo le queda aceptar o cancelar.
    propuesta_final_cliente  = Column(Integer,      default=0,           nullable=True)

    usuario            = relationship("Usuario", back_populates="ventas")
    productos          = relationship("VentaXProducto", back_populates="venta")
    detalle            = relationship("DetalleVenta", back_populates="venta")
    domicilios         = relationship("Domicilio", back_populates="venta")
    devoluciones       = relationship("Devolucion", back_populates="venta")
    ordenes_produccion = relationship("OrdenProduccion", back_populates="venta")


class VentaXProducto(Base):
    __tablename__ = "Venta_x_Producto"

    ID_Venta    = Column(Integer, ForeignKey("Ventas.ID_Venta"), primary_key=True)
    ID_Producto = Column(Integer, ForeignKey("Productos.ID_Producto"), primary_key=True)
    Cantidad    = Column(Integer)
    # Unidades pedidas por encima del stock disponible al crear la venta
    # (preorden). No altera el stock real: solo identifica la parte especial.
    Cantidad_Preorden = Column(Integer, default=0, nullable=True)

    venta    = relationship("Venta", back_populates="productos")
    producto = relationship("Producto", back_populates="ventas")


class HistorialFechasPropuestas(Base):
    __tablename__ = "Historial_Fechas_Propuestas"

    ID_Historial   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Venta       = Column(Integer, ForeignKey("Ventas.ID_Venta"), nullable=False)
    ID_Usuario     = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), nullable=True)
    Fecha_Propuesta = Column(DateTime, nullable=True)   # la fecha de entrega propuesta/aceptada
    Fecha_Accion   = Column(DateTime, nullable=False)   # cuándo ocurrió la acción
    Tipo_Accion    = Column(String(20), nullable=False)  # 'propuesta' | 'aceptada' | 'rechazada'
    Motivo_Rechazo = Column(Text, nullable=True)


class DetalleVenta(Base):
    __tablename__ = "Detalle_Venta"

    ID_DetalleVenta = Column(Integer, primary_key=True, index=True)
    ID_Venta        = Column(Integer, ForeignKey("Ventas.ID_Venta"))
    A_Nombre_De     = Column(String(100))
    IVA             = Column(Numeric(30, 2))
    Descuento       = Column(Numeric(30, 2))
    SubTotal        = Column(Numeric(30, 2))

    venta        = relationship("Venta", back_populates="detalle")
    devoluciones = relationship("Devolucion", back_populates="detalle_venta")


# ─────────────────────────────────────────
# LOGISTICA Y DEVOLUCIONES
# ─────────────────────────────────────────

class Domicilio(Base):
    __tablename__ = "Domicilios"

    ID_Domicilio         = Column(Integer, primary_key=True, index=True)
    ID_Venta             = Column(Integer, ForeignKey("Ventas.ID_Venta"))
    ID_Empleado          = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), nullable=True)
    Fecha_asignacion     = Column(DateTime)
    Fecha_entrega        = Column(DateTime)
    Observaciones        = Column(Text)
    # Quién registró el cobro en efectivo, cuándo y por cuánto. Vive aparte de
    # Observaciones porque eso es texto que el cliente escribe y lee.
    Cobro_Auditoria      = Column(Text, nullable=True)
    Estado               = Column(Integer, ForeignKey("Estados.ID_Estados"))
    Direccion_entrega    = Column(String(50))
    Municipio_entrega    = Column(String(25))
    Departamento_entrega = Column(String(60))
    # Código de entrega que se le pedía al cliente al recibir. Se quitó del
    # flujo: entregar ya no depende de dictar un número. Las columnas quedan por
    # los domicilios viejos que lo tienen guardado; nadie las lee ni las escribe.
    OTP        = Column(String(10), nullable=True)
    OTP_Expira = Column(DateTime, nullable=True)

    # ── Snapshot del precio del domicilio (módulo Ubicaciones) ──────────────
    # Se congela al CREAR el domicilio y no se recalcula nunca, aunque después
    # cambie el precio del barrio o una oferta. Reemplaza la antigua constante
    # COSTO_DOMICILIO = Decimal("5000"). Desglose_Ofertas guarda el JSON
    # congelado {base, pesos_total, ofertas:[{id,nombre,tipo,valor,efecto}],
    # final, techo_aplicado?}. Migración: ver src/main.py.
    ID_Barrio              = Column(Integer, ForeignKey("Barrios.ID_Barrio"), nullable=True)
    Precio_Domicilio_Base  = Column(Integer, nullable=True)
    Precio_Domicilio_Final = Column(Integer, nullable=True)
    Desglose_Ofertas       = Column(JSON, nullable=True)

    # ── Liquidación del efectivo cobrado por el repartidor ──────────────────
    # Cuando el método de pago es efectivo, el repartidor cobra en el domicilio
    # y el admin registra aquí que esa plata ya fue entregada a la empresa.
    Efectivo_Liquidado  = Column(Integer, default=0, nullable=True)   # 0 = pendiente, 1 = liquidado
    Fecha_Liquidacion   = Column(DateTime, nullable=True)
    ID_Liquidado_Por    = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), nullable=True)

    venta          = relationship("Venta", back_populates="domicilios")
    empleado       = relationship("Usuario", foreign_keys=[ID_Empleado])
    liquidado_por  = relationship("Usuario", foreign_keys=[ID_Liquidado_Por])
    barrio         = relationship("Barrio", foreign_keys=[ID_Barrio])


class Devolucion(Base):
    __tablename__ = "Devoluciones"

    ID_Devolucion   = Column(Integer, primary_key=True, index=True)
    ID_Venta        = Column(Integer, ForeignKey("Ventas.ID_Venta"))
    ID_Usuario      = Column(Integer, ForeignKey("Usuarios.ID_Usuario"))            # ← actualizado
    ID_DetalleVenta = Column(Integer, ForeignKey("Detalle_Venta.ID_DetalleVenta"))
    FechaDevolucion = Column(DateTime)
    Motivo          = Column(Text)
    Estado          = Column(Integer, ForeignKey("Estados.ID_Estados"))
    TotalDevuelto   = Column(Numeric(30, 2))
    FechaAprobacion = Column(DateTime)
    FechaReembolso  = Column(DateTime)
    UsuarioAprueba  = Column(Boolean)
    Comentario      = Column(Text)
    Comprobante_Imagen = Column(Text)   # evidencia fotográfica (base64), opcional

    venta         = relationship("Venta", back_populates="devoluciones")
    usuario       = relationship("Usuario", back_populates="devoluciones")
    detalle_venta = relationship("DetalleVenta", back_populates="devoluciones")
    detalles      = relationship("DevolucionDetalle", back_populates="devolucion")


class DevolucionDetalle(Base):
    __tablename__ = "Devolucion_Detalle"

    ID_Devolucion_Detalle = Column(Integer, primary_key=True, index=True)
    ID_Devolucion         = Column(Integer, ForeignKey("Devoluciones.ID_Devolucion"))
    ID_Producto           = Column(Integer, ForeignKey("Productos.ID_Producto"))
    Cantidad              = Column(Integer)
    PrecioUnitario        = Column(Numeric(30, 2))
    Subtotal              = Column(Numeric(30, 2))

    devolucion = relationship("Devolucion", back_populates="detalles")
    producto   = relationship("Producto", back_populates="devoluciones")


class MensajeChat(Base):
    __tablename__ = "MensajesChat"

    ID_Mensaje       = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Domicilio     = Column(Integer, ForeignKey("Domicilios.ID_Domicilio"))
    Tipo_Remitente   = Column(String(20))
    ID_Remitente     = Column(Integer)
    Nombre_Remitente = Column(String(100), nullable=True)
    Contenido        = Column(Text)
    Fecha            = Column(DateTime)


# ─────────────────────────────────────────
# CREDITOS DE CLIENTE
# ─────────────────────────────────────────

class CreditoCliente(Base):
    __tablename__ = "Credito_Cliente"

    ID_Credito   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Usuario   = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), unique=True)
    Saldo        = Column(Numeric(30, 2), default=0)
    Fecha_Update = Column(DateTime)

    usuario      = relationship("Usuario", foreign_keys=[ID_Usuario])
    movimientos  = relationship("MovimientoCredito", back_populates="credito")


class MovimientoCredito(Base):
    __tablename__ = "Movimiento_Credito"

    ID_Movimiento = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Credito    = Column(Integer, ForeignKey("Credito_Cliente.ID_Credito"))
    ID_Devolucion = Column(Integer, ForeignKey("Devoluciones.ID_Devolucion"), nullable=True)
    ID_Venta      = Column(Integer, ForeignKey("Ventas.ID_Venta"), nullable=True)
    Tipo          = Column(String(20))      # "recarga" o "uso"
    Monto         = Column(Numeric(30, 2))
    Fecha         = Column(DateTime)

    credito    = relationship("CreditoCliente", back_populates="movimientos")


# ─────────────────────────────────────────
# CONFIGURACIÓN DE LANDING PAGE
# ─────────────────────────────────────────

class ConfiguracionLanding(Base):
    __tablename__ = "Configuracion_Landing"

    ID                       = Column(Integer, primary_key=True, index=True, autoincrement=True)
    hero_badge               = Column(String(200),  nullable=True)
    hero_title               = Column(String(200),  nullable=True)
    hero_description         = Column(Text,          nullable=True)
    history_title            = Column(String(200),  nullable=True)
    history_description      = Column(Text,          nullable=True)
    cta_title                = Column(String(200),  nullable=True)
    cta_description          = Column(Text,          nullable=True)
    contact_phone1           = Column(String(50),   nullable=True)
    contact_phone2           = Column(String(50),   nullable=True)
    contact_address_line     = Column(String(200),  nullable=True)
    contact_city             = Column(String(200),  nullable=True)
    contact_instagram_url    = Column(String(500),  nullable=True)
    contact_instagram_handle = Column(String(100),  nullable=True)
    # Ubicación del local en el mapa del footer (punto exacto, editable desde
    # "Editar Landing Page"). Si están en NULL se cae a geocodificar la dirección.
    map_lat                  = Column(Numeric(10, 7), nullable=True)
    map_lng                  = Column(Numeric(10, 7), nullable=True)
    # Horario de atención estructurado: gobierna el aviso de "fuera de horario"
    # del carrito y el checkout. Solo un admin puede editarlo.
    hora_apertura            = Column(String(5),   nullable=True)   # "08:00"
    hora_cierre              = Column(String(5),   nullable=True)   # "20:00"
    dias_atencion            = Column(String(20),  nullable=True)   # CSV ISO 1..7 (1=Lun)
    # Monto mínimo del pedido (sin domicilio) para habilitar entrega a domicilio.
    # 0 o NULL = sin mínimo. Editable solo por admin.
    pedido_minimo            = Column(Integer,     nullable=True,   default=0)

# ─────────────────────────────────────────
# SALIDAS (daños, vencimientos, ajustes)
# ─────────────────────────────────────────

class Salida(Base):
    __tablename__ = "Salidas"

    ID_Salida      = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Tipo           = Column(String(20))          # 'vencimiento','daño','ajuste','consumo','devolución'
    ID_Insumo      = Column(Integer, ForeignKey("Insumos.ID_Insumo"),    nullable=True)
    ID_Producto    = Column(Integer, ForeignKey("Productos.ID_Producto"), nullable=True)
    Cantidad       = Column(Integer)
    Motivo         = Column(Text, nullable=True)
    ID_Empleado    = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), nullable=True)
    Fecha          = Column(DateTime)
    Estado         = Column(Integer, ForeignKey("Estados.ID_Estados"))
    ID_Anulado_Por = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), nullable=True)
    Fecha_Anulacion = Column(DateTime, nullable=True)

    insumo      = relationship("Insumo",   foreign_keys=[ID_Insumo])
    producto    = relationship("Producto", foreign_keys=[ID_Producto])
    empleado    = relationship("Usuario",  foreign_keys=[ID_Empleado])
    anulado_por = relationship("Usuario",  foreign_keys=[ID_Anulado_Por])


# ─────────────────────────────────────────
# NOTIFICACIONES
# ─────────────────────────────────────────

class Notificacion(Base):
    __tablename__ = "Notificaciones"

    ID_Notificacion = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Tipo            = Column(String(30))
    Titulo          = Column(String(100))
    Mensaje         = Column(Text, nullable=True)
    Referencia_ID   = Column(Integer, nullable=True)
    Ruta            = Column(String(200), nullable=True)
    Fecha           = Column(DateTime)
    Leida           = Column(Boolean, default=False)
    # El admin la sacó del panel. No se borra la fila: las de stock hay que
    # recordarlas para no volver a crearlas mientras el problema sea el mismo.
    Descartada      = Column(Boolean, default=False, nullable=False)


# ─────────────────────────────────────────
# DESCUENTOS
# ─────────────────────────────────────────

class Descuento(Base):
    __tablename__ = "Descuentos"

    ID_Descuento   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Nombre         = Column(String(100))
    Tipo           = Column(String(20))         # "cupon", "antiguedad", "emision"
    Codigo         = Column(String(50), nullable=True, unique=True)  # solo cupones
    Porcentaje     = Column(Numeric(5, 2))
    Meses_Minimos  = Column(Integer, nullable=True)     # solo antigüedad
    Fecha_Inicio   = Column(DateTime)
    Fecha_Fin      = Column(DateTime, nullable=True)    # null = sin vencimiento
    Usos_Max       = Column(Integer, nullable=True)     # null = ilimitado
    Usos_Actuales  = Column(Integer, default=0)
    Estado         = Column(Integer, ForeignKey("Estados.ID_Estados"))

    asignaciones   = relationship("DescuentoXUsuario", back_populates="descuento")
    ventas         = relationship("DescuentoXVenta", back_populates="descuento")


class DescuentoXUsuario(Base):
    """Tabla de ruptura para descuentos de emisión asignados a usuarios específicos."""
    __tablename__ = "Descuento_x_Usuario"

    ID_Descuento      = Column(Integer, ForeignKey("Descuentos.ID_Descuento"), primary_key=True)
    ID_Usuario        = Column(Integer, ForeignKey("Usuarios.ID_Usuario"), primary_key=True)
    Usado             = Column(Boolean, default=False)
    Fecha_Asignacion  = Column(DateTime)

    descuento = relationship("Descuento", back_populates="asignaciones")
    usuario   = relationship("Usuario", foreign_keys=[ID_Usuario])


class DescuentoXVenta(Base):
    """Registra qué descuento se aplicó en cada venta y cuánto."""
    __tablename__ = "Descuento_x_Venta"

    ID_Venta        = Column(Integer, ForeignKey("Ventas.ID_Venta"), primary_key=True)
    ID_Descuento    = Column(Integer, ForeignKey("Descuentos.ID_Descuento"), primary_key=True)
    Monto_Aplicado  = Column(Numeric(30, 2))

    descuento = relationship("Descuento", back_populates="ventas")
    venta     = relationship("Venta", foreign_keys=[ID_Venta])


# ─────────────────────────────────────────
# UBICACIONES — Departamento → Ciudad → Barrio + ofertas de domicilio
# ─────────────────────────────────────────
# El precio del domicilio de un pedido sale de Barrios.Precio ajustado por las
# ofertas activas del barrio ese día, y se CONGELA como snapshot en Domicilios
# al confirmar el pedido. Reemplaza la constante COSTO_DOMICILIO = 5000.
#
# Estado en cascada: cada nodo tiene su Estado propio; el "estado efectivo"
# (disponible para domicilio) = Estado propio activo Y todos los ancestros
# activos. Desactivar un padre NO toca el Estado propio de los hijos.

class Departamento(Base):
    __tablename__ = "Departamentos"

    ID_Departamento = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Nombre          = Column(String(80), nullable=False)
    Estado          = Column(Integer, ForeignKey("Estados.ID_Estados"), nullable=False, default=1)

    ciudades = relationship("Ciudad", back_populates="departamento")


class Ciudad(Base):
    __tablename__ = "Ciudades"

    ID_Ciudad       = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Departamento = Column(Integer, ForeignKey("Departamentos.ID_Departamento"), nullable=False)
    Nombre          = Column(String(120), nullable=False)
    Estado          = Column(Integer, ForeignKey("Estados.ID_Estados"), nullable=False, default=1)

    departamento = relationship("Departamento", back_populates="ciudades")
    barrios      = relationship("Barrio", back_populates="ciudad")


class Barrio(Base):
    __tablename__ = "Barrios"

    ID_Barrio = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ID_Ciudad = Column(Integer, ForeignKey("Ciudades.ID_Ciudad"), nullable=False)
    Nombre    = Column(String(35), nullable=False)
    Precio    = Column(Integer, nullable=False, default=0)     # entero COP, >= 0, <= 9_999_999
    # 1 = sembrado (quemado): inmutable salvo Precio y Estado, no se puede eliminar.
    # 0 = creado desde el módulo: nombre y precio editables, eliminable si no lo referencia nada.
    Es_Base   = Column(Boolean, nullable=False, default=False)
    Estado    = Column(Integer, ForeignKey("Estados.ID_Estados"), nullable=False, default=1)

    ciudad  = relationship("Ciudad", back_populates="barrios")
    ofertas = relationship("OfertaXBarrio", back_populates="barrio")


class OfertaDomicilio(Base):
    __tablename__ = "Ofertas_Domicilio"

    ID_Oferta      = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Nombre         = Column(String(80), nullable=False)
    # 'descuento' baja el precio del domicilio; 'recargo' lo sube. Monto_Pesos y
    # Porcentaje se guardan SIEMPRE >= 0: el Tipo decide el signo al calcular.
    Tipo           = Column(String(10), nullable=False, default="descuento")
    Monto_Pesos    = Column(Integer, nullable=True)   # >= 0, <= 9_999_999; NULL = no aplica
    Porcentaje     = Column(Integer, nullable=True)   # 0..100; NULL = no aplica
    # CSV de enteros. Dias_Semana: ISO (Lunes=1 … Domingo=7). Dias_Mes: 1..31.
    # Si hay ambos, la oferta aplica cuando coincide CUALQUIERA (OR).
    Dias_Semana    = Column(String(20), nullable=True)
    Dias_Mes       = Column(String(120), nullable=True)
    Estado         = Column(Integer, ForeignKey("Estados.ID_Estados"), nullable=False, default=1)
    Fecha_Creacion = Column(DateTime, nullable=True)

    barrios = relationship("OfertaXBarrio", back_populates="oferta", cascade="all, delete-orphan")


class OfertaXBarrio(Base):
    __tablename__ = "Oferta_x_Barrio"

    ID_Oferta = Column(Integer, ForeignKey("Ofertas_Domicilio.ID_Oferta"), primary_key=True)
    ID_Barrio = Column(Integer, ForeignKey("Barrios.ID_Barrio"), primary_key=True)

    oferta = relationship("OfertaDomicilio", back_populates="barrios")
    barrio = relationship("Barrio", back_populates="ofertas")


# ─────────────────────────────────────────
# RECUPERACIÓN DE CONTRASEÑA
# ─────────────────────────────────────────

class CodigoReset(Base):
    __tablename__ = "Codigos_Reset"

    ID_Codigo = Column(Integer, primary_key=True, index=True, autoincrement=True)
    Correo    = Column(String(255), index=True)
    Codigo    = Column(String(6))
    Expira_En = Column(DateTime)
    Usado     = Column(Boolean, default=False)