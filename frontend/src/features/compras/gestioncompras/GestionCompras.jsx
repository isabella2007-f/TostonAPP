import { useState, useRef, useEffect } from "react";
import { Search, X, Check, CheckCircle2, Ban, Building2, CreditCard, FileText, Banknote, Eye, PenLine, ShoppingCart, Clock, RefreshCw } from "lucide-react";
import { getCompras, crearCompra as apiCrearCompra, editarCompra, completarCompra, anularCompra } from "../../../services/comprasService.js";
import { getProveedores } from "../../../services/proveedoresService.js";
import CrearCompra from "./CrearCompra.jsx";
import EditarCompra, { AnularCompraModal } from "./EditarCompra.jsx";
import { fmtFecha } from "../../../utils/dateUtils";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { usePrivilegio } from "../../../context/PrivilegiosContext";
import "./compras.css";
import { formatCOP } from "../../../utils/formato";

const ITEMS_PER_PAGE = 5;

const COP = formatCOP;

const METODOS_LABEL = {
  efectivo:      { label: "Efectivo",      Icon: Banknote,    bg: "#e8f5e9", color: "#2e7d32", border: "#c8e6c9" },
  transferencia: { label: "Transferencia", Icon: Building2,   bg: "#e3f2fd", color: "#1565c0", border: "#90caf9" },
  crédito:       { label: "Crédito",       Icon: CreditCard,  bg: "#f3e5f5", color: "#6a1b9a", border: "#ce93d8" },
  cheque:        { label: "Cheque",        Icon: FileText,    bg: "#fff8e1", color: "#f57f17", border: "#ffe082" },
};

/* ── Celda "Fechas" (completación / anulación) ─────────────── */
function FechaBadge({ tipo, fecha }) {
  const esComp = tipo === "completada";
  return (
    <span className={`fecha-badge fecha-badge--${esComp ? "completada" : "anulada"}`}>
      <span className="fecha-badge__label">{esComp ? "Completada" : "Anulada"}</span>
      <span className="fecha-badge__date">
        {esComp ? <CheckCircle2 size={11} /> : <Ban size={11} />} {fmtFecha(fecha)}
      </span>
    </span>
  );
}

function FechasCell({ compra }) {
  if (compra.estado === "anulada") {
    // Completada y luego anulada → ambas apiladas (completación arriba, anulación abajo)
    return (
      <div className="fechas-cell">
        {compra.fecha_llegada && <FechaBadge tipo="completada" fecha={compra.fecha_llegada} />}
        <FechaBadge tipo="anulada" fecha={compra.fecha_anulada} />
      </div>
    );
  }
  if (compra.estado === "completada") {
    return (
      <div className="fechas-cell">
        <FechaBadge tipo="completada" fecha={compra.fecha_llegada} />
      </div>
    );
  }
  return <span style={{ fontSize: 11, color: "#bdbdbd", fontWeight: 600 }}>Pendiente</span>;
}

/* ── Toast ────────────────────────────────────────────────── */
function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className="toast" style={{ background: toast.type === "success" ? "#2e7d32" : "#c62828" }}>
      <span style={{ fontSize: 15, display: "flex", alignItems: "center" }}>{toast.type === "success" ? <Check size={14} /> : <X size={14} />}</span>
      {toast.message}
    </div>
  );
}

