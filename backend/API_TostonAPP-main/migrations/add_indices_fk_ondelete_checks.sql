-- Migración: índices faltantes, ON DELETE explícito en FKs, UNIQUE 1:1 y CHECK de booleanos.
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).
-- Alcance acordado con el usuario (2026-09-16): NO toca ninguna columna de pago/comprobante
-- en Ventas (Estado_Pago, Sobre_Stock, Requiere_Anticipo, Anticipo_*, Pago_Final_*, etc.),
-- NO toca el módulo Descuentos (postergado), NO toca tablas huérfanas fuera de models.py
-- (Grupos_Envio, Grupo_Envio_Item, Liquidaciones, Registro_Horas, Usuario_x_Rol) — ver
-- hallazgos adicionales reportados aparte.

-- ═════════════════════════════════════════════════════════════════════════
-- PASO 0: Limpieza de duplicados en Domicilios.ID_Venta (bug pre-existente,
-- no relacionado con esta tarea) — requisito para poder crear la UNIQUE.
-- Se conserva la fila más completa/real de cada grupo (con Fecha_entrega real
-- cuando existe) y se borran los duplicados generados por reintentos.
-- Revisado y confirmado con el usuario antes de ejecutar.
-- ═════════════════════════════════════════════════════════════════════════

-- ID_Venta 164: conservar 57 (Estado=8 Entregado, Fecha_entrega real, ID_Empleado=18)
DELETE FROM Domicilios WHERE ID_Domicilio IN (56, 58);

-- ID_Venta 178: conservar 66 (Estado=8 Entregado, Fecha_entrega real, ID_Empleado=18)
DELETE FROM Domicilios WHERE ID_Domicilio IN (65, 67);

-- ID_Venta 179: conservar 69 (más reciente, con Fecha_entrega registrada)
DELETE FROM Domicilios WHERE ID_Domicilio IN (68, 70);

-- ID_Venta 180: conservar 73 (más reciente)
DELETE FROM Domicilios WHERE ID_Domicilio IN (71, 72);

-- ID_Venta 189: conservar 74 (Estado=8 Entregado, Fecha_entrega real, ID_Empleado=18)
DELETE FROM Domicilios WHERE ID_Domicilio IN (75);


-- ═════════════════════════════════════════════════════════════════════════
-- PASO 1: Índices en columnas de filtro/orden frecuente
-- (Ventas.Estado_Pago se excluye a propósito: es columna de pago, zona de
-- peligro según CLAUDE.md, se toca en la migración futura a tabla Pagos)
-- ═════════════════════════════════════════════════════════════════════════

CREATE INDEX ix_ventas_id_usuario   ON Ventas (ID_Usuario);
CREATE INDEX ix_ventas_estado       ON Ventas (Estado);
CREATE INDEX ix_ventas_fecha_venta  ON Ventas (Fecha_Venta);
CREATE INDEX ix_ventas_fecha_pedido ON Ventas (Fecha_pedido);

CREATE INDEX ix_domicilios_id_empleado ON Domicilios (ID_Empleado);
-- ix_domicilios_id_venta no se crea aparte: la UNIQUE del paso 2 ya sirve como índice.

CREATE INDEX ix_salidas_id_insumo   ON Salidas (ID_Insumo);
CREATE INDEX ix_salidas_id_producto ON Salidas (ID_Producto);


-- ═════════════════════════════════════════════════════════════════════════
-- PASO 2: UNIQUE que refleja la relación 1:1 asumida por el código
-- ═════════════════════════════════════════════════════════════════════════

-- Detalle_Venta.ID_Venta: sin duplicados existentes (verificado 2026-09-16), directo.
CREATE UNIQUE INDEX ux_detalle_venta_id_venta ON Detalle_Venta (ID_Venta);

-- Domicilios.ID_Venta: requiere el PASO 0 primero (había 5 grupos duplicados).
CREATE UNIQUE INDEX ux_domicilios_id_venta ON Domicilios (ID_Venta);


-- ═════════════════════════════════════════════════════════════════════════
-- PASO 3: CHECK en columnas booleanas guardadas como Integer
-- (excluye toda la tabla Ventas — zona de peligro, columnas de pago/estado
-- del rediseño de checkout, confirmado con el usuario)
-- ═════════════════════════════════════════════════════════════════════════

