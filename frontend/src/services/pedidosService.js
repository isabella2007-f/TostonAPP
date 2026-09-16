import { apiFetch } from "../utils/api";

// Estados de VENTA (tabla global Estados). Son los que usa
// pedidos/services/estados.py: EstadoPedido. Los IDs 2 y 3 no se usan para
// ventas, por eso no aparecen aquí.
const ESTADO_PEDIDO_MAP = {
  1:  "Pendiente",
  4:  "Confirmado",
  5:  "Cancelado",
  8:  "Entregado",
  9:  "En camino",
  10: "Asignado",
  11: "Listo",
  13: "En producción",
  16: "Fecha propuesta",
  17: "Fecha rechazada",
  18: "Parcialmente entregado",
  19: "Escalado a admin",
  20: "Esperando pago",
  21: "Fecha propuesta final",
  22: "Retenido en tienda",
  23: "En ruta de retorno",
};

const adaptPedido = (p) => {
  const estado = ESTADO_PEDIDO_MAP[p.Estado] || p.estado_label || "Pendiente";

  const productosItems = (p.productos || p.Productos || []).map(i => ({
    idProducto:        i.ID_Producto     || i.id_producto,
    nombre:            i.nombre_producto || i.Nombre || i.nombre || "",
    precio:            i.precio_unitario || i.Precio_venta || i.precio || 0,
    cantidad:          i.Cantidad        || i.cantidad || 0,
    cantidad_preorden: i.cantidad_preorden || 0,
  }));
  const productosPorId = Object.fromEntries(productosItems.map(pi => [pi.idProducto, pi]));

  return {
    id:               p.ID_Venta          || p.id,
    numero:           p.Numero_Pedido     || p.numero_pedido   || p.numero || `V-${p.ID_Venta || p.id}`,
    estado,
    metodo_pago:      p.Metodo_Pago       || p.metodo_pago     || "",
    // Pago mixto: cuánto va de cada forma (null en el resto de pedidos).
    monto_efectivo:      p.monto_efectivo      ?? null,
    monto_transferencia: p.monto_transferencia ?? null,
    domicilio:        !!(p.tiene_domicilio ?? p.Domicilio ?? p.domicilio),
    id_domicilio:     p.ID_Domicilio || null,
    direccion_entrega: p.direccion_entrega    || "",
    municipio:         p.municipio_entrega    || "",
    departamento:      p.departamento_entrega || "",
    // Precio del domicilio: snapshot congelado (barrio + ofertas del día).
    id_barrio:              p.ID_Barrio ?? null,
    barrio_entrega:         p.barrio_entrega || "",
    precio_domicilio_base:  p.precio_domicilio_base ?? null,
    precio_domicilio_final: p.precio_domicilio_final ?? null,
    desglose_domicilio:     p.desglose_domicilio ?? null,
    subtotal:         p.subtotal_bruto    || p.Subtotal         || p.subtotal || 0,
    descuento:        p.credito_aplicado  || p.Descuento        || p.descuento || 0,
    total:            p.Total             || p.total            || 0,
    notas:            p.Notas             || p.notas            || "",
    fecha_pedido:     p.Fecha_pedido      || p.Fecha_Pedido     || p.fecha_pedido || "",
    fecha_venta:      p.Fecha_Venta       || p.fecha_venta      || null,
    // Entrega real. De acá sale el plazo de devolución: sin esta fecha
    // habría que contar desde que se hizo el pedido, que es otra cosa.
    fecha_entrega:    p.Fecha_entrega     || p.fecha_entrega    || null,
    fecha_actualizacion: p.Fecha_Actualizacion || p.fecha_actualizacion || null,
    idCliente:        p.ID_Usuario        || p.ID_Cliente       || p.id_cliente   || null,
    idEmpleado:          p.ID_Empleado          || p.id_empleado         || null,
    nombre_domiciliario: p.nombre_domiciliario  || null,
    orden_produccion:      (p.ordenes_produccion_pendientes > 0) || !!(p.Orden_Produccion ?? p.orden_produccion),
    ordenes_en_espera:     p.ordenes_en_espera || 0,
    requiereProduccion:    !!(p.requiere_produccion),
    requiereFechaPropuesta: !!(p.requiere_fecha_propuesta),
    fecha_propuesta:  p.Fecha_Propuesta || p.fecha_propuesta || p.Fecha_entrega_esperada || null,
    fecha_rechazada:  p.fecha_rechazada || null,
    intentos_rechazo: p.intentos_rechazo || 0,
    resaltarCanalExcepcion: !!(p.resaltar_canal_excepcion),
    comprobante:             p.comprobante_pago || p.Comprobante || p.comprobante || null,
    // Las tres notas de la entrega, cada una de su autor.
    observaciones_domicilio: p.observaciones_domicilio || null,
    observaciones_admin:      p.observaciones_admin      || null,
    observaciones_repartidor: p.observaciones_repartidor || null,
    sobre_stock:      !!(p.sobre_stock),
    anticipo_requerido: p.anticipo_requerido != null ? Number(p.anticipo_requerido) : null,
    anticipo_pagado:    p.anticipo_pagado    != null ? Number(p.anticipo_pagado)    : null,
    anticipo_monto:     p.anticipo_monto     != null ? Number(p.anticipo_monto)     : null,
    anticipo_metodo_pago:    p.anticipo_metodo_pago    || null,
    anticipo_comprobante_url: p.anticipo_comprobante_url || null,
    anticipo_registrado:    !!(p.anticipo_registrado),
    requiere_anticipo:      !!(p.requiere_anticipo),
    pago_final_registrado:     !!(p.pago_final_registrado),
    pago_final_monto:          p.pago_final_monto    != null ? Number(p.pago_final_monto) : null,
    pago_final_metodo_pago:    p.pago_final_metodo_pago    || null,
    pago_final_comprobante_url: p.pago_final_comprobante_url || null,
    pago_final_fecha:          p.pago_final_fecha    || null,
    estado_pago:               p.estado_pago         || null,
    motivo_rechazo_comprobante: p.motivo_rechazo_comprobante || null,
    // Segundo comprobante: el saldo restante tras el anticipo (3.10)
    saldo_comprobante_url: p.saldo_comprobante_url || null,
    intentos_rechazo_comprobante_anticipo: p.intentos_rechazo_comprobante_anticipo || 0,
    intentos_rechazo_comprobante_saldo:    p.intentos_rechazo_comprobante_saldo    || 0,
    // 3.7: cuándo entró a "Retenido en tienda" (ventanas de 24h/48h, solo UI —
    // el backend valida lo mismo al actuar).
    fecha_retenido_en_tienda: p.fecha_retenido_en_tienda || null,
    envio_completo_domingo:
      p.envio_completo_domingo == null ? null : !!p.envio_completo_domingo,
    cliente: {
      nombre:   p.nombre_cliente   || "",
      correo:   p.correo_cliente   || "",
      telefono: p.telefono_cliente || "",
    },
    productosItems,
  };
};

