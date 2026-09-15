import { useState, useEffect, useRef } from "react";
import { X, AlertTriangle, Trash2, Leaf, Eye, Pencil, Search, RefreshCw } from "lucide-react";
import { fmtFecha } from "../../../utils/dateUtils.js";
import { Toast, ModalOverlay } from "./ui.jsx";
import CrearCategoria from "./CrearCategoria.jsx";
import EditarCategoria from "./EditarCategoria.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import ModalEliminarValidado from "../../../ModalEliminarValidado";
import {
  getCategorias,
  crearCategoria,
  editarCategoria,
  eliminarCategoria,
  toggleEstadoCategoria,
} from "../../../services/categoriasProductosService";
import "./Categoriaproductos.css";

const ITEMS_PER_PAGE = 5;

function adaptCat(c) {
  return {
    id: c.ID_Categoria,
    nombre: c.Nombre_Categoria,
    descripcion: c.Descripcion ?? "",
    icon: c.Icono ?? "",
    estado: c.Estado === 1,
    fecha: fmtFecha(c.Fecha_creacion || c.Fecha_Creacion),
    totalProductos: c.total_productos ?? 0,
  };
}

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

function StatusPill({ active }) {
  return (
    <span
      className="status-pill"
      style={{
        background: active ? "#e8f5e9" : "#f5f5f5",
        color: active ? "#2e7d32" : "#9e9e9e",
        border: `1px solid ${active ? "#a5d6a7" : "#e0e0e0"}`,
      }}
    >
      <span
        className="status-dot"
        style={{ background: active ? "#43a047" : "#bdbdbd" }}
      />
      {active ? "Activo" : "Inactivo"}
    </span>
  );
}