ALTER TABLE Usuarios  ADD CONSTRAINT chk_usuarios_correo_verificado CHECK (Correo_Verificado IN (0,1));
ALTER TABLE Usuarios  ADD CONSTRAINT chk_usuarios_auto_eliminado    CHECK (Auto_Eliminado IN (0,1));
ALTER TABLE Productos ADD CONSTRAINT chk_productos_requiere_prod    CHECK (Requiere_Produccion IN (0,1));
ALTER TABLE Productos ADD CONSTRAINT chk_productos_publicado        CHECK (Publicado IN (0,1));
ALTER TABLE Domicilios ADD CONSTRAINT chk_domicilios_efectivo_liq   CHECK (Efectivo_Liquidado IN (0,1));


-- ═════════════════════════════════════════════════════════════════════════
-- PASO 4: ON DELETE explícito en todas las FK del esquema modelado
-- (MySQL no permite ALTER de la acción de una FK existente: hay que
-- DROP + ADD CONSTRAINT). Por defecto RESTRICT (bloquea borrar el padre
-- mientras haya hijos) salvo el grupo SET NULL abajo (columnas nullable de
-- "quién hizo la acción" / referencias opcionales, acordado con el usuario).
--
-- Domicilios.ID_Empleado tenía DOS constraints duplicadas apuntando a la
-- misma columna (Domicilios_ibfk_2 y fk_domicilios_usuario) — hallazgo
-- adicional, bug de una migración anterior. Se consolidan en una sola.
-- ═════════════════════════════════════════════════════════════════════════

-- --- Domicilios.ID_Empleado: consolidar las 2 FK duplicadas en 1 con SET NULL ---
ALTER TABLE Domicilios DROP FOREIGN KEY Domicilios_ibfk_2;
ALTER TABLE Domicilios DROP FOREIGN KEY fk_domicilios_usuario;
ALTER TABLE Domicilios ADD CONSTRAINT fk_domicilios_empleado
  FOREIGN KEY (ID_Empleado) REFERENCES Usuarios(ID_Usuario) ON DELETE SET NULL;

-- --- Domicilios.ID_Liquidado_Por: SET NULL ---
ALTER TABLE Domicilios DROP FOREIGN KEY dom_liquidado_por_fk;
ALTER TABLE Domicilios ADD CONSTRAINT dom_liquidado_por_fk
  FOREIGN KEY (ID_Liquidado_Por) REFERENCES Usuarios(ID_Usuario) ON DELETE SET NULL;

-- --- Orden_Produccion.ID_Venta: NO se toca aquí. models.py la declara como FK pero
-- information_schema confirma que esa constraint NUNCA se creó en la BD real. Está
-- fuera del alcance de esta tarea (no es de los 4 hallazgos originales) — reportado
-- como hallazgo adicional, no como un DROP+ADD.

-- --- Resto de FKs modeladas: RESTRICT por defecto, SET NULL en las 7 marcadas ---

ALTER TABLE Barrios DROP FOREIGN KEY Barrios_ibfk_2;
ALTER TABLE Barrios ADD CONSTRAINT Barrios_ibfk_2 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Barrios DROP FOREIGN KEY Barrios_ibfk_1;
ALTER TABLE Barrios ADD CONSTRAINT Barrios_ibfk_1 FOREIGN KEY (ID_Ciudad) REFERENCES Ciudades(ID_Ciudad) ON DELETE RESTRICT;

ALTER TABLE Categoria_Insumos DROP FOREIGN KEY Categoria_Insumos_ibfk_1;
ALTER TABLE Categoria_Insumos ADD CONSTRAINT Categoria_Insumos_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Categoria_Producto DROP FOREIGN KEY Categoria_Producto_ibfk_1;
ALTER TABLE Categoria_Producto ADD CONSTRAINT Categoria_Producto_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Ciudades DROP FOREIGN KEY Ciudades_ibfk_2;
ALTER TABLE Ciudades ADD CONSTRAINT Ciudades_ibfk_2 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Ciudades DROP FOREIGN KEY Ciudades_ibfk_1;
ALTER TABLE Ciudades ADD CONSTRAINT Ciudades_ibfk_1 FOREIGN KEY (ID_Departamento) REFERENCES Departamentos(ID_Departamento) ON DELETE RESTRICT;

ALTER TABLE Compras DROP FOREIGN KEY Compras_ibfk_2;
ALTER TABLE Compras ADD CONSTRAINT Compras_ibfk_2 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Compras DROP FOREIGN KEY Compras_ibfk_1;
ALTER TABLE Compras ADD CONSTRAINT Compras_ibfk_1 FOREIGN KEY (ID_Proveedor) REFERENCES Proveedores(ID_Proveedor) ON DELETE RESTRICT;

