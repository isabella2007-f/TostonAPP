import { useState, useEffect, useRef } from "react";
import { esEmpleadoRepartidor } from "../../../utils/roles.js";
import { Navigate } from "react-router-dom";
import { formatCOP } from "../../../utils/formato";
import {
  Search, Bike, Package, CheckCircle2, XCircle, Clock,
  MapPin, AlertTriangle, AlertCircle, User, ShoppingBag, CreditCard, Calendar,
  Banknote, Building2, Scale, Eye, Globe, Zap, PenLine, FileText,
  Check, X, Ban, Navigation, ClipboardList, BarChart2, Truck, ChevronRight,
  ChevronDown, History,
  Utensils,
} from "lucide-react";
import { getDomicilios, asignarRepartidor, actualizarDomicilio, cambiarEstadoDomicilio, registrarPagoEfectivo } from "../../../services/domiciliosService.js";
import { getUsuarios, toggleEstadoUsuario } from "../../../services/usuariosService.js";
import { getUser } from "../../../services/authService.js";
import { esRolRepartidor, INICIO_REPARTIDOR } from "../../../utils/roles.js";
import { fmtFecha } from "../../../utils/dateUtils.js";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import {
  ESTADO_DOMICILIO, ESTADO_DOM_CONFIG, ESTADO_PAGO_LABEL, FILTRO_ESTADOS_DOM,
  bloqueoEntrega, cobroEfectivoPendiente, esDomicilioActivo, esPagoEfectivo, esPagoMixto, esPagoTransferencia,
  puedeReasignarse,
  transicionesDom,
} from "./estadosDomicilio";
import "./Domicilios.css";
import { montoACobrar } from "./estadosDomicilio";

function SkeletonRows({ cols = 9, rows = 5 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i}>
      {Array.from({ length: cols }).map((__, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

/* ─── Helpers ────────────────────────────────────────────── */
const fmt = formatCOP;

const PER_PAGE = 5;

// Estado del domicilio (entrega)
// Los estados y transiciones del domicilio viven en estadosDomicilio.js: antes
// esta pantalla ofrecía estados del PEDIDO (Confirmado, En preparación, Listo)
// que el backend interpretaba como "Entregado" al recibirlos.
const ESTADO_CONFIG = ESTADO_DOM_CONFIG;

const FILTER_OPTIONS = FILTRO_ESTADOS_DOM;

/* ─── Componentes pequeños ───────────────────────────────── */
/** Método de pago del pedido: el admin necesita saber si hay que cobrar. */
function MetodoPagoChip({ metodo }) {
  const texto = (metodo || "").trim();
  if (!texto) return <span style={{ fontSize: 11, color: "#bdbdbd" }}>—</span>;
  // El mixto se pregunta primero: es efectivo Y transferencia a la vez, así
  // que las dos preguntas de abajo le dirían que sí.
  const cfg = esPagoMixto(texto)
    ? { label: "Mixto",         icon: <Scale size={11} />,      dot: "#6a1b9a", bg: "#f3e5f5" }
    : esPagoEfectivo(texto)
      ? { label: "Efectivo",      icon: <Banknote size={11} />,   dot: "#2e7d32", bg: "#e8f5e9" }
      : esPagoTransferencia(texto)
        ? { label: "Transferencia", icon: <Building2 size={11} />, dot: "#1565c0", bg: "#e3f2fd" }
        : { label: texto,           icon: <CreditCard size={11} />, dot: "#616161", bg: "#f5f5f5" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "2px 7px", borderRadius: 4, fontSize: 11, fontWeight: 700,
      background: cfg.bg, color: cfg.dot, border: `1px solid ${cfg.dot}44`,
    }}>
      {cfg.icon}{cfg.label}
    </span>
  );
}

/** Estado del cobro (Ventas.Estado_Pago). */
function EstadoPagoChip({ estadoPago }) {
  const cfg = ESTADO_PAGO_LABEL[estadoPago] || null;
  if (!cfg) return null;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "2px 7px", borderRadius: 4, fontSize: 10.5, fontWeight: 700,
      background: cfg.bg, color: cfg.dot, border: `1px solid ${cfg.dot}44`,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.dot }} />
      {cfg.label}
    </span>
  );
}

