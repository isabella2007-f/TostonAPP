# TostonApp API — CLAUDE.md

Guía de contexto para Claude Code. Léela completa antes de tocar cualquier archivo.

---

## Stack

- Python 3.11 + FastAPI + SQLAlchemy ORM
- MySQL en Aiven.io (plan gratuito — se apaga solo, reactivar manualmente si hay errores de conexión)
- Deploy en Render.com (plan gratuito — se duerme tras 15 min de inactividad)
- Auth: JWT con python-jose + passlib[bcrypt==4.0.1]
- Docs: Swagger en /docs con HTTPBearer
- Prefijo global de rutas: `/api`

---

## Reglas inamovibles

- **NO actualizar bcrypt** — está fijado en 4.0.1 en requirements.txt, versiones superiores rompen el hashing
- **NO usar `solo_empleados()`** en routers nuevos — está deprecado, usar siempre `requiere_permiso("nombre_permiso")`
- **NO crear permisos `gestionar_X`** — solo existen `ver_`, `crear_`, `editar_`, `eliminar_`, ademas de otros especiales por modulos
- **NO tocar el módulo `configuracion/descuentos`** — postergado para una fase futura
- **NO hardcodear contraseñas ni secrets** — usar variables de entorno via `python-dotenv`
- **CORS**: actualizar a `allow_origins=["https://frontend-ten-xi-31.vercel.app", "http://localhost:5173"]` y `allow_credentials=True`. Actualmente está en `["*"]` con `allow_credentials=False` — PENDIENTE corregir
- **Super admin = `ID_Usuario == 1`** (el del seed). Tiene control total *por ser ese usuario*, con bypass propio en `requiere_permiso()` equivalente al de `ID_Rol == 1`. NADIE puede modificarlo (editar, estado, rol, eliminar); ni él mismo puede cambiarse el rol. Blindaje en backend, no solo UI. Ver `prompts/prompt-roles.md` (en la raíz del repo).
- **Rol Cliente (`ID_Rol == 3`) es estático y sin permisos** — como Admin: no editable ni eliminable, solo cambio de estado. El comportamiento de cliente se decide por `ID_Rol == 3` (o un helper `es_cliente(actual)`), NO por permisos del rol. Un cliente debe poder hacer todo lo que hace hoy.
- **Nadie cambia su propio rol** — el endpoint de cambio de rol rechaza `objetivo == actual`, sin excepción (ni super admin).
- **Anular una Compra** — prohibido si cualquier lote de insumo generado por esa compra ya tuvo consumo (orden de producción, salida, cualquier descuento de stock). Verificar antes de anular; `HTTPException` con el detalle de qué se consumió. Ver `prompts/prompt-compras.md` (raíz del repo).
- **Precio del domicilio = snapshot del barrio** — sale de `Barrios.Precio` + ofertas del día, se congela en `Domicilios` al crear el pedido y **no se recalcula** (ni pendientes ni históricos). `COSTO_DOMICILIO` fue eliminada. Ver "Módulo Ubicaciones" abajo. No sumar un costo fijo de domicilio en ningún lado.

---

## Estructura de carpetas

```
raíz/
├── main.py               ← punto de entrada, NO está en src/
├── seed.py               ← rehashea Admin123@ para todos los usuarios en cada deploy
├── reset_transaccional.py
├── requirements.txt
└── src/
    ├── main.py           ← este NO se usa, el real es el de la raíz
    ├── shared/services/
    │   ├── database.py   ← SessionLocal, get_db
    │   ├── models.py     ← TODOS los modelos SQLAlchemy aquí
    │   └── dependencies.py  ← VACÍO intencionalmente
    └── features/
        ├── auth/services/
        │   ├── router.py
        │   ├── service.py
        │   ├── schemas.py
        │   └── dependencies.py  ← obtener_usuario_actual, requiere_permiso, solo_empleados
        ├── configuracion/
        │   ├── control_acceso/services/   ← módulo existente, no modificar sin consultar
        │   ├── roles/services/
        │   ├── usuarios/services/
        │   ├── notificaciones/services/
        │   └── descuentos/services/       ← POSTERGADO, no tocar
        ├── compras/
        │   ├── insumos/services/
        │   ├── categoria_insumos/services/
        │   └── proveedores/services/
        ├── produccion/
        │   ├── productos/services/
        │   ├── categoria_productos/services/
        │   └── ordenes_produccion/services/
        ├── ventas/
        │   ├── clientes/services/
        │   ├── pedidos/services/
        │   ├── gestion_ventas/services/
        │   ├── devoluciones/services/
        │   ├── domicilios/services/
        │   └── ubicaciones/services/     ← Departamento→Ciudad→Barrio + ofertas de domicilio
        └── dashboard/services/
```

