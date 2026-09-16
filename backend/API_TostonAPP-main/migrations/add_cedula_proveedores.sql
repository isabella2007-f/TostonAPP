-- Migración: campo Cedula en la tabla Proveedores (personas naturales)
-- Correr UNA SOLA VEZ en la base de datos de producción (Aiven MySQL).

ALTER TABLE Proveedores
  ADD COLUMN Cedula VARCHAR(20) NULL DEFAULT NULL
  COMMENT 'Cédula del responsable (personas naturales).'
  AFTER NIT;
