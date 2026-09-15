import { useState, useEffect, useRef } from "react";
import * as XLSX from "xlsx";
import { getSalidas, registrarSalida, anularSalida, procesarVencidos } from "../../services/salidasService.js";
import { getProductos } from "../../services/productosService.js";
import { getInsumos } from "../../services/insumosService.js";
import { usePrivilegios } from "../../context/PrivilegiosContext.jsx";
import FilasRelleno from "../../shared/components/FilasRelleno";
import { Clock, Flame, Scale, Utensils, CornerUpLeft, ClipboardList, X, Package, Archive, Ban, Search, CheckCircle2, XCircle, RefreshCw, BarChart2, Calendar, Printer, TrendingDown, Lock, AlertTriangle, Eye } from "lucide-react";
import "./Salidas.css";

/* ══════════════════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════════════════ */

const ITEMS_PER_PAGE = 5;

function hoyISO() { return new Date().toISOString().split("T")[0]; }

const TIPOS = [
  { val: "vencimiento", label: "Vencido",    Icon: Clock,        color: "#e65100", bg: "#fff3e0", border: "#ffcc80" },
  { val: "daño",        label: "Dañado",     Icon: Flame,        color: "#c62828", bg: "#ffebee", border: "#ef9a9a" },
  { val: "ajuste",      label: "Ajuste",     Icon: Scale,        color: "#1565c0", bg: "#e3f2fd", border: "#90caf9" },
  { val: "consumo",     label: "Consumo",    Icon: Utensils,     color: "#4a148c", bg: "#f3e5f5", border: "#ce93d8" },
  { val: "devolución",  label: "Devolución", Icon: CornerUpLeft, color: "#2e7d32", bg: "#e8f5e9", border: "#a5d6a7" },
];
const TIPO_MAP = Object.fromEntries(TIPOS.map(t => [t.val, t]));

function fmtDate(dt) {
  if (!dt) return null;
  return String(dt).split("T")[0];
}

function adaptarSalida(s) {
  return {
    id:              s.ID_Salida,
    tipo:            s.Tipo,
    entidadId:       s.ID_Insumo || s.ID_Producto,
    entidadTipo:     s.ID_Insumo ? "insumo" : "producto",
    entidadNombre:   s.nombre_insumo || s.nombre_producto || "—",
    entidadCat:      s.nombre_categoria || "—",
    unidad:          s.simbolo_unidad || "uds.",
    cantidad:        s.Cantidad,
    motivo:          s.Motivo,
    fecha:           fmtDate(s.Fecha),
    anulada:         s.Estado === 12,
    estadoLabel:     s.estado_label || "Activa",
    empleado:        s.nombre_empleado || (s.Tipo === "vencimiento" ? "Sistema (auto)" : "—"),
    anuladoPor:      s.nombre_anulado_por || null,
    fechaAnulacion:  fmtDate(s.Fecha_Anulacion),
  };
}


/* ══════════════════════════════════════════════════════════
   MODAL VER DETALLE
══════════════════════════════════════════════════════════ */
function InfoRow({ label, value, color }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: "0.6px" }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color || "#1a1a1a" }}>{value}</span>
    </div>
  );
}

