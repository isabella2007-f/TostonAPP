// Horario de atención de la tienda.
//
// La configuración vive en la landing (`getLandingConfig()`): `horaApertura` y
// `horaCierre` en formato "HH:MM" y `diasAtencion` como CSV de días ISO
// (1 = lunes … 7 = domingo). Estos helpers deciden si la tienda está abierta y
// arman los textos que se muestran al cliente (carrito, checkout, footer).

// Rango de fechas seleccionable para pedidos con producción.
// Espejo en backend: DIAS_MIN_PRODUCCION / MESES_MAX_PEDIDO en service.py.
export const DIAS_MIN_PRODUCCION = 7;
export const MESES_MAX_PEDIDO    = 6;

const HORA_APERTURA_DEF = "08:00";
const HORA_CIERRE_DEF   = "20:00";
// Se atiende todos los días. Es lo que rige mientras el administrador no
// configure otra cosa desde "Editar Landing Page".
const DIAS_DEF          = "1,2,3,4,5,6,7";

const parseHM = (s) => {
  const [h, m] = String(s || "").split(":").map(Number);
  return (Number.isFinite(h) ? h : 0) * 60 + (Number.isFinite(m) ? m : 0);
};

const fmt12 = (hm) => {
  const [h, m] = String(hm || "").split(":").map(Number);
  const H = Number.isFinite(h) ? h : 0;
  const M = Number.isFinite(m) ? m : 0;
  const ampm = H < 12 ? "am" : "pm";
  const h12  = H % 12 === 0 ? 12 : H % 12;
  return M ? `${h12}:${String(M).padStart(2, "0")} ${ampm}` : `${h12}:00 ${ampm}`;
};

/** Día ISO (1..7) de una fecha. JS usa 0=domingo. */
const diaISO = (d) => (d.getDay() === 0 ? 7 : d.getDay());

/** Set de días ISO en los que se atiende. */
export const diasAtencionSet = (cfg) =>
  new Set(
    String(cfg?.diasAtencion ?? DIAS_DEF)
      .split(",")
      .map((s) => parseInt(s, 10))
      .filter((n) => n >= 1 && n <= 7)
  );

/** ¿La tienda está abierta ahora (o en la fecha dada)? */
export const estaAbierto = (cfg, ahora = new Date()) => {
  if (!diasAtencionSet(cfg).has(diaISO(ahora))) return false;
  const ap  = parseHM(cfg?.horaApertura ?? HORA_APERTURA_DEF);
  const ci  = parseHM(cfg?.horaCierre ?? HORA_CIERRE_DEF);
  const cur = ahora.getHours() * 60 + ahora.getMinutes();
  return cur >= ap && cur < ci;
};

/** Texto para el cliente cuando hace un pedido fuera del horario. */
export const mensajeFueraHorario = (cfg, ahora = new Date()) => {
  const dias  = diasAtencionSet(cfg);
  const iso   = diaISO(ahora);
  const ap    = parseHM(cfg?.horaApertura ?? HORA_APERTURA_DEF);
  const cur   = ahora.getHours() * 60 + ahora.getMinutes();
  const apTxt = fmt12(cfg?.horaApertura ?? HORA_APERTURA_DEF);

  if (dias.has(iso) && cur < ap) {
    return `Abrimos hoy a las ${apTxt}. Tu pedido quedará registrado y no se atenderá hasta que abramos.`;
  }

  const NOMBRE = { 1: "el lunes", 2: "el martes", 3: "el miércoles", 4: "el jueves", 5: "el viernes", 6: "el sábado", 7: "el domingo" };
  for (let i = 1; i <= 7; i++) {
    const d = ((iso - 1 + i) % 7) + 1;
    if (dias.has(d)) {
      const cuando = i === 1 ? "mañana" : NOMBRE[d];
      return `Estamos cerrados. Tu pedido quedará registrado y no se atenderá hasta ${cuando} a las ${apTxt}.`;
    }
  }
  return "Estamos fuera del horario de atención. Tu pedido quedará registrado y no se atenderá hasta que volvamos a abrir.";
};

/** "YYYY-MM-DD" de hoy + `dias` días (en la zona horaria local). */
const isoMasDias = (hoy, dias) => {
  const d = new Date(hoy);
  d.setDate(d.getDate() + dias);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
};

/**
 * Primer día seleccionable para "¿para cuándo necesitas tu pedido?": hoy
 * mismo si todavía se puede recibir (día de atención y antes de la hora de
 * cierre), si no el próximo día de atención. Espejo en JS de
 * `_fecha_minima_entrega` (backend) — la misma regla se valida ahí también,
 * esto solo evita que el cliente elija algo que el servidor va a rechazar.
 */
export const primeraFechaValida = (cfg, ahora = new Date()) => {
  const dias = diasAtencionSet(cfg);
  const iso  = diaISO(ahora);
  const ci   = parseHM(cfg?.horaCierre ?? HORA_CIERRE_DEF);
  const cur  = ahora.getHours() * 60 + ahora.getMinutes();

  if (dias.has(iso) && cur < ci) return isoMasDias(ahora, 0);

  for (let i = 1; i <= 7; i++) {
    const d = ((iso - 1 + i) % 7) + 1;
    if (dias.has(d)) return isoMasDias(ahora, i);
  }
  return isoMasDias(ahora, 0);
};

/**
 * Primer día seleccionable para un pedido con producción: el más tardío
 * entre el primer día hábil (lógica de horario) y hoy + DIAS_MIN_PRODUCCION.
 */
export const fechaMinimaPedido = (cfg, ahora = new Date()) => {
  const porHorario  = primeraFechaValida(cfg, ahora);
  const porMargen   = isoMasDias(ahora, DIAS_MIN_PRODUCCION);
  return porHorario >= porMargen ? porHorario : porMargen;
};

/** Último día seleccionable para un pedido: hoy + MESES_MAX_PEDIDO meses. */
export const fechaMaximaPedido = (ahora = new Date()) => {
  const d = new Date(ahora.getFullYear(), ahora.getMonth() + MESES_MAX_PEDIDO, ahora.getDate());
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Rango "8:00 am – 8:00 pm" con la config actual. */
export const rangoHorario = (cfg) =>
  `${fmt12(cfg?.horaApertura ?? HORA_APERTURA_DEF)} – ${fmt12(cfg?.horaCierre ?? HORA_CIERRE_DEF)}`;

/**
 * Filas para el bloque "Horario" del footer: agrupa días contiguos con el mismo
 * estado. Ej: [{dias:"Lun – Sáb", horas:"8:00 am – 8:00 pm", activo:true},
 *              {dias:"Dom", horas:"Cerrado", activo:false}]
 */
export const filasHorario = (cfg) => {
  const dias  = diasAtencionSet(cfg);
  const rango = rangoHorario(cfg);
  const ABBR  = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
  const rows  = [];
  let i = 0;
  while (i < 7) {
    const abre = dias.has(i + 1);
    let j = i;
    while (j + 1 < 7 && dias.has(j + 2) === abre) j++;
    rows.push({
      dias:  i === j ? ABBR[i] : `${ABBR[i]} – ${ABBR[j]}`,
      horas: abre ? rango : "Cerrado",
      activo: abre,
    });
    i = j + 1;
  }
  return rows;
};
