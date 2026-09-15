"""
Catálogo canónico de permisos del sistema.

Única fuente de verdad para:
- `seed.py` (siembra la tabla `Permisos`)
- `requiere_permiso()` y `obtener_mis_permisos()` (regla de auto-otorgado de `ver_`)
- la validación anti-escalación y el forzado de `ver_` al asignar permisos a un rol

Cada entrada: (nombre_permiso, descripcion, modulo, accion)

`modulo` usa la misma clave que el frontend (`PrivilegiosModal.jsx`) para que
front y back agrupen igual. `accion` es "ver", "crear", "editar", "eliminar",
"anular", "cancelar", "cambiar_estado", "generar_salida", "ver_detalle",
"aprobar", ...
"""

# (nombre, descripcion, modulo, accion)
PERMISOS: list[tuple[str, str, str, str]] = [
    # ── Sitio web ──
    ("editar_landing_page",       "Editar el contenido de la landing page",              "LandingPage",        "editar"),

    # ── Dashboard ──
    ("ver_dashboard",             "Ver el panel de métricas y estadísticas",             "Dashboard",          "ver"),

    # ── Roles ──
    ("ver_roles",                 "Ver listado y detalle de roles",                      "Roles",              "ver"),
    ("crear_roles",               "Crear nuevos roles",                                  "Roles",              "crear"),
    ("editar_roles",              "Editar roles y asignar permisos",                     "Roles",              "editar"),
    ("eliminar_roles",            "Eliminar roles",                                      "Roles",              "eliminar"),

    # ── Usuarios ──
    ("ver_usuarios",              "Ver listado y detalle de usuarios",                   "Usuarios",           "ver"),
    ("crear_usuarios",            "Crear nuevos usuarios",                               "Usuarios",           "crear"),
    ("editar_usuarios",           "Editar información de usuarios",                       "Usuarios",           "editar"),
    ("eliminar_usuarios",         "Eliminar usuarios",                                   "Usuarios",           "eliminar"),
    ("cambiar_estado_usuarios",   "Activar o desactivar usuarios",                       "Usuarios",           "cambiar_estado"),
    ("cambiar_rol_usuarios",      "Cambiar el rol de otros usuarios",                    "Usuarios",           "cambiar_rol"),

    # ── Salidas ──
    ("ver_salidas",               "Ver listado y detalle de salidas de inventario",      "GestionSalidas",     "ver"),
    ("crear_salidas",             "Registrar nuevas salidas",                            "GestionSalidas",     "crear"),
    ("editar_salidas",            "Editar salidas registradas",                          "GestionSalidas",     "editar"),
    ("eliminar_salidas",          "Eliminar salidas",                                    "GestionSalidas",     "eliminar"),

    # ── Categoría Insumos ──
    ("ver_cat_insumos",           "Ver categorías de insumos",                           "CategoriaInsumos",   "ver"),
    ("crear_cat_insumos",         "Crear categorías de insumos",                         "CategoriaInsumos",   "crear"),
    ("editar_cat_insumos",        "Editar categorías de insumos",                        "CategoriaInsumos",   "editar"),
    ("eliminar_cat_insumos",      "Eliminar categorías de insumos",                      "CategoriaInsumos",   "eliminar"),

    # ── Insumos ──
    ("ver_insumos",               "Ver listado y detalle de insumos",                   "Insumos",            "ver"),
    ("crear_insumos",             "Crear nuevos insumos",                                "Insumos",            "crear"),
    ("editar_insumos",            "Editar insumos",                                      "Insumos",            "editar"),
    ("eliminar_insumos",          "Eliminar insumos",                                    "Insumos",            "eliminar"),
    ("generar_salida_insumo",     "Generar una salida directa desde un insumo",          "Insumos",            "generar_salida"),

    # ── Proveedores ──
    ("ver_proveedores",           "Ver listado y detalle de proveedores",               "Proveedores",        "ver"),
    ("crear_proveedores",         "Crear nuevos proveedores",                            "Proveedores",        "crear"),
    ("editar_proveedores",        "Editar proveedores",                                  "Proveedores",        "editar"),
    ("eliminar_proveedores",      "Eliminar proveedores",                                "Proveedores",        "eliminar"),

    # ── Compras ──
    ("ver_compras",               "Ver listado y detalle de compras",                   "Compras",            "ver"),
    ("crear_compras",             "Registrar nuevas compras",                            "Compras",            "crear"),
    ("editar_compras",            "Editar compras",                                      "Compras",            "editar"),
    ("cambiar_estado_compras",    "Confirmar la llegada de una compra (cambia estado)",  "Compras",            "cambiar_estado"),
    ("anular_compras",            "Anular compras (no elimina, cambia estado)",          "Compras",            "anular"),

    # ── Categoría Productos ──
    ("ver_cat_productos",         "Ver categorías de productos",                         "CategoriaProductos", "ver"),
    ("crear_cat_productos",       "Crear categorías de productos",                       "CategoriaProductos", "crear"),
    ("editar_cat_productos",      "Editar categorías de productos",                      "CategoriaProductos", "editar"),
    ("eliminar_cat_productos",    "Eliminar categorías de productos",                    "CategoriaProductos", "eliminar"),

    # ── Productos ──
    ("ver_productos",             "Ver listado y detalle de productos",                  "GestionProductos",   "ver"),
    ("crear_productos",           "Crear nuevos productos",                              "GestionProductos",   "crear"),
    ("editar_productos",          "Editar productos",                                    "GestionProductos",   "editar"),
    ("eliminar_productos",        "Eliminar productos",                                  "GestionProductos",   "eliminar"),
    ("generar_salida_producto",   "Generar una salida directa desde un producto",        "GestionProductos",   "generar_salida"),

    # ── Órdenes de Producción ──
    ("ver_ordenes",               "Ver listado y detalle de órdenes de producción",     "OrdenesProduccion",  "ver"),
    ("crear_ordenes",             "Crear nuevas órdenes de producción",                  "OrdenesProduccion",  "crear"),
    ("editar_ordenes",            "Editar órdenes de producción",                        "OrdenesProduccion",  "editar"),
    ("cambiar_estado_ordenes",    "Mover una orden entre estados operativos",            "OrdenesProduccion",  "cambiar_estado"),
    ("anular_ordenes",            "Anular órdenes de producción (cambia estado, no elimina)", "OrdenesProduccion", "anular"),

    # ── Pedidos ──
    ("ver_pedidos",               "Ver listado y detalle de pedidos",                    "Pedidos",            "ver"),
    ("crear_pedidos",             "Crear nuevos pedidos",                                "Pedidos",            "crear"),
    ("editar_pedidos",            "Editar el contenido de un pedido (productos, montos, domicilio)", "Pedidos", "editar"),
    ("cancelar_pedidos",          "Cancelar pedidos (cambia estado, no elimina)",        "Pedidos",            "cancelar"),
    # Gobierna todas las acciones que cambian el estado del pedido o
    # aprueban/rechazan algo dentro del flujo (proponer/aprobar/rechazar
    # fecha, aprobar/rechazar comprobante, registrar cobro, registrar pago
    # final, resolver escalado/retenido en tienda, marcar listo/avisar
    # despacho) — incluye poder ver los comprobantes en ese contexto.
    # Distinto de `editar_pedidos`, que es solo el contenido (PUT /pedidos/{id}).
    ("cambiar_estado_pedidos",    "Cambiar el estado de un pedido y sus acciones de aprobación/rechazo (incluye ver comprobantes)", "Pedidos", "cambiar_estado"),

    # ── Devoluciones ──
    ("ver_devoluciones",          "Ver listado y detalle de devoluciones",              "Devoluciones",       "ver"),
    ("crear_devoluciones",        "Registrar nuevas devoluciones",                       "Devoluciones",       "crear"),
    ("editar_devoluciones",       "Editar devoluciones",                                 "Devoluciones",       "editar"),
    ("eliminar_devoluciones",     "Eliminar devoluciones",                               "Devoluciones",       "eliminar"),
    ("aprobar_devoluciones",      "Aprobar o desaprobar solicitudes de devolución",      "Devoluciones",       "aprobar"),

    # ── Domicilios ──
    ("ver_domicilios",            "Ver listado de domicilios",                           "Domicilios",         "ver"),
    ("ver_detalle_domicilios",    "Ver el detalle completo de un domicilio",             "Domicilios",         "ver_detalle"),
    ("crear_domicilios",          "Crear domicilios",                                    "Domicilios",         "crear"),
    ("editar_domicilios",         "Editar y asignar repartidor a un domicilio",          "Domicilios",         "editar"),
    ("cambiar_estado_domicilios", "Cambiar el estado de un domicilio",                   "Domicilios",         "cambiar_estado"),


    # ── Ubicaciones (Departamento → Ciudad → Barrio + ofertas de domicilio) ──
    # Los 5 gobiernan barrios Y ofertas de domicilio con mapeo natural. La
    # columna Permisos.Permiso se amplió a VARCHAR(60) para que
    # `cambiar_estado_ubicaciones` (26 chars) quepa (ver src/main.py).
    ("ver_ubicaciones",             "Ver ubicaciones y ofertas de domicilio: listar, filtrar, ver detalle", "Ubicaciones", "ver"),
    ("crear_ubicaciones",           "Crear barrios y crear ofertas de domicilio",                           "Ubicaciones", "crear"),
    ("editar_ubicaciones",          "Editar barrios (precio, y nombre si es creado) y editar ofertas",      "Ubicaciones", "editar"),
    ("eliminar_ubicaciones",        "Eliminar barrios creados no referenciados y eliminar ofertas",         "Ubicaciones", "eliminar"),
    ("cambiar_estado_ubicaciones",  "Activar/desactivar departamentos, ciudades, barrios y ofertas (incluye acciones masivas)", "Ubicaciones", "cambiar_estado"),
]


