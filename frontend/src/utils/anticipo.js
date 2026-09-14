/**
 * A qué pedido se le pide anticipo.
 *
 * Espeja `_pide_anticipo` de `src/features/ventas/gestion_ventas/services/service.py`
 * y `EvaluacionSobreStock` de la app móvil. Las tres capas tienen que contestar
 * lo mismo: si el checkout no muestra el bloque del anticipo y el servidor sí lo
 * exige, el cliente arma todo el pedido y se lo rechazan al confirmar; y al
 * revés, se le pide plata por adelantado a quien no tenía por qué darla.
 *
 * Esto último fue lo que pasó: las dos pantallas tenían el anticipo clavado en
 * `true` y lo pedían en TODOS los pedidos, con stock de sobra y por cualquier
 * monto.
 */

/** Monto a partir del cual un pedido por encargo pide anticipo (COP). */
export const UMBRAL_ANTICIPO = 100000;

/** Porcentaje del pedido que se anticipa. */
export const PORCENTAJE_ANTICIPO = 0.5;

/**
 * ¿Esta línea del carrito hay que hornearla?
 *
 * Solo si el producto se fabrica y se pidió más de lo que hay: eso es lo que
 * genera una orden de producción. Lo que sale de la vitrina no arriesga nada.
 */
export const lineaPorProducir = (linea = {}) =>
  !!linea.requiereProduccion && (linea.cantidad || 0) > (linea.stock || 0);

/** ¿Hay algo en el carrito que haya que fabricar? */
export const hayQueProducir = (lineas = []) => lineas.some(lineaPorProducir);

/**
 * La regla completa: el total del pedido supera el umbral.
 *
 * `totalPedido` es lo que cuesta el pedido (productos − descuento + domicilio),
 * ANTES del saldo a favor: el mismo total con el que el servidor decide.
 * Ya no importa si hay que fabricar: cualquier pedido >= $100.000 pide anticipo.
 */
export const pideAnticipo = (_lineas, totalPedido) =>
  Number(totalPedido || 0) >= UMBRAL_ANTICIPO;

/**
 * Un producto cuenta como fabricable si está marcado o si tiene ficha técnica.
 *
 * Mismo criterio que `_productos_producibles` en el servidor: la ficha es la
 * receta, y al cargar el catálogo la marca se olvida. Mirando solo la marca, el
 * checkout no mostraría el anticipo de un producto que el servidor sí manda a
 * producir, y el pedido se rechazaría al confirmar.
 */
export const esFabricable = (producto = {}) =>
  !!(
    producto.Requiere_Produccion ||
    producto.requiere_produccion ||
    producto.requiereProduccion ||
    producto.ficha_tecnica
  );
