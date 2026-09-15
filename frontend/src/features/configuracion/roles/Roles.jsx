import { useState, useEffect, useRef } from "react";
import { AlertTriangle, Check, X, Search, Eye, PenLine, Trash2, Shield, RefreshCw } from "lucide-react";
import { usePrivilegio } from "../../../context/PrivilegiosContext";
import { getRoles, eliminarRol, toggleEstadoRol } from "../../../services/rolesService.js";
import CrearRol from "./CrearRol.jsx";
import EditarRol from "./EditarRol.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import ModalEliminarValidado from "../../../ModalEliminarValidado";
import "./Roles.css";

const ITEMS_PER_PAGE = 5;

function Toggle({ value, onChange, disabled = false }) {
  return (
    <button
      onClick={disabled ? undefined : onChange}
      className="toggle-btn"
      disabled={disabled}
      style={{
        background: disabled ? "#bdbdbd" : value ? "#43a047" : "#c62828",
        boxShadow: disabled
          ? "none"
          : value
          ? "0 2px 8px rgba(67,160,71,0.45)"
          : "0 2px 8px rgba(198,40,40,0.3)",
        opacity: disabled ? 0.55 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
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

function ModalConfirmarDesactivarRol({ rol, onConfirm, onCancel }) {
  return (
    <div className="modal-overlay">
      <div style={{
        background: "#fff", borderRadius: 16, padding: "32px 28px",
        width: "min(420px, 95vw)", boxShadow: "0 8px 40px rgba(0,0,0,0.2)",
        textAlign: "center",
      }} onClick={e => e.stopPropagation()}>
        <AlertTriangle size={38} strokeWidth={1} style={{color:"#b71c1c",marginBottom:12}} />
        <h3 style={{ margin: "0 0 10px", fontSize: 18, fontWeight: 800, color: "#b71c1c" }}>
          Desactivar rol "{rol.nombre}"
        </h3>
        <p style={{ margin: "0 0 24px", color: "#616161", fontSize: 14, lineHeight: 1.6 }}>
          Este rol tiene <strong>{rol.totalUsuarios} usuario{rol.totalUsuarios !== 1 ? "s" : ""}</strong> asignado{rol.totalUsuarios !== 1 ? "s" : ""}.
          Desactivarlo les quitará el acceso al sistema hasta que el rol se reactive.
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onCancel} style={{
            flex: 1, padding: "11px", borderRadius: 10,
            border: "1px solid #e0e0e0", background: "#fff",
            color: "#555", fontSize: 14, cursor: "pointer", fontWeight: 600,
          }}>Cancelar</button>
          <button onClick={onConfirm} style={{
            flex: 1, padding: "11px", borderRadius: 10,
            border: "none", background: "#c62828",
            color: "#fff", fontSize: 14, cursor: "pointer", fontWeight: 700,
          }}>Sí, desactivar</button>
        </div>
      </div>
    </div>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className="toast" style={{ background: toast.type === "error" ? "#c62828" : "#2e7d32" }}>
      {toast.type === "error" ? <X size={15} /> : <Check size={15} />}
      {toast.message}
    </div>
  );
}

function SkeletonRows() {
  return Array.from({ length: 5 }, (_, i) => (
    <tr key={i}>
      {Array.from({ length: 7 }, (_, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

export default function GestionRoles() {
  const puedeCrear    = usePrivilegio("Roles_crear");
  const puedeEditar   = usePrivilegio("Roles_editar");
  const puedeEliminar = usePrivilegio("Roles_eliminar");

  const [roles,      setRoles]      = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [search,     setSearch]     = useState("");
  const [filter,     setFilter]     = useState("todos");
  const [showFilter, setShowFilter] = useState(false);
  const [page,       setPage]       = useState(1);
  const [modal,      setModal]      = useState(null);
  const [toast,      setToast]      = useState(null);
  const filterRef = useRef();

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const cargarDatos = async () => {
    setLoading(true);
    try {
      const data = await getRoles();
      setRoles(data);
    } catch (e) {
      showToast(e.message || "Error al cargar roles", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  useEffect(() => {
    const h = e => {
      if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const filtered   = roles.filter(r => {
    const matchQ = r.nombre.toLowerCase().includes(search.toLowerCase());
    const matchE = filter === "todos" || (filter === "activo" ? r.estado : !r.estado);
    return matchQ && matchE;
  });
  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);

  useEffect(() => setPage(1), [search, filter]);

  const handleSave = async (info) => {
    await cargarDatos();
    if (info?.sinCambios) {
      showToast("No se hicieron cambios");
    } else {
      showToast(modal?.mode === "new" ? "Rol creado" : "Cambios guardados");
    }
    setModal(null);
  };

  const handleDeleteConfirm = async () => {
    try {
      await eliminarRol(modal.rol.id);
      showToast("Rol eliminado", "error");
      await cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al eliminar", "error");
    }
    setModal(null);
  };

  const doToggle = async (rol) => {
    setRoles(prev => prev.map(r => r.id === rol.id ? { ...r, estado: !r.estado } : r));
    try {
      await toggleEstadoRol(rol.id, rol.estado);
      showToast(
        rol.estado ? `Rol "${rol.nombre}" desactivado` : `Rol "${rol.nombre}" activado`,
        rol.estado ? "error" : "success"
      );
    } catch (e) {
      setRoles(prev => prev.map(r => r.id === rol.id ? { ...r, estado: rol.estado } : r));
      showToast(e.message || "Error al cambiar estado", "error");
    }
  };

  const handleToggleClick = (rol) => {
    if (rol.esAdmin) return;
    if (rol.estado && (rol.totalUsuarios ?? 0) > 0) {
      setModal({ mode: "confirmDesactivar", rol });
      return;
    }
    doToggle(rol);
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Roles</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar rol…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar roles">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className={"filter-icon-btn" + (filter !== "todos" ? " has-filter" : "")}
              onClick={() => setShowFilter(v => !v)}
            >▼</button>
            {showFilter && (
              <div className="filter-dropdown">
                {[
                  { val: "todos",    label: "Todos",    dot: "#bdbdbd" },
                  { val: "activo",   label: "Activos",  dot: "#43a047" },
                  { val: "inactivo", label: "Inactivos",dot: "#ef5350" },
                ].map(f => (
                  <button
                    key={f.val}
                    className={"filter-option" + (filter === f.val ? " active" : "")}
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
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilter("todos"); }} style={{ display:"flex", alignItems:"center", gap:4 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          {puedeCrear && (
            <button className="btn-agregar" onClick={() => setModal({ mode: "new" })} data-tooltip="Crear nuevo rol">
              Agregar <span style={{ fontSize: 18 }}>+</span>
            </button>
          )}
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "64px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 48 }}>Nº</th>
                  <th>Ícono</th>
                  <th>Rol</th>
                  <th>Usuarios</th>
                  <th>Estado</th>
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
                        <div className="empty-state__icon"><Shield size={48} strokeWidth={1} style={{color:"#bdbdbd"}}/></div>
                        <p className="empty-state__text">Sin resultados</p>
                      </div>
                    </td>
                  </tr>
                ) : paginated.map((rol, idx) => (
                  <tr key={rol.id} className="tbl-row">
                    <td>
                      <span className="row-num">
                        {String((safePage - 1) * ITEMS_PER_PAGE + idx + 1).padStart(2, "0")}
                      </span>
                    </td>
                    <td>
                      <div className="rol-icon-wrap" style={{ cursor: "default" }}>
                        {rol.iconoPreview
                          ? <img src={rol.iconoPreview} alt={rol.nombre} />
                          : <span style={{ fontSize: 20 }}>{rol.icono}</span>}
                      </div>
                    </td>
                    <td>
                      <span className="cat-name">{rol.nombre}</span>
                      {rol.esEstatico && (
                        <span style={{
                          marginLeft: 6, fontSize: 10, fontWeight: 700,
                          color: "#f9a825", background: "#fff8e1",
                          border: "1px solid #ffe082", borderRadius: 6, padding: "1px 6px",
                        }}>protegido</span>
                      )}
                    </td>
                    <td>
                      <span style={{
                        fontSize: 12, fontWeight: 700,
                        color: (rol.totalUsuarios ?? 0) > 0 ? "#2e7d32" : "#bdbdbd",
                        background: (rol.totalUsuarios ?? 0) > 0 ? "#e8f5e9" : "#fafafa",
                        border: `1px solid ${(rol.totalUsuarios ?? 0) > 0 ? "#c8e6c9" : "#eeeeee"}`,
                        borderRadius: 20, padding: "2px 10px",
                      }}>
                        {rol.totalUsuarios ?? 0}
                      </span>
                    </td>
                    <td>
                      <Toggle value={rol.estado} onChange={() => handleToggleClick(rol)} disabled={rol.esAdmin} />
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button
                          className="act-btn act-btn--view"
                          data-tooltip="Ver rol"
                          onClick={() => setModal({ mode: "view", rol })}
                        ><Eye size={16} /></button>
                        {!rol.esEstatico && (
                          <>
                            {puedeEditar && (
                              <button
                                className="act-btn act-btn--edit"
                                data-tooltip="Editar rol"
                                onClick={() => setModal({ mode: "edit", rol })}
                              ><PenLine size={16} /></button>
                            )}
                            {puedeEliminar && (
                              <button
                                className="act-btn act-btn--delete"
                                data-tooltip="Eliminar rol"
                                onClick={() => setModal({ mode: "delete", rol })}
                              ><Trash2 size={16} /></button>
                            )}
                          </>
                        )}
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
              {filtered.length} {filtered.length === 1 ? "rol" : "roles"} en total
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

      {modal?.mode === "confirmDesactivar" && (
        <ModalConfirmarDesactivarRol
          rol={modal.rol}
          onCancel={() => setModal(null)}
          onConfirm={() => { setModal(null); doToggle(modal.rol); }}
        />
      )}
      {modal?.mode === "new"    && <CrearRol onClose={() => setModal(null)} onSave={handleSave} />}
      {modal?.mode === "edit"   && <EditarRol rol={modal.rol} mode="edit" onClose={() => setModal(null)} onSave={handleSave} />}
      {modal?.mode === "view"   && <EditarRol rol={modal.rol} mode="view" onClose={() => setModal(null)} />}
      {modal?.mode === "delete" && (
        <ModalEliminarValidado
          titulo="Eliminar rol"
          descripcion={`¿Está seguro de que desea eliminar el rol "${modal.rol.nombre}"?`}
          validacion={
            (modal.rol.totalUsuarios ?? 0) > 0
              ? { ok: false, razon: `No se puede eliminar: el rol tiene ${modal.rol.totalUsuarios} usuario(s) asignado(s). Reasigna o elimina esos usuarios primero.` }
              : { ok: true }
          }
          onClose={() => setModal(null)}
          onConfirm={handleDeleteConfirm}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
