# TostonApp — Frontend

App de gestión para una empresa de tostones. React SPA conectada a una API FastAPI en Render.

## Stack
- **Frontend:** React 19 + Vite 5 (JavaScript puro, sin TypeScript)
- **Routing:** React Router v7
- **Estilos:** CSS modules propios por módulo (Tailwind disponible pero no se usa principalmente)
- **Charts:** Recharts
- **Backend:** FastAPI (Python) — `https://api-tostonapp.onrender.com/api`
- **Auth:** JWT Bearer token guardado en `localStorage`

## Comandos
- Dev:   `npm run dev`   (puerto 5173)
- Build: `npm run build`
- Lint:  `npm run lint`

## Estructura clave
```
src/
  config/api.js          — API_URL base
  utils/api.js           — apiFetch() con Bearer token, redirige /login en 401
  services/              — un archivo por módulo (productosService.js, ubicacionesService.js, etc.)
  features/              — componentes por módulo
  AppContext.jsx          — contexto global (algunos módulos aún lo usan)
  shared/components/     — Sidebar, Layout, etc.
```

## Módulo Ubicaciones + precio del domicilio
- `src/services/ubicacionesService.js` — jerarquía Departamento → Ciudad → Barrio y ofertas de domicilio. Endpoints `/ubicaciones/checkout/*` (lectura para el cliente, cualquier rol autenticado) y `/ubicaciones/*` (panel, con `*_ubicaciones`).
- `src/features/configuracion/ubicaciones/` — panel con 2 pestañas: jerarquía (árbol Depto→Ciudad→Barrio con acordeón; barrios paginados server-side, y los niveles Depto/Ciudad paginados en cliente con el helper `Pager` local) y ofertas/recargos. Los modales del módulo reutilizan las clases `ub-modal*` — su estética (header verde con eyebrow, cards de detalle) espeja `.modal-box` del resto del panel.
- `src/shared/components/SelectorBarrioEntrega.jsx` — Depto → Ciudad → Barrio contra el API + recuadro de cobertura/precio. Lo usan el checkout (`CheckoutModal`), el alta/edición de pedido del panel (`CrearPedido`, `EditarPedido`) y el perfil (`ProfileForm`, con `mostrarCobertura={false}`).
- **El precio del domicilio ya no es una constante.** Sale del barrio de entrega (`precio_domicilio_final` / `desglose_domicilio` en la respuesta del pedido). En el checkout se muestra el precio ya calculado (base tachado + final + etiqueta de oferta). El carrito (`CartAside`) ya no suma un costo fijo: dice "se calcula en el checkout".
- ~~**Pedido dividido = un domicilio por viaje.**~~ **DESACTUALIZADO (2026-09-14): el backend eliminó `GrupoEnvio`/`GrupoEnvioItem` y `FEATURE_DIVISION_PEDIDOS`** (commits `9e8d1c6`/`8ced18d`). Un pedido tiene un solo domicilio; ya no existe `grupos_envio[]` en la respuesta. Ver la advertencia equivalente en el CLAUDE.md raíz, sección Ubicaciones. `ubicacionesService.js` cachea en memoria las listas del checkout (no la cobertura); las mutaciones del panel limpian la caché.
- `utils/barrios.js` y la lista de barrios de `utils/direccionEntrega.js` / `FormularioDireccion.jsx` / `SelectorDireccionEntrega.jsx` **quedaron sin uso en la web** (solo las espeja la app Flutter). No borrar hasta sincronizar la app — ver la sección "Sincronización pendiente con la app Flutter" en el CLAUDE.md raíz.

## Formato de dinero y horario
- **Precios**: `src/utils/formato.js` → `formatCOP(n)` = `$100'000` (pesos, sin decimales, apóstrofe de miles). `milesConApostrofe(n)` para el número solo, `parseMiles(s)` para leerlo. Es el único formateador de dinero de la app (web, panel y factura). No usar `Intl.NumberFormat`/`toLocaleString` para montos.
- **Horario de atención**: `src/utils/horario.js` (`estaAbierto`, `mensajeFueraHorario`, `rangoHorario`, `filasHorario`) lee `getLandingConfig()` (`horaApertura`, `horaCierre`, `diasAtencion` CSV ISO 1..7). El aviso de "fuera de horario" es **informativo** (carrito y checkout), no bloquea el pedido. Solo un admin edita el horario en "Editar Landing Page"; el mapa del footer usa `mapLat`/`mapLng` de la config (fallback: geocodificar la dirección).

