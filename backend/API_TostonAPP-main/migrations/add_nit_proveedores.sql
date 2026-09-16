-- Migración: campo NIT en la tabla Proveedores
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).

ALTER TABLE Proveedores
  ADD COLUMN NIT VARCHAR(20) NULL DEFAULT NULL
  COMMENT 'NIT del proveedor (personas jurídicas) o documento alternativo.'
  AFTER Sujeto_Derecho;
