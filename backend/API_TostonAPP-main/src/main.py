import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_log = logging.getLogger(__name__)

# ── Auth ──
from src.features.auth.services.router import router as auth_router

# ── Configuración ──
from src.features.configuracion.usuarios.services.router           import router as usuarios_router
from src.features.configuracion.roles.services.router              import router as roles_router
from src.features.configuracion.notificaciones.services.router     import router as notificaciones_router
from src.features.configuracion.salidas.services.router            import router as salidas_router
from src.features.configuracion.control_acceso.services.router     import router as control_acceso_router
from src.features.configuracion.landing.services.router            import router as landing_router

# ── Compras ──
from src.features.compras.insumos.services.router           import router as insumos_router
from src.features.compras.categoria_insumos.services.router import router as cat_insumos_router
from src.features.compras.proveedores.services.router       import router as proveedores_router
from src.features.compras.compras.services.router           import router as compras_router

# ── Producción ──
from src.features.produccion.productos.services.router           import router as productos_router
from src.features.produccion.categoria_productos.services.router import router as cat_productos_router
from src.features.produccion.ordenes_produccion.services.router  import router as ordenes_router

# ── Ventas ──
from src.features.ventas.clientes.services.router       import router as clientes_router
from src.features.ventas.pedidos.services.router        import router as pedidos_router
from src.features.ventas.gestion_ventas.services.router import router as ventas_router
from src.features.ventas.devoluciones.services.router   import router as devoluciones_router
from src.features.ventas.domicilios.services.router     import router as domicilios_router
from src.features.ventas.ubicaciones.services.router    import router as ubicaciones_router

# ── Dashboard ──
from src.features.dashboard.services.router import router as dashboard_router



app = FastAPI(
    title="API Proyecto",
    version="1.0.0",
    description="API para gestión de producción y ventas"
)


