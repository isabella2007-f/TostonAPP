import { apiFetch } from "../utils/api";
import { labelEstadoDom, normalizarEstadoDom } from "../features/ventas/domicilios/estadosDomicilio";

const adaptDomicilio = (d) => {
  // El estado se normaliza a la numeración canónica (ver estadosDomicilio.js) y
  // la etiqueta se deriva de ahí, para no depender de dos mapas distintos.
  const estadoId = normalizarEstadoDom(d.Estado, Boolean(d.ID_Empleado));
  const observaciones = d.Observaciones ?? d.observaciones ?? d.observaciones_domicilio ?? d.obs_domicilio ?? "";
  const indicaciones = d.indicaciones_cliente ?? d.indicaciones ?? "";

  return {
    id:                 d.ID_Domicilio,
    idVenta:            d.ID_Venta            || null,
    numero:             `DOM-${d.ID_Domicilio}`,
    estadoId,
    estado:             labelEstadoDom(estadoId),
    idEmpleado:         d.ID_Empleado         || null,
    nombre_repartidor:  d.nombre_repartidor   || "",
    direccion_entrega:  d.Direccion_entrega   || "",
    municipio_entrega:  d.Municipio_entrega   || "",
    departamento_entrega: d.Departamento_entrega || "",
    // Cuatro textos distintos, cada uno de un autor. Antes el del
    // domiciliario se escribía encima del del cliente y se perdía el
    // complemento de la dirección justo cuando más falta hacía.
    obs_domicilio:      observaciones,                       // lo puso el cliente al pedir
    obs_admin:          d.observaciones_admin      || "",    // la nota del administrador
    obs_repartidor:     d.observaciones_repartidor || "",    // la novedad de la entrega
    indicaciones_cliente: indicaciones,                      // del perfil del cliente
    fecha_pedido:       d.Fecha_asignacion    || "",
    fecha_entrega_real: d.Fecha_entrega       || null,
    total:              d.total               || 0,
    metodo_pago:        d.metodo_pago         || "",
    // Pago mixto: lo que hay que cobrar en mano (null en el resto de pedidos).
    monto_efectivo:     d.monto_efectivo ?? null,
    comprobante_pago:   d.comprobante_pago    || null,
    productos:          d.productos           || [],
    estado_pago:        d.estado_pago        || null,
    domicilio:          true,
    venta_estado_id:    d.venta_estado ?? null,
    cliente: {
      nombre:   d.nombre_cliente   || "",
      correo:   "",
      telefono: d.telefono_cliente || "",
    },
  };
};

export const getDomicilios = async ({
  pagina = 1, porPagina = 100, estado = "", idEmpleado = null,
  fechaInicio = null, fechaFin = null, busqueda = null,
} = {}) => {
  const params = new URLSearchParams({ pagina, por_pagina: porPagina });
  if (estado)      params.append("estado",       encodeURIComponent(estado));
  if (idEmpleado)  params.append("id_empleado",  idEmpleado);
  if (fechaInicio) params.append("fecha_inicio",  fechaInicio);
  if (fechaFin)    params.append("fecha_fin",     fechaFin);
  if (busqueda)    params.append("busqueda",      encodeURIComponent(busqueda));
  const data = await apiFetch(`/domicilios/?${params}`);
  return {
    total:      data.total,
    pagina:     data.pagina,
    por_pagina: data.por_pagina,
    domicilios: (data.domicilios || []).map(adaptDomicilio),
  };
};

/**
 * Todos los domicilios que cumplan el filtro, no solo la primera página.
 *
 * El backend topeó `por_pagina` en 100, y las pantallas del repartidor
 * pedían una sola página y sacaban cuentas sobre eso: pasadas las 100
 * entregas, su historial y sus totales empezaban a dejar plata afuera sin
 * avisar. Acá se recorren las páginas hasta traerlas todas.
 */
export const getTodosLosDomicilios = async (filtros = {}) => {
  const POR_PAGINA = 100;
  const primera = await getDomicilios({ ...filtros, pagina: 1, porPagina: POR_PAGINA });
  const paginas = Math.ceil((primera.total || 0) / POR_PAGINA);
  if (paginas <= 1) return primera.domicilios;

  const resto = await Promise.all(
    Array.from({ length: paginas - 1 }, (_, i) =>
      getDomicilios({ ...filtros, pagina: i + 2, porPagina: POR_PAGINA })
    )
  );
  return resto.reduce((todos, p) => todos.concat(p.domicilios), primera.domicilios);
};

export const getDomicilio = async (id) => {
  const data = await apiFetch(`/domicilios/${id}`);
  return adaptDomicilio(data);
};

export const getResumenDia = async () => {
  return apiFetch("/domicilios/resumen");
};

export const asignarRepartidor = async (id, idEmpleado) => {
  return apiFetch(`/domicilios/${id}/repartidor`, {
    method: "PATCH",
    body: JSON.stringify({ ID_Empleado: idEmpleado }),
  });
};

export const cambiarEstadoDomicilio = async (id, estado, observaciones = null) => {
  const body = { Estado: estado };
  if (observaciones !== null) body.Observaciones = observaciones;
  return apiFetch(`/domicilios/${id}/estado`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
};

export const actualizarDomicilio = async (id, data) => {
  return apiFetch(`/domicilios/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
};

export const registrarPagoEfectivo = async (id, { recibido, monto = null, motivo = null }) => {
  return apiFetch(`/domicilios/${id}/registrar-pago-efectivo`, {
    method: "PATCH",
    body: JSON.stringify({ recibido, monto, motivo }),
  });
};

// PUNTO 7: liquidación del efectivo cobrado por repartidores
export const getEfectivoPendiente = async () =>
  apiFetch("/domicilios/efectivo-pendiente");

export const liquidarEfectivo = async (id) =>
  apiFetch(`/domicilios/${id}/liquidar-efectivo`, { method: "PATCH" });

// 3.7: el domiciliario confirma que el pedido ya está físicamente de vuelta
// en la tienda tras una entrega fallida (registrarPagoEfectivo con
// recibido=false ya movió el pedido a "En ruta de retorno").
export const confirmarRetornoTienda = async (id) => {
  return apiFetch(`/domicilios/${id}/confirmar-retorno`, { method: "PATCH" });
};
