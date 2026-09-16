import { useState, useEffect } from "react";
import { X, Check, Banknote, Building2, Paperclip, Receipt, Tag } from "lucide-react";
import { getProveedores } from "../../../services/proveedoresService.js";
import { getInsumos } from "../../../services/insumosService.js";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import ImageLightbox from "../../../shared/components/ImageLightbox.jsx";
import { subirImagenCloudinary } from "../../../utils/cloudinary.js";
import DetalleInsumoFields from "./DetalleInsumoFields.jsx";
import { GRUPO_UNIDAD, CANT_MAX } from "./compraDetalleUtils.js";
import "./compras.css";
import { formatCOP } from "../../../utils/formato";

const METODOS_PAGO = [
  { value: "efectivo",      label: "Efectivo",      Icon: Banknote  },
  { value: "transferencia", label: "Transferencia", Icon: Building2 },
];

const COP = formatCOP;

// total entre $0 y $50 000 000 COP
const TOTAL_MIN  = 0;
const TOTAL_MAX  = 50_000_000;
const PORC_MAX   = 100;        // IVA y descuento en % (admiten decimales)

// Filtros de entrada de los campos de gastos (transporte / otros: entero, máx. 8 dígitos)
const soloPorcentaje = (v) => v === "" || /^\d{0,3}(\.\d{0,2})?$/.test(v);   // 0–100 con hasta 2 decimales
const soloEntero     = (v) => v === "" || /^\d{0,8}$/.test(v);              // entero, máx. 8 dígitos
const bloquearSigno  = (e) => { if (["+", "-", "e", "E"].includes(e.key)) e.preventDefault(); };
const bloquearSignoYPunto = (e) => { if (["+", "-", "e", "E", ".", ","].includes(e.key)) e.preventDefault(); };

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
  isExpanded:       true,
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

