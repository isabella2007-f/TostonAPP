import { apiFetch } from "../utils/api";

const soloFecha = (v) => (v ? String(v).split("T")[0] : "");

const adaptLote = (l) => ({
  id:              l.id ?? l.ID_Lote_Compra ?? null,
  idCompra:        l.id_compra ?? null,
  fechaVencimiento: l.fecha_vencimiento ?? null,
  cantidadInicial: Number(l.cantidad_inicial ?? 0),
  cantidadActual:  Number(l.cantidad_actual ?? 0),
  consumido:       Number(l.consumido ?? 0),
  estado:          l.estado ?? null,
  vencido:         !!l.vencido,
});

const adaptCompra = (c) => ({
  id:           c.ID_Compra        || c.id,
  idProveedor:  c.ID_Proveedor     || c.id_proveedor   || null,
  proveedor:    c.nombre_proveedor || c.proveedor       || "",
  // El backend guarda "Efectivo"/"Transferencia"; el formulario usa minúsculas.
  metodoPago:   (c.Metodo_Pago     || c.metodo_pago     || "").toLowerCase(),
  comprobante:  c.Comprobante      || c.comprobante     || null,
  total:        c.Total_Pago       || c.Total           || c.total           || 0,
  estado:       (() => {
    const label = c.estado_label;
    if (label) {
      const m = { pendiente: "pendiente", confirmado: "completada", cancelado: "anulada", anulada: "anulada", completada: "completada" };
      return m[label.toLowerCase()] || "pendiente";
    }
    const raw = c.Estado ?? c.estado;
    if (typeof raw === "string") return raw.toLowerCase();
    const m = { 3: "pendiente", 4: "completada", 11: "completada", 5: "anulada", 12: "anulada" };
    return m[raw] || "pendiente";
  })(),
  fecha:        soloFecha(c.Fecha_Compra || c.fecha_compra || c.fecha),
  fecha_llegada: c.Fecha_Llegada  ? new Date(c.Fecha_Llegada).toISOString().split('T')[0] : null,
  fecha_anulada: c.Fecha_Anulada  ? new Date(c.Fecha_Anulada).toISOString().split('T')[0] : null,
  notas:        c.Notas            || c.notas           || "",
  stockAplicado: [4, 11].includes(c.Estado ?? c.estado) || ["confirmado", "completada"].includes((c.estado_label || "").toLowerCase()),
  transporte:         Number(c.Costo_Transporte     ?? c.transporte)          || 0,
  ivaPorcentaje:      Number(c.IVA_Porcentaje       ?? c.iva_porcentaje)      || 0,
  descuentoPorcentaje: Number(c.Descuento_Porcentaje ?? c.descuento_porcentaje) || 0,
  otros:              Number(c.Otros_Costos         ?? c.otros_costos)        || 0,
  items: (c.items || c.detalles || []).map(i => ({
    idDetalle:        i.ID_Detalle_Compra || i.ID_Detalle        || i.id_detalle        || null,
    idInsumo:         i.ID_Insumo         || i.id_insumo         || null,
    idLoteCompra:     i.ID_Lote_Compra    || i.id_lote_compra    || null,
    idUnidad:         i.ID_Unidad_Medida      ?? i.id_unidad_medida      ?? null,
    idUnidadCompra:   i.ID_Unidad_Compra     ?? i.id_unidad_compra     ?? null,
    nombre:           i.nombre_insumo         || i.nombre               || "",
    categoria:        i.nombre_categoria      || i.categoria            || "",
    // Muestra la unidad con la que se registró la compra; si no existe (compra
    // antigua sin esta columna) cae en el símbolo base del insumo.
    unidad:           i.simbolo_unidad_compra || i.simbolo_unidad || i.unidad || "",
    cantidad:         Number(i.Cantidad   ?? i.cantidad          ?? 0),
    precioUnd:        Number(i.Precio_Und  ?? i.precio_und        ?? 0),
    subtotal:         i.Subtotal          || i.subtotal          || 0,
    fechaVencimiento: i.Fecha_Vencimiento || i.fecha_vencimiento || null,
    loteOrigen:       i.lote_origen ? adaptLote(i.lote_origen) : null,
    otrosLotes:       Array.isArray(i.otros_lotes) ? i.otros_lotes.map(adaptLote) : [],
  })),
});

