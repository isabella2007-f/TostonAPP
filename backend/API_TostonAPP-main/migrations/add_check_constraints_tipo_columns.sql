-- Migración: CHECK constraints en columnas de texto libre que son enums de negocio.
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).
-- Alcance acordado con el usuario (2026-09-16): Historial_Fechas_Propuestas.Tipo_Accion,
-- Salidas.Tipo, Descuentos.Tipo, Ofertas_Domicilio.Tipo, MensajesChat.Tipo_Remitente.
-- NO toca ninguna columna de pago/comprobante en Ventas (zona de peligro aparte).
--
-- Valores verificados contra datos reales (2026-09-16):
--   Historial_Fechas_Propuestas.Tipo_Accion: propuesta(48), aceptada(28), rechazada(20, legacy)
--   Salidas.Tipo: vencimiento(15), devolución(7), daño(2), consumo(2) — ajuste sin uso real pero válido
--   Descuentos.Tipo: tabla vacía
--   Ofertas_Domicilio.Tipo: descuento(1), recargo(1)
--   MensajesChat.Tipo_Remitente: cliente(1), admin(1) — domiciliario sin uso real pero válido

-- ═════════════════════════════════════════════════════════════════════════
-- PASO 0: 'rechazada' es un valor legacy que el código ya no escribe (fue
-- reemplazado por 'rechazada_final' en el rediseño de checkout del 12-sep-2026).
-- Se migra el historial existente al valor vigente antes de aplicar el CHECK,
-- para no perder ni bloquear esas 20 filas.
-- ═════════════════════════════════════════════════════════════════════════

UPDATE Historial_Fechas_Propuestas
SET Tipo_Accion = 'rechazada_final'
WHERE Tipo_Accion = 'rechazada';

-- ═════════════════════════════════════════════════════════════════════════
-- PASO 1: CHECK constraints
-- ═════════════════════════════════════════════════════════════════════════

ALTER TABLE Historial_Fechas_Propuestas
  ADD CONSTRAINT chk_historial_fechas_tipo_accion
  CHECK (Tipo_Accion IN ('propuesta', 'aceptada', 'propuesta_final', 'rechazada_final'));

ALTER TABLE Salidas
  ADD CONSTRAINT chk_salidas_tipo
  CHECK (Tipo IN ('vencimiento', 'daño', 'ajuste', 'consumo', 'devolución'));

ALTER TABLE Descuentos
  ADD CONSTRAINT chk_descuentos_tipo
  CHECK (Tipo IN ('cupon', 'antiguedad', 'emision'));

ALTER TABLE Ofertas_Domicilio
  ADD CONSTRAINT chk_ofertas_domicilio_tipo
  CHECK (Tipo IN ('descuento', 'recargo'));

ALTER TABLE MensajesChat
  ADD CONSTRAINT chk_mensajeschat_tipo_remitente
  CHECK (Tipo_Remitente IN ('cliente', 'admin', 'domiciliario'));
