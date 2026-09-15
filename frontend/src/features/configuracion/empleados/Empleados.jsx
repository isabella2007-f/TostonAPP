import { useState, useEffect, useRef } from "react";
import { Check, X, Search, User, Eye, PenLine, Trash2, Phone, RefreshCw } from "lucide-react";
import { ITEMS_PER_PAGE } from "./empleadosUtils.js";
import { RolBadge } from "./CrearEmpleado.jsx";
import CrearEmpleado from "./CrearEmpleado.jsx";
import EditarEmpleado, { ModalVerEmpleado, ModalEliminarEmpleado } from "./EditarEmpleado.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { getUsuarios, crearEmpleado, editarUsuario, eliminarUsuario, toggleEstadoUsuario } from "../../../services/usuariosService.js";
import { subirImagenCloudinary } from "../../../utils/cloudinary.js";
import { getRoles } from "../../../services/rolesService.js";
import "./Empleados.css";

/* ─── Toggle ─────────────────────────────────────────────── */
function Toggle({ value, onChange }) {
  return (
    <button onClick={() => onChange(!value)} className="toggle-btn"
      style={{ background: value ? "#43a047" : "#c62828", boxShadow: value ? "0 2px 8px rgba(67,160,71,0.45)" : "0 2px 8px rgba(198,40,40,0.3)" }}>
      <span className="toggle-thumb" style={{ left: value ? 27 : 3 }}>
        <span className="toggle-label" style={{ color:"black" }}>{value ? "ON" : "OFF"}</span>
      </span>
    </button>
  );
}

/* ─── Toast ──────────────────────────────────────────────── */
function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className="toast" style={{ background: toast.type === "success" ? "#2e7d32" : "#c62828" }}>
      {toast.type === "success" ? <Check size={15} /> : <X size={16} />}
      {toast.message}
    </div>
  );
}

const adaptarEmpleado = (u) => ({
  id:           u.id,
  tipoDoc:      u.tipoDocumento || "CC",
  numDoc:       u.cedula || "",
  nombre:       u.nombre || "",
  apellidos:    u.apellidos || "",
  correo:       u.correo || "",
  telefono:     u.telefono || "",
  direccion:    u.direccion || "",
  departamento: u.departamento || "",
  municipio:    u.municipio || "",
  idRol:        u.idRol || "",
  estado:       u.estado,
  fotoPreview:  u.foto || null,
  fechaIngreso: "",
});