function ModalVerDetalle({ salida, onClose }) {
  const tc = TIPO_MAP[salida.tipo] || { color: "#757575", bg: "#f5f5f5", border: "#e0e0e0", Icon: ClipboardList, label: salida.tipo };
  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 460 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header" style={{ background: `linear-gradient(135deg, ${tc.color} 0%, ${tc.color}cc 100%)` }}>
          <div>
            <p className="modal-header__eyebrow">Detalle de salida #{salida.id}</p>
            <h2 className="modal-header__title" style={{display:"flex",alignItems:"center",gap:8}}><tc.Icon size={16}/> {tc.label}</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16}/></button>
        </div>
        <div className="modal-body" style={{ padding: "20px 24px 24px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <InfoRow label="Estado"         value={salida.estadoLabel} color={salida.anulada ? "#c62828" : "#2e7d32"} />
            <InfoRow label="Tipo elemento"  value={salida.entidadTipo === "producto" ? "Producto" : "Insumo"} />
            <InfoRow label="Elemento"       value={salida.entidadNombre} />
            <InfoRow label="Categoría"      value={salida.entidadCat} />
            <InfoRow label="Cantidad"       value={`-${salida.cantidad} ${salida.unidad}`} color="#c62828" />
            <InfoRow label="Registrado por" value={salida.empleado} />
            <InfoRow label="Fecha registro" value={salida.fecha || "—"} />
            {salida.anulada && (
              <InfoRow label="Anulado por"    value={salida.anuladoPor || "—"} color="#c62828" />
            )}
            {salida.anulada && (
              <InfoRow label="Fecha anulación" value={salida.fechaAnulacion || "—"} />
            )}
          </div>
          {salida.motivo && (
            <div style={{ marginTop: 14, padding: "10px 14px", background: "#f9f9f9", borderRadius: 9, border: "1px solid #e0e0e0" }}>
              <InfoRow label="Motivo" value={salida.motivo} />
            </div>
          )}
          <div style={{ marginTop: 20, textAlign: "right" }}>
            <button className="btn-ghost" onClick={onClose}>Cerrar</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MODAL CONFIRMAR ANULAR
══════════════════════════════════════════════════════════ */
function ModalConfirmarAnular({ salida, onConfirmar, onCancelar }) {
  const tc = TIPO_MAP[salida.tipo] || { color: "#757575", bg: "#f5f5f5", border: "#e0e0e0", Icon: ClipboardList, label: salida.tipo };
  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 420 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Confirmar acción</p>
            <h2 className="modal-header__title">Anular salida</h2>
          </div>
          <button className="modal-close-btn" onClick={onCancelar}><X size={16}/></button>
        </div>
        <div className="modal-body" style={{ padding: "20px 24px 24px" }}>
          <div className="sl-confirm-card">
            <div className="sl-confirm-card__icon"><Ban size={30}/></div>
            <p className="sl-confirm-card__text">
              ¿Estás seguro de que deseas anular esta salida? El stock será <strong>reintegrado automáticamente</strong>.
            </p>
            <div className="sl-confirm-card__detail" style={{ borderColor: tc.border, background: tc.bg }}>
              <span style={{ display:"flex",alignItems:"center" }}>{salida.entidadTipo === "producto" ? <Package size={18}/> : <Archive size={18}/>}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: "#1a1a1a" }}>{salida.entidadNombre}</div>
                <div style={{ display: "flex", gap: 8, marginTop: 3, flexWrap: "wrap" }}>
                  <span className="sl-tipo-badge" style={{ color: tc.color, background: "#fff", border: `1px solid ${tc.border}`, fontSize: 11, display:"flex",alignItems:"center",gap:4 }}>
                    <tc.Icon size={11}/> {tc.label}
                  </span>
                  <span style={{ fontSize: 12, color: "#c62828", fontWeight: 700 }}>-{salida.cantidad} uds.</span>
                  <span style={{ fontSize: 12, color: "#9e9e9e" }}>{salida.fecha}</span>
                </div>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button className="sl-btn-cancel" onClick={onCancelar}>Cancelar</button>
            <button className="sl-btn-delete" onClick={onConfirmar}>Sí, anular</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MODAL REGISTRAR SALIDA
══════════════════════════════════════════════════════════ */
function RegistrarSalida({ productos, insumos, onClose, onRegistrada }) {
  const [entidadTipo,  setEntidadTipo]  = useState("producto");
  const [busqueda,     setBusqueda]     = useState("");
  const [seleccionado, setSeleccionado] = useState(null);
  const [tipoSalida,   setTipoSalida]   = useState("daño");
  const [cantidad,     setCantidad]     = useState("");
  const [motivo,       setMotivo]       = useState("");
  const [errors,    setErrors] = useState({});
  const [saving,    setSaving] = useState(false);
  const [errToast,  setErrToast] = useState(null);

  const showErrToast = (msg) => {
    setErrToast(msg);
    setTimeout(() => setErrToast(null), 3500);
  };

  const lista = entidadTipo === "producto" ? productos : insumos;
  const filtrados = lista.filter(e =>
    (e.nombre || "").toLowerCase().includes(busqueda.toLowerCase()) ||
    (e._label || "").toLowerCase().includes(busqueda.toLowerCase())
  );

  const unidadLabel  = seleccionado?._unidad || "uds.";
  const stockActual  = seleccionado?._stock ?? 0;
  const tipoActual   = TIPO_MAP[tipoSalida];
  const stockDespues = Math.max(0, stockActual - (Number(cantidad) || 0));
  const pct          = stockActual > 0 ? Math.min(100, Math.round((stockDespues / stockActual) * 100)) : 0;

  const validate = () => {
    const e = {};
    if (!seleccionado) e.seleccionado = "Selecciona un producto o insumo";
    if (stockActual === 0) {
      e.cantidad = "No se puede registrar la salida. El producto no tiene stock disponible.";
    } else if (!cantidad || isNaN(cantidad)) {
      e.cantidad = "Ingresa una cantidad válida.";
    } else if (Number(cantidad) < 0) {
      e.cantidad = "La cantidad no puede ser negativa.";
    } else if (Number(cantidad) === 0) {
      e.cantidad = "La cantidad debe ser mayor que 0.";
    } else if (Number(cantidad) > stockActual) {
      e.cantidad = `Stock insuficiente. Solo hay ${stockActual} ${unidadLabel} disponibles.`;
    }
    return e;
  };

  const handleRegistrar = async () => {
    const e = validate();
    if (Object.keys(e).length) { setErrors(e); return; }
    setSaving(true);
    try {
      await registrarSalida({
        tipo:       tipoSalida,
        idProducto: seleccionado._tipo === "producto" ? seleccionado.id : null,
        idInsumo:   seleccionado._tipo === "insumo"   ? seleccionado.id : null,
        cantidad:   Number(cantidad),
        motivo:     motivo.trim() || undefined,
      });
      onRegistrada?.(`Salida registrada — ${seleccionado.nombre} (-${cantidad} ${unidadLabel})`);
      return; // el modal se desmonta; no tocar estado después de aquí
    } catch (err) {
      showErrToast(err.message || "Error al registrar");
    }
    setSaving(false);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 850 }}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Logística</p>
            <h2 className="modal-header__title">Registrar Salida</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16}/></button>
        </div>

        <div className="modal-body">
          <div className="sl-registrar-grid">
            <div className="sl-panel">
              <p className="sl-panel__title">1 · Seleccionar elemento</p>
              <div className="sl-tipo-tabs">
                <button className={`sl-tipo-tab${entidadTipo === "producto" ? " active" : ""}`}
                  onClick={() => { setEntidadTipo("producto"); setSeleccionado(null); setBusqueda(""); }}
                  style={{display:"flex",alignItems:"center",gap:6}}>
                  <Package size={14}/> Productos
                </button>
                <button className={`sl-tipo-tab${entidadTipo === "insumo" ? " active" : ""}`}
                  onClick={() => { setEntidadTipo("insumo"); setSeleccionado(null); setBusqueda(""); }}
                  style={{display:"flex",alignItems:"center",gap:6}}>
                  <Archive size={14}/> Insumos
                </button>
              </div>
              <div className="sl-search">
                <span className="sl-search__icon"><Search size={16}/></span>
                <input className="sl-search__input" placeholder="Buscar por nombre o categoría…"
                  value={busqueda}
                  onChange={e => { setBusqueda(e.target.value); setErrors(p => ({ ...p, seleccionado: "" })); }} />
              </div>
              <div className="sl-lista">
                {filtrados.length === 0
                  ? <div className="sl-lista__empty">Sin resultados</div>
                  : filtrados.map(item => {
                      const stock = item._stock;
                      const min   = item.stockMinimo ?? 10;
                      const agot  = stock === 0;
                      const bajo  = stock < min && !agot;
                      return (
                        <button key={`${item._tipo}-${item.id}`}
                          className={`sl-lista__item${seleccionado?.id === item.id && seleccionado?._tipo === item._tipo ? " selected" : ""}`}
                          onClick={() => {
                            setSeleccionado(item);
                            setErrors(p => ({
                              ...p,
                              seleccionado: "",
                              cantidad: agot ? "No se puede registrar la salida. El producto no tiene stock disponible." : "",
                            }));
                          }}
                          style={agot ? { borderColor: "#ef9a9a", background: "#fff8f8" } : undefined}>
                          <div className="sl-lista__item-name" style={agot ? { color: "#c62828" } : undefined}>
                            {item.nombre}
                          </div>
                          <div className="sl-lista__item-meta">
                            <span className="sl-lista__item-cat">{item._label}</span>
                            <span style={{ fontWeight: 700, fontSize: 12, color: agot ? "#c62828" : bajo ? "#f57f17" : "#2e7d32" }}>
                              {stock} {item._unidad || "uds."}
                            </span>
                          </div>
                        </button>
                      );
                    })
                }
              </div>
              {errors.seleccionado && <p className="field-error" style={{ marginTop: 6 }}>{errors.seleccionado}</p>}
            </div>

            <div className="sl-panel sl-panel--form">
              <p className="sl-panel__title">2 · Registrar salida</p>
              {seleccionado ? (
                <div className="sl-seleccionado">
                  <span style={{ display:"flex",alignItems:"center" }}>{seleccionado._tipo === "producto" ? <Package size={22}/> : <Archive size={22}/>}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>{seleccionado.nombre}</div>
                    <div style={{ fontSize: 12, color: "#9e9e9e" }}>
                      Stock actual: <strong style={{ color: "#2e7d32" }}>{stockActual} {unidadLabel}</strong>
                    </div>
                  </div>
                  <button onClick={() => { setSeleccionado(null); setCantidad(""); setErrors({}); }}
                    style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "#bdbdbd" }}><X size={16}/></button>
                </div>
              ) : (
                <div className="sl-seleccionado sl-seleccionado--empty">
                  <span style={{ opacity: 0.3 }}><Package size={26}/></span>
                  <span style={{ fontSize: 13, color: "#bdbdbd" }}>Selecciona un elemento</span>
                </div>
              )}

              <div style={{ marginTop: 10, marginBottom: 10 }}>
                <label className="sl-label">Tipo de salida</label>
                <div className="sl-tipos-grid">
                  {TIPOS.filter(t => t.val !== "vencimiento").map(t => (
                    <button key={t.val} onClick={() => setTipoSalida(t.val)}
                      className={`sl-tipo-btn${tipoSalida === t.val ? " active" : ""}`}
                      style={tipoSalida === t.val ? { borderColor: t.border, background: t.bg, color: t.color } : {}}>
                      <t.Icon size={17}/>
                      <span>{t.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ marginBottom: 10 }}>
                <label className="sl-label">Cantidad a descontar</label>
                <div style={{ position: "relative" }}>
                  <input type="number" min="1" max={stockActual}
                    className={`sl-input${errors.cantidad ? " sl-input--error" : ""}`}
                    value={cantidad}
                    onKeyDown={e => { if (["-", "e", "E", "+", "."].includes(e.key)) e.preventDefault(); }}
                    onChange={e => {
                      const v = e.target.value;
                      setCantidad(v);
                      let err = "";
                      if (v !== "" && isNaN(v)) err = "Ingresa una cantidad válida.";
                      else if (v !== "" && Number(v) < 0) err = "La cantidad no puede ser negativa.";
                      else if (v !== "" && Number(v) === 0) err = "La cantidad debe ser mayor que 0.";
                      else if (v !== "" && Number(v) > stockActual) err = `Stock insuficiente. Solo hay ${stockActual} ${unidadLabel} disponibles.`;
                      setErrors(p => ({ ...p, cantidad: err }));
                    }}
                    placeholder={seleccionado ? `Máx. ${stockActual}` : "—"}
                    disabled={!seleccionado || stockActual === 0} />
                  <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", fontSize: 12, color: "#9e9e9e", pointerEvents: "none" }}>
                    {unidadLabel}
                  </span>
                </div>
                {errors.cantidad && <p className="field-error">{errors.cantidad}</p>}
              </div>

              {seleccionado && cantidad && !errors.cantidad && (
                <div style={{ marginBottom: 12, padding: "10px 14px", borderRadius: 10, background: tipoActual.bg, border: `1px solid ${tipoActual.border}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: 12 }}>
                    <span style={{ color: "#9e9e9e" }}>Stock después de la salida</span>
                    <span style={{ fontWeight: 700, color: tipoActual.color }}>{stockDespues} {unidadLabel}</span>
                  </div>
                  <div style={{ height: 5, background: "#e0e0e0", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 3, transition: "width 0.35s", width: pct + "%", background: pct > 50 ? "#43a047" : pct > 20 ? "#ffa726" : "#ef5350" }} />
                  </div>
                </div>
              )}

              <div style={{ marginBottom: 10 }}>
                <label className="sl-label">Motivo <span style={{ color: "#bdbdbd", fontWeight: 400, textTransform: "none" }}>(opcional)</span></label>
                <input className="sl-input" value={motivo}
                  onChange={e => setMotivo(e.target.value)}
                  placeholder="Descripción adicional…" disabled={!seleccionado} />
              </div>

              <button className="sl-btn-registrar" onClick={handleRegistrar}
                disabled={saving || !seleccionado || stockActual === 0}
                style={{ background: tipoActual.color }}>
                {saving ? "Registrando…" : <><tipoActual.Icon size={14}/> {`Registrar ${tipoActual.label.toLowerCase()}`}</>}
              </button>
            </div>
          </div>
        </div>
      </div>

      {errToast && (
        <div className="sl-toast" style={{ background: "#c62828" }}>
          <XCircle size={14}/> {errToast}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   SKELETON
══════════════════════════════════════════════════════════ */
function SkeletonRows({ cols = 7 }) {
  return Array.from({ length: 5 }, (_, i) => (
    <tr key={i}>
      {Array.from({ length: cols }, (_, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

/* ══════════════════════════════════════════════════════════
   TAB HISTORIAL
══════════════════════════════════════════════════════════ */
function HistorialSalidas({ salidas, loading, onAgregarClick, cargarSalidas }) {
  const [filtroTipo,      setFiltroTipo]     = useState("todos");
  const [filtroEntidad,   setFiltroEntidad]  = useState("todos");
  const [busqueda,        setBusqueda]       = useState("");
  const [showFilter,      setShowFilter]     = useState(false);
  const [salidaAAnular,   setSalidaAAnular]  = useState(null);
  const [salidaAVer,      setSalidaAVer]     = useState(null);
  const [toast,           setToast]          = useState(null);
  const [page,            setPage]           = useState(1);
  const filterRef = useRef();

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    const h = e => { if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  useEffect(() => { setPage(1); }, [filtroTipo, filtroEntidad, busqueda]);

  const filtradas = salidas.filter(s => {
    const matchTipo    = filtroTipo    === "todos" || s.tipo === filtroTipo;
    const matchEntidad = filtroEntidad === "todos" || s.entidadTipo === filtroEntidad;
    const matchQ       = s.entidadNombre.toLowerCase().includes(busqueda.toLowerCase()) ||
                         (s.motivo || "").toLowerCase().includes(busqueda.toLowerCase());
    return matchTipo && matchEntidad && matchQ;
  });

  const totalPages = Math.ceil(filtradas.length / ITEMS_PER_PAGE);
  const safePage   = Math.min(page, Math.max(1, totalPages));
  const paginadas  = filtradas.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);
  const totalUnidades = salidas.filter(s => !s.anulada).reduce((acc, s) => acc + (s.cantidad || 0), 0);

  const toggleFiltroTipo = (val) => setFiltroTipo(prev => prev === val ? "todos" : val);

  const handleConfirmarAnular = async () => {
    if (!salidaAAnular) return;
    try {
      await anularSalida(salidaAAnular.id);
      showToast("Salida anulada — stock reintegrado");
      await cargarSalidas();
    } catch (err) {
      showToast(err.message || "Error al anular", "error");
    }
    setSalidaAAnular(null);
  };

  return (
    <div className="sl-tab-content">
      {/* Stats */}
      <div className="sl-stats-row">
        <div className={`sl-stat-card ${filtroTipo === "todos" && filtroEntidad === "todos" ? "active" : ""}`}
          onClick={() => { setFiltroTipo("todos"); setFiltroEntidad("todos"); }} style={{ cursor: "pointer" }}>
          <span className="sl-stat-card__num">{salidas.length}</span>
          <span className="sl-stat-card__label">Total salidas</span>
        </div>
        <div className="sl-stat-card">
          <span className="sl-stat-card__num">{totalUnidades}</span>
          <span className="sl-stat-card__label">Unidades</span>
        </div>
        {TIPOS.map(t => {
          const count = salidas.filter(s => s.tipo === t.val).length;
          return (
            <div key={t.val} className={`sl-stat-card ${filtroTipo === t.val ? "active" : ""}`}
              style={{ borderColor: count > 0 ? (filtroTipo === t.val ? t.color : t.border) : "#e0e0e0", cursor: "pointer" }}
              onClick={() => toggleFiltroTipo(t.val)}>
              <t.Icon size={18}/>
              <span className="sl-stat-card__num" style={{ color: count > 0 ? t.color : "#bdbdbd", fontSize: 18 }}>{count}</span>
              <span className="sl-stat-card__label">{t.label}</span>
            </div>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="sl-toolbar" style={{ alignItems: "stretch" }}>
        <div className="sl-search" style={{ flex: 1, marginBottom: 0, display: "flex", alignItems: "center" }}>
          <span className="sl-search__icon"><Search size={16}/></span>
          <input className="sl-search__input" placeholder="Buscar por nombre o motivo…"
            value={busqueda} onChange={e => setBusqueda(e.target.value)} style={{ height: "100%" }} />
        </div>
        <div ref={filterRef} style={{ position: "relative", display: "flex" }}>
          <button className={`sl-filter-btn ${filtroTipo !== "todos" || filtroEntidad !== "todos" ? "has-filter" : ""}`}
            onClick={() => setShowFilter(v => !v)}>▼ Filtros</button>
          {showFilter && (
            <div className="sl-filter-dropdown sl-filter-dropdown--wide">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <div>
                  <p className="sl-filter-title">Tipo de salida</p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 2 }}>
                    {[{ val: "todos", label: "Todos", Icon: ClipboardList }, ...TIPOS].map(t => (
                      <button key={t.val} className={`sl-filter-opt${filtroTipo === t.val ? " active" : ""}`}
                        onClick={() => setFiltroTipo(t.val)} style={{display:"flex",alignItems:"center",gap:6}}>
                        <t.Icon size={13}/>{t.val === "todos" ? "Todos los tipos" : t.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div style={{ borderLeft: "1px solid #f0f0f0", paddingLeft: 12 }}>
                  <p className="sl-filter-title">Tipo de elemento</p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 2 }}>
                    {[{ val: "todos", label: "Todos", Icon: ClipboardList }, { val: "producto", label: "Productos", Icon: Package }, { val: "insumo", label: "Insumos", Icon: Archive }]
                      .map(opt => (
                        <button key={opt.val} className={`sl-filter-opt${filtroEntidad === opt.val ? " active" : ""}`}
                          onClick={() => { setFiltroEntidad(opt.val); setShowFilter(false); }}
                          style={{display:"flex",alignItems:"center",gap:6}}>
                          <opt.Icon size={13}/>{opt.label}
                        </button>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
        {(filtroTipo !== "todos" || filtroEntidad !== "todos" || busqueda) && (
          <button className="btn-limpiar" onClick={() => { setBusqueda(""); setFiltroTipo("todos"); setFiltroEntidad("todos"); }} style={{display:"flex",alignItems:"center",gap:6}}>
            <X size={14}/> Limpiar
          </button>
        )}

        <button className="btn-agregar" onClick={onAgregarClick} data-tooltip="Registrar nueva salida">
          Registrar Salida <span style={{ fontSize: 18 }}>+</span>
        </button>
      </div>

      <div className="card">
        <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "60px", "--tbl-rows": ITEMS_PER_PAGE }}>
        <table className="tbl tbl--fixed-rows">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Elemento</th>
                <th>Categoría</th>
                <th>Cantidad</th>
                <th>Motivo</th>
                <th>Fecha</th>
                <th style={{ width: 80, textAlign: "center" }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows />
              ) : paginadas.length === 0 ? (
                <tr><td colSpan={7}>
                  <div className="empty-state">
                    <div className="empty-state__icon"><ClipboardList size={36} strokeWidth={1} style={{color:"#bdbdbd"}}/></div>
                    <p className="empty-state__text">No hay salidas registradas</p>
                  </div>
                </td></tr>
              ) : paginadas.map((s, idx) => {
                const tc = TIPO_MAP[s.tipo] || { color: "#757575", bg: "#f5f5f5", border: "#e0e0e0", Icon: ClipboardList, label: s.tipo };
                return (
                  <tr key={s.id || idx} className="tbl-row" style={{ opacity: s.anulada ? 0.5 : 1 }}>
                    <td>
                      <span className="sl-tipo-badge" style={{ color: tc.color, background: tc.bg, border: `1px solid ${tc.border}`, display:"flex",alignItems:"center",gap:4 }}>
                        <tc.Icon size={12}/> {tc.label}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ display:"flex",alignItems:"center" }}>{s.entidadTipo === "producto" ? <Package size={15}/> : <Archive size={15}/>}</span>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: 13 }}>{s.entidadNombre}</div>
                          <div style={{ fontSize: 11, color: "#9e9e9e" }}>{s.entidadTipo}</div>
                        </div>
                      </div>
                    </td>
                    <td><span style={{ fontSize: 12, color: "#616161" }}>{s.entidadCat}</span></td>
                    <td><span style={{ fontWeight: 700, color: "#c62828", fontSize: 14 }}>-{s.cantidad} <span style={{ fontWeight: 400, fontSize: 11, color: "#9e9e9e" }}>{s.unidad}</span></span></td>
                    <td><span style={{ fontSize: 13, color: "#424242" }}>{s.motivo || "—"}</span></td>
                    <td><span style={{ fontSize: 12, color: "#9e9e9e" }}>{s.fecha || "—"}</span></td>
                    <td>
                      <div className="sl-table-actions">
                        <button className="sl-action-btn" data-tooltip="Ver detalles" onClick={() => setSalidaAVer(s)}
                          style={{ background: "#e3f2fd", color: "#1565c0", border: "1.5px solid #90caf9" }}><Eye size={15}/></button>
                        {s.anulada
                          ? <span className="sl-action-locked" title="Salida anulada"><Ban size={15}/></span>
                          : <button className="sl-action-btn sl-action-btn--delete" data-tooltip="Anular salida" onClick={() => setSalidaAAnular(s)}><Ban size={15}/></button>
                        }
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!loading && (
                <FilasRelleno current={paginadas.length} perPage={ITEMS_PER_PAGE} colSpan={7} />
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="pagination-bar">
        <span className="pagination-count">
          {filtradas.length} {filtradas.length === 1 ? "salida" : "salidas"} en total
        </span>
        <div className="pagination-btns">
          <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
          <button className="pg-btn-arrow" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
          <span className="pg-pill">Página {safePage} de {Math.max(1, totalPages)}</span>
          <button className="pg-btn-arrow" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}>›</button>
          <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage >= totalPages}>»</button>
        </div>
      </div>

      {salidaAVer && (
        <ModalVerDetalle salida={salidaAVer} onClose={() => setSalidaAVer(null)} />
      )}

      {salidaAAnular && (
        <ModalConfirmarAnular
          salida={salidaAAnular}
          onConfirmar={handleConfirmarAnular}
          onCancelar={() => setSalidaAAnular(null)}
        />
      )}

      {toast && (
        <div className="sl-toast" style={{ background: toast.type === "error" ? "#c62828" : "#2e7d32" }}>
          {toast.type === "error" ? <XCircle size={14}/> : <CheckCircle2 size={14}/>} {toast.msg}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   TAB VENCIDOS
══════════════════════════════════════════════════════════ */
function Vencidos({ salidas, loading, cargarSalidas }) {
  const [filtro,     setFiltro]     = useState("todos");
  const [procesando, setProcesando] = useState(false);
  const [toast,      setToast]      = useState(null);
  const [page,       setPage]       = useState(1);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => { setPage(1); }, [filtro]);

  const vencimientos = salidas.filter(s => s.tipo === "vencimiento");
  const porProducto  = vencimientos.filter(s => s.entidadTipo === "producto");
  const porInsumo    = vencimientos.filter(s => s.entidadTipo === "insumo");
  const totalUnidades = vencimientos.filter(s => !s.anulada).reduce((acc, s) => acc + (s.cantidad || 0), 0);

  const filtrados = filtro === "producto" ? porProducto
    : filtro === "insumo" ? porInsumo
    : vencimientos;

  const totalPages = Math.ceil(filtrados.length / ITEMS_PER_PAGE);
  const safePage   = Math.min(page, Math.max(1, totalPages));
  const paginados  = filtrados.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);

  const handleProcesar = async () => {
    setProcesando(true);
    try {
      const res = await procesarVencidos();
      showToast(`${res.procesados} lote(s) procesado(s) — stock descontado`);
      await cargarSalidas();
    } catch (err) {
      showToast(err.message || "Error al procesar vencidos", "error");
    }
    setProcesando(false);
  };

  return (
    <div className="sl-tab-content">
      {/* Stats */}
      <div className="sl-stats-row">
        <div className={`sl-stat-card ${filtro === "todos" ? "active" : ""}`}
          style={{ cursor: "pointer", borderColor: vencimientos.length > 0 ? (filtro === "todos" ? "#c62828" : "#ef9a9a") : "#e0e0e0" }}
          onClick={() => setFiltro("todos")}>
          <AlertTriangle size={18}/>
          <span className="sl-stat-card__num" style={{ color: vencimientos.length > 0 ? "#c62828" : "#bdbdbd" }}>{vencimientos.length}</span>
          <span className="sl-stat-card__label">Total vencimientos</span>
        </div>
        <div className="sl-stat-card">
          <TrendingDown size={18}/>
          <span className="sl-stat-card__num" style={{ color: totalUnidades > 0 ? "#c62828" : "#bdbdbd" }}>{totalUnidades}</span>
          <span className="sl-stat-card__label">Unidades perdidas</span>
        </div>
        <div className={`sl-stat-card ${filtro === "producto" ? "active" : ""}`}
          style={{ cursor: "pointer", borderColor: porProducto.length > 0 ? (filtro === "producto" ? "#c62828" : "#ef9a9a") : "#e0e0e0" }}
          onClick={() => setFiltro("producto")}>
          <Package size={18}/>
          <span className="sl-stat-card__num" style={{ color: porProducto.length > 0 ? "#c62828" : "#bdbdbd" }}>{porProducto.length}</span>
          <span className="sl-stat-card__label">Productos</span>
        </div>
        <div className={`sl-stat-card ${filtro === "insumo" ? "active" : ""}`}
          style={{ cursor: "pointer", borderColor: porInsumo.length > 0 ? (filtro === "insumo" ? "#c62828" : "#ef9a9a") : "#e0e0e0" }}
          onClick={() => setFiltro("insumo")}>
          <Archive size={18}/>
          <span className="sl-stat-card__num" style={{ color: porInsumo.length > 0 ? "#c62828" : "#bdbdbd" }}>{porInsumo.length}</span>
          <span className="sl-stat-card__label">Insumos</span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="sl-toolbar">
        <div style={{ display: "flex", gap: 6 }}>
          {[
            { val: "todos",    label: "Todos",     Icon: ClipboardList },
            { val: "producto", label: "Productos", Icon: Package },
            { val: "insumo",   label: "Insumos",   Icon: Archive },
          ].map(opt => (
            <button key={opt.val}
              className={`sl-pill${filtro === opt.val ? " active" : ""}`}
              onClick={() => setFiltro(opt.val)} style={{display:"flex",alignItems:"center",gap:6}}>
              <opt.Icon size={13}/> {opt.label}
            </button>
          ))}
        </div>
        <button className="btn-agregar" onClick={handleProcesar} disabled={procesando}
          style={{ marginLeft: "auto", background: procesando ? "#bdbdbd" : "#c62828" }}>
          {procesando ? "Procesando…" : <><RefreshCw size={14}/> Procesar vencidos</>}
        </button>
      </div>

      {/* Tabla compacta */}
      <div className="card">
        <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "60px", "--tbl-rows": ITEMS_PER_PAGE }}>
        <table className="tbl tbl--fixed-rows">
          <thead>
            <tr>
              <th>Elemento</th>
              <th>Categoría</th>
              <th>Cantidad</th>
              <th>Motivo / Lote</th>
              <th>Fecha</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows cols={6} />
            ) : paginados.length === 0 ? (
              <tr><td colSpan={6}>
                <div className="empty-state">
                  <div className="empty-state__icon"><CheckCircle2 size={36} strokeWidth={1} style={{color:"#bdbdbd"}}/></div>
                  <p className="empty-state__text">No hay registros de vencimiento</p>
                </div>
              </td></tr>
            ) : paginados.map((s, idx) => (
              <tr key={s.id || idx} className="tbl-row" style={{ opacity: s.anulada ? 0.5 : 1 }}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ display:"flex",alignItems:"center" }}>{s.entidadTipo === "producto" ? <Package size={15}/> : <Archive size={15}/>}</span>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13 }}>{s.entidadNombre}</div>
                      <div style={{ fontSize: 11, color: "#9e9e9e" }}>{s.entidadTipo}</div>
                    </div>
                  </div>
                </td>
                <td><span style={{ fontSize: 12, color: "#616161" }}>{s.entidadCat}</span></td>
                <td>
                  <span style={{ fontWeight: 700, color: "#c62828", fontSize: 14 }}>
                    -{s.cantidad} <span style={{ fontWeight: 400, fontSize: 11, color: "#9e9e9e" }}>uds.</span>
                  </span>
                </td>
                <td><span style={{ fontSize: 12, color: "#424242" }}>{s.motivo || "—"}</span></td>
                <td><span style={{ fontSize: 12, color: "#9e9e9e" }}>{s.fecha || "—"}</span></td>
                <td>
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                    background: s.anulada ? "#f5f5f5" : "#ffebee",
                    color: s.anulada ? "#9e9e9e" : "#c62828",
                    border: `1px solid ${s.anulada ? "#e0e0e0" : "#ef9a9a"}`,
                  }}>
                    {s.anulada ? <><Ban size={11}/> Anulada</> : <><AlertTriangle size={11}/> Vencido</>}
                  </span>
                </td>
              </tr>
            ))}
            {!loading && (
              <FilasRelleno current={paginados.length} perPage={ITEMS_PER_PAGE} colSpan={6} />
            )}
          </tbody>
        </table>
        </div>
      </div>

      <div className="pagination-bar">
        <span className="pagination-count">
          {filtrados.length} {filtrados.length === 1 ? "registro" : "registros"} en total
        </span>
        <div className="pagination-btns">
          <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
          <button className="pg-btn-arrow" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
          <span className="pg-pill">Página {safePage} de {Math.max(1, totalPages)}</span>
          <button className="pg-btn-arrow" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages}>›</button>
          <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage >= totalPages}>»</button>
        </div>
      </div>

      {toast && (
        <div className="sl-toast" style={{ background: toast.type === "error" ? "#c62828" : "#2e7d32" }}>
          {toast.type === "error" ? <XCircle size={14}/> : <CheckCircle2 size={14}/>} {toast.msg}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   REPORTE DE SALIDAS  (A_48_01 – CA_48_06)
══════════════════════════════════════════════════════════ */
function ReporteSalidas({ salidas, loading }) {
  const { hasPrivilegio, isAdmin } = usePrivilegios();
  const canReport = isAdmin || hasPrivilegio("GestionSalidas_ver");

  const [fechaInicio, setFechaInicio] = useState("");
  const [fechaFin,    setFechaFin]    = useState(hoyISO());
  const [generado,    setGenerado]    = useState(false);
  const [errFecha,    setErrFecha]    = useState("");

  const handleGenerar = () => {
    if (fechaInicio && fechaFin && fechaInicio > fechaFin) {
      setErrFecha("La fecha de inicio no puede ser posterior a la fecha fin.");
      return;
    }
    setErrFecha("");
    setGenerado(true);
  };

  // Salidas activas (no anuladas) dentro del rango seleccionado
  const filtradas = generado
    ? salidas.filter(s => {
        if (s.anulada) return false;
        const f = String(s.fecha || "").split("T")[0];
        if (fechaInicio && f < fechaInicio) return false;
        if (fechaFin    && f > fechaFin)    return false;
        return true;
      })
    : [];

  const totalUds = filtradas.reduce((a, s) => a + (s.cantidad || 0), 0);

  const statsPorTipo = TIPOS.map(t => ({
    ...t,
    count: filtradas.filter(s => s.tipo === t.val).length,
    uds:   filtradas.filter(s => s.tipo === t.val).reduce((a, s) => a + (s.cantidad || 0), 0),
  }));

  const topElementos = Object.values(
    filtradas.reduce((acc, s) => {
      const key = `${s.entidadTipo}-${s.entidadId}`;
      if (!acc[key]) acc[key] = { nombre: s.entidadNombre, tipo: s.entidadTipo, total: 0, count: 0 };
      acc[key].total += s.cantidad || 0;
      acc[key].count += 1;
      return acc;
    }, {})
  ).sort((a, b) => b.total - a.total).slice(0, 5);

  const exportExcel = () => {
    const aoa = [
      // ── Encabezado ──────────────────────────────────────────────
      ["TostonApp — Reporte de Salidas de Inventario"],
      [`Período: ${rangoLabel}`],
      [`Generado el: ${hoyISO()}`],
      [],
      // ── Resumen general ─────────────────────────────────────────
      ["RESUMEN GENERAL", "", ""],
      ["Total de salidas", filtradas.length, ""],
      ["Total de unidades retiradas", totalUds, ""],
      [],
      // ── Desglose por tipo ────────────────────────────────────────
      ["DESGLOSE POR TIPO", "Salidas", "Unidades"],
      ...statsPorTipo.map(t => [t.label, t.count, t.uds]),
      [],
      // ── Tabla de detalle ─────────────────────────────────────────
      ["DETALLE DE SALIDAS"],
      [
        "N°", "Elemento", "Tipo de elemento", "Categoría",
        "Tipo de salida", "Cantidad", "Unidad",
        "Motivo", "Registrado por", "Fecha",
      ],
      ...filtradas.map((s, i) => [
        i + 1,
        s.entidadNombre,
        s.entidadTipo === "producto" ? "Producto" : "Insumo",
        s.entidadCat  || "—",
        TIPO_MAP[s.tipo]?.label || s.tipo,
        s.cantidad,
        s.unidad      || "uds.",
        s.motivo      || "—",
        s.empleado    || "—",
        s.fecha       || "—",
      ]),
    ];

    const ws = XLSX.utils.aoa_to_sheet(aoa);

    ws["!cols"] = [
      { wch: 30 },  // N° / títulos de sección
      { wch: 28 },  // Elemento
      { wch: 16 },  // Tipo elemento
      { wch: 22 },  // Categoría
      { wch: 15 },  // Tipo salida
      { wch: 10 },  // Cantidad
      { wch: 10 },  // Unidad
      { wch: 35 },  // Motivo
      { wch: 22 },  // Registrado por
      { wch: 12 },  // Fecha
    ];

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Salidas");
    XLSX.writeFile(wb, `reporte-salidas${fechaInicio ? "-" + fechaInicio : ""}${fechaFin ? "-al-" + fechaFin : ""}.xlsx`);
  };

  if (!canReport) {
    return (
      <div className="sl-tab-content">
        <div className="empty-state" style={{ marginTop: 60 }}>
          <div className="empty-state__icon"><Lock size={36} strokeWidth={1} style={{color:"#bdbdbd"}}/></div>
          <p className="empty-state__text">No tienes permiso para generar reportes de salidas.</p>
        </div>
      </div>
    );
  }

  const rangoLabel = fechaInicio && fechaFin
    ? `${fechaInicio} al ${fechaFin}`
    : fechaInicio ? `Desde ${fechaInicio}`
    : fechaFin    ? `Hasta ${fechaFin}`
    : "Todo el historial";

  return (
    <div className="sl-tab-content sl-report">

      {/* ─── Filtro de fechas ─── */}
      <div className="sl-report-filter card no-print">
        <h3 className="sl-report-filter__title" style={{display:"flex",alignItems:"center",gap:8}}><Calendar size={16}/> Selecciona el rango de fechas</h3>
        <div className="sl-report-dates">
          <div className="sl-report-date-field">
            <label>Desde</label>
            <input
              type="date"
              value={fechaInicio}
              max={fechaFin || hoyISO()}
              onChange={e => { setFechaInicio(e.target.value); setGenerado(false); }} />
          </div>
          <div className="sl-report-date-field">
            <label>Hasta</label>
            <input
              type="date"
              value={fechaFin}
              max={hoyISO()}
              onChange={e => { setFechaFin(e.target.value); setGenerado(false); }} />
          </div>
          <button
            className="btn-agregar"
            style={{ alignSelf: "flex-end" }}
            onClick={handleGenerar}
            disabled={loading}>
            {loading ? "Cargando…" : <><BarChart2 size={14}/> Generar reporte</>}
          </button>
        </div>
        {errFecha && <p className="field-error" style={{ marginTop: 6 }}>{errFecha}</p>}
      </div>

      {/* ─── Contenido generado ─── */}
      {generado && (
        <div className="sl-report-body">
          {/* Encabezado para impresión */}
          <div className="sl-print-header print-only">
            <div className="sl-print-header__logo">TostonApp</div>
            <h2 className="sl-print-header__title">Reporte de Salidas de Inventario</h2>
            <p className="sl-print-header__periodo">Período: {rangoLabel}</p>
            <p className="sl-print-header__gen">Generado el {hoyISO()}</p>
          </div>

          {filtradas.length === 0 ? (
            /* CA_48_05 – estado vacío */
            <div className="empty-state" style={{ marginTop: 40 }}>
              <div className="empty-state__icon"><ClipboardList size={36} strokeWidth={1} style={{color:"#bdbdbd"}}/></div>
              <p className="empty-state__text">No hay salidas en el periodo seleccionado.</p>
              <p style={{ fontSize: 13, color: "#9e9e9e", marginTop: 4 }}>
                Intenta con un rango de fechas diferente.
              </p>
            </div>
          ) : (
            <>
              {/* CA_48_04 – botones de exportación */}
              <div className="sl-report-actions no-print">
                <button className="sl-report-btn sl-report-btn--csv" onClick={exportExcel} style={{display:"flex",alignItems:"center",gap:6}}>
                  <BarChart2 size={14}/> Exportar Excel (.xlsx)
                </button>
                <button className="sl-report-btn sl-report-btn--pdf" onClick={() => window.print()} style={{display:"flex",alignItems:"center",gap:6}}>
                  <Printer size={14}/> Exportar PDF
                </button>
              </div>

              {/* CA_48_03 – resumen del período */}
              <div className="sl-report-section">
                <h3 className="sl-report-section-title">Resumen del período · {rangoLabel}</h3>
                <div className="sl-report-summary-grid">
                  <div className="sl-report-sum-card sl-report-sum-card--total">
                    <span className="sl-report-sum-card__num">{filtradas.length}</span>
                    <span className="sl-report-sum-card__label">Total salidas</span>
                  </div>
                  <div className="sl-report-sum-card sl-report-sum-card--total">
                    <span className="sl-report-sum-card__num">{totalUds}</span>
                    <span className="sl-report-sum-card__label">Unidades retiradas</span>
                  </div>
                  {statsPorTipo.filter(t => t.count > 0).map(t => (
                    <div key={t.val} className="sl-report-sum-card"
                      style={{ borderColor: t.border, background: t.bg }}>
                      <t.Icon size={20}/>
                      <span className="sl-report-sum-card__num" style={{ color: t.color }}>{t.count}</span>
                      <span className="sl-report-sum-card__label">{t.label}</span>
                      <span className="sl-report-sum-card__sub">{t.uds} uds.</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* CA_48_03 – top elementos */}
              {topElementos.length > 0 && (
                <div className="sl-report-section">
                  <h3 className="sl-report-section-title">Elementos con mayor movimiento</h3>
                  <div className="sl-report-top-list">
                    {topElementos.map((el, i) => (
                      <div key={i} className="sl-report-top-item">
                        <span className="sl-report-top-rank">#{i + 1}</span>
                        <span style={{ display:"flex",alignItems:"center" }}>{el.tipo === "producto" ? <Package size={18}/> : <Archive size={18}/>}</span>
                        <div className="sl-report-top-info">
                          <div className="sl-report-top-name">{el.nombre}</div>
                          <div className="sl-report-top-meta">{el.count} salida{el.count !== 1 ? "s" : ""} · {el.total} uds.</div>
                        </div>
                        <div className="sl-report-top-bar-wrap">
                          <div
                            className="sl-report-top-bar"
                            style={{ width: `${Math.round((el.total / topElementos[0].total) * 100)}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* CA_48_02 – tabla de detalle */}
              <div className="sl-report-section">
                <h3 className="sl-report-section-title">Detalle de salidas</h3>
                <div className="card">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Elemento</th>
                        <th>Tipo</th>
                        <th>Cantidad</th>
                        <th>Motivo</th>
                        <th>Fecha</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtradas.map((s, idx) => {
                        const tc = TIPO_MAP[s.tipo] || { color: "#757575", bg: "#f5f5f5", border: "#e0e0e0", Icon: ClipboardList, label: s.tipo };
                        return (
                          <tr key={s.id || idx} className="tbl-row">
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ display:"flex",alignItems:"center" }}>{s.entidadTipo === "producto" ? <Package size={15}/> : <Archive size={15}/>}</span>
                                <div>
                                  <div style={{ fontWeight: 700, fontSize: 13 }}>{s.entidadNombre}</div>
                                  <div style={{ fontSize: 11, color: "#9e9e9e" }}>{s.entidadCat}</div>
                                </div>
                              </div>
                            </td>
                            <td>
                              <span className="sl-tipo-badge"
                                style={{ color: tc.color, background: tc.bg, border: `1px solid ${tc.border}`, display:"flex",alignItems:"center",gap:4 }}>
                                <tc.Icon size={12}/> {tc.label}
                              </span>
                            </td>
                            <td>
                              <span style={{ fontWeight: 700, color: "#c62828", fontSize: 14 }}>
                                -{s.cantidad} <span style={{ fontWeight: 400, fontSize: 11, color: "#9e9e9e" }}>{s.unidad || "uds."}</span>
                              </span>
                            </td>
                            <td><span style={{ fontSize: 13, color: "#424242" }}>{s.motivo || "—"}</span></td>
                            <td><span style={{ fontSize: 12, color: "#9e9e9e" }}>{s.fecha || "—"}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   PÁGINA PRINCIPAL
══════════════════════════════════════════════════════════ */
export default function GestionSalidas() {
  const [tab,       setTab]       = useState("historial");
  const [showModal, setShowModal] = useState(false);
  const [salidas,   setSalidas]   = useState([]);
  const [productos, setProductos] = useState([]);
  const [insumos,   setInsumos]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [pageToast, setPageToast] = useState(null);

  const showPageToast = (msg, type = "success") => {
    setPageToast({ msg, type });
    setTimeout(() => setPageToast(null), 3000);
  };

  // Mapas id → nombre de categoría, construidos una vez al cargar
  const prodCatMap = useRef({});
  const insCatMap  = useRef({});

  const enriquecerSalidas = (rawSalidas) =>
    rawSalidas.map(s => {
      const adapted = adaptarSalida(s);
      if (adapted.entidadTipo === "producto" && adapted.entidadId) {
        adapted.entidadCat = prodCatMap.current[adapted.entidadId] || adapted.entidadCat;
      } else if (adapted.entidadTipo === "insumo" && adapted.entidadId) {
        adapted.entidadCat = insCatMap.current[adapted.entidadId] || adapted.entidadCat;
      }
      return adapted;
    });

  const cargarSalidas = async () => {
    setLoading(true);
    try {
      const [data, pData, iData] = await Promise.all([
        getSalidas(),
        getProductos().catch(() => null),
        getInsumos().catch(() => null),
      ]);
      if (pData) {
        const prodList = (pData.productos || []).filter(p => p.Estado !== 0).map(p => ({
          id: p.ID_Producto, nombre: p.nombre || p.Nombre || "",
          _tipo: "producto", _stock: p.Stock_Actual ?? p.Stock ?? 0,
          _label: p.nombre_categoria || "", _unidad: "uds.",
        }));
        prodCatMap.current = Object.fromEntries(prodList.map(p => [p.id, p._label]));
        setProductos(prodList);
      }
      if (iData) {
        const insList = (iData.insumos || []).filter(i => i.Estado !== 0).map(i => ({
          id: i.ID_Insumo, nombre: i.Nombre, _tipo: "insumo",
          _stock: i.Stock_Actual ?? 0, _label: i.nombre_categoria || "",
          _unidad: i.simbolo_unidad || "uds.", stockMinimo: i.Stock_Minimo,
        }));
        insCatMap.current = Object.fromEntries(insList.map(i => [i.id, i._label]));
        setInsumos(insList);
      }
      setSalidas(enriquecerSalidas([...(data.salidas || [])].sort((a, b) => b.ID_Salida - a.ID_Salida)));
    } catch {
      showPageToast("Error al cargar salidas. Verifica la conexión.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const [sData, pData, iData] = await Promise.all([
          getSalidas(),
          getProductos().catch(() => ({ productos: [] })),
          getInsumos().catch(() => ({ insumos: [] })),
        ]);

        const prodList = (pData.productos || []).filter(p => p.Estado !== 0).map(p => ({
          id:          p.ID_Producto,
          nombre:      p.nombre || p.Nombre || "",
          _tipo:       "producto",
          _stock:      p.Stock_Actual ?? p.Stock ?? 0,
          _label:      p.nombre_categoria || "",
          _unidad:     "uds.",
        }));
        const insList = (iData.insumos || []).filter(i => i.Estado !== 0).map(i => ({
          id:          i.ID_Insumo,
          nombre:      i.Nombre,
          _tipo:       "insumo",
          _stock:      i.Stock_Actual ?? 0,
          _label:      i.nombre_categoria || "",
          _unidad:     i.simbolo_unidad || "uds.",
          stockMinimo: i.Stock_Minimo,
        }));

        // Construir mapas id → categoría para enriquecer el historial
        prodCatMap.current = Object.fromEntries(prodList.map(p => [p.id, p._label]));
        insCatMap.current  = Object.fromEntries(insList.map(i => [i.id, i._label]));

        setProductos(prodList);
        setInsumos(insList);
        setSalidas(enriquecerSalidas([...(sData.salidas || [])].sort((a, b) => b.ID_Salida - a.ID_Salida)));
      } catch {
        showPageToast("Error al cargar datos. Verifica la conexión.", "error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const TABS = [
    { key: "historial", label: "Historial",  Icon: ClipboardList },
    { key: "vencidos",  label: "Vencidos",   Icon: AlertTriangle },
    { key: "reporte",   label: "Reporte",    Icon: BarChart2 },
  ];

  return (
    <div className="sl-page">
      <div className="sl-page__header">
        <h1 className="sl-page__title">Gestión de Salidas</h1>
        <div className="sl-page__line" />
      </div>

      <div className="sl-page__tabs">
        {TABS.map(t => (
          <button key={t.key}
            className={`sl-tab${tab === t.key ? " active" : ""}`}
            onClick={() => setTab(t.key)} style={{display:"flex",alignItems:"center",gap:6}}>
            <t.Icon size={14}/> {t.label}
          </button>
        ))}
      </div>

      <div className="sl-page__body">
        {tab === "historial" && (
          <HistorialSalidas
            salidas={salidas}
            loading={loading}
            onAgregarClick={() => setShowModal(true)}
            cargarSalidas={cargarSalidas}
          />
        )}
        {tab === "vencidos" && (
          <Vencidos salidas={salidas} loading={loading} cargarSalidas={cargarSalidas} />
        )}
        {tab === "reporte" && (
          <ReporteSalidas salidas={salidas} loading={loading} />
        )}
      </div>

      {showModal && (
        <RegistrarSalida
          productos={productos}
          insumos={insumos}
          onClose={() => setShowModal(false)}
          onRegistrada={(msg) => { setShowModal(false); cargarSalidas(); if (msg) showPageToast(msg); }}
        />
      )}

      {pageToast && (
        <div className="sl-toast" style={{ background: pageToast.type === "error" ? "#c62828" : "#2e7d32" }}>
          {pageToast.type === "error" ? <XCircle size={14}/> : <CheckCircle2 size={14}/>} {pageToast.msg}
        </div>
      )}
    </div>
  );
}
