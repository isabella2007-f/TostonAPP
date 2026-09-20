import { useState, useEffect } from "react";
import { formatCOP } from "../../../utils/formato";
import {
  Check, X, Package, ClipboardList, Building2, Calendar, CreditCard, PenLine,
  AlertTriangle, CheckCircle2, Ban, Banknote, Receipt, Tag, Paperclip, Clock, ChevronDown,
} from "lucide-react";
import { getProveedores } from "../../../services/proveedoresService.js";
import { getInsumos } from "../../../services/insumosService.js";
import { getCompra } from "../../../services/comprasService.js";
import { fmtFecha } from "../../../utils/dateUtils";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import ImageLightbox from "../../../shared/components/ImageLightbox.jsx";
import { subirImagenCloudinary } from "../../../utils/cloudinary.js";
import DetalleInsumoFields from "./DetalleInsumoFields.jsx";
import { GRUPO_UNIDAD, CANT_MAX } from "./compraDetalleUtils.js";
import "./compras.css";

const TOTAL_MIN  = 0;
const TOTAL_MAX  = 50_000_000;
const PORC_MAX   = 100;   // IVA y descuento en % (admiten decimales)

const soloPorcentaje = (v) => v === "" || /^\d{0,3}(\.\d{0,2})?$/.test(v);
const soloEnteroTxt  = (v) => v === "" || /^\d{0,8}$/.test(v);
const bloquearSigno       = (e) => { if (["+", "-", "e", "E"].includes(e.key)) e.preventDefault(); };
const bloquearSignoYPunto = (e) => { if (["+", "-", "e", "E", ".", ","].includes(e.key)) e.preventDefault(); };

/* Íconos de estado — mismos que usa el listado de compras (GestionCompras) */
const ESTADO_ICON = { pendiente: Clock, completada: CheckCircle2, anulada: Ban };

function EstadoChip({ estado }) {
  const Icon = ESTADO_ICON[estado] || Clock;
  const label = String(estado || "").charAt(0).toUpperCase() + String(estado || "").slice(1);
  return (
    <span className={`estado-chip estado-chip--${estado}`}>
      <Icon size={13} /> {label}
    </span>
  );
}

const METODOS_PAGO = [
  { value: "efectivo",      label: "Efectivo",      Icon: Banknote  },
  { value: "transferencia", label: "Transferencia", Icon: Building2 },
];

const COP = formatCOP;

const calcularSubtotal = (items) =>
  (items || []).reduce((s, i) => s + (Number(i.cantidad) || 0) * (Number(i.precioUnd) || 0), 0);

const sumarDias = (n) => {
  const d = new Date();
  d.setDate(d.getDate() + Number(n));
  return d.toISOString().split("T")[0];
};

const diasHasta = (fecha) => {
  if (!fecha) return null;
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  return Math.round((new Date(fecha) - hoy) / (1000 * 60 * 60 * 24));
};

const emptyDetalle = () => ({
  _key:             Date.now() + Math.random(),
  idInsumo:         "",
  idUnidad:         "",
  cantidad:         "",
  precioUnd:        "",
  notas:            "",
  vencimientoTipo:  "dias",
  vencimientoValor: "30",
  fechaVencimiento: "",
});

const STEPS = [
  { idx: 1, label: "Información general" },
  { idx: 2, label: "Insumos comprados"   },
  { idx: 3, label: "Gastos adicionales"  },
];

function StepsBar({ current }) {
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "14px 28px", flexShrink: 0, background: "#fff", borderBottom: "1px solid #f0f0f0" }}>
      {STEPS.map((s, i) => {
        const done   = current > s.idx;
        const active = current === s.idx;
        return (
          <div key={s.idx} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : "none" }}>
            <div style={{ width: 30, height: 30, borderRadius: "50%", border: `2px solid ${active || done ? "#2e7d32" : "#d0d0d0"}`, background: done ? "#2e7d32" : "#fff", color: active ? "#2e7d32" : done ? "#fff" : "#bdbdbd", fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, transition: "all 0.2s" }}>
              {done ? <Check size={13} /> : s.idx}
            </div>
            <span style={{ marginLeft: 10, fontSize: 14, fontWeight: active ? 700 : 500, color: active ? "#2e7d32" : done ? "#9e9e9e" : "#bdbdbd", whiteSpace: "nowrap", transition: "color 0.2s" }}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && <div style={{ flex: 1, height: 1.5, background: done ? "#2e7d32" : "#e0e0e0", margin: "0 14px", transition: "background 0.2s" }} />}
          </div>
        );
      })}
    </div>
  );
}