Cada módulo tiene: `router.py`, `service.py`, `schemas.py`.

---

## Autenticación y permisos

### Dónde viven las dependencias
```
src/features/auth/services/dependencies.py
```
Contiene: `obtener_usuario_actual`, `requiere_permiso()`, `solo_empleados()`.  
`src/shared/services/dependencies.py` está vacío intencionalmente — no mover nada ahí.

### Roles
| ID | Nombre | Permisos |
|----|--------|----------|
| 1 | Admin | Todos — bypass total, no verificar permisos |
| 2 | Empleado | 25 permisos |
| 3 | Cliente | 6 permisos |
| 4 | Domiciliario | 3 permisos |

### Cómo se asigna el rol
- **CORREGIDO (verificado 2026-09-16 contra `models.py`): NO existen las tablas `Empleados` ni `Usuario_x_Rol`.** Todos los usuarios (empleados, admin, clientes, domiciliarios) viven en la **única** tabla `Usuarios` (clase `Usuario` en `models.py`, línea 59), con la columna **`ID_Rol`** (FK directa a `Roles.ID_Rol`) determinando el rol de cada uno. No hay tabla intermedia ni separación física entre "empleados" y "clientes" — la diferencia es puramente el valor de `ID_Rol`.
- Al registrarse un nuevo usuario → se crea una fila en `Usuarios` con `ID_Rol = 3` (Cliente) directamente, no hay tabla puente que poblar.
- Cualquier referencia previa a `Empleados`/`Usuario_x_Rol` en este archivo o en otros CLAUDE.md del repo estaba **desactualizada/incorrecta** y fue reemplazada por esta descripción.

### Admin siempre tiene acceso total
```python
# En requiere_permiso(), el Admin hace bypass completo:
if id_rol == 1:
    return actual  # sin verificar Rol_x_Permiso
```

### Regla de permisos ver_
Si un rol tiene, por ejemplo: `editar_X` o `eliminar_X` pero NO `ver_X`, el sistema otorga `ver_X` automáticamente. Todos los usuarios sin excepción pueden ver la landing page

### Cómo proteger un endpoint
```python
# Correcto
from src.features.auth.services.dependencies import requiere_permiso

@router.get("/insumos")
def listar(_, db=Depends(get_db), actual=Depends(requiere_permiso("ver_insumos"))):
    ...

# Incorrecto — NO usar
from src.features.auth.services.dependencies import solo_empleados
```

---

## Base de datos

### Modelos críticos
(Revisar models.py en src -> shared -> services)

### Imágenes — Cloudinary
Los campos de imagen ya NO son LONGBLOB. Son `VARCHAR(500)` con una URL de Cloudinary o un emoji como string.
- El frontend sube la imagen directo a Cloudinary y solo envía la URL a la API
- La API guarda el string tal cual — sin conversión, sin base64
- Eliminar cualquier `base64.b64encode(...)` que quede en los services

```python
# Correcto
"icono": rol.Icono  # ya es string (emoji o URL)

# Incorrecto — eliminar si aparece
"icono": base64.b64encode(rol.Icono).decode() if rol.Icono else None
```

### Estados (tabla Estados)
```
1=Activo        2=Inactivo      3=Pendiente     4=Confirmado    5=Cancelado
6=Aprobada      7=Rechazada     8=Entregado     9=En camino     10=Asignado
11=Completada   12=Anulada      13=En proceso   14=Stock bajo   15=Agotado
(pueden ser mas)
```

### Estados automáticos de stock
```
Producto.Stock = 0              → Estado = 15 (Agotado)
0 < Stock <= Stock_Minimo       → Estado = 14 (Stock bajo)
Stock > Stock_Minimo            → Estado = 1  (Activo)

Insumo.Stock_Actual = 0         → Estado = 15 (Agotado)
0 < Stock_Actual <= Stock_Minimo → Estado = 14 (Stock bajo)
Stock_Actual > Stock_Minimo     → Estado = 1  (Activo)
```

