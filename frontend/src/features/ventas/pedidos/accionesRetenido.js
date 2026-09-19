/**
 * Qué se puede hacer con un pedido «Retenido en tienda».
 *
 * A ese estado se llega por dos caminos distintos, y no admiten las mismas
 * salidas:
 *
 * - Recogida en tienda: el cliente no volvió o no se le pudo cobrar
 *   (`marcar_retenido_en_tienda`, solo para pedidos SIN domicilio).
 * - Domicilio: el repartidor no pudo cobrar ni entregar, volvió a la tienda y
 *   el pedido pasó por «En ruta de retorno».
 *
 * Espeja las validaciones del servidor en
 * `features/ventas/pedidos/services/service.py`. Ofrecer una acción que el
 * backend va a rechazar es peor que no ofrecerla: el administrador llena el
 * formulario y recibe un error.
 */

/** Horas desde que quedó retenido, o null si no hay marca. */
export const horasRetenido = (fechaRetenido, ahora = Date.now()) => {
  if (!fechaRetenido) return null;
  const t = new Date(fechaRetenido).getTime();
  if (Number.isNaN(t)) return null;
  return (ahora - t) / 3_600_000;
};

/** Ventana para reintentar el cobro, y plazo total antes de cancelar. */
export const VENTANA_REINTENTO_H = 24;
export const VENTANA_LIMITE_H = 48;

export const fueraDePlazo = (horas) =>
  horas !== null && horas >= VENTANA_LIMITE_H;

/**
 * ¿Se puede reintentar el cobro? Solo dentro de las primeras 24 horas.
 */
export const puedeReintentarCobro = (horas) =>
  !fueraDePlazo(horas) && (horas === null || horas < VENTANA_REINTENTO_H);

/**
 * ¿Se le puede mandar a domicilio?
 *
 * Solo si NO tiene uno ya. El servidor lo rechaza de plano —«Este pedido ya
 * tiene un domicilio asociado»— porque esta acción CREA el domicilio y le
 * suma el costo al total; no cambia el repartidor de uno que ya existe.
 *
 * Es, además, la única salida útil del pedido de recogida que nadie vino a
 * buscar: en vez de cancelarlo, se le lleva.
 */
export const puedeEnviarADomicilio = (pedido, horas) =>
  !fueraDePlazo(horas) && !pedido?.domicilio;

/** Cancelar siempre está disponible, y pasadas las 48h es lo único que queda. */
export const puedeCancelarRetenido = () => true;
