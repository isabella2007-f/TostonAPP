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
};

const adaptPedido = (p) => {
  const estado = ESTADO_PEDIDO_MAP[p.Estado] || p.estado_label || "Pendiente";

  // Build product list first so grupos_envio can cross-reference names without JSX logic.
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
    observaciones_domicilio: p.observaciones_domicilio || null,
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
    envio_completo_domingo:
      p.envio_completo_domingo == null ? null : !!p.envio_completo_domingo,
    // Un domicilio por viaje: si el pedido está dividido, es la suma de los
    // domicilios de cada grupo a domicilio; si no, el snapshot único. Ya incluido en `total`.
    costo_domicilio_total: p.costo_domicilio_total ?? null,
    grupos_resumen: (p.grupos_resumen || []),
    grupos_envio: (p.grupos_envio || []).map(g => ({
      id_grupo:    g.id_grupo,
      tipo:        g.tipo,          // 'anticipado' | 'programado'
      fecha:       g.fecha,
      tipo_entrega: g.tipo_entrega,
      estado:      g.estado,        // 'pendiente' | 'enviado' | 'entregado' | 'cancelado'
      // Snapshot del domicilio de ESTE grupo (solo si tipo_entrega === 'domicilio').
      // Un domicilio por viaje: cada grupo a domicilio trae su propio precio.
      direccion_entrega:    g.direccion_entrega    || '',
      municipio_entrega:    g.municipio_entrega    || null,
      departamento_entrega: g.departamento_entrega || null,
      domicilio_con_repartidor: !!g.domicilio_con_repartidor,
      domicilio_estado:       g.domicilio_estado ?? null,
      barrio_entrega:         g.barrio_entrega || '',
      precio_domicilio_base:  g.precio_domicilio_base ?? null,
      precio_domicilio_final: g.precio_domicilio_final ?? null,
      desglose_domicilio:     g.desglose_domicilio ?? null,
      // Productos del grupo con nombre resuelto desde productosItems del mismo pedido.
      // Un producto puede aparecer en dos grupos si está parcialmente cubierto por stock.
      productos: (g.productos || []).map(pr => {
        const base = typeof pr === 'object' ? pr : { id_producto: pr, cantidad: null };
        const item = productosPorId[base.id_producto];
        return { ...base, nombre: item?.nombre || '', precio: item?.precio ?? null };
      }),
    })),
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

// Detalle de una venta propia: devuelve grupos_envio completos (la lista batch los omite).
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

export const proponerFechaProduccion = async (id, fecha) =>
  apiFetch(`/ventas/${id}/proponer-fecha`, {
    method: "PATCH",
    body: JSON.stringify({ fecha_entrega: fecha }),
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

export const rechazarFechaProduccion = async (id, motivo = null) => {
  const data = await apiFetch(`/ventas/${id}/rechazar-fecha`, {
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

// ── Grupos de envío ────────────────────────────────────────────────────────

export const getItemsListos = async (idVenta) =>
  apiFetch(`/ventas/${idVenta}/items-listos`);

export const crearGruposEnvio = async (idVenta, {
  fechaAnticipada,
  tipoEntregaA = null, tipoEntregaB = null,
  // Un domicilio por viaje: el barrio de cada grupo decide su precio.
  direccionA = null, idBarrioA = null,
  direccionB = null, idBarrioB = null,
}) => {
  const data = await apiFetch(`/ventas/${idVenta}/crear-grupos-envio`, {
    method: "POST",
    body: JSON.stringify({
      fecha_anticipada:  fechaAnticipada,
      tipo_entrega_a:    tipoEntregaA,
      tipo_entrega_b:    tipoEntregaB,
      direccion_a:       direccionA || null,
      id_barrio_a:       idBarrioA  || null,
      direccion_b:       direccionB || null,
      id_barrio_b:       idBarrioB  || null,
    }),
  });
  return adaptPedido(data);
};

export const actualizarEstadoGrupo = async (idVenta, idGrupo, estado) => {
  const data = await apiFetch(`/ventas/${idVenta}/grupos/${idGrupo}/estado`, {
    method: "PATCH",
    body: JSON.stringify({ estado }),
  });
  return adaptPedido(data);
};

export const actualizarTipoEntregaGrupo = async (idVenta, idGrupo, tipoEntrega, { idBarrio = null, direccion = null } = {}) => {
  const data = await apiFetch(`/ventas/${idVenta}/grupos/${idGrupo}/tipo-entrega`, {
    method: "PATCH",
    body: JSON.stringify({
      tipo_entrega: tipoEntrega,
      id_barrio: idBarrio || null,
      direccion: direccion || null,
    }),
  });
  return adaptPedido(data);
};

export const cancelarGrupoPendiente = async (idVenta, idGrupo) => {
  const data = await apiFetch(`/ventas/${idVenta}/grupos/${idGrupo}`, { method: "DELETE" });
  return adaptPedido(data);
};

export const editarGrupo = async (idVenta, idGrupo, datos) => {
  const data = await apiFetch(`/ventas/${idVenta}/grupos/${idGrupo}`, {
    method: "PUT",
    body: JSON.stringify(datos),
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