---

## Flujo general del sistema

### Proveedores → Compras → Insumos
El ciclo comienza con los **proveedores**, quienes abastecen a la empresa mediante **compras**. De cada compra se obtienen **insumos** (materia prima), que quedan registrados en lotes (`LoteCompra` / `LoteInsumo`). Tanto insumos como productos se organizan en **categorías**.

### Sistema de lotes — FEFO estricto
Insumos y productos se manejan por lotes. La regla de consumo es **FEFO (First Expired, First Out)**: siempre se descuenta primero del lote con fecha de vencimiento más próxima, independientemente de cuándo llegó al inventario.

Reglas críticas del sistema de lotes:
- **Al descontar stock** (por venta, orden de producción o salida), el sistema busca los lotes ordenados por `Fecha_Vencimiento ASC` y descuenta del más próximo a vencer primero.
- **Si un lote no alcanza** para cubrir la cantidad requerida, el sistema toma el remanente del siguiente lote con la siguiente fecha de vencimiento más próxima, y así sucesivamente hasta completar la cantidad. Esto se hace en una sola operación transaccional.
- **Los lotes pueden quedar en cantidad 0** y siguen existiendo en la BD como historial — no se eliminan ni se inactivan automáticamente.
- **Los lotes de insumos** se crean al registrar una compra.
- **Los lotes de productos** se crean únicamente cuando se completa una `OrdenProduccion` — la única forma de que exista stock de un producto es mediante una orden de producción completada (ya sea creada automáticamente por el sistema o manualmente por un rol con permisos/admin).

### Órdenes de producción y ficha técnica
Cada producto tiene una **ficha técnica** (`FichaTecnica`) que es la referencia obligatoria para producirlo. La ficha técnica especifica:
- Insumos requeridos y sus cantidades exactas
- Medidas y procedimiento de fabricación
- Pasos ordenados del proceso
- Fecha de caducidad del producto resultante o cantidad de días de vida útil (dato crítico para el módulo de salidas)

Cuando se completa una `OrdenProduccion`:
1. Se descuentan los insumos requeridos según la ficha técnica, respetando FEFO
2. Se crea un nuevo lote de producto (`LoteProducto`) con la cantidad producida y la fecha de caducidad calculada a partir de los días de vida útil de la ficha técnica
3. Se incrementa el `Stock` total del producto
4. El estado del producto se actualiza automáticamente según las reglas de stock

Si al recibir un pedido de un cliente no hay stock suficiente del producto solicitado, el sistema genera automáticamente una `OrdenProduccion` con la cantidad necesaria. El pedido queda en estado `Pendiente` hasta que la orden se complete.

### Módulo de salidas — vencimientos y daños
Los insumos y productos pueden deteriorarse, vencerse o sufrir daños que obliguen a retirarlos del inventario. El módulo de **salidas** maneja estos casos:

- **Salida automática por vencimiento**: el sistema detecta lotes cuya `Fecha_Vencimiento` se ha cumplido o cuya vida útil en días ha expirado, y registra la salida automáticamente. Lo más común es que un lote completo venza de golpe, por lo que el sistema procesa salidas de lotes enteros en la mayoría de los casos.
- **Salida manual**: un empleado/admin con permisos puede registrar una salida por cualquier otra causa (daño, pérdida, contaminación, etc.) especificando el motivo, la cantidad y el lote afectado.
- En ambos casos la cantidad se descuenta del lote correspondiente y el stock total del insumo o producto se actualiza automáticamente, aplicando también las reglas de estado por stock.

### Ventas y domicilios
Una vez el cliente confirma su pedido cumpliendo los requisitos (cuenta activa con rol Cliente, teléfono registrado en su perfil si el pedido incluye domicilio, y productos disponibles), se genera la **venta** y el stock de los productos se descuenta automáticamente respetando FEFO por lotes.

El cliente puede optar por recibir su pedido como **domicilio**. Un empleado o admin con permisos asigna ese domicilio a un **domiciliario** (usuario con rol Domiciliario, `ID_Rol=4`). **CORREGIDO (verificado 2026-09-16): `Domicilios.ID_Empleado` es FK a `Usuarios.ID_Usuario`** (`models.py` línea 521) — no existe tabla `Empleados`, así que no puede apuntar ahí. Lo mismo aplica a `Domicilios.ID_Liquidado_Por` (línea 554), también FK a `Usuarios.ID_Usuario`.

