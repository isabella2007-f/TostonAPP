-- Migración: Precio_Unitario histórico en Venta_x_Producto + limpieza de columnas OTP muertas.
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).
-- Alcance acordado con el usuario (2026-09-20): no toca columnas de pago/comprobante
-- en Ventas ni enums/CHECK de Metodo_Pago/Tipo/Tipo_Accion.

-- ═════════════════════════════════════════════════════════════════════════
-- TAREA 1: Precio unitario histórico por línea de venta
-- Filas existentes quedan con Precio_Unitario = NULL (dato histórico ya
-- perdido, no se puede reconstruir). El código hace fallback al precio
-- actual del producto solo para esas filas viejas.
-- ═════════════════════════════════════════════════════════════════════════

ALTER TABLE Venta_x_Producto ADD COLUMN Precio_Unitario DECIMAL(30,2) NULL;


-- ═════════════════════════════════════════════════════════════════════════
-- TAREA 2: Eliminar columnas OTP/OTP_Expira de Domicilios (confirmado muerto
-- en todo el backend y frontend: solo aparecían en el comentario del modelo,
-- la migración histórica que las creó y un test que verificaba que quedan
-- en NULL — sin ninguna lectura/escritura real).
-- ═════════════════════════════════════════════════════════════════════════

ALTER TABLE Domicilios DROP COLUMN OTP;
ALTER TABLE Domicilios DROP COLUMN OTP_Expira;
