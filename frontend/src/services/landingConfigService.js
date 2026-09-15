import { apiFetch } from "../utils/api";

export const LANDING_DEFAULTS = {
  heroBadge:          "SABOR NATURAL 100%",
  heroTitle:          "El poder del Plátano",
  heroDescription:    "Descubre tostones, chips y delicias artesanales que redefinen el sabor de nuestra tierra. Crujientes, frescos y recolectados con amor.",
  historyTitle:       "Desde el campo hasta tu mesa",
  historyDescription: "En Tostón App celebramos la tierra. Cada plátano es seleccionado para garantizar una experiencia épica y natural.",
  ctaTitle:           "Únete a la Revolución",
  ctaDescription:     "Estamos transformando la forma en que el mundo ve al plátano.",
  contactPhone1:         "321 754 3305",
  contactPhone2:         "313 789 9946",
  // Correo de contacto para la escalación a admin (3.4.1): mailto: en el
  // aviso de "Escalado a admin" de PedidosClientePage.jsx.
  contactEmail:          "",
  contactAddressLine:    "Carrera 38A No. 80-12",
  contactCity:           "Barranquilla, Colombia",
  contactInstagramUrl:   "https://www.instagram.com/tostonesbroms?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw==",
  contactInstagramHandle:"@tostonesbroms",
  // Punto exacto del local en el mapa (editable en "Editar Landing Page"). Si
  // están en null, el footer geocodifica la dirección como respaldo.
  mapLat:                null,
  mapLng:                null,
  // Horario de atención (solo lo edita un admin). Gobierna el aviso de "fuera
  // de horario" del carrito y el checkout. diasAtencion = CSV ISO (1=Lun … 7=Dom).
  horaApertura:          "08:00",
  horaCierre:            "20:00",
  diasAtencion:          "1,2,3,4,5,6,7",
  // Monto mínimo del pedido (sin domicilio) para habilitar entrega a domicilio.
  // 0 = sin mínimo requerido.
  pedidoMinimo:          0,
};

export async function getLandingConfig() {
  try {
    const data = await apiFetch("/configuracion/landing");
    // Mezcla los defaults con lo que devuelve el backend
    // (los campos null en el backend usan el default)
    const merged = { ...LANDING_DEFAULTS };
    for (const key of Object.keys(LANDING_DEFAULTS)) {
      if (data[key] != null) merged[key] = data[key];
    }
    return merged;
  } catch {
    return { ...LANDING_DEFAULTS };
  }
}

export async function saveLandingConfig(config) {
  return apiFetch("/configuracion/landing", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

export async function resetLandingConfig() {
  await saveLandingConfig(
    Object.fromEntries(Object.keys(LANDING_DEFAULTS).map(k => [k, LANDING_DEFAULTS[k]]))
  );
  return { ...LANDING_DEFAULTS };
}