### Módulo Ubicaciones y precio del domicilio (reemplaza `COSTO_DOMICILIO`)
Jerarquía `Departamentos` → `Ciudades` → `Barrios` (modelos en `models.py`, migraciones en `src/main.py`, seed en `seed_ubicaciones.py` + `data/*.json`). Cada barrio tiene un **`Precio` entero (COP)** que es el costo del domicilio de un pedido cuya entrega cae en ese barrio.

- **Función única de cálculo**: `src/features/ventas/ubicaciones/services/service.py` → `precio_domicilio_final(db, id_barrio, fecha) -> dict` (`base`, `final`, `techo_aplicado`, `piso_aplicado`, `ofertas`). La envuelve `resolver_domicilio(...)` validando **cobertura** (estado efectivo activo). Reutilizada por `gestion_ventas.crear_venta`, `pedidos.editar_pedido`, el endpoint de cobertura y la vista del cliente. **Toda** validación de límites, estados, cobertura, descuento y snapshot se hace en backend.
- **Snapshot**: al crear el pedido se congela en `Domicilios` (`ID_Barrio`, `Precio_Domicilio_Base`, `Precio_Domicilio_Final`, `Desglose_Ofertas` JSON). No se recalcula aunque después cambie el precio del barrio o una oferta. `Venta.Total` usa el snapshot.
- **Estado en cascada**: estado propio de cada nodo + estado efectivo = propio AND ancestros. Desactivar/reactivar un padre **no** muta el estado propio de los hijos. No se puede activar un hijo con el padre inactivo.
- **Ofertas de domicilio** (`Ofertas_Domicilio` + `Oferta_x_Barrio`): `Tipo` `'descuento'|'recargo'`; `Monto_Pesos`/`Porcentaje` siempre `>= 0` (el `Tipo` decide el signo); `Dias_Semana`/`Dias_Mes` como CSV de enteros (OR entre ambos); día evaluado en `America/Bogota`. Acumulación: **recargos primero** (pesos uno a uno, luego cada % compuesto en orden `ID` asc), luego descuentos igual; **piso 0**, **techo `TECHO_DOMICILIO = 50_000`**, redondeo `ROUND_HALF_UP` por paso. Independiente del módulo congelado `configuracion/descuentos`.
- **Cobertura para el checkout**: `GET /api/ubicaciones/checkout/{departamentos,ciudades,barrios,cobertura/{id}}` — protegidos con `obtener_usuario_actual` (autenticado, cualquier rol), solo devuelven lo disponible. El panel usa `/api/ubicaciones/*` con `requiere_permiso("*_ubicaciones")`.
- **`Usuarios.ID_Barrio`** (nullable): dato guía del perfil. `GET/PUT /api/auth/perfil` lo acepta/devuelve (`0` = quitar) + un bloque `Barrio` legible.
- **Permisos**: los 5 (`ver_/crear_/editar_/eliminar_/cambiar_estado_ubicaciones`, módulo `Ubicaciones`) en `permisos_catalogo.py`. La columna `Permisos.Permiso` se amplió a `VARCHAR(60)` para que `cambiar_estado_ubicaciones` (26 chars) quepa.

### Devoluciones y créditos
Una vez el pedido es entregado (`Estado=8`), el cliente puede solicitar una **devolución**. La solicitud llega a un empleado/admin con permisos quien la analiza y puede aprobarla (`Estado=6`) o rechazarla (`Estado=7`). Si la aprueba, el cliente recibe **créditos** en `CreditoCliente` equivalentes al valor devuelto, registrando el movimiento en `MovimientoCredito` con tipo `'recarga'`. El cliente puede usar esos créditos como dinero en futuras compras.

### Notificaciones
- **Clientes**: cambio de estado de su pedido, cambio de estado de su devolución, mensajes generales del sistema.
- **Empleados/Admin**: stock bajo de insumos o productos, stock agotado, domicilios pendientes de asignar, devoluciones pendientes de revisar, insumos o productos vencidos, compras pendientes de gestionar.

