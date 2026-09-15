import { useState, useRef, useEffect } from "react";
import { Bell, X, Search, Check, Eye, Trash2, BellOff } from "lucide-react";
import {
  useNotificaciones,
  TIPOS, TIPO_LABELS, TIPO_ICONS, TIPO_COLORS,
} from "../context/NotificacionesContext";
import NotificacionDetalle from "./NotificacionDetalle";
import "./notificaciones.css";

/* ── helpers ─────────────────────────────────────────────── */
const fmtFecha = (iso) => {
  const d = new Date(iso);
  const hoy = new Date();
  const diff = Math.floor((hoy - d) / 60000); // minutos
  if (diff < 1)   return "Ahora";
  if (diff < 60)  return `Hace ${diff} min`;
  if (diff < 1440) return `Hace ${Math.floor(diff / 60)}h`;
  return d.toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
};

/* ══════════════════════════════════════════════════════════
   PANEL PRINCIPAL
══════════════════════════════════════════════════════════ */
export default function NotificacionesPanel({ isOpen, onClose }) {
  const {
    notificaciones, noLeidas,
    marcarLeida, marcarTodasLeidas, eliminarNotificacion, eliminarTodasNotificaciones,
    filtrar,
  } = useNotificaciones();

  // HU_03 — filtros (CA_03_01..05)
  const [filtroTipo,   setFiltroTipo]   = useState("");
  const [filtroEstado, setFiltroEstado] = useState("");
  const [busqueda,     setBusqueda]     = useState("");
  const [detalle,      setDetalle]      = useState(null); // HU_02 — ver detalle CA_02_04
  const panelRef = useRef(null);

  // Obtener usuario para filtrar las opciones del select
  const user = JSON.parse(localStorage.getItem("usuario") || "null");
  const rol = user?.rol?.toLowerCase();
  const isAdmin        = user?.tipo === "empleado" && (rol === "admin" || rol === "administrador");
  const isCocinero     = ["cocina", "cocinero", "produccion", "producción"].includes(rol);
  const isDomiciliario = rol === "domiciliario";

  // Tipos relevantes según rol
  const tiposRelevantes = Object.entries(TIPO_LABELS).filter(([tipo]) => {
    if (isAdmin) return true;
    if (isCocinero) return [TIPOS.PEDIDO_NUEVO, TIPOS.PEDIDO_EN_PRODUCCION].includes(tipo);
    if (isDomiciliario) return [TIPOS.DOMICILIO_ASIGNADO, TIPOS.PEDIDO_CANCELADO].includes(tipo);
    // Cliente
    return [
      TIPOS.PEDIDO_CONFIRMADO, TIPOS.PEDIDO_ENTREGADO, TIPOS.PEDIDO_CANCELADO,
      TIPOS.DEVOLUCION_APROBADA, TIPOS.DEVOLUCION_RECHAZADA,
      TIPOS.PEDIDO_EN_PRODUCCION, TIPOS.FECHA_PROPUESTA, TIPOS.ESPERANDO_PAGO,
      TIPOS.PEDIDO_EN_CAMINO, TIPOS.COMPROBANTE_RECHAZADO,
    ].includes(tipo);
  });

  // Cerrar con Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Cerrar al hacer clic fuera
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      // Si el clic es fuera del panel Y fuera de cualquier modal, cerramos
      const isOutsidePanel = panelRef.current && !panelRef.current.contains(e.target);
      const isClickingModal = e.target.closest(".modal-overlay") || e.target.closest(".modal-box") || e.target.closest(".notif-overlay");
      
      if (isOutsidePanel && !isClickingModal) {
        onClose();
      }
    };
    setTimeout(() => document.addEventListener("mousedown", handler), 50);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen, onClose]);

  // CA_03_03 — filtros combinados, CA_03_04 — lista se actualiza
  const lista = filtrar({ tipo: filtroTipo, estado: filtroEstado, texto: busqueda });

  // CA_03_05 — limpiar filtros
  const limpiarFiltros = () => { setFiltroTipo(""); setFiltroEstado(""); setBusqueda(""); };
  const hayFiltros = filtroTipo || filtroEstado || busqueda;

  const handleVerDetalle = (notif) => {
    marcarLeida(notif.id); // CA_02_05 — marcar como leída al ver
    setDetalle(notif);
  };

  return (
    <>
      {/* Overlay */}
      {isOpen && <div className="notif-overlay" onClick={onClose} />}

      {/* Panel */}
      <aside ref={panelRef} className={`notif-panel ${isOpen ? "notif-panel--open" : ""}`}>

        {/* ── Header ── */}
        <div className="notif-panel__header">
          <div className="notif-panel__title-row">
            <span className="notif-panel__title" style={{display:"flex",alignItems:"center",gap:6}}><Bell size={16} /> Notificaciones</span>
            {noLeidas > 0 && (
              <span className="notif-badge-header">{noLeidas} nueva{noLeidas > 1 ? "s" : ""}</span>
            )}
          </div>
          <div className="notif-panel__header-actions">
            {noLeidas > 0 && (
              <button className="notif-link-btn" onClick={marcarTodasLeidas}>
                Marcar todas como leídas
              </button>
            )}
            {lista.length > 0 && (
              <button className="notif-link-btn notif-link-btn--danger" onClick={eliminarTodasNotificaciones} data-tooltip="Eliminar todas las notificaciones" style={{display:"flex",alignItems:"center",gap:4}}>
                <Trash2 size={12} /> Eliminar todas
              </button>
            )}
            <button className="notif-close-btn" onClick={onClose} data-tooltip="Cerrar panel" style={{display:"flex",alignItems:"center",justifyContent:"center"}}><X size={16} /></button>
          </div>
        </div>

        {/* ── Buscador ── */}
        <div className="notif-search-wrap">
          <span className="notif-search-icon"><Search size={15} /></span>
          <input
            className="notif-search-input"
            placeholder="Buscar notificación..."
            value={busqueda}
            onChange={e => setBusqueda(e.target.value)}
          />
        </div>

        {/* ── HU_03 Filtros — CA_03_01 tipo, CA_03_02 estado ── */}
        <div className="notif-filters">
          {/* Filtro tipo — CA_03_01 */}
          <select
            className="notif-select"
            value={filtroTipo}
            onChange={e => setFiltroTipo(e.target.value)}
          >
            <option value="">Todos los tipos</option>
            {tiposRelevantes.map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>

          {/* Filtro estado — CA_03_02 */}
          <select
            className="notif-select"
            value={filtroEstado}
            onChange={e => setFiltroEstado(e.target.value)}
          >
            <option value="">Todos los estados</option>
            <option value="no_leida">No leídas</option>
            <option value="leida">Leídas</option>
          </select>

          {/* CA_03_05 — limpiar */}
          {hayFiltros && (
            <button className="notif-clear-btn" onClick={limpiarFiltros} data-tooltip="Limpiar filtros activos" style={{display:"flex",alignItems:"center",gap:4}}>
              <X size={13} /> Limpiar
            </button>
          )}
        </div>

        {/* ── HU_04 Lista — CA_04_01..05 ── */}
        <div className="notif-list">
          {lista.length === 0 ? (
            <div className="notif-empty">
              <span className="notif-empty__icon"><BellOff size={48} strokeWidth={1} style={{color:"#bdbdbd"}}/></span>
              <p className="notif-empty__text">
                {hayFiltros ? "Sin resultados con estos filtros" : "No hay notificaciones"}
              </p>
            </div>
          ) : (
            lista.map(n => (
              <NotifItem
                key={n.id}
                notif={n}
                onVer={handleVerDetalle}
                onMarcarLeida={marcarLeida}
                onEliminar={eliminarNotificacion}
              />
            ))
          )}
        </div>

        {/* ── Footer con contador ── */}
        {lista.length > 0 && (
          <div className="notif-panel__footer">
            <span className="notif-count-text">
              {lista.length} notificación{lista.length > 1 ? "es" : ""}
              {hayFiltros ? " (filtradas)" : ""}
            </span>
          </div>
        )}
      </aside>

      {/* HU_02 — Detalle CA_02_01..05 */}
      {detalle && (
        <NotificacionDetalle
          notif={detalle}
          onClose={() => setDetalle(null)}
          onMarcarLeida={marcarLeida}
        />
      )}
    </>
  );
}