ALTER TABLE Credito_Cliente DROP FOREIGN KEY Credito_Cliente_ibfk_1;
ALTER TABLE Credito_Cliente ADD CONSTRAINT Credito_Cliente_ibfk_1 FOREIGN KEY (ID_Usuario) REFERENCES Usuarios(ID_Usuario) ON DELETE RESTRICT;

ALTER TABLE Departamentos DROP FOREIGN KEY Departamentos_ibfk_1;
ALTER TABLE Departamentos ADD CONSTRAINT Departamentos_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Detalle_Compra DROP FOREIGN KEY Detalle_Compra_ibfk_1;
ALTER TABLE Detalle_Compra ADD CONSTRAINT Detalle_Compra_ibfk_1 FOREIGN KEY (ID_Compra) REFERENCES Compras(ID_Compra) ON DELETE RESTRICT;

ALTER TABLE Detalle_Compra DROP FOREIGN KEY Detalle_Compra_ibfk_2;
ALTER TABLE Detalle_Compra ADD CONSTRAINT Detalle_Compra_ibfk_2 FOREIGN KEY (ID_Insumo) REFERENCES Insumos(ID_Insumo) ON DELETE RESTRICT;

ALTER TABLE Detalle_Compra DROP FOREIGN KEY Detalle_Compra_ibfk_3;
ALTER TABLE Detalle_Compra ADD CONSTRAINT Detalle_Compra_ibfk_3 FOREIGN KEY (ID_Lote_Compra) REFERENCES Lote_Compra(ID_Lote_Compra) ON DELETE RESTRICT;

ALTER TABLE Detalle_Venta DROP FOREIGN KEY Detalle_Venta_ibfk_1;
ALTER TABLE Detalle_Venta ADD CONSTRAINT Detalle_Venta_ibfk_1 FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE RESTRICT;

ALTER TABLE Devolucion_Detalle DROP FOREIGN KEY Devolucion_Detalle_ibfk_1;
ALTER TABLE Devolucion_Detalle ADD CONSTRAINT Devolucion_Detalle_ibfk_1 FOREIGN KEY (ID_Devolucion) REFERENCES Devoluciones(ID_Devolucion) ON DELETE RESTRICT;

ALTER TABLE Devolucion_Detalle DROP FOREIGN KEY Devolucion_Detalle_ibfk_2;
ALTER TABLE Devolucion_Detalle ADD CONSTRAINT Devolucion_Detalle_ibfk_2 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE Devoluciones DROP FOREIGN KEY Devoluciones_ibfk_4;
ALTER TABLE Devoluciones ADD CONSTRAINT Devoluciones_ibfk_4 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Devoluciones DROP FOREIGN KEY Devoluciones_ibfk_3;
ALTER TABLE Devoluciones ADD CONSTRAINT Devoluciones_ibfk_3 FOREIGN KEY (ID_DetalleVenta) REFERENCES Detalle_Venta(ID_DetalleVenta) ON DELETE RESTRICT;

ALTER TABLE Devoluciones DROP FOREIGN KEY Devoluciones_ibfk_2;
ALTER TABLE Devoluciones ADD CONSTRAINT Devoluciones_ibfk_2 FOREIGN KEY (ID_Usuario) REFERENCES Usuarios(ID_Usuario) ON DELETE RESTRICT;

ALTER TABLE Devoluciones DROP FOREIGN KEY Devoluciones_ibfk_1;
ALTER TABLE Devoluciones ADD CONSTRAINT Devoluciones_ibfk_1 FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE RESTRICT;

ALTER TABLE Domicilios DROP FOREIGN KEY Domicilios_ibfk_3;
ALTER TABLE Domicilios ADD CONSTRAINT Domicilios_ibfk_3 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Domicilios DROP FOREIGN KEY Domicilios_ibfk_1;
ALTER TABLE Domicilios ADD CONSTRAINT Domicilios_ibfk_1 FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE RESTRICT;

ALTER TABLE Ficha_Tecnica DROP FOREIGN KEY Ficha_Tecnica_ibfk_3;
ALTER TABLE Ficha_Tecnica ADD CONSTRAINT Ficha_Tecnica_ibfk_3 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Ficha_Tecnica DROP FOREIGN KEY Ficha_Tecnica_ibfk_2;
ALTER TABLE Ficha_Tecnica ADD CONSTRAINT Ficha_Tecnica_ibfk_2 FOREIGN KEY (ID_Categoria) REFERENCES Categoria_Producto(ID_Categoria) ON DELETE RESTRICT;