function VerCategoria({ category, onClose }) {
  return (
    <ModalOverlay onClose={onClose}>
      <div className="modal-header">
        <div>
          <p className="modal-header__eyebrow">Categorías de Producto</p>
          <h2 className="modal-header__title">Detalle de Categoría</h2>
        </div>
        <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
      </div>
      <div className="modal-body">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "80px 1fr",
            gap: 20,
            marginBottom: 16,
          }}
        >
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Ícono</label>
            <div
              style={{
                width: "100%",
                height: 46,
                borderRadius: 10,
                background: "#f1f8f1",
                border: "1px solid #c8e6c9",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 28,
              }}
            >
              {category.icon}
            </div>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Nombre</label>
            <div className="field-input field-input--disabled">{category.nombre}</div>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Descripción</label>
          <div
            className="field-input field-input--disabled"
            style={{ minHeight: 60, lineHeight: 1.4, fontSize: 13, overflowWrap: "break-word", wordBreak: "break-word" }}
          >
            {category.descripcion || "Sin descripción registrada."}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            paddingTop: 8,
          }}
        >
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label">Estado actual</label>
            <StatusPill active={category.estado} />
          </div>
          {category.fecha && (
            <div style={{ textAlign: "right", fontSize: 11, color: "#9e9e9e" }}>
              <p style={{ margin: 0 }}>Fecha de creación</p>
              <strong style={{ color: "#616161" }}>{category.fecha}</strong>
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

function ModalDesactivarCategoria({ cat, count, onClose, onConfirm }) {
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
        <div className="delete-icon-wrap" style={{ background: "#fff8e1", border: "1px solid #ffe082", color: "#e65100" }}><AlertTriangle size={24} /></div>
        <h3 className="delete-title">Desactivar categoría</h3>
        <p className="delete-body">
          La categoría <strong>"{cat.nombre}"</strong> tiene {count} producto{count > 1 ? "s" : ""} asociado{count > 1 ? "s" : ""}.
        </p>

        <div style={{ textAlign: "left", margin: "12px 0", background: "#fff8e1", borderRadius: 10, padding: "12px 16px", border: "1px solid #ffe082" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <span style={{ fontSize: 14, marginTop: 1 }}>•</span>
            <span style={{ fontSize: 13, color: "#6d4c00", lineHeight: 1.4 }}>
              Todos los productos vinculados a esta categoría serán <strong>desactivados</strong> automáticamente.
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

function SkeletonRow() {
  return (
    <tr className="tbl-row">
      <td><div className="skeleton-cell" style={{ width: 28 }} /></td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="skeleton-cell" style={{ width: 36, height: 36, borderRadius: 9, flexShrink: 0 }} />
          <div className="skeleton-cell" style={{ width: "70%" }} />
        </div>
      </td>
      <td><div className="skeleton-cell" style={{ width: "85%" }} /></td>
      <td><div className="skeleton-cell" style={{ width: 52, height: 28, borderRadius: 14 }} /></td>
      <td><div className="skeleton-cell" style={{ width: 70 }} /></td>
      <td>
        <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
          {[0, 1, 2].map(i => (
            <div key={i} className="skeleton-cell" style={{ width: 34, height: 34, borderRadius: 8 }} />
          ))}
        </div>
      </td>
    </tr>
  );
}

export default function CategoriaProductos() {
  const [categorias,  setCategorias]  = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [search,      setSearch]      = useState("");
  const [filter,      setFilter]      = useState("todos");
  const [showFilter,  setShowFilter]  = useState(false);
  const [page,        setPage]        = useState(1);
  const [modal,       setModal]       = useState(null);
  const [toast,       setToast]       = useState(null);
  const filterRef = useRef(null);

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const cargarDatos = async () => {
    setLoading(true);
    try {
      const res = await getCategorias();
      setCategorias((res.categorias ?? []).map(adaptCat));
    } catch (e) {
      showToast("Error cargando categorías: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []); // eslint-disable-line

  useEffect(() => {
    const h = e => {
      if (filterRef.current && !filterRef.current.contains(e.target))
        setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const filtered = categorias.filter(c => {
    const q = search.toLowerCase();
    return (
      (c.nombre.toLowerCase().includes(q) ||
        c.descripcion.toLowerCase().includes(q)) &&
      (filter === "todos" ||
        (filter === "activo" ? c.estado : !c.estado))
    );
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice(
    (safePage - 1) * ITEMS_PER_PAGE,
    safePage * ITEMS_PER_PAGE
  );
  useEffect(() => setPage(1), [search, filter]);

  /* ── Toggle ── */
  const handleToggle = async (cat) => {
    if (cat.estado && cat.totalProductos > 0) {
      setModal({ type: "desactivar", category: cat });
      return;
    }
    // optimistic
    setCategorias(prev => prev.map(c => c.id === cat.id ? { ...c, estado: !c.estado } : c));
    try {
      await toggleEstadoCategoria(cat.id, cat.estado);
    } catch (e) {
      // revert
      setCategorias(prev => prev.map(c => c.id === cat.id ? { ...c, estado: cat.estado } : c));
      showToast("Error al cambiar estado: " + e.message, "error");
    }
  };

  const handleToggleConfirm = async (catId) => {
    try {
      await toggleEstadoCategoria(catId, true);
      showToast("Categoría y productos asociados desactivados");
      await cargarDatos();
    } catch (e) {
      showToast("Error al desactivar: " + e.message, "error");
    }
  };

  /* ── CRUD ── */
  const handleCreate = async (apiData) => {
    try {
      await crearCategoria(apiData);
      showToast("Categoría creada");
      setModal(null);
      await cargarDatos();
    } catch (e) {
      showToast("Error: " + e.message, "error");
      throw e;
    }
  };

  const handleEdit = async (apiData, toggleEstado) => {
    if (apiData?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    try {
      await editarCategoria(modal.category.id, apiData);
      if (toggleEstado) await toggleEstadoCategoria(modal.category.id, modal.category.estado);
      showToast("Cambios guardados");
      setModal(null);
      await cargarDatos();
    } catch (e) {
      showToast("Error: " + e.message, "error");
      throw e;
    }
  };

  const handleDelete = async () => {
    const catId = modal.category.id;
    setModal(null);
    try {
      await eliminarCategoria(catId);
      showToast("Categoría eliminada", "error");
      await cargarDatos();
    } catch (e) {
      showToast("Error al eliminar: " + e.message, "error");
      await cargarDatos();
    }
  };

  const canDelete = (cat) => {
    if (cat.totalProductos > 0)
      return {
        ok: false,
        razon: `Esta categoría tiene ${cat.totalProductos} producto${cat.totalProductos > 1 ? "s" : ""} vinculado${cat.totalProductos > 1 ? "s" : ""}. Reasígnalos o elimínalos antes de continuar.`,
      };
    return { ok: true };
  };

  const filterOptions = [
    { val: "todos",    label: "Todos",     dot: "#bdbdbd" },
    { val: "activo",   label: "Activos",   dot: "#43a047" },
    { val: "inactivo", label: "Inactivos", dot: "#ef5350" },
  ];

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Categorías de Productos</h1>
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
              title="Filtrar"
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
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilter("todos"); }} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          <button className="btn-agregar" onClick={() => setModal({ type: "crear" })} data-tooltip="Agregar nueva categoría">
            Agregar <span style={{ fontSize: 18 }}>+</span>
          </button>
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "66px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th>Nº</th>
                  <th>Nombre</th>
                  <th>Descripción</th>
                  <th>Estado</th>
                  <th>Fecha</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }, (_, i) => <SkeletonRow key={i} />)
                ) : paginated.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <div className="empty-state">
                        <div className="empty-state__icon"><Leaf size={40} strokeWidth={1} style={{ color: "#bdbdbd" }} /></div>
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
                    <td style={{ maxWidth: 220 }}>
                      <span className="cat-desc">{cat.descripcion}</span>
                    </td>
                    <td>
                      <Toggle value={cat.estado} onChange={() => handleToggle(cat)} />
                    </td>
                    <td><span className="cat-date">{cat.fecha}</span></td>
                    <td>
                      <div className="actions-cell">
                        <button
                          className="act-btn act-btn--view"
                          data-tooltip="Ver categoría"
                          onClick={() => setModal({ type: "ver", category: cat })}
                        ><Eye size={16} /></button>
                        <button
                          className="act-btn act-btn--edit"
                          data-tooltip="Editar categoría"
                          onClick={() => setModal({ type: "editar", category: cat })}
                        ><Pencil size={16} /></button>
                        <button
                          className="act-btn act-btn--delete"
                          data-tooltip="Eliminar categoría"
                          onClick={() => setModal({ type: "eliminar", category: cat })}
                        ><Trash2 size={16} /></button>
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
              {loading ? "Cargando…" : `${filtered.length} ${filtered.length === 1 ? "categoría" : "categorías"} en total`}
            </span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
              <button
                className="pg-btn-arrow"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={safePage === 1}
              >‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button
                className="pg-btn-arrow"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
              >›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
            </div>
          </div>
        </div>
      </div>

      {modal?.type === "crear"    && <CrearCategoria existingCategories={categorias} onClose={() => setModal(null)} onSave={handleCreate} />}
      {modal?.type === "editar"   && <EditarCategoria existingCategories={categorias} category={modal.category} onClose={() => setModal(null)} onSave={handleEdit} />}
      {modal?.type === "ver"      && <VerCategoria category={modal.category} onClose={() => setModal(null)} />}
      {modal?.type === "eliminar" && (
        <ModalEliminarValidado
          titulo="Eliminar categoría"
          descripcion={`¿Está seguro de que desea eliminar la categoría "${modal.category.nombre}"?`}
          validacion={canDelete(modal.category)}
          onClose={() => setModal(null)}
          onConfirm={handleDelete}
        />
      )}
      {modal?.type === "desactivar" && (
        <ModalDesactivarCategoria
          cat={modal.category}
          count={modal.category.totalProductos}
          onClose={() => setModal(null)}
          onConfirm={handleToggleConfirm}
        />
      )}
      <Toast toast={toast} />
    </div>
  );
}
