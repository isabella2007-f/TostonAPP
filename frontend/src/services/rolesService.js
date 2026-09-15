import { apiFetch } from "../utils/api";

/**
 * Puente entre las claves del frontend (`Modulo_accion`, ver `PrivilegiosModal`)
 * y los NOMBRES de permiso del backend (`src/shared/services/permisos_catalogo.py`).
 *
 * Ya NO se usan IDs enteros: el backend recibe y devuelve nombres. Si esta tabla
 * y el catálogo del backend se desincronizan, el permiso simplemente no se
 * asigna (400) en vez de asignar uno equivocado en silencio.
 */
const CLAVE_A_PERMISO = {
  "LandingPage_editar":              "editar_landing_page",
  "Dashboard_ver":                   "ver_dashboard",
  "Roles_ver":                       "ver_roles",
  "Roles_crear":                     "crear_roles",
  "Roles_editar":                    "editar_roles",
  "Roles_eliminar":                  "eliminar_roles",
  "Usuarios_ver":                    "ver_usuarios",
  "Usuarios_crear":                  "crear_usuarios",
  "Usuarios_editar":                 "editar_usuarios",
  "Usuarios_eliminar":               "eliminar_usuarios",
  "Usuarios_cambiar_estado":         "cambiar_estado_usuarios",
  "Usuarios_cambiar_rol":            "cambiar_rol_usuarios",
  "GestionSalidas_ver":              "ver_salidas",
  "GestionSalidas_crear":            "crear_salidas",
  "GestionSalidas_editar":           "editar_salidas",
  "GestionSalidas_eliminar":         "eliminar_salidas",
  "CategoriaInsumos_ver":            "ver_cat_insumos",
  "CategoriaInsumos_crear":          "crear_cat_insumos",
  "CategoriaInsumos_editar":         "editar_cat_insumos",
  "CategoriaInsumos_eliminar":       "eliminar_cat_insumos",
  "Insumos_ver":                     "ver_insumos",
  "Insumos_crear":                   "crear_insumos",
  "Insumos_editar":                  "editar_insumos",
  "Insumos_eliminar":                "eliminar_insumos",
  "Insumos_generar_salida":          "generar_salida_insumo",
  "Proveedores_ver":                 "ver_proveedores",
  "Proveedores_crear":               "crear_proveedores",
  "Proveedores_editar":              "editar_proveedores",
  "Proveedores_eliminar":            "eliminar_proveedores",
  "Compras_ver":                     "ver_compras",
  "Compras_crear":                   "crear_compras",
  "Compras_editar":                  "editar_compras",
  "Compras_cambiar_estado":          "cambiar_estado_compras",
  "Compras_anular":                  "anular_compras",
  "CategoriaProductos_ver":          "ver_cat_productos",
  "CategoriaProductos_crear":        "crear_cat_productos",
  "CategoriaProductos_editar":       "editar_cat_productos",
  "CategoriaProductos_eliminar":     "eliminar_cat_productos",
  "GestionProductos_ver":            "ver_productos",
  "GestionProductos_crear":          "crear_productos",
  "GestionProductos_editar":         "editar_productos",
  "GestionProductos_eliminar":       "eliminar_productos",
  "GestionProductos_generar_salida": "generar_salida_producto",
  "OrdenesProduccion_ver":           "ver_ordenes",
  "OrdenesProduccion_crear":         "crear_ordenes",
  "OrdenesProduccion_editar":        "editar_ordenes",
  "OrdenesProduccion_cambiar_estado":"cambiar_estado_ordenes",
  "OrdenesProduccion_anular":        "anular_ordenes",
  "Pedidos_ver":                     "ver_pedidos",
  "Pedidos_crear":                   "crear_pedidos",
  "Pedidos_editar":                  "editar_pedidos",
  "Pedidos_cancelar":                "cancelar_pedidos",
  "Pedidos_cambiar_estado":          "cambiar_estado_pedidos",
  "Devoluciones_ver":                "ver_devoluciones",
  "Devoluciones_crear":              "crear_devoluciones",
  "Devoluciones_editar":             "editar_devoluciones",
  "Devoluciones_eliminar":           "eliminar_devoluciones",
  "Devoluciones_aprobar":            "aprobar_devoluciones",
  "Devoluciones_desaprobar":         "aprobar_devoluciones",
  "Domicilios_ver":                  "ver_domicilios",
  "Domicilios_ver_detalles":         "ver_detalle_domicilios",
  "Domicilios_crear":                "crear_domicilios",
  "Domicilios_editar":               "editar_domicilios",
  "Domicilios_cambiar_estado":       "cambiar_estado_domicilios",
  "Ubicaciones_ver":                 "ver_ubicaciones",
  "Ubicaciones_crear":               "crear_ubicaciones",
  "Ubicaciones_editar":              "editar_ubicaciones",
  "Ubicaciones_eliminar":            "eliminar_ubicaciones",
  "Ubicaciones_cambiar_estado":      "cambiar_estado_ubicaciones",
};

