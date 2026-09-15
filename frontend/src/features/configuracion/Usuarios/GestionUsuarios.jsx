import { useState, useEffect, useRef } from "react";
import { Check, X, Search, User, Eye, PenLine, Trash2, Phone, Shield, RefreshCw } from "lucide-react";
import {
  getUsuarios, eliminarUsuario, toggleEstadoUsuario, cambiarRolUsuario,
} from "../../../services/usuariosService.js";
import { getRoles } from "../../../services/rolesService.js";
import { getUser } from "../../../services/authService.js";
import { usePrivilegio, usePrivilegios } from "../../../context/PrivilegiosContext.jsx";
import { Avatar, Toggle, RolBadge } from "./CrearUsuario.jsx";
import CrearUsuario from "./CrearUsuario.jsx";
import { ModalVerUsuario, ModalEliminarUsuario } from "./EditarUsuario.jsx";
import ModalCambiarRol from "./ModalCambiarRol.jsx";
import "./Usuarios.css";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { getRecordDate } from "../../../utils/dateUtils";
import { enlaceWhatsApp } from "../../../utils/whatsapp";

const PER_PAGE = 5;

function ToggleConTooltip({ on, onToggle, disabled, razon }) {
  return (
    <div style={{ position: "relative", display: "inline-flex" }} className="toggle-tooltip-wrap">
      <Toggle on={on} onToggle={onToggle} disabled={disabled} />
      {disabled && razon && <div className="toggle-tooltip">{razon}</div>}
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
      {Array.from({ length: 8 }, (_, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

export default function GestionUsuarios() {
  const puedeCambiarRol    = usePrivilegio("Usuarios_cambiar_rol");
  const puedeCambiarEstado = usePrivilegio("Usuarios_cambiar_estado");
  const { isAdmin }     = usePrivilegios();
  const sesion          = getUser();
  const soySuperAdmin   = !!sesion && String(sesion.id) === "1";
  const soyAdmin        = soySuperAdmin || isAdmin;

  const [usuarios,   setUsuarios]   = useState([]);
  const [roles,      setRoles]      = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [search,     setSearch]     = useState("");
  const [filter,     setFilter]     = useState("todos");
  const [filterRol,  setFilterRol]  = useState("todos");
  const [filterDesde, setFilterDesde] = useState("");
  const [filterHasta, setFilterHasta] = useState("");
  const [showFilter, setShowFilter] = useState(false);
  const [page,       setPage]       = useState(1);
  const [modal,      setModal]      = useState(null);
  const [toast,      setToast]      = useState(null);
  const filterRef = useRef();

  // Qué acciones ofrece cada fila (solo UX; el backend revalida todo).
  //  - Nadie toca al super admin (usuario id 1) salvo el propio super admin.
  //  - A un admin normal (idRol 1, id != 1) solo lo gestiona el super admin.
  //  - Un gestor de usuarios no admin no gestiona a otro gestor de usuarios.
  //  - Nadie se cambia el rol / estado / se elimina a sí mismo.
  const permisosFila = (u) => {
    const esSuperAdminFila = u.id === 1;
    const esAdminNormal    = u.idRol === 1 && u.id !== 1;
    const esFilaPropia     = !!sesion && String(sesion.id) === String(u.id);
    const rolObjetivo      = roles.find(r => r.nombre === u.rol);
    const objetivoEsGestor = !!rolObjetivo && (rolObjetivo.esAdmin || (rolObjetivo.permisos || []).some(c => c.startsWith("Usuarios_")));
    const gestionable =
      !(esSuperAdminFila && !esFilaPropia) &&
      !(esAdminNormal && !soySuperAdmin) &&
      !(objetivoEsGestor && !esFilaPropia && !soyAdmin);
    return {
      puedeEditar:     gestionable,
      puedeEliminar:   gestionable && !esFilaPropia && !esSuperAdminFila,
      puedeToggle:     puedeCambiarEstado && gestionable && !esFilaPropia && !esSuperAdminFila,
      puedeCambiarRol: puedeCambiarRol && gestionable && !esFilaPropia && !esSuperAdminFila,
    };
  };

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const cargarDatos = async () => {
    setLoading(true);
    try {
      const [users, rolesData] = await Promise.all([
        getUsuarios(),
        getRoles().catch(() => []),
      ]);
      setUsuarios([...users].sort((a, b) => b.id - a.id));
      setRoles(rolesData);
    } catch (e) {
      showToast(e.message || "Error al cargar usuarios", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  useEffect(() => {
    if (!modal) return;
    const block = e => e.stopPropagation();
    document.addEventListener("keydown", block, true);
    document.addEventListener("keyup",   block, true);
    document.addEventListener("keypress",block, true);
    return () => {
      document.removeEventListener("keydown", block, true);
      document.removeEventListener("keyup",   block, true);
      document.removeEventListener("keypress",block, true);
    };
  }, [modal]);

  useEffect(() => {
    const h = e => {
      if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const filtered = usuarios.filter(u => {
    const q      = search.toLowerCase();
    const matchQ = [u.nombre, u.apellidos, u.correo, u.rol, u.cedula, u.municipio]
      .filter(Boolean).some(v => v.toLowerCase().includes(q));
    const matchE   = filter    === "todos" || (filter === "activo" ? u.estado : !u.estado);
    const matchRol = filterRol === "todos" || u.rol === filterRol;
    // Fecha range (created/registered)
    let matchFecha = true;
    if (filterDesde || filterHasta) {
      const val = getRecordDate(u) || u.created_at || u.fecha_creacion;
      if (!val) matchFecha = false;
      else {
        const d = new Date(String(val).split('T')[0]);
        if (filterDesde && new Date(filterDesde) > d) matchFecha = false;
        if (filterHasta && new Date(filterHasta) < d) matchFecha = false;
      }
    }
    return matchQ && matchE && matchRol && matchFecha;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paged      = filtered.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);

  useEffect(() => { setPage(1); }, [search, filter, filterRol, filterDesde, filterHasta]);

  const handleSave = async (info) => {
    await cargarDatos();
    // Si el admin editó al usuario de la sesión actual, refrescar sus privilegios
    if (modal?.user && sesion && String(sesion.id) === String(modal.user.id)) {
      window.dispatchEvent(new CustomEvent("session-changed"));
    }
    if (info?.sinCambios) {
      showToast("No se hicieron cambios");
    } else {
      showToast(modal?.user ? "Usuario actualizado" : "Usuario creado");
    }
    setModal(null);
  };

  const handleCambiarRol = async (idRol) => {
    await cambiarRolUsuario(modal.user.id, idRol);
    if (sesion && String(sesion.id) === String(modal.user.id)) {
      window.dispatchEvent(new CustomEvent("session-changed"));
    }
    setModal(null);
    showToast("Rol actualizado");
    await cargarDatos();
  };

  const handleDeleteConfirm = async (id) => {
    const user = usuarios.find(u => u.id === id);
    try {
      await eliminarUsuario(user.tipo, id);
      showToast("Usuario eliminado");
      await cargarDatos();
      setModal(null);
    } catch (e) {
      // Mostrar el error como modal bloqueante (no como toast) para que el usuario lo vea ANTES de intentar de nuevo
      setModal({ type: "delete", user, razon: e.message || "No se puede eliminar este usuario." });
    }
  };

  const handleToggleClick = async (user) => {
    if (!permisosFila(user).puedeToggle) return;
    const match = u => u.id === user.id && u.tipo === user.tipo;
    setUsuarios(prev => prev.map(u => match(u) ? { ...u, estado: !u.estado } : u));
    try {
      await toggleEstadoUsuario(user.tipo, user.id, user.estado);
    } catch (e) {
      setUsuarios(prev => prev.map(u => match(u) ? { ...u, estado: user.estado } : u));
      showToast(e.message || "Error al cambiar estado", "error");
    }
  };

  const hasFilter = filter !== "todos" || filterRol !== "todos" || !!filterDesde || !!filterHasta;
  const todosLosRoles = roles.map(r => r.nombre).filter(Boolean).sort();

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Usuarios</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar por nombre, correo, rol o documento…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar usuarios">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className={"filter-icon-btn" + (hasFilter ? " has-filter" : "")}
              onClick={() => setShowFilter(v => !v)}
              data-tooltip="Filtrar usuarios"
            >▼</button>
            {showFilter && (
              <div className="filter-dropdown" style={{ minWidth: 240 }}>
                <p className="filter-section-title">Estado</p>
                <div className="filter-chips-row">
                  {[
                    { val: "todos",    label: "Todos",     color: "#bdbdbd" },
                    { val: "activo",   label: "Activos",   color: "#43a047" },
                    { val: "inactivo", label: "Inactivos", color: "#ef5350" },
                  ].map(f => (
                    <button key={f.val}
                      className={"filter-chip" + (filter === f.val ? " active" : "")}
                      style={{ "--chip-color": f.color }}
                      onClick={() => { setFilter(f.val); setPage(1); }}>
                      <span className="filter-dot" style={{ background: f.color }} />{f.label}
                    </button>
                  ))}
                </div>
                <div style={{ height: 1, background: "#f0f0f0", margin: "4px 6px" }} />
                <p className="filter-section-title">Rol</p>
                <div className="filter-roles-grid">
                  <button
                    className={"filter-role-chip" + (filterRol === "todos" ? " active" : "")}
                    onClick={() => { setFilterRol("todos"); setPage(1); }}>
                    Todos
                  </button>
                  {todosLosRoles.map(r => (
                    <button key={r}
                      className={"filter-role-chip" + (filterRol === r ? " active" : "")}
                      onClick={() => { setFilterRol(r); setPage(1); }}>
                      {r}
                    </button>
                  ))}
                </div>
                <div style={{ height: 1, background: "#f0f0f0", margin: "4px 6px" }} />
                <div style={{ padding: "4px 8px 8px" }}>
                  <DateRangeFilter
                    desde={filterDesde}
                    hasta={filterHasta}
                    onApply={({desde, hasta}) => { setFilterDesde(desde || ''); setFilterHasta(hasta || ''); setShowFilter(false); }}
                    onClear={() => { setFilterDesde(''); setFilterHasta(''); setShowFilter(false); }}
                    label="Fecha de registro"
                  />
                </div>
              </div>
            )}
          </div>

          {(hasFilter || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilter("todos"); setFilterRol("todos"); setFilterDesde(""); setFilterHasta(""); }} style={{ display:"flex", alignItems:"center", gap:4 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          <button className="btn-agregar" onClick={() => setModal({ type: "form", user: null })} data-tooltip="Agregar nuevo usuario">
            Agregar <span style={{ fontSize: 18 }}>+</span>
          </button>
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "72px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 48 }}>Nº</th>
                  <th>Usuario</th>
                  <th>N° Documento</th>
                  <th>Teléfono</th>
                  <th>Ubicación</th>
                  <th>Rol</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <SkeletonRows />
                ) : paged.length === 0 ? (
                  <tr><td colSpan={8}>
                    <div className="empty-state">
                      <div className="empty-state__icon"><User size={40} strokeWidth={1} style={{color:"#bdbdbd"}} /></div>
                      <p className="empty-state__text">
                        {hasFilter || search ? "Sin usuarios que coincidan." : "No hay usuarios registrados."}
                      </p>
                    </div>
                  </td></tr>
                ) : paged.map((user, idx) => (
                  <tr key={`${user.tipo}-${user.id}`} className="tbl-row">
                    <td>
                      <span className="row-num">
                        {String((safePage - 1) * PER_PAGE + idx + 1).padStart(2, "0")}
                      </span>
                    </td>
                    <td>
                      <div className="client-cell">
                        <div className="avatar-wrap">
                          <Avatar foto={user.foto} size={38} border={false} />
                        </div>
                        <div>
                          <div className="client-name">{user.nombre} {user.apellidos}</div>
                          <a href={`mailto:${user.correo}`} className="client-email" style={{ textDecoration: "none" }}>{user.correo}</a>
                          {user.autoEliminado && (
                            <div style={{ marginTop: 3, fontSize: 10, fontWeight: 800, color: "#b26a00", background: "#fff3e0", border: "1px solid #ffe0b2", borderRadius: 6, padding: "2px 6px", display: "inline-block" }}>
                              ⚠ El usuario eliminó su propia cuenta — edítalo o actívalo para recuperarla
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="doc-badge">
                        <span className="doc-type">{user.tipoDocumento || "CC"}</span>
                        <span className="doc-num">{user.cedula || "—"}</span>
                      </div>
                    </td>
                    <td>
                      {/* Con indicativo: sin el 57, wa.me contesta que el número
                          no existe. Un teléfono que no se entiende se muestra
                          escrito, sin enlace. */}
                      {!user.telefono
                        ? <span className="phone-cell" style={{ color: "#bdbdbd" }}>—</span>
                        : enlaceWhatsApp(user.telefono)
                        ? <a href={enlaceWhatsApp(user.telefono)} className="phone-cell" style={{ textDecoration: "none", display:"flex", alignItems:"center", gap:5 }} target="_blank" rel="noopener noreferrer">
                            <Phone size={14} />
                            {user.telefono}
                          </a>
                        : <span className="phone-cell" style={{ display:"flex", alignItems:"center", gap:5 }}>
                            <Phone size={14} />
                            {user.telefono}
                          </span>
                      }
                    </td>
                    <td>
                      <div className="location-city">{user.municipio    || "—"}</div>
                      <div className="location-dept">{user.departamento || ""}</div>
                    </td>
                    <td><RolBadge rol={user.rol} roles={roles} /></td>
                    <td>
                      {(() => {
                        const acc = permisosFila(user);
                        const esSuperAdminFila = user.id === 1;
                        const rolDesactivado = user.rol && roles.some(r => r.nombre === user.rol && !r.estado);
                        const razon =
                          esSuperAdminFila   ? "El super administrador siempre está activo"
                          : !acc.puedeToggle ? "No puedes cambiar el estado de este usuario"
                          : rolDesactivado   ? `El rol "${user.rol}" está desactivado`
                          : null;
                        return (
                          <ToggleConTooltip
                            on={esSuperAdminFila ? true : (!rolDesactivado && user.estado)}
                            onToggle={() => handleToggleClick(user)}
                            disabled={!acc.puedeToggle || rolDesactivado}
                            razon={razon}
                          />
                        );
                      })()}
                    </td>
                    <td>
                      {(() => {
                        const acc = permisosFila(user);
                        return (
                          <div className="actions-cell">
                            <button className="act-btn act-btn--view" data-tooltip="Ver usuario"
                              onClick={() => setModal({ type: "ver", user })}><Eye size={16} /></button>
                            {acc.puedeEditar && (
                              <button className="act-btn act-btn--edit" data-tooltip="Editar usuario"
                                onClick={() => setModal({ type: "form", user })}><PenLine size={16} /></button>
                            )}
                            {acc.puedeCambiarRol && (
                              <button className="act-btn act-btn--edit" data-tooltip="Cambiar rol"
                                onClick={() => setModal({ type: "rol", user })}><Shield size={16} /></button>
                            )}
                            {acc.puedeEliminar && (
                              <button className="act-btn act-btn--delete" data-tooltip="Eliminar usuario"
                                onClick={() => {
                                  const advertencias = user.tipo === "empleado"
                                    ? ["Si tiene domicilios asignados, la eliminación será rechazada."]
                                    : ["Si tiene ventas o pedidos registrados, la eliminación será rechazada."];
                                  setModal({ type: "delete", user, advertencias, razon: null });
                                }}><Trash2 size={16} /></button>
                            )}
                          </div>
                        );
                      })()}
                    </td>
                  </tr>
                ))}
                {!loading && (
                  <FilasRelleno current={paged.length} perPage={PER_PAGE} colSpan={8} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <span className="pagination-count">
              {filtered.length} {filtered.length === 1 ? "usuario" : "usuarios"} en total
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

      {modal?.type === "ver" && (
        <ModalVerUsuario user={modal.user} roles={roles} onClose={() => setModal(null)} />
      )}
      {modal?.type === "form" && (
        <CrearUsuario
          user={modal.user}
          roles={roles}
          onClose={() => setModal(null)}
          onSave={handleSave}
        />
      )}
      {modal?.type === "delete" && (
        <ModalEliminarUsuario
          user={modal.user}
          razon={modal.razon ?? null}
          advertencias={modal.advertencias ?? []}
          onClose={() => setModal(null)}
          onConfirm={handleDeleteConfirm}
        />
      )}
      {modal?.type === "rol" && (
        <ModalCambiarRol
          user={modal.user}
          roles={roles}
          onClose={() => setModal(null)}
          onConfirm={handleCambiarRol}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