export async function getCompras({ pagina = 1, porPagina = 100, busqueda = "", idProveedor = null, fechaDesde = "", fechaHasta = "" } = {}) {
  const params = new URLSearchParams({ pagina, por_pagina: porPagina });
  if (busqueda)    params.append("busqueda",     busqueda);
  if (idProveedor) params.append("id_proveedor", idProveedor);
  if (fechaDesde)  params.append("fecha_desde",  fechaDesde);
  if (fechaHasta)  params.append("fecha_hasta",  fechaHasta);
  const data = await apiFetch(`/compras/?${params}`);
  return {
    total:   data.total,
    compras: (data.compras || []).map(adaptCompra),
  };
}

export async function getCompra(id) {
  const data = await apiFetch(`/compras/${id}`);
  return adaptCompra(data);
}

export async function crearCompra(payload) {
  // El backend valida contra {"Efectivo", "Transferencia", "Crédito", "Cheque"} (Primera letra mayúscula)
  const raw = payload.metodoPago || "";
  const metodoPago = raw.charAt(0).toUpperCase() + raw.slice(1);

  const g = payload.gastos || {};
  const body = {
    ID_Proveedor:         Number(payload.idProveedor),
    Metodo_Pago:          metodoPago,
    Fecha_Compra:         payload.fecha || null,
    Notas:                payload.notas || null,
    Comprobante:          payload.comprobante || null,
    Costo_Transporte:     Number(g.transporte) || null,
    IVA_Porcentaje:       Number(g.iva)        || null,  // porcentaje
    Descuento_Porcentaje: Number(g.descuento)  || null,  // porcentaje
    Otros_Costos:         Number(g.otros)      || null,
    detalles: (payload.detalles || []).map(i => ({
      ID_Insumo:         Number(i.idInsumo),
      ID_Unidad_Compra:  i.idUnidad ? Number(i.idUnidad) : null,
      Cantidad:          Number(i.cantidad),
      Precio_Und:        Number(i.precioUnd),
      Notas:             i.notas || null,
      Fecha_Vencimiento: i.fechaVencimiento || null,
    })),
  };
  const data = await apiFetch("/compras/", { method: "POST", body: JSON.stringify(body) });
  return adaptCompra(data);
}

export async function editarCompra(id, payload) {
  const raw = payload.metodoPago || "";
  const metodoPago = raw.charAt(0).toUpperCase() + raw.slice(1);

  // Solo se envía lo que el formulario incluyó según el estado de la compra;
  // el backend rechaza campos no editables para el estado actual.
  const body = {
    Metodo_Pago: metodoPago || undefined,
    Notas:       payload.notas ?? null,
  };

  // Comprobante: URL para fijarlo, "" para quitarlo, ausente = sin cambios.
  if (payload.comprobante !== undefined) body.Comprobante = payload.comprobante || "";
  if (payload.fecha_llegada !== undefined) body.Fecha_Llegada = payload.fecha_llegada || null;
  if (payload.idProveedor !== undefined) body.ID_Proveedor = Number(payload.idProveedor);
  if (payload.fecha !== undefined) body.Fecha_Compra = payload.fecha || null;

  if (payload.gastos) {
    const g = payload.gastos;
    body.Costo_Transporte     = Number(g.transporte) || null;
    body.IVA_Porcentaje       = Number(g.iva)        || null; // porcentaje
    body.Descuento_Porcentaje = Number(g.descuento)  || null; // porcentaje
    body.Otros_Costos         = Number(g.otros)      || null;
  }

  // Insumos — idem: solo cuando la compra es editable a nivel de líneas
  if (Array.isArray(payload.detalles)) {
    body.detalles = payload.detalles.map(i => ({
      ID_Insumo:         Number(i.idInsumo),
      ID_Unidad_Compra:  i.idUnidad ? Number(i.idUnidad) : null,
      Cantidad:          Number(i.cantidad),
      Precio_Und:        Number(i.precioUnd),
      Notas:             i.notas || null,
      Fecha_Vencimiento: i.fechaVencimiento || null,
    }));
  }

  const data = await apiFetch(`/compras/${id}`, {
    method: "PUT",
    body:   JSON.stringify(body),
  });
  return adaptCompra(data);
}

export async function completarCompra(id, fecha = null) {
  const opts = { method: "PATCH" };
  if (fecha) opts.body = JSON.stringify({ Fecha_Llegada: fecha });
  const data = await apiFetch(`/compras/${id}/completar`, opts);
  return adaptCompra(data);
}

export async function anularCompra(id) {
  const data = await apiFetch(`/compras/${id}/anular`, { method: "PATCH" });
  return adaptCompra(data);
}
