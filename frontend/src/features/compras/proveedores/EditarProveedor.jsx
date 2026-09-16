import { useState } from "react";
import { X, Building2, MapPin, Phone, Mail } from "lucide-react";
import { esUbicacionValida } from "../../../utils/inputFilters";
import { fmtFecha } from "../../../utils/dateUtils";
import { enlaceWhatsApp } from "../../../utils/whatsapp";
import "./Proveedores.css";

const fmtTel = raw => {
  const d = (raw || "").replace(/\D/g, "").slice(0, 10);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)} ${d.slice(3)}`;
  return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
};


const DEPARTAMENTOS_CO = [
  "Amazonas","Antioquia","Arauca","Atlántico","Bogotá D.C.","Bolívar","Boyacá",
  "Caldas","Caquetá","Casanare","Cauca","Cesar","Chocó","Córdoba","Cundinamarca",
  "Guainía","Guaviare","Huila","La Guajira","Magdalena","Meta","Nariño",
  "Norte de Santander","Putumayo","Quindío","Risaralda","San Andrés y Providencia",
  "Santander","Sucre","Tolima","Valle del Cauca","Vaupés","Vichada",
];

function LocationSelects({ departamento, ciudad, onDepto, onCiudad, disabled }) {
  const inputStyle = {
    width: "100%", border: "1.5px solid #e0e0e0", borderRadius: 9,
    padding: "9px 11px", fontSize: 13, outline: "none",
    background: disabled ? "#fafafa" : "white",
    fontFamily: "inherit", color: "#1a1a1a", boxSizing: "border-box",
    pointerEvents: disabled ? "none" : "auto",
  };
  const selStyle = { ...inputStyle, appearance: "none", paddingRight: 32 };
  const arrow = (
    <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="2.5"><polyline points="6 9 12 15 18 9" /></svg>
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      <div className="form-group">
        <label className="form-label">Departamento</label>
        <div style={{ position: "relative" }}>
          <select value={departamento || ""} onChange={e => onDepto(e.target.value)}
            style={selStyle} disabled={disabled}>
            <option value="">— Seleccionar —</option>
            {DEPARTAMENTOS_CO.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          {arrow}
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">Ciudad / Municipio</label>
        <input
          type="text"
          value={ciudad || ""}
          onChange={e => onCiudad(e.target.value)}
          placeholder="Ej: Medellín, Bogotá…"
          style={inputStyle}
          disabled={disabled}
        />
      </div>
    </div>
  );
}

/* ── Vista de sólo lectura — diseño compacto con contexto ── */
function VistaProveedor({ proveedor, onClose }) {
  const { responsable, celular, correo, direccion, departamento, ciudad,
          totalCompras, ultimaCompraFecha, ultimaCompraEstado, insumosProvistos } = proveedor;

  const ubicacion = [direccion, ciudad, departamento].filter(Boolean).join(", ");
  const telRaw    = (celular || "").replace(/\s/g, "");

  return (
    <div className="modal-overlay">
      <div className="modal-card" style={{ maxWidth: 460 }} onClick={e => e.stopPropagation()}>

        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Proveedores</p>
            <h2 className="modal-header__title">Detalles del Proveedor</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Cabecera del proveedor */}
          <div style={{ display: "flex", alignItems: "center", gap: 14,
                        padding: "12px 14px", background: "#f1f8f1",
                        border: "1.5px solid #c8e6c9", borderRadius: 12 }}>
            <div className="prov-avatar" style={{ width: 44, height: 44, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}><Building2 size={22} /></div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 15, color: "#1a1a1a" }}>{responsable}</div>
              <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2 }}>ID: {proveedor.id}</div>
            </div>
          </div>

          {/* Contacto — tappable */}
          <div>
            <p className="section-label" style={{ margin: "0 0 8px" }}>Contacto</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {/* Con indicativo: sin el 57, wa.me contesta que el número no
                  existe. Uno que no se entiende va escrito, sin enlace. */}
              {!celular
                ? <span className="prov-contact-empty">Sin teléfono</span>
                : enlaceWhatsApp(celular)
                ? <a href={enlaceWhatsApp(celular)} className="prov-contact-link prov-contact-link--tel" target="_blank" rel="noopener noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Phone size={13} /> {celular}</a>
                : <span className="prov-contact-link prov-contact-link--tel" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Phone size={13} /> {celular}</span>
              }
              {correo
                ? <a href={`mailto:${correo}`} className="prov-contact-link prov-contact-link--mail" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Mail size={13} /> {correo}</a>
                : <span className="prov-contact-empty">Sin correo</span>
              }
            </div>
          </div>

          {/* Ubicación */}
          {ubicacion && (
            <div>
              <p className="section-label" style={{ margin: "0 0 6px" }}>Ubicación</p>
              <span style={{ fontSize: 13, color: "#424242", display: "inline-flex", alignItems: "center", gap: 4 }}><MapPin size={13} /> {ubicacion}</span>
            </div>
          )}

          {/* Actividad */}
          <div>
            <p className="section-label" style={{ margin: "0 0 8px" }}>Actividad</p>
            <div style={{ display: "flex", gap: 10 }}>
              <div className="prov-stat-card">
                <span className="prov-stat-card__num">{totalCompras}</span>
                <span className="prov-stat-card__label">Compras</span>
              </div>
              <div className="prov-stat-card" style={{ flex: 2 }}>
                <span className="prov-stat-card__num" style={{ fontSize: 13 }}>
                  {fmtFecha(ultimaCompraFecha) ?? "—"}
                </span>
                <span className="prov-stat-card__label">
                  Última compra{ultimaCompraEstado ? ` · ${ultimaCompraEstado}` : ""}
                </span>
              </div>
            </div>
          </div>

          {/* Insumos que provee */}
          <div>
            <p className="section-label" style={{ margin: "0 0 8px" }}>Insumos que provee</p>
            {insumosProvistos.length > 0
              ? <div className="prov-chips">
                  {insumosProvistos.map(n => (
                    <span key={n} className="prov-chip">{n}</span>
                  ))}
                </div>
              : <span className="prov-chip prov-chip--empty">Sin compras registradas</span>
            }
          </div>

        </div>

        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

export default function EditarProveedor({ proveedor, mode = "edit", onClose, onSave }) {
  const isView = mode === "view";

  if (isView) return <VistaProveedor proveedor={proveedor} onClose={onClose} />;

  const [form,   setForm]   = useState({
    nit:          "",
    responsable:  "",
    celular:      "",
    correo:       "",
    direccion:    "",
    departamento: "",
    ciudad:       "",
    ...proveedor,
  });
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  // Instantánea del formulario al abrir, para detectar "guardar sin cambios".
  // `proveedor` es un prop estable durante la vida del modal → const simple.
  const snapshot = (f) => JSON.stringify({
    nit:          (f.nit          || "").trim(),
    responsable:  (f.responsable  || "").trim(),
    celular:      (f.celular      || "").replace(/\D/g, ""),
    correo:       (f.correo       || "").trim(),
    direccion:    (f.direccion    || "").trim(),
    departamento: (f.departamento || "").trim(),
    ciudad:       (f.ciudad       || "").trim(),
  });
  const snapshotInicial = snapshot(proveedor || {});

  const set = (k, v) => {
    setForm(f => ({ ...f, [k]: v }));
    let err = "";
    if (k === "responsable" && !v.trim()) err = "Campo obligatorio";
    if (k === "celular" && v.trim() && v.replace(/\D/g, "").length !== 10)
      err = "El celular debe tener 10 dígitos";
    if (k === "correo") {
      if (v.trim() && !/\S+@\S+\.\S+/.test(v)) err = "Correo inválido";
    }
    if (k === "direccion" && v.trim() && !esUbicacionValida(v))
      err = "La dirección debe tener letras y números (mín. 5 caracteres)";
    setErrors(e => ({ ...e, [k]: err }));
  };

  const validate = () => {
    const e = {};
    if (!form.responsable?.trim()) e.responsable = "Campo obligatorio";
    if (form.celular?.trim() && form.celular.replace(/\D/g, "").length !== 10) e.celular = "El celular debe tener 10 dígitos";
    if (form.correo?.trim() && !/\S+@\S+\.\S+/.test(form.correo)) e.correo = "Correo inválido";
    if (form.direccion?.trim() && !esUbicacionValida(form.direccion))
      e.direccion = "La dirección debe tener letras y números (mín. 5 caracteres)";
    return e;
  };

  const handleSave = async () => {
    const e = validate();
    if (Object.keys(e).length) { setErrors(e); return; }
    if (snapshot(form) === snapshotInicial) { onSave({ sinCambios: true }); return; }
    setSaving(true);
    try {
      await onSave({
        NIT:          form.nit?.trim()  || undefined,
        Responsable:  form.responsable.trim(),
        Direccion:    form.direccion    || undefined,
        Municipio:    form.ciudad       || undefined,
        Departamento: form.departamento || undefined,
        Telefono:     form.celular      || undefined,
        Correo:       form.correo       || undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  const renderField = (k, label, type = "text", placeholder = "") => (
    <div className="form-group" key={k}>
      <label className="form-label">{label}{k === "responsable" && <span className="required"> *</span>}</label>
      <input
        className={`field-input${errors[k] ? " error" : ""}`}
        type={type}
        value={form[k] || ""}
        onChange={e => set(k, k === "celular" ? fmtTel(e.target.value) : e.target.value)}
        placeholder={placeholder}
      />
      {errors[k] && <span className="field-error">{errors[k]}</span>}
    </div>
  );

  return (
    <div className="modal-overlay">
      <div className="modal-card" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>

        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Proveedores</p>
            <h2 className="modal-header__title">Editar Proveedor</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body">
          <p className="section-label" style={{ marginTop: 0 }}>Identificación</p>
          {renderField("responsable", "Nombre / Razón Social", "text", "Ej: Juan García")}
          {renderField("nit", "NIT", "text", "Ej: 900.123.456-1")}

          <p className="section-label">Contacto</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {renderField("celular", "Celular", "text", "300 000 0000")}
            {renderField("correo",  "Correo electrónico", "email", "correo@empresa.com")}
          </div>

          <p className="section-label">Ubicación</p>
          {renderField("direccion", "Dirección", "text", "Ej: Cra 5 #12-34")}
          <LocationSelects
            departamento={form.departamento}
            ciudad={form.ciudad}
            onDepto={v => set("departamento", v)}
            onCiudad={v => set("ciudad", v)}
            disabled={false}
          />
        </div>

        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn-save" onClick={handleSave} disabled={saving}>
            {saving ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>
      </div>
    </div>
  );
}
