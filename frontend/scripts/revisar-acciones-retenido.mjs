/**
 * Las acciones del pedido retenido en tienda, verificadas contra las
 * validaciones del servidor (`cambiar_a_domicilio_retenido`,
 * `reintentar_pago_retenido`, `cancelar_retenido_en_tienda`).
 */
import {
  puedeEnviarADomicilio, puedeReintentarCobro, puedeCancelarRetenido,
  horasRetenido, fueraDePlazo,
} from '../src/features/ventas/pedidos/accionesRetenido.js';

let fallos = 0;
const comprobar = (que, real, esperado) => {
  if (real !== esperado) {
    fallos++;
    console.error(`  ✗ ${que}: esperaba ${esperado}, dio ${real}`);
  }
};

const recogida  = { domicilio: false };
const aDomicilio = { domicilio: true };

console.log('Acciones del pedido retenido en tienda');

// ── Enviárselo a domicilio ──────────────────────────────────────────
comprobar('el de recogida sí se puede enviar',
  puedeEnviarADomicilio(recogida, 2), true);

comprobar('el que ya es domicilio no: el servidor lo rechaza',
  puedeEnviarADomicilio(aDomicilio, 2), false);

comprobar('recién retenido, sin marca de hora, también se puede',
  puedeEnviarADomicilio(recogida, null), true);

comprobar('pasadas las 48h ya no',
  puedeEnviarADomicilio(recogida, 49), false);

// ── Reintentar el cobro ─────────────────────────────────────────────
comprobar('dentro de las 24h se reintenta',
  puedeReintentarCobro(3), true);

comprobar('pasadas las 24h ya no',
  puedeReintentarCobro(25), false);

comprobar('pasadas las 48h menos todavía',
  puedeReintentarCobro(60), false);

// ── Cancelar ────────────────────────────────────────────────────────
comprobar('cancelar siempre está', puedeCancelarRetenido(), true);

// ── El reloj ────────────────────────────────────────────────────────
const AHORA = new Date('2026-09-19T12:00:00Z').getTime();
comprobar('cuenta las horas desde que quedó retenido',
  Math.round(horasRetenido('2026-09-19T06:00:00Z', AHORA)), 6);

comprobar('sin fecha no inventa horas', horasRetenido(null, AHORA), null);
comprobar('sin horas no está fuera de plazo', fueraDePlazo(null), false);

if (fallos) {
  console.error(`\n${fallos} regla(s) mal.`);
  process.exit(1);
}
console.log('  ✓ todas las reglas dan lo esperado');