/* ── Modal anular ───────────────────────────────────────── */
export function AnularCompraModal({ compra, onClose, onConfirm }) {
  const [confirming, setConfirming] = useState(false);
  const [checked,    setChecked]    = useState(false);

  const handleConfirm = async () => {
    if (!checked) return;
    setConfirming(true);
    await onConfirm(compra.id);
    setConfirming(false);
  };

  const yaCompletada = compra.stockAplicado === true || compra.estado === "completada";

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()}>
        <div style={{ padding: "28px 24px 18px", textAlign: "center" }}>
          <div className="delete-icon-wrap" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><Ban size={24} /></div>
          <h3 className="delete-title">Anular compra #{compra.id}</h3>
          {yaCompletada ? (
            <div className="stock-aviso stock-aviso--block" style={{ marginTop: 12, textAlign: "left" }}>
              <p style={{ margin: "0 0 6px" }}>
                <AlertTriangle size={13} style={{ verticalAlign: "middle" }} /> Esta compra ya fue <strong>completada</strong> y su stock fue aplicado al inventario.
                Al anularla, el sistema revierte el stock de cada insumo.
              </p>
              <p style={{ margin: 0, fontSize: 12, color: "#b71c1c" }}>
                Si cualquier lote de esta compra ya tuvo consumo (orden de producción, salida o cualquier
                descuento de stock), la anulación se bloquea por completo. Solo se puede anular si el 100%
                de lo comprado sigue disponible.
              </p>
            </div>
          ) : (
            <p className="delete-body" style={{ marginTop: 8 }}>
              La compra está <strong>pendiente</strong> — el stock aún no fue aplicado.
              La anulación no afectará el inventario.
            </p>
          )}
          <label style={{ display: "flex", alignItems: "flex-start", gap: 10, marginTop: 18, textAlign: "left", cursor: "pointer", fontSize: 13, color: "#424242" }}>
            <input
              type="checkbox"
              checked={checked}
              onChange={e => setChecked(e.target.checked)}
              style={{ marginTop: 2, accentColor: "#c62828", flexShrink: 0 }}
            />
            Entiendo las consecuencias y confirmo la anulación.
          </label>
        </div>
        <div className="modal-footer modal-footer--center">
          <button className="btn-ghost" onClick={onClose} disabled={confirming}>Cancelar</button>
          <button
            className="btn-danger"
            onClick={handleConfirm}
            disabled={!checked || confirming}
          >
            {confirming ? "Anulando…" : "Confirmar Anulación"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Lote (3.15 / 3.16): fila con datos de consumo, opcionalmente desplegable ── */
function LoteRow({ lote, unidad, destacado = false }) {
  const uni = unidad || "uds.";
  return (
    <div className={"compra-det-lote-item" + (lote.vencido ? " compra-det-lote-item--vencido" : "") + (destacado ? " compra-det-lote-item--origen" : "")}>
      <div className="compra-det-lote-item__main">
        <div className="compra-det-lote-item__num">
          Lote #{lote.id}
          {lote.vencido && <span className="compra-det-lote-badge--vencido">Vencido</span>}
          {destacado && <span className="compra-det-lote-badge--origen">Esta compra</span>}
        </div>
        <div className="compra-det-lote-item__meta">
          {lote.idCompra ? `Compra de origen: #${lote.idCompra}` : "Compra de origen: —"}
          {lote.fechaVencimiento && ` · Vence: ${fmtFecha(lote.fechaVencimiento)}`}
        </div>
        <div className="compra-det-lote-item__meta">
          Comprado: {lote.cantidadInicial} {uni} · Restante: {lote.cantidadActual} {uni}
          {lote.consumido > 0 && ` · Consumido: ${lote.consumido} ${uni}`}
        </div>
      </div>
      <div className="compra-det-lote-item__qty">
        <span className="compra-det-lote-item__qty-num">{lote.cantidadActual}</span>
        <span className="compra-det-lote-item__qty-unit">{uni}</span>
      </div>
    </div>
  );
}

function LotesInsumoGrupo({ item, insumosActivos = [] }) {
  const [abierto, setAbierto] = useState(false);
  const ins    = insumosActivos.find(i => i.id === Number(item.idInsumo));
  const uni    = item.unidad || ins?.unidad || "";
  const nombre = item.nombre || ins?.nombre || "Insumo";
  const otros  = item.otrosLotes || [];

  return (
    <div className="compra-det-lote-grupo">
      <div className="compra-det-lote-grupo__header">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Package size={14} /> {nombre}</span>
        <span className="compra-det-lote-grupo__qty">{item.cantidad} {uni} comprados</span>
      </div>

      {item.loteOrigen
        ? <LoteRow lote={item.loteOrigen} unidad={uni} destacado />
        : <div className="compra-det-lotes-empty">Sin lote registrado para este insumo</div>}

      {otros.length > 0 && (
        <>
          <button
            type="button"
            className="compra-det-lote-toggle"
            onClick={() => setAbierto(a => !a)}
          >
            <ChevronDown size={13} style={{ transform: abierto ? "rotate(180deg)" : "none", transition: "transform 0.15s" }} />
            {abierto ? "Ocultar" : `Ver otros ${otros.length} lote${otros.length === 1 ? "" : "s"} de este insumo`}
          </button>
          {abierto && otros.map(l => <LoteRow key={l.id} lote={l} unidad={uni} />)}
        </>
      )}
    </div>
  );
}

/* ── EditarCompra / VerCompra ───────────────────────────── */
export default function EditarCompra({ compra, mode, onClose, onSave }) {
  const [proveedores,    setProveedores]    = useState([]);
  const [insumosActivos, setInsumosActivos] = useState([]);

  useEffect(() => {
    getProveedores({ porPagina: 100 })
      .then(d => setProveedores(d.proveedores || d || []))
      .catch(() => {});
    getInsumos()
      .then(d => {
        const lista = (d.insumos || d || []).map(i => ({
          id:       i.ID_Insumo || i.id,
          nombre:   i.Nombre    || i.nombre || "",
          unidad:   i.simbolo_unidad || i.unidad || "",
          idUnidad: i.Unidad_Medida  || i.idUnidad || null,
          estado:   i.Estado !== 2,
        }));
        setInsumosActivos(lista.filter(i => i.estado));
      })
      .catch(() => {});
  }, []);

  const getProveedorById = (id) =>
    proveedores.find(p => String(p.ID_Proveedor || p.id) === String(id)) || null;

  const isView   = mode === "view";
  const isLocked = compra.stockAplicado === true;   // completada: stock aplicado
  const esAnulada = compra.estado === "anulada";

  const editable = {
    proveedor:    compra.estado === "pendiente" && !isLocked,
    fecha:        compra.estado === "pendiente" && !isLocked,
    metodo:       !esAnulada,
    comprobante:  !esAnulada,
    notas:        !esAnulada,
    lineas:       compra.estado === "pendiente" && !isLocked,
    gastos:       compra.estado === "pendiente" && !isLocked,
    fechaLlegada: isLocked || compra.estado === "completada",
  };

  const hoy = new Date().toISOString().split("T")[0];

  /* ─────────── Estado del formulario ─────────── */
  const [step, setStep] = useState(1);

  const [form, setForm] = useState({
    idProveedor:   compra.idProveedor  || "",
    fecha:         compra.fecha        || "",
    metodoPago:    compra.metodoPago   || "",
    notas:         String(compra.notas || ""),
    fecha_llegada: compra.fecha_llegada || "",
  });

  const [comprobanteFile,    setComprobanteFile]    = useState(null);
  const [comprobantePreview, setComprobantePreview] = useState(null);
  const [comprobanteUrl,     setComprobanteUrl]     = useState(compra.comprobante || "");

  const onComprobanteFile = (file) => {
    if (!file) { setComprobanteFile(null); setComprobantePreview(null); return; }
    setComprobanteFile(file);
    const reader = new FileReader();
    reader.onload = (ev) => setComprobantePreview(ev.target.result);
    reader.readAsDataURL(file);
  };
  const quitarComprobante = () => {
    setComprobanteFile(null);
    setComprobantePreview(null);
    setComprobanteUrl("");
  };

  const [gastos, setGastos] = useState({
    transporte: compra.transporte         ? String(compra.transporte)         : "",
    iva:        compra.ivaPorcentaje       ? String(compra.ivaPorcentaje)      : "",
    descuento:  compra.descuentoPorcentaje ? String(compra.descuentoPorcentaje): "",
    otros:      compra.otros               ? String(compra.otros)              : "",
  });

  const validarGasto = (k, v) => {
    if (v === "") return "";
    const n = Number(v);
    if (k === "iva")       return (n < 0 || n > PORC_MAX) ? "El IVA debe estar entre 0 y 100%" : "";
    if (k === "descuento") return (n < 0 || n > PORC_MAX) ? "El descuento debe estar entre 0 y 100%" : "";
    if (n < 0) return "No puede ser negativo";
    if (v.length > 8) return "Máximo 8 dígitos";
    return "";
  };
  const setGasto = (k, v) => {
    const permitido = (k === "iva" || k === "descuento") ? soloPorcentaje(v) : soloEnteroTxt(v);
    if (!permitido) return;
    setGastos(g => ({ ...g, [k]: v }));
    setErrors(e => ({ ...e, [k]: validarGasto(k, v) }));
  };

  const [detalles, setDetalles] = useState(
    (compra.items || []).map((d, i) => ({
      _key:             d.idDetalle || d.idInsumo || `item-${i}`,
      idInsumo:         d.idInsumo ? String(d.idInsumo) : "",
      idUnidad:         d.idUnidad ? String(d.idUnidad) : "",
      cantidad:         d.cantidad != null ? String(d.cantidad) : "",
      precioUnd:        d.precioUnd != null ? String(d.precioUnd) : "",
      notas:            d.notas || "",
      vencimientoTipo:  "fecha",
      vencimientoValor: "30",
      fechaVencimiento: d.fechaVencimiento ? String(d.fechaVencimiento).split("T")[0] : "",
    }))
  );

  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const set = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    let err = "";
    if (k === "idProveedor" && !v) err = "Selecciona un proveedor";
    if (k === "fecha") {
      if (!v) err = "Ingresa la fecha";
      else if (v > hoy) err = "La fecha no puede ser futura";
    }
    if (k === "metodoPago" && !v) err = "El método de pago es obligatorio";
    setErrors(e => ({ ...e, [k]: err }));
  };

  const setDetalle = (key, field, value) =>
    setDetalles(ds => ds.map((d, i) => {
      if (d._key !== key) return d;
      const updated = { ...d, [field]: value };
      let err = "";
      if (field === "idInsumo" && !value) err = "Selecciona un insumo";
      if (field === "cantidad") {
        const n = Number(value);
        const grupo = GRUPO_UNIDAD[Number(updated.idUnidad)];
        const soloEntero = grupo === "und";
        if (!value || n <= 0) err = "Cantidad inválida";
        else if (soloEntero && !Number.isInteger(n)) err = "La cantidad debe ser un número entero";
        else if (n > CANT_MAX) err = `Máximo ${CANT_MAX.toLocaleString("es-CO")} por línea`;
      }
      if (field === "precioUnd") {
        if (!value || Number(value) <= 0) err = "El precio unitario debe ser mayor a $0";
      }
      if (field === "fechaVencimiento" && updated.vencimientoTipo === "fecha" && !value) err = "Ingresa la fecha";
      if (field === "vencimientoValor" && updated.vencimientoTipo === "dias" && (!value || Number(value) <= 0)) err = "Ingresa los días";
      const errKey = field === "idInsumo" ? `ins_${i}`
        : field === "cantidad" ? `cant_${i}`
        : field === "precioUnd" ? `precio_${i}`
        : (field === "fechaVencimiento" || field === "vencimientoValor") ? `venc_${i}`
        : null;
      if (errKey) setErrors(prev => ({ ...prev, [errKey]: err }));
      return updated;
    }));

  const addDetalle    = () => setDetalles(ds => [...ds, emptyDetalle()]);
  const removeDetalle = (key) => setDetalles(ds => ds.filter(d => d._key !== key));

  const idsSeleccionados = detalles.map(d => String(d.idInsumo)).filter(Boolean);

  const subtotalActual = calcularSubtotal(detalles);
  const gTransporte = Number(gastos.transporte) || 0;
  const gIvaPct     = Number(gastos.iva)        || 0;
  const gDescPct    = Number(gastos.descuento)  || 0;
  const gOtros      = Number(gastos.otros)      || 0;
  const valorIvaActual  = subtotalActual * gIvaPct  / 100;
  const valorDescActual = subtotalActual * gDescPct / 100;
  const totalActual = subtotalActual + gTransporte + valorIvaActual - valorDescActual + gOtros;

  /* ─────────── 3.18: detección de "sin cambios" ─────────── */
  // `compra` es un prop estable durante la vida del modal → const simple.
  const snapshotInicial = JSON.stringify({
    idProveedor: String(compra.idProveedor || ""),
    fecha:       compra.fecha || "",
    metodoPago:  compra.metodoPago || "",
    notas:       String(compra.notas || ""),
    fecha_llegada: compra.fecha_llegada || "",
    comprobante: compra.comprobante || "",
    gastos: {
      transporte: compra.transporte         ? String(compra.transporte)          : "",
      iva:        compra.ivaPorcentaje       ? String(compra.ivaPorcentaje)       : "",
      descuento:  compra.descuentoPorcentaje ? String(compra.descuentoPorcentaje) : "",
      otros:      compra.otros               ? String(compra.otros)               : "",
    },
    detalles: (compra.items || []).map(d => ({
      idInsumo:  String(d.idInsumo || ""),
      cantidad:  d.cantidad != null ? String(d.cantidad) : "",
      precioUnd: d.precioUnd != null ? String(d.precioUnd) : "",
      venc:      d.fechaVencimiento ? String(d.fechaVencimiento).split("T")[0] : "",
    })),
  });

  const snapshotActual = () => JSON.stringify({
    idProveedor: String(form.idProveedor || ""),
    fecha:       form.fecha || "",
    metodoPago:  form.metodoPago || "",
    notas:       String(form.notas || ""),
    fecha_llegada: form.fecha_llegada || "",
    comprobante: comprobanteFile ? "__nuevo__" : (comprobanteUrl || ""),
    gastos: {
      transporte: gastos.transporte, iva: gastos.iva, descuento: gastos.descuento, otros: gastos.otros,
    },
    detalles: detalles.map(d => ({
      idInsumo:  String(d.idInsumo || ""),
      cantidad:  d.cantidad || "",
      precioUnd: d.precioUnd || "",
      venc:      d.vencimientoTipo === "dias" ? sumarDias(d.vencimientoValor) : (d.fechaVencimiento || ""),
    })),
  });

  /* ─────────── Validación ─────────── */
  const validarInfo = () => {
    const e = {};
    if (editable.proveedor && !form.idProveedor) e.idProveedor = "Selecciona un proveedor";
    if (editable.fecha) {
      if (!form.fecha) e.fecha = "Ingresa la fecha";
      else if (form.fecha > hoy) e.fecha = "La fecha no puede ser futura";
    }
    if (!form.metodoPago) e.metodoPago = "El método de pago es obligatorio";
    return e;
  };

  const validarLineas = () => {
    const e = {};
    if (!editable.lineas) return e;
    if (!detalles.length) e.detalles = "Agrega al menos un insumo";
    detalles.forEach((d, i) => {
      const n = Number(d.cantidad);
      const grupo = GRUPO_UNIDAD[Number(d.idUnidad)];
      const soloEntero = grupo === "und";
      if (!d.idInsumo) e[`ins_${i}`] = "Selecciona un insumo";
      if (!d.cantidad || n <= 0) e[`cant_${i}`] = "Cantidad inválida";
      else if (soloEntero && !Number.isInteger(n)) e[`cant_${i}`] = "La cantidad debe ser un número entero";
      else if (n > CANT_MAX) e[`cant_${i}`] = `Máximo ${CANT_MAX.toLocaleString("es-CO")} por línea`;
      if (!d.precioUnd || Number(d.precioUnd) <= 0) e[`precio_${i}`] = "El precio unitario debe ser mayor a $0";
      if (d.vencimientoTipo === "fecha" && !d.fechaVencimiento) e[`venc_${i}`] = "Ingresa la fecha";
      else if (d.vencimientoTipo === "dias" && (!d.vencimientoValor || Number(d.vencimientoValor) <= 0)) e[`venc_${i}`] = "Ingresa los días";
    });
    return e;
  };

  const validarGastos = () => {
    const e = {};
    if (!editable.gastos) return e;
    ["iva", "descuento", "transporte", "otros"].forEach(k => {
      const msg = validarGasto(k, gastos[k]);
      if (msg) e[k] = msg;
    });
    if (totalActual < TOTAL_MIN) e.total = `El total (${COP(totalActual)}) no puede ser negativo`;
    else if (totalActual > TOTAL_MAX) e.total = `El total (${COP(totalActual)}) supera el máximo permitido de ${COP(TOTAL_MAX)} COP`;
    return e;
  };

  const handleNextStep = () => {
    const e = step === 1 ? validarInfo() : step === 2 ? validarLineas() : {};
    if (Object.keys(e).length) { setErrors(e); return; }
    setErrors({});
    setStep(s => s + 1);
  };

  const handleSave = async () => {
    if (saving) return;

    // 3.18 — se abrió y no se tocó nada: no se dispara ninguna escritura.
    if (snapshotActual() === snapshotInicial) {
      onSave({ sinCambios: true });
      return;
    }

    const e = { ...validarInfo(), ...validarLineas(), ...validarGastos() };
    if (Object.keys(e).length) { setErrors(e); return; }

    setSaving(true);

    // Comprobante
    let comprobanteOut = "";
    if (form.metodoPago === "transferencia") {
      if (comprobanteFile) {
        try {
          comprobanteOut = await subirImagenCloudinary(comprobanteFile);
        } catch {
          setErrors(prev => ({ ...prev, comprobante: "No se pudo subir el comprobante. Intenta de nuevo." }));
          setSaving(false);
          return;
        }
      } else {
        comprobanteOut = comprobanteUrl || "";
      }
    }

    // Payload explícito: solo los campos editables en el estado actual. Los que
    // no lo son NO se envían (el backend rechaza campos no permitidos).
    const payload = {
      id:         compra.id,
      metodoPago: form.metodoPago,
      notas:      form.notas,
      comprobante: comprobanteOut,
    };
    if (editable.fechaLlegada) payload.fecha_llegada = form.fecha_llegada || "";
    if (editable.proveedor)    payload.idProveedor   = form.idProveedor;
    if (editable.fecha)        payload.fecha         = form.fecha;
    if (editable.lineas) {
      payload.detalles = detalles.map(d => ({
        idInsumo:  Number(d.idInsumo),
        idUnidad:  d.idUnidad ? Number(d.idUnidad) : null,
        cantidad:  Number(d.cantidad),
        precioUnd: Number(d.precioUnd),
        notas:     d.notas?.trim() || "",
        fechaVencimiento: d.vencimientoTipo === "dias" ? sumarDias(d.vencimientoValor) : (d.fechaVencimiento || ""),
      }));
    }
    if (editable.gastos) {
      payload.gastos = { transporte: gTransporte, iva: gIvaPct, descuento: gDescPct, otros: gOtros };
    }
    onSave(payload);
  };

  const modalStyle = {
    maxWidth: 860,
    width: "95vw",
    display: "flex",
    flexDirection: "column",
    maxHeight: "92vh",
    overflow: "hidden",
  };

  /* ═══════════════ VISTA DETALLE (mode="view") ═══════════════ */
  if (isView) {
    return <VerCompra compraBase={compra} onClose={onClose} getProveedorById={getProveedorById} insumosActivos={insumosActivos} />;
  }

  /* ═══════════════ MODO EDITAR (wizard de 3 pasos) ═══════════════ */
  const provNombre = (() => {
    const p = getProveedorById(form.idProveedor);
    return compra.proveedor || p?.Responsable || p?.responsable || "—";
  })();

  const renderComprobante = () => (
    <div className="field-wrap comprobante-wrap">
      <label className="field-label">Comprobante de transferencia</label>
      {editable.comprobante ? (
        <>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label className="comprobante-upload-btn" style={{ flex: 1 }}>
              <input type="file" accept="image/*" style={{ display: "none" }}
                onChange={e => onComprobanteFile(e.target.files?.[0] || null)} />
              <span className="comprobante-upload-icon" style={{ display: "flex", alignItems: "center" }}><Paperclip size={16} /></span>
              {comprobanteFile
                ? <span className="comprobante-filename">{comprobanteFile.name}</span>
                : comprobanteUrl
                  ? <span className="comprobante-filename">Comprobante adjunto</span>
                  : <span>Adjuntar comprobante (imagen)</span>}
            </label>
            {(comprobanteFile || comprobanteUrl) && (
              <button type="button" onClick={quitarComprobante}
                style={{ flexShrink: 0, padding: "0 12px", height: 36, borderRadius: 8, border: "1.5px solid #ef5350", background: "#fff", color: "#c62828", fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                <X size={14} /> Quitar
              </button>
            )}
          </div>
          {(comprobantePreview || comprobanteUrl) && (
            <div style={{ marginTop: 8 }}>
              <ImageLightbox src={comprobantePreview || comprobanteUrl} alt="Comprobante" label="Comprobante de transferencia" thumbStyle={{ maxWidth: 220 }} />
            </div>
          )}
          {errors.comprobante
            ? <span className="field-error">{errors.comprobante}</span>
            : <span className="field-hint">Opcional — puedes adjuntarlo ahora o más tarde</span>}
        </>
      ) : (
        comprobanteUrl
          ? <ImageLightbox src={comprobanteUrl} alt="Comprobante" label="Comprobante de transferencia" thumbStyle={{ maxWidth: 220 }} />
          : <span className="field-hint">Sin comprobante adjunto.</span>
      )}
    </div>
  );

  return (
    <div className="modal-overlay">
      <div className="modal-card" onClick={e => e.stopPropagation()} style={modalStyle}>

        <div className="modal-header" style={{ flexShrink: 0, padding: "18px 28px" }}>
          <div>
            <p className="modal-header__eyebrow">Compras · {compra.id}</p>
            <h2 className="modal-header__title">Editar Compra</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <EstadoChip estado={compra.estado} />
            <button type="button" className="modal-close-btn" onClick={onClose} style={{ flexShrink: 0 }}><X size={16} /></button>
          </div>
        </div>

        <StepsBar current={step} />

        <div className="modal-body" style={{ flex: 1, overflowY: "auto", padding: "22px 28px" }}>

          {isLocked && (
            <div className="stock-aviso stock-aviso--info" style={{ marginBottom: 16 }}>
              Esta compra ya fue <strong>completada y su stock fue aplicado</strong>. Solo puedes editar el
              método de pago, el comprobante, las notas y la fecha de llegada; el resto se muestra como referencia.
            </div>
          )}

          {/* ── PASO 1 ── */}
          {step === 1 && (
            <>
              <div className="field-wrap">
                <label className="field-label">Proveedor <span className="required">*</span></label>
                {editable.proveedor ? (
                  <SearchableSelect
                    options={proveedores}
                    value={form.idProveedor}
                    onChange={e => set("idProveedor", e.target.value)}
                    getValue={p => p.ID_Proveedor || p.id}
                    getLabel={p => { const doc = p.NIT || p.nit ? `NIT ${p.NIT || p.nit}` : p.Cedula || p.cedula ? `CC ${p.Cedula || p.cedula}` : ""; return `${p.Responsable || p.responsable || ""}${doc ? ` - ${doc}` : ""}`; }}
                    placeholder="— Seleccionar proveedor —"
                    searchPlaceholder="Buscar proveedor…"
                    className={`field-select ${errors.idProveedor ? "error" : ""}`}
                  />
                ) : (
                  <input className="field-input" value={provNombre} disabled />
                )}
                {errors.idProveedor && <span className="field-error">{errors.idProveedor}</span>}
              </div>

              <div className="field-grid-2">
                <div className="field-wrap">
                  <label className="field-label">Fecha de compra <span className="required">*</span></label>
                  <input
                    type="date"
                    max={hoy}
                    className={`field-input ${errors.fecha ? "error" : ""}`}
                    value={form.fecha}
                    disabled={!editable.fecha}
                    onChange={e => set("fecha", e.target.value)}
                  />
                  {errors.fecha && <span className="field-error">{errors.fecha}</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label">Método de pago <span className="required">*</span></label>
                  <SearchableSelect
                    options={METODOS_PAGO}
                    value={form.metodoPago}
                    onChange={e => { set("metodoPago", e.target.value); if (e.target.value !== "transferencia") quitarComprobante(); }}
                    getValue={m => m.value}
                    getLabel={m => m.label}
                    placeholder="— Seleccionar método —"
                    searchPlaceholder="Método…"
                    className={`field-select ${errors.metodoPago ? "error" : ""}`}
                    disabled={!editable.metodo}
                  />
                  {errors.metodoPago && <span className="field-error">{errors.metodoPago}</span>}
                </div>
              </div>

              {form.metodoPago === "transferencia" && renderComprobante()}

              <div className="field-wrap">
                <label className="field-label">Notas</label>
                <textarea
                  className="field-input field-textarea"
                  rows={2}
                  placeholder="Observaciones…"
                  value={form.notas}
                  disabled={!editable.notas}
                  onChange={e => set("notas", e.target.value)}
                />
              </div>

              {editable.fechaLlegada && (
                <div className="field-wrap">
                  <label className="field-label">Fecha de llegada</label>
                  <input
                    type="date"
                    className="field-input"
                    value={form.fecha_llegada || ""}
                    max={hoy}
                    onChange={e => set("fecha_llegada", e.target.value)}
                  />
                </div>
              )}
            </>
          )}

          {/* ── PASO 2 ── */}
          {step === 2 && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "#616161" }}>Insumos comprados</p>
                {errors.detalles && <span className="field-error">{errors.detalles}</span>}
              </div>

              {detalles.map((d, i) => (
                <div key={d._key} style={{ border: "1px solid #e8e8e8", borderRadius: 10, padding: "10px 12px", marginBottom: 8, background: "#fafafa" }}>
                  <DetalleInsumoFields
                    detalle={d}
                    index={i}
                    insumosActivos={insumosActivos}
                    idsSeleccionados={idsSeleccionados}
                    errors={errors}
                    disabled={!editable.lineas}
                    onInsumoChange={ins => setDetalles(ds => ds.map(det =>
                      det._key === d._key
                        ? { ...det, idInsumo: String(ins.id), idUnidad: ins.idUnidad ? String(ins.idUnidad) : "" }
                        : det
                    ))}
                    onField={(field, value) => setDetalle(d._key, field, value)}
                    onRemove={editable.lineas ? () => removeDetalle(d._key) : undefined}
                  />
                </div>
              ))}

              {editable.lineas && (
                <button className="btn-add-detalle" type="button" onClick={addDetalle} style={{ marginTop: 4 }}>
                  + Agregar insumo
                </button>
              )}
            </>
          )}

          {/* ── PASO 3 ── */}
          {step === 3 && (
            <>
              <div style={{ marginBottom: 18 }}>
                <p style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 700, color: "#616161" }}>Gastos adicionales</p>
                <p style={{ margin: 0, fontSize: 12, color: "#9e9e9e" }}>
                  {editable.gastos
                    ? "Ingresa los porcentajes para IVA y Descuento; el sistema calcula el valor automáticamente."
                    : "Los gastos de esta compra ya no son editables."}
                </p>
              </div>

              <div className="gastos-grid gastos-grid--standalone">
                <div className="field-wrap">
                  <label className="field-label">Transporte</label>
                  <input type="text" inputMode="numeric" className={`field-input ${errors.transporte ? "error" : ""}`} placeholder="$ 0"
                    value={gastos.transporte} disabled={!editable.gastos} onKeyDown={bloquearSignoYPunto} onChange={e => setGasto("transporte", e.target.value)} />
                  {errors.transporte && <span className="field-error">{errors.transporte}</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 4 }}><Receipt size={14} /> IVA (%)</label>
                  <div style={{ position: "relative" }}>
                    <input type="text" inputMode="decimal" className={`field-input ${errors.iva ? "error" : ""}`} placeholder="0" style={{ paddingRight: 30 }}
                      value={gastos.iva} disabled={!editable.gastos} onKeyDown={bloquearSigno} onChange={e => setGasto("iva", e.target.value)} />
                    <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: "#9e9e9e", fontWeight: 700 }}>%</span>
                  </div>
                  {errors.iva
                    ? <span className="field-error">{errors.iva}</span>
                    : valorIvaActual > 0 && <span className="field-hint" style={{ color: "#2e7d32", fontWeight: 600 }}>+ {COP(valorIvaActual)}</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 4 }}><Tag size={14} /> Descuento del proveedor (%)</label>
                  <div style={{ position: "relative" }}>
                    <input type="text" inputMode="decimal" className={`field-input gastos-descuento-input ${errors.descuento ? "error" : ""}`} placeholder="0" style={{ paddingRight: 30 }}
                      value={gastos.descuento} disabled={!editable.gastos} onKeyDown={bloquearSigno} onChange={e => setGasto("descuento", e.target.value)} />
                    <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: "#c62828", fontWeight: 700 }}>%</span>
                  </div>
                  {errors.descuento
                    ? <span className="field-error">{errors.descuento}</span>
                    : valorDescActual > 0
                      ? <span className="field-hint" style={{ color: "#c62828", fontWeight: 600 }}>− {COP(valorDescActual)}</span>
                      : <span className="field-hint">Se descuenta del subtotal de insumos de esta compra (rebaja que concede el proveedor).</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label">Otros costos</label>
                  <input type="text" inputMode="numeric" className={`field-input ${errors.otros ? "error" : ""}`} placeholder="$ 0"
                    value={gastos.otros} disabled={!editable.gastos} onKeyDown={bloquearSignoYPunto} onChange={e => setGasto("otros", e.target.value)} />
                  {errors.otros && <span className="field-error">{errors.otros}</span>}
                </div>
              </div>

              <div className="total-desglose" style={{ marginTop: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                  <span style={{ color: "#757575" }}>Subtotal insumos</span>
                  <span style={{ fontWeight: 600 }}>{COP(subtotalActual)}</span>
                </div>
                {gTransporte > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>+ Transporte</span><span style={{ color: "#2e7d32" }}>{COP(gTransporte)}</span>
                  </div>
                )}
                {valorIvaActual > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>+ IVA ({gIvaPct}%)</span><span style={{ color: "#2e7d32" }}>{COP(valorIvaActual)}</span>
                  </div>
                )}
                {valorDescActual > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>− Descuento del proveedor ({gDescPct}%)</span><span style={{ color: "#c62828" }}>{COP(valorDescActual)}</span>
                  </div>
                )}
                {gOtros > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>+ Otros</span><span style={{ color: "#2e7d32" }}>{COP(gOtros)}</span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ flexShrink: 0, display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 28px 20px", borderTop: "1px solid #f5f5f5" }}>
          <div className="total-bar" style={{ margin: 0 }}>
            <span className="total-bar__label">Total</span>
            <span className="total-bar__value" style={{ color: errors.total ? "#c62828" : undefined }}>
              {COP(totalActual || 0)}
            </span>
            {errors.total && (
              <span className="field-error" style={{ display: "block", fontSize: 11, marginTop: 2 }}>{errors.total}</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            {step > 1
              ? <button className="btn-ghost" onClick={() => setStep(s => s - 1)}>← Volver</button>
              : <button className="btn-ghost" onClick={onClose}>Cancelar</button>}
            <button
              className="btn-save"
              onClick={step < 3 ? handleNextStep : handleSave}
              disabled={saving}
            >
              {saving ? "Guardando…" : step < 3 ? "Siguiente →" : "Guardar Cambios"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════ VISTA DETALLE ═══════════════ */
function VerCompra({ compraBase, onClose, getProveedorById, insumosActivos }) {
  const [compra, setCompra] = useState(compraBase);
  const [cargando, setCargando] = useState(true);
  const [viewTab, setViewTab] = useState("resumen");

  useEffect(() => {
    let vivo = true;
    getCompra(compraBase.id)
      .then(full => { if (vivo) setCompra(full); })
      .catch(() => {})
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [compraBase.id]);

  const _prov = getProveedorById(compra.idProveedor);
  const provNombre = compra.proveedor || _prov?.Responsable || _prov?.responsable || "—";
  const metodo = METODOS_PAGO.find(m => m.value === compra.metodoPago);
  const items = compra.items || [];

  const subtotal   = items.reduce((s, d) => s + (Number(d.cantidad) || 0) * (Number(d.precioUnd) || 0), 0);
  const transporte = compra.transporte || 0;
  const ivaPct     = compra.ivaPorcentaje || 0;
  const descPct    = compra.descuentoPorcentaje || 0;
  const otros      = compra.otros || 0;
  const valorIva   = subtotal * ivaPct / 100;
  const valorDesc  = subtotal * descPct / 100;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card modal-card--compra-det" onClick={e => e.stopPropagation()}>

        <div className="modal-header" style={{ flexShrink: 0, padding: "16px 24px" }}>
          <div>
            <p className="modal-header__eyebrow">Compra #{compra.id}</p>
            <h2 className="modal-header__title">Detalle de Compra</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <EstadoChip estado={compra.estado} />
            <button type="button" className="modal-close-btn" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        <div className="compra-det-tabs">
          <button className={`compra-det-tab${viewTab === "resumen" ? " compra-det-tab--active" : ""}`} onClick={() => setViewTab("resumen")}>
            <ClipboardList size={14} style={{ verticalAlign: "middle", marginRight: 4 }} /> Resumen
          </button>
          {compra.stockAplicado && (
            <button className={`compra-det-tab${viewTab === "lotes" ? " compra-det-tab--active" : ""}`} onClick={() => setViewTab("lotes")}>
              <Package size={14} style={{ verticalAlign: "middle", marginRight: 4 }} /> Lotes generados
            </button>
          )}
        </div>

        <div className="modal-body" style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>

          {viewTab === "resumen" && (
            <>
              <p className="section-label" style={{ marginTop: 0 }}>Información general</p>
              <div className="compra-det-info-grid">
                <div className="compra-det-info-card compra-det-info-card--prov">
                  <div className="compra-det-info-card__lbl">Proveedor</div>
                  <div className="compra-det-info-card__val" style={{ display: "flex", alignItems: "center", gap: 4 }}><Building2 size={14} /> {provNombre}</div>
                </div>
                <div className="compra-det-info-card">
                  <div className="compra-det-info-card__lbl">Fecha de compra</div>
                  <div className="compra-det-info-card__val" style={{ display: "flex", alignItems: "center", gap: 4 }}><Calendar size={14} /> {fmtFecha(compra.fecha)}</div>
                </div>
                <div className="compra-det-info-card">
                  <div className="compra-det-info-card__lbl">Método de pago</div>
                  <div className="compra-det-info-card__val" style={{ display: "flex", alignItems: "center", gap: 4 }}>{metodo ? <metodo.Icon size={14} /> : <CreditCard size={14} />} {metodo?.label || compra.metodoPago || "—"}</div>
                </div>
                {compra.fecha_llegada && (
                  <div className="compra-det-info-card">
                    <div className="compra-det-info-card__lbl">Fecha de completación</div>
                    <div className="compra-det-info-card__val" style={{ display: "flex", alignItems: "center", gap: 4, color: "#2e7d32" }}><CheckCircle2 size={14} /> {fmtFecha(compra.fecha_llegada)}</div>
                  </div>
                )}
                {compra.fecha_anulada && (
                  <div className="compra-det-info-card">
                    <div className="compra-det-info-card__lbl">Fecha de anulación</div>
                    <div className="compra-det-info-card__val" style={{ display: "flex", alignItems: "center", gap: 4, color: "#c62828" }}><Ban size={14} /> {fmtFecha(compra.fecha_anulada)}</div>
                  </div>
                )}
              </div>

              {/* 3.11 — comprobante si el pago fue transferencia */}
              {compra.metodoPago === "transferencia" && (
                <>
                  <p className="section-label">Comprobante de transferencia</p>
                  {compra.comprobante
                    ? <ImageLightbox src={compra.comprobante} alt="Comprobante" label={`Comprobante · Compra #${compra.id}`} thumbStyle={{ maxWidth: 240 }} />
                    : <p style={{ fontSize: 12, color: "#9e9e9e", margin: 0 }}>No se adjuntó comprobante.</p>}
                </>
              )}

              {compra.notas && (
                <div className="compra-det-notas" style={{ display: "flex", alignItems: "flex-start", gap: 6, marginTop: 16 }}><PenLine size={14} style={{ flexShrink: 0, marginTop: 2 }} /> {compra.notas}</div>
              )}

              <p className="section-label">Insumos comprados</p>
              <div className="compra-det-insumos">
                <div className="compra-det-insumos__header">
                  <span>Insumo</span><span>Cantidad</span><span>Precio/u</span><span>Subtotal</span><span>Vencimiento</span>
                </div>
                {cargando && items.length === 0 ? (
                  <div className="compra-det-insumos__empty">Cargando insumos…</div>
                ) : items.length === 0 ? (
                  <div className="compra-det-insumos__empty">Sin insumos registrados en esta compra</div>
                ) : (
                  items.map((d, idx) => {
                    const ins  = insumosActivos.find(i => i.id === Number(d.idInsumo));
                    const uni  = d.unidad || ins?.unidad || "";
                    const dias = diasHasta(d.fechaVencimiento);
                    return (
                      <div key={d.idDetalle || d.idInsumo || idx} className="compra-det-insumos__row">
                        <span className="compra-det-insumos__name">{d.nombre || ins?.nombre || "—"}</span>
                        <span className="compra-det-insumos__qty">{d.cantidad} {uni}</span>
                        <span className="compra-det-insumos__pu">{COP(d.precioUnd)}</span>
                        <span className="compra-det-insumos__sub">{COP((Number(d.cantidad) || 0) * (Number(d.precioUnd) || 0))}</span>
                        <span className={`compra-det-insumos__venc${dias !== null && dias < 0 ? " venc-danger" : dias !== null && dias <= 7 ? " venc-warn" : ""}`}>
                          {d.fechaVencimiento ? fmtFecha(d.fechaVencimiento) : "—"}
                          {dias !== null && dias < 0 && <AlertTriangle size={13} style={{ verticalAlign: "middle" }} />}
                          {dias !== null && dias >= 0 && dias <= 7 && ` (${dias}d)`}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>

              <p className="section-label">Desglose de costos</p>
              <div className="compra-det-costos">
                <div className="compra-det-costos__row"><span>Subtotal insumos</span><span>{COP(subtotal)}</span></div>
                {transporte > 0 && <div className="compra-det-costos__row"><span>Transporte</span><span>{COP(transporte)}</span></div>}
                {valorIva > 0 && (
                  <div className="compra-det-costos__row">
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Receipt size={13} /> IVA ({ivaPct}%)</span><span>{COP(valorIva)}</span>
                  </div>
                )}
                {valorDesc > 0 && (
                  <div className="compra-det-costos__row compra-det-costos__row--desc">
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Tag size={13} /> Descuento del proveedor ({descPct}%) — se descuenta del subtotal</span><span>−{COP(valorDesc)}</span>
                  </div>
                )}
                {otros > 0 && <div className="compra-det-costos__row"><span>Otros costos</span><span>{COP(otros)}</span></div>}
                <div className="compra-det-costos__total"><span>Total final</span><span>{COP(compra.total)}</span></div>
              </div>
            </>
          )}

          {viewTab === "lotes" && (
            <>
              <p className="section-label" style={{ marginTop: 0 }}>Lotes generados</p>
              <div className="compra-det-lotes-info" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <CheckCircle2 size={13} /> Compra completada el {fmtFecha(compra.fecha_llegada || compra.fecha)}. Stock aplicado al inventario.
              </div>
              {cargando ? (
                <div style={{ textAlign: "center", padding: "40px 0", color: "#9e9e9e", fontSize: 13 }}>Cargando lotes…</div>
              ) : items.length === 0 ? (
                <div style={{ textAlign: "center", padding: "40px 0", color: "#9e9e9e", fontSize: 13 }}>Sin lotes registrados</div>
              ) : (
                items.map((d, idx) => <LotesInsumoGrupo key={d.idInsumo || idx} item={d} insumosActivos={insumosActivos} />)
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}