ALTER TABLE Ficha_Tecnica DROP FOREIGN KEY Ficha_Tecnica_ibfk_1;
ALTER TABLE Ficha_Tecnica ADD CONSTRAINT Ficha_Tecnica_ibfk_1 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE Ficha_Tecnica_Insumo DROP FOREIGN KEY Ficha_Tecnica_Insumo_ibfk_1;
ALTER TABLE Ficha_Tecnica_Insumo ADD CONSTRAINT Ficha_Tecnica_Insumo_ibfk_1 FOREIGN KEY (ID_Ficha) REFERENCES Ficha_Tecnica(ID_Ficha) ON DELETE RESTRICT;

ALTER TABLE Ficha_Tecnica_Insumo DROP FOREIGN KEY Ficha_Tecnica_Insumo_ibfk_2;
ALTER TABLE Ficha_Tecnica_Insumo ADD CONSTRAINT Ficha_Tecnica_Insumo_ibfk_2 FOREIGN KEY (ID_Insumo) REFERENCES Insumos(ID_Insumo) ON DELETE RESTRICT;

ALTER TABLE Historial_Fechas_Propuestas DROP FOREIGN KEY Historial_Fechas_Propuestas_ibfk_2;
ALTER TABLE Historial_Fechas_Propuestas ADD CONSTRAINT Historial_Fechas_Propuestas_ibfk_2 FOREIGN KEY (ID_Usuario) REFERENCES Usuarios(ID_Usuario) ON DELETE SET NULL;

ALTER TABLE Historial_Fechas_Propuestas DROP FOREIGN KEY Historial_Fechas_Propuestas_ibfk_1;
ALTER TABLE Historial_Fechas_Propuestas ADD CONSTRAINT Historial_Fechas_Propuestas_ibfk_1 FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE RESTRICT;

ALTER TABLE Insumos DROP FOREIGN KEY Insumos_ibfk_4;
ALTER TABLE Insumos ADD CONSTRAINT Insumos_ibfk_4 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Insumos DROP FOREIGN KEY Insumos_ibfk_1;
ALTER TABLE Insumos ADD CONSTRAINT Insumos_ibfk_1 FOREIGN KEY (ID_Categoria) REFERENCES Categoria_Insumos(ID_Categoria) ON DELETE RESTRICT;

ALTER TABLE Insumos DROP FOREIGN KEY Insumos_ibfk_2;
ALTER TABLE Insumos ADD CONSTRAINT Insumos_ibfk_2 FOREIGN KEY (ID_Lote_Compra) REFERENCES Lote_Compra(ID_Lote_Compra) ON DELETE RESTRICT;

ALTER TABLE Insumos DROP FOREIGN KEY Insumos_ibfk_3;
ALTER TABLE Insumos ADD CONSTRAINT Insumos_ibfk_3 FOREIGN KEY (Unidad_Medida) REFERENCES Unidad_Medida(ID_Unidad_Medida) ON DELETE RESTRICT;

ALTER TABLE Lote_Compra DROP FOREIGN KEY Lote_Compra_ibfk_1;
ALTER TABLE Lote_Compra ADD CONSTRAINT Lote_Compra_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Lote_Compra DROP FOREIGN KEY Lote_Compra_ibfk_2;
ALTER TABLE Lote_Compra ADD CONSTRAINT Lote_Compra_ibfk_2 FOREIGN KEY (ID_Insumo) REFERENCES Insumos(ID_Insumo) ON DELETE RESTRICT;

ALTER TABLE Lote_Producto DROP FOREIGN KEY Lote_Producto_ibfk_3;
ALTER TABLE Lote_Producto ADD CONSTRAINT Lote_Producto_ibfk_3 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Lote_Producto DROP FOREIGN KEY Lote_Producto_ibfk_1;
ALTER TABLE Lote_Producto ADD CONSTRAINT Lote_Producto_ibfk_1 FOREIGN KEY (ID_Orden_Produccion) REFERENCES Orden_Produccion(ID_Orden_Produccion) ON DELETE RESTRICT;

ALTER TABLE Lote_Producto DROP FOREIGN KEY Lote_Producto_ibfk_2;
ALTER TABLE Lote_Producto ADD CONSTRAINT Lote_Producto_ibfk_2 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE MensajesChat DROP FOREIGN KEY MensajesChat_ibfk_1;
ALTER TABLE MensajesChat ADD CONSTRAINT MensajesChat_ibfk_1 FOREIGN KEY (ID_Domicilio) REFERENCES Domicilios(ID_Domicilio) ON DELETE RESTRICT;