export const getPedidos = async ({ pagina = 1, porPagina = 100, estado = null, busqueda = null, timeout } = {}) => {
  let url = `/pedidos/?pagina=${pagina}&por_pagina=${porPagina}`;
  if (estado   != null) url += `&estado=${estado}`;
  if (busqueda)         url += `&busqueda=${encodeURIComponent(busqueda)}`;
  const data = await apiFetch(url, timeout ? { timeout } : {});
  return {
    total:     data.total,
    pagina:    data.pagina,
    por_pagina:data.por_pagina,
    pedidos:   (data.pedidos || []).map(adaptPedido),
  };
};

export const getHistorialPedidos = async ({ pagina = 1, porPagina = 100 } = {}) => {
  const data = await apiFetch(`/ventas/?pagina=${pagina}&por_pagina=${porPagina}`);
  if (!data) return { total: 0, pedidos: [] };
  return {
    total:   data.total,
    pedidos: (data.pedidos || data.ventas || [])
      .map(adaptPedido)
      .filter(p => ["Entregado", "Cancelado"].includes(p.estado)),
  };
};

export const getPedido = async (id) => {
  const data = await apiFetch(`/pedidos/${id}`);
  return adaptPedido(data);
};

export const confirmarPedido = async (id) => {
  return apiFetch(`/pedidos/${id}/confirmar`, { method: "PATCH" });
};

