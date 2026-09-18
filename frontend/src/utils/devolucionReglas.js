/**
 * Las reglas de una devolución, en un solo lugar.
 *
 * Espejo de `devoluciones/services/service.py` (el que decide) y de
 * `lib/models/devolucion_reglas.dart` en la app. Si los tres no dicen lo
 * mismo, el cliente ve un pedido como devolvible y recibe un rebote al enviar.
 */

/** Plazo para pedir una devolución, contado desde la entrega. */
export const HORAS_LIMITE_DEVOLUCION = 48;

/**
 * Estados que bloquean un nuevo pedido de devolución. Solo Pendiente: una
 * aprobada no bloquea (permite devoluciones parciales en tandas). Una
 * rechazada tampoco: el cliente puede reintentar esas unidades.
 */
export const ESTADOS_DEVOLUCION_ACTIVA = ['Pendiente'];

/** Los mismos, por id: 3=Pendiente (7=Rechazada, 6=Aprobada no bloquean). */
export const IDS_DEVOLUCION_ACTIVA = [3];

/** Lo que se le dice al cliente sobre por qué no ve todos sus pedidos. */
export const AVISO_PLAZO_DEVOLUCION =
  `Los pedidos con más de ${HORAS_LIMITE_DEVOLUCION} horas de entregados ya no ` +
  'se pueden devolver, y tampoco los que ya tienen una devolución pendiente de revisión: ' +
  'por eso no aparecen en la lista.';

/**
 * Desde cuándo se cuenta el plazo.
 *
 * Se prefiere la entrega real; si el pedido es viejo y no la tiene, se cae a
 * la fecha del pedido, igual que el servidor.
 *
 * El servidor guarda hora de Colombia. Cuando la manda marcada como UTC hay
 * que correrla; cuando llega sin marcar ya viene en hora local y basta leerla.
 */
export const fechaReferencia = (fechaEntrega, fechaPedido) => {
  const crudo = fechaEntrega || fechaPedido || '';
  if (!crudo) return null;
  const marcadaUtc = /z$|[+-]\d{2}:?\d{2}$/i.test(crudo.trim());
  const d = new Date(marcadaUtc ? crudo : `${crudo.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return null;
  return marcadaUtc ? new Date(d.getTime() - 5 * 3600 * 1000) : d;
};

/** Cuántas horas pasaron desde la entrega, o null si no hay fecha confiable. */
export const horasDesdeLaEntrega = (fechaEntrega, fechaPedido, ahora = new Date()) => {
  const ref = fechaReferencia(fechaEntrega, fechaPedido);
  if (!ref) return null;
  // `ahora` es hora local del navegador; se lleva al mismo marco que `ref`,
  // que quedó en hora de Colombia.
  const ahoraBogota = new Date(ahora.getTime() - 5 * 3600 * 1000);
  return Math.floor((ahoraBogota - ref) / 3600000);
};

/**
 * True si al pedido se le pasó el plazo.
 *
 * Sin fecha confiable se deja pasar: decide el servidor. Esconderle al cliente
 * un pedido que sí podía devolver es peor que un rebote.
 */
export const plazoVencido = (fechaEntrega, fechaPedido, ahora = new Date()) => {
  const horas = horasDesdeLaEntrega(fechaEntrega, fechaPedido, ahora);
  if (horas === null) return false;
  return horas > HORAS_LIMITE_DEVOLUCION;
};

/** True si el pedido ya tiene una devolución que lo ocupa. */
export const tieneDevolucionActiva = (devoluciones, idVenta) =>
  (devoluciones || []).some((d) => {
    if (String(d.idVenta) !== String(idVenta)) return false;
    // El id manda cuando viene; la etiqueta es el respaldo para respuestas
    // que solo la traen.
    return d.estadoId != null
      ? IDS_DEVOLUCION_ACTIVA.includes(Number(d.estadoId))
      : ESTADOS_DEVOLUCION_ACTIVA.includes(d.estado);
  });

/**
 * Los pedidos que de verdad se pueden devolver.
 *
 * Antes se listaban todos los entregados y los vencidos rebotaban al enviar la
 * solicitud, con el formulario ya lleno.
 */
export const pedidosDevolvibles = (pedidos, devoluciones, ahora = new Date()) =>
  (pedidos || []).filter(
    p => !tieneDevolucionActiva(devoluciones, p.id)
      && !plazoVencido(p.fecha_entrega, p.fecha_pedido, ahora),
  );