### Acceso por tipo de usuario
- **Invitados** (sin cuenta): pueden ver el catálogo, la landing page y agregar productos a un carrito local, pero no pueden confirmar pedidos hasta crear una cuenta con rol Cliente.
- **Clientes** (rol ID=3): todo lo anterior más confirmar pedidos, ver sus pedidos y devoluciones con su estado en tiempo real, y editar su perfil.
- **Empleados/Admin/Otros**: panel de gestión con sidebar dinámico según permisos. Admin (ID=1) tiene acceso total sin restricciones.

---

## Reglas de negocio

- Si una venta incluye domicilio → el cliente DEBE tener `Telefono` en su perfil (validar antes de crear)
- **Cuenta eliminada por el propio cliente** (`DELETE /api/auth/mi-cuenta`): si tiene historial se hace borrado lógico — libera `Correo`, borra `Cedula`/`Tipo_Documento`, `Estado=2` y `Auto_Eliminado=1`. Un admin/empleado con permiso la recupera al editarla o reactivarla (`Auto_Eliminado` vuelve a 0). El panel muestra el aviso "eliminó su propia cuenta".
- **Horario de atención** (`Configuracion_Landing.hora_apertura/hora_cierre/dias_atencion`): solo un **admin** (`ID_Usuario==1` o `ID_Rol==1`) puede cambiarlo vía `PUT /api/configuracion/landing`; para el resto esos campos se ignoran. `Configuracion_Landing` también guarda `map_lat`/`map_lng` (punto del local en el mapa del footer).
- Devolución aprobada → recargar crédito automáticamente en `CreditoCliente`
- Al completar una `OrdenProduccion` → incrementar `Stock` del `Producto`
- Al iniciar una `OrdenProduccion` → descontar `Stock_Actual` del `Insumo` usado
- Al confirmar una venta → descontar `Stock` del `Producto`
- Módulo Salidas (nuevo, aún no implementado): registra daños/vencimientos y descuenta stock directamente de `Insumos` o `Productos`
- Descuentos: postergados — no implementar

---

## Endpoints de Auth

**CORREGIDO (verificado 2026-09-16 contra `src/features/auth/services/router.py`): la lista estaba incompleta, faltaban 8 endpoints.** Lista completa (18 endpoints):

```
POST   /api/auth/login                 Login unificado empleados y clientes
POST   /api/auth/registro              Crea cliente (Nombre, Apellidos, Correo, Contrasena, Confirmar_contrasena, Numero_documento?). Rechaza correo o Numero_documento ya registrados.
GET    /api/auth/verificar-empleado
GET    /api/auth/verificar-email
POST   /api/auth/reenviar-verificacion
POST   /api/auth/verificar-correo      409 si el correo ya existe (chequeo en vivo del registro)
POST   /api/auth/verificar-documento   409 si el Numero_documento ya existe (chequeo en vivo del registro)
POST   /api/auth/recuperar-contrasena  Genera código 6 dígitos y lo envía al correo (Resend SMTP)
POST   /api/auth/verificar-codigo      Valida código, retorna reset_token (10 min)
POST   /api/auth/resetear-contrasena   Valida reset_token tipo="reset", actualiza contraseña
GET    /api/auth/me                    Perfil básico del usuario autenticado
GET    /api/auth/perfil                Perfil completo del cliente (incluye ID_Barrio + bloque Barrio legible)
PUT    /api/auth/perfil                Edita Telefono, Direccion, Municipio, Departamento, ID_Barrio (0 = quitar)
POST   /api/auth/cambiar-contrasena
POST   /api/auth/foto-perfil
DELETE /api/auth/foto-perfil
GET    /api/auth/mis-permisos          Lista de nombres de permisos del usuario actual (ya existe, no hace falta crearlo — ver sección "Contexto del frontend" más abajo, desactualizada en ese punto)
DELETE /api/auth/mi-cuenta             Borrado lógico de la propia cuenta (ver Reglas de negocio)
POST   /api/auth/fcm-token
DELETE /api/auth/fcm-token
```

---

## Contexto del frontend (para saber qué debe devolver la API)

El frontend es React + Vite, desplegado en https://tostonapp.vercel.app/ La API debe estar lista para responder a tres tipos de usuario:

### 1. Invitado (sin sesión)
- Ve catálogo de productos públicamente → `GET /api/produccion/productos` debe funcionar sin token
- No puede confirmar pedidos