/* ══════════════════════════════════════════════════════════
   ITEM DE NOTIFICACIÓN
   CA_02_02 — info básica del evento
   CA_04_01 — muestra todas
   CA_04_02 — visualiza fecha y tipo
   CA_04_03 — ordenadas por más recientes
   CA_04_04 — permite cambiar estado
   CA_04_05 — actualiza automáticamente
══════════════════════════════════════════════════════════ */
function NotifItem({ notif, onVer, onMarcarLeida, onEliminar }) {
  const color = TIPO_COLORS[notif.tipo] || "#2e7d32";

  return (
    <div
      className={`notif-item ${notif.leida ? "notif-item--leida" : "notif-item--nueva"}`}
      style={{ "--notif-color": color }}
    >
      <div className="notif-item__accent" />

      <div className="notif-item__body" onClick={() => onVer(notif)}>
        <div className="notif-item__top">
          <span className="notif-item__icon">{(() => { const Icon = TIPO_ICONS[notif.tipo]; return Icon ? <Icon size={14} /> : null; })()}</span>
          <span className="notif-item__tipo" style={{ color }}>
            {TIPO_LABELS[notif.tipo]}
          </span>
          {/* CA_04_02 — fecha */}
          <span className="notif-item__fecha">{fmtFecha(notif.fecha)}</span>
          {!notif.leida && <span className="notif-item__dot" />}
        </div>

        {/* CA_02_02 — info básica */}
        <p className="notif-item__titulo">{notif.titulo}</p>
        <p className="notif-item__msg">{notif.mensaje}</p>
      </div>

      <div className="notif-item__actions">
        {/* CA_04_04 / CA_05_01 — marcar leída sin eliminar */}
        {!notif.leida && (
          <button
            className="notif-item__btn notif-item__btn--read"
            onClick={e => { e.stopPropagation(); onMarcarLeida(notif.id); }}
            data-tooltip="Marcar como leída"
          >
            <Check size={13} />
          </button>
        )}
        <button
          className="notif-item__btn notif-item__btn--view"
          onClick={e => { e.stopPropagation(); onVer(notif); }}
          data-tooltip="Ver detalle"
        >
          <Eye size={14} />
        </button>
        <button
          className="notif-item__btn notif-item__btn--del"
          onClick={e => { e.stopPropagation(); onEliminar(notif.id); }}
          data-tooltip="Eliminar notificación"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}