ALTER TABLE Movimiento_Credito DROP FOREIGN KEY Movimiento_Credito_ibfk_1;
ALTER TABLE Movimiento_Credito ADD CONSTRAINT Movimiento_Credito_ibfk_1 FOREIGN KEY (ID_Credito) REFERENCES Credito_Cliente(ID_Credito) ON DELETE RESTRICT;

ALTER TABLE Movimiento_Credito DROP FOREIGN KEY Movimiento_Credito_ibfk_2;
ALTER TABLE Movimiento_Credito ADD CONSTRAINT Movimiento_Credito_ibfk_2 FOREIGN KEY (ID_Devolucion) REFERENCES Devoluciones(ID_Devolucion) ON DELETE SET NULL;

ALTER TABLE Movimiento_Credito DROP FOREIGN KEY Movimiento_Credito_ibfk_3;
ALTER TABLE Movimiento_Credito ADD CONSTRAINT Movimiento_Credito_ibfk_3 FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE SET NULL;

ALTER TABLE Oferta_x_Barrio DROP FOREIGN KEY Oferta_x_Barrio_ibfk_2;
ALTER TABLE Oferta_x_Barrio ADD CONSTRAINT Oferta_x_Barrio_ibfk_2 FOREIGN KEY (ID_Barrio) REFERENCES Barrios(ID_Barrio) ON DELETE RESTRICT;

ALTER TABLE Oferta_x_Barrio DROP FOREIGN KEY Oferta_x_Barrio_ibfk_1;
ALTER TABLE Oferta_x_Barrio ADD CONSTRAINT Oferta_x_Barrio_ibfk_1 FOREIGN KEY (ID_Oferta) REFERENCES Ofertas_Domicilio(ID_Oferta) ON DELETE RESTRICT;

ALTER TABLE Ofertas_Domicilio DROP FOREIGN KEY Ofertas_Domicilio_ibfk_1;
ALTER TABLE Ofertas_Domicilio ADD CONSTRAINT Ofertas_Domicilio_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Orden_Produccion DROP FOREIGN KEY Orden_Produccion_ibfk_1;
ALTER TABLE Orden_Produccion ADD CONSTRAINT Orden_Produccion_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Orden_Produccion DROP FOREIGN KEY Orden_Produccion_ibfk_4;
ALTER TABLE Orden_Produccion ADD CONSTRAINT Orden_Produccion_ibfk_4 FOREIGN KEY (ID_Ficha) REFERENCES Ficha_Tecnica(ID_Ficha) ON DELETE RESTRICT;

ALTER TABLE Orden_Produccion DROP FOREIGN KEY Orden_Produccion_ibfk_3;
ALTER TABLE Orden_Produccion ADD CONSTRAINT Orden_Produccion_ibfk_3 FOREIGN KEY (ID_Insumo) REFERENCES Insumos(ID_Insumo) ON DELETE SET NULL;

ALTER TABLE Orden_Produccion DROP FOREIGN KEY Orden_Produccion_ibfk_2;
ALTER TABLE Orden_Produccion ADD CONSTRAINT Orden_Produccion_ibfk_2 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE Producto_Imagenes DROP FOREIGN KEY Producto_Imagenes_ibfk_1;
ALTER TABLE Producto_Imagenes ADD CONSTRAINT Producto_Imagenes_ibfk_1 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE Productos DROP FOREIGN KEY Productos_ibfk_2;
ALTER TABLE Productos ADD CONSTRAINT Productos_ibfk_2 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Productos DROP FOREIGN KEY Productos_ibfk_1;
ALTER TABLE Productos ADD CONSTRAINT Productos_ibfk_1 FOREIGN KEY (ID_Categoria) REFERENCES Categoria_Producto(ID_Categoria) ON DELETE RESTRICT;

ALTER TABLE Productos DROP FOREIGN KEY Productos_ibfk_3;
ALTER TABLE Productos ADD CONSTRAINT Productos_ibfk_3 FOREIGN KEY (ID_Orden_Produccion) REFERENCES Orden_Produccion(ID_Orden_Produccion) ON DELETE RESTRICT;

ALTER TABLE Productos DROP FOREIGN KEY Productos_ibfk_4;
ALTER TABLE Productos ADD CONSTRAINT Productos_ibfk_4 FOREIGN KEY (Imagen) REFERENCES Producto_Imagenes(ID_Producto_Img) ON DELETE SET NULL;