export const cancelarPedido = async (id, motivo = null) => {
  const options = { method: "PATCH" };
  if (motivo) options.body = JSON.stringify({ Motivo: motivo });
  return apiFetch(`/pedidos/${id}/cancelar`, options);
};

export const crearPedido = async (data) => {
  return apiFetch("/pedidos/", { method: "POST", body: JSON.stringify(data) });
};

export const editarPedido = async (id, data) => {
  return apiFetch(`/pedidos/${id}`, { method: "PUT", body: JSON.stringify(data) });
};

export const registrarPagoFinal = async (id, { monto, metodo_pago, comprobante_url }) => {
  const data = await apiFetch(`/ventas/${id}/registrar-pago-final`, {
    method: "POST",
    body: JSON.stringify({ monto, metodo_pago, comprobante_url: comprobante_url ?? null }),
  });
  return adaptPedido(data);
};

export const cambiarEstadoVenta = async (id, estadoId) => {
  return apiFetch(`/ventas/${id}/estado`, {
    method: "PATCH",
    body: JSON.stringify({ Estado: estadoId }),
  });
};

export const getMiCredito = async () => {
  return apiFetch("/ventas/mi-credito");
};

export const getMisVentas = async ({ pagina = 1, porPagina = 100 } = {}) => {
  const data = await apiFetch(`/ventas/mis-ventas?pagina=${pagina}&por_pagina=${porPagina}`);
  return {
    total:   data.total,
    pedidos: (data.pedidos || data.ventas || []).map(adaptPedido),
  };
};

export const getMiVenta = async (id) => {
  const data = await apiFetch(`/ventas/mis-ventas/${id}`);
  return adaptPedido(data);
};

export const cancelarMiPedido = async (id) =>
  apiFetch(`/pedidos/${id}/cancelar-mi-pedido`, { method: "PATCH" });

export const editarMiPedido = async (id, datos) =>
  apiFetch(`/pedidos/${id}/editar-mi-pedido`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });

export const proponerFechaProduccion = async (id, fecha, motivo = null) =>
  apiFetch(`/ventas/${id}/proponer-fecha`, {
    method: "PATCH",
    body: JSON.stringify({ fecha_entrega: fecha, motivo }),
  });

export const aceptarFechaProduccion = async (id) => {
  const data = await apiFetch(`/ventas/${id}/aceptar-fecha`, { method: "PATCH" });
  return adaptPedido(data);
};

// Camino A: admin aprueba en 1 clic la fecha que el cliente pidió al hacer el pedido.
export const aprobarFechaDirecta = async (id) => {
  const data = await apiFetch(`/ventas/${id}/aprobar-fecha`, { method: "PATCH" });
  return adaptPedido(data);
};

// El cliente pide hablar directamente con el admin (canal de excepción) en
// vez de seguir rechazando la contraoferta de fecha.
export const solicitarEscalado = async (id) => {
  const data = await apiFetch(`/ventas/${id}/solicitar-escalado`, { method: "PATCH" });
  return adaptPedido(data);
};

// El cliente adjunta el comprobante (o el anticipo) de un pedido 'Esperando Pago'.
export const pagarPedido = async (id, { comprobante_url, monto = null }) => {
  const data = await apiFetch(`/pedidos/${id}/pagar`, {
    method: "PATCH",
    body: JSON.stringify({ comprobante_url, monto }),
  });
  return adaptPedido(data);
};

// El cliente rechaza la fecha propuesta con su propia contraoferta final:
// fecha propia y motivo, los dos obligatorios (prompt-pedidos-2, 3.4).
export const rechazarFechaProduccion = async (id, fechaPropuesta, motivo) => {
  const data = await apiFetch(`/ventas/${id}/rechazar-fecha`, {
    method: "PATCH",
    body: JSON.stringify({ fecha_propuesta: fechaPropuesta, motivo }),
  });
  return adaptPedido(data);
};