### 2. Cliente (rol ID=3)
- Confirma pedidos con: productos, dirección de entrega, método de pago (Transferencia/Efectivo), comprobante (URL Cloudinary si es transferencia), "A nombre de"
- Ve sus pedidos filtrados por estado
- Solicita devoluciones sobre pedidos entregados
- Edita su perfil (Telefono, Direccion, Municipio, Departamento, Foto_perfil)

### 3. Admin/Empleado/Otros
- Panel de gestión con sidebar dinámico según permisos
- El frontend consulta los permisos del usuario para mostrar/ocultar módulos
- Admin (ID=1) ve todo sin restricción

### Endpoint de permisos necesario para el sidebar
**CORREGIDO (verificado 2026-09-16): el endpoint ya existe**, no hay que crearlo — `GET /api/auth/mis-permisos` retorna la lista de nombres de permisos del usuario actual (ver "Endpoints de Auth" arriba).

---

## Convenciones de código

- Schemas: Pydantic v2 (`model_validator`, `model_dump`)
- Imports de dependencias siempre desde `src.features.auth.services.dependencies`
- Imports de modelos siempre desde `src.shared.services.models`
- Imports de DB siempre desde `src.shared.services.database`
- Contraseña universal de prueba: `Admin123@` (seed.py la aplica en cada deploy)
- Los errores de negocio van como `HTTPException`, no como excepciones genéricas

---

## ZONAS DE PELIGRO

No tocar, o tocar solo con confirmación explícita del usuario antes de escribir código (agregado/verificado 2026-09-16):

### a. Módulo de Pagos — `Ventas` ya NO tiene las columnas de pago/comprobante

**MIGRADO (2026-09-18): las ~17 columnas de pago/comprobante que antes vivían en `Ventas` se movieron a una tabla `Pagos` separada** (migración `migrations/add_pagos_tabla.sql`, ejecutada contra producción tras confirmación explícita). No tocar `Pagos` directamente desde un módulo nuevo sin pasar por `src/shared/services/pagos_utils.py` — es el único punto de acceso (helpers `obtener_pago`, `pago_o_nuevo`, más los predicados `cobro_efectivo_pendiente`/`saldo_final_pendiente`/`comprobante_sin_aprobar`, que ahora reciben `db` como primer argumento).

**Modelo (`models.py`, clase `Pago`):** una fila por "pata" de pago de una venta, como mucho dos por venta:
- `Tipo`: `'anticipo'` (lo que se paga/valida por adelantado — el anticipo del 50%, el total completo si no hay anticipo, o la mitad transferida de un pedido mixto) | `'saldo'` (lo que queda: el resto tras el anticipo, o la mitad en efectivo de un mixto).
- `Metodo_Pago` (`'Efectivo'|'Transferencia'`), `Monto` (declarado/pagado, nunca "lo requerido"), `Comprobante_Url` (NULL si Efectivo), `Estado` (`pendiente|pendiente_validacion|aprobado|rechazado|recibido|no_recibido`), `Motivo_Rechazo`, `Intentos_Rechazo`, `Fecha_Registro`, `Fecha_Resolucion`, `ID_Registrado_Por` (quién lo registró si fue personal; NULL = self-service del cliente), `Monto_Verificado_Creacion` (solo fila `anticipo` del flujo admin/mostrador, dato de auditoría puntual).
- `UNIQUE(ID_Venta, Tipo)`: nunca hay más de una fila `anticipo` o `saldo` por venta — se actualiza in-place (`pago_o_nuevo`), no es un ledger de intentos históricos.

**Se queda en `Ventas`** (no son transacciones de pago, son reglas de negocio o atributos del pedido): `Metodo_Pago` (elección del cliente al pedir, gatilla `_es_mixto`/`_es_transferencia`), `Requiere_Anticipo` (bool), `Anticipo_Requerido` (el mínimo exigido, recalculado en varios puntos — **no confundir con `Pago.Monto`, que es lo realmente pagado**), `Estado_Pago` (agregado de 9 valores, sigue escribiéndose a mano en cada función que muta un `Pago`, igual que antes — **no** es una columna derivada automáticamente), `Fecha_Rechazada`/`intentos_rechazo` (negociación de fecha, no de pago), `Fecha_Retenido_En_Tienda`, `Stock_Reservado`, `Sobre_Stock`, `Necesita_Produccion`, `Envio_Completo_Domingo`.