# nombre -> (descripcion, modulo, accion)
POR_NOMBRE: dict[str, tuple[str, str, str]] = {
    nombre: (desc, modulo, accion) for nombre, desc, modulo, accion in PERMISOS
}

# nombre de permiso -> su módulo
MODULO_DE_PERMISO: dict[str, str] = {
    nombre: modulo for nombre, _desc, modulo, _accion in PERMISOS
}

# modulo -> nombre del permiso "ver" de ese módulo (si tiene)
VER_DE_MODULO: dict[str, str] = {
    modulo: nombre
    for nombre, _desc, modulo, accion in PERMISOS
    if accion == "ver"
}

# nombre de permiso -> nombre del permiso "ver" de su módulo.
#
# Sirve para dos reglas:
#  - Auto-otorgado: tener `editar_X` (o anular_X, cambiar_estado_X, …) implica
#    poder ver X; un permiso sin "ver" no sirve para nada.
#  - Forzado de "ver" al asignar permisos a un rol.
#
# `crear_X` se EXCLUYE a propósito: el rol Cliente tiene `crear_pedidos` (hacer
# un pedido en la tienda) y eso NO debe darle acceso al listado de gestión de
# pedidos. Al asignar permisos desde el panel, la regla 3.2 ya fuerza el "ver".
VER_HERMANO: dict[str, str] = {
    nombre: VER_DE_MODULO[modulo]
    for nombre, _desc, modulo, accion in PERMISOS
    if accion not in ("ver", "crear") and modulo in VER_DE_MODULO
}

# conjunto de todos los permisos "ver"
PERMISOS_VER: set[str] = set(VER_DE_MODULO.values())