function EstadoBadge({ estado, estadoId }) {
  const cfg = ESTADO_CONFIG[estadoId] || {
    dot: "#9e9e9e", bg: "#f5f5f5", border: "#e0e0e0",
    label: estado || estadoId, desc: "",
  };
  return (
    <span
      className="estado-badge"
      title={cfg.desc}
      style={{ background: cfg.bg, color: cfg.dot, borderColor: cfg.border }}
    >
      <span className="estado-badge__dot" style={{ background: cfg.dot }} />
      {cfg.label || estado || estadoId}
    </span>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  const bg =
    toast.type === "error" ? "#c62828" :
    toast.type === "warn"  ? "#e65100" :
    "#2e7d32";
  return (
    <div className="toast" style={{ background: bg }}>
      <span style={{ display: "flex", alignItems: "center" }}>
        {toast.type === "error" ? <X size={14} /> : toast.type === "warn" ? <AlertTriangle size={14} /> : <Check size={14} />}
      </span>
      {toast.message}
    </div>
  );
}


// Igual que en la app móvil: la búsqueda incluye municipio, departamento y país
// para que el geocoding no confunda direcciones repetidas entre ciudades.
const mapToGoogleMaps = (address, municipio = "", departamento = "") => {
  if (!address) return "https://www.google.com/maps";
  const partes = [address, municipio, departamento, "Colombia"]
    .map(p => (p || "").trim())
    .filter(Boolean);
  const query = encodeURIComponent(partes.join(", "));
  return `https://www.google.com/maps/search/?api=1&query=${query}`;
};

/* ── Exportar CSV ──────────────────────────────────────────────────────
   Tres cosas que el archivo anterior hacía mal:

   1. La columna "Domiciliario" leía `row.domiciliario`, un campo que el
      adaptador no arma nunca, así que TODAS las filas salían "Sin asignar".
      El nombre se resuelve igual que en la tabla, contra los empleados.
   2. Excel en español separa por ";" (el separador de lista del sistema).
      Con comas metía la fila entera en una sola celda. La marca "sep=" se
      lo dice explícitamente y el BOM evita leer "Dirección" como
      "DirecciÃ³n".
   3. Fechas y montos salían crudos ("2026-08-30T14:02:11", "22500.0").

   Las columnas siguen el mismo orden en que se leen en la tabla. */
const CSV_COLUMNAS = [
  { titulo: "Domicilio",            valor: (d) => d.numero },
  { titulo: "Pedido",               valor: (d) => (d.idVenta ? `V-${d.idVenta}` : "") },
  { titulo: "Cliente",              valor: (d) => d.cliente?.nombre },
  { titulo: "Teléfono",             valor: (d) => d.cliente?.telefono },
  { titulo: "Dirección",            valor: (d) => d.direccion_entrega },
  { titulo: "Municipio",            valor: (d) => d.municipio_entrega },
  { titulo: "Domiciliario",         valor: (d, nombre) => nombre(d) || "Sin asignar" },
  { titulo: "Estado de la entrega", valor: (d) => d.estado },
  { titulo: "Método de pago",       valor: (d) => d.metodo_pago },
  { titulo: "Estado del pago",      valor: (d) => ESTADO_PAGO_LABEL[d.estado_pago]?.label },
  { titulo: "Total",                valor: (d) => (d.total != null ? Math.round(d.total) : "") },
  { titulo: "Fecha del pedido",     valor: (d) => csvFecha(d.fecha_pedido) },
  { titulo: "Fecha de entrega",     valor: (d) => csvFecha(d.fecha_entrega_real) },
  { titulo: "Observaciones",        valor: (d) => d.obs_domicilio },
  { titulo: "Indicaciones del cliente", valor: (d) => d.indicaciones_cliente },
];

// fmtFecha devuelve "—" cuando no hay fecha; en una celda queda mejor vacía.
const csvFecha = (iso) => (iso ? fmtFecha(iso) : "");

const celdaCsv = (val) => {
  const txt = String(val ?? "").replace(/\r?\n/g, " ").trim();
  return `"${txt.replace(/"/g, '""')}"`;
};

const exportToCsv = (rows, nombreRepartidor) => {
  if (!rows || rows.length === 0) return false;
  const lineas = [
    "sep=;",
    CSV_COLUMNAS.map(c => celdaCsv(c.titulo)).join(";"),
    ...rows.map(d =>
      CSV_COLUMNAS.map(c => celdaCsv(c.valor(d, nombreRepartidor))).join(";")
    ),
  ];
  // El BOM es lo que hace que Excel lo abra como UTF-8.
  const blob = new Blob(["\uFEFF" + lineas.join("\r\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `domicilios-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // Revocar en el mismo tick corta la descarga en algunos navegadores.
  setTimeout(() => URL.revokeObjectURL(url), 0);
  return true;
};

/* ═══════════════════════════════════════════════════════════
   MODAL CONFIRMAR DESACTIVAR DOMICILIARIO
   ═══════════════════════════════════════════════════════════ */
function ModalConfirmarDesactivar({ usuario, pedidosActivos, onConfirm, onClose }) {
  return (
    <div className="modal-overlay">
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Advertencia</p>
            <h2 className="modal-header__title">Desactivar domiciliario</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body" style={{ overflow: "visible" }}>
          <div className="info-box info-box--warn">
            <span className="info-box__icon"><AlertTriangle size={14} /></span>
            <div className="info-box__text">
              <span className="info-box__label">
                {usuario.nombre} {usuario.apellidos} tiene {pedidosActivos.length}{" "}
                domicilio{pedidosActivos.length !== 1 ? "s" : ""} activo
                {pedidosActivos.length !== 1 ? "s" : ""}
              </span>
              Al desactivarlo, estos pedidos quedarán sin domiciliario asignado.
            </div>
          </div>

          {/* Lista de pedidos afectados */}
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6, maxHeight: 220, overflowY: "auto" }}>
            {pedidosActivos.map(p => (
              <div key={p.id} className="hist-pedido-row">
                <span className="hist-pedido-num">{p.numero}</span>
                <span className="hist-pedido-dir">{p.direccion_entrega}</span>
                <EstadoBadge estado={p.estado} estadoId={p.estadoId} />
                <span className="hist-pedido-fecha">{fmtFecha(p.fecha_pedido)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button
            className="btn-save"
            style={{ background: "#c62828", boxShadow: "0 3px 10px rgba(198,40,40,0.35)" }}
            onClick={onConfirm}
          >
            Desactivar de todas formas
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL REGISTRAR COBRO EN EFECTIVO
   Usa PATCH /domicilios/{id}/registrar-pago-efectivo (ya existente).
   Replica las validaciones del backend: monto exacto si se recibió,
   motivo de al menos 10 caracteres si no.
   ═══════════════════════════════════════════════════════════ */
function ModalRegistrarCobro({ pedido, saving, onClose, onConfirm }) {
  const [recibido, setRecibido] = useState(null);
  const [motivo,   setMotivo]   = useState("");
  const [error,    setError]    = useState(null);

  const handleConfirm = () => {
    if (recibido === null) {
      setError("Indica si recibiste el efectivo.");
      return;
    }
    if (recibido === false && motivo.trim().length < 10) {
      setError("Explica por qué no se recibió (mínimo 10 caracteres).");
      return;
    }
    setError(null);
    onConfirm(pedido, recibido, recibido ? montoACobrar(pedido) : null, recibido ? null : motivo.trim());
  };

  const opcion = (valor, icono, titulo, detalle, color) => {
    const activo = recibido === valor;
    return (
      <button
        type="button"
        onClick={() => { setRecibido(valor); setError(null); }}
        style={{
          display: "flex", alignItems: "center", gap: 12, width: "100%",
          padding: "12px 14px", borderRadius: 10, cursor: "pointer",
          textAlign: "left", background: activo ? `${color}14` : "#fff",
          border: `1.5px solid ${activo ? color : "#e0e0e0"}`,
        }}
      >
        <span style={{ fontSize: 22 }}>{icono}</span>
        <span>
          <span style={{ display: "block", fontSize: 13.5, fontWeight: 700, color: "#1a1a1a" }}>{titulo}</span>
          <span style={{ display: "block", fontSize: 11.5, color: "#757575", marginTop: 2 }}>{detalle}</span>
        </span>
      </button>
    );
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Domicilio {pedido.numero}</p>
            <h2 className="modal-header__title">Registrar cobro en efectivo</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div className="info-box" style={{ marginBottom: 14 }}>
            <span className="info-box__icon"><Banknote size={14} /></span>
            <span className="info-box__text">
              Total a cobrar en mano: <strong>{fmt(montoACobrar(pedido))}</strong>
            </span>
          </div>

          <div style={{ display: "grid", gap: 8 }}>
            {opcion(true,  <CheckCircle2 size={22} />, "Sí, se recibió completo",
                    `Se registra el monto exacto: ${fmt(montoACobrar(pedido))}`, "#2e7d32")}
            {opcion(false, <XCircle size={22} />, "No se recibió",
                    "Requiere explicar el motivo", "#c62828")}
          </div>

          {recibido === false && (
            <>
              <p className="section-label">Motivo</p>
              <textarea
                className="form-input"
                rows={3}
                value={motivo}
                onChange={e => { setMotivo(e.target.value); setError(null); }}
                placeholder="Ej: el cliente no tenía el efectivo completo al recibir"
                style={{ width: "100%", resize: "vertical" }}
              />
              <p style={{ fontSize: 11, color: motivo.trim().length < 10 ? "#c62828" : "#9e9e9e", marginTop: 4 }}>
                {motivo.trim().length}/10 caracteres mínimos
              </p>
            </>
          )}

          {error && (
            <div className="info-box info-box--warn" style={{ marginTop: 12 }}>
              <span className="info-box__icon"><AlertTriangle size={14} /></span>
              <span className="info-box__text">{error}</span>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose} disabled={saving}>Cancelar</button>
          <button className="btn-primary" onClick={handleConfirm} disabled={saving}>
            {saving ? "Registrando…" : "Registrar cobro"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL CAMBIAR ESTADO
   ═══════════════════════════════════════════════════════════ */
function ModalCambiarEstado({ pedido, esRepartidor = false, onClose, onSave }) {
  const opciones = transicionesDom(pedido.estadoId, esRepartidor);
  const [seleccion, setSeleccion] = useState(opciones[0]?.id ?? "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!seleccion) return;
    setSaving(true);
    try {
      await onSave(pedido.id, seleccion, pedido);
      onClose();
    } catch {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Domicilio</p>
            <h2 className="modal-header__title">Cambiar estado</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <p style={{ margin: "0 0 14px", fontSize: 13, color: "#616161" }}>
            Pedido: <strong>{pedido.numero}</strong> — Estado actual: <strong>{ESTADO_CONFIG[pedido.estadoId]?.label || pedido.estado}</strong>
          </p>
          {opciones.length === 0 ? (
            <p style={{ color: "#9e9e9e", fontSize: 13 }}>No hay transiciones disponibles para este estado.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {opciones.map(op => {
                const cfg = ESTADO_CONFIG[op.id] || {};
                return (
                  <button
                    key={op.id}
                    onClick={() => setSeleccion(op.id)}
                    style={{
                      padding: "12px 16px", borderRadius: 10, cursor: "pointer",
                      border: seleccion === op.id ? `2px solid ${cfg.dot || "#4caf50"}` : "1.5px solid #e0e0e0",
                      background: seleccion === op.id ? (cfg.bg || "#e8f5e9") : "#fafafa",
                      color: seleccion === op.id ? (cfg.dot || "#2e7d32") : "#616161",
                      fontWeight: 700, fontSize: 13, textAlign: "left",
                      display: "flex", alignItems: "center", gap: 8,
                    }}
                  >
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: cfg.dot || "#bdbdbd", flexShrink: 0 }} />
                    {op.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button
            className="btn-save"
            onClick={handleSave}
            disabled={saving || !seleccion || opciones.length === 0}
          >
            {saving ? "Guardando…" : "Confirmar"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL VER DETALLE — Side panel
   ═══════════════════════════════════════════════════════════ */
const NAV_VER = [
  { id: "cliente",      label: "Cliente",      Icon: User },
  { id: "direccion",    label: "Dirección",    Icon: MapPin },
  { id: "productos",    label: "Productos",    Icon: ShoppingBag },
  { id: "pago",         label: "Pago",         Icon: CreditCard },
  { id: "domiciliario", label: "Domiciliario", Icon: Bike },
  { id: "fechas",       label: "Fechas",       Icon: Calendar },
];

function ModalVerDomicilio({ pedido, emp, domicilios, onClose, onReasignar, onObservaciones }) {
  const [activeSection, setActiveSection] = useState("cliente");
  const activo = !["Entregado", "Cancelado"].includes(pedido.estado);
  const cfg = ESTADO_CONFIG[pedido.estadoId] || { dot: "#bdbdbd", label: pedido.estado, desc: "" };
  const pedidosAsignados = domicilios.filter(d => d.idEmpleado === emp?.id);
  const pendientes  = pedidosAsignados.filter(d => !["Entregado", "Cancelado"].includes(d.estado)).length;
  const enCamino    = pedidosAsignados.filter(d => d.estado === "En camino").length;
  const entregados  = pedidosAsignados.filter(d => d.estado === "Entregado").length;

  return (
    <div className="modal-overlay">
      <div
        className="modal-box modal-box--wide"
        onClick={e => e.stopPropagation()}
        style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}
      >
        {/* Header */}
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Domicilio</p>
            <h2 className="modal-header__title">{pedido.numero}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 6, fontSize: 11,
                fontWeight: 600, color: cfg.dot, marginBottom: 2
              }}>
                <span style={{
                  width: 10, height: 10, borderRadius: "50%",
                  background: cfg.dot, display: "inline-block"
                }} />
                {cfg.label}
              </div>
              <div style={{ fontSize: 11, color: "#999" }}>{cfg.desc}</div>
            </div>
            <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        {/* Side panel layout */}
        <div style={{ display: "flex" }}>

          {/* Nav lateral */}
          <nav style={{
            width: 150, borderRight: "1px solid #f0f0f0", background: "#fafdf9",
            display: "flex", flexDirection: "column", padding: "12px 0", flexShrink: 0,
          }}>
            <div style={{
              display: "flex", justifyContent: "center",
              marginBottom: 16, paddingBottom: 12, borderBottom: "1px solid #f0f0f0"
            }}>
              <div style={{
                width: 48, height: 48, borderRadius: "50%", background: "#e8f5e9",
                border: "1.5px solid #a5d6a7", display: "flex", alignItems: "center",
                justifyContent: "center", color: "#2e7d32",
              }}><Bike size={22} strokeWidth={1.5} /></div>
            </div>

            {NAV_VER.map(item => (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "10px 16px", border: "none",
                  borderLeft: activeSection === item.id ? "3px solid #2e7d32" : "3px solid transparent",
                  background: activeSection === item.id ? "#e8f5e9" : "transparent",
                  color: activeSection === item.id ? "#2e7d32" : "#757575",
                  fontWeight: activeSection === item.id ? 700 : 500,
                  fontSize: 13, cursor: "pointer", fontFamily: "inherit",
                  transition: "all 0.15s", textAlign: "left", width: "100%",
                }}
              >
                <item.Icon size={14} />
                {item.label}
              </button>
            ))}
          </nav>

          {/* Contenido */}
          <div style={{ flex: 1, padding: "20px 24px", overflowY: "auto", maxHeight: "calc(100vh - 300px)" }}>

            {/* ── Cliente ── */}
            {activeSection === "cliente" && (
              <>
                <p className="section-label" style={{ marginTop: 0 }}>Datos del cliente</p>
                <div className="form-grid-2">
                  <div>
                    <label className="form-label">Nombre</label>
                    <div className="field-input--disabled">{pedido.cliente?.nombre || "—"}</div>
                  </div>
                  <div>
                    <label className="form-label">Teléfono</label>
                    <div className="field-input--disabled">{pedido.cliente?.telefono || "—"}</div>
                  </div>
                </div>
                <div style={{ marginTop: 8 }}>
                  <label className="form-label">Total del pedido</label>
                  <div className="field-input--disabled" style={{ color: "#2e7d32", fontWeight: 700 }}>
                    {fmt(pedido.total)}
                  </div>
                </div>

                <p className="section-label">Estado del pedido</p>
                <div style={{
                  background: cfg.dot + "11",
                  border: `1px solid ${cfg.dot}33`,
                  borderRadius: 8,
                  padding: 12
                }}>
                  <div style={{
                    display: "flex", alignItems: "center", gap: 8,
                    marginBottom: 6, fontSize: 14, fontWeight: 700, color: cfg.dot
                  }}>
                    <span style={{ width: 12, height: 12, borderRadius: "50%", background: cfg.dot }} />
                    {cfg.label}
                  </div>
                  <div style={{ fontSize: 12, color: "#666" }}>
                    {cfg.desc || "Ver más información en las otras pestañas."}
                  </div>
                </div>
              </>
            )}

            {/* ── Dirección ── */}
            {activeSection === "direccion" && (
              <>
                <p className="section-label" style={{ marginTop: 0 }}>Dirección de entrega</p>
                <div className="info-box info-box--info">
                  <span className="info-box__icon"><MapPin size={14} /></span>
                  <span className="info-box__text">{pedido.direccion_entrega || "—"}</span>
                </div>
                {pedido.direccion_entrega && (
                  <a
                    className="link-button"
                    href={mapToGoogleMaps(pedido.direccion_entrega, pedido.municipio_entrega, pedido.departamento_entrega)}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ marginTop: 12, display: "inline-block", fontSize: 13 }}
                  >Abrir en Google Maps</a>
                )}
                {/* Indicaciones que el cliente guardó en su perfil (referencia del
                    punto de entrega). Es un dato distinto de las observaciones
                    de esta entrega, igual que en la app móvil. */}
                {pedido.indicaciones_cliente && (
                  <>
                    <p className="section-label">Indicaciones del cliente</p>
                    <div className="info-box">
                      <span className="info-box__icon"><Navigation size={14} /></span>
                      <span className="info-box__text">{pedido.indicaciones_cliente}</span>
                    </div>
                  </>
                )}
                {pedido.obs_domicilio ? (
                  <>
                    <p className="section-label">Observaciones de la entrega</p>
                    <div className="info-box info-box--warn">
                      <span className="info-box__icon"><PenLine size={14} /></span>
                      <span className="info-box__text">{pedido.obs_domicilio}</span>
                    </div>
                  </>
                ) : (
                  <p style={{ fontSize: 12, color: "#bdbdbd", marginTop: 12 }}>Sin observaciones registradas.</p>
                )}
              </>
            )}

            {/* ── Productos del pedido ── */}
            {activeSection === "productos" && (
              <>
                <p className="section-label" style={{ marginTop: 0 }}>
                  Productos {pedido.idVenta ? `del pedido #${pedido.idVenta}` : ""}
                </p>
                {(pedido.productos || []).length === 0 ? (
                  <p style={{ fontSize: 12, color: "#bdbdbd" }}>
                    Este domicilio no tiene productos registrados.
                  </p>
                ) : (
                  <div style={{ display: "grid", gap: 10 }}>
                    {pedido.productos.map((pr, i) => (
                      <div key={pr.ID_Producto ?? i} style={{
                        display: "flex", alignItems: "center", gap: 12,
                        padding: "10px 12px", borderRadius: 10,
                        border: "1px solid #eeeeee", background: "#fafafa",
                      }}>
                        {pr.imagen ? (
                          <img
                            src={pr.imagen}
                            alt={pr.nombre_producto || "Producto"}
                            loading="lazy"
                            style={{
                              width: 46, height: 46, borderRadius: 8,
                              objectFit: "cover", flexShrink: 0, background: "#e8f5e9",
                            }}
                          />
                        ) : (
                          <div style={{
                            width: 46, height: 46, borderRadius: 8, background: "#e8f5e9",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "#a5d6a7", flexShrink: 0,
                          }}><Utensils size={20} strokeWidth={1.5} /></div>
                        )}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1a1a" }}>
                            {pr.nombre_producto || "Producto"}
                          </div>
                          <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2 }}>
                            {pr.Cantidad} × {fmt(pr.precio_unitario)}
                          </div>
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: "#2e7d32" }}>
                          {fmt(pr.subtotal)}
                        </div>
                      </div>
                    ))}
                    <div style={{
                      display: "flex", justifyContent: "space-between",
                      paddingTop: 10, borderTop: "1px solid #eeeeee",
                      fontSize: 14, fontWeight: 800,
                    }}>
                      <span>Total del pedido</span>
                      <span style={{ color: "#2e7d32" }}>{fmt(pedido.total)}</span>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── Pago ── */}
            {activeSection === "pago" && (
              <>
                <p className="section-label" style={{ marginTop: 0 }}>Método de pago</p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <MetodoPagoChip metodo={pedido.metodo_pago} />
                  <EstadoPagoChip estadoPago={pedido.estado_pago} />
                </div>

                <p className="section-label">Total a cobrar en mano</p>
                <div className="info-box">
                  <span className="info-box__icon"><Banknote size={14} /></span>
                  <span className="info-box__text" style={{ fontWeight: 800 }}>{fmt(montoACobrar(pedido))}</span>
                </div>

                {/* Mismo criterio que aplica el backend al marcar entregado */}
                {bloqueoEntrega(pedido) ? (
                  <div className="info-box info-box--warn" style={{ marginTop: 12 }}>
                    <span className="info-box__icon"><AlertTriangle size={14} /></span>
                    <span className="info-box__text">{bloqueoEntrega(pedido)}</span>
                  </div>
                ) : (
                  <div className="info-box" style={{ marginTop: 12 }}>
                    <span className="info-box__icon"><CheckCircle2 size={14} /></span>
                    <span className="info-box__text">
                      El cobro está registrado: se puede marcar como entregado.
                    </span>
                  </div>
                )}

                <p className="section-label">Comprobante</p>
                {pedido.comprobante_pago ? (
                  <a href={pedido.comprobante_pago} target="_blank" rel="noopener noreferrer">
                    <img
                      src={pedido.comprobante_pago}
                      alt="Comprobante de pago"
                      loading="lazy"
                      style={{
                        maxWidth: "100%", maxHeight: 260, borderRadius: 10,
                        border: "1px solid #eeeeee", display: "block",
                      }}
                    />
                  </a>
                ) : (
                  <p style={{ fontSize: 12, color: "#bdbdbd" }}>
                    {esPagoTransferencia(pedido.metodo_pago)
                      ? "El cliente aún no adjuntó el comprobante."
                      : "No aplica: el pago es en efectivo."}
                  </p>
                )}
              </>
            )}

            {/* ── Domiciliario ── */}
            {activeSection === "domiciliario" && (
              <>
                <p className="section-label" style={{ marginTop: 0 }}>Domiciliario asignado</p>
                {emp ? (
                  <>
                    <div style={{
                      display: "flex", alignItems: "center", gap: 14, padding: "12px 16px",
                      borderRadius: 10, border: "1.5px solid #c8e6c9", background: "#f9fdf9",
                    }}>
                      <div style={{
                        width: 42, height: 42, borderRadius: "50%", background: "#e8f5e9",
                        border: "1.5px solid #a5d6a7", display: "flex", alignItems: "center",
                        justifyContent: "center", color: "#2e7d32", flexShrink: 0,
                      }}><Bike size={20} strokeWidth={1.5} /></div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: "#1a1a1a" }}>
                          {emp.nombre} {emp.apellidos}
                        </div>
                        <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2 }}>{emp.correo}</div>
                      </div>
                    </div>

                    <div style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                      gap: 10, marginTop: 14
                    }}>
                      {[
                        { label: "Asignados",  val: pedidosAsignados.length, bg: "#fff8e1", border: "#ffe082", color: "#6d4c41" },
                        { label: "Pendientes", val: pendientes,              bg: "#e3f2fd", border: "#90caf9", color: "#1565c0" },
                        { label: "En camino",  val: enCamino,               bg: "#f3e5f5", border: "#ce93d8", color: "#6a1b9a" },
                        { label: "Entregados", val: entregados,             bg: "#e8f5e9", border: "#a5d6a7", color: "#2e7d32" },
                      ].map(s => (
                        <div key={s.label} style={{ background: s.bg, border: `1px solid ${s.border}`, borderRadius: 10, padding: 12 }}>
                          <div style={{ fontSize: 12, color: s.color, marginBottom: 4 }}>{s.label}</div>
                          <div style={{ fontSize: 18, fontWeight: 700, color: s.color }}>{s.val}</div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="info-box info-box--warn">
                    <span className="info-box__icon"><AlertTriangle size={14} /></span>
                    <span className="info-box__text">Sin domiciliario asignado.</span>
                  </div>
                )}
              </>
            )}

            {/* ── Fechas ── */}
            {activeSection === "fechas" && (
              <>
                <p className="section-label" style={{ marginTop: 0 }}>Fechas</p>
                <div className="form-grid-2">
                  <div>
                    <label className="form-label">Fecha del pedido</label>
                    <div className="field-input--disabled">{fmtFecha(pedido.fecha_pedido)}</div>
                  </div>
                  <div>
                    <label className="form-label">Fecha de entrega real</label>
                    <div className="field-input--disabled" style={{ color: pedido.fecha_entrega_real ? "#2e7d32" : "#bdbdbd" }}>
                      {pedido.fecha_entrega_real ? fmtFecha(pedido.fecha_entrega_real) : "Pendiente"}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
          {activo && (
            <button className="btn-cancel" onClick={() => { onClose(); onObservaciones(pedido); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <PenLine size={14} /> Observaciones
            </button>
          )}
          {puedeReasignarse(pedido.estadoId) && (
            <button className="btn-save" onClick={() => { onClose(); onReasignar(pedido); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Bike size={14} /> Reasignar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL REASIGNAR DOMICILIARIO
   ═══════════════════════════════════════════════════════════ */
function ModalReasignar({ pedido, empleados, repartidores, onClose, onConfirm }) {
  const [empId, setEmpId] = useState(pedido.idEmpleado || "");
  const [error, setError] = useState("");
  const empActual = empleados.find(e => e.id === pedido.idEmpleado);

  const handleConfirm = () => {
    if (!empId) { setError("Selecciona un domiciliario"); return; }
    if (parseInt(empId) === pedido.idEmpleado) { setError("Ya está asignado a este domiciliario"); return; }
    onConfirm(pedido.id, parseInt(empId));
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Logística</p>
            <h2 className="modal-header__title">Reasignar domiciliario</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body" style={{ overflow: "visible" }}>
          <p style={{ margin: 0, fontSize: 12, color: "#616161" }}>
            Pedido: <strong>{pedido.numero}</strong>
          </p>

          <div className="info-box info-box--info">
            <span className="info-box__icon"><MapPin size={14} /></span>
            <span className="info-box__text">{pedido.direccion_entrega}</span>
          </div>

          {empActual && (
            <div className="info-box info-box--warn">
              <span className="info-box__icon"><Bike size={14} /></span>
              <span className="info-box__text">
                Actual: <strong>{empActual.nombre} {empActual.apellidos}</strong>
              </span>
            </div>
          )}

          <div>
            <label className="form-label">Nuevo domiciliario <span className="required">*</span></label>
            <SearchableSelect
              className={`field-select${error ? " error" : ""}`}
              options={repartidores}
              value={empId}
              onChange={e => { setEmpId(e.target.value); setError(""); }}
              getValue={e => e.id}
              getLabel={e => `${e.nombre} ${e.apellidos}${e.id === pedido.idEmpleado ? " (actual)" : ""}`}
              placeholder="Seleccione…"
              searchPlaceholder="Buscar domiciliario…"
            />
            {error && <p className="field-error">{error}</p>}
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button className="btn-save" onClick={handleConfirm}>Reasignar</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL OBSERVACIONES
   ═══════════════════════════════════════════════════════════ */
function ModalObservaciones({ pedido, onClose, onConfirm }) {
  const [obs, setObs]   = useState(pedido.obs_domicilio || "");
  const [done, setDone] = useState(false);

  return (
    <div className="modal-overlay">
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Domicilio</p>
            <h2 className="modal-header__title">Observaciones</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="modal-body" style={{ overflow: "visible" }}>
          <p style={{ margin: 0, fontSize: 12, color: "#616161" }}>
            Pedido: <strong>{pedido.numero}</strong> · {pedido.cliente?.nombre}
          </p>
          <div className="info-box info-box--info">
            <span className="info-box__icon"><MapPin size={14} /></span>
            <span className="info-box__text">{pedido.direccion_entrega}</span>
          </div>
          <div>
            <label className="form-label">Observaciones de entrega</label>
            <textarea
              className="field-textarea"
              rows={4}
              placeholder="Instrucciones especiales, referencias del lugar, llamar al llegar…"
              value={obs}
              onChange={e => setObs(e.target.value)}
            />
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button
            className="btn-save"
            disabled={done}
            onClick={() => { setDone(true); setTimeout(() => onConfirm(pedido.id, obs), 700); }}
          >
            {done ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   HISTORIAL POR DOMICILIARIO
   ═══════════════════════════════════════════════════════════ */
function HistorialDomiciliario({ domicilios, empleados, onDesactivar }) {
  const [abiertos, setAbiertos] = useState({});
  const toggle = (id) => setAbiertos(p => ({ ...p, [id]: !p[id] }));

  const grupos = empleados.map(emp => {
    const pedidosEmp = domicilios.filter(p => p.idEmpleado === emp.id);
    return {
      emp,
      total:      pedidosEmp.length,
      entregados: pedidosEmp.filter(p => p.estado === "Entregado").length,
      enCamino:   pedidosEmp.filter(p => p.estado === "En camino").length,
      activos:    pedidosEmp.filter(p => !["Entregado", "Cancelado"].includes(p.estado)).length,
      pedidos:    pedidosEmp,
    };
  }).filter(g => g.total > 0).sort((a, b) => b.total - a.total);

  if (grupos.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state__icon" style={{ color: "#d4d4d4", display: "flex", justifyContent: "center" }}><Bike size={40} /></div>
        <p className="empty-state__text">No hay domicilios asignados a empleados.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {grupos.map(({ emp, total, entregados, enCamino, activos, pedidos }) => (
        <div key={emp.id} className="hist-emp-card">
          <div className="hist-emp-header" onClick={() => toggle(emp.id)}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 38, height: 38, borderRadius: "50%", background: "#e8f5e9",
                border: "1.5px solid #a5d6a7", display: "flex", alignItems: "center",
                justifyContent: "center", color: "#2e7d32", flexShrink: 0,
              }}><Bike size={18} strokeWidth={1.5} /></div>
              <div>
                <div className="hist-emp-name">{emp.nombre} {emp.apellidos}</div>
                <div style={{ fontSize: 11, color: "#9e9e9e" }}>{emp.correo}</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div className="hist-emp-stats">
                <span className="hist-stat hist-stat--total">Total: {total}</span>
                <span className="hist-stat hist-stat--active">Pendientes: {activos}</span>
                {enCamino   > 0 && <span className="hist-stat hist-stat--camino" style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Bike size={11} />{enCamino}</span>}
                {entregados > 0 && <span className="hist-stat hist-stat--entregado" style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Check size={11} />{entregados}</span>}
              </div>
              {/* ── Botón desactivar con advertencia si tiene activos ── */}
              {onDesactivar && (
                <button
                  className="act-btn"
                  title={activos > 0 ? `Tiene ${activos} domicilio(s) activo(s)` : "Desactivar domiciliario"}
                  style={{
                    background: activos > 0 ? "#fff8e1" : "#ffebee",
                    border: `1.5px solid ${activos > 0 ? "#ffe082" : "#ef9a9a"}`,
                    color:   activos > 0 ? "#f9a825" : "#c62828",
                    fontSize: 14,
                  }}
                  onClick={e => { e.stopPropagation(); onDesactivar(emp, pedidos.filter(p => !["Entregado", "Cancelado"].includes(p.estado))); }}
                >
                  {activos > 0 ? <AlertTriangle size={14} /> : <Ban size={14} />}
                </button>
              )}
              <span style={{
                color: "#9e9e9e", fontSize: 16,
                transform: abiertos[emp.id] ? "rotate(90deg)" : "none",
                transition: "transform 0.2s",
                display: "flex",
              }}><ChevronRight size={16} /></span>
            </div>
          </div>

          {abiertos[emp.id] && (
            <div className="hist-pedidos-list">
              {pedidos.map(p => (
                <div key={p.id} className="hist-pedido-row">
                  <span className="hist-pedido-num">{p.numero}</span>
                  <span className="hist-pedido-dir">{p.direccion_entrega}</span>
                  <EstadoBadge estado={p.estado} estadoId={p.estadoId} />
                  <span className="hist-pedido-fecha">{fmtFecha(p.fecha_pedido)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENTE PRINCIPAL
   ═══════════════════════════════════════════════════════════ */
export default function GestionDomicilios() {
  const [domicilios,   setDomicilios]   = useState([]);
  const [empleados,    setEmpleados]    = useState([]);
  const [repartidores, setRepartidores] = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [errorCarga,      setErrorCarga]      = useState(null);
  const [actionSaving,    setActionSaving]    = useState(false);
  const [tab,             setTab]             = useState("tabla");
  const [totalDomicilios, setTotalDomicilios] = useState(0);
  const [search,          setSearch]          = useState("");
  const [filterEstado, setFilterEstado] = useState("todos");
  const [filterDesde,  setFilterDesde]  = useState("");
  const [filterHasta,  setFilterHasta]  = useState("");
  const [showFilter,   setShowFilter]   = useState(false);
  // El aviso de "sin domiciliario" arranca abierto, como la lista de
  // solicitudes de la app móvil, pero se puede plegar: con muchos pendientes
  // la lista de chips empujaba la tabla fuera de la pantalla.
  const [avisoAbierto, setAvisoAbierto] = useState(true);
  const [page,         setPage]         = useState(1);
  const [modal,        setModal]        = useState(null);
  const [toast,        setToast]        = useState(null);
  const filterRef = useRef();

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3200);
  };

  const cargarDatos = async ({ busqueda = null, fechaInicio = null, fechaFin = null } = {}) => {
    setLoading(true);
    setErrorCarga(null);
    try {
      const [dData, uData] = await Promise.all([
        getDomicilios({ porPagina: 100, busqueda, fechaInicio, fechaFin }),
        getUsuarios({ porPagina: 100 }).catch(() => []),
      ]);
      setTotalDomicilios(dData.total || 0);
      setDomicilios(dData.domicilios);
      // Lista amplia: resuelve el nombre de quien ya está asignado.
      setEmpleados((uData || []).filter(u =>
        u.tipo === "empleado" && u.estado && (
          u.idRol === 1 || u.idRol === 4 ||
          ["admin", "administrador", "domiciliario"].includes((u.rol || "").toLowerCase())
        )
      ));
      // A quién SÍ se le puede asignar: sin administradores. Antes la lista
      // de arriba alimentaba el selector, así que salía "Administrador Toston"
      // como opción, y además filtraba por idRol 3, que es otro rol.
      setRepartidores((uData || []).filter(esEmpleadoRepartidor));
    } catch (err) {
      // Antes solo salía un toast y la tabla mostraba "No hay domicilios
      // registrados", que es falso cuando lo que falló fue la carga.
      const msg = /403|permiso/i.test(err?.message || "")
        ? "No tienes permiso para ver los domicilios (ver_domicilios)."
        : (err?.message || "No se pudieron cargar los domicilios.");
      setErrorCarga(msg);
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  // Re-buscar en el servidor cuando cambia el texto (debounce 400ms)
  const domSearchMounted = useRef(false);
  useEffect(() => {
    if (!domSearchMounted.current) { domSearchMounted.current = true; return; }
    const q = search || null;
    const t = setTimeout(() => cargarDatos({ busqueda: q, fechaInicio: filterDesde || null, fechaFin: filterHasta || null }), 400);
    return () => clearTimeout(t);
  }, [search]);

  // Re-buscar en el servidor cuando cambia el rango de fechas (inmediato)
  const domDateMounted = useRef(false);
  useEffect(() => {
    if (!domDateMounted.current) { domDateMounted.current = true; return; }
    cargarDatos({ busqueda: search || null, fechaInicio: filterDesde || null, fechaFin: filterHasta || null });
  }, [filterDesde, filterHasta]);

  useEffect(() => {
    const h = e => { if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  /* El nombre del repartidor no viene en el domicilio adaptado: la tabla lo
     resuelve contra los empleados y el CSV hace lo mismo. */
  const nombreRepartidor = (d) => {
    const emp = empleados.find(e => e.id === d.idEmpleado);
    return emp ? `${emp.nombre} ${emp.apellidos}`.trim() : "";
  };

  /* ── Solo pedidos listos para salir ────────────────────────────────────
     El domicilio se crea junto con la venta, así que el panel lo mostraba
     desde que se hacía el pedido. No hay nada que gestionar hasta que el
     pedido está LISTO (11): antes sigue en cocina o esperando confirmación.
     Se incluyen los posteriores —En camino (9) y Entregado (8)— y los
     cancelados (5), para poder cerrarlos. Mismo criterio que la app móvil.
     Si el backend no envía el estado de la venta, no se oculta nada. */
  const listoParaSalir = (d) =>
    d.id_grupo || d.venta_estado_id == null || [11, 9, 8, 5].includes(d.venta_estado_id);

  const gestionables = domicilios.filter(listoParaSalir);

  /* Lo que de verdad hay que atender: el pedido ya salió de cocina y todavía
     no tiene quién lo lleve. Es el mismo criterio que usa la app móvil para
     su lista de "Solicitudes sin asignar" y el mismo del filtro de la tabla.
     Antes acá se avisaba de los pedidos que seguían en cocina, que no son
     algo sobre lo que este panel pueda hacer nada. */
  const sinAsignarLista = gestionables.filter(
    d => !d.idEmpleado && esDomicilioActivo(d.estadoId)
  );

  /* ── Filtrado ── */
  const filtered = gestionables.filter(p => {
    const q   = search.toLowerCase();
    const emp = empleados.find(e => e.id === p.idEmpleado);
    const matchQ = [
      p.numero, p.cliente?.nombre, p.cliente?.correo,
      p.direccion_entrega,
      emp ? `${emp.nombre} ${emp.apellidos}` : "",
    ].filter(Boolean).some(v => v.toLowerCase().includes(q));

  // La pestaña decide de qué mitad se habla; los chips filtran dentro.
  const enSuPestana = tab === "historial"
    ? !esDomicilioActivo(p.estadoId)
    : esDomicilioActivo(p.estadoId);

  const matchE =
    filterEstado === "todos"       ? true :
    filterEstado === "activos"     ? esDomicilioActivo(p.estadoId) :
    filterEstado === "sin-asignar" ? !p.idEmpleado && esDomicilioActivo(p.estadoId) :
    p.estadoId === filterEstado;

    let matchFecha = true;
    if (filterDesde || filterHasta) {
      const fechaRaw = String(p.fecha_pedido || "").slice(0, 10);
      const fecha = fechaRaw ? new Date(`${fechaRaw}T00:00:00`) : null;
      if (!fecha) matchFecha = false;
      if (filterDesde && fecha && new Date(`${filterDesde}T00:00:00`) > fecha) matchFecha = false;
      if (filterHasta && fecha && new Date(`${filterHasta}T00:00:00`) < fecha) matchFecha = false;
    }

    return enSuPestana && matchQ && matchE && matchFecha;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paged      = filtered.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);
  useEffect(() => setPage(1), [search, filterEstado, filterDesde, filterHasta, tab]);
  // Los chips de estado de una pestaña no significan nada en la otra.
  useEffect(() => setFilterEstado("todos"), [tab]);

  const hasFilter = filterEstado !== "todos" || filterDesde || filterHasta;

  /* ── Handlers ── */
  const handleReasignar = async (domicilioId, empId) => {
    setActionSaving(true);
    try {
      await asignarRepartidor(domicilioId, empId);
      await cargarDatos();
      const emp = empleados.find(e => e.id === empId);
      showToast(`Reasignado a ${emp?.nombre} ${emp?.apellidos}`);
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al reasignar domiciliario", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleObservaciones = async (domicilioId, obs) => {
    setActionSaving(true);
    try {
      await actualizarDomicilio(domicilioId, { Observaciones: obs });
      await cargarDatos();
      showToast("Observaciones guardadas");
      setModal(null);
    } catch (err) {
      showToast(err.message || "Error al guardar observaciones", "error");
    } finally {
      setActionSaving(false);
    }
  };

  // El cobro en efectivo se registra con el endpoint que ya usa el repartidor;
  // el administrador tiene el mismo permiso (cambiar_estado_domicilios) con el
  // que cambia estados aquí, así que no se añaden permisos nuevos.
  const handleRegistrarCobro = async (pedido, recibido, monto, motivo) => {
    setActionSaving(true);
    try {
      await registrarPagoEfectivo(pedido.id, { recibido, monto, motivo });
      await cargarDatos();
      showToast(recibido
        ? `Cobro de ${fmt(montoACobrar(pedido))} registrado para ${pedido.numero}`
        : `Se registró que ${pedido.numero} no fue cobrado`);
      setModal(null);
    } catch (err) {
      showToast(err.message || "No se pudo registrar el cobro", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleCambiarEstado = async (domicilioId, nuevoEstadoId, pedido = null) => {
    // Misma regla que el backend: hace falta el cobro registrado y el
    // comprobante SOLO si el pago fue por transferencia. Antes se exigía
    // comprobante siempre, así que un pedido en efectivo no se podía entregar.
    if (nuevoEstadoId === ESTADO_DOMICILIO.ENTREGADO && pedido) {
      const bloqueo = bloqueoEntrega(pedido);
      if (bloqueo) {
        showToast(`No se puede entregar: ${bloqueo}`, "error");
        return;
      }
    }
    setActionSaving(true);
    try {
      await cambiarEstadoDomicilio(domicilioId, nuevoEstadoId);
      await cargarDatos();
      showToast("Estado actualizado correctamente");
    } catch (err) {
      showToast(err.message || "Error al cambiar el estado", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const abrirReasignar = (ped) => {
    if (!puedeReasignarse(ped.estadoId)) {
      showToast(
        ped.estadoId === ESTADO_DOMICILIO.EN_CAMINO
          ? "El pedido ya va en camino: no se puede cambiar de domiciliario"
          : "No se puede reasignar un domicilio ya finalizado",
        "warn",
      );
      return;
    }
    setModal({ type: "reasignar", pedido: ped });
  };

  const abrirObservaciones = (ped) => {
    if (["Entregado", "Cancelado"].includes(ped.estado)) {
      showToast("No se pueden editar observaciones de un domicilio finalizado", "warn"); return;
    }
    setModal({ type: "obs", pedido: ped });
  };

  const handleSolicitarDesactivar = (emp, pedidosActivos) => {
    if (pedidosActivos.length > 0) {
      setModal({ type: "confirmar-desactivar", usuario: emp, pedidosActivos });
    } else {
      toggleEstadoUsuario(emp.tipo || "empleado", emp.id, emp.estado)
        .then(() => { cargarDatos(); showToast(`${emp.nombre} ${emp.apellidos} desactivado`); })
        .catch(err => showToast(err.message || "Error al desactivar", "error"));
    }
  };

  const handleConfirmarDesactivar = async () => {
    const { usuario } = modal;
    try {
      await toggleEstadoUsuario(usuario.tipo || "empleado", usuario.id, usuario.estado);
      await cargarDatos();
      showToast(`${usuario.nombre} ${usuario.apellidos} desactivado`, "warn");
    } catch (err) {
      showToast(err.message || "Error al desactivar", "error");
    }
    setModal(null);
  };

  /* ── Stats ── */
  const totalDom   = gestionables.length;
  const enCamino   = gestionables.filter(p => p.estado === "En camino").length;
  const entregados = gestionables.filter(p => p.estado === "Entregado").length;
  const conAsignar = gestionables.filter(p => p.idEmpleado).length;
  const sinAsignar = sinAsignarLista.length;

  // Domiciliarios solo pueden ver su propio panel
  if (esRolRepartidor(getUser()?.rol)) {
    return <Navigate to={INICIO_REPARTIDOR} replace />;
  }

  return (
    <div className="page-wrapper mod-domicilios">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Domicilios</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">

        {/* ── Stats ── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
          {[
            { label: "Total domicilios", val: totalDom,   color: "#2e7d32", bg: "#e8f5e9", border: "#a5d6a7", Icon: Truck },
            { label: "Asignados",        val: conAsignar, color: "#1565c0", bg: "#e3f2fd", border: "#90caf9", Icon: MapPin },
            { label: "En camino",        val: enCamino,   color: "#6a1b9a", bg: "#f3e5f5", border: "#ce93d8", Icon: Bike },
            { label: "Entregados",       val: entregados, color: "#2e7d32", bg: "#e8f5e9", border: "#a5d6a7", Icon: CheckCircle2 },
            {
              label: "Sin asignar",
              val: sinAsignar,
              color:  sinAsignar > 0 ? "#c62828" : "#9e9e9e",
              bg:     sinAsignar > 0 ? "#ffebee" : "#fafafa",
              border: sinAsignar > 0 ? "#ef9a9a" : "#e0e0e0",
              Icon:   AlertTriangle,
            },
          ].map(s => (
            <div key={s.label} style={{
              background: s.bg, border: `1.5px solid ${s.border}`, borderRadius: 12,
              padding: "14px 16px", display: "flex", alignItems: "center", gap: 12,
            }}>
              <s.Icon size={24} strokeWidth={1.5} style={{ color: s.color, flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: 22, fontWeight: 800, color: s.color, fontFamily: "var(--font-head)", lineHeight: 1 }}>{s.val}</div>
                <div style={{ fontSize: 11, color: s.color, marginTop: 3, fontWeight: 600 }}>{s.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* ── Tabs ── */}
        <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
          {[
            { key: "tabla",       label: "Activos",     Icon: Bike },
            { key: "historial",   label: "Historial",   Icon: History },
            { key: "domiciliario", label: "Por domiciliario", Icon: BarChart2 },
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              padding: "9px 18px", borderRadius: "10px 10px 0 0", border: "none",
              background: tab === t.key ? "#fff" : "transparent",
              fontFamily: "inherit", fontSize: 13, fontWeight: 700,
              color: tab === t.key ? "#2e7d32" : "#9e9e9e", cursor: "pointer",
              borderBottom: tab === t.key ? "3px solid #2e7d32" : "3px solid transparent",
              transition: "all 0.15s",
              display: "flex", alignItems: "center", gap: 6,
            }}><t.Icon size={14} />{t.label}</button>
          ))}
        </div>

        {/* ══ TAB: Tabla ══ */}
        {(tab === "tabla" || tab === "historial") && (
          <>
            {totalDomicilios > 100 && !search && !filterDesde && !filterHasta && (
              <div className="info-box info-box--warning" style={{ marginBottom: 12 }}>
                <span className="info-box__icon"><AlertCircle size={14} /></span>
                <span className="info-box__text">
                  Mostrando los 100 domicilios más recientes de <strong>{totalDomicilios}</strong> en total.
                  Usa la búsqueda o el filtro de fechas para encontrar registros anteriores.
                </span>
              </div>
            )}
            <div className="toolbar">
              <div className="search-wrap">
                <Search size={14} className="search-icon" />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Buscar por pedido, cliente, dirección o domiciliario…"
                  value={search}
                  onChange={e => { setSearch(e.target.value); setPage(1); }}
                />
              </div>

              <button
                className="btn-action"
                style={{ display: "flex", alignItems: "center", gap: 6 }}
                disabled={filtered.length === 0}
                data-tooltip={
                  filtered.length === 0
                    ? "No hay domicilios que exportar"
                    : `Exportar ${filtered.length} domicilio${filtered.length === 1 ? "" : "s"}`
                }
                onClick={() => {
                  // Se exporta lo que se está viendo (búsqueda y filtros
                  // incluidos), no solo la página actual.
                  if (exportToCsv(filtered, nombreRepartidor)) {
                    showToast(
                      `${filtered.length} domicilio${filtered.length === 1 ? "" : "s"} exportado${filtered.length === 1 ? "" : "s"}`,
                      "success"
                    );
                  }
                }}
              >
                <FileText size={14} /> Exportar CSV
              </button>

              <div ref={filterRef} style={{ position: "relative" }}>
                <button
                  className={`filter-icon-btn${hasFilter ? " has-filter" : ""}`}
                  onClick={() => setShowFilter(v => !v)}
                  data-tooltip="Filtrar domicilios"
                >▼</button>
                {showFilter && (
                  <div className="filter-dropdown" style={{ minWidth: 185 }}>
                    <p className="filter-section-title">Estado</p>
                    {FILTER_OPTIONS.map(f => (
                      <button
                        key={f.val}
                        className={`filter-option${filterEstado === f.val ? " active" : ""}`}
                        onClick={() => { setFilterEstado(f.val); setPage(1); setShowFilter(false); }}
                      >
                        <span className="filter-dot" style={{ background: f.dot }} />
                        {f.label}
                      </button>
                    ))}
                    <div style={{ height: 1, background: "#f0f0f0", margin: "8px 0" }} />
                    <DateRangeFilter
                      desde={filterDesde}
                      hasta={filterHasta}
                      label="Fecha del pedido"
                      onApply={({ desde, hasta }) => {
                        setFilterDesde(desde || "");
                        setFilterHasta(hasta || "");
                      }}
                      onClear={() => {
                        setFilterDesde("");
                        setFilterHasta("");
                      }}
                    />
                  </div>
                )}
              </div>
            </div>

            {tab === "tabla" && sinAsignarLista.length > 0 && (
              <section className="sin-asignar">
                <button
                  type="button"
                  className="sin-asignar__head"
                  aria-expanded={avisoAbierto}
                  onClick={() => setAvisoAbierto(v => !v)}
                >
                  <span className="sin-asignar__icono"><Bike size={16} /></span>
                  <span className="sin-asignar__txt">
                    <strong>Esperando domiciliario</strong>
                    <em>
                      {sinAsignarLista.length === 1
                        ? "1 pedido listo para salir, sin quién lo lleve"
                        : `${sinAsignarLista.length} pedidos listos para salir, sin quién los lleve`}
                    </em>
                  </span>
                  <span className="sin-asignar__badge">{sinAsignarLista.length}</span>
                  <ChevronDown size={18} className="sin-asignar__chevron" />
                </button>

                {avisoAbierto && (
                  <div className="sin-asignar__grid">
                    {sinAsignarLista.map(d => (
                      <article key={d.id} className="sa-card">
                        <header className="sa-card__top">
                          <span className="sa-card__num">{d.numero}</span>
                          {d.total != null && (
                            <span className="sa-card__total">{formatCOP(d.total)}</span>
                          )}
                        </header>
                        <p className="sa-card__cliente">
                          <User size={12} /> {d.cliente?.nombre || "Sin nombre"}
                        </p>
                        {d.direccion_entrega && (
                          <p className="sa-card__dir">
                            <MapPin size={12} />
                            <span>
                              {d.direccion_entrega}
                              {d.barrio_entrega ? ` · ${d.barrio_entrega}` : ""}
                            </span>
                          </p>
                        )}
                        <button
                          type="button"
                          className="sa-card__btn"
                          onClick={() => abrirReasignar(d)}
                        >
                          <Bike size={13} /> Asignar domiciliario
                        </button>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            <div className="card">
              <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "92px", "--tbl-rows": 5 }}>
                <table className="tbl tbl--fixed-rows">
                  <thead>
                    <tr>
                      <th>Pedido</th>
                      <th>Cliente</th>
                      <th>Dirección</th>
                      <th>Domiciliario</th>
                      <th>Pago</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <SkeletonRows cols={7} rows={5} />
                    ) : errorCarga ? (
                      <tr><td colSpan={7}>
                        <div className="empty-state">
                          <div className="empty-state__icon" style={{ color: "#ef9a9a", display: "flex", justifyContent: "center" }}><AlertTriangle size={40} /></div>
                          <p className="empty-state__text">{errorCarga}</p>
                          <button className="btn-ghost" style={{ marginTop: 10 }} onClick={cargarDatos}>
                            Reintentar
                          </button>
                        </div>
                      </td></tr>
                    ) : paged.length === 0 ? (
                      <tr><td colSpan={7}>
                        <div className="empty-state">
                          <div className="empty-state__icon" style={{ color: "#d4d4d4", display: "flex", justifyContent: "center" }}>
                            {hasFilter || search ? <Search size={40} /> : <Bike size={40} />}
                          </div>
                          <p className="empty-state__text">
                            {hasFilter || search ? "Sin domicilios que coincidan." : "No hay domicilios registrados."}
                          </p>
                          {(hasFilter || search) && (
                            <button
                              className="btn-ghost"
                              style={{ marginTop: 10 }}
                              onClick={() => { setSearch(""); setFilterEstado("todos"); setFilterDesde(""); setFilterHasta(""); }}
                            >Limpiar filtros</button>
                          )}
                        </div>
                      </td></tr>
                    ) : paged.map((ped) => {
                      const emp    = empleados.find(e => e.id === ped.idEmpleado);
                      const activo = !["Entregado", "Cancelado"].includes(ped.estado);
                      const sinAsignado = !emp && activo;
                      return (
                        <tr
                          key={ped.id}
                          className="tbl-row"
                          style={{ background: sinAsignado ? "#fffbf0" : "transparent" }}
                        >
                          <td data-label="Pedido">
                            <div className="pedido-num">{ped.numero}</div>
                            <div className="pedido-fecha">{fmt(ped.total)}</div>
                          </td>
                          <td data-label="Cliente">
                            <div className="client-name">{ped.cliente?.nombre || "—"}</div>
                            <div className="client-phone">{ped.cliente?.telefono || ""}</div>
                          </td>
                          <td data-label="Dirección">
                            <div
                              className="dir-main"
                              style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                            >
                              {ped.direccion_entrega || "—"}
                            </div>
                            {ped.obs_domicilio && (
                              <div className="dir-sub" title={ped.obs_domicilio} style={{ display: "flex", alignItems: "flex-start", gap: 4 }}>
                                <PenLine size={11} style={{ flexShrink: 0, marginTop: 1 }} />{ped.obs_domicilio.length > 30
                                  ? ped.obs_domicilio.slice(0, 30) + "…"
                                  : ped.obs_domicilio}
                              </div>
                            )}
                          </td>
                          <td data-label="Domiciliario">
                            {emp ? (
                              <div className="emp-name" style={{ display: "flex", alignItems: "center", gap: 5 }}><Bike size={12} />{emp.nombre} {emp.apellidos}</div>
                            ) : (
                              <div className="emp-none">Sin asignar</div>
                            )}
                          </td>
                          <td data-label="Pago">
                            <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                              <MetodoPagoChip metodo={ped.metodo_pago} />
                              <EstadoPagoChip estadoPago={ped.estado_pago} />
                            </div>
                          </td>
                          <td data-label="Estado">
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                              <EstadoBadge estado={ped.estado} estadoId={ped.estadoId} />
                              {FEATURE_DIVISION_PEDIDOS && ped.id_grupo && (
                                <span style={{
                                  fontSize: 10, fontWeight: 700, color: "#6a1b9a",
                                  background: "#f3e5f5", borderRadius: 4, padding: "2px 5px",
                                }}>
                                  {ped.tipo_grupo === "anticipado" ? "Grupo anticipado" : "Grupo programado"}
                                </span>
                              )}
                              {/* Avisa si venta cancelada pero entrega aún abierta */}
                              {ped.venta_estado_id === 5 && ped.estadoId !== 5 && ped.estadoId !== 8 && (
                                <span style={{
                                  fontSize: 10, fontWeight: 700, color: "#c62828",
                                  background: "#ffebee", borderRadius: 4, padding: "2px 5px",
                                }}>Pedido cancelado</span>
                              )}
                            </div>
                          </td>
                          <td data-label="Acciones">
                            <div className="actions-cell">
                              <button
                                className="act-btn act-btn--view"
                                data-tooltip="Ver detalle del pedido"
                                onClick={() => setModal({ type: "ver", pedido: ped })}
                              ><Eye size={14} /></button>
                              <button
                                className="act-btn act-btn--map"
                                data-tooltip="Ver en Google Maps"
                                onClick={() => window.open(mapToGoogleMaps(ped.direccion_entrega, ped.municipio_entrega, ped.departamento_entrega), "_blank", "noopener")}
                              ><Globe size={14} /></button>
                              {cobroEfectivoPendiente(ped) && esDomicilioActivo(ped.estadoId) && (
                                <button
                                  className="act-btn"
                                  data-tooltip="Registrar cobro en efectivo"
                                  onClick={() => setModal({ type: "registrarCobro", pedido: ped })}
                                  style={{ background: "#fff8e1", color: "#f9a825" }}
                                ><Banknote size={14} /></button>
                              )}
                              {transicionesDom(ped.estadoId).length > 0 && (
                                <button
                                  className="act-btn"
                                  data-tooltip="Cambiar estado del pedido"
                                  onClick={() => setModal({ type: "cambiarEstado", pedido: ped })}
                                  style={{ background: "#e8f5e9", color: "#2e7d32" }}
                                ><Zap size={14} /></button>
                              )}
                              {puedeReasignarse(ped.estadoId) && (
                                <button
                                  className="act-btn act-btn--reasignar"
                                  data-tooltip="Reasignar domiciliario"
                                  onClick={() => abrirReasignar(ped)}
                                ><Bike size={14} /></button>
                              )}
                              <button
                                className="act-btn act-btn--obs"
                                data-tooltip={activo ? "Agregar observación" : "Domicilio finalizado"}
                                disabled={!activo}
                                onClick={() => abrirObservaciones(ped)}
                                style={{ opacity: activo ? 1 : 0.35, cursor: activo ? "pointer" : "not-allowed" }}
                              ><PenLine size={14} /></button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {!loading && !errorCarga && (
                      <FilasRelleno current={paged.length} perPage={PER_PAGE} colSpan={7} />
                    )}
                  </tbody>
                </table>
              </div>

              <div className="pagination-bar">
                <span className="pagination-count">
                  {filtered.length} {filtered.length === 1 ? "domicilio" : "domicilios"} en total
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
          </>
        )}

        {/* ══ TAB: Historial ══ */}
        {tab === "domiciliario" && (
          <div className="card" style={{ padding: 20 }}>
            <HistorialDomiciliario
              domicilios={gestionables}
              empleados={empleados}
              onDesactivar={handleSolicitarDesactivar}
            />
          </div>
        )}
      </div>

      {/* ── Modales ── */}
      {modal?.type === "ver" && (
        <ModalVerDomicilio
          pedido={modal.pedido}
          emp={empleados.find(e => e.id === modal.pedido.idEmpleado)}
          domicilios={gestionables}
          onClose={() => setModal(null)}
          onReasignar={ped => setModal({ type: "reasignar", pedido: ped })}
          onObservaciones={ped => setModal({ type: "obs", pedido: ped })}
        />
      )}
      {modal?.type === "reasignar" && (
        <ModalReasignar
          pedido={modal.pedido}
          empleados={empleados}
          repartidores={repartidores}
          onClose={() => setModal(null)}
          onConfirm={handleReasignar}
        />
      )}
      {modal?.type === "obs" && (
        <ModalObservaciones
          pedido={modal.pedido}
          onClose={() => setModal(null)}
          onConfirm={handleObservaciones}
        />
      )}
      {modal?.type === "confirmar-desactivar" && (
        <ModalConfirmarDesactivar
          usuario={modal.usuario}
          pedidosActivos={modal.pedidosActivos}
          onClose={() => setModal(null)}
          onConfirm={handleConfirmarDesactivar}
        />
      )}
      {modal?.type === "registrarCobro" && (
        <ModalRegistrarCobro
          pedido={modal.pedido}
          saving={actionSaving}
          onClose={() => setModal(null)}
          onConfirm={handleRegistrarCobro}
        />
      )}

      {modal?.type === "cambiarEstado" && (
        <ModalCambiarEstado
          pedido={modal.pedido}
          onClose={() => setModal(null)}
          onSave={handleCambiarEstado}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}