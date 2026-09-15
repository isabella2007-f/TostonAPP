-- Migración: columnas nuevas de prompts/prompt-pedidos-2-flujo-completo.md
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).

ALTER TABLE Ventas
  ADD COLUMN Intentos_Rechazo_Comprobante_Anticipo TINYINT NOT NULL DEFAULT 0
  COMMENT 'Rechazos del primer comprobante (anticipo o total sin producción); al llegar a 3 el pedido se cancela solo.',
  ADD COLUMN Intentos_Rechazo_Comprobante_Saldo TINYINT NOT NULL DEFAULT 0
  COMMENT 'Rechazos del comprobante del saldo restante antes de despachar; al llegar a 3 el pedido se cancela solo.',
  ADD COLUMN Saldo_Comprobante_Url VARCHAR(500) NULL DEFAULT NULL
  COMMENT 'Comprobante del saldo restante subido por el cliente, mientras se valida.',
  ADD COLUMN Fecha_Retenido_En_Tienda DATETIME NULL DEFAULT NULL
  COMMENT 'Cuándo se marcó Retenido en tienda; base para la ventana de reintento (24h) y el plazo de cancelación (48h), evaluados de forma perezosa.',
  ADD COLUMN Stock_Reservado TINYINT NOT NULL DEFAULT 0
  COMMENT 'Si ya se descontó/reservó la porción disponible de stock de este pedido (3.6): evita doble descuento entre la reserva perezosa al cierre de la ventana de 10 min y la reserva al confirmar.';

ALTER TABLE Configuracion_Landing
  ADD COLUMN contact_email VARCHAR(200) NULL DEFAULT NULL
  COMMENT 'Correo de contacto para la escalación a admin (3.4.1/3.15).';
