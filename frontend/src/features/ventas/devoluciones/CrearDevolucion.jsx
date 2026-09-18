import { useState, useRef, useEffect, useCallback } from "react";
import { getPedidos } from "../../../services/pedidosService.js";
import { formatCOP } from "../../../utils/formato";
import { AVISO_PLAZO_DEVOLUCION, plazoVencido, tieneDevolucionActiva }
  from "../../../utils/devolucionReglas";
import { subirImagenCloudinary } from "../../../utils/cloudinary.js";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import { Check, X, Search, Paperclip, AlertTriangle, Video, FileText, Loader } from "lucide-react";
import "./Devoluciones.css";

const fmt = formatCOP;

const MOTIVOS = [
  "Producto en mal estado",
  "Producto incorrecto",
  "Producto vencido",
  "No cumple con lo solicitado",
  "Error en el pedido",
  "Otro",
];


/* ─── BARRA DE PASOS ─────────────────────────────────────── */
const STEPS = ["Pedido", "Productos", "Detalles"];

function StepsBar({ current }) {
  return (
    <div className="wizard-steps-bar">
      {STEPS.map((label, i) => {
        const idx    = i + 1;
        const done   = idx < current;
        const active = idx === current;
        return (
          <div key={label} className="wizard-step-item">
            <div className={`wizard-step-circle${done ? " done" : active ? " active" : ""}`}>
              {done ? <Check size={14}/> : idx}
            </div>
            <span className={`wizard-step-label${active ? " active" : done ? " done" : ""}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`wizard-step-line${done ? " done" : ""}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ─── PedidoSelect — búsqueda server-side con debounce ──── */
function PedidoSelect({ value, pedidos, onChange, onSearch, searching, error, disabled, hayOcultos }) {
  const [query, setQuery] = useState("");
  const debounceRef = useRef(null);
  const selected = pedidos.find(p => String(p.id) === String(value));

  const handleQueryChange = (q) => {
    setQuery(q);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onSearch(q), 350);
  };

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  if (selected) {
    return (
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "10px 14px", borderRadius: 10,
        background: "#e8f5e9", border: `1.5px solid ${error ? "#ef5350" : "#a5d6a7"}`,
      }}>
        <span style={{ flex: 1, fontSize: 14, fontWeight: 700, color: "#1b5e20" }}>
          {selected.numero} — {selected.cliente?.nombre}
        </span>
        <button type="button" onClick={() => { onChange(""); setQuery(""); onSearch(""); }}
          style={{ border: "none", background: "none", cursor: "pointer", color: "#c62828", padding: 0, lineHeight: 1 }}>
          <X size={16}/>
        </button>
      </div>
    );
  }

  return (
    <div style={{ border: `1.5px solid ${error ? "#ef5350" : "#e0e0e0"}`, borderRadius: 10, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 12px", background: "#fafdf9" }}>
        {searching
          ? <Loader size={13} style={{ color: "#9e9e9e", flexShrink: 0, animation: "spin 1s linear infinite" }}/>
          : <Search size={13} style={{ color: "#9e9e9e", flexShrink: 0 }}/>
        }
        <input
          type="text"
          placeholder={disabled ? "Cargando…" : "Buscar por número o nombre de cliente…"}
          value={query}
          disabled={disabled}
          onChange={e => handleQueryChange(e.target.value)}
          style={{ flex: 1, border: "none", outline: "none", fontSize: 13, background: "transparent", color: "#333", fontFamily: "inherit" }}
        />
        {query && (
          <button type="button" onClick={() => { handleQueryChange(""); }}
            style={{ border: "none", background: "none", cursor: "pointer", color: "#bdbdbd", padding: 0, lineHeight: 1 }}>
            <X size={14}/>
          </button>
        )}
      </div>
      <div style={{ maxHeight: 220, overflowY: "auto", borderTop: "1px solid #f0f0f0" }}>
        {/* Si se escondió alguno se dice por qué: si no, quien atiende no
            sabe qué contestarle al cliente que reclama por su pedido. */}
        {hayOcultos && (
          <div style={{
            display: "flex", gap: 7, alignItems: "flex-start",
            padding: "9px 12px", background: "#fffbeb",
            borderBottom: "1px solid #fde68a",
          }}>
            <AlertTriangle size={13} color="#b45309" style={{ flexShrink: 0, marginTop: 1 }} />
            <span style={{ fontSize: 11, color: "#92400e", fontWeight: 600, lineHeight: 1.45 }}>
              {AVISO_PLAZO_DEVOLUCION}
            </span>
          </div>
        )}
        {pedidos.length === 0 ? (
          <div style={{ padding: "14px", fontSize: 12, color: "#9e9e9e", textAlign: "center", lineHeight: 1.5 }}>
            {searching
              ? "Buscando…"
              : query
                ? `Sin resultados para "${query}"`
                : hayOcultos
                  ? "Ninguno de los pedidos entregados se puede devolver ahora."
                  : "No hay pedidos entregados disponibles para devolución."}
          </div>
        ) : pedidos.map(p => (
          <button
            key={p.id}
            type="button"
            onClick={() => { onChange(String(p.id)); setQuery(""); }}
            style={{
              width: "100%", textAlign: "left", padding: "9px 14px",
              border: "none", borderBottom: "1px solid #f5f5f5",
              background: "transparent", fontSize: 13, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "space-between",
              fontFamily: "inherit", color: "#222",
            }}
            onMouseEnter={e => e.currentTarget.style.background = "#f1f8f1"}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            <span style={{ fontWeight: 700 }}>{p.numero}</span>
            <span style={{ fontSize: 12, color: "#757575", marginLeft: 8 }}>{p.cliente?.nombre}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── RESUMEN DEL PEDIDO (paso 1) ────────────────────────── */
function ResumenPedido({ pedido }) {
  return (
    <div className="resumen-pedido">
      <div className="resumen-pedido__head">
        <span className="resumen-pedido__num">{pedido.numero}</span>
        <span className="resumen-pedido__cliente">{pedido.cliente?.nombre}</span>
      </div>
      <div className="resumen-pedido__meta">
        <span>{pedido.metodo_pago || "—"}</span>
        {pedido.fecha_pedido && (
          <span>{new Date(pedido.fecha_pedido).toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" })}</span>
        )}
      </div>

      <div className="resumen-pedido__lista">
        {(pedido.productosItems || []).map((p, i) => (
          <div key={i} className="resumen-prod-row">
            <span className="resumen-prod-row__name">{p.nombre}</span>
            <span className="resumen-prod-row__qty">×{p.cantidad}</span>
            <span className="resumen-prod-row__price">{fmt(p.precio * p.cantidad)}</span>
          </div>
        ))}
      </div>

      <div className="resumen-pedido__total">
        <span>Total pagado</span>
        <span className="resumen-pedido__total-val">{fmt(pedido.total)}</span>
      </div>
    </div>
  );
}

/* ─── UPLOAD DE EVIDENCIA — sube a Cloudinary ────────────── */
function EvidenciaUpload({ evidencia, onEvidencia }) {
  const fileRef = useRef();
  const [dragging,    setDragging]    = useState(false);
  const [uploading,   setUploading]   = useState(false);
  const [uploadError, setUploadError] = useState("");

  const processFile = async (file) => {
    if (!file) return;
    setUploadError("");
    setUploading(true);
    try {
      const url = await subirImagenCloudinary(file);
      onEvidencia({ nombre: file.name, url, tipo: file.type });
    } catch (err) {
      setUploadError(err?.message || "Error al subir el archivo");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    processFile(e.dataTransfer.files[0]);
  };

  const isImage = evidencia?.tipo?.startsWith("image/");

  if (uploading) {
    return (
      <div className="evidencia-dropzone" style={{ pointerEvents: "none", opacity: 0.7 }}>
        <Loader size={24} style={{ animation: "spin 1s linear infinite", color: "#4caf50" }}/>
        <span className="evidencia-dropzone__text">Subiendo archivo…</span>
      </div>
    );
  }

  if (evidencia) {
    return (
      <div className="evidencia-preview">
        {isImage ? (
          <img src={evidencia.url} alt="evidencia" className="evidencia-preview__img" />
        ) : (
          <div className="evidencia-preview__file">
            <span className="evidencia-preview__file-icon">
              {evidencia.tipo?.startsWith("video/") ? <Video size={20}/> : <FileText size={20}/>}
            </span>
            <span className="evidencia-preview__file-name">{evidencia.nombre}</span>
          </div>
        )}
        <div className="evidencia-preview__bar">
          <span className="evidencia-preview__name" style={{display:"flex",alignItems:"center",gap:4}}><Paperclip size={13}/> {evidencia.nombre}</span>
          <button className="evidencia-preview__remove" onClick={() => onEvidencia(null)}><X size={14}/></button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        className={`evidencia-dropzone${dragging ? " dragging" : ""}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <span className="evidencia-dropzone__icon"><Paperclip size={24}/></span>
        <span className="evidencia-dropzone__text">
          Arrastra un archivo o <strong>haz clic para seleccionar</strong>
        </span>
        <span className="evidencia-dropzone__hint">Imágenes, PDF, video · Opcional</span>
        <input
          ref={fileRef}
          type="file"
          style={{ display: "none" }}
          accept="image/*,application/pdf,video/*"
          onChange={(e) => processFile(e.target.files[0])}
        />
      </div>
      {uploadError && (
        <p className="field-error" style={{ marginTop: 4 }}>
          <AlertTriangle size={12} style={{ marginRight: 4 }}/>{uploadError}
        </p>
      )}
    </>
  );
}

/* ─── ITEM DE PRODUCTO (paso 2) ──────────────────────────── */
function ProdItem({ item, idx, onSet }) {
  return (
    <div className="prod-dev-row">
      <div className="prod-dev-row__info">
        <div className="prod-dev-row__name">{item.nombre}</div>
        <div className="prod-dev-row__meta">
          {fmt(item.precio)} c/u · disponibles: {item.cantMax}
        </div>
      </div>

      <div className="prod-dev-row__qty-wrap">
        <button
          className="qty-btn"
          onClick={() => onSet(idx, item.cantidad - 1)}
          disabled={item.cantidad === 0}
        >−</button>
        <input
          className="qty-input"
          type="number"
          min={0}
          max={item.cantMax}
          value={item.cantidad}
          onChange={(e) => onSet(idx, e.target.value)}
        />
        <button
          className="qty-btn"
          onClick={() => onSet(idx, item.cantidad + 1)}
          disabled={item.cantidad >= item.cantMax}
        >+</button>
      </div>

      <div className="prod-dev-row__sub">
        {item.cantidad > 0 ? fmt(item.precio * item.cantidad) : "—"}
      </div>
    </div>
  );
}

/* ─── COMPONENTE PRINCIPAL ───────────────────────────────── */
export default function CrearDevolucion({ onClose, onSave, saving, devoluciones = [] }) {
  const [pedidosEntregados, setPedidosEntregados] = useState([]);
  const [loadError,         setLoadError]         = useState("");
  const [searching,         setSearching]         = useState(false);

  const buscarPedidos = useCallback((q = "") => {
    setLoadError("");
    setSearching(true);
    getPedidos({ porPagina: 20, estado: 8, busqueda: q || null, timeout: 90000 })
      .then(data => setPedidosEntregados(data.pedidos || []))
      .catch(err => setLoadError(err?.message || "Error al cargar pedidos entregados"))
      .finally(() => setSearching(false));
  }, []);

  useEffect(() => { buscarPedidos(""); }, [buscarPedidos]);

  // Calcula la cantidad aún devolvible por producto en un pedido,
  // descontando lo que ya fue aprobado o está pendiente de aprobación.
  const calcRestantes = (pedido) => {
    const devsDelPedido = devoluciones.filter(
      d => String(d.idVenta) === String(pedido.id) && d.estado !== "Rechazada"
    );
    return (pedido.productosItems || []).map(p => {
      const yaDevuelto = devsDelPedido.reduce((sum, dev) => {
        const encontrado = (dev.productos || []).find(
          dp => String(dp.idProducto) === String(p.idProducto)
        );
        return sum + (encontrado ? encontrado.cantidad : 0);
      }, 0);
      return { ...p, cantMax: Math.max(0, p.cantidad - yaDevuelto) };
    });
  };

  // Solo lo que de verdad se puede devolver: con producto pendiente, sin una
  // devolución en curso y dentro del plazo. Antes se ofrecían todos los
  // entregados y el rebote llegaba al enviar la solicitud.
  const pedidosDisponibles = pedidosEntregados.filter(ped =>
    calcRestantes(ped).some(p => p.cantMax > 0)
    && !tieneDevolucionActiva(devoluciones, ped.id)
    && !plazoVencido(ped.fecha_entrega, ped.fecha_pedido)
  );
  const hayOcultos = pedidosDisponibles.length < pedidosEntregados.length;

  const [idPedido,   setIdPedido]   = useState("");
  const [motivo,     setMotivo]     = useState("");
  const [comentario, setComentario] = useState("");
  const [evidencia,  setEvidencia]  = useState(null);
  const [items,      setItems]      = useState([]);
  const [errors,     setErrors]     = useState({});
  const [step,       setStep]       = useState(1);

  const pedidoSel = pedidosEntregados.find((p) => String(p.id) === String(idPedido));

  const handleSelectPedido = (val) => {
    setIdPedido(val);
    setErrors((e) => ({ ...e, idPedido: val ? "" : "Debes seleccionar un pedido" }));
    const ped = pedidosEntregados.find((p) => String(p.id) === String(val));
    if (ped) {
      const restantes = calcRestantes(ped);
      setItems(
        restantes
          .filter(p => p.cantMax > 0)
          .map((p) => ({
            idProducto: p.idProducto,
            nombre:     p.nombre,
            precio:     Number(p.precio) || 0,
            cantMax:    p.cantMax,
            cantidad:   0,
          }))
      );
    } else {
      setItems([]);
    }
  };

  const setCantidad = (idx, val) => {
    const n = Math.max(0, Math.min(items[idx].cantMax, Number(val) || 0));
    setItems((prev) => {
      const arr = [...prev];
      arr[idx] = { ...arr[idx], cantidad: n };
      const hasAny = arr.some(i => i.cantidad > 0);
      setErrors((e) => ({ ...e, items: hasAny ? "" : "Selecciona al menos un producto a devolver" }));
      return arr;
    });
  };

  const itemsSeleccionados = items.filter((i) => i.cantidad > 0);
  const totalDevolucion    = itemsSeleccionados.reduce((a, i) => a + i.precio * i.cantidad, 0);

  const validateStep = (s) => {
    const e = {};
    if (s === 1 && !idPedido) {
      e.idPedido = "Debes seleccionar un pedido";
    }
    if (s === 2 && itemsSeleccionados.length === 0) {
      e.items = "Selecciona al menos un producto a devolver";
    }
    if (s === 3 && !motivo) {
      e.motivo = "Selecciona el motivo de la devolución";
    }
    return e;
  };

  const handleNext = () => {
    const e = validateStep(step);
    if (Object.keys(e).length) { setErrors(e); return; }
    setStep((s) => s + 1);
  };

  const handleBack = () => setStep((s) => s - 1);

  const handleSave = () => {
    const e = validateStep(3);
    if (Object.keys(e).length) { setErrors(e); return; }
    onSave({
      idPedido:     pedidoSel.id,
      numeroPedido: pedidoSel.numero,
      idCliente:    pedidoSel.idCliente,
      cliente:      pedidoSel.cliente,
      motivo,
      comentario,
      productos: itemsSeleccionados.map((i) => ({
        idProducto:     i.idProducto,
        nombre:         i.nombre,
        cantidad:       i.cantidad,
        precioUnitario: i.precio,
        subtotal:       i.precio * i.cantidad,
      })),
      totalDevuelto: totalDevolucion,
      evidencia:     evidencia ? evidencia.url : null,
    });
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card modal-devolucion" style={{ maxWidth: 760 }} onClick={(e) => e.stopPropagation()}>

        {/* Header */}
        <div className="modal-header modal-header--red" style={{ padding: "12px 20px" }}>
          <div>
            <p className="modal-header__eyebrow">Devoluciones</p>
            <h2 className="modal-header__title" style={{ fontSize: "1.2rem" }}>
              Registrar devolución
            </h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16}/></button>
        </div>

        {/* Steps */}
        <div style={{ padding: "8px 20px 0" }}>
          <StepsBar current={step} />
        </div>

        <div className="modal-body" style={{ overflowY: "auto", minHeight: 0 }}>

          {/* ── Paso 1: Seleccionar pedido ── */}
          {step === 1 && (
            <>
              <p className="section-label" style={{ marginTop: 0, marginBottom: 0 }}>
                Pedido entregado
              </p>

              {loadError && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "10px 14px", background: "#ffebee", border: "1px solid #ef9a9a", borderRadius: 10, color: "#c62828", fontSize: 13, fontWeight: 600 }}>
                  <span style={{display:"flex",alignItems:"center",gap:5}}><AlertTriangle size={13}/> El servidor tardó en responder.</span>
                  <button
                    onClick={() => buscarPedidos("")}
                    style={{ background: "#c62828", color: "#fff", border: "none", borderRadius: 7, padding: "5px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}
                  >
                    Reintentar
                  </button>
                </div>
              )}

              <div className="field-wrap">
                <label className="field-label">
                  Selecciona un pedido <span className="required">*</span>
                </label>
                <PedidoSelect
                  value={idPedido}
                  pedidos={pedidosDisponibles}
                  hayOcultos={hayOcultos}
                  error={errors.idPedido}
                  disabled={false}
                  searching={searching}
                  onSearch={buscarPedidos}
                  onChange={handleSelectPedido}
                />
                {errors.idPedido && <span className="field-error">{errors.idPedido}</span>}
              </div>

              {pedidoSel && <ResumenPedido pedido={pedidoSel} />}
            </>
          )}

          {/* ── Paso 2: Productos a devolver ── */}
          {step === 2 && (
            <>
              <p className="section-label" style={{ marginTop: 0, marginBottom: 0 }}>
                ¿Qué productos quieres devolver?
              </p>

              <div className="prod-dev-list">
                <div className="prod-dev-list__header">
                  <span>Producto</span>
                  <span style={{ textAlign: "center" }}>Cantidad</span>
                  <span style={{ textAlign: "right" }}>Subtotal</span>
                </div>
                {items.length === 0 ? (
                  <div style={{ padding: "14px", textAlign: "center", fontSize: 13, color: "#bdbdbd" }}>
                    Sin productos disponibles
                  </div>
                ) : (
                  items.map((item, idx) => (
                    <ProdItem key={idx} item={item} idx={idx} onSet={setCantidad} />
                  ))
                )}
              </div>

              {errors.items && <p className="field-error">{errors.items}</p>}

              {totalDevolucion > 0 && (
                <div className="dev-subtotal-bar">
                  <span>Subtotal a devolver</span>
                  <span className="dev-subtotal-bar__val">{fmt(totalDevolucion)}</span>
                </div>
              )}
            </>
          )}

          {/* ── Paso 3: Motivo y detalles ── */}
          {step === 3 && (
            <>
              <p className="section-label" style={{ marginTop: 0, marginBottom: 0 }}>
                Motivo de la devolución
              </p>

              <div className="field-wrap">
                <label className="field-label">
                  Motivo <span className="required">*</span>
                </label>
                <SearchableSelect
                  options={MOTIVOS.map(m => ({ value: m, label: m }))}
                  value={motivo}
                  onChange={e => { setMotivo(e.target.value); setErrors(prev => ({ ...prev, motivo: "" })); }}
                  getValue={o => o.value}
                  getLabel={o => o.label}
                  placeholder="Seleccione…"
                  searchPlaceholder="Buscar motivo…"
                  className={`field-select${errors.motivo ? " error" : ""}`}
                />
                {errors.motivo && <span className="field-error">{errors.motivo}</span>}
              </div>

              <div className="field-wrap">
                <label className="field-label">Comentario (opcional)</label>
                <textarea
                  className="field-textarea"
                  rows={2}
                  placeholder="Describe el problema con más detalle…"
                  value={comentario}
                  onChange={(e) => setComentario(e.target.value)}
                />
              </div>

              <div className="field-wrap">
                <label className="field-label">Evidencia (opcional)</label>
                <EvidenciaUpload evidencia={evidencia} onEvidencia={setEvidencia} />
              </div>

              <div className="dev-resumen-final">
                <div className="dev-resumen-final__row">
                  <span>Productos a devolver</span>
                  <span>{itemsSeleccionados.length} ítem{itemsSeleccionados.length !== 1 ? "s" : ""}</span>
                </div>
                <div className="dev-resumen-final__row dev-resumen-final__row--total">
                  <span>Total a devolver</span>
                  <span>{fmt(totalDevolucion)}</span>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer" style={{ justifyContent: "space-between", padding: "10px 20px" }}>
          {step > 1 ? (
            <button className="btn-ghost" onClick={handleBack}>← Atrás</button>
          ) : (
            <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          )}

          {step < 3 ? (
            <button className="btn-save" onClick={handleNext}>
              Siguiente →
            </button>
          ) : (
            <button
              className="btn-save"
              style={{ background: "#c62828" }}
              onClick={handleSave}
              disabled={saving || totalDevolucion === 0}
            >
              {saving ? "Guardando…" : "Registrar devolución"}
            </button>
          )}
        </div>

      </div>
    </div>
  );
}
