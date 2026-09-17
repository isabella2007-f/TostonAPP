/**
 * Estados del DOMICILIO — fuente única para el panel web.
 *
 * Numeración canónica: los IDs de la tabla global `Estados` del backend, los
 * mismos que valida `domicilios/services/estados.py`. Antes había dos mapas
 * distintos (uno en el service y otro en Gestiondomicilios) y la web enviaba
 * estados del PEDIDO (4 Confirmado, 13 En producción, 11 Listo) al endpoint del
 * domicilio, donde el backend los interpretaba como "Entregado" y descontaba
 * stock. Un domicilio solo pasa por los cinco estados de abajo.
 */

export const ESTADO_DOMICILIO = {
  PENDIENTE: 3,
  CANCELADO: 5,
  ENTREGADO: 8,
  EN_CAMINO: 9,
  ASIGNADO: 10,
};

/** Etiqueta, color y descripción de cada estado. */
export const ESTADO_DOM_CONFIG = {
  3:  { label: "Pendiente", desc: "Sin repartidor asignado", dot: "#f9a825", bg: "#fff8e1", border: "#ffe082" },
  10: { label: "Asignado",  desc: "Repartidor asignado, aún no sale", dot: "#1976d2", bg: "#e3f2fd", border: "#90caf9" },
  9:  { label: "En camino", desc: "En ruta de entrega", dot: "#6a1b9a", bg: "#f3e5f5", border: "#ce93d8" },
  8:  { label: "Entregado", desc: "Entregado al cliente", dot: "#43a047", bg: "#e8f5e9", border: "#a5d6a7" },
  5:  { label: "Cancelado", desc: "Cancelado", dot: "#c62828", bg: "#ffebee", border: "#ef9a9a" },
};

/** Estados que ya no admiten cambios. */
export const ESTADOS_DOM_FINALES = [ESTADO_DOMICILIO.ENTREGADO, ESTADO_DOMICILIO.CANCELADO];

/** Un domicilio está activo mientras no se haya entregado ni cancelado. */
export const esDomicilioActivo = (estadoId) =>
  !ESTADOS_DOM_FINALES.includes(Number(estadoId));

/**
 * Traducción de la numeración vieja de la app móvil (3=En camino, 4=Entregado).
 * El backend ya normaliza, pero la web se protege por si queda una respuesta
 * cacheada o un despliegue desfasado.
 */
const LEGACY_MOVIL = { 1: 3, 2: 3, 4: 8 };

export const normalizarEstadoDom = (valor, tieneRepartidor = false) => {
  const estado = Number(valor);
  if (!Number.isFinite(estado)) return null;
  if (LEGACY_MOVIL[estado] != null) return LEGACY_MOVIL[estado];
  // Un 3 con repartidor viene de la app vieja, donde significaba "En camino".
  if (estado === ESTADO_DOMICILIO.PENDIENTE && tieneRepartidor) {
    return ESTADO_DOMICILIO.EN_CAMINO;
  }
  return estado;
};

export const labelEstadoDom = (estadoId) =>
  ESTADO_DOM_CONFIG[Number(estadoId)]?.label || "Pendiente";

/**
 * Transiciones que el panel ofrece, por rol. Refleja el recorrido real del
 * domicilio y las reglas que ya aplica la app móvil:
 * - gestión (admin/empleado): puede corregir el recorrido completo.
 * - domiciliario: solo avanza a En camino o Entregado.
 * "Asignado" no se elige a mano: se alcanza al asignar repartidor.
 */
const TRANSICIONES_GESTION = {
  3:  [ESTADO_DOMICILIO.EN_CAMINO, ESTADO_DOMICILIO.CANCELADO],
  10: [ESTADO_DOMICILIO.EN_CAMINO, ESTADO_DOMICILIO.CANCELADO],
  9:  [ESTADO_DOMICILIO.ENTREGADO, ESTADO_DOMICILIO.CANCELADO],
  8:  [],
  5:  [],
};

const TRANSICIONES_REPARTIDOR = {
  3:  [],
  10: [ESTADO_DOMICILIO.EN_CAMINO],
  // Ya en ruta puede cerrarla como entregada o, si no pudo, cancelarla.
  9:  [ESTADO_DOMICILIO.ENTREGADO, ESTADO_DOMICILIO.CANCELADO],
  8:  [],
  5:  [],
};

/** Opciones de cambio de estado disponibles: [{ id, label }]. */
export const transicionesDom = (estadoId, esRepartidor = false) => {
  const tabla = esRepartidor ? TRANSICIONES_REPARTIDOR : TRANSICIONES_GESTION;
  return (tabla[Number(estadoId)] || []).map((id) => ({
    id,
    label: labelEstadoDom(id),
  }));
};

/** Opciones para el filtro de la tabla. */
/** Cambiar de domiciliario solo tiene sentido antes de que el pedido salga:
 *  después ya lo lleva alguien encima y reasignarlo desordena a los dos. */