## Convenciones API
- El backend devuelve campos PascalCase para IDs y datos (`ID_Producto`, `Nombre`, `Estado`)
- Excepciones: nombres de joins son snake_case (`nombre_producto`, `nombre_categoria`)
- El campo `nombre` del producto viene en **minúscula** (`p.nombre`), no `p.Nombre`
- Insumos sí usan `i.Nombre` (mayúscula)
- Siempre adaptar la respuesta en el service antes de guardar en state

## Reglas
- JavaScript, no TypeScript. Sin `any`, sin tipos explícitos.
- El backend SÍ tiene `/api/compras/` (GET, POST, GET /{id}). `GestionCompras.jsx` puede migrarse.
- Clientes en la API tienen `tipo: "cliente"`, empleados tienen `tipo: "empleado"`.
- `GET /api/productos/` es público (sin auth). Los demás endpoints requieren Bearer.
- `por_pagina` máximo es **100** en todos los endpoints.
- `apiFetch` no sirve para el login (redirige en 401). Usar `fetch` directo en `authService`.
- Respuestas cortas. No summarizar lo que ya se ve en el diff.
- No instalar dependencias sin preguntar.
- No modificar algo que ya funciona/se ve bien solo por estilo o preferencia.

## Separación de responsabilidades por módulo
- Un componente de `features/<módulo>/` **no** llama a `fetch`/`apiFetch` directamente: toda llamada HTTP pasa por su archivo en `src/services/`. Ese archivo es también donde se adapta la respuesta (PascalCase → lo que use el componente) antes de guardarla en state.
- CSS por módulo: cada `features/<módulo>/*.css` es propio de ese módulo. Si necesitas un estilo para varias vistas, o va a `src/shared/` o creas una clase nueva y específica — **no** cuelgues estilos de otro módulo de una clase que ya usa otra vista.
- Componentes reutilizables viven en `src/shared/components/` (`DateRangeFilter`, `SearchableSelect`, `CampoMonto`, `EmojiPicker`, …). Revísalos antes de crear uno nuevo.
- La UI puede ocultar/deshabilitar acciones por permiso o por estado, pero eso es solo UX: el backend siempre revalida. Nunca dejes una regla de negocio (permiso, estado, stock, monto, fecha) como única barrera en el frontend.
- Hoy **no hay** componente de paginación compartido: cada listado implementa el suyo. Si tocas paginación en varios a la vez, evalúa extraer uno a `src/shared/` (ver [`../prompts/prompt-todos.md`](../prompts/prompt-todos.md), 3.2).

## Zonas de peligro (frontend)
- **Formularios de editar** — al guardar sin cambios no debe dispararse `PUT`/`PATCH`; mostrar "No se hicieron cambios". No relajes validaciones por implementar esto.
- **Costo del domicilio en el checkout** — nunca lo calcules ni lo hardcodees en el frontend. Viene de `GET /ubicaciones/checkout/cobertura/{id_barrio}` (`base`, `final`, `desglose`) y el backend lo **recalcula y congela** al confirmar. El frontend solo lo muestra. `Municipio_entrega`/`Departamento_entrega` los deriva el backend del barrio. En un pedido dividido, **el mismo principio por grupo**: se cobra un domicilio por cada grupo a domicilio.
- **Barrio del perfil** — es `Usuario.ID_Barrio`, **dato guía**: no habilita ni condiciona el domicilio. `Municipio`/`Departamento` del perfil siguen siendo texto libre. El pedido siempre vuelve a pedir la ubicación de entrega.
- **Comprobantes de pago / imágenes** — son URLs de Cloudinary (string plano). El frontend sube a Cloudinary y solo manda la URL. Nunca base64.
- **Vistas del cliente** (`features/client/`, catálogo público, carrito, perfil) — el cliente se identifica por `ID_Rol === 3`, no por permisos. No condiciones funcionalidad de cliente a permisos del rol.
- **Órdenes de producción ligadas a un pedido** (`orden.idVenta`) — no se editan ni se cancelan desde la UI de órdenes; su avance manual (iniciar/completar) solo se habilita cuando el pedido ya está confirmado o en producción (`ESTADOS_VENTA_PRODUCIENDO`). Cada bloqueo se explica con su motivo y con un enlace al pedido (`/admin/pedidos?search=<idVenta>`). Ver [`../prompts/prompt-orden-produccion.md`](../prompts/prompt-orden-produccion.md).
- **Rango de fechas invertido** (`DateRangeFilter` y filtros de listados) — si `inicio > fin`, no bloquear: ordenar las dos fechas y consultar igual.
