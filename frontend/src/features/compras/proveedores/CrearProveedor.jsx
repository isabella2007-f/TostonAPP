import { useState, useRef, useEffect } from "react";
import { X, Check, Search } from "lucide-react";
import { esUbicacionValida } from "../../../utils/inputFilters";
import { DEPARTAMENTOS, getCiudades } from "../../../utils/departamentosYCiudades";
import "./Proveedores.css";

const fmtTel = raw => {
  if (!raw || typeof raw !== "string") return "";
  const d = raw.replace(/\D/g, "").slice(0, 10);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)} ${d.slice(3)}`;
  return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
};

const STEPS = ["Identificación", "Contacto y Ubicación"];

function StepsBar({ current }) {
  return (
    <div className="wizard-steps-bar" style={{ padding: "0 24px" }}>
      {STEPS.map((label, i) => {
        const idx    = i + 1;
        const done   = idx < current;
        const active = idx === current;
        return (
          <div key={label} className="wizard-step-item" style={{ flex: 1 }}>
            <div className={`wizard-step-circle${done ? " done" : active ? " active" : ""}`}>
              {done ? <Check size={13} /> : idx}
            </div>
            <span className={`wizard-step-label${active ? " active" : done ? " done" : ""}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`wizard-step-line${done ? " done" : ""}`} style={{ flex: 1 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function SearchableSelect({ value, onChange, options, placeholder = "— Seleccionar —", error, disabled }) {
  const [open,  setOpen]  = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef();

  useEffect(() => {
    const handler = e => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = options.filter(opt =>
    opt.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        className={`field-input${error ? " error" : ""}`}
        style={{
          textAlign: "left",
          cursor: disabled ? "not-allowed" : "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          opacity: disabled ? 0.6 : 1,
          width: "100%",
        }}
        onClick={() => { if (!disabled) setOpen(o => !o); }}
      >
        <span style={{
          color: value ? "inherit" : "#aaa",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontSize: 13,
        }}>
          {value || placeholder}
        </span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="2.5"
          style={{ flexShrink: 0, marginLeft: 6, transform: open ? "rotate(180deg)" : "none", transition: "transform .15s" }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0,
          right: 0,
          zIndex: 1000,
          background: "var(--bg-card, #fff)",
          border: "1px solid var(--border-color, #e0e0e0)",
          borderRadius: 8,
          boxShadow: "0 4px 20px rgba(0,0,0,0.14)",
          overflow: "hidden",
        }}>
          <div style={{ padding: "8px 8px 4px" }}>
            <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
              <Search size={13} style={{ position: "absolute", left: 8, color: "#999", pointerEvents: "none" }} />
              <input
                autoFocus
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Buscar..."
                style={{
                  width: "100%",
                  padding: "6px 8px 6px 28px",
                  border: "1px solid var(--border-color, #e0e0e0)",
                  borderRadius: 6,
                  fontSize: 13,
                  outline: "none",
                  boxSizing: "border-box",
                  background: "var(--bg-input, #f5f5f5)",
                  color: "inherit",
                }}
              />
            </div>
          </div>
          <div style={{ maxHeight: 180, overflowY: "auto" }}>
            {filtered.length === 0 ? (
              <div style={{ padding: "10px 12px", color: "#999", fontSize: 13 }}>Sin resultados</div>
            ) : filtered.map(opt => (
              <button
                key={opt}
                type="button"
                onClick={() => { onChange(opt); setOpen(false); setQuery(""); }}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 12px",
                  fontSize: 13,
                  border: "none",
                  borderBottom: "1px solid var(--border-color, #f0f0f0)",
                  background: opt === value ? "var(--accent-light, #e8f5e9)" : "transparent",
                  cursor: "pointer",
                  color: "inherit",
                  fontWeight: opt === value ? 600 : 400,
                }}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LocationSelects({ departamento, ciudad, onDepto, onCiudad, errDepto, errCiudad }) {
  const ciudades = getCiudades(departamento);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      <div className="form-group">
        <label className="form-label">Departamento <span className="required">*</span></label>
        <SearchableSelect
          value={departamento}
          onChange={onDepto}
          options={DEPARTAMENTOS}
          placeholder="— Seleccionar —"
          error={errDepto}
        />
        {errDepto && <span className="field-error">{errDepto}</span>}
      </div>

      <div className="form-group">
        <label className="form-label">Ciudad / Municipio <span className="required">*</span></label>
        <SearchableSelect
          value={ciudad}
          onChange={onCiudad}
          options={ciudades}
          placeholder={departamento ? "— Seleccionar —" : "Elige depto. primero"}
          error={errCiudad}
          disabled={!departamento}
        />
        {errCiudad && <span className="field-error">{errCiudad}</span>}
      </div>
    </div>
  );
}

function FieldText({ label, value, onChange, error, type = "text", placeholder = "", required }) {
  return (
    <div className="form-group">
      <label className="form-label">{label}{required && <span className="required"> *</span>}</label>
      <input
        className={`field-input${error ? " error" : ""}`}
        type={type}
        value={value || ""}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

export default function CrearProveedor({ onClose, onSave }) {
  const [form, setForm] = useState({
    tipo:         "natural",
    nit:          "",
    responsable:  "",
    celular:      "",
    correo:       "",
    direccion:    "",
    departamento: "",
    ciudad:       "",
  });
  const [errors,  setErrors]  = useState({});
  const [saving,  setSaving]  = useState(false);
  const [step,    setStep]    = useState(1);

  const set = (k, v) => {
    setForm(f => {
      const next = { ...f, [k]: v };
      if (k === "departamento") next.ciudad = "";
      return next;
    });

    if (k === "departamento") {
      setErrors(e => ({ ...e, departamento: v ? "" : "Selecciona un departamento", ciudad: "" }));
      return;
    }

    let err = "";
    if (k === "responsable" && !v.trim()) err = "El nombre/razón social es obligatorio";
    if (k === "celular") {
      if (!v.trim()) err = "El celular es obligatorio";
      else if (v.replace(/\D/g, "").length !== 10) err = "El celular debe tener 10 dígitos";
    }
    if (k === "correo") {
      if (!v.trim()) err = "El correo es obligatorio";
      else if (!/\S+@\S+\.\S+/.test(v)) err = "Formato de correo inválido";
    }
    if (k === "ciudad" && !v) err = "Selecciona una ciudad";
    if (k === "direccion" && v.trim() && !esUbicacionValida(v))
      err = "La dirección debe tener letras y números (mín. 5 caracteres)";
    setErrors(e => ({ ...e, [k]: err }));
  };

  const labelResponsable = form.tipo === "juridica" ? "Razón Social" : "Nombre del responsable";

  const validateStep = (s) => {
    const e = {};
    if (s === 1) {
      if (!form.responsable.trim()) e.responsable = "El nombre/razón social es obligatorio";
    }
    if (s === 2) {
      if (!form.celular.trim()) e.celular = "El celular es obligatorio";
      else if (form.celular.replace(/\D/g, "").length !== 10) e.celular = "El celular debe tener 10 dígitos";
      if (!form.correo.trim()) e.correo = "El correo es obligatorio";
      else if (!/\S+@\S+\.\S+/.test(form.correo)) e.correo = "Formato de correo inválido";
      if (!form.departamento) e.departamento = "Selecciona un departamento";
      if (!form.ciudad)       e.ciudad       = "Selecciona una ciudad";
      if (form.direccion?.trim() && !esUbicacionValida(form.direccion))
        e.direccion = "La dirección debe tener letras y números (mín. 5 caracteres)";
    }
    return e;
  };

  const handleNext = () => {
    const e = validateStep(step);
    if (Object.keys(e).length) { setErrors(e); return; }
    setStep(s => s + 1);
  };

  const handleSave = async () => {
    const e = { ...validateStep(1), ...validateStep(2) };
    if (Object.keys(e).length) { setErrors(e); return; }
    setSaving(true);
    try {
      await onSave({
        Sujeto_Derecho: form.tipo === "juridica" ? 2 : 1,
        NIT:            form.nit.trim()  || undefined,
        Responsable:    form.responsable.trim(),
        Direccion:      form.direccion?.trim() || undefined,
        Municipio:      form.ciudad       || undefined,
        Departamento:   form.departamento || undefined,
        Telefono:       form.celular ? form.celular.replace(/\D/g, "") : undefined,
        Correo:         form.correo       || undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>

        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Proveedores</p>
            <h2 className="modal-header__title">Nuevo Proveedor</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div style={{ padding: "16px 24px 0" }}>
          <StepsBar current={step} />
        </div>

        <div className="modal-body" style={{ minHeight: 220 }}>

          {step === 1 && (
            <>
              <p className="section-label" style={{ marginTop: 0 }}>Datos de identificación</p>

              <div className="form-group">
                <label className="form-label">Tipo de persona <span className="required">*</span></label>
                <div style={{ position: "relative" }}>
                  <select
                    className="field-input"
                    style={{ appearance: "none", paddingRight: 32 }}
                    value={form.tipo}
                    onChange={e => set("tipo", e.target.value)}
                  >
                    <option value="natural">Persona Natural</option>
                    <option value="juridica">Persona Jurídica</option>
                  </select>
                  <div style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888" strokeWidth="2.5"><polyline points="6 9 12 15 18 9" /></svg>
                  </div>
                </div>
              </div>

              <FieldText
                label={labelResponsable}
                value={form.responsable}
                onChange={v => set("responsable", v)}
                error={errors.responsable}
                placeholder={form.tipo === "juridica" ? "Ej: Distribuidora XYZ S.A.S." : "Ej: Juan García"}
                required
              />
              <FieldText
                label="NIT"
                value={form.nit}
                onChange={v => set("nit", v)}
                error={errors.nit}
                placeholder="Ej: 900.123.456-1"
              />
            </>
          )}

          {step === 2 && (
            <>
              <p className="section-label" style={{ marginTop: 0 }}>Contacto</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <FieldText
                  label="Celular"
                  value={form.celular}
                  onChange={v => set("celular", fmtTel(v))}
                  error={errors.celular}
                  placeholder="300 000 0000"
                  required
                />
                <FieldText
                  label="Correo electrónico"
                  value={form.correo}
                  onChange={v => set("correo", v)}
                  error={errors.correo}
                  type="email"
                  placeholder="correo@empresa.com"
                  required
                />
              </div>

              <p className="section-label">Ubicación</p>
              <LocationSelects
                departamento={form.departamento}
                ciudad={form.ciudad}
                onDepto={v => set("departamento", v)}
                onCiudad={v => set("ciudad", v)}
                errDepto={errors.departamento}
                errCiudad={errors.ciudad}
              />
              <FieldText
                label="Dirección (opcional)"
                value={form.direccion}
                onChange={v => set("direccion", v)}
                error={errors.direccion}
                placeholder="Ej: Cra 5 #12-34"
              />
            </>
          )}
        </div>

        <div className="modal-footer">
          {step > 1
            ? <button className="btn-ghost" onClick={() => setStep(1)}>← Atrás</button>
            : <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          }
          <div style={{ display: "flex", gap: 10 }}>
            {step < 2
              ? <button className="btn-save" onClick={handleNext}>Siguiente →</button>
              : <button className="btn-save" onClick={handleSave} disabled={saving}>
                  {saving ? "Guardando…" : "Crear proveedor"}
                </button>
            }
          </div>
        </div>
      </div>
    </div>
  );
}