export const puedeReasignarse = (estadoId) =>
  estadoId === ESTADO_DOMICILIO.PENDIENTE || estadoId === ESTADO_DOMICILIO.ASIGNADO;

export const FILTRO_ESTADOS_DOM = [
  { val: "todos",       label: "Todos",       dot: "#bdbdbd" },
  { val: "activos",     label: "Activos",     dot: "#43a047" },
  { val: ESTADO_DOMICILIO.PENDIENTE, label: "Pendiente", dot: ESTADO_DOM_CONFIG[3].dot },
  { val: ESTADO_DOMICILIO.ASIGNADO,  label: "Asignado",  dot: ESTADO_DOM_CONFIG[10].dot },
  { val: ESTADO_DOMICILIO.EN_CAMINO, label: "En camino", dot: ESTADO_DOM_CONFIG[9].dot },
  { val: ESTADO_DOMICILIO.ENTREGADO, label: "Entregado", dot: ESTADO_DOM_CONFIG[8].dot },
  { val: ESTADO_DOMICILIO.CANCELADO, label: "Cancelado", dot: ESTADO_DOM_CONFIG[5].dot },
  { val: "sin-asignar", label: "Sin asignar", dot: "#e53935" },
];

/**
 * Estados de pago con los que el backend permite marcar la entrega
 * (`_ESTADOS_PAGO_ENTREGA` en domicilios/services/service.py). Se replica aquí
 * solo para avisar ANTES de la llamada; la regla la sigue aplicando el backend.
 */
export const ESTADOS_PAGO_ENTREGA = [
  "efectivo_recibido", "pagado_completo", "anticipo_pagado",
  "no_recibido", "pendiente_validacion",
];

export const ESTADO_PAGO_LABEL = {
  pendiente:             { label: "Pago pendiente",       dot: "#f9a825", bg: "#fff8e1" },
  pendiente_validacion:  { label: "Comprobante por validar", dot: "#1976d2", bg: "#e3f2fd" },
  comprobante_rechazado: { label: "Comprobante rechazado", dot: "#c62828", bg: "#ffebee" },
  efectivo_recibido:     { label: "Efectivo recibido",    dot: "#43a047", bg: "#e8f5e9" },
  anticipo_pagado:       { label: "Anticipo pagado",      dot: "#43a047", bg: "#e8f5e9" },
  pagado_completo:       { label: "Pagado",               dot: "#43a047", bg: "#e8f5e9" },
  no_recibido:           { label: "Cobro no recibido",    dot: "#c62828", bg: "#ffebee" },
};

// Cómo se paga el pedido: vive en utils/metodosPago.js porque también lo
// necesita la pantalla de pedidos. Se re-exporta para no cambiar los imports
// de este módulo.
import { esPagoMixto, esPagoTransferencia, esPagoEfectivo, montoACobrar } from "../../../utils/metodosPago.js";
export { esPagoMixto, esPagoTransferencia, esPagoEfectivo, montoACobrar };

/**
 * ¿Este domicilio todavía tiene plata por cobrar en mano?
 *
 * Aplica a pedidos en efectivo/mixto/contraentrega Y a pedidos con anticipo
 * ya registrado que tienen saldo pendiente (la diferencia total − anticipo se
 * cobra en mano aunque el método de pago original sea transferencia).
 * Deja de aplicar en cuanto el repartidor registra el resultado.
 */
export const cobroEfectivoPendiente = (dom) => {
  if (!dom) return false;
  if (["efectivo_recibido", "no_recibido", "pagado_completo"].includes(dom.estado_pago)) return false;
  if (esPagoEfectivo(dom.metodo_pago)) return true;
  // Anticipo registrado con saldo pendiente: la diferencia se cobra en mano.
  return dom.anticipo_registrado === true &&
    (dom.anticipo_monto ?? 0) > 0 &&
    Number(dom.total || 0) > Number(dom.anticipo_monto || 0);
};

/**
 * Motivo por el que no se puede marcar entregado, o null si sí se puede.
 * Refleja la regla del backend: hace falta el cobro registrado, y el
 * comprobante solo se exige cuando el pago fue por transferencia (los pedidos
 * en efectivo se cobran en mano).
 */
export const bloqueoEntrega = (dom) => {
  if (!dom) return null;
  const pagoOk = ESTADOS_PAGO_ENTREGA.includes(dom.estado_pago || "");
  if (!pagoOk) {
    return "Falta registrar el cobro de este pedido antes de marcarlo como entregado.";
  }
  // En un mixto el comprobante solo hace falta si de verdad hubo una
  // transferencia: con el reparto en 100% efectivo no hay nada que adjuntar.
  const hayTransferencia = esPagoMixto(dom.metodo_pago)
    ? Number(dom.total || 0) - montoACobrar(dom) > 0
    : esPagoTransferencia(dom.metodo_pago);
  if (hayTransferencia && !dom.comprobante_pago) {
    return "El pago es por transferencia y no tiene comprobante adjunto.";
  }
  return null;
};