export default function CrearCompra({ onClose, onSave }) {
  const [proveedores,  setProveedores]  = useState([]);
  const [insumosActivos, setInsumosActivos] = useState([]);

  useEffect(() => {
    getProveedores({ porPagina: 100 }).then(d => setProveedores(d.proveedores || d || [])).catch(() => {});
    getInsumos().then(d => {
      const lista = (d.insumos || d || []).map(i => ({
        id:        i.ID_Insumo || i.id,
        nombre:    i.Nombre    || i.nombre    || "",
        unidad:    i.simbolo_unidad || i.unidad || "",
        idUnidad:  i.Unidad_Medida  || i.idUnidad || null,
        estado:    i.Estado !== 2,
      }));
      setInsumosActivos(lista.filter(i => i.estado));
    }).catch(() => {});
  }, []);

  const [form, setForm] = useState({
    idProveedor: "",
    fecha:       new Date().toISOString().split("T")[0],
    estado:      "pendiente",
    metodoPago:  "",
    notas:       "",
  });

  const [comprobante,        setComprobante]        = useState(null);   // File
  const [comprobantePreview, setComprobantePreview] = useState(null);   // dataURL

  const onComprobanteFile = (file) => {
    if (!file) { setComprobante(null); setComprobantePreview(null); return; }
    setComprobante(file);
    const reader = new FileReader();
    reader.onload = (ev) => setComprobantePreview(ev.target.result);
    reader.readAsDataURL(file);
  };

  const [gastos, setGastos] = useState({
    transporte: "",
    iva:        "", // porcentaje (admite decimales)
    descuento:  "", // porcentaje (admite decimales)
    otros:      "",
  });

  // Validación en vivo de cada campo de gastos.
  const validarGasto = (k, v) => {
    const n = Number(v);
    if (v === "") return "";
    if (k === "iva")       return (n < 0 || n > PORC_MAX) ? "El IVA debe estar entre 0 y 100%" : "";
    if (k === "descuento") return (n < 0 || n > PORC_MAX) ? "El descuento debe estar entre 0 y 100%" : "";
    // transporte / otros: entero en pesos, máx. 8 dígitos
    if (n < 0) return "No puede ser negativo";
    if (v.length > 8) return "Máximo 8 dígitos";
    return "";
  };

  const setGasto = (k, v) => {
    const permitido = (k === "iva" || k === "descuento") ? soloPorcentaje(v) : soloEntero(v);
    if (!permitido) return;
    setGastos(g => ({ ...g, [k]: v }));
    setErrors(e => ({ ...e, [k]: validarGasto(k, v) }));
  };

  const [detalles, setDetalles] = useState([emptyDetalle()]);
  const [errors,   setErrors]   = useState({});
  const [saving,   setSaving]   = useState(false);
  const [step,     setStep]     = useState(1);

  const subtotalInsumos = detalles.reduce((s, d) => s + (Number(d.cantidad) || 0) * (Number(d.precioUnd) || 0), 0);

  // Cálculos de porcentajes
  const valorIva = (subtotalInsumos * (Number(gastos.iva) || 0)) / 100;
  const valorDescuento = (subtotalInsumos * (Number(gastos.descuento) || 0)) / 100;

  const totalGastosExtras =
    (Number(gastos.transporte) || 0) +
    valorIva -
    valorDescuento +
    (Number(gastos.otros)      || 0);

  const totalActual = subtotalInsumos + totalGastosExtras;

  const set = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    const hoy = new Date().toISOString().split("T")[0];
    let err = "";
    if (k === "idProveedor" && !v) err = "Selecciona un proveedor";
    if (k === "fecha") {
      if (!v) err = "Ingresa la fecha";
      else if (v > hoy) err = "La fecha no puede ser futura";
    }
    if (k === "metodoPago" && !v) err = "Selecciona el método de pago";
    setErrors(e => ({ ...e, [k]: err }));
  };

  const setDetalle = (key, field, value) => {
    setDetalles(ds => ds.map((d, i) => {
      if (d._key !== key) return d;
      const updated = { ...d, [field]: value };
      let err = "";
      if (field === "idInsumo" && !value) err = "Selecciona un insumo";
      if (field === "cantidad") {
        const n = Number(value);
        const grupo = GRUPO_UNIDAD[Number(d.idUnidad)];
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
      if (errKey) {
        setErrors(prev => ({ ...prev, [errKey]: err }));
      }
      return updated;
    }));
  };

  const addDetalle = () => {
    setDetalles(ds => [
      ...ds.map(d => ({ ...d, isExpanded: false })),
      emptyDetalle(),
    ]);
  };

  const removeDetalle = (key) => setDetalles(ds => ds.filter(d => d._key !== key));

  const idsSeleccionados = detalles.map(d => String(d.idInsumo)).filter(Boolean);

  const validateStep1 = () => {
    const e = {};
    const hoy = new Date().toISOString().split("T")[0];
    if (!form.idProveedor)  e.idProveedor = "Selecciona un proveedor";
    if (!form.fecha)        e.fecha       = "Ingresa la fecha";
    else if (form.fecha > hoy) e.fecha    = "La fecha no puede ser futura";
    if (!form.metodoPago)  e.metodoPago  = "Selecciona el método de pago";
    return e;
  };

  const validateStep2 = () => {
    const e = {};
    if (detalles.length === 0) e.detalles = "Agrega al menos un insumo";
    detalles.forEach((d, i) => {
      const n = Number(d.cantidad);
      const grupo = GRUPO_UNIDAD[Number(d.idUnidad)];
      const soloEntero = grupo === "und";
      if (!d.idInsumo)
        e[`ins_${i}`] = "Selecciona un insumo";
      if (!d.cantidad || n <= 0)
        e[`cant_${i}`] = "Cantidad inválida";
      else if (soloEntero && !Number.isInteger(n))
        e[`cant_${i}`] = "La cantidad debe ser un número entero para esta unidad";
      else if (n > CANT_MAX)
        e[`cant_${i}`] = `Máximo ${CANT_MAX.toLocaleString("es-CO")} por línea`;
      if (!d.precioUnd || Number(d.precioUnd) <= 0)
        e[`precio_${i}`] = "El precio unitario debe ser mayor a $0";
      if (d.vencimientoTipo === "fecha" && !d.fechaVencimiento)
        e[`venc_${i}`] = "Ingresa la fecha";
      else if (d.vencimientoTipo === "dias" && (!d.vencimientoValor || Number(d.vencimientoValor) <= 0))
        e[`venc_${i}`] = "Ingresa los días";
    });
    return e;
  };

  const handleNextStep = () => {
    let e = {};
    if (step === 1) e = validateStep1();
    if (step === 2) e = validateStep2();
    if (Object.keys(e).length) { setErrors(e); return; }
    setErrors({});
    setStep(s => s + 1);
  };

  const handleBack = () => setStep(s => s - 1);

  const validateTotal = () => {
    const e = {};
    ["iva", "descuento", "transporte", "otros"].forEach(k => {
      const msg = validarGasto(k, gastos[k]);
      if (msg) e[k] = msg;
    });
    if (totalActual < TOTAL_MIN)
      e.total = `El total (${COP(totalActual)}) no puede ser negativo`;
    else if (totalActual > TOTAL_MAX)
      e.total = `El total (${COP(totalActual)}) supera el máximo permitido de ${COP(TOTAL_MAX)} COP`;
    return e;
  };

  const handleSave = async () => {
    if (saving) return;
    const e = { ...validateStep1(), ...validateStep2(), ...validateTotal() };
    if (Object.keys(e).length) { setErrors(e); return; }
    setSaving(true);
    try {
      let comprobanteUrl = null;
      if (comprobante) {
        try {
          comprobanteUrl = await subirImagenCloudinary(comprobante);
        } catch {
          setErrors(prev => ({ ...prev, comprobante: "No se pudo subir el comprobante. Intenta de nuevo." }));
          setSaving(false);
          return;
        }
      }
      const detallesLimpios = detalles.map(d => ({
        idInsumo:         Number(d.idInsumo),
        idUnidad:         d.idUnidad ? Number(d.idUnidad) : null,
        cantidad:         Number(d.cantidad),
        precioUnd:        Number(d.precioUnd),
        notas:            (d.notas || "").trim(),
        fechaVencimiento: d.vencimientoTipo === "dias"
          ? (() => { const f = new Date(); f.setDate(f.getDate() + Number(d.vencimientoValor)); return f.toISOString().split("T")[0]; })()
          : d.fechaVencimiento || null,
      }));
      onSave({
        ...form,
        detalles: detallesLimpios,
        comprobante:  comprobanteUrl,
        // Misma forma que envía EditarCompra: iva/descuento son porcentajes.
        gastos: {
          transporte: Number(gastos.transporte) || 0,
          iva:        Number(gastos.iva)        || 0,
          descuento:  Number(gastos.descuento)  || 0,
          otros:      Number(gastos.otros)      || 0,
        },
      });
    } catch (err) {
      console.error("Error saving purchase:", err);
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div
        className="modal-card"
        onClick={e => e.stopPropagation()}
        style={{
          /* ── FIX 1: modal más ancho ── */
          maxWidth: 860,
          width: "95vw",
          display: "flex",
          flexDirection: "column",
          maxHeight: "92vh",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div className="modal-header" style={{ flexShrink: 0, padding: "18px 28px" }}>
          <div>
            <p className="modal-header__eyebrow">Compras</p>
            <h2 className="modal-header__title">Nueva Compra</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} style={{ flexShrink: 0 }}><X size={16} /></button>
        </div>

        <StepsBar current={step} />

        {/* Body */}
        <div className="modal-body" style={{ flex: 1, overflowY: "auto", padding: "22px 28px" }}>

          {/* ── PASO 1 ── */}
          {step === 1 && (
            <>
              <div className="field-wrap">
                <label className="field-label">Proveedor <span className="required">*</span></label>
                <SearchableSelect
                  options={proveedores}
                  value={form.idProveedor}
                  onChange={e => set("idProveedor", e.target.value)}
                  getValue={p => p.ID_Proveedor || p.id}
                  getLabel={p => `${p.Responsable || p.responsable || ""}${p.NIT || p.nit ? ` - NIT ${p.NIT || p.nit}` : ""}`}
                  placeholder="— Seleccionar proveedor —"
                  searchPlaceholder="Buscar proveedor…"
                  className="field-select"
                  error={!!errors.idProveedor}
                />
                {errors.idProveedor && <span className="field-error">{errors.idProveedor}</span>}
              </div>

              <div className="field-grid-2">
                <div className="field-wrap">
                  <label className="field-label">Fecha de compra <span className="required">*</span></label>
                  <input
                    type="date"
                    max={new Date().toISOString().split("T")[0]}
                    className={`field-input ${errors.fecha ? "error" : ""}`}
                    value={form.fecha}
                    onChange={e => set("fecha", e.target.value)}
                  />
                  {errors.fecha && <span className="field-error">{errors.fecha}</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label">Método de pago <span className="required">*</span></label>
                  <SearchableSelect
                    options={METODOS_PAGO}
                    value={form.metodoPago}
                    onChange={e => { set("metodoPago", e.target.value); onComprobanteFile(null); }}
                    getValue={m => m.value}
                    getLabel={m => m.label}
                    placeholder="— Seleccionar método —"
                    searchPlaceholder="Método…"
                    className={`field-select ${errors.metodoPago ? "error" : ""}`}
                  />
                  {errors.metodoPago && <span className="field-error">{errors.metodoPago}</span>}
                </div>
              </div>

              {form.metodoPago === "transferencia" && (
                <div className="field-wrap comprobante-wrap">
                  <label className="field-label">Comprobante de transferencia</label>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <label className="comprobante-upload-btn" style={{ flex: 1 }}>
                      <input
                        type="file"
                        accept="image/*"
                        style={{ display: "none" }}
                        onChange={e => onComprobanteFile(e.target.files?.[0] || null)}
                      />
                      <span className="comprobante-upload-icon" style={{ display: "flex", alignItems: "center" }}><Paperclip size={16} /></span>
                      {comprobante
                        ? <span className="comprobante-filename">{comprobante.name}</span>
                        : <span>Adjuntar comprobante (imagen)</span>
                      }
                    </label>
                    {comprobante && (
                      <button
                        type="button"
                        onClick={e => { e.preventDefault(); onComprobanteFile(null); }}
                        style={{ flexShrink: 0, padding: "0 12px", height: 36, borderRadius: 8, border: "1.5px solid #ef5350", background: "#fff", color: "#c62828", fontSize: 12, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}
                      >
                        <X size={14} /> Quitar
                      </button>
                    )}
                  </div>
                  {comprobantePreview && (
                    <div style={{ marginTop: 8 }}>
                      <ImageLightbox src={comprobantePreview} alt="Comprobante" label="Comprobante de transferencia" thumbStyle={{ maxWidth: 220 }} />
                    </div>
                  )}
                  {errors.comprobante
                    ? <span className="field-error">{errors.comprobante}</span>
                    : <span className="field-hint">Opcional — puedes adjuntarlo ahora o más tarde</span>}
                </div>
              )}

              <div className="field-wrap">
                <label className="field-label">Notas</label>
                <textarea
                  className="field-input field-textarea"
                  placeholder="Observaciones generales…"
                  rows={2}
                  value={form.notas}
                  onChange={e => set("notas", e.target.value)}
                />
              </div>
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
                    onInsumoChange={ins => setDetalles(ds => ds.map(det =>
                      det._key === d._key
                        ? { ...det, idInsumo: String(ins.id), idUnidad: ins.idUnidad ? String(ins.idUnidad) : "" }
                        : det
                    ))}
                    onField={(field, value) => setDetalle(d._key, field, value)}
                    onRemove={() => removeDetalle(d._key)}
                  />
                </div>
              ))}

              <button className="btn-add-detalle" type="button" onClick={addDetalle} style={{ marginTop: 4 }}>
                + Agregar insumo
              </button>
            </>
          )}

          {/* ── PASO 3 ── */}
          {step === 3 && (
            <>
              <div style={{ marginBottom: 18 }}>
                <p style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 700, color: "#616161" }}>
                  Gastos adicionales
                </p>
                <p style={{ margin: 0, fontSize: 12, color: "#9e9e9e" }}>
                  Ingresa los porcentajes para IVA y Descuento; el sistema calculará el valor automáticamente.
                </p>
              </div>

              <div className="gastos-grid gastos-grid--standalone">
                <div className="field-wrap">
                  <label className="field-label">Transporte</label>
                  <input type="text" inputMode="numeric" className={`field-input ${errors.transporte ? "error" : ""}`} placeholder="$ 0"
                    value={gastos.transporte} onKeyDown={bloquearSignoYPunto} onChange={e => setGasto("transporte", e.target.value)} />
                  {errors.transporte && <span className="field-error">{errors.transporte}</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 4 }}><Receipt size={14} /> IVA (%)</label>
                  <div style={{ position: "relative" }}>
                    <input type="text" inputMode="decimal" className={`field-input ${errors.iva ? "error" : ""}`} placeholder="0"
                      value={gastos.iva} onKeyDown={bloquearSigno} onChange={e => setGasto("iva", e.target.value)} style={{ paddingRight: 30 }} />
                    <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: "#9e9e9e", fontWeight: 700 }}>%</span>
                  </div>
                  {errors.iva
                    ? <span className="field-error">{errors.iva}</span>
                    : valorIva > 0 && <span className="field-hint" style={{ color: "#2e7d32", fontWeight: 600 }}>+ {COP(valorIva)}</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label" style={{ display: "flex", alignItems: "center", gap: 4 }}><Tag size={14} /> Descuento del proveedor (%)</label>
                  <div style={{ position: "relative" }}>
                    <input type="text" inputMode="decimal" className={`field-input gastos-descuento-input ${errors.descuento ? "error" : ""}`} placeholder="0"
                      value={gastos.descuento} onKeyDown={bloquearSigno} onChange={e => setGasto("descuento", e.target.value)} style={{ paddingRight: 30 }} />
                    <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: "#c62828", fontWeight: 700 }}>%</span>
                  </div>
                  {errors.descuento
                    ? <span className="field-error">{errors.descuento}</span>
                    : valorDescuento > 0
                      ? <span className="field-hint" style={{ color: "#c62828", fontWeight: 600 }}>− {COP(valorDescuento)}</span>
                      : <span className="field-hint">Se descuenta del subtotal de insumos de esta compra (rebaja que concede el proveedor).</span>}
                </div>
                <div className="field-wrap">
                  <label className="field-label">Otros costos</label>
                  <input type="text" inputMode="numeric" className={`field-input ${errors.otros ? "error" : ""}`} placeholder="$ 0"
                    value={gastos.otros} onKeyDown={bloquearSignoYPunto} onChange={e => setGasto("otros", e.target.value)} />
                  {errors.otros && <span className="field-error">{errors.otros}</span>}
                </div>
              </div>

              <div className="total-desglose" style={{ marginTop: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                  <span style={{ color: "#757575" }}>Subtotal insumos</span>
                  <span style={{ fontWeight: 600 }}>{COP(subtotalInsumos)}</span>
                </div>
                {Number(gastos.transporte) > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>+ Transporte</span>
                    <span style={{ color: "#2e7d32" }}>{COP(Number(gastos.transporte))}</span>
                  </div>
                )}
                {valorIva > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>+ IVA ({gastos.iva}%)</span>
                    <span style={{ color: "#2e7d32" }}>{COP(valorIva)}</span>
                  </div>
                )}
                {valorDescuento > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>− Descuento ({gastos.descuento}%)</span>
                    <span style={{ color: "#c62828" }}>{COP(valorDescuento)}</span>
                  </div>
                )}
                {Number(gastos.otros) > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "#757575" }}>+ Otros</span>
                    <span style={{ color: "#2e7d32" }}>{COP(Number(gastos.otros))}</span>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ flexShrink: 0, padding: "14px 28px 20px", borderTop: "1px solid #f5f5f5" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div className="total-bar" style={{ margin: 0 }}>
              <span className="total-bar__label">Total</span>
              <span className="total-bar__value" style={{ color: errors.total ? "#c62828" : undefined }}>
                {COP(totalActual || 0)}
              </span>
              {errors.total && (
                <span className="field-error" style={{ display: "block", fontSize: 11, marginTop: 2 }}>
                  {errors.total}
                </span>
              )}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {step > 1
                ? <button className="btn-ghost" onClick={handleBack}>← Volver</button>
                : <button className="btn-ghost" onClick={onClose}>Cancelar</button>
              }
              <button
                className="btn-save"
                onClick={step < 3 ? handleNextStep : handleSave}
                disabled={saving}
              >
                {saving ? "Guardando…" : step < 3 ? "Siguiente →" : "Guardar compra"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}