/* ─── Main ───────────────────────────────────────────────── */
export default function GestionEmpleados() {
  const [empleados, setEmpleados]   = useState([]);
  const [roles, setRoles]           = useState([]);
  const [loading, setLoading]       = useState(true);
  const [search, setSearch]         = useState("");
  const [filter, setFilter]         = useState("todos");
  const [filterRol, setFilterRol]   = useState(0);
  const [showFilter, setShowFilter] = useState(false);
  const [page, setPage]             = useState(1);
  const [modal, setModal]           = useState(null);
  const [toast, setToast]           = useState(null);
  const filterRef                   = useRef();

  const showToast = (msg, type = "success") => { setToast({ message:msg, type }); setTimeout(() => setToast(null), 3000); };

  const cargarDatos = async () => {
    setLoading(true);
    try {
      const [todos, rolesData] = await Promise.all([
        getUsuarios({ porPagina: 100 }),
        getRoles().catch(() => []),
      ]);
      setEmpleados(todos.filter(u => u.tipo === "empleado").map(adaptarEmpleado));
      setRoles(rolesData);
    } catch (e) {
      showToast(e.message || "Error al cargar empleados", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  useEffect(() => {
    const h = e => { if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const filtered = empleados.filter(e => {
    const q      = search.toLowerCase();
    const rolNom = roles.find(r => r.id === Number(e.idRol))?.nombre || "";
    const matchQ   = `${e.nombre} ${e.apellidos}`.toLowerCase().includes(q) || (e.correo||"").toLowerCase().includes(q) || (e.municipio||"").toLowerCase().includes(q) || (e.numDoc||"").toLowerCase().includes(q) || rolNom.toLowerCase().includes(q);
    const matchE   = filter    === "todos" || (filter === "activo" ? e.estado : !e.estado);
    const matchRol = filterRol === 0       || e.idRol === filterRol;
    return matchQ && matchE && matchRol;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice((safePage-1)*ITEMS_PER_PAGE, safePage*ITEMS_PER_PAGE);

  const handleSearch = value => { setSearch(value); setPage(1); };
  const handleFilterChange = value => { setFilter(value); setPage(1); };
  const handleFilterRolChange = value => { setFilterRol(value); setPage(1); };

  const handleCreate = async (data) => {
    const fotoUrl = data.fotoFile ? await subirImagenCloudinary(data.fotoFile).catch(() => null) : null;
    const payload = {
      Cedula:         data.numDoc,
      Tipo_Documento: data.tipoDoc,
      Nombre:         data.nombre,
      Apellidos:      data.apellidos,
      Correo:         data.correo,
      Contrasena:     data.contrasena,
      ID_Rol:         Number(data.idRol),
      Direccion:      data.direccion    || null,
      Municipio:      data.municipio    || null,
      Departamento:   data.departamento || null,
      Telefono:       data.telefono ? data.telefono.replace(/\s/g, "") : null,
      Foto:           fotoUrl,
    };
    try {
      await crearEmpleado(payload);
      showToast("Empleado creado");
      setModal(null);
      await cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al crear empleado", "error");
      throw e;
    }
  };

  const handleEdit = async (data) => {
    if (data?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    const fotoUrl = data.fotoFile
      ? await subirImagenCloudinary(data.fotoFile).catch(() => data.fotoPreview)
      : data.fotoPreview;
    const payload = {
      Cedula:         data.numDoc,
      Tipo_Documento: data.tipoDoc,
      Nombre:         data.nombre,
      Apellidos:      data.apellidos,
      Correo:         data.correo,
      ID_Rol:         Number(data.idRol),
      Direccion:      data.direccion    || null,
      Municipio:      data.municipio    || null,
      Departamento:   data.departamento || null,
      Telefono:       data.telefono ? data.telefono.replace(/\s/g, "") : null,
      Foto:           fotoUrl || null,
      ...(data.contrasena ? { Contrasena: data.contrasena } : {}),
    };
    try {
      await editarUsuario("empleado", data.id, payload);
      showToast("Cambios guardados");
      setModal(null);
      await cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al guardar cambios", "error");
      throw e;
    }
  };

  const handleDelete = async () => {
    try {
      await eliminarUsuario("empleado", modal.empleado.id);
      showToast("Empleado eliminado");
    } catch (e) {
      showToast(e.message || "No se puede eliminar este empleado", "error");
    }
    setModal(null);
    await cargarDatos();
  };

  const toggleEstado = async (emp) => {
    setEmpleados(p => p.map(e => e.id === emp.id ? { ...e, estado: !e.estado } : e));
    try {
      await toggleEstadoUsuario("empleado", emp.id, emp.estado);
    } catch {
      setEmpleados(p => p.map(e => e.id === emp.id ? { ...e, estado: emp.estado } : e));
      showToast("Error al cambiar estado", "error");
    }
  };

  const hasFilter = filter !== "todos" || filterRol !== 0;

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Empleados</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        {/* Toolbar */}
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={16} className="search-icon" />
            <input type="text" className="search-input"
              placeholder="Buscar por nombre, correo, ciudad, documento o rol…"
              value={search} onChange={e => handleSearch(e.target.value)} />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar empleados">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position:"relative" }}>
            <button className={"filter-icon-btn" + (hasFilter ? " has-filter" : "")} onClick={() => setShowFilter(v => !v)}>▼</button>
            {showFilter && (
              <div className="filter-dropdown">
                <p className="filter-section-title">Estado</p>
                {[{val:"todos",label:"Todos",dot:"#bdbdbd"},{val:"activo",label:"Activos",dot:"#43a047"},{val:"inactivo",label:"Inactivos",dot:"#ef5350"}].map(f => (
                  <button key={f.val} className={"filter-option"+(filter===f.val?" active":"")} onClick={() => handleFilterChange(f.val)}>
                    <span className="filter-dot" style={{ background:f.dot }} />{f.label}
                  </button>
                ))}
                <div style={{ height:1, background:"#f5f5f5", margin:"4px 0" }} />
                <p className="filter-section-title">Rol</p>
                <button className={"filter-option"+(filterRol===0?" active":"")} onClick={() => { handleFilterRolChange(0); setShowFilter(false); }}>
                  <span className="filter-dot" style={{ background:"#bdbdbd" }} />Todos
                </button>
                {roles.map(r => (
                  <button key={r.id} className={"filter-option"+(filterRol===r.id?" active":"")} onClick={() => { handleFilterRolChange(r.id); setShowFilter(false); }}>
                    <span style={{ fontSize:13 }}>{r.icono}</span>{r.nombre}
                  </button>
                ))}
              </div>
            )}
          </div>

          {(hasFilter || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilter("todos"); setFilterRol(0); }} style={{ display:"flex", alignItems:"center", gap:4 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          <button className="btn-agregar" onClick={() => setModal({ type:"crear" })}>
            Agregar <span style={{ fontSize:18 }}>+</span>
          </button>
        </div>

        {/* Tabla */}
        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "70px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width:48 }}>Nº</th>
                  <th>Empleado</th>
                  <th>Documento</th>
                  <th>Rol</th>
                  <th>Teléfono</th>
                  <th>Ubicación</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }, (_, i) => (
                    <tr key={i}>{Array.from({ length: 8 }, (_, j) => <td key={j}><div className="skeleton-cell" /></td>)}</tr>
                  ))
                ) : paginated.length === 0 ? (
                  <tr><td colSpan={8}>
                    <div className="empty-state">
                      <div className="empty-state__icon"><User size={48} strokeWidth={1} style={{color:"#bdbdbd"}}/></div>
                      <p className="empty-state__text">Sin empleados encontrados</p>
                    </div>
                  </td></tr>
                ) : paginated.map((emp, idx) => (
                  <tr key={emp.id} className="tbl-row">
                    <td><span className="row-num">{String((safePage-1)*ITEMS_PER_PAGE+idx+1).padStart(2,"0")}</span></td>
                    <td>
                      <div className="emp-cell">
                        <div className="avatar-wrap">{emp.fotoPreview ? <img src={emp.fotoPreview} alt={emp.nombre} /> : <User size={22} />}</div>
                        <div>
                          <div className="emp-name">{emp.nombre} {emp.apellidos}</div>
                          <div className="emp-email">{emp.correo}</div>
                        </div>
                      </div>
                    </td>
                    <td><div className="doc-badge"><span className="doc-type">{emp.tipoDoc}</span><span className="doc-num">{emp.numDoc}</span></div></td>
                    <td><RolBadge idRol={emp.idRol} roles={roles} /></td>
                    <td><span className="phone-cell" style={{display:"flex",alignItems:"center",gap:5}}><Phone size={14} />{emp.telefono}</span></td>
                    <td><div className="location-city">{emp.municipio}</div><div className="location-dept">{emp.departamento}</div></td>
                    <td><Toggle value={emp.estado} onChange={() => toggleEstado(emp)} /></td>
                    <td>
                      <div className="actions-cell">
                        <button className="act-btn act-btn--view"   onClick={() => setModal({ type:"ver",      empleado:emp })}><Eye size={16} /></button>
                        <button className="act-btn act-btn--edit"   onClick={() => setModal({ type:"editar",   empleado:emp })}><PenLine size={16} /></button>
                        <button className="act-btn act-btn--delete" onClick={() => setModal({ type:"eliminar", empleado:emp })}><Trash2 size={16} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && (
                  <FilasRelleno current={paginated.length} perPage={ITEMS_PER_PAGE} colSpan={8} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <span className="pagination-count">{filtered.length} {filtered.length === 1 ? "empleado" : "empleados"} en total</span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.max(1,p-1))} disabled={safePage===1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.min(totalPages,p+1))} disabled={safePage===totalPages}>›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
            </div>
          </div>
        </div>
      </div>

      {modal?.type === "crear"    && <CrearEmpleado onClose={() => setModal(null)} onSave={handleCreate} roles={roles} />}
      {modal?.type === "editar"   && <EditarEmpleado empleado={modal.empleado} onClose={() => setModal(null)} onSave={handleEdit} roles={roles} />}
      {modal?.type === "ver"      && <ModalVerEmpleado empleado={modal.empleado} onClose={() => setModal(null)} roles={roles} />}
      {modal?.type === "eliminar" && <ModalEliminarEmpleado empleado={modal.empleado} onClose={() => setModal(null)} onConfirm={handleDelete} />}

      <Toast toast={toast} />
    </div>
  );
}