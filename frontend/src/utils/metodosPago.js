/**
 * Cómo se paga un pedido (Ventas.Metodo_Pago).
 *
 * Vivían dentro del módulo de domicilios, pero son del pedido: la pantalla de
 * gestión de pedidos preguntaba por su cuenta con `.includes("transfer")` y
 * `.includes("efectivo")`, y por eso un pedido mixto se quedaba sin el botón
 * de revisar comprobante y sin el de registrar el cobro — no coincidía con
 * ninguna de las dos.
 */

/**
 * Pago mixto: el pedido se reparte entre efectivo y transferencia. Lleva las
 * dos cargas a la vez —comprobante por lo transferido, cobro en mano por lo
 * demás—, así que las dos preguntas de abajo le dicen que sí.
 */
export const esPagoMixto = (metodo) => /mixto/i.test(metodo || "");

/** ¿Hay un comprobante que revisar? */
export const esPagoTransferencia = (metodo) =>
  /transf|nequi|daviplata|bancol|qr/i.test(metodo || "") || esPagoMixto(metodo);

/** ¿Hay plata que cobrar en mano? */
export const esPagoEfectivo = (metodo) =>
  /efectiv|contra|cash/i.test(metodo || "") || esPagoMixto(metodo);

/**
 * Cuánto hay que cobrar en mano.
 * - Pago mixto: solo la parte en efectivo (monto_efectivo).
 * - Anticipo ya registrado: solo el saldo pendiente (total − anticipo_monto).
 * - Resto: el total completo.
 */
export const montoACobrar = (pedido) => {
  if ((pedido?.monto_efectivo ?? null) !== null) return Number(pedido.monto_efectivo);
  if (pedido?.anticipo_registrado && (pedido?.anticipo_monto ?? 0) > 0)
    return Math.max(0, Number(pedido?.total || 0) - Number(pedido.anticipo_monto));
  return Number(pedido?.total || 0);
};

/** Cuánto entró (o va a entrar) por transferencia. */
export const montoTransferido = (pedido) =>
  (pedido?.monto_transferencia ?? null) !== null
    ? Number(pedido.monto_transferencia)
    : Math.max(0, Number(pedido?.total || 0) - montoACobrar(pedido));