/* ── Mini-modal: Registrar fecha de llegada ───────────────── */
function ModalRegistrarLlegada({ compra, onClose, onConfirm }) {
  const hoy = new Date().toISOString().split('T')[0];
  const [fecha,      setFecha]      = useState(compra.fecha_llegada || hoy);
  const [err,        setErr]        = useState("");
  const [confirming, setConfirming] = useState(false);

  const handleOk = async () => {
    if (!fecha) { setErr("Selecciona la fecha de llegada"); return; }
    if (confirming) return;
    setConfirming(true);
    await onConfirm(compra.id, fecha);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" style={{ maxWidth: 360 }} onClick={e => e.stopPropagation()}>
        <div style={{ padding: "24px 24px 16px" }}>
          <h3 style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 700, color: "#1a1a1a" }}>
            {compra.stockAplicado ? "Editar fecha de llegada" : "Registrar llegada"}
          </h3>
          <p style={{ margin: "0 0 18px", fontSize: 13, color: "#616161" }}>
            Compra <strong>{compra.id}</strong>
            {!compra.stockAplicado && " — se marcará como recibida y se aplicará el stock"}
          </p>
          <div className="field-wrap">
            <label className="field-label">Fecha de llegada</label>
            <input
              type="date"
              className={`field-input${err ? " error" : ""}`}
              value={fecha}
              max={hoy}
              onChange={e => { setFecha(e.target.value); setErr(""); }}
            />
            {err && <span className="field-error">{err}</span>}
          </div>
        </div>
        <div className="modal-footer modal-footer--center">
          <button className="btn-ghost" onClick={onClose} disabled={confirming}>Cancelar</button>
          <button className="btn-save" onClick={handleOk} disabled={confirming}>
            {confirming ? "Registrando…" : "Confirmar"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Página principal ─────────────────────────────────────── */
export default function GestionCompras() {
  const puedeCrear         = usePrivilegio("Compras_crear");
  const puedeEditar        = usePrivilegio("Compras_editar");
  const puedeCambiarEstado = usePrivilegio("Compras_cambiar_estado");
  const puedeAnular        = usePrivilegio("Compras_anular");

  const [compras,      setCompras]      = useState([]);
  const [proveedores,  setProveedores]  = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [search,        setSearch]        = useState("");
  const [filterEstado,  setFilterEstado]  = useState("todos");
  const [filterProv,    setFilterProv]    = useState("todos");
  const [filterDesde,   setFilterDesde]   = useState("");
  const [filterHasta,   setFilterHasta]   = useState("");
  const [showFilter,    setShowFilter]    = useState(false);
  const [page,          setPage]          = useState(1);
  const [modal,         setModal]         = useState(null);
  const [llegadaModal,  setLlegadaModal]  = useState(null);
  const [toast,         setToast]         = useState(null);
  const filterRef = useRef();

  const getProveedor = (id) => proveedores.find(p => (p.ID_Proveedor || p.id) === id) || null;

  // Si el rango viene invertido se ordena solo: el menor es "desde", el mayor "hasta".
  const [rangoDesde, rangoHasta] = (filterDesde && filterHasta && filterDesde > filterHasta)
    ? [filterHasta, filterDesde]
    : [filterDesde, filterHasta];

  const cargarCompras = async () => {
    setLoading(true);
    try {
      const cData = await getCompras({
        porPagina:  100,
        busqueda:   search.trim(),
        idProveedor: filterProv !== "todos" ? filterProv : null,
        fechaDesde: rangoDesde,
        fechaHasta: rangoHasta,
      });
      setCompras([...(cData.compras || [])].sort((a, b) => b.id - a.id));
    } catch (err) {
      showToast(err?.message || "Error al cargar las compras. Intenta de nuevo.", "error");
    } finally {
      setLoading(false);
    }
  };

  // Proveedores: se cargan una sola vez. Las compras las carga el efecto de abajo.
  useEffect(() => {
    getProveedores({ porPagina: 100 })
      .then(pData => setProveedores(pData.proveedores || pData || []))
      .catch(() => {});
  }, []);

  // Carga inicial + refetch (con debounce) cuando cambian los filtros que resuelve el backend.
  useEffect(() => {
    const t = setTimeout(() => { cargarCompras(); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, filterProv, rangoDesde, rangoHasta]);

  useEffect(() => {
    const h = e => {
      if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  /* ── Filtrado ──
     El backend ya resuelve búsqueda, proveedor y rango de fechas (ver cargarCompras).
     Aquí solo queda el estado (client-only) y una pasada rápida de texto para dar
     feedback inmediato mientras el debounce del refetch corre. */
  const filtered = compras.filter(c => {
    const q = search.toLowerCase();
    const matchQ = !q || (
      String(c.id).toLowerCase().includes(q) ||
      (c.proveedor   || "").toLowerCase().includes(q) ||
      (c.metodoPago  || "").toLowerCase().includes(q) ||
      (c.notas       || "").toLowerCase().includes(q)
    );
    const matchEstado = filterEstado === "todos" || c.estado === filterEstado;
    return matchQ && matchEstado;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);

  useEffect(() => setPage(1), [search, filterEstado, filterProv, rangoDesde, rangoHasta]);

  const hasFilter = filterEstado !== "todos" || filterProv !== "todos";

  /* ── CRUD handlers ── */
  const handleCreate = async (form) => {
    try {
      await apiCrearCompra(form);
      await cargarCompras();
      showToast("Compra registrada correctamente");
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al registrar la compra", "error");
    }
  };

  const handleEdit = async (form) => {
    // 3.18 — el formulario avisa cuando no se modificó nada: no se hace PUT.
    if (form?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    try {
      await editarCompra(form.id, form);
      await cargarCompras();
      showToast("Compra actualizada correctamente");
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al actualizar la compra", "error");
    }
  };

  const handleAnular = async (id) => {
    setModal(null);  // cerrar modal antes de mostrar toast para evitar que quede detrás
    try {
      await anularCompra(id);
      await cargarCompras();
      showToast("Compra anulada correctamente");
    } catch (err) {
      showToast(err.message || "Error al anular la compra", "error");
    }
  };

  const handleCompletarRapido = (id) => {
    const compra = compras.find(c => c.id === id);
    if (compra) setLlegadaModal(compra);
  };

  const handleConfirmarLlegada = async (id, fecha) => {
    try {
      await completarCompra(id, fecha);
      await cargarCompras();
      showToast("Compra completada y stock aplicado correctamente");
      setLlegadaModal(null);
    } catch (err) {
      showToast(err.message || "Error al completar la compra", "error");
      setLlegadaModal(null);
    }
  };

  return (
    <div className="page-wrapper">

      {/* ENCABEZADO */}
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Compras</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">

        {/* TOOLBAR */}
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar por ID, proveedor, método de pago…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarCompras()} data-tooltip="Actualizar compras">
            <RefreshCw size={15} />
          </button>

          {/* Filtros */}
          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className={"filter-icon-btn" + (hasFilter ? " has-filter" : "")}
              onClick={() => setShowFilter(v => !v)}
              data-tooltip="Filtrar compras"
            >
              ▼
            </button>

            {showFilter && (
              <div className="filter-dropdown filter-dropdown--wide">
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <div>
                    <p className="filter-section-title">Estado</p>
                    <div className="filter-grid">
                      {[
                        { val: "todos",      label: "Todos",       dot: "#bdbdbd" },
                        { val: "pendiente",  label: "Pendientes",  dot: "#f9a825" },
                        { val: "completada", label: "Completadas", dot: "#43a047" },
                        { val: "anulada",    label: "Anuladas",    dot: "#e53935" },
                      ].map(f => (
                        <button
                          key={f.val}
                          className={"filter-option" + (filterEstado === f.val ? " active" : "")}
                          onClick={() => { setFilterEstado(f.val); setPage(1); }}
                        >
                          <span className="filter-dot" style={{ background: f.dot }} />{f.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={{ borderLeft: "1px solid #f0f0f0", paddingLeft: 12 }}>
                    <p className="filter-section-title">Proveedor</p>
                    <div className="filter-grid">
                      <button
                        className={"filter-option" + (filterProv === "todos" ? " active" : "")}
                        onClick={() => { setFilterProv("todos"); setPage(1); }}
                      >
                        <span className="filter-dot" style={{ background: "#bdbdbd" }} />Todos
                      </button>
                      {proveedores.map(p => {
                        const pid = String(p.ID_Proveedor || p.id || "");
                        return (
                          <button
                            key={pid}
                            className={"filter-option" + (filterProv === pid ? " active" : "")}
                            onClick={() => { setFilterProv(pid); setPage(1); }}
                          >
                            <span className="filter-dot" style={{ background: "#2e7d32" }} />
                            {(p.responsable || p.Responsable || "").split(" ")[0]}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: 12 }}>
                  <DateRangeFilter
                    desde={filterDesde}
                    hasta={filterHasta}
                    onApply={({desde, hasta}) => { setFilterDesde(desde || ''); setFilterHasta(hasta || ''); setPage(1); }}
                    onClear={() => { setFilterDesde(''); setFilterHasta(''); setPage(1); }}
                    label="Filtrar por fecha de compra"
                  />
                </div>

                {hasFilter && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #f0f0f0", textAlign: "center" }}>
                    <button
                      onClick={() => { setFilterEstado("todos"); setFilterProv("todos"); setShowFilter(false); }}
                      style={{ fontSize: 11, fontWeight: 700, color: "#c62828", background: "none", border: "none", cursor: "pointer" }}
                    >Limpiar filtros</button>
                  </div>
                )}
              </div>
            )}
          </div>

          {(hasFilter || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilterEstado("todos"); setFilterProv("todos"); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          {puedeCrear && (
            <button className="btn-agregar" onClick={() => setModal({ mode: "new" })} data-tooltip="Registrar nueva compra">
              Nueva compra <span style={{ fontSize: 18 }}>+</span>
            </button>
          )}
        </div>

        {/* TABLA */}
        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "78px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 72 }}>ID</th>
                  <th>Proveedor</th>
                  <th>Método</th>
                  <th>Total</th>
                  <th>Estado</th>
                  <th>Fechas</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }, (_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 8 }, (_, j) => (
                        <td key={j}><div className="skeleton-cell" /></td>
                      ))}
                    </tr>
                  ))
                ) : paginated.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      <div className="empty-state">
                        <div className="empty-state__icon"><ShoppingCart size={32} strokeWidth={1} style={{ color: "#bdbdbd" }} /></div>
                        <p className="empty-state__text">
                          {hasFilter || search ? "Sin compras que coincidan." : "Sin compras registradas"}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : paginated.map((c, idx) => {
                  const prov  = getProveedor(c.idProveedor);
                  const metodo = METODOS_LABEL[(c.metodoPago || "").toLowerCase()];

                  return (
                    <tr key={c.id} className="tbl-row">

                      {/* ID + Nº */}
                      <td>
                        <span className="compra-id-badge">{c.id}</span>
                        <div style={{ fontSize: 10, color: "#bdbdbd", fontWeight: 600, marginTop: 2 }}>
                          #{String((safePage - 1) * ITEMS_PER_PAGE + idx + 1).padStart(2, "0")}
                        </div>
                      </td>

                      {/* Proveedor */}
                      <td>
                        <div className="prov-cell">
                          <div className="prov-avatar" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><Building2 size={18} /></div>
                          <div>
                            <div className="prov-name">{c.proveedor || prov?.Responsable || prov?.responsable || "—"}</div>
                            <div className="prov-id">{prov?.Ciudad || prov?.ciudad || ""}</div>
                          </div>
                        </div>
                      </td>

                      {/* Método */}
                      <td>
                        <span style={{
                          display: "inline-flex", alignItems: "center", gap: 5,
                          padding: "4px 10px", borderRadius: 20, fontSize: 12, fontWeight: 700,
                          background: metodo?.bg || "#f5f5f5",
                          color:      metodo?.color || "#757575",
                          border:     `1px solid ${metodo?.border || "#e0e0e0"}`,
                          whiteSpace: "nowrap",
                        }}>
                          {metodo?.Icon && <metodo.Icon size={14} style={{ flexShrink: 0 }} />} {metodo?.label || c.metodoPago}
                        </span>
                      </td>

                      {/* Total */}
                      <td>
                        <span className="total-cell">{COP(c.total)}</span>
                      </td>

                      {/* Estado */}
                      <td>
                        <span className={`estado-chip estado-chip--${c.estado}`}>
                          {c.estado === "pendiente"  && <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Clock size={13} /> Pendiente</span>}
                          {c.estado === "completada" && <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><CheckCircle2 size={13} /> Completada</span>}
                          {c.estado === "anulada"    && <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Ban size={13} /> Anulada</span>}
                        </span>
                      </td>

                      {/* Fechas de estado */}
                      <td><FechasCell compra={c} /></td>

                      {/* Acciones */}
                      <td>
                        <div className="actions-cell">
                          <button
                            className="act-btn act-btn--view"
                            data-tooltip="Ver detalle de compra"
                            onClick={() => setModal({ mode: "view", compra: c })}
                          ><Eye size={15} /></button>

                          {c.estado === "pendiente" && puedeCambiarEstado && (
                            <button
                              className="act-btn act-btn--success"
                              data-tooltip="Registrar llegada de mercancía"
                              onClick={() => handleCompletarRapido(c.id)}
                            ><CheckCircle2 size={15} /></button>
                          )}
                          {c.estado !== "anulada" && puedeEditar && (
                            <button
                              className="act-btn act-btn--edit"
                              data-tooltip="Editar compra"
                              onClick={() => setModal({ mode: "edit", compra: c })}
                            ><PenLine size={15} /></button>
                          )}

                          {c.estado !== "anulada" && puedeAnular && (
                            <button
                              className="act-btn act-btn--delete"
                              data-tooltip="Anular compra"
                              onClick={() => setModal({ mode: "anular", compra: c })}
                            ><Ban size={15} /></button>
                          )}
                        </div>
                      </td>

                    </tr>
                  );
                })}
                {!loading && (
                  <FilasRelleno current={paginated.length} perPage={ITEMS_PER_PAGE} colSpan={7} />
                )}
              </tbody>
            </table>
          </div>

          {/* PAGINACIÓN */}
          <div className="pagination-bar">
            <span className="pagination-count">
              {filtered.length} {filtered.length === 1 ? "compra" : "compras"} en total
            </span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow"
                onClick={() => setPage(1)}
                disabled={safePage === 1}>«</button>
              <button className="pg-btn-arrow"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={safePage === 1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}>›</button>
              <button className="pg-btn-arrow"
                onClick={() => setPage(totalPages)}
                disabled={safePage === totalPages}>»</button>
            </div>
          </div>
        </div>

      </div>

      {/* MODALES */}
      {modal?.mode === "new" && (
        <CrearCompra onClose={() => setModal(null)} onSave={handleCreate} />
      )}
      {modal?.mode === "view" && (
        <EditarCompra
          compra={modal.compra}
          mode="view"
          onClose={() => setModal(null)}
        />
      )}
      {modal?.mode === "edit" && (
        <EditarCompra
          compra={modal.compra}
          mode="edit"
          onClose={() => setModal(null)}
          onSave={handleEdit}
        />
      )}
      {modal?.mode === "anular" && (
        <AnularCompraModal
          compra={modal.compra}
          onClose={() => setModal(null)}
          onConfirm={handleAnular}
        />
      )}

      {llegadaModal && (
        <ModalRegistrarLlegada
          compra={llegadaModal}
          onClose={() => setLlegadaModal(null)}
          onConfirm={handleConfirmarLlegada}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
