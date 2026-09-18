/**
 * La foto de perfil, pedida del tamaño en que se va a ver.
 *
 * Se estaba mostrando la imagen original —a veces de varios miles de píxeles—
 * dentro de un círculo de 32, y en pantallas de mucha densidad se veía
 * pixelada: el navegador encoge como puede, sin saber que el recorte importa.
 *
 * Cloudinary sabe recortarla en su servidor si se le pide en la URL, así que
 * se le pide: el cuadrado exacto, centrado en la cara, al doble de píxeles
 * para pantallas retina, con el formato y la calidad que mejor le venga al
 * navegador. De paso pesa una fracción de lo que pesaba.
 */

/** Cuánto se le pide de más para que se vea nítida en pantallas densas. */
const DENSIDAD = 2;

/**
 * URL de Cloudinary redimensionada para una imagen de producto.
 * `c_limit` limita el ancho sin recortar ni estirar imágenes más pequeñas.
 * `q_auto,f_auto`: calidad y formato óptimos para el navegador (WebP cuando lo soporta).
 */
export function urlProductImg(url, maxW = 800) {
  const u = (url || '').trim();
  if (!u) return '';
  const marca = '/image/upload/';
  const corte = u.indexOf(marca);
  if (!u.startsWith('https://res.cloudinary.com/') || corte === -1) return u;
  const inicio = corte + marca.length;
  const resto = u.slice(inicio);
  if (/^[a-z]+_[^/]+\//.test(resto)) return u;
  return `${u.slice(0, inicio)}c_limit,w_${maxW},q_auto,f_auto/${resto}`;
}

/**
 * `url` recortada a un cuadrado de `lado` píxeles CSS.
 *
 * Lo que no sea una imagen de Cloudinary se devuelve tal cual: una URL de otro
 * lado o un `data:` no entienden estas instrucciones y romperlas sería peor
 * que mostrarlas grandes.
 */
export function urlAvatar(url, lado = 32) {
  const u = (url || '').trim();
  if (!u) return '';

  const marca = '/image/upload/';
  const corte = u.indexOf(marca);
  if (!u.startsWith('https://res.cloudinary.com/') || corte === -1) return u;

  const inicio = corte + marca.length;
  const resto = u.slice(inicio);

  // Si alguien ya le puso transformaciones, se respetan: volver a recortar
  // encima da resultados difíciles de explicar. Una carpeta que se llamara
  // como una transformación caería acá también, y lo único que pasaría es que
  // esa foto se vería como hasta ahora.
  if (/^[a-z]+_[^/]+\//.test(resto)) return u;

  const px = Math.round(lado * DENSIDAD);
  // c_fill + g_face: recorta al cuadrado sin deformar y deja la cara adentro.
  // q_auto + f_auto: la calidad y el formato que mejor le venga al navegador.
  const receta = `c_fill,g_face,w_${px},h_${px},q_auto,f_auto`;
  return `${u.slice(0, inicio)}${receta}/${resto}`;
}