**Contrato de `VentaResponse`/`PedidoResponse` sin cambios**: `_formato_venta` sigue devolviendo los mismos nombres de campo (`anticipo_monto`, `comprobante_pago`, `pago_final_registrado`, etc.), ahora calculados desde `venta.pagos` en vez de columnas propias. El frontend no necesita cambios salvo que quiera consumir detalle nuevo que no existía antes (`Fecha_Registro`/`Fecha_Resolucion`/`ID_Registrado_Por` por pata, no expuesto aún en el schema).

**No hay dos sistemas de anticipo "activo vs deprecado"** — siguen siendo dos cosas distintas, ambas vigentes:
- **`Anticipo_Requerido`** (Venta, Numeric): el mínimo exigido, activo en TODO el flujo (creación admin/cliente, aprobación de fecha, edición) — es lo que valida `pagar_pedido` contra `Pago(tipo='anticipo').Monto`. **Corrige una imprecisión anterior de este archivo**: no es exclusivo del flujo "sobre stock", se usa en ambos.
- **`Pago.Monto_Verificado_Creacion`** (antes `Venta.Anticipo_Pagado`): solo se escribe una vez, dentro de `crear_venta` (rama admin/mostrador); ninguna otra función lo vuelve a leer — es auditoría puntual de ese chequeo, no un segundo flujo con efecto duradero.

### b. Otras zonas sensibles encontradas explorando el código

- **Anulación de Compras** (`src/features/compras/compras/services/service.py`, función `anular_compra`, línea 680). Usa `with_for_update()` sobre `Compra`, `Insumo` y `LoteCompra` (bloqueo de fila, orden determinista por ID para evitar deadlocks) porque debe verificar de forma atómica que **ningún lote de insumo generado por la compra tuvo consumo** antes de permitir anularla desde estado Completada; si algo se consumió, bloquea la anulación por completo. Es lógica transaccional crítica de inventario — no tocar el orden de bloqueo ni la verificación de consumo sin entender el flujo completo.
- **Aprobación de planta / fecha de entrega** (`src/features/ventas/gestion_ventas/services/service.py`): `aprobar_fecha_directa` (línea 2288) es el "1 clic" con el que el admin aprueba, sin cambiar, la fecha que el cliente puso al pedir (o la contraoferta final del cliente tras rechazar la fecha del admin). Solo aplica desde los estados `PENDIENTE` o `FECHA_PROPUESTA_FINAL`, y solo si `requiere_fecha_propuesta(db, venta)` es verdadero. `proponer_fecha` (línea 2108) es el otro lado: el admin propone una fecha distinta a la pedida por el cliente. Ambas rutas terminan escribiendo en `HistorialFechasPropuestas` (`_guardar_historial_fecha`) para dejar rastro de cada oferta/rechazo. Es lógica de negocio central del rediseño de checkout de 2026-09-12 — cambiarla sin entender los estados de `EstadoPedido` puede romper el flujo de aprobación completo.
- **Cálculo de créditos del cliente** (`src/features/ventas/gestion_ventas/services/service.py`, `obtener_mi_credito`, línea 2017; y `_abonar_credito`/`_aplicar_credito`, líneas 356/612). El **libro mayor de `MovimientoCredito` (append-only, tipos `"recarga"`/`"uso"`) es la fuente de verdad**, no el campo `CreditoCliente.Saldo`, que es una caché: `obtener_mi_credito` recalcula el balance sumando/restando movimientos y **autocorrige y persiste** `Saldo` si detecta desfase (>0.01) contra el balance real. `devoluciones/service.py` (`_recargar_credito`, línea 144) también escribe en este libro mayor cuando se aprueba una devolución. No asumas que `CreditoCliente.Saldo` es confiable de leer directamente en código nuevo — siempre recalcular o reusar `obtener_mi_credito`.

---

## Antes de hacer cualquier cambio

1. Leer el archivo relevante completo antes de editarlo
2. Pedir `models.py` si vas a tocar lógica de BD
3. No asumir que un campo es NOT NULL — revisar el modelo
4. Si el cambio afecta stock, permisos o roles → revisar las reglas de negocio de este archivo primero

ESTE ARCHIVO NO ESTA ACTUALIZADO CON LAS ULTIMAS METRICAS, PUEDEN HABER ERRORES O FALTA DE ESPECIFICACIÓN