ALTER TABLE Proveedores DROP FOREIGN KEY Proveedores_ibfk_1;
ALTER TABLE Proveedores ADD CONSTRAINT Proveedores_ibfk_1 FOREIGN KEY (Sujeto_Derecho) REFERENCES Sujeto_Derecho(ID_Sujeto_Derecho) ON DELETE RESTRICT;

ALTER TABLE Rol_x_Permiso DROP FOREIGN KEY Rol_x_Permiso_ibfk_2;
ALTER TABLE Rol_x_Permiso ADD CONSTRAINT Rol_x_Permiso_ibfk_2 FOREIGN KEY (ID_Permiso) REFERENCES Permisos(ID_Permiso) ON DELETE RESTRICT;

ALTER TABLE Rol_x_Permiso DROP FOREIGN KEY Rol_x_Permiso_ibfk_1;
ALTER TABLE Rol_x_Permiso ADD CONSTRAINT Rol_x_Permiso_ibfk_1 FOREIGN KEY (ID_Rol) REFERENCES Roles(ID_Rol) ON DELETE RESTRICT;

ALTER TABLE Roles DROP FOREIGN KEY Roles_ibfk_1;
ALTER TABLE Roles ADD CONSTRAINT Roles_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Salidas DROP FOREIGN KEY Salidas_ibfk_4;
ALTER TABLE Salidas ADD CONSTRAINT Salidas_ibfk_4 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Salidas DROP FOREIGN KEY fk_salidas_anulado_por;
ALTER TABLE Salidas ADD CONSTRAINT fk_salidas_anulado_por FOREIGN KEY (ID_Anulado_Por) REFERENCES Usuarios(ID_Usuario) ON DELETE SET NULL;

ALTER TABLE Salidas DROP FOREIGN KEY fk_salidas_usuario;
ALTER TABLE Salidas ADD CONSTRAINT fk_salidas_usuario FOREIGN KEY (ID_Empleado) REFERENCES Usuarios(ID_Usuario) ON DELETE SET NULL;

ALTER TABLE Salidas DROP FOREIGN KEY Salidas_ibfk_1;
ALTER TABLE Salidas ADD CONSTRAINT Salidas_ibfk_1 FOREIGN KEY (ID_Insumo) REFERENCES Insumos(ID_Insumo) ON DELETE RESTRICT;

ALTER TABLE Salidas DROP FOREIGN KEY Salidas_ibfk_2;
ALTER TABLE Salidas ADD CONSTRAINT Salidas_ibfk_2 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE Usuarios DROP FOREIGN KEY Usuarios_ibfk_1;
ALTER TABLE Usuarios ADD CONSTRAINT Usuarios_ibfk_1 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Usuarios DROP FOREIGN KEY fk_usuarios_rol;
ALTER TABLE Usuarios ADD CONSTRAINT fk_usuarios_rol FOREIGN KEY (ID_Rol) REFERENCES Roles(ID_Rol) ON DELETE RESTRICT;

ALTER TABLE Venta_x_Producto DROP FOREIGN KEY Venta_x_Producto_ibfk_2;
ALTER TABLE Venta_x_Producto ADD CONSTRAINT Venta_x_Producto_ibfk_2 FOREIGN KEY (ID_Producto) REFERENCES Productos(ID_Producto) ON DELETE RESTRICT;

ALTER TABLE Venta_x_Producto DROP FOREIGN KEY Venta_x_Producto_ibfk_1;
ALTER TABLE Venta_x_Producto ADD CONSTRAINT Venta_x_Producto_ibfk_1 FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE RESTRICT;

ALTER TABLE Ventas DROP FOREIGN KEY Ventas_ibfk_2;
ALTER TABLE Ventas ADD CONSTRAINT Ventas_ibfk_2 FOREIGN KEY (Estado) REFERENCES Estados(ID_Estados) ON DELETE RESTRICT;

ALTER TABLE Ventas DROP FOREIGN KEY Ventas_ibfk_1;
ALTER TABLE Ventas ADD CONSTRAINT Ventas_ibfk_1 FOREIGN KEY (ID_Usuario) REFERENCES Usuarios(ID_Usuario) ON DELETE RESTRICT;

ALTER TABLE Verificaciones_Email DROP FOREIGN KEY fk_verif_usuario;
ALTER TABLE Verificaciones_Email ADD CONSTRAINT fk_verif_usuario FOREIGN KEY (ID_Usuario) REFERENCES Usuarios(ID_Usuario) ON DELETE RESTRICT;