// Admin rechaza en definitivo la propuesta final del cliente (3.4) → Escalado a admin.
export const rechazarFechaFinal = async (id, motivo = null) => {
  const data = await apiFetch(`/ventas/${id}/rechazar-fecha-final`, {
    method: "PATCH",
    body: JSON.stringify({ motivo: motivo || null }),
  });
  return adaptPedido(data);
};

export const resolverEscaladoAcuerdo = async (id, fechaAcordada) => {
  const data = await apiFetch(`/ventas/${id}/resolver-escalado-acuerdo`, {
    method: "PATCH",
    body: JSON.stringify({ fecha_acordada: fechaAcordada }),
  });
  return adaptPedido(data);
};

export const resolverEscaladoCancelar = async (id) => {
  const data = await apiFetch(`/ventas/${id}/resolver-escalado-cancelar`, { method: "PATCH" });
  return adaptPedido(data);
};

export const guardarEnvioCompletoDomingo = async (id, valor) => {
  const data = await apiFetch(`/ventas/${id}/envio-completo-domingo`, {
    method: "PATCH",
    body: JSON.stringify({ envio_completo_domingo: valor }),
  });
  return adaptPedido(data);
};

export const aprobarComprobante = async (id) =>
  apiFetch(`/pedidos/${id}/aprobar-comprobante`, { method: "PATCH" });

export const rechazarComprobante = async (id, motivo) =>
  apiFetch(`/pedidos/${id}/rechazar-comprobante`, {
    method: "PATCH",
    body: JSON.stringify({ motivo }),
  });

export const registrarCobroPedido = async (id, { recibido, monto = null, motivo = null }) =>
  apiFetch(`/pedidos/${id}/registrar-cobro`, {
    method: "PATCH",
    body: JSON.stringify({ recibido, monto, motivo }),
  });

// Segundo comprobante: el saldo restante tras el anticipo, solo cuando ese
// resto se paga por transferencia (3.10). Mismo mecanismo de 3 intentos que
// el primer comprobante (pagarPedido/aprobarComprobante/rechazarComprobante).
export const pagarSaldoPedido = async (id, { comprobante_url, monto = null }) => {
  const data = await apiFetch(`/pedidos/${id}/pagar-saldo`, {
    method: "PATCH",
    body: JSON.stringify({ comprobante_url, monto }),
  });
  return adaptPedido(data);
};

export const aprobarComprobanteSaldo = async (id) =>
  apiFetch(`/pedidos/${id}/aprobar-comprobante-saldo`, { method: "PATCH" });

export const rechazarComprobanteSaldo = async (id, motivo) =>
  apiFetch(`/pedidos/${id}/rechazar-comprobante-saldo`, {
    method: "PATCH",
    body: JSON.stringify({ motivo }),
  });

// ── 3.7: excepción de cobro en efectivo (recoger en tienda) ──
export const marcarRetenidoEnTienda = async (id) => {
  const data = await apiFetch(`/pedidos/${id}/retener-en-tienda`, { method: "PATCH" });
  return adaptPedido(data);
};

export const reintentarPagoRetenido = async (id, { recibido, monto = null, motivo = null }) => {
  const data = await apiFetch(`/pedidos/${id}/reintentar-pago-retenido`, {
    method: "PATCH",
    body: JSON.stringify({ recibido, monto, motivo }),
  });
  return adaptPedido(data);
};

export const cambiarADomicilioRetenido = async (id, datos) => {
  const data = await apiFetch(`/pedidos/${id}/cambiar-a-domicilio`, {
    method: "PATCH",
    body: JSON.stringify(datos),
  });
  return adaptPedido(data);
};

export const cancelarRetenidoEnTienda = async (id) => {
  const data = await apiFetch(`/pedidos/${id}/cancelar-retenido`, { method: "PATCH" });
  return adaptPedido(data);
};

// ── 3.11: avisos de despacho (no cambian de estado) ──
export const avisarPuedeRecoger = async (id) =>
  apiFetch(`/pedidos/${id}/avisar-puede-recoger`, { method: "PATCH" });

export const avisarEnviarAEntregar = async (id) =>
  apiFetch(`/pedidos/${id}/avisar-enviar-a-entregar`, { method: "PATCH" });
