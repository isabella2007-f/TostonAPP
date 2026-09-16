import { useState, useEffect, useRef } from "react";
import { Eye, Save, RotateCcw, CheckCircle2, Info, Lock, Clock3, MapPin } from "lucide-react";
import MapaSelectorAdmin from "./MapaSelectorAdmin";
import {
  getLandingConfig,
  saveLandingConfig,
  resetLandingConfig,
  LANDING_DEFAULTS,
} from "../../../services/landingConfigService";
import { getUser } from "../../../services/authService";

const FIELDS = [
  {
    group: "Hero principal",
    fields: [
      { key: "heroBadge",       label: "Badge (etiqueta pequeña)",  type: "text",     placeholder: LANDING_DEFAULTS.heroBadge },
      { key: "heroTitle",       label: "Título principal",           type: "text",     placeholder: LANDING_DEFAULTS.heroTitle },
      { key: "heroDescription", label: "Descripción del hero",       type: "textarea", placeholder: LANDING_DEFAULTS.heroDescription },
    ],
  },
  {
    group: "Sección Nosotros",
    fields: [
      { key: "historyTitle",       label: "Título",       type: "text",     placeholder: LANDING_DEFAULTS.historyTitle },
      { key: "historyDescription", label: "Descripción",  type: "textarea", placeholder: LANDING_DEFAULTS.historyDescription },
    ],
  },
  {
    group: "CTA (llamada a la acción)",
    fields: [
      { key: "ctaTitle",       label: "Título CTA",       type: "text",     placeholder: LANDING_DEFAULTS.ctaTitle },
      { key: "ctaDescription", label: "Descripción CTA",  type: "textarea", placeholder: LANDING_DEFAULTS.ctaDescription },
    ],
  },
  {
    group: "Información de contacto",
    fields: [
      { key: "contactPhone1",          label: "Teléfono 1",             type: "text", placeholder: LANDING_DEFAULTS.contactPhone1 },
      { key: "contactPhone2",          label: "Teléfono 2",             type: "text", placeholder: LANDING_DEFAULTS.contactPhone2 },
      { key: "contactEmail",           label: "Correo de contacto",     type: "text", placeholder: "contacto@tostonapp.com" },
      { key: "contactAddressLine",     label: "Dirección",              type: "text", placeholder: LANDING_DEFAULTS.contactAddressLine },
      { key: "contactCity",            label: "Ciudad y país",          type: "text", placeholder: LANDING_DEFAULTS.contactCity },
      { key: "contactInstagramHandle", label: "Instagram (usuario)",    type: "text", placeholder: LANDING_DEFAULTS.contactInstagramHandle },
      { key: "contactInstagramUrl",    label: "Instagram (enlace URL)", type: "text", placeholder: LANDING_DEFAULTS.contactInstagramUrl },
    ],
  },
];

const DIAS = [
  { iso: 1, label: "Lun" }, { iso: 2, label: "Mar" }, { iso: 3, label: "Mié" },
  { iso: 4, label: "Jue" }, { iso: 5, label: "Vie" }, { iso: 6, label: "Sáb" },
  { iso: 7, label: "Dom" },
];

const snapshot = (f) => JSON.stringify(f);

const esAdminUser = (u) =>
  !!u && (u.rol === "Admin" || String(u.id ?? u.cedula ?? "") === "1");

