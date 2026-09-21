-- Migración: extrae las ~17 columnas de pago/comprobante de `Ventas` a una
-- tabla `Pagos` normalizada (ver CLAUDE.md, sección "Módulo de Pagos").
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).
--
-- IRREVERSIBLE: el DROP COLUMN borra el detalle transaccional histórico de
-- pago (comprobantes, métodos, fechas de pago final, motivos y contadores de
-- rechazo) de TODAS las ventas existentes. No hay backfill: se confirmó
-- explícitamente con el usuario que perder ese histórico es aceptable — la
-- tabla `Pagos` arranca vacía y se puebla desde cero con los pedidos nuevos.
--
-- No se usa `DROP COLUMN IF EXISTS` (algunos clientes/extensiones SQL no lo
-- reconocen aunque el servidor sí lo soporte desde 8.0.29). Verificado a mano
-- el 2026-09-20 contra Aiven: las 17 columnas están presentes, así que el
-- DROP plano de todas es seguro. Si alguna ya no existiera, el ALTER fallaría
-- con "check that column/key exists" — en ese caso avisar antes de reintentar.

CREATE TABLE Pagos (
    ID_Pago           INT AUTO_INCREMENT PRIMARY KEY,
    ID_Venta          INT NOT NULL,
    Tipo              VARCHAR(20) NOT NULL
      COMMENT 'anticipo (pago validado por transferencia al hacer el pedido, o la mitad transferida de un mixto) | saldo (lo que queda: resto tras el anticipo, o la mitad en efectivo de un mixto)',
    Metodo_Pago       VARCHAR(30) NOT NULL COMMENT 'Efectivo | Transferencia',
    Monto             DECIMAL(30,2) NULL COMMENT 'Declarado/pagado — nunca "lo requerido" (eso vive en Ventas.Anticipo_Requerido)',
    Comprobante_Url   VARCHAR(500) NULL COMMENT 'NULL si Metodo_Pago = Efectivo',
    Estado            VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    Motivo_Rechazo    TEXT NULL,
    Intentos_Rechazo  INT NOT NULL DEFAULT 0,
    Fecha_Registro    DATETIME NULL COMMENT 'Cuándo se declaró/subió',
    Fecha_Resolucion  DATETIME NULL COMMENT 'Cuándo se aprobó/rechazó/cobró',
    ID_Registrado_Por INT NULL COMMENT 'Quién lo registró si fue personal (cobro en efectivo, pago final directo); NULL = self-service del cliente',
    Monto_Verificado_Creacion DECIMAL(30,2) NULL
      COMMENT 'Solo fila anticipo del flujo admin/mostrador (crear_venta): crédito verificado al crear la venta. Dato de auditoría puntual, ninguna otra función lo vuelve a leer.',

    CONSTRAINT fk_pagos_venta FOREIGN KEY (ID_Venta) REFERENCES Ventas(ID_Venta) ON DELETE RESTRICT,
    CONSTRAINT fk_pagos_registrado_por FOREIGN KEY (ID_Registrado_Por) REFERENCES Usuarios(ID_Usuario) ON DELETE SET NULL,
    CONSTRAINT chk_pagos_tipo CHECK (Tipo IN ('anticipo','saldo')),
    CONSTRAINT chk_pagos_metodo CHECK (Metodo_Pago IN ('Efectivo','Transferencia')),
    CONSTRAINT chk_pagos_estado CHECK (Estado IN ('pendiente','pendiente_validacion','aprobado','rechazado','recibido','no_recibido')),
    CONSTRAINT uq_pagos_venta_tipo UNIQUE (ID_Venta, Tipo),
    INDEX ix_pagos_venta (ID_Venta),
    INDEX ix_pagos_estado (Estado)
);

ALTER TABLE Ventas
  DROP COLUMN Comprobante_Pago,
  DROP COLUMN Anticipo_Pagado,
  DROP COLUMN Anticipo_Monto,
  DROP COLUMN Anticipo_Metodo_Pago,
  DROP COLUMN Anticipo_Comprobante_Url,
  DROP COLUMN Anticipo_Registrado,
  DROP COLUMN Pago_Final_Registrado,
  DROP COLUMN Pago_Final_Monto,
  DROP COLUMN Pago_Final_Metodo_Pago,
  DROP COLUMN Pago_Final_Comprobante_Url,
  DROP COLUMN Pago_Final_Fecha,
  DROP COLUMN Monto_Efectivo,
  DROP COLUMN Monto_Transferencia,
  DROP COLUMN Motivo_Rechazo_Comprobante,
  DROP COLUMN Intentos_Rechazo_Comprobante_Anticipo,
  DROP COLUMN Intentos_Rechazo_Comprobante_Saldo,
  DROP COLUMN Saldo_Comprobante_Url;

-- NO se tocan (se quedan en Ventas — no son transacciones de pago, ver
-- CLAUDE.md): Metodo_Pago, Requiere_Anticipo, Anticipo_Requerido, Estado_Pago,
-- Fecha_Rechazada, intentos_rechazo, Fecha_Retenido_En_Tienda, Stock_Reservado,
-- Sobre_Stock, Necesita_Produccion, Envio_Completo_Domingo.
