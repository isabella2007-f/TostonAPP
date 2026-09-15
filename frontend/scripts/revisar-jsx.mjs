/**
 * Busca componentes usados en JSX que no están definidos en ninguna parte.
 *
 * Es el error que tumba una pantalla entera en el navegador —"RefreshCw is not
 * defined"— y que ni el linter ni el build ven:
 *
 * - `no-undef` de ESLint no mira dentro del JSX. La regla que sí lo hace
 *   (`react/jsx-no-undef`) viene en eslint-plugin-react, que no está instalado.
 * - Vite compila sin quejarse: un identificador suelto es un error de
 *   ejecución, no de compilación. Aparece cuando alguien abre la pantalla.
 *
 * Se pasó una vez en Gestión de Insumos y dejó el módulo inservible. Esto lo
 * encuentra antes, en un segundo y sin dependencias nuevas.
 *
 *   node scripts/revisar-jsx.mjs
 *
 * Sale con código 1 si encuentra algo, para poder usarlo en CI.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const RAIZ = new URL("../src", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");

/** Etiquetas JSX que no son componentes del archivo. */
const NO_SON_COMPONENTES = new Set([
  "Fragment", "React", "Suspense", "StrictMode", "Profiler",
]);

function archivos(dir) {
  const salida = [];
  for (const nombre of readdirSync(dir)) {
    const ruta = join(dir, nombre);
    if (statSync(ruta).isDirectory()) salida.push(...archivos(ruta));
    else if (/\.(jsx|tsx)$/.test(nombre)) salida.push(ruta);
  }
  return salida;
}

/**
 * Lo que el archivo tiene a mano: lo que importa, lo que declara y lo que
 * recibe por props. No hace falta ser exacto —cualquier mención del nombre
 * fuera del JSX cuenta— porque lo que se busca es el nombre que no aparece
 * en NINGUNA otra parte, que es el caso que revienta.
 */
function loQueConoce(codigo) {
  // Se le quitan las etiquetas JSX para no contarse a sí mismas.
  const sinJsx = codigo.replace(/<\/?[A-Z][\w.]*/g, " ");
  return new Set(sinJsx.match(/[A-Za-z_$][\w$]*/g) ?? []);
}

/**
 * True si esa línea es un comentario.
 *
 * Los ejemplos de uso escritos en comentarios —`<Route path=...>` dentro de un
 * bloque JSDoc— se denunciaban como componentes sin importar, y una
 * herramienta que grita en falso deja de mirarse.
 *
 * Se mira línea por línea, sin intentar quitar los comentarios del archivo
 * entero: hacerlo con expresiones regulares se traga código de verdad, porque
 * un literal como `/[^A-Za-z0-9]/` tiene barras y asteriscos que parecen el
 * principio de un comentario.
 */
function esComentario(linea) {
  const t = linea.trimStart();
  return t.startsWith("//") || t.startsWith("*") || t.startsWith("/*");
}

const problemas = [];

for (const ruta of archivos(RAIZ)) {
  const codigo = readFileSync(ruta, "utf8");
  const conocidos = loQueConoce(codigo);

  // <Componente ...> y <Componente/>. Solo los que empiezan en mayúscula:
  // los de minúscula son etiquetas de HTML.
  const vistos = new Map();
  codigo.split("\n").forEach((linea, i) => {
    if (esComentario(linea)) return;
    for (const m of linea.matchAll(/<([A-Z][\w]*)[\s/>]/g)) {
      if (!vistos.has(m[1])) vistos.set(m[1], i + 1);
    }
  });

  for (const [nombre, linea] of vistos) {
    if (NO_SON_COMPONENTES.has(nombre)) continue;
    if (conocidos.has(nombre)) continue;
    problemas.push(`${relative(RAIZ, ruta)}:${linea}  <${nombre}> no está definido`);
  }
}

if (problemas.length) {
  console.error(
    `\nComponentes usados sin importar (${problemas.length}).\n` +
    `Cada uno tumba su pantalla al abrirla:\n`
  );
  for (const p of problemas) console.error("  " + p);
  console.error("");
  process.exit(1);
}

console.log("Sin componentes sueltos: ningún JSX usa algo que no exista.");
