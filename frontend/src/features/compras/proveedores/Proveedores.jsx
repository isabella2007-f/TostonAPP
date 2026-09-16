import { useState, useRef, useEffect } from "react";
import { Search, X, Check, Eye, PenLine, Trash2, Building2, Phone, RefreshCw } from "lucide-react";
import "./Proveedores.css";
import CrearProveedor  from "./CrearProveedor";
import EditarProveedor from "./EditarProveedor";
import ModalEliminarValidado from "../../../ModalEliminarValidado";
import {
  getProveedores,
  crearProveedor,
  editarProveedor,
  eliminarProveedor,
} from "../../../services/proveedoresService.js";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { getRecordDate } from "../../../utils/dateUtils";
import { enlaceWhatsApp } from "../../../utils/whatsapp";

const ITEMS_PER_PAGE = 5;

const ADAPT = raw => ({
  id:                 raw.ID_Proveedor,
  sujetoDerecho:      raw.Sujeto_Derecho    ?? 1,
  nit:                raw.NIT               ?? "",
  responsable:        raw.Responsable,
  direccion:          raw.Direccion         ?? "",
  ciudad:             raw.Municipio         ?? "",
  departamento:       raw.Departamento      ?? "",
  celular:            raw.Telefono          ?? "",
  correo:             raw.Correo            ?? "",
  totalCompras:       raw.total_compras     ?? 0,
  ultimaCompraFecha:  raw.ultima_compra_fecha  ?? null,
  ultimaCompraEstado: raw.ultima_compra_estado ?? null,
  insumosProvistos:   raw.insumos_provistos    ?? [],
});

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className="toast" style={{ background: toast.type === "success" ? "#2e7d32" : "#c62828" }}>
      <span style={{ fontSize: 15, display: "flex", alignItems: "center" }}>{toast.type === "success" ? <Check size={14} /> : <X size={14} />}</span>
      {toast.message}
    </div>
  );
}

function SkeletonRows() {
  return Array.from({ length: 5 }, (_, i) => (
    <tr key={i} className="tbl-row">
      <td><div className="skeleton-cell" style={{ width: 28 }} /></td>
      <td><div className="skeleton-cell" style={{ width: "65%" }} /></td>
      <td><div className="skeleton-cell" style={{ width: "55%" }} /></td>
      <td><div className="skeleton-cell" style={{ width: "70%" }} /></td>
      <td><div className="skeleton-cell" style={{ width: 80 }} /></td>
    </tr>
  ));
}

