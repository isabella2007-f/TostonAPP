/**
 * El número con que se le escribe a alguien por WhatsApp.
 *
 * WhatsApp quiere el número con indicativo de país y sin nada más: ni
 * espacios, ni guiones, ni el `+`. Los teléfonos se guardan como los escribe
 * la gente ("300 123 4567", "+57 300-1234567"), así que hay que normalizarlo.
 *
 * El detalle que rompe esto es invisible: sin el 57 el enlace abre WhatsApp
 * igual, pero contesta que el número no existe. No dice "le falta el
 * indicativo", así que parece que el cliente dio mal el teléfono.
 *
 * Espejo de `numeroWhatsApp` en la app (lib/widgets/info_chips.dart).
 */
export const numeroWhatsApp = (telefono) => {
  // Un 0 al principio es de marcación nacional: no va al indicativo.
  const digitos = String(telefono ?? "")
    .replace(/\D/g, "")
    .replace(/^0+/, "");

  // Diez dígitos: el número colombiano de toda la vida, celular o fijo.
  if (digitos.length === 10) return `57${digitos}`;
  // Doce empezando por 57: ya viene con indicativo.
  if (digitos.length === 12 && digitos.startsWith("57")) return digitos;

  // Cualquier otra cosa devuelve null a propósito. Rellenar a ojo un número
  // que no se entiende abre el chat de un desconocido, y eso es peor que no
  // ofrecer el botón.
  return null;
};

/**
 * El enlace para abrir la conversación, o null si el número no sirve.
 *
 * `mensaje` queda escrito en la caja de texto, sin enviarse: quien escribe lo
 * lee antes de mandarlo y lo cambia si quiere.
 */
export const enlaceWhatsApp = (telefono, mensaje) => {
  const numero = numeroWhatsApp(telefono);
  if (!numero) return null;
  const texto = String(mensaje ?? "").trim();
  return texto
    ? `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`
    : `https://wa.me/${numero}`;
};

/**
 * El saludo que el domiciliario tiene listo para mandar.
 *
 * Escribir de cero en cada entrega, con el casco puesto y la moto encendida,
 * es justamente lo que nadie hace.
 */
export const saludoDomiciliario = ({ nombre, numeroPedido, enCamino }) => {
  const primerNombre = String(nombre ?? "").trim().split(" ")[0];
  const saludo = primerNombre ? `Hola ${primerNombre}` : "Hola";
  const pedido = numeroPedido ? ` ${numeroPedido}` : "";
  return enCamino
    ? `${saludo}, soy tu domiciliario de Los Tostones Brom's. Voy en camino con tu pedido${pedido}.`
    : `${saludo}, soy tu domiciliario de Los Tostones Brom's. Te escribo por tu pedido${pedido}.`;
};
