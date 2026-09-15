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
- **Empleados**: campo `ID_Rol` directo en tabla `Empleados`
- **Clientes**: tabla `Usuario_x_Rol`
- Al registrarse un nuevo usuario → rol Cliente asignado automáticamente en `Usuario_x_Rol`

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

El cliente puede optar por recibir su pedido como **domicilio**. Un empleado o admin con permisos asigna ese domicilio a un **domiciliario** (empleado con rol Domiciliario, `ID_Rol=4`). `Domicilios.ID_Empleado` apunta a `Empleados`, nunca a `Usuarios`.

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

## Endpoints de Auth (todos implementados) (pueden estar incompletos)

```
POST /api/auth/login                 Login unificado empleados y clientes
POST /api/auth/registro              Crea cliente (Nombre, Apellidos, Correo, Contrasena, Confirmar_contrasena, Numero_documento?). Rechaza correo o Numero_documento ya registrados.
POST /api/auth/verificar-correo      409 si el correo ya existe (chequeo en vivo del registro)
POST /api/auth/verificar-documento   409 si el Numero_documento ya existe (chequeo en vivo del registro)
POST /api/auth/recuperar-contrasena  Genera código 6 dígitos y lo envía al correo (Resend SMTP)
POST /api/auth/verificar-codigo      Valida código, retorna reset_token (10 min)
POST /api/auth/resetear-contrasena   Valida reset_token tipo="reset", actualiza contraseña
GET  /api/auth/me                    Perfil básico del usuario autenticado
GET  /api/auth/perfil                Perfil completo del cliente (incluye ID_Barrio + bloque Barrio legible)
PUT  /api/auth/perfil                Edita Telefono, Direccion, Municipio, Departamento, ID_Barrio (0 = quitar)
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
El frontend necesita saber qué permisos tiene el usuario autenticado. Verificar si existe un endpoint que los devuelva; si no existe, hay que crearlo:
```
GET /api/auth/mis-permisos   → retorna lista de nombres de permisos del usuario actual
```

---

## Convenciones de código

- Schemas: Pydantic v2 (`model_validator`, `model_dump`)
- Imports de dependencias siempre desde `src.features.auth.services.dependencies`
- Imports de modelos siempre desde `src.shared.services.models`
- Imports de DB siempre desde `src.shared.services.database`
- Contraseña universal de prueba: `Admin123@` (seed.py la aplica en cada deploy)
- Los errores de negocio van como `HTTPException`, no como excepciones genéricas

---

## Antes de hacer cualquier cambio

1. Leer el archivo relevante completo antes de editarlo
2. Pedir `models.py` si vas a tocar lógica de BD
3. No asumir que un campo es NOT NULL — revisar el modelo
4. Si el cambio afecta stock, permisos o roles → revisar las reglas de negocio de este archivo primero

ESTE ARCHIVO NO ESTA ACTUALIZADO CON LAS ULTIMAS METRICAS, PUEDEN HABER ERRORES O FALTA DE ESPECIFICACIÓN