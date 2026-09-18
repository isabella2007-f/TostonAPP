/**
 * Las reglas de edición del cliente, verificadas contra los mismos casos que
 * cubre la suite del servidor (`tests/test_edicion_pedido_cliente.py`).
 *
 * El proyecto no tiene corredor de pruebas en el frontend; esto se ejecuta
 * con `node` y falla con código 1, que es lo que necesita `npm run lint`.
 */
import {
  puedeEditarPedido, puedeCancelarPedido, puedeReabrirNegociacion,
  restanteDeVentana, montoATransferir,
} from '../src/features/sales/orders/reglasEdicionCliente.js';

let fallos = 0;
const comprobar = (que, real, esperado) => {
  const ok = JSON.stringify(real) === JSON.stringify(esperado);
  if (!ok) {
    fallos++;
    console.error(`  ✗ ${que}: esperaba ${esperado}, dio ${real}`);
  }
};

// Un reloj fijo, para que las pruebas no dependan de la hora en que corran.
const AHORA = new Date('2026-09-18T15:00:00Z');   // 10:00 en Bogotá
const pedido = (extra = {}) => ({
  estado: 'Esperando pago',
  fecha_pedido: '2026-09-18T09:55:00',            // hace 5 minutos
  estado_pago: 'pendiente',
  anticipo_registrado: false,
  ...extra,
});

console.log('Reglas de edición del pedido (cliente)');

comprobar('dentro de los 10 min se edita',
  puedeEditarPedido(pedido(), AHORA), true);

comprobar('pasados los 10 min no',
  puedeEditarPedido(pedido({ fecha_pedido: '2026-09-18T09:30:00' }), AHORA), false);

comprobar('confirmado y fuera de ventana, no',
  puedeEditarPedido(
    pedido({ estado: 'Confirmado', fecha_pedido: '2026-09-18T09:30:00' }), AHORA), false);

comprobar('confirmado pero recién hecho, sí',
  puedeEditarPedido(pedido({ estado: 'Confirmado' }), AHORA), true);

comprobar('entregado nunca',
  puedeEditarPedido(pedido({ estado: 'Entregado' }), AHORA), false);

comprobar('con el anticipo ya registrado, no',
  puedeEditarPedido(pedido({ anticipo_registrado: true }), AHORA), false);

comprobar('con el pago ya cobrado, no',
  puedeEditarPedido(pedido({ estado_pago: 'pagado_completo' }), AHORA), false);

comprobar('la negociación de fecha no mira el reloj',
  puedeReabrirNegociacion(pedido({
    estado: 'Pendiente', fecha_pedido: '2026-09-15T09:00:00',
    requiereFechaPropuesta: true,
  })), true);

comprobar('cancelar esperando pago, sin reloj',
  puedeCancelarPedido(pedido({ fecha_pedido: '2026-09-15T09:00:00' }), AHORA), true);

comprobar('cancelar pendiente pasada la ventana, no',
  puedeCancelarPedido(
    pedido({ estado: 'Pendiente', fecha_pedido: '2026-09-18T09:30:00' }), AHORA), false);

comprobar('cancelar pendiente recién hecho, sí',
  puedeCancelarPedido(pedido({ estado: 'Pendiente' }), AHORA), true);

comprobar('un pedido caro sin pagar se cancela',
  puedeCancelarPedido(pedido({ requiere_anticipo: true }), AHORA), true);

comprobar('confirmado no se cancela desde acá',
  puedeCancelarPedido(pedido({ estado: 'Confirmado' }), AHORA), false);

comprobar('quedan 5 minutos', Math.round(restanteDeVentana(pedido(), AHORA) / 60000), 5);

comprobar('el mixto transfiere el resto', montoATransferir('Mixto', 20000, 8000), 12000);
comprobar('la transferencia cubre el total', montoATransferir('Transferencia', 20000, 0), 20000);
comprobar('el efectivo no transfiere nada', montoATransferir('Efectivo', 20000, 0), 0);

if (fallos) {
  console.error(`\n${fallos} regla(s) mal.`);
  process.exit(1);
}
console.log('  ✓ todas las reglas dan lo esperado');
