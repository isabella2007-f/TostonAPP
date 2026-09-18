import { formatCOP } from "../../../utils/formato";
/* Constantes y helpers compartidos del detalle de insumos de una compra.
   Fuente única para CrearCompra, EditarCompra y DetalleInsumoFields. */

export const UNIDADES = [
  { id: 1, nombre: "Kilogramo", simbolo: "kg"   },
  { id: 2, nombre: "Gramo",     simbolo: "g"    },
  { id: 3, nombre: "Litro",     simbolo: "L"    },
  { id: 4, nombre: "Mililitro", simbolo: "ml"   },
  { id: 5, nombre: "Unidad",    simbolo: "uds." },
  { id: 6, nombre: "Libra",     simbolo: "lb"   },
];

export const GRUPO_UNIDAD = { 1: "masa", 2: "masa", 6: "masa", 3: "vol", 4: "vol", 5: "und" };

export const CANT_MAX = 10_000;

// Deja pasar dígitos y un punto decimal; rechaza signo, letras y separadores.
export const soloNumero = (v) => v === "" || /^\d*\.?\d*$/.test(v);

export const unidadesDelGrupo = (idUnidadBase) => {
  const grupo = GRUPO_UNIDAD[Number(idUnidadBase)];
  if (!grupo) return [];
  return UNIDADES.filter((u) => GRUPO_UNIDAD[u.id] === grupo);
};

// Factor de cada unidad respecto a la unidad mínima del grupo
// (masa → gramos, volumen → mililitros)
const _FACTOR_MASA = { 1: 1000, 2: 1, 6: 453.592 };   // kg=1000g, g=1g, lb≈453.6g
const _FACTOR_VOL  = { 3: 1000, 4: 1 };                // L=1000ml, ml=1ml

/**
 * Convierte cantidad y precioUnd a la unidad base del insumo.
 * Si las unidades son iguales o no son comparables, devuelve los mismos valores.
 */
export const convertirABase = (cantidad, precioUnd, idUnidadSeleccionada, idUnidadBase) => {
  const sel  = Number(idUnidadSeleccionada);
  const base = Number(idUnidadBase);
  if (!sel || !base || sel === base) return { cantidad, precioUnd };

  const fm = _FACTOR_MASA[sel] !== undefined && _FACTOR_MASA[base] !== undefined;
  const fv = _FACTOR_VOL[sel]  !== undefined && _FACTOR_VOL[base]  !== undefined;
  if (!fm && !fv) return { cantidad, precioUnd };

  const factorSel  = fm ? _FACTOR_MASA[sel]  : _FACTOR_VOL[sel];
  const factorBase = fm ? _FACTOR_MASA[base] : _FACTOR_VOL[base];
  const ratio = factorSel / factorBase;   // factor de conversión sel→base

  // cantidad_base = cantidad_sel * ratio
  // precio_base   = precio_sel  / ratio  (para mantener subtotal igual)
  return {
    cantidad:  cantidad  * ratio,
    precioUnd: precioUnd / ratio,
  };
};

export const COP = formatCOP;