export default function EditarLanding() {
  const [form,       setForm]       = useState({ ...LANDING_DEFAULTS });
  const [saved,      setSaved]      = useState(false);
  const [saveError,  setSaveError]  = useState('');
  const [sinCambios, setSinCambios] = useState(false);
  const [confirm,    setConfirm]    = useState(false);
  const [loading,    setLoading]    = useState(true);
  const [isSaving,   setIsSaving]   = useState(false);
  const snapshotGuardado = useRef(snapshot({ ...LANDING_DEFAULTS }));
  const esAdmin = esAdminUser(getUser());

  useEffect(() => {
    getLandingConfig().then(config => {
      setForm(config);
      snapshotGuardado.current = snapshot(config);
      setLoading(false);
    });
  }, []);

  const handleChange = (key, value) => {
    setForm(prev => ({ ...prev, [key]: value }));
    setSaved(false);
    setSinCambios(false);
  };

  const diasSet = new Set(
    String(form.diasAtencion || "").split(",").map(s => parseInt(s, 10)).filter(Boolean)
  );

  const toggleDia = (iso) => {
    const next = new Set(diasSet);
    next.has(iso) ? next.delete(iso) : next.add(iso);
    handleChange("diasAtencion", [...next].sort((a, b) => a - b).join(","));
  };

  const handleSave = async () => {
    if (snapshot(form) === snapshotGuardado.current) {
      setSinCambios(true);
      setSaveError('');
      setTimeout(() => setSinCambios(false), 3000);
      return;
    }

    setIsSaving(true);
    setSaveError('');

    try {
      await saveLandingConfig(form);
      snapshotGuardado.current = snapshot(form);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setSaveError(err?.message || "No se pudieron guardar los cambios.");
      setSaved(false);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm) { setConfirm(true); return; }
    const defaults = await resetLandingConfig();
    setForm(defaults);
    snapshotGuardado.current = snapshot(defaults);
    setConfirm(false);
    setSaved(false);
    setSinCambios(false);
  };

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-8">

      {/* Cabecera */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-black text-[#1b5e20]">Editar Landing Page</h1>
          <p className="text-sm text-gray-500 mt-1">Los cambios se aplican inmediatamente para todos los visitantes.</p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/"
            target="_blank"
            rel="noopener noreferrer"
            data-tooltip="Abrir la landing page en una nueva pestaña"
            className="flex items-center gap-2 px-4 py-2 bg-[#e8f5e9] text-[#1b5e20] rounded-xl font-bold text-sm hover:bg-[#c8e6c9] transition-colors"
          >
            <Eye className="w-4 h-4" />
            Ver landing
          </a>
          <button
            onClick={handleReset}
            data-tooltip={confirm ? "Confirmar restauración de valores predeterminados" : "Restaurar textos predeterminados"}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl font-bold text-sm transition-colors ${
              confirm
                ? "bg-red-100 text-red-700 hover:bg-red-200"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            <RotateCcw className="w-4 h-4" />
            {confirm ? "¿Seguro? Confirmar" : "Restaurar defecto"}
          </button>
          {confirm && (
            <button
              onClick={() => setConfirm(false)}
              data-tooltip="Cancelar restauración"
              className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700"
            >
              Cancelar
            </button>
          )}
        </div>
      </div>

      {/* Toast guardado */}
      {saved && (
        <div className="flex items-center gap-3 px-5 py-4 bg-[#e8f5e9] border border-[#a5d6a7] rounded-2xl text-[#1b5e20] font-bold">
          <CheckCircle2 className="w-5 h-5 text-[#4caf50]" />
          Cambios guardados correctamente
        </div>
      )}

      {saveError && (
        <div className="flex items-center gap-3 px-5 py-4 bg-red-50 border border-red-200 rounded-2xl text-red-700 font-bold">
          <Info className="w-5 h-5 text-red-500" />
          {saveError}
        </div>
      )}

      {/* Toast sin cambios */}
      {sinCambios && (
        <div className="flex items-center gap-3 px-5 py-4 bg-gray-100 border border-gray-200 rounded-2xl text-gray-600 font-bold">
          <Info className="w-5 h-5 text-gray-400" />
          No se hicieron cambios
        </div>
      )}

      {/* Grupos de campos de texto */}
      {FIELDS.map(({ group, fields }) => (
        <section key={group} className="bg-white rounded-2xl border border-[#e8f5e9] overflow-hidden shadow-sm">
          <div className="px-6 py-4 bg-[#f7faf8] border-b border-[#e8f5e9]">
            <h2 className="font-black text-[#1b5e20] text-sm uppercase tracking-wider">{group}</h2>
          </div>
          <div className="p-6 space-y-5">
            {fields.map(({ key, label, type, placeholder }) => (
              <div key={key}>
                <label className="block text-sm font-bold text-gray-700 mb-1.5">{label}</label>
                {type === "textarea" ? (
                  <textarea
                    rows={3}
                    value={form[key] ?? ""}
                    onChange={e => handleChange(key, e.target.value)}
                    placeholder={placeholder}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:border-[#4caf50] focus:ring-2 focus:ring-[#4caf50]/20 text-sm resize-none transition"
                  />
                ) : (
                  <input
                    type="text"
                    value={form[key] ?? ""}
                    onChange={e => handleChange(key, e.target.value)}
                    placeholder={placeholder}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:border-[#4caf50] focus:ring-2 focus:ring-[#4caf50]/20 text-sm transition"
                  />
                )}
                <p className="text-xs text-gray-400 mt-1">Por defecto: {placeholder}</p>
              </div>
            ))}
          </div>
        </section>
      ))}

      {/* Ubicación en el mapa */}
      <section className="bg-white rounded-2xl border border-[#e8f5e9] overflow-hidden shadow-sm">
        <div className="px-6 py-4 bg-[#f7faf8] border-b border-[#e8f5e9] flex items-center gap-2">
          <MapPin className="w-4 h-4 text-[#1b5e20]" />
          <h2 className="font-black text-[#1b5e20] text-sm uppercase tracking-wider">Ubicación en el mapa</h2>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-xs text-gray-500">
            Busca la dirección para colocar el pin automáticamente. Si el punto queda
            desplazado, arrástralo o haz clic en la posición correcta del mapa.
            Guarda los cambios para que el pie de página use ese punto exacto.
          </p>
          <MapaSelectorAdmin
            lat={form.mapLat}
            lng={form.mapLng}
            address={form.contactAddressLine}
            city={form.contactCity}
            onChange={(lat, lng) => {
              handleChange("mapLat", lat);
              handleChange("mapLng", lng);
            }}
          />
        </div>
      </section>

      {/* Horario de atención — solo admin */}
      <section className="bg-white rounded-2xl border border-[#e8f5e9] overflow-hidden shadow-sm">
        <div className="px-6 py-4 bg-[#f7faf8] border-b border-[#e8f5e9] flex items-center gap-2">
          <Clock3 className="w-4 h-4 text-[#1b5e20]" />
          <h2 className="font-black text-[#1b5e20] text-sm uppercase tracking-wider">Horario de atención</h2>
          {!esAdmin && (
            <span className="ml-auto flex items-center gap-1 text-[11px] font-bold text-gray-400">
              <Lock className="w-3 h-3" /> Solo un administrador puede cambiarlo
            </span>
          )}
        </div>
        <div className="p-6 space-y-5">
          <p className="text-xs text-gray-500">
            Define cuándo se atienden los pedidos. Fuera de este horario, al cliente se le
            avisa que su pedido no se atenderá hasta volver a abrir.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-1.5">Hora de apertura</label>
              <input
                type="time"
                disabled={!esAdmin}
                value={form.horaApertura ?? "08:00"}
                onChange={e => handleChange("horaApertura", e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:border-[#4caf50] focus:ring-2 focus:ring-[#4caf50]/20 text-sm transition disabled:bg-gray-50 disabled:text-gray-400"
              />
            </div>
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-1.5">Hora de cierre</label>
              <input
                type="time"
                disabled={!esAdmin}
                value={form.horaCierre ?? "20:00"}
                onChange={e => handleChange("horaCierre", e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:border-[#4caf50] focus:ring-2 focus:ring-[#4caf50]/20 text-sm transition disabled:bg-gray-50 disabled:text-gray-400"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-2">Días que se atiende</label>
            <div className="flex flex-wrap gap-2">
              {DIAS.map(({ iso, label }) => {
                const on = diasSet.has(iso);
                return (
                  <button
                    key={iso}
                    type="button"
                    disabled={!esAdmin}
                    onClick={() => toggleDia(iso)}
                    className={`px-4 py-2 rounded-xl text-sm font-black transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${
                      on ? "bg-[#1b5e20] text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* Mínimo para domicilio — solo admin */}
      <section className="bg-white rounded-2xl border border-[#e8f5e9] overflow-hidden shadow-sm">
        <div className="px-6 py-4 bg-[#f7faf8] border-b border-[#e8f5e9] flex items-center gap-2">
          <h2 className="font-black text-[#1b5e20] text-sm uppercase tracking-wider">Mínimo para domicilio</h2>
          {!esAdmin && (
            <span className="ml-auto flex items-center gap-1 text-[11px] font-bold text-gray-400">
              <Lock className="w-3 h-3" /> Solo un administrador puede cambiarlo
            </span>
          )}
        </div>
        <div className="p-6 space-y-4">
          <p className="text-xs text-gray-500">
            Monto mínimo del pedido (sin contar el domicilio) para que el cliente pueda elegir entrega a domicilio.
            Escribe <strong>0</strong> para no exigir un mínimo.
          </p>
          <div>
            <label className="block text-sm font-bold text-gray-700 mb-1.5">Monto mínimo (COP)</label>
            <input
              type="number"
              min="0"
              step="1000"
              inputMode="numeric"
              disabled={!esAdmin}
              value={form.pedidoMinimo ?? 0}
              onChange={e => handleChange("pedidoMinimo", e.target.value === "" ? 0 : Number(e.target.value))}
              placeholder="0"
              className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:border-[#4caf50] focus:ring-2 focus:ring-[#4caf50]/20 text-sm transition disabled:bg-gray-50 disabled:text-gray-400"
            />
            {form.pedidoMinimo > 0 && (
              <p className="text-xs text-gray-400 mt-1">
                El cliente debe pedir al menos ${Number(form.pedidoMinimo).toLocaleString("es-CO")} COP para optar por domicilio.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Botón guardar fijo */}
      <div className="sticky bottom-0 bg-white/80 backdrop-blur-md border-t border-[#e8f5e9] -mx-6 px-6 py-4 flex justify-end">
        <button
          onClick={handleSave}
          disabled={loading || isSaving}
          data-tooltip="Guardar todos los cambios en la landing page"
          className="flex items-center gap-2 px-8 py-3 bg-[#1b5e20] text-white font-black rounded-2xl hover:bg-[#0d3300] transition-all shadow-lg active:scale-95 disabled:opacity-50"
        >
          <Save className={`w-4 h-4 ${isSaving ? 'animate-pulse' : ''}`} />
          {isSaving ? 'Guardando...' : 'Guardar cambios'}
        </button>
      </div>
    </div>
  );
}
