import { crearPedido } from '../../../../services/pedidosService';
import { getCart } from './cartService';
import { getUser } from '../../../../services/authService';

/**
 * Envío de un pedido hecho por el cliente.
 *
 * Existe porque el checkout se abre desde dos pantallas —la landing y "Hacer
 * pedidos"— y cada una tenía su propia copia de este envío. Con un solo
 * camino, una mejora aquí vale para las dos pantallas.
 *
 * Arma el cuerpo que espera la API. Lanza un Error con el motivo si algo
 * falla; quien llama decide qué mostrar y qué hacer después (limpiar carrito,
 * cerrar el modal, avisar…).
 */

/**
 * Datos de entrega finales: el modal puede haberlos cambiado respecto a lo que
 * traía el carrito. También lo usa la pantalla de pedidos para ofrecer guardar
 * la dirección después de confirmar.
 */
export const resolverEntrega = (deliveryInfo, orderDetails) => ({
  tieneDomicilio: deliveryInfo?.tieneDomicilio ?? orderDetails?.tieneDomicilio ?? false,
  address:        deliveryInfo?.address        || orderDetails?.address        || '',
  // El barrio de entrega es ahora un ID (módulo Ubicaciones): determina el
  // precio del domicilio, que el backend resuelve y congela como snapshot.
  idBarrio:       deliveryInfo?.idBarrio       ?? orderDetails?.idBarrio       ?? null,
  municipio:      deliveryInfo?.municipio      || orderDetails?.municipio      || '',
  departamento:   deliveryInfo?.departamento   || orderDetails?.departamento   || '',
  date:           deliveryInfo?.date           || orderDetails?.date           || '',
  time:           deliveryInfo?.time           || '',
  observaciones:  deliveryInfo?.observaciones  || orderDetails?.observaciones  || null,
});

/** Método de pago tal como lo guarda la API, sin emojis ni variantes. */
const metodoPagoApi = (metodo) =>
  metodo === 'digital' ? 'Transferencia'
  : metodo === 'mixto' ? 'Mixto'
  : 'Efectivo';

/** Fecha de entrega en el formato que espera la API, o null. */
const fechaEntregaApi = (fecha, hora) =>
  fecha ? `${fecha}T${hora || '00:00'}:00` : null;

export async function crearPedidoCliente({
  paymentMethod,
  saldoAFavor,
  deliveryInfo,
  orderDetails,
}) {
  const usuario = getUser();
  const carrito = getCart();

  const entrega = resolverEntrega(deliveryInfo, orderDetails);

  // El comprobante ya no se sube al crear el pedido: si no necesita
  // producción, se adjunta después desde "Mis pedidos" ('Esperando pago'); si
  // necesita producción, se pide (junto con el anticipo, si aplica) recién
  // cuando el admin apruebe la fecha de entrega.
  const payload = {
    ID_Usuario:  usuario?.id || null,
    productos:   carrito.map(item => ({
      ID_Producto: Number(item.id),
      Cantidad:    Number(item.cantidad),
    })),
    Metodo_Pago:            metodoPagoApi(paymentMethod),
    // Solo lo mira el backend cuando el método es Mixto: cuánta plata pone el
    // cliente en efectivo. Allá se recorta contra el total real.
    pago_efectivo_monto: paymentMethod === 'mixto'
      ? (saldoAFavor?.efectivoMonto ?? 0)
      : null,
    usar_credito:           !!saldoAFavor?.usar,
    // Cuanto de ese saldo se aplica. El backend lo toma como tope: si el
    // cliente pide mas de lo que tiene, alla se recorta.
    credito_monto:          saldoAFavor?.usar ? (saldoAFavor.monto ?? null) : null,
    codigo_descuento:       null,
    Fecha_entrega_esperada: fechaEntregaApi(entrega.date, entrega.time),

    domicilio: entrega.tieneDomicilio && entrega.address && entrega.idBarrio ? {
      Direccion_entrega:    entrega.address,
      // El barrio determina el precio del domicilio; el backend resuelve
      // nombre, ciudad, departamento y precio a partir de él.
      ID_Barrio:            Number(entrega.idBarrio),
      Municipio_entrega:    entrega.municipio    || null,
      Departamento_entrega: entrega.departamento || null,
      Observaciones:        entrega.observaciones,
    } : null,
  };

  return crearPedido(payload);
}
