-- Migración: IVA discriminado en la tabla Ventas
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).
-- Los registros existentes quedan con NULL (IVA = 0 implícito, sin recalcular).

ALTER TABLE Ventas
  ADD COLUMN Subtotal_Base DECIMAL(30, 2) NULL DEFAULT NULL
    COMMENT 'Base imponible del pedido (Total / 1.19). NULL en ventas anteriores.',
  ADD COLUMN IVA_Total DECIMAL(30, 2) NULL DEFAULT NULL
    COMMENT 'IVA extraído del total (Total - Subtotal_Base). NULL en ventas anteriores.';
