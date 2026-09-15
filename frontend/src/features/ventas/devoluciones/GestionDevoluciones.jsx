import { useState, useEffect, useRef } from "react";
import CrearDevolucion from "./CrearDevolucion.jsx";
import { getDevoluciones, crearDevolucion, resolverDevolucion, getCreditoCliente } from "../../../services/devolucionesService.js";
import { registrarSalida } from "../../../services/salidasService.js";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { X, Check, AlertTriangle, BarChart2, Clock, CreditCard, Ban, Search, CornerUpLeft, Package, Eye, CheckCircle2, Image, Video, FileText, Paperclip, ClipboardList, RefreshCw } from "lucide-react";
import "./Devoluciones.css";
import { formatCOP } from "../../../utils/formato";

function SkeletonRows({ cols = 8, rows = 5 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i}>
      {Array.from({ length: cols }).map((__, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

const fmt = formatCOP;

const PER_PAGE  = 10;
const ESTADO_IDS = { Pendiente: 3, Reembolsada: 6, Rechazada: 7 };

function EstadoBadge({ estado }) {
  return (
    <span className={`estado-badge estado--${estado}`}>
      <span className="estado-badge__dot" />
      {estado}
    </span>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  const bg = toast.type === "error" ? "#c62828" : toast.type === "warn" ? "#e65100" : "#2e7d32";
  return (
    <div className="toast" style={{ background: bg }}>
      <span style={{ fontSize: 15, display: "flex" }}>{toast.type === "error" ? <X size={15} /> : toast.type === "warn" ? <AlertTriangle size={15} /> : <Check size={15} />}</span>
      {toast.message}
    </div>
  );
}


/* ─── Evidencia inline en modal detalle ─────────────────── */
function EvidenciaVer({ evidencia }) {
  if (!evidencia) return null;
  const isImage = evidencia.tipo?.startsWith("image/");
  const isVideo = evidencia.tipo?.startsWith("video/");

  return (
    <div className="evidencia-ver">
      {isImage ? (
        <>
          <img src={evidencia.url} alt="evidencia" className="evidencia-ver__img" />
          <div className="evidencia-ver__footer">
            <Image size={14} className="evidencia-ver__icon" />
            <span className="evidencia-ver__name">{evidencia.nombre}</span>
          </div>
        </>
      ) : isVideo ? (
        <>
          <video
            src={evidencia.url}
            controls
            style={{ width: "100%", maxHeight: 200, display: "block", background: "#000" }}
          />
          <div className="evidencia-ver__footer">
            <Video size={14} className="evidencia-ver__icon" />
            <span className="evidencia-ver__name">{evidencia.nombre}</span>
          </div>
        </>
      ) : (
        <div className="evidencia-ver__file">
          <FileText size={24} className="evidencia-ver__file-icon" />
          <div className="evidencia-ver__file-info">
            <div className="evidencia-ver__file-name">{evidencia.nombre}</div>
            <div className="evidencia-ver__file-sub">Archivo adjunto</div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL VER DETALLE
   ═══════════════════════════════════════════════════════════ */
function ModalVerDevolucion({ dev, creditoCliente, onClose }) {
  const [tab, setTab] = useState("informacion");

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--wide" onClick={(e) => e.stopPropagation()}>

        <div className="modal-header modal-header--red">
          <div>
            <p className="modal-header__eyebrow">DEVOLUCIÓN</p>
            <h2 className="modal-header__title modal-header__title--red">{dev.numero}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <EstadoBadge estado={dev.estado} />
            <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        <div style={{ padding: "16px 24px 0", borderBottom: "1px solid #e0e0e0" }}>
          <div className="modal-tabs">
            <button
              className={`modal-tab-btn ${tab === "informacion" ? "active" : ""}`}
              onClick={() => setTab("informacion")}
            >Información</button>
            <button
              className={`modal-tab-btn ${tab === "productos" ? "active" : ""}`}
              onClick={() => setTab("productos")}
            >Productos y evidencia</button>
          </div>
        </div>

        <div className="modal-body" style={{ flexShrink: 0 }}>

          {tab === "informacion" && (
            <>
              <p className="section-label">Información general</p>
              <div className="form-grid-2">
                <div>
                  <label className="form-label">Cliente</label>
                  <div className="field-input--disabled">{dev.cliente?.nombre || "—"}</div>
                </div>
                <div>
                  <label className="form-label">Pedido original</label>
                  <div className="field-input--disabled" style={{ color: "#2e7d32", fontWeight: 700 }}>
                    {dev.numeroPedido}
                  </div>
                </div>
                <div>
                  <label className="form-label">Fecha solicitud</label>
                  <div className="field-input--disabled">{dev.fechaSolicitud}</div>
                </div>
                <div>
                  <label className="form-label">Fecha aprobación</label>
                  <div className="field-input--disabled">{dev.fechaAprobacion || "—"}</div>
                </div>
              </div>

              <p className="section-label">Motivo</p>
              <div className="info-box info-box--warn">
                <ClipboardList size={13} className="info-box__icon" />
                <div className="info-box__text">
                  <span className="info-box__label">{dev.motivo}</span>
                  {dev.comentario && dev.comentario}
                </div>
              </div>

              {dev.estado === "Reembolsada" && (
                <div className="credito-box" style={{ marginTop: 12 }}>
                  <CreditCard size={16} className="credito-box__icon" />
                  <div>
                    <div className="credito-box__label">Saldo a favor abonado</div>
                    <div className="credito-box__val">{fmt(dev.totalDevuelto)}</div>
                    <div className="credito-box__saldo">
                      Saldo actual del cliente: {fmt(creditoCliente || 0)}
                    </div>
                  </div>
                </div>
              )}

              {dev.estado === "Rechazada" && dev.motivoRechazo && (
                <div className="info-box info-box--danger" style={{ marginTop: 12 }}>
                  <Ban size={13} className="info-box__icon" />
                  <div className="info-box__text">
                    <span className="info-box__label">Motivo de rechazo</span>
                    {dev.motivoRechazo}
                  </div>
                </div>
              )}
            </>
          )}

          {tab === "productos" && (
            <>
              <p className="section-label">Productos devueltos</p>
              <div style={{ borderRadius: 10, border: "1px solid #e8f5e9", overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "#f1f8f1" }}>
                      <th style={{ padding: "8px 12px", fontSize: 11, fontWeight: 700, color: "#2e7d32", textAlign: "left" }}>Producto</th>
                      <th style={{ padding: "8px 12px", fontSize: 11, fontWeight: 700, color: "#2e7d32", textAlign: "center" }}>Cant.</th>
                      <th style={{ padding: "8px 12px", fontSize: 11, fontWeight: 700, color: "#2e7d32", textAlign: "right" }}>Precio unit.</th>
                      <th style={{ padding: "8px 12px", fontSize: 11, fontWeight: 700, color: "#2e7d32", textAlign: "right" }}>Subtotal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(dev.productos || []).map((p, i) => (
                      <tr key={i} style={{ borderTop: "1px solid #f1f8f1" }}>
                        <td style={{ padding: "9px 12px", fontWeight: 600 }}>{p.nombre}</td>
                        <td style={{ padding: "9px 12px", textAlign: "center", fontWeight: 700, color: "#1565c0" }}>{p.cantidad}</td>
                        <td style={{ padding: "9px 12px", textAlign: "right", fontSize: 12, color: "#757575" }}>{fmt(p.precioUnitario)}</td>
                        <td style={{ padding: "9px 12px", textAlign: "right", fontWeight: 700, color: "#c62828" }}>{fmt(p.subtotal)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "#f9fdf9", borderTop: "1.5px solid #c8e6c9" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: "0.5px" }}>Total a devolver</span>
                  <span style={{ fontSize: 16, fontWeight: 800, color: "#c62828" }}>{fmt(dev.totalDevuelto)}</span>
                </div>
              </div>

              {dev.evidencia && (
                <>
                  <p className="section-label" style={{ marginTop: 16 }}>Evidencia</p>
                  <EvidenciaVer evidencia={dev.evidencia} />
                </>
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

/* ═══════════════════════════════════════════════════════════
   MODAL APROBAR
   ═══════════════════════════════════════════════════════════ */
function ModalAprobar({ dev, onClose, onConfirm }) {
  const [done, setDone] = useState(false);
  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--md" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">APROBAR</p>
            <h2 className="modal-header__title">Aprobar devolución</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, fontSize: 13, color: "#616161" }}>
            ¿Aprobar la devolución <strong>{dev.numero}</strong> de <strong>{dev.cliente?.nombre}</strong>?
          </p>
          <div className="info-box info-box--success" style={{ marginTop: 12 }}>
            <CheckCircle2 size={13} className="info-box__icon" />
            <div className="info-box__text">
              <span className="info-box__label">Al aprobar</span>
              La devolución se marcará como aprobada y se realizará el reembolso automático al crédito del cliente.
            </div>
          </div>
          <div className="credito-box" style={{ marginTop: 12 }}>
            <CreditCard size={16} className="credito-box__icon" />
            <div>
              <div className="credito-box__label">Monto a reembolsar</div>
              <div className="credito-box__val">{fmt(dev.totalDevuelto)}</div>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button
            className="btn-approve"
            disabled={done}
            onClick={() => { setDone(true); setTimeout(() => onConfirm(dev.id, dev.productos || []), 700); }}
          >
            {done ? "Aprobando…" : <><CheckCircle2 size={14} /> Aprobar y Reembolsar</>}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL RECHAZAR
   ═══════════════════════════════════════════════════════════ */
function ModalRechazar({ dev, onClose, onConfirm }) {
  const [motivo, setMotivo] = useState("");
  const [error,  setError]  = useState("");
  const [done,   setDone]   = useState(false);

  const handleConfirm = () => {
    if (!motivo.trim()) { setError("Ingresa el motivo del rechazo"); return; }
    setDone(true);
    setTimeout(() => onConfirm(dev.id, motivo), 700);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--md" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header modal-header--red">
          <div>
            <p className="modal-header__eyebrow">RECHAZAR</p>
            <h2 className="modal-header__title modal-header__title--red">Rechazar devolución</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, fontSize: 13, color: "#616161" }}>
            ¿Rechazar la devolución <strong>{dev.numero}</strong>?
          </p>
          <div className="info-box info-box--danger" style={{ marginTop: 12 }}>
            <AlertTriangle size={13} className="info-box__icon" />
            <span className="info-box__text">El cliente recibirá una notificación en la aplicación informando el rechazo.</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12 }}>
            <label className="form-label">Motivo del rechazo <span className="required">*</span></label>
            <textarea
              className={`field-textarea${error ? " error" : ""}`}
              rows={3}
              placeholder="Explica por qué se rechaza la devolución…"
              value={motivo}
              onChange={(e) => { setMotivo(e.target.value); setError(""); }}
              style={{ borderColor: error ? "#e53935" : undefined }}
            />
            {error && <span className="field-error">{error}</span>}
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button className="btn-reject" disabled={done} onClick={handleConfirm}>
            {done ? "Rechazando…" : <><Ban size={14} /> Rechazar</>}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENTE PRINCIPAL
   ═══════════════════════════════════════════════════════════ */
export default function GestionDevoluciones() {
  const [devoluciones,     setDevoluciones]     = useState([]);
  const [total,            setTotal]            = useState(0);
  const [totalesPorEstado, setTotalesPorEstado] = useState({});
  const [loading,          setLoading]          = useState(true);
  const [actionSaving,     setActionSaving]     = useState(false);
  const [search,           setSearch]           = useState("");
  const [searchQuery,      setSearchQuery]      = useState("");
  const [filterEstado,     setFilterEstado]     = useState("todos");
  const [filterDesde,      setFilterDesde]      = useState("");
  const [filterHasta,      setFilterHasta]      = useState("");
  const [showFilter,       setShowFilter]       = useState(false);
  const [page,             setPage]             = useState(1);
  const [reloadTrigger,    setReloadTrigger]    = useState(0);
  const [modal,            setModal]            = useState(null);
  const [creditoVer,       setCreditoVer]       = useState(0);
  const [toast,            setToast]            = useState(null);
  const filterRef = useRef();

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3200);
  };

  const recargar = () => setReloadTrigger((n) => n + 1);

  useEffect(() => {
    const t = setTimeout(() => { setSearchQuery(search); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const estadoId = ESTADO_IDS[filterEstado] ?? null;
    getDevoluciones({ pagina: page, porPagina: PER_PAGE, busqueda: searchQuery, estadoId, fechaDesde: filterDesde, fechaHasta: filterHasta })
      .then(data => {
        if (!active) return;
        setDevoluciones(data.devoluciones || []);
        setTotal(data.total || 0);
        setTotalesPorEstado(data.totalesPorEstado || {});
      })
      .catch(err => { if (active) showToast(err.message || "Error al cargar devoluciones", "error"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, searchQuery, filterEstado, filterDesde, filterHasta, reloadTrigger]); // eslint-disable-line

  useEffect(() => {
    const h = (e) => { if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
  const safePage   = Math.min(page, totalPages);

  const hasFilter = filterEstado !== "todos" || filterDesde || filterHasta;

  const handleCrear = async (payload) => {
    setActionSaving(true);
    try {
      const dev = await crearDevolucion(payload);
      setPage(1);
      recargar();
      showToast(`Devolución ${dev.numero} registrada`);
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al registrar devolución", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleAprobar = async (id, productosModal = []) => {
    setActionSaving(true);
    try {
      const dev = await resolverDevolucion(id, "aprobar");

      // Registrar salidas de forma no bloqueante: si falla no interrumpe la aprobación
      const prods = productosModal.length > 0 ? productosModal : (dev.productos || []);
      let salidasOk = true;
      for (const prod of prods) {
        try {
          await registrarSalida({
            tipo:       "devolución",
            idProducto: prod.idProducto,
            cantidad:   prod.cantidad,
            motivo:     `Devolución aprobada ${dev.numero} — pedido ${dev.numeroPedido}`,
          });
        } catch (_) {
          salidasOk = false;
        }
      }

      window.dispatchEvent(new Event('credito-updated'));
      recargar();
      if (salidasOk) {
        showToast("Devolución aprobada y reembolso procesado");
      } else {
        showToast("Devolución aprobada, pero hubo un error al registrar la salida de inventario", "warn");
      }
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al aprobar devolución", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleRechazar = async (id, motivo) => {
    setActionSaving(true);
    try {
      const dev = await resolverDevolucion(id, "rechazar", motivo);
      recargar();
      showToast("Devolución rechazada", "warn");
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al rechazar devolución", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const counts = {
    todos:       totalesPorEstado.todos       ?? 0,
    Pendiente:   totalesPorEstado.Pendiente   ?? 0,
    Reembolsada: totalesPorEstado.Reembolsada ?? 0,
    Rechazada:   totalesPorEstado.Rechazada   ?? 0,
  };

  const toggleFilter = (est) => {
    setFilterEstado((prev) => (prev === est ? "todos" : est));
    setPage(1);
  };

  const abrirAprobar = (dev) => {
    if (dev.estado !== "Pendiente") { showToast("Solo se pueden aprobar devoluciones pendientes", "warn"); return; }
    setModal({ type: "aprobar", dev });
  };

  const abrirRechazar = (dev) => {
    if (dev.estado !== "Pendiente") { showToast("Solo se pueden rechazar devoluciones pendientes", "warn"); return; }
    setModal({ type: "rechazar", dev });
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Devoluciones</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">

        {/* Métricas */}
        <div className="metrics-row">
          {[
            { val: "todos",       label: "Total",        count: counts.todos,       color: "#2e7d32", Icon: BarChart2 },
            { val: "Pendiente",   label: "Pendientes",   count: counts.Pendiente,   color: "#f9a825", Icon: Clock },
            { val: "Reembolsada", label: "Reembolsadas", count: counts.Reembolsada, color: "#2e7d32", Icon: CreditCard },
            { val: "Rechazada",   label: "Rechazadas",   count: counts.Rechazada,   color: "#c62828", Icon: Ban },
          ].map((m) => (
            <button
              key={m.val}
              className={`metric-card-btn ${filterEstado === m.val ? "active" : ""}`}
              onClick={() => toggleFilter(m.val)}
              style={{ borderColor: filterEstado === m.val ? m.color : "#e0e0e0" }}
            >
              <div className="metric-card-btn__icon" style={{ background: m.color + "15", color: m.color }}><m.Icon size={16} /></div>
              <div className="metric-card-btn__info">
                <span className="metric-card-btn__count">{m.count}</span>
                <span className="metric-card-btn__label">{m.label}</span>
              </div>
            </button>
          ))}
        </div>

        {/* Toolbar */}
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={16} className="search-icon" />
            <input
              type="text" className="search-input"
              placeholder="Buscar por número, cliente, pedido o motivo…"
              value={search} onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <button className="filter-icon-btn" onClick={recargar} data-tooltip="Actualizar devoluciones">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className={`filter-icon-btn${hasFilter ? " has-filter" : ""}`}
              onClick={() => setShowFilter((v) => !v)}
              data-tooltip="Filtrar devoluciones"
            >▼</button>
            {showFilter && (
              <div className="filter-dropdown" style={{ minWidth: 175 }}>
                <p className="filter-section-title">Estado</p>
                {[
                  { val: "todos",       label: "Todos",       dot: "#bdbdbd" },
                  { val: "Pendiente",   label: "Pendiente",   dot: "#f9a825" },
                  { val: "Reembolsada", label: "Reembolsada", dot: "#43a047" },
                  { val: "Rechazada",   label: "Rechazada",   dot: "#e53935" },
                ].map((f) => (
                  <button
                    key={f.val}
                    className={`filter-option${filterEstado === f.val ? " active" : ""}`}
                    onClick={() => { setFilterEstado(f.val); setPage(1); setShowFilter(false); }}
                  >
                    <span className="filter-dot" style={{ background: f.dot }} />{f.label}
                  </button>
                ))}
                <div style={{ height: 1, background: "#f0f0f0", margin: "8px 0" }} />
                <DateRangeFilter
                  desde={filterDesde}
                  hasta={filterHasta}
                  label="Fecha de solicitud"
                  onApply={({ desde, hasta }) => {
                    setFilterDesde(desde || "");
                    setFilterHasta(hasta || "");
                    setPage(1);
                  }}
                  onClear={() => {
                    setFilterDesde("");
                    setFilterHasta("");
                  }}
                />
              </div>
            )}
          </div>

          {(hasFilter || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setSearchQuery(""); setFilterEstado("todos"); setFilterDesde(""); setFilterHasta(""); setPage(1); }}>
              <X size={13} /> Limpiar
            </button>
          )}

          <button className="btn-agregar" onClick={() => setModal({ type: "crear" })} data-tooltip="Registrar nueva devolución">
            Nueva devolución <span style={{ fontSize: 18 }}>+</span>
          </button>
        </div>

        {/* Tabla */}
        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "74px", "--tbl-rows": 10 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>Nº</th>
                  <th>Devolución</th>
                  <th>Cliente</th>
                  <th>Motivo</th>
                  <th>Fecha</th>
                  <th>Total</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <SkeletonRows cols={8} rows={5} />
                ) : devoluciones.length === 0 ? (
                  <tr><td colSpan={8}>
                    <div className="empty-state">
                      <div className="empty-state__icon"><CornerUpLeft size={40} /></div>
                      <p className="empty-state__text">
                        {hasFilter || search ? "Sin devoluciones que coincidan." : "No hay devoluciones registradas."}
                      </p>
                    </div>
                  </td></tr>
                ) : devoluciones.map((dev, idx) => (
                  <tr key={dev.id} className="tbl-row">
                    <td>
                      <span className="row-num">
                        {String((safePage - 1) * PER_PAGE + idx + 1).padStart(2, "0")}
                      </span>
                    </td>
                    <td>
                      <div className="dev-num">{dev.numero}</div>
                      <div className="dev-pedido" style={{ display:"flex",alignItems:"center",gap:4 }}><Package size={11} /> {dev.numeroPedido}</div>
                    </td>
                    <td>
                      <div className="client-name">{dev.cliente?.nombre || "—"}</div>
                      <div className="client-email">{dev.cliente?.correo || ""}</div>
                    </td>
                    <td>
                      <div style={{ fontSize: 13, color: "#424242", fontWeight: 500 }}>{dev.motivo}</div>
                      {dev.comentario && (
                        <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2, maxWidth: 180, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {dev.comentario}
                        </div>
                      )}
                    </td>
                    <td><span className="date-badge">{dev.fechaSolicitud}</span></td>
                    <td>
                      <div className="monto-val">{fmt(dev.totalDevuelto)}</div>
                      <div className="monto-met">Crédito</div>
                    </td>
                    <td><EstadoBadge estado={dev.estado} /></td>
                    <td>
                      <div className="actions-cell">
                        <button className="act-btn act-btn--view" data-tooltip="Ver detalle de devolución"
                          onClick={() => {
                            setCreditoVer(0);
                            setModal({ type: "ver", dev });
                            if (dev.idCliente) {
                              getCreditoCliente(dev.idCliente)
                                .then(s => setCreditoVer(s))
                                .catch(() => {});
                            }
                          }}><Eye size={14} /></button>
                        <button className="act-btn act-btn--approve" data-tooltip="Aprobar y reembolsar"
                          onClick={() => abrirAprobar(dev)}
                          style={{ opacity: dev.estado === "Pendiente" ? 1 : 0.35, cursor: dev.estado === "Pendiente" ? "pointer" : "default" }}>
                          <CheckCircle2 size={14} />
                        </button>
                        <button className="act-btn act-btn--reject" data-tooltip="Rechazar solicitud"
                          onClick={() => abrirRechazar(dev)}
                          style={{ opacity: dev.estado === "Pendiente" ? 1 : 0.35, cursor: dev.estado === "Pendiente" ? "pointer" : "default" }}>
                          <Ban size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && (
                  <FilasRelleno current={devoluciones.length} perPage={PER_PAGE} colSpan={8} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <span className="pagination-count">
              {total} {total === 1 ? "devolución" : "devoluciones"} en total
            </span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
              <button className="pg-btn-arrow"
                onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>››</button>
            </div>
          </div>
        </div>
      </div>

      {modal?.type === "crear"    && <CrearDevolucion onClose={() => setModal(null)} onSave={handleCrear} saving={actionSaving} devoluciones={devoluciones} />}
      {modal?.type === "ver"      && <ModalVerDevolucion dev={modal.dev} creditoCliente={creditoVer} onClose={() => setModal(null)} />}
      {modal?.type === "aprobar"  && <ModalAprobar  dev={modal.dev} onClose={() => setModal(null)} onConfirm={handleAprobar} />}
      {modal?.type === "rechazar" && <ModalRechazar dev={modal.dev} onClose={() => setModal(null)} onConfirm={handleRechazar} />}

      <Toast toast={toast} />
    </div>
  );
}