import { apiFetch } from "../utils/api";

// El backend usa Estado=1 ("Activo" en la tabla Estados) para órdenes nuevas/pendientes.
// El frontend las muestra como "Pendiente" para claridad.
const ESTADO_DISPLAY_MAP = {
  "Activo":     "Pendiente",
  "En proceso": "En proceso",
  "Completada": "Completada",
  "Cancelado":  "Cancelada",
};

function adaptarOrden(o) {
  const label = o.estado_label || "";
  return {
    id:             o.ID_Orden_Produccion,
    idVenta:        o.ID_Venta        || o.id_venta        || null,
    ventaEstado:      o.venta_estado ?? null,
    ventaEstadoLabel: o.venta_estado_label ?? null,
    idProducto:     o.ID_Producto,
    nombreProducto: o.nombre_producto,
    idInsumo:       o.ID_Insumo,
    nombreInsumo:   o.nombre_insumo,
    stockInsumo:    o.stock_insumo ?? null,
    idFicha:        o.ID_Ficha,
    versionFicha:   o.version_ficha,
    cantidad:       o.Cantidad,
    fechaCreacion:  o.Fecha_Creacion ? String(o.Fecha_Creacion).split("T")[0] : null,
    fechaInicio:    o.Fecha_inicio  ? String(o.Fecha_inicio).split("T")[0]  : null,
    fechaEntrega:   o.Fecha_Entrega ? String(o.Fecha_Entrega).split("T")[0] : null,
    fechaFin:       o.Fecha_fin     ? String(o.Fecha_fin).split("T")[0]     : null,
    estado:         ESTADO_DISPLAY_MAP[label] || label || "Pendiente",
    costo:          parseFloat(o.Costo ?? 0),
    costoDetalle:   o.costo_detalle || [],
    lote: o.lote ? {
      id:               o.lote.ID_Lote_Producto,
      numeroLote:       o.lote.Numero_Lote,
      fechaProduccion:  o.lote.Fecha_Produccion  ? String(o.lote.Fecha_Produccion).split("T")[0]  : null,
      fechaVencimiento: o.lote.Fecha_Vencimiento ? String(o.lote.Fecha_Vencimiento).split("T")[0] : null,
      cantidad:         o.lote.Cantidad,
      alertaVencimientoPrevioEntrega: o.lote.alerta_vencimiento_previo_entrega ?? false,
    } : null,
  };
}

export async function getOrdenes({ busqueda = "" } = {}) {
  // El backend pagina de a 100 como máximo. El listado se recorre entero para
  // que con más de 100 órdenes no queden truncadas de forma silenciosa.
  const POR_PAGINA = 100;
  const todas = [];
  let pagina = 1;
  let total = Infinity;
  while (todas.length < total) {
    const params = new URLSearchParams({ pagina, por_pagina: POR_PAGINA });
    if (busqueda) params.append("busqueda", busqueda);
    const data = await apiFetch(`/ordenes-produccion/?${params}`);
    total = data.total ?? 0;
    const lote = (data.ordenes || []).map(adaptarOrden);
    todas.push(...lote);
    if (lote.length < POR_PAGINA) break;
    pagina += 1;
  }
  return todas;
}

export async function crearOrden(data) {
  return apiFetch("/ordenes-produccion/", { method: "POST", body: JSON.stringify(data) });
}

export async function editarOrden(id, data) {
  return apiFetch(`/ordenes-produccion/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

// "Anular" = pasar la orden a estado Cancelada conservando su historial.
// El backend usa el verbo DELETE pero NO borra el registro.
export async function anularOrden(id) {
  return apiFetch(`/ordenes-produccion/${id}`, { method: "DELETE" });
}

export async function cambiarEstadoOrden(id, estadoNum, loteData = {}) {
  const body = { Estado: estadoNum, ...loteData };
  return apiFetch(`/ordenes-produccion/${id}/estado`, {
    method: "PATCH",
    body: JSON.stringify(body),
    timeout: 60000,
  });
}
