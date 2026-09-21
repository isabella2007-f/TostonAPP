/**
 * Qué puede todavía hacer el cliente con su pedido.
 *
 * Espeja las reglas del servidor (`editar_mi_pedido` / `cancelar_pedido` en
 * `features/ventas/pedidos/services/service.py`) y de la app
 * (`lib/models/pedido_especial.dart`). La autoridad es el backend: esto
 * decide qué se MUESTRA, para no ofrecer un botón que el servidor va a
 * rechazar, ni esconder uno que sí funciona.
 *
 * Antes no había nada de esto: el botón "Editar pedido" salía en cualquier
 * pedido que no estuviera cancelado o entregado, así llevara tres días
 * confirmado. El aviso de los 10 minutos desaparecía solo (era un contador
 * aparte) y el botón se quedaba.
 */

/** Los 10 minutos en los que el pedido todavía es del cliente. */
export const VENTANA_EDICION_MS = 10 * 60 * 1000;

/** Estados desde los que el cliente puede cancelar (espeja el servidor). */
export const ESTADOS_CANCELABLES = [
  'Pendiente', 'Fecha propuesta', 'Fecha propuesta final',
  'Fecha rechazada', 'Escalado a admin', 'Esperando pago',
];

/**
 * Estados con la negociación de fecha abierta: ahí el cliente ajusta
 * cantidades y fecha aunque el reloj ya haya vencido, porque esa
 * conversación la abre el admin y ocurre después.
 */
export const ESTADOS_NEGOCIACION = ['Pendiente', 'Fecha propuesta'];

const ESTADOS_FINALES = ['Cancelado', 'Entregado'];

/** Estados de pago en los que la plata ya entró: no se toca nada. */
const ESTADOS_PAGO_CERRADOS = ['efectivo_recibido', 'pagado_completo', 'no_recibido'];

/**
 * Las fechas del servidor vienen en hora de Bogotá y SIN marca de zona, así
 * que `new Date(texto)` las interpreta como hora del navegador. Restarle
 * `Date.now()` a eso compara instantes absolutos y, en un navegador que no
 * esté en Bogotá, el resultado se corre por la diferencia horaria: un pedido
 * recién hecho podía nacer con la ventana ya vencida, o con horas de sobra.
 *
 * Acá se comparan relojes de pared, que es lo que las dos fechas de verdad
 * representan.
 */
const relojDeLaFecha = (texto) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(String(texto || ''));
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
};

const FORMATO_BOGOTA = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Bogota', hour12: false,
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
});

/** El reloj de pared de Bogotá, en la misma escala que `relojDeLaFecha`. */
export const relojDeAhora = (ahora = new Date()) => {
  const p = Object.fromEntries(
    FORMATO_BOGOTA.formatToParts(ahora).map(x => [x.type, x.value])
  );
  return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second);
};

/** Milisegundos que le quedan al pedido de ventana; 0 si ya venció. */
export const restanteDeVentana = (pedido, ahora = new Date()) => {
  const creado = relojDeLaFecha(pedido?.fecha_pedido || pedido?.Fecha_pedido);
  if (creado === null) return 0;
  return Math.max(0, VENTANA_EDICION_MS - (relojDeAhora(ahora) - creado));
};

export const dentroDeLaVentana = (pedido, ahora = new Date()) =>
  restanteDeVentana(pedido, ahora) > 0;

const pagoCerrado = (pedido) =>
  ESTADOS_PAGO_CERRADOS.includes(pedido?.estado_pago);

/**
 * ¿Puede cambiar cómo paga o cómo recibe el pedido?
 *
 * Es el arrepentimiento inmediato: vence con el reloj, en cualquier estado.
 * Adjuntar el comprobante de un pedido "Esperando pago" NO es esto —eso es
 * cumplir el pedido, y sigue disponible después (ver `puedePagar`).
 */
export const puedeEditarPedido = (pedido, ahora = new Date()) => {
  if (!pedido) return false;
  if (ESTADOS_FINALES.includes(pedido.estado)) return false;
  if (pedido.anticipo_registrado) return false;
  if (pagoCerrado(pedido)) return false;
  return dentroDeLaVentana(pedido, ahora);
};

/**
 * ¿Puede ajustar cantidades y fecha? Solo mientras la negociación de fecha
 * sigue abierta, y ahí el reloj no cuenta.
 */
export const puedeReabrirNegociacion = (pedido) =>
  !!pedido
  && ESTADOS_NEGOCIACION.includes(pedido.estado)
  && !!pedido.requiereFechaPropuesta
  && !pedido.anticipo_registrado;

/** ¿Tiene algo que hacer en el modal de edición? */
export const puedeAbrirEdicion = (pedido, ahora = new Date()) =>
  puedeEditarPedido(pedido, ahora) || puedeReabrirNegociacion(pedido);

/**
 * ¿Puede cancelar?
 *
 * Los 10 minutos valen para todos los estados: es el plazo del
 * arrepentimiento y se acaba igual para cualquier pedido. El servidor es más
 * permisivo —acepta cancelar mientras se negocia la fecha, sin reloj— pero
 * acá se ofrece lo más estrecho: nunca un botón que vaya a fallar, y una
 * sola regla que el cliente pueda entender. Es la misma que aplica la app.
 */
export const puedeCancelarPedido = (pedido, ahora = new Date()) => {
  if (!pedido) return false;
  if (!ESTADOS_CANCELABLES.includes(pedido.estado)) return false;
  if (pedido.anticipo_registrado) return false;
  return dentroDeLaVentana(pedido, ahora);
};

/** Cuánto hay que transferir según el método: lo que un comprobante respalda. */
export const montoATransferir = (metodo, total, efectivo) => {
  const t = Number(total) || 0;
  if (metodo === 'Mixto') return Math.max(0, t - (Number(efectivo) || 0));
  if (metodo === 'Transferencia') return t;
  return 0;
};

/**
 * ¿El carrito lleva algo que hay que hornear?
 *
 * Una línea es "por encargo" cuando el producto se fabrica y se piden más
 * unidades de las que hay en vitrina: ese faltante abre una orden de
 * producción. Es el mismo criterio con el que el servidor decide
 * `Necesita_Produccion` al crear la venta.
 */
export const llevaProduccion = (items) =>
  (items || []).some(
    (it) => it?.requiereProduccion && (it.cantidad || 0) > (it.stock ?? 0)
  );

/**
 * ¿Se puede pagar en efectivo?
 *
 * Un encargo no: el efectivo se cobra al recibir, cuando el pedido ya se
 * produjo y los insumos ya se gastaron, así que no respalda nada. El
 * servidor lo rechaza al crear y al editar; acá se deja de ofrecer, que es
 * lo que evita el botón que no hace nada.
 */
export const permiteEfectivo = ({ porEncargo }) => !porEncargo;

/** ¿Este método necesita que alguien revise un comprobante? */
export const llevaTransferencia = (metodo) =>
  metodo === 'Transferencia' || metodo === 'Mixto';
