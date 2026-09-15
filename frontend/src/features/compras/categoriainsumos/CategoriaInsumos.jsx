import { useState, useEffect, useRef } from "react";
import { Search, X, Eye, PenLine, Trash2, AlertTriangle, Tag, Package, Ban, RefreshCw } from "lucide-react";
import { fmtFecha } from "../../../utils/dateUtils.js";
import { Toast, ModalOverlay } from "./ui.jsx";
import CrearCategoriaInsumo from "./CrearCategoriaInsumo.jsx";
import EditarCategoriaInsumo from "./EditarCategoriaInsumo.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import ModalEliminarValidado from "../../../ModalEliminarValidado";
import {
  getCategorias,
  crearCategoria,
  editarCategoria,
  eliminarCategoria,
  toggleEstadoCategoria,
} from "../../../services/categoriasInsumosService.js";
import "./CategoriaInsumos.css";

const ITEMS_PER_PAGE = 5;

const ADAPT = raw => ({
  id:           raw.ID_Categoria,
  nombre:       raw.Nombre_Categoria,
  descripcion:  raw.Descripcion ?? "",
  icon:         raw.Icono ?? "",
  estado:       raw.Estado === 1,
  fecha:        fmtFecha(raw.Fecha_Creacion ?? raw.Fecha_creacion),
  totalInsumos: raw.total_insumos ?? 0,
});

function Toggle({ value, onChange }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className="toggle-btn"
      style={{
        background: value ? "#43a047" : "#c62828",
        boxShadow: value
          ? "0 2px 8px rgba(67,160,71,0.45)"
          : "0 2px 8px rgba(198,40,40,0.3)",
      }}
    >
      <span className="toggle-thumb" style={{ left: value ? 27 : 3 }}>
        <span className="toggle-label" style={{ color: "black" }}>
          {value ? "ON" : "OFF"}
        </span>
      </span>
    </button>
  );
}