export default function GestionProveedores() {
  const [proveedores,  setProveedores]  = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [search,       setSearch]       = useState("");
  const [filterCiudad, setFilterCiudad] = useState("todas");
  const [showFilter,   setShowFilter]   = useState(false);
  const [filterDesde,  setFilterDesde]   = useState("");
  const [filterHasta,  setFilterHasta]   = useState("");
  const [page,         setPage]         = useState(1);
  const [modal,        setModal]        = useState(null);
  const [toast,        setToast]        = useState(null);
  const filterRef = useRef();

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

  const cargarDatos = async () => {
    try {
      setLoading(true);
      const data = await getProveedores();
      setProveedores((data.proveedores ?? []).map(ADAPT));
    } catch (e) {
      showToast(e.message || "Error cargando proveedores", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  const ciudadesUnicas = [...new Set(proveedores.map(p => p.ciudad).filter(Boolean))].sort();

  const filtered = proveedores.filter(p => {
    const q = search.toLowerCase();
    const matchQ = (
      p.responsable.toLowerCase().includes(q) ||
      (p.correo    || "").toLowerCase().includes(q) ||
      (p.celular   || "").toLowerCase().includes(q) ||
      (p.direccion || "").toLowerCase().includes(q)
    );
    const matchCiudad = filterCiudad === "todas" || p.ciudad === filterCiudad;
    // Fecha range over ultimaCompraFecha or other candidate
    let matchFecha = true;
    if (filterDesde || filterHasta) {
      const val = getRecordDate(p) || p.ultimaCompraFecha;
      if (!val) matchFecha = false;
      else {
        const d = new Date(String(val).split('T')[0]);
        if (filterDesde && new Date(filterDesde) > d) matchFecha = false;
        if (filterHasta && new Date(filterHasta) < d) matchFecha = false;
      }
    }
    return matchQ && matchCiudad && matchFecha;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);
  useEffect(() => setPage(1), [search, filterCiudad]);

  const hasFilter = filterCiudad !== "todas";

  /* ── CRUD ── */
  const handleCreate = async (payload) => {
    try {
      await crearProveedor(payload);
      showToast("Proveedor creado");
      setModal(null);
      cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al crear el proveedor", "error");
    }
  };

  const handleEdit = async (payload) => {
    if (payload?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    try {
      await editarProveedor(modal.proveedor.id, payload);
      showToast("Cambios guardados");
      setModal(null);
      cargarDatos();
    } catch (e) {
      showToast(e.message || "Error al guardar cambios", "error");
    }
  };

  const handleDelete = async () => {
    try {
      await eliminarProveedor(modal.proveedor.id);
      showToast("Proveedor eliminado");
      setModal(null);
      cargarDatos();
    } catch (e) {
      setModal(null);
      showToast(e.message || "Error al eliminar el proveedor", "error");
    }
  };

  return (
    <div className="page-wrapper">

      <div className="page-header">
        <h1 className="page-header__title">Gestión de Proveedores</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">

        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar por responsable, correo o celular…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar proveedores">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              className={"filter-icon-btn" + (hasFilter ? " has-filter" : "")}
              onClick={() => setShowFilter(v => !v)}
            >▼</button>

            {showFilter && (
              <div className="filter-dropdown" style={{ minWidth: 200 }}>
                <div className="filter-dropdown__section">
                  <p className="filter-section-title">Ciudad</p>
                  <button
                    className={"filter-option" + (filterCiudad === "todas" ? " active" : "")}
                    onClick={() => setFilterCiudad("todas")}
                  >
                    <span className="filter-dot" style={{ background: "#bdbdbd" }} />Todas
                  </button>
                  {ciudadesUnicas.map(ciudad => (
                    <button
                      key={ciudad}
                      className={"filter-option" + (filterCiudad === ciudad ? " active" : "")}
                      onClick={() => setFilterCiudad(ciudad)}
                    >
                      <span className="filter-dot" style={{ background: "#2e7d32" }} />{ciudad}
                    </button>
                  ))}
                </div>
                <div style={{ padding: 12 }}>
                  <DateRangeFilter
                    desde={filterDesde}
                    hasta={filterHasta}
                    onApply={({desde, hasta}) => { setFilterDesde(desde || ''); setFilterHasta(hasta || ''); setShowFilter(false); }}
                    onClear={() => { setFilterDesde(''); setFilterHasta(''); setShowFilter(false); }}
                    label="Filtrar por fecha (última compra)"
                  />
                </div>
              </div>
            )}
          </div>

          {(filterCiudad !== "todas" || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilterCiudad("todas"); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          <button className="btn-agregar" onClick={() => setModal({ mode: "new" })} data-tooltip="Agregar nuevo proveedor">
            Agregar <span style={{ fontSize: 18 }}>+</span>
          </button>
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "68px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 48 }}>Nº</th>
                  <th>Proveedor</th>
                  <th>Teléfono</th>
                  <th>Ubicación</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <SkeletonRows />
                ) : paginated.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      <div className="empty-state">
                        <Building2 size={32} strokeWidth={1} style={{ color: "#bdbdbd" }} />
                        <p className="empty-state__text">
                          {hasFilter || search ? "Sin proveedores que coincidan." : "Sin proveedores registrados"}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : paginated.map((p, idx) => (
                  <tr key={p.id} className="tbl-row">

                    <td>
                      <span className="row-num">
                        {String((safePage - 1) * ITEMS_PER_PAGE + idx + 1).padStart(2, "0")}
                      </span>
                    </td>

                    <td>
                      <div className="client-cell">
                        <div style={{ width: 38, height: 38, borderRadius: 10, background: "#e8f5e9", border: "2px solid #c8e6c9", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <Building2 size={18} />
                        </div>
                        <div>
                          <div className="client-name">{p.responsable}</div>
                          {p.correo
                            ? <a href={`mailto:${p.correo}`} className="client-email" style={{ textDecoration: "none" }}>{p.correo}</a>
                            : <span className="client-email" style={{ color: "#bdbdbd" }}>Sin correo</span>
                          }
                        </div>
                      </div>
                    </td>

                    <td>
                      {/* Con indicativo: sin el 57, wa.me contesta que el número
                          no existe. Uno que no se entiende va escrito, sin
                          enlace. */}
                      {!p.celular
                        ? <span className="phone-cell" style={{ color: "#bdbdbd" }}>—</span>
                        : enlaceWhatsApp(p.celular)
                        ? <a href={enlaceWhatsApp(p.celular)} className="phone-cell" style={{ textDecoration: "none" }} target="_blank" rel="noopener noreferrer">
                            <Phone size={14} />
                            {p.celular}
                          </a>
                        : <span className="phone-cell">
                            <Phone size={14} />
                            {p.celular}
                          </span>
                      }
                    </td>

                    <td>
                      <div className="location-city">{p.ciudad || "—"}</div>
                      <div className="location-dept">{p.departamento || ""}</div>
                    </td>

                    <td>
                      <div className="actions-cell">
                        <button className="act-btn act-btn--view" data-tooltip="Ver proveedor"
                          onClick={() => setModal({ mode: "view", proveedor: p })}><Eye size={15} /></button>
                        <button className="act-btn act-btn--edit" data-tooltip="Editar proveedor"
                          onClick={() => setModal({ mode: "edit", proveedor: p })}><PenLine size={15} /></button>
                        <button className="act-btn act-btn--delete" data-tooltip="Eliminar proveedor"
                          onClick={() => setModal({ mode: "delete", proveedor: p })}><Trash2 size={15} /></button>
                      </div>
                    </td>

                  </tr>
                ))}
                {!loading && (
                  <FilasRelleno current={paginated.length} perPage={ITEMS_PER_PAGE} colSpan={5} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <span className="pagination-count">
              {filtered.length} {filtered.length === 1 ? "proveedor" : "proveedores"} en total
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

      {modal?.mode === "new" && (
        <CrearProveedor onClose={() => setModal(null)} onSave={handleCreate} />
      )}
      {modal?.mode === "edit" && (
        <EditarProveedor
          proveedor={modal.proveedor}
          mode="edit"
          onClose={() => setModal(null)}
          onSave={handleEdit}
        />
      )}
      {modal?.mode === "view" && (
        <EditarProveedor
          proveedor={modal.proveedor}
          mode="view"
          onClose={() => setModal(null)}
        />
      )}
      {modal?.mode === "delete" && (
        <ModalEliminarValidado
          titulo="Eliminar proveedor"
          descripcion={`¿Está seguro de que desea eliminar al proveedor "${modal.proveedor.responsable}"?`}
          validacion={
            modal.proveedor.totalCompras > 0
              ? { ok: false, razon: `Este proveedor tiene ${modal.proveedor.totalCompras} compra(s) registrada(s) y no puede eliminarse.` }
              : { ok: true }
          }
          onClose={() => setModal(null)}
          onConfirm={handleDelete}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