// nombre backend → clave(s) frontend (varias claves pueden compartir permiso)
const PERMISO_A_CLAVES = {};
for (const [clave, permiso] of Object.entries(CLAVE_A_PERMISO)) {
  (PERMISO_A_CLAVES[permiso] ||= []).push(clave);
}

/** Convierte una lista de claves de frontend en nombres de permiso backend (deduplicado). */
export function clavesAPermisos(claves) {
  const out = [];
  for (const c of claves) {
    const p = CLAVE_A_PERMISO[c];
    if (p && !out.includes(p)) out.push(p);
  }
  return out;
}

/** Convierte una lista de nombres de permiso backend en claves de frontend. */
export function permisosAClaves(nombres) {
  const out = [];
  (nombres || []).forEach(n => {
    (PERMISO_A_CLAVES[n] || []).forEach(c => { if (!out.includes(c)) out.push(c); });
  });
  return out;
}

const DEFAULT_EMOJI_MAP = [
  [["admin", "administrador", "gerente", "director"],              "👑"],
  [["domiciliario", "repartidor", "delivery", "mensajero"],        "🛵"],
  [["vendedor", "venta", "ventas", "comercial", "asesor"],         "🛒"],
  [["produccion", "producción", "chef", "cocina", "cocinero"],     "🧑‍🍳"],
  [["bodega", "almacen", "almacén", "inventario", "logistica"],    "📦"],
  [["contador", "contabilidad", "finanzas", "tesorero"],           "📊"],
  [["sistemas", "soporte", "tecnico", "técnico", "informatica"],   "🧑‍💻"],
  [["supervisor", "coordinador", "jefe"],                          "🔍"],
  [["cajero", "caja", "cobrador"],                                 "💵"],
  [["seguridad", "vigilante", "portero"],                          "🛡️"],
  [["rrhh", "recursos", "talento", "personal"],                    "🤝"],
  [["marketing", "publicidad", "community"],                       "📢"],
  [["cliente", "comprador"],                                       "🧑"],
];

function getDefaultEmoji(nombre) {
  const lower = (nombre || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
  for (const [keys, emoji] of DEFAULT_EMOJI_MAP) {
    if (keys.some(k => lower.includes(k))) return emoji;
  }
  return "👤";
}

function adaptarRol(r) {
  const isUrl = typeof r.Icono === "string" && r.Icono.startsWith("http");

  // Convert API permisos [{ID_Permiso, Permiso, Descripcion}] → frontend clave strings
  const claves = permisosAClaves(
    (r.permisos || []).map(p => p.Permiso || p.permiso).filter(Boolean)
  );

  return {
    id:            r.ID_Rol,
    nombre:        r.Rol,
    icono:         isUrl ? getDefaultEmoji(r.Rol) : (r.Icono || getDefaultEmoji(r.Rol)),
    iconoPreview:  isUrl ? r.Icono : null,
    estado:        r.Estado === 1,
    totalUsuarios: r.total_usuarios ?? 0,
    // esAdmin  → no se le puede cambiar el estado (solo Admin)
    // esEstatico → no se puede editar ni eliminar (Admin, Cliente)
    esAdmin:       r.protegido ?? false,
    esEstatico:    r.es_estatico ?? r.protegido ?? false,
    permisos:      claves,
    fecha:         null,
  };
}

export async function getRoles({ busqueda = "" } = {}) {
  const params = new URLSearchParams({ por_pagina: 100 });
  if (busqueda) params.append("busqueda", busqueda);
  const data = await apiFetch(`/roles/?${params}`);
  return (data.roles || []).map(adaptarRol);
}

export async function crearRol(data, claves) {
  const body = { ...data };
  if (claves && claves.length) body.permisos = clavesAPermisos(claves);
  return apiFetch("/roles/", { method: "POST", body: JSON.stringify(body) });
}

export async function editarRol(id, data) {
  return apiFetch(`/roles/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function eliminarRol(id) {
  return apiFetch(`/roles/${id}`, { method: "DELETE" });
}

export async function toggleEstadoRol(id, estadoActual) {
  return apiFetch(`/roles/${id}/estado`, {
    method: "PATCH",
    body: JSON.stringify({ Estado: estadoActual ? 2 : 1 }),
  });
}

export async function gestionarPermisos(id, claves) {
  // claves = strings tipo "Dashboard_ver"; el backend recibe NOMBRES de permiso.
  return apiFetch(`/roles/${id}/permisos`, {
    method: "PUT",
    body: JSON.stringify({ permisos: clavesAPermisos(claves) }),
  });
}

// Llama /auth/mis-permisos (solo requiere token válido) y traduce los nombres
// de permiso del backend a claves de frontend.
export async function getMisPermisos() {
  const data = await apiFetch("/auth/mis-permisos");
  return permisosAClaves(data.permisos || []);
}