function ModalDesactivarCategoriaInsumo({ cat, count, onClose, onConfirm }) {
  const [done, setDone] = useState(false);

  const handleConfirm = () => {
    setDone(true);
    setTimeout(() => {
      onConfirm(cat.id);
      onClose();
    }, 600);
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div style={{ padding: "28px 24px 18px", textAlign: "center" }}>
        <div className="delete-icon-wrap" style={{ background: "#fff8e1", border: "1px solid #ffe082", color: "#e65100", fontSize: 24, display: "flex", alignItems: "center", justifyContent: "center" }}><AlertTriangle size={24} /></div>
        <h3 className="delete-title">Desactivar categoría</h3>
        <p className="delete-body">
          La categoría <strong>"{cat.nombre}"</strong> tiene {count} insumo{count > 1 ? "s" : ""} asociado{count > 1 ? "s" : ""}.
        </p>
        <div style={{ textAlign: "left", margin: "12px 0", background: "#fff8e1", borderRadius: 10, padding: "12px 16px", border: "1px solid #ffe082" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <span style={{ fontSize: 14, marginTop: 1 }}>•</span>
            <span style={{ fontSize: 13, color: "#6d4c00", lineHeight: 1.4 }}>
              Todos los insumos vinculados a esta categoría serán <strong>desactivados</strong> automáticamente.
            </span>
          </div>
        </div>
        <p className="delete-warn">¿Desea continuar de todas formas?</p>
      </div>
      <div className="modal-footer" style={{ justifyContent: "center", gap: 12 }}>
        <button className="btn-cancel-full" onClick={onClose}>Cancelar</button>
        <button
          className="btn-danger"
          style={{ background: "#e65100", boxShadow: "0 3px 10px rgba(230,81,0,0.3)" }}
          onClick={handleConfirm}
          disabled={done}
        >
          {done ? "Desactivando…" : "Sí, desactivar"}
        </button>
      </div>
    </ModalOverlay>
  );
}

function StatusPill({ active }) {
  return (
    <span
      className="status-pill"
      style={{
        background: active ? "#e8f5e9" : "#f5f5f5",
        color:      active ? "#2e7d32" : "#9e9e9e",
        border:     `1px solid ${active ? "#a5d6a7" : "#e0e0e0"}`,
      }}
    >
      <span className="status-dot" style={{ background: active ? "#43a047" : "#bdbdbd" }} />
      {active ? "Activo" : "Inactivo"}
    </span>
  );
}

function VerCategoria({ cat, onClose }) {
  return (
    <ModalOverlay onClose={onClose}>
      <div className="modal-header">
        <div>
          <p className="modal-header__eyebrow">Categorías de Insumo</p>
          <h2 className="modal-header__title">Detalle de Categoría</h2>
        </div>
        <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
      </div>
      <div className="modal-body">
        <div style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: 20, marginBottom: 16 }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Ícono</label>
            <div style={{ width: "100%", height: 46, borderRadius: 10, background: "#f1f8f1", border: "1px solid #c8e6c9", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>
              {cat.icon}
            </div>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Nombre</label>
            <div className="field-input field-input--disabled">{cat.nombre}</div>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Descripción</label>
          <div className="field-input field-input--disabled" style={{ minHeight: 60, lineHeight: 1.4, fontSize: 13 }}>
            {cat.descripcion || "Sin descripción registrada."}
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 8 }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Estado actual</label>
            <StatusPill active={cat.estado} />
          </div>
          {cat.fecha && (
            <div style={{ textAlign: "right", fontSize: 11, color: "#9e9e9e" }}>
              <p style={{ margin: 0 }}>Fecha de creación</p>
              <strong style={{ color: "#616161" }}>{cat.fecha}</strong>
            </div>
          )}
        </div>
      </div>
      <div className="modal-footer">
        <button className="btn-ghost" onClick={onClose}>Cerrar</button>
      </div>
    </ModalOverlay>
  );
}

function SkeletonRows() {
  return Array.from({ length: 5 }, (_, i) => (
    <tr key={i} className="tbl-row">
      <td><div className="skeleton-cell" style={{ width: 28 }} /></td>
      <td><div className="skeleton-cell" style={{ width: "60%" }} /></td>
      <td><div className="skeleton-cell" style={{ width: "80%" }} /></td>
      <td><div className="skeleton-cell" style={{ width: 52 }} /></td>
      <td><div className="skeleton-cell" style={{ width: 80 }} /></td>
      <td><div className="skeleton-cell" style={{ width: 80 }} /></td>
    </tr>
  ));
}

export default function CategoriaInsumos() {
  const [categorias,  setCategorias]  = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [search,      setSearch]      = useState("");
  const [filter,      setFilter]      = useState("todos");
  const [showFilter,  setShowFilter]  = useState(false);
  const [page,        setPage]        = useState(1);
  const [modal,       setModal]       = useState(null);
  const [toast,       setToast]       = useState(null);
  const filterRef = useRef();

  useEffect(() => {
    const h = e => {
      if (filterRef.current && !filterRef.current.contains(e.target))
        setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const cargarDatos = async () => {
    try {
      setLoading(true);
      const data = await getCategorias();
      setCategorias((data.categorias ?? []).map(ADAPT));
    } catch (e) {
      showToast(e.message || "Error cargando categorías", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  /* ── Filtrado ── */
  const filtered = categorias.filter(c => {
    const q      = search.toLowerCase();
    const matchQ = c.nombre.toLowerCase().includes(q) || c.descripcion.toLowerCase().includes(q);
    const matchE = filter === "todos" || (filter === "activo" ? c.estado : !c.estado);
    return matchQ && matchE;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);
  useEffect(() => setPage(1), [search, filter]);

  /* ── Toggle con confirmación si tiene insumos ── */
  const handleToggle = async (cat) => {
    if (cat.estado && cat.totalInsumos > 0) {
      setModal({ type: "desactivar", cat });
      return;
    }
    setCategorias(prev => prev.map(c => c.id === cat.id ? { ...c, estado: !c.estado } : c));
    try {
      await toggleEstadoCategoria(cat.id, cat.estado);
    } catch (e) {
      setCategorias(prev => prev.map(c => c.id === cat.id ? { ...c, estado: cat.estado } : c));
      showToast(e.message || "Error al cambiar estado", "error");
    }
  };

  const handleToggleConfirm = async (catId) => {
    try {
      await toggleEstadoCategoria(catId, true);
      showToast("Categoría e insumos asociados desactivados");
      await cargarDatos();
    } catch (e) {
      showToast("Error al desactivar: " + e.message, "error");
    }
  };

  /* ── CRUD ── */
  const handleCreate = async (payload) => {
    try {
      await crearCategoria(payload);
      showToast("Categoría creada");
      setModal(null);
      cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al crear la categoría", "error");
    }
  };

  const handleEdit = async (payload, toggleEstado) => {
    if (payload?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    try {
      await editarCategoria(modal.cat.id, payload);
      if (toggleEstado) await toggleEstadoCategoria(modal.cat.id, modal.cat.estado);
      showToast("Cambios guardados");
      setModal(null);
      cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al guardar cambios", "error");
    }
  };

  const handleDelete = async () => {
    try {
      await eliminarCategoria(modal.cat.id);
      showToast("Categoría eliminada");
      setModal(null);
      cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al eliminar la categoría", "error");
    }
  };

  const filterOptions = [
    { val: "todos",    label: "Todos",     dot: "#bdbdbd" },
    { val: "activo",   label: "Activos",   dot: "#43a047" },
    { val: "inactivo", label: "Inactivos", dot: "#ef5350" },
  ];

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Categorías de Insumos</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar por nombre o descripción…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar categorías">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className={`filter-icon-btn${filter !== "todos" ? " has-filter" : ""}`}
              onClick={() => setShowFilter(v => !v)}
            >▼</button>
            {showFilter && (
              <div className="filter-dropdown">
                {filterOptions.map(f => (
                  <button
                    key={f.val}
                    className={`filter-option${filter === f.val ? " active" : ""}`}
                    onClick={() => { setFilter(f.val); setShowFilter(false); }}
                  >
                    <span className="filter-dot" style={{ background: f.dot }} />
                    {f.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {(filter !== "todos" || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilter("todos"); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          <button className="btn-agregar" onClick={() => setModal({ type: "crear" })} data-tooltip="Agregar nueva categoría de insumo">
            Agregar <span style={{ fontSize: 18 }}>+</span>
          </button>
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "66px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th>Nº</th>
                  <th>Categoría</th>
                  <th>Descripción</th>
                  <th>Estado</th>
                  <th>Fecha de creación</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <SkeletonRows />
                ) : paginated.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-state">
                        <div className="empty-state__icon"><Tag size={48} strokeWidth={1} style={{ color: "#bdbdbd" }} /></div>
                        <p className="empty-state__text">Sin resultados</p>
                      </div>
                    </td>
                  </tr>
                ) : paginated.map((cat, idx) => (
                  <tr key={cat.id} className="tbl-row">
                    <td>
                      <span className="cat-num">
                        {String((safePage - 1) * ITEMS_PER_PAGE + idx + 1).padStart(2, "0")}
                      </span>
                    </td>
                    <td>
                      <div className="cat-cell">
                        <div className="cat-icon-box">{cat.icon}</div>
                        <span className="cat-name">{cat.nombre}</span>
                      </div>
                    </td>
                    <td style={{ maxWidth: 200 }}>
                      <span className="cat-desc">{cat.descripcion}</span>
                    </td>
                    <td>
                      <Toggle value={cat.estado} onChange={() => handleToggle(cat)} />
                    </td>
                    <td>
                      <span className="cat-date">{cat.fecha}</span>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button className="act-btn act-btn--view" data-tooltip="Ver categoría"
                          onClick={() => setModal({ type: "ver", cat })}><Eye size={15} /></button>
                        <button className="act-btn act-btn--edit" data-tooltip="Editar categoría"
                          onClick={() => setModal({ type: "editar", cat })}><PenLine size={15} /></button>
                        <button className="act-btn act-btn--delete" data-tooltip="Eliminar categoría"
                          onClick={() => setModal({ type: "eliminar", cat })}><Trash2 size={15} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && (
                  <FilasRelleno current={paginated.length} perPage={ITEMS_PER_PAGE} colSpan={6} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">

            <span className="pagination-count">
              {filtered.length} {filtered.length === 1 ? "categoría" : "categorías"} en total
            </span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
            </div>
          </div>
        </div>
      </div>

      {modal?.type === "crear"    && <CrearCategoriaInsumo existingCategories={categorias} onClose={() => setModal(null)} onSave={handleCreate} />}
      {modal?.type === "editar"   && <EditarCategoriaInsumo existingCategories={categorias} cat={modal.cat} onClose={() => setModal(null)} onSave={handleEdit} />}
      {modal?.type === "ver"      && <VerCategoria cat={modal.cat} onClose={() => setModal(null)} />}
      {modal?.type === "desactivar" && (
        <ModalDesactivarCategoriaInsumo
          cat={modal.cat}
          count={modal.cat.totalInsumos}
          onClose={() => setModal(null)}
          onConfirm={handleToggleConfirm}
        />
      )}
      {modal?.type === "eliminar" && (
        modal.cat.totalInsumos > 0 ? (
          <div className="modal-overlay">
            <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()} style={{ overflow: "hidden", padding: 0 }}>

              <div style={{ background: "linear-gradient(135deg, #b71c1c 0%, #c62828 100%)", padding: "28px 24px 22px", textAlign: "center", position: "relative" }}>
                <button onClick={() => setModal(null)} style={{ position: "absolute", top: 12, right: 12, color: "rgba(255,255,255,0.8)", background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.3)", borderRadius: 8, width: 30, height: 30, cursor: "pointer", fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center" }}><X size={14} /></button>
                <div style={{ width: 64, height: 64, borderRadius: "50%", background: "rgba(255,255,255,0.15)", border: "2px solid rgba(255,255,255,0.3)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}><Ban size={30} /></div>
                <h3 style={{ margin: 0, fontSize: 19, fontWeight: 800, color: "#fff", letterSpacing: -0.3 }}>No se puede eliminar</h3>
                <p style={{ margin: "6px 0 0", fontSize: 13, color: "rgba(255,255,255,0.85)", fontWeight: 500 }}>"{modal.cat.nombre}"</p>
              </div>

              <div style={{ padding: "18px 24px" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 14px", background: "#ffebee", border: "1.5px solid #ef9a9a", borderRadius: 10 }}>
                  <Package size={18} style={{ flexShrink: 0 }} />
                  <div>
                    <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "#c62828" }}>
                      Tiene {modal.cat.totalInsumos} insumo{modal.cat.totalInsumos !== 1 ? "s" : ""} asociado{modal.cat.totalInsumos !== 1 ? "s" : ""}
                    </p>
                    <p style={{ margin: "3px 0 0", fontSize: 12, color: "#616161" }}>
                      Reasigna o elimina los insumos de esta categoría antes de poder eliminarla.
                    </p>
                  </div>
                </div>
              </div>

              <div style={{ padding: "0 24px 20px" }}>
                <button onClick={() => setModal(null)} style={{ width: "100%", padding: "11px", borderRadius: 10, border: "none", background: "#c62828", color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>
                  Entendido
                </button>
              </div>
            </div>
          </div>
        ) : (
          <ModalEliminarValidado
            titulo="Eliminar categoría"
            descripcion={`¿Está seguro de que desea eliminar la categoría "${modal.cat.nombre}"?`}
            validacion={{ ok: true }}
            onClose={() => setModal(null)}
            onConfirm={handleDelete}
          />
        )
      )}

      <Toast toast={toast} />
    </div>
  );
}