@app.on_event("startup")
def migrate_db():
    """Agrega columnas nuevas y tablas si no existen (migraciones manuales)."""
    from sqlalchemy import text
    from src.shared.services.database import engine
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE Orden_Produccion ADD COLUMN ID_Venta INT NULL",
            "ALTER TABLE Orden_Produccion MODIFY COLUMN ID_Insumo INT NULL",
            "ALTER TABLE Orden_Produccion MODIFY COLUMN ID_Ficha  INT NULL",
            "ALTER TABLE Ficha_Tecnica ADD COLUMN Dias_Vida_Util INT NULL",
            "ALTER TABLE Compras ADD COLUMN Fecha_Llegada DATETIME NULL",
            "ALTER TABLE Compras ADD COLUMN Fecha_Anulada DATETIME NULL",
            """CREATE TABLE IF NOT EXISTS Ficha_Tecnica_Insumo (
                ID_Ficha_Insumo INT AUTO_INCREMENT PRIMARY KEY,
                ID_Ficha        INT NOT NULL,
                ID_Insumo       INT NOT NULL,
                Cantidad        DECIMAL(10,2),
                Unidad          VARCHAR(50),
                FOREIGN KEY (ID_Ficha)  REFERENCES Ficha_Tecnica(ID_Ficha),
                FOREIGN KEY (ID_Insumo) REFERENCES Insumos(ID_Insumo)
            )""",
            "ALTER TABLE Productos ADD COLUMN Fecha_Creacion DATETIME NULL",
            "ALTER TABLE Compras ADD COLUMN Notas TEXT NULL",
            "ALTER TABLE Compras ADD COLUMN Comprobante VARCHAR(500) NULL",
            "ALTER TABLE Compras ADD COLUMN Costo_Transporte DECIMAL(30,2) NULL",
            "ALTER TABLE Compras ADD COLUMN IVA_Porcentaje DECIMAL(5,2) NULL",
            "ALTER TABLE Compras ADD COLUMN Descuento_Porcentaje DECIMAL(5,2) NULL",
            "ALTER TABLE Compras ADD COLUMN Otros_Costos DECIMAL(30,2) NULL",
            # Pago mixto: cuánto del pedido va en efectivo y cuánto por transferencia
            "ALTER TABLE Ventas ADD COLUMN Monto_Efectivo DECIMAL(30,2) NULL",
            "ALTER TABLE Ventas ADD COLUMN Monto_Transferencia DECIMAL(30,2) NULL",
            # La auditoría del cobro en efectivo se escribía dentro de
            # Domicilios.Observaciones, que es texto que lee el cliente: las
            # indicaciones de entrega terminaban mezcladas con líneas
            # [COBRO|...]. Ahora tiene su propio campo.
            "ALTER TABLE Domicilios ADD COLUMN Cobro_Auditoria TEXT NULL",
            # Y se limpia de una vez lo que quedó guardado antes, para que
            # no dependa de que todas las lecturas acuerden filtrarlo.
            # REGEXP_REPLACE es de MySQL 8; si el motor es más viejo esta
            # sentencia se salta y el filtro de lectura sigue cubriendo.
            r"""UPDATE Domicilios
               SET Observaciones = NULLIF(TRIM(
                     REGEXP_REPLACE(Observaciones, '\\n?\\[COBRO\\|[^]]*\\]', '')
                   ), '')
               WHERE Observaciones LIKE '%[COBRO|%'""",
            """CREATE TABLE IF NOT EXISTS Lote_Producto (
                ID_Lote_Producto    INT AUTO_INCREMENT PRIMARY KEY,
                ID_Orden_Produccion INT,
                ID_Producto         INT,
                Numero_Lote         VARCHAR(50),
                Fecha_Produccion    DATETIME,
                Fecha_Vencimiento   DATETIME,
                Cantidad            INT,
                Estado              INT DEFAULT 1,
                FOREIGN KEY (ID_Orden_Produccion) REFERENCES Orden_Produccion(ID_Orden_Produccion),
                FOREIGN KEY (ID_Producto)         REFERENCES Productos(ID_Producto),
                FOREIGN KEY (Estado)              REFERENCES Estados(ID_Estados)
            )""",
            """CREATE TABLE IF NOT EXISTS Codigos_Reset (
                ID_Codigo INT AUTO_INCREMENT PRIMARY KEY,
                Correo    VARCHAR(255),
                Codigo    VARCHAR(6),
                Expira_En DATETIME,
                Usado     TINYINT(1) DEFAULT 0
            )""",
            "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) VALUES (10, 10, 'Asignado')",
            "ALTER TABLE Devoluciones ADD COLUMN Comprobante_Imagen LONGTEXT NULL",
            # Columna agregada al modelo Venta; sin esta migración todo SELECT a
            # Ventas falla con 500 (mis-ventas, crear-venta, etc.)
            "ALTER TABLE Ventas ADD COLUMN Fecha_entrega_esperada DATETIME NULL",
            # Activa los clientes que quedaron bloqueados en Estado=2 (verificación
            # de correo) antes de eliminar el bloqueo de registro. ID_Rol=3 = Cliente.
            "UPDATE Usuarios SET Estado = 1 WHERE Estado = 2 AND ID_Rol = 3",
            # Indicaciones de entrega del cliente (referencia/punto de entrega),
            # opcional. Se muestra y edita en "Mis datos".
            "ALTER TABLE Usuarios ADD COLUMN Indicaciones VARCHAR(255) NULL",
            # FCM tokens persistidos en BD para sobrevivir reinicios de Render
            "ALTER TABLE Usuarios ADD COLUMN FCM_Token VARCHAR(300) NULL",
            # Código de entrega, ya fuera de uso. Las columnas se siguen creando
            # para que una base nueva calce con el modelo.
            "ALTER TABLE Domicilios ADD COLUMN OTP VARCHAR(10) NULL",
            "ALTER TABLE Domicilios ADD COLUMN OTP_Expira DATETIME NULL",
            # Pedidos por encima del stock (preorden): marca, anticipo del 50%
            # exigido y anticipo efectivamente cubierto. Los calcula el backend.
            "ALTER TABLE Ventas ADD COLUMN Sobre_Stock TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE Ventas ADD COLUMN Anticipo_Requerido DECIMAL(30,2) NULL",
            "ALTER TABLE Ventas ADD COLUMN Anticipo_Pagado DECIMAL(30,2) NULL",
            # Anticipo del 50% por total > $50.000 (regla general de negocio)
            "ALTER TABLE Ventas ADD COLUMN Requiere_Anticipo TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE Ventas ADD COLUMN Anticipo_Monto DECIMAL(30,2) NULL",
            "ALTER TABLE Ventas ADD COLUMN Anticipo_Metodo_Pago VARCHAR(30) NULL",
            "ALTER TABLE Ventas ADD COLUMN Anticipo_Comprobante_Url VARCHAR(500) NULL",
            "ALTER TABLE Ventas ADD COLUMN Anticipo_Registrado TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE Ventas ADD COLUMN Pago_Final_Registrado TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE Ventas ADD COLUMN Estado_Pago VARCHAR(30) NULL DEFAULT 'pendiente'",
            # Unidades de cada línea que van por encima del stock (preorden)
            "ALTER TABLE Venta_x_Producto ADD COLUMN Cantidad_Preorden INT NOT NULL DEFAULT 0",
            # Fecha en que se registró la orden de producción (automática, solo lectura).
            # Backfill: las órdenes previas heredan su Fecha_inicio como aproximación.
            "ALTER TABLE Orden_Produccion ADD COLUMN Fecha_Creacion DATETIME NULL",
            "UPDATE Orden_Produccion SET Fecha_Creacion = Fecha_inicio WHERE Fecha_Creacion IS NULL",
            # Landing: punto exacto del local en el mapa + horario de atención
            # estructurado (gobierna el aviso de "fuera de horario").
            "ALTER TABLE Configuracion_Landing ADD COLUMN map_lat DECIMAL(10,7) NULL",
            "ALTER TABLE Configuracion_Landing ADD COLUMN map_lng DECIMAL(10,7) NULL",
            "ALTER TABLE Configuracion_Landing ADD COLUMN hora_apertura VARCHAR(5) NULL",
            "ALTER TABLE Configuracion_Landing ADD COLUMN hora_cierre VARCHAR(5) NULL",
            "ALTER TABLE Configuracion_Landing ADD COLUMN dias_atencion VARCHAR(20) NULL",
            # Monto mínimo de compra para habilitar domicilio (0 = sin mínimo).
            "ALTER TABLE Configuracion_Landing ADD COLUMN pedido_minimo INT NULL DEFAULT 0",
            # Marca que el propio cliente eliminó su cuenta (para distinguirla de
            # una desactivada por un admin y poder recuperarla).
            "ALTER TABLE Usuarios ADD COLUMN Auto_Eliminado TINYINT(1) NOT NULL DEFAULT 0",
            # Domicilios fantasma de pedidos ya divididos: la fila original
            # (sin grupo) dejó de ser un viaje cuando cada grupo hizo el suyo,
            # pero las divididas antes del arreglo quedaron Pendientes y sin
            # repartidor, ofreciéndose en el tablero para asignar. Se cierran;
            # la fila se conserva porque de ella salen la dirección que
            # heredaron los grupos y el precio que se descontó del total.
            """UPDATE Domicilios d
               JOIN (SELECT DISTINCT ID_Venta FROM Domicilios
                      WHERE ID_Grupo IS NOT NULL) g ON g.ID_Venta = d.ID_Venta
                SET d.Estado = 5, d.ID_Empleado = NULL
              WHERE d.ID_Grupo IS NULL AND d.Estado NOT IN (5, 8)""",
            # Chat de domicilios persistido en BD (antes se perdía en cada reinicio)
            """CREATE TABLE IF NOT EXISTS MensajesChat (
                ID_Mensaje       INT AUTO_INCREMENT PRIMARY KEY,
                ID_Domicilio     INT NOT NULL,
                Tipo_Remitente   VARCHAR(20),
                ID_Remitente     INT,
                Nombre_Remitente VARCHAR(100),
                Contenido        TEXT,
                Fecha            DATETIME,
                FOREIGN KEY (ID_Domicilio) REFERENCES Domicilios(ID_Domicilio)
            )""",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as exc:
                _log.debug("migrate skip (ya existe): %.80s", exc)

    # ── Pago_Final: columnas para registrar el cobro del saldo al entregar ──────
    # Se verifica columna a columna en information_schema antes de alterar;
    # así el ALTER siempre es válido y los errores reales se logean — no se silencian.
    _PAGO_FINAL_COLS = [
        ("Pago_Final_Monto",           "DECIMAL(30,2) NULL"),
        ("Pago_Final_Metodo_Pago",     "VARCHAR(30)   NULL"),
        ("Pago_Final_Comprobante_Url", "VARCHAR(500)  NULL"),
        ("Pago_Final_Fecha",           "DATETIME      NULL"),
    ]
    with engine.connect() as conn:
        faltan = []
        for col_name, col_def in _PAGO_FINAL_COLS:
            existe = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME   = 'Ventas' "
                "  AND COLUMN_NAME  = :col"
            ), {"col": col_name}).scalar()
            if not existe:
                faltan.append(f"ADD COLUMN {col_name} {col_def}")
        if not faltan:
            _log.info("migración pago_final: ya aplicada, sin cambios")
        else:
            alter_sql = "ALTER TABLE Ventas\n  " + ",\n  ".join(faltan)
            try:
                conn.execute(text(alter_sql))
                conn.commit()
                _log.info("migración pago_final: %d columna(s) creada(s): %s",
                          len(faltan), [f.split()[2] for f in faltan])
            except Exception as exc:
                _log.error("migración pago_final FALLÓ — %s", exc, exc_info=True)

    # ── Necesita_Produccion: flag guardado al crear la venta (stock snapshot) ───
    # Evita que el cálculo dinámico de requiere_fecha_propuesta sea incorrecto
    # cuando el stock cambia después de que el pedido fue creado.
    with engine.connect() as conn:
        existe = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "  AND TABLE_NAME   = 'Ventas' "
            "  AND COLUMN_NAME  = 'Necesita_Produccion'"
        )).scalar()
        if not existe:
            try:
                conn.execute(text(
                    "ALTER TABLE Ventas ADD COLUMN Necesita_Produccion TINYINT(1) NOT NULL DEFAULT 0"
                ))
                conn.commit()
                _log.info("migración necesita_produccion: columna creada")
            except Exception as exc:
                _log.error("migración necesita_produccion FALLÓ — %s", exc, exc_info=True)
        else:
            _log.info("migración necesita_produccion: ya existe, sin cambios")

    # Migrar FK de Domicilios.ID_Empleado: Empleados → Usuarios
    # El código usa Usuarios.ID_Usuario pero la DB de producción aún apunta a Empleados
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE Domicilios DROP FOREIGN KEY Domicilios_ibfk_2"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text(
                "ALTER TABLE Domicilios ADD CONSTRAINT Domicilios_ibfk_2 "
                "FOREIGN KEY (ID_Empleado) REFERENCES Usuarios(ID_Usuario)"
            ))
            conn.commit()
        except Exception:
            pass

    # Correo_Verificado: columna separada de Estado para distinguir "verificó su
    # correo" de "cuenta activa". Se agrega con default 0; los usuarios que YA
    # existían (creados antes de esta función) se marcan como verificados=1 para
    # no bloquearles la recuperación de contraseña. Solo se hace el backfill la
    # primera vez (cuando el ALTER tiene éxito); en arranques posteriores el ALTER
    # falla porque la columna ya existe y se omite el UPDATE.
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE Usuarios ADD COLUMN Correo_Verificado TINYINT NOT NULL DEFAULT 0"))
            conn.commit()
            conn.execute(text("UPDATE Usuarios SET Correo_Verificado = 1"))
            conn.commit()
        except Exception:
            pass  # la columna ya existe; no re-hacer el backfill

    # Comprobante_Pago: LONGTEXT para soportar imágenes en base64
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE Ventas ADD COLUMN Comprobante_Pago LONGTEXT NULL"))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
                conn.execute(text("ALTER TABLE Ventas MODIFY COLUMN Comprobante_Pago LONGTEXT NULL"))
                conn.commit()
            except Exception:
                pass

    # Ventas.Fecha_entrega: timestamp real de entrega (fuente para el plazo de
    # devoluciones de 36h, también en pedidos de recoger en tienda). No se
    # rellenan filas existentes: el cálculo usa Domicilios.Fecha_entrega para
    # pedidos con domicilio y hace fallback a Fecha_pedido para los antiguos.
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE Ventas ADD COLUMN Fecha_entrega DATETIME NULL"))
            conn.commit()
        except Exception:
            pass  # la columna ya existe


    # Corrección de lotes huérfanos: lotes con Estado=1 que pertenecen a compras Pendientes
    # (creados antes de que el flujo fuera corregido para usar Estado=3)
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                UPDATE Lote_Compra lc
                JOIN Detalle_Compra dc ON dc.ID_Lote_Compra = lc.ID_Lote_Compra
                JOIN Compras c ON c.ID_Compra = dc.ID_Compra
                SET lc.Estado = 3
                WHERE lc.Estado = 1
                  AND c.Estado = 3
            """))
            conn.commit()
        except Exception:
            pass

    # ── Estados de negociación de fecha ─────────────────────────────────────────
    # 16 = Fecha de entrega propuesta (puede existir ya en BD; INSERT IGNORE es seguro)
    # 17 = Fecha rechazada (cliente rechazó; admin propone de nuevo)
    # 18 = Parcialmente entregado (grupo A entregado, grupo B pendiente)
    # 19 = Escalado a admin (demasiados rechazos; admin gestiona manualmente)
    with engine.connect() as conn:
        for stmt in [
            "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) VALUES (16, 16, 'Fecha de entrega propuesta')",
            "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) VALUES (17, 17, 'Fecha rechazada')",
            "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) VALUES (18, 18, 'Parcialmente entregado')",
            "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) VALUES (19, 19, 'Escalado a admin')",
            # 20 = Esperando pago (fecha aprobada, o pedido sin producción, en
            # espera del comprobante/anticipo antes de pasar a producción/alistamiento)
            "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) VALUES (20, 20, 'Esperando pago')",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as exc:
                _log.error("migración estados 16-20 FALLÓ — %s", exc, exc_info=True)

    # ── Columna intentos_rechazo en Ventas ────────────────────────────────────
    with engine.connect() as conn:
        try:
            existe = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME   = 'Ventas'
                  AND COLUMN_NAME  = 'intentos_rechazo'
            """)).scalar()
            if not existe:
                conn.execute(text(
                    "ALTER TABLE Ventas ADD COLUMN intentos_rechazo INT NOT NULL DEFAULT 0"
                ))
                conn.commit()
                _log.info("migración intentos_rechazo: columna creada en Ventas")
            else:
                _log.debug("migración intentos_rechazo: columna ya existe, sin cambios")
        except Exception as exc:
            _log.error("migración intentos_rechazo FALLÓ — %s", exc, exc_info=True)

    # ── Columna Descartada en Notificaciones ──────────────────────────────────
    with engine.connect() as conn:
        try:
            existe = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME   = 'Notificaciones'
                  AND COLUMN_NAME  = 'Descartada'
            """)).scalar()
            if not existe:
                conn.execute(text(
                    "ALTER TABLE Notificaciones "
                    "ADD COLUMN Descartada BOOLEAN NOT NULL DEFAULT 0"
                ))
                conn.commit()
                _log.info("migración Descartada: columna creada en Notificaciones")
            else:
                _log.debug("migración Descartada: columna ya existe, sin cambios")
        except Exception as exc:
            _log.error("migración Descartada FALLÓ — %s", exc, exc_info=True)

    # ── Tabla de historial de fechas propuestas ───────────────────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS Historial_Fechas_Propuestas (
                    ID_Historial    INT AUTO_INCREMENT PRIMARY KEY,
                    ID_Venta        INT NOT NULL,
                    ID_Usuario      INT NULL,
                    Fecha_Propuesta DATETIME NULL,
                    Fecha_Accion    DATETIME NOT NULL,
                    Tipo_Accion     VARCHAR(20) NOT NULL,
                    Motivo_Rechazo  TEXT NULL,
                    FOREIGN KEY (ID_Venta)   REFERENCES Ventas(ID_Venta),
                    FOREIGN KEY (ID_Usuario) REFERENCES Usuarios(ID_Usuario)
                )
            """))
            conn.commit()
            _log.info("migración Historial_Fechas_Propuestas: tabla creada o ya existia")
        except Exception as exc:
            _log.error("migración Historial_Fechas_Propuestas FALLÓ — %s", exc, exc_info=True)

    # ── Columna Envio_Completo_Domingo en Ventas ─────────────────────────────
    with engine.connect() as conn:
        try:
            existe = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND TABLE_NAME   = 'Ventas' "
                "  AND COLUMN_NAME  = 'Envio_Completo_Domingo'"
            )).scalar()
            if not existe:
                conn.execute(text(
                    "ALTER TABLE Ventas ADD COLUMN Envio_Completo_Domingo TINYINT NULL"
                ))
                conn.commit()
                _log.info("migración Envio_Completo_Domingo: columna creada en Ventas")
            else:
                _log.debug("migración Envio_Completo_Domingo: ya existe, sin cambios")
        except Exception as exc:
            _log.error("migración Envio_Completo_Domingo FALLÓ — %s", exc, exc_info=True)

    # ── Refactor del catálogo de permisos ─────────────────────────────────────
    # Renombres, fusión de "ventas" en "pedidos", retiro de permisos sin uso y
    # migración de los endpoints que usaban un permiso "proxy" de otro módulo a
    # su permiso propio. Cada rol conserva el acceso que ya tenía.
    _migrar_catalogo_permisos(engine)

    # ── Permisos del rol "Empleado" ───────────────────────────────────────────
    # El empleado puede CREAR y VER pedidos (con selección de cliente) y VER
    # devoluciones, pero NO confirmar/cancelar pedidos ni aprobar/rechazar
    # devoluciones (esas acciones requieren editar_pedidos / editar_devoluciones).
    with engine.connect() as conn:
        # Otorgar permisos necesarios (idempotente)
        try:
            conn.execute(text("""
                INSERT IGNORE INTO Rol_x_Permiso (ID_Rol, ID_Permiso)
                SELECT r.ID_Rol, p.ID_Permiso
                FROM Roles r
                JOIN Permisos p
                  ON p.Permiso IN (
                       'ver_pedidos', 'crear_pedidos',
                       'ver_usuarios', 'ver_devoluciones'
                     )
                WHERE LOWER(TRIM(r.Rol)) = 'empleado'
            """))
            conn.commit()
        except Exception:
            pass
        # Revocar acciones que el empleado NO debe tener
        try:
            conn.execute(text("""
                DELETE rxp FROM Rol_x_Permiso rxp
                JOIN Roles r     ON r.ID_Rol     = rxp.ID_Rol
                JOIN Permisos p  ON p.ID_Permiso = rxp.ID_Permiso
                WHERE LOWER(TRIM(r.Rol)) = 'empleado'
                  AND p.Permiso IN ('editar_pedidos', 'editar_devoluciones')
            """))
            conn.commit()
        except Exception:
            pass

    # ── Rol "Cliente": estático y SIN permisos ──────────────────────────────
    # El rol Cliente (ID_Rol = 3) no lleva permisos en Rol_x_Permiso. Todo lo
    # que un cliente puede hacer se decide por su ID_Rol actual:
    #   - confirmar / crear pedidos  → dependencies.permiso_o_cliente()
    #   - mis-ventas, mis-devoluciones, cancelar pedido propio, perfil, crédito
    #     → obtener_usuario_actual (sin requiere_permiso)
    # Este DELETE deja el rol limpio en cada arranque (idempotente).
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                DELETE rxp FROM Rol_x_Permiso rxp
                JOIN Roles r ON r.ID_Rol = rxp.ID_Rol
                WHERE r.ID_Rol = 3 OR LOWER(TRIM(r.Rol)) = 'cliente'
            """))
            conn.commit()
        except Exception:
            pass

    # ── Configuración de Landing Page ─────────────────────────────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS Configuracion_Landing (
                    ID                       INT AUTO_INCREMENT PRIMARY KEY,
                    hero_badge               VARCHAR(200)  NULL,
                    hero_title               VARCHAR(200)  NULL,
                    hero_description         TEXT          NULL,
                    history_title            VARCHAR(200)  NULL,
                    history_description      TEXT          NULL,
                    cta_title                VARCHAR(200)  NULL,
                    cta_description          TEXT          NULL,
                    contact_phone1           VARCHAR(50)   NULL,
                    contact_phone2           VARCHAR(50)   NULL,
                    contact_address_line     VARCHAR(200)  NULL,
                    contact_city             VARCHAR(200)  NULL,
                    contact_instagram_url    VARCHAR(500)  NULL,
                    contact_instagram_handle VARCHAR(100)  NULL,
                    horario_lunes_viernes    VARCHAR(100)  NULL,
                    horario_sabado           VARCHAR(100)  NULL
                )
            """))
            conn.commit()
            # Garantizar que exista la fila singleton (ID=1) con defaults
            conn.execute(text("""
                INSERT INTO Configuracion_Landing (
                    ID, hero_badge, hero_title, hero_description,
                    history_title, history_description,
                    cta_title, cta_description,
                    contact_phone1, contact_phone2,
                    contact_address_line, contact_city,
                    contact_instagram_url, contact_instagram_handle,
                    horario_lunes_viernes, horario_sabado
                ) VALUES (
                    1,
                    'SABOR NATURAL 100%',
                    'El poder del Plátano',
                    'Descubre tostones, chips y delicias artesanales que redefinen el sabor de nuestra tierra. Crujientes, frescos y recolectados con amor.',
                    'Desde el campo hasta tu mesa',
                    'En Tostón App celebramos la tierra. Cada plátano es seleccionado para garantizar una experiencia épica y natural.',
                    'Únete a la Revolución',
                    'Estamos transformando la forma en que el mundo ve al plátano.',
                    '321 754 3305', '313 789 9946',
                    'Carrera 38A No. 80-12', 'Barranquilla, Colombia',
                    'https://www.instagram.com/tostonesbroms?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw==',
                    '@tostonesbroms',
                    '8:00 am – 8:00 pm', '8:00 am – 8:00 pm'
                )
                ON DUPLICATE KEY UPDATE ID = ID
            """))
            conn.commit()
            # Rellenar campos NULL con defaults (para filas ya existentes)
            conn.execute(text("""
                UPDATE Configuracion_Landing SET
                    hero_badge               = COALESCE(hero_badge,               'SABOR NATURAL 100%'),
                    hero_title               = COALESCE(hero_title,               'El poder del Plátano'),
                    hero_description         = COALESCE(hero_description,         'Descubre tostones, chips y delicias artesanales que redefinen el sabor de nuestra tierra. Crujientes, frescos y recolectados con amor.'),
                    history_title            = COALESCE(history_title,            'Desde el campo hasta tu mesa'),
                    history_description      = COALESCE(history_description,      'En Tostón App celebramos la tierra. Cada plátano es seleccionado para garantizar una experiencia épica y natural.'),
                    cta_title                = COALESCE(cta_title,                'Únete a la Revolución'),
                    cta_description          = COALESCE(cta_description,          'Estamos transformando la forma en que el mundo ve al plátano.'),
                    contact_phone1           = COALESCE(contact_phone1,           '321 754 3305'),
                    contact_phone2           = COALESCE(contact_phone2,           '313 789 9946'),
                    contact_address_line     = COALESCE(contact_address_line,     'Carrera 38A No. 80-12'),
                    contact_city             = COALESCE(contact_city,             'Barranquilla, Colombia'),
                    contact_instagram_url    = COALESCE(contact_instagram_url,    'https://www.instagram.com/tostonesbroms?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw=='),
                    contact_instagram_handle = COALESCE(contact_instagram_handle, '@tostonesbroms'),
                    horario_lunes_viernes    = COALESCE(horario_lunes_viernes,    '8:00 am – 8:00 pm'),
                    horario_sabado           = COALESCE(horario_sabado,           '8:00 am – 8:00 pm')
                WHERE ID = 1
            """))
            conn.commit()
            _log.info("migración Configuracion_Landing: lista")
        except Exception as exc:
            _log.debug("migración Configuracion_Landing skip: %.80s", exc)

    # ── Vida_Util_Unidad: columna que acompaña a Dias_Vida_Util ─────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE Ficha_Tecnica ADD COLUMN Vida_Util_Unidad VARCHAR(10) NULL"
            ))
            conn.commit()
            _log.info("migración Vida_Util_Unidad: columna creada")
        except Exception:
            pass  # ya existe

    # ── Fecha_Produccion en Lote_Producto (puede faltar en tablas viejas) ────────
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE Lote_Producto ADD COLUMN Fecha_Produccion DATETIME NULL"
            ))
            conn.commit()
            _log.info("migración Lote_Producto.Fecha_Produccion: columna creada")
        except Exception:
            pass  # ya existe

    # ── Backfill Fecha_Vencimiento en lotes ya creados ──────────────────────────
    # Los lotes creados antes de que se configurara Dias_Vida_Util tienen
    # Fecha_Vencimiento = NULL. Se calcula desde Fecha_Produccion del lote,
    # o desde Fecha_fin de la orden como respaldo cuando Fecha_Produccion es NULL.
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                UPDATE Lote_Producto lp
                JOIN Orden_Produccion op ON op.ID_Orden_Produccion = lp.ID_Orden_Produccion
                JOIN Ficha_Tecnica ft    ON ft.ID_Ficha             = op.ID_Ficha
                SET lp.Fecha_Produccion  = COALESCE(lp.Fecha_Produccion, op.Fecha_fin),
                    lp.Fecha_Vencimiento = CASE
                        WHEN ft.Vida_Util_Unidad = 'meses'
                            THEN DATE_ADD(COALESCE(lp.Fecha_Produccion, op.Fecha_fin), INTERVAL ft.Dias_Vida_Util MONTH)
                        WHEN ft.Vida_Util_Unidad = 'semanas'
                            THEN DATE_ADD(COALESCE(lp.Fecha_Produccion, op.Fecha_fin), INTERVAL ft.Dias_Vida_Util WEEK)
                        ELSE
                            DATE_ADD(COALESCE(lp.Fecha_Produccion, op.Fecha_fin), INTERVAL ft.Dias_Vida_Util DAY)
                    END
                WHERE lp.Fecha_Vencimiento IS NULL
                  AND ft.Dias_Vida_Util IS NOT NULL
                  AND COALESCE(lp.Fecha_Produccion, op.Fecha_fin) IS NOT NULL
            """))
            conn.commit()
            _log.info("migración backfill Fecha_Vencimiento lotes: ok")
        except Exception as exc:
            _log.debug("migración backfill Fecha_Vencimiento skip: %.80s", exc)

    # ── Módulo Ubicaciones: ampliar columna Permisos.Permiso ─────────────────
    # cambiar_estado_ubicaciones tiene 26 chars; si la columna es VARCHAR(50) no cabe.
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE Permisos MODIFY COLUMN Permiso VARCHAR(60) NOT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # ya tiene el ancho correcto o mayor

    # ── Módulo Ubicaciones: tablas de jerarquía y ofertas ────────────────────
    with engine.connect() as conn:
        for stmt in [
            """CREATE TABLE IF NOT EXISTS Departamentos (
                ID_Departamento INT AUTO_INCREMENT PRIMARY KEY,
                Nombre          VARCHAR(80) NOT NULL,
                Estado          INT NOT NULL DEFAULT 1,
                FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados)
            )""",
            """CREATE TABLE IF NOT EXISTS Ciudades (
                ID_Ciudad       INT AUTO_INCREMENT PRIMARY KEY,
                ID_Departamento INT NOT NULL,
                Nombre          VARCHAR(120) NOT NULL,
                Estado          INT NOT NULL DEFAULT 1,
                FOREIGN KEY (ID_Departamento) REFERENCES Departamentos(ID_Departamento),
                FOREIGN KEY (Estado)          REFERENCES Estados(ID_Estados)
            )""",
            """CREATE TABLE IF NOT EXISTS Barrios (
                ID_Barrio INT AUTO_INCREMENT PRIMARY KEY,
                ID_Ciudad INT NOT NULL,
                Nombre    VARCHAR(35) NOT NULL,
                Precio    INT NOT NULL DEFAULT 0,
                Es_Base   TINYINT(1) NOT NULL DEFAULT 0,
                Estado    INT NOT NULL DEFAULT 1,
                FOREIGN KEY (ID_Ciudad) REFERENCES Ciudades(ID_Ciudad),
                FOREIGN KEY (Estado)    REFERENCES Estados(ID_Estados)
            )""",
            """CREATE TABLE IF NOT EXISTS Ofertas_Domicilio (
                ID_Oferta      INT AUTO_INCREMENT PRIMARY KEY,
                Nombre         VARCHAR(80) NOT NULL,
                Tipo           VARCHAR(10) NOT NULL DEFAULT 'descuento',
                Monto_Pesos    INT NULL,
                Porcentaje     INT NULL,
                Dias_Semana    VARCHAR(20) NULL,
                Dias_Mes       VARCHAR(120) NULL,
                Estado         INT NOT NULL DEFAULT 1,
                Fecha_Creacion DATETIME NULL,
                FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados)
            )""",
            """CREATE TABLE IF NOT EXISTS Oferta_x_Barrio (
                ID_Oferta INT NOT NULL,
                ID_Barrio INT NOT NULL,
                PRIMARY KEY (ID_Oferta, ID_Barrio),
                FOREIGN KEY (ID_Oferta) REFERENCES Ofertas_Domicilio(ID_Oferta),
                FOREIGN KEY (ID_Barrio) REFERENCES Barrios(ID_Barrio)
            )""",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # tabla ya existe

    # ── Módulo Ubicaciones: columnas nuevas en tablas existentes ─────────────
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE Usuarios   ADD COLUMN ID_Barrio              INT  NULL",
            "ALTER TABLE Domicilios ADD COLUMN ID_Barrio              INT  NULL",
            "ALTER TABLE Domicilios ADD COLUMN Precio_Domicilio_Base  INT  NULL",
            "ALTER TABLE Domicilios ADD COLUMN Precio_Domicilio_Final INT  NULL",
            "ALTER TABLE Domicilios ADD COLUMN Desglose_Ofertas       JSON NULL",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # columna ya existe

    # ── Comprobante rechazado: guardar motivo visible al cliente ──────────────
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE Ventas ADD COLUMN Motivo_Rechazo_Comprobante TEXT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # columna ya existe

    # ── Nuevas columnas PUNTO 1-7 (flujo completo de pagos y negociación) ─────
    with engine.connect() as conn:
        for stmt in [
            # PUNTO 7: liquidación del efectivo cobrado por el repartidor
            "ALTER TABLE Domicilios ADD COLUMN Efectivo_Liquidado TINYINT NOT NULL DEFAULT 0",
            "ALTER TABLE Domicilios ADD COLUMN Fecha_Liquidacion DATETIME NULL",
            "ALTER TABLE Domicilios ADD COLUMN ID_Liquidado_Por INT NULL",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # columna ya existe

    # ── prompt-pedidos-2: columnas nuevas de Ventas y de la landing ──────────
    # Las declara el modelo, así que SQLAlchemy las nombra en CADA consulta a
    # Ventas. Sin la columna en la base, MySQL contesta 1054 "Unknown column" y
    # el error sale como un 500 en cargar pedidos, crear pedidos y todo lo que
    # toque una venta.
    #
    # En las pruebas no se nota: el arnés crea las tablas desde el modelo, así
    # que las columnas siempre existen y la suite queda verde con la base real
    # rota. Por eso cada columna nueva necesita su línea acá.
    with engine.connect() as conn:
        for stmt in [
            # Rechazos de cada comprobante: el del anticipo y el del saldo.
            "ALTER TABLE Ventas ADD COLUMN Intentos_Rechazo_Comprobante_Anticipo INT NULL DEFAULT 0",
            "ALTER TABLE Ventas ADD COLUMN Intentos_Rechazo_Comprobante_Saldo INT NULL DEFAULT 0",
            # Comprobante del saldo mientras se valida.
            "ALTER TABLE Ventas ADD COLUMN Saldo_Comprobante_Url VARCHAR(500) NULL",
            # Cuándo se retuvo en tienda, para los plazos de reintento.
            "ALTER TABLE Ventas ADD COLUMN Fecha_Retenido_En_Tienda DATETIME NULL",
            # Si ya se reservó el stock de este pedido (evita descontar dos veces).
            "ALTER TABLE Ventas ADD COLUMN Stock_Reservado INT NULL DEFAULT 0",
            # Correo de contacto de la landing.
            "ALTER TABLE Configuracion_Landing ADD COLUMN contact_email VARCHAR(200) NULL",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as exc:
                # Lo normal es que la columna ya exista. Cualquier otra cosa se
                # anota: una migración que falla en silencio deja la API
                # devolviendo 500 sin que nadie sepa por qué.
                if "duplicate column" not in str(exc).lower():
                    _log.error("migración de columna FALLÓ — %s | %s", stmt, exc)

    # ── prompt-pedidos-2: estados 21/22/23 del flujo de pedidos ───────────────
    # El ID 21 lo usó primero una implementación paralela (PUNTO 6, "Retenido
    # en tienda") que quedó reemplazada por el diseño más completo de este
    # prompt (FECHA_PROPUESTA_FINAL=21, RETENIDO_EN_TIENDA=22,
    # EN_RUTA_RETORNO=23, ver estados.py). INSERT IGNORE no pisa una fila que
    # ya exista con la etiqueta vieja, así que el 21 se corrige con UPDATE.
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) "
                "VALUES (21, 21, 'Fecha propuesta final')"
            ))
            conn.execute(text(
                "UPDATE Estados SET Estado = 'Fecha propuesta final', Codigo = 21 "
                "WHERE ID_Estados = 21 AND Estado <> 'Fecha propuesta final'"
            ))
            conn.execute(text(
                "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) "
                "VALUES (22, 22, 'Retenido en tienda')"
            ))
            conn.execute(text(
                "INSERT IGNORE INTO Estados (ID_Estados, Codigo, Estado) "
                "VALUES (23, 23, 'En ruta de retorno')"
            ))
            conn.commit()
        except Exception as exc:
            _log.error("migración estados 21/22/23 FALLÓ — %s", exc, exc_info=True)

    # FK de Domicilios.ID_Liquidado_Por → Usuarios (solo si la columna ya existe)
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE Domicilios ADD CONSTRAINT dom_liquidado_por_fk "
                "FOREIGN KEY (ID_Liquidado_Por) REFERENCES Usuarios(ID_Usuario)"
            ))
            conn.commit()
        except Exception:
            pass  # FK ya existe o columna no fue creada aún


def _migrar_catalogo_permisos(engine):
    """Migración idempotente del catálogo de permisos (ver `migrate_db`)."""
    from sqlalchemy import text
    from src.shared.services.permisos_catalogo import PERMISOS as _CAT

    # Fusiones = el permiso de origen se retira y su acceso pasa al destino.
    #  - Renombre semántico: "eliminar" → "anular"/"cancelar" en módulos operativos.
    #  - "Gestión de Ventas" no existe como módulo: una venta es un pedido
    #    completado; su permiso pasa al equivalente de pedidos.
    fusiones = [
        ("eliminar_ordenes", "anular_ordenes"),
        ("eliminar_pedidos", "cancelar_pedidos"),
        ("ver_ventas",       "ver_pedidos"),
        ("crear_ventas",     "crear_pedidos"),
        ("editar_ventas",    "editar_pedidos"),
    ]
    # 3. Endpoints que pedían un permiso de otro módulo → grant del propio.
    proxies = [
        # "cambiar_estado_usuarios" es nuevo: los roles que ya podían editar
        # usuarios conservan la capacidad de activar/desactivar (antes iba
        # dentro de editar_usuarios).
        ("editar_usuarios", "cambiar_estado_usuarios"),
        ("ver_productos",    "ver_ordenes"),
        ("crear_productos",  "crear_ordenes"),
        ("editar_productos", "editar_ordenes"),
        ("editar_productos", "cambiar_estado_ordenes"),
        ("eliminar_productos", "anular_ordenes"),
        ("ver_productos",    "ver_cat_productos"),
        ("crear_productos",  "crear_cat_productos"),
        ("editar_productos", "editar_cat_productos"),
        ("eliminar_productos", "eliminar_cat_productos"),
        ("ver_insumos",    "ver_compras"),
        ("crear_insumos",  "crear_compras"),
        ("editar_insumos", "editar_compras"),
        ("editar_insumos", "cambiar_estado_compras"),
        ("editar_insumos", "anular_compras"),
        ("ver_insumos",    "ver_cat_insumos"),
        ("crear_insumos",  "crear_cat_insumos"),
        ("editar_insumos", "editar_cat_insumos"),
        ("eliminar_insumos", "eliminar_cat_insumos"),
        ("ver_insumos",    "ver_proveedores"),
        ("crear_insumos",  "crear_proveedores"),
        ("editar_insumos", "editar_proveedores"),
        ("eliminar_insumos", "eliminar_proveedores"),
        ("ver_domicilios", "ver_detalle_domicilios"),
        ("editar_devoluciones", "aprobar_devoluciones"),
        ("editar_pedidos", "cancelar_pedidos"),
        # `cambiar_estado_pedidos` es nuevo (prompt-pedidos-2, 3.14): gobierna
        # las transiciones/aprobaciones del flujo de pedidos, que antes vivían
        # bajo `editar_pedidos`. Todo rol que ya podía editar pedidos conserva
        # esa capacidad sin que se le desaparezca al migrar.
        ("editar_pedidos", "cambiar_estado_pedidos"),
    ]
    obsoletos = ["ver_landing_page"]

    with engine.connect() as conn:
        # Sembrar todo el catálogo (llena los nombres nuevos que falten).
        for nombre, desc, _m, _a in _CAT:
            try:
                conn.execute(text(
                    "INSERT IGNORE INTO Permisos (Permiso, Descripcion) VALUES (:n, :d)"
                ), {"n": nombre, "d": desc})
                conn.commit()
            except Exception:
                conn.rollback()

        # Fusiones y proxies: grant del permiso destino a todo rol que ya tenía
        # el de origen; las fusiones además retiran el permiso de origen.
        for origen, destino in fusiones + proxies:
            try:
                conn.execute(text("""
                    INSERT IGNORE INTO Rol_x_Permiso (ID_Rol, ID_Permiso)
                    SELECT rxp.ID_Rol, pd.ID_Permiso
                    FROM Rol_x_Permiso rxp
                    JOIN Permisos po ON po.ID_Permiso = rxp.ID_Permiso AND po.Permiso = :o
                    JOIN Permisos pd ON pd.Permiso = :d
                """), {"o": origen, "d": destino})
                conn.commit()
            except Exception:
                conn.rollback()

        for origen, _destino in fusiones:
            for sql in (
                "DELETE rxp FROM Rol_x_Permiso rxp JOIN Permisos p ON p.ID_Permiso = rxp.ID_Permiso WHERE p.Permiso = :o",
                "DELETE FROM Permisos WHERE Permiso = :o",
            ):
                try:
                    conn.execute(text(sql), {"o": origen})
                    conn.commit()
                except Exception:
                    conn.rollback()

        for nombre in obsoletos:
            for sql in (
                "DELETE rxp FROM Rol_x_Permiso rxp JOIN Permisos p ON p.ID_Permiso = rxp.ID_Permiso WHERE p.Permiso = :o",
                "DELETE FROM Permisos WHERE Permiso = :o",
            ):
                try:
                    conn.execute(text(sql), {"o": nombre})
                    conn.commit()
                except Exception:
                    conn.rollback()

# ── CORS — origins desde variable de entorno para no hardcodear URLs ──
_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "https://frontend-ten-xi-31.vercel.app,"
        "https://frontend-git-main-isabela-s-projects1.vercel.app,"
        "https://tostonapp.vercel.app,"
        "http://localhost:5173",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Registro de routers ──
PREFIX = "/api"

app.include_router(auth_router,            prefix=PREFIX)
app.include_router(usuarios_router,        prefix=PREFIX)
app.include_router(roles_router,           prefix=PREFIX)
app.include_router(notificaciones_router,  prefix=PREFIX)
app.include_router(salidas_router,         prefix=PREFIX)
app.include_router(control_acceso_router,  prefix=PREFIX)
app.include_router(landing_router,         prefix=PREFIX)

app.include_router(insumos_router,         prefix=PREFIX)
app.include_router(cat_insumos_router,     prefix=PREFIX)
app.include_router(proveedores_router,     prefix=PREFIX)
app.include_router(compras_router,         prefix=PREFIX)
app.include_router(productos_router,     prefix=PREFIX)
app.include_router(cat_productos_router, prefix=PREFIX)
app.include_router(ordenes_router,       prefix=PREFIX)
app.include_router(clientes_router,      prefix=PREFIX)
app.include_router(pedidos_router,       prefix=PREFIX)
app.include_router(ventas_router,        prefix=PREFIX)
app.include_router(devoluciones_router,  prefix=PREFIX)
app.include_router(domicilios_router,    prefix=PREFIX)
app.include_router(ubicaciones_router,   prefix=PREFIX)
app.include_router(dashboard_router,      prefix=PREFIX)


@app.get("/")
def root():
    return {"mensaje": "API funcionando ✅"}

