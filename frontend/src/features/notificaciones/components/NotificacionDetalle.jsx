import { useState } from "react";
import { X, Calendar, AlertTriangle, Check, CheckCircle2, Info, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useNotificaciones, TIPO_ICONS, TIPO_LABELS, TIPO_COLORS, TIPOS } from "../context/NotificacionesContext";

import { fmtFechaHora as fmtFechaCompleta } from "../../../utils/dateUtils.js";
import { aceptarFechaProduccion } from "../../../services/pedidosService.js";
import "./notificaciones.css";

/* Mapeo de rutas para navegación rápida */
const RUTA_MAP = {
  [TIPOS.STOCK_MINIMO]:         "/admin/gestion-insumos",
  [TIPOS.STOCK_AGOTADO]:        "/admin/gestion-insumos",
  [TIPOS.LOTE_POR_VENCER]:      "/admin/gestion-insumos",
  [TIPOS.LOTE_VENCIDO]:         "/admin/gestion-insumos",
  [TIPOS.PEDIDO_NUEVO]:         "/admin/pedidos",
  [TIPOS.COMPRA_PENDIENTE]:     "/admin/compras",
  [TIPOS.DEVOLUCION_PENDIENTE]: "/admin/devoluciones",
  [TIPOS.SISTEMA]:              "/admin",
  // Rutas del cliente
  [TIPOS.PEDIDO_CONFIRMADO]:    "/cliente/pedidos",
  [TIPOS.PEDIDO_ENTREGADO]:     "/cliente/pedidos",
  [TIPOS.PEDIDO_CANCELADO]:     "/cliente/pedidos",
  [TIPOS.DEVOLUCION_APROBADA]:  "/cliente/devoluciones",
  [TIPOS.DEVOLUCION_RECHAZADA]: "/cliente/devoluciones",
  [TIPOS.PEDIDO_EN_PRODUCCION]: "/cliente/pedidos",
  [TIPOS.FECHA_PROPUESTA]:      "/cliente/pedidos",
  [TIPOS.FECHA_RECHAZADA]:      "/admin/pedidos",
};

export default function NotificacionDetalle({ notif, onClose }) {
  const { eliminarNotificacion } = useNotificaciones();
  const navigate = useNavigate();
  const [accionando, setAccionando] = useState(null); // "aceptar" | "rechazar"
  const [accionError, setAccionError] = useState("");
  const [accionDone,  setAccionDone]  = useState(false);

  if (!notif) return null;

  const color = TIPO_COLORS[notif.tipo] || "#2e7d32";
  const ruta  = RUTA_MAP[notif.tipo] || "/dashboard";

  const esFechaPropuesta = notif.tipo === TIPOS.FECHA_PROPUESTA;

  const handleIrAlRecurso = () => {
    navigate(ruta);
    onClose();
  };

  const handleListo = () => {
    eliminarNotificacion(notif.id);
    onClose();
  };

  const handleAceptar = async () => {
    if (!notif.idPedido) { setAccionError("No se encontró el pedido asociado."); return; }
    setAccionando("aceptar");
    setAccionError("");
    try {
      await aceptarFechaProduccion(notif.idPedido);
      setAccionDone(true);
      eliminarNotificacion(notif.id);
    } catch (e) {
      setAccionError(e.message || "No se pudo aceptar la fecha");
    } finally {
      setAccionando(null);
    }
  };

  // Rechazar ya no es de un clic (3.4): el cliente tiene que proponer su
  // propia fecha final y decir el motivo, así que este botón lleva al
  // formulario completo de "Mis pedidos" en vez de duplicarlo acá.
  const handleRechazar = () => {
    navigate("/cliente/pedidos");
    onClose();
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm notif-detalle" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="modal-header" style={{ background: `linear-gradient(135deg, ${color} 0%, ${color}cc 100%)` }}>
          <div>
            <p className="modal-header__eyebrow">DETALLE DE NOTIFICACIÓN</p>
            <h2 className="modal-header__title" style={{display:"flex",alignItems:"center",gap:6}}>
              {(() => { const Icon = TIPO_ICONS[notif.tipo]; return Icon ? <Icon size={16} /> : null; })()}
              {TIPO_LABELS[notif.tipo]}
            </h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} style={{display:"flex",alignItems:"center",justifyContent:"center"}}><X size={16} /></button>
        </div>

        {/* Body */}
        <div className="modal-body notif-detalle__body">
          <div className="notif-detalle__pill-row">
            <span className="notif-detalle__pill" style={{ background: `${color}18`, color, display:"inline-flex", alignItems:"center", gap:5 }}>
              {(() => { const Icon = TIPO_ICONS[notif.tipo]; return Icon ? <Icon size={13} /> : null; })()}
              {TIPO_LABELS[notif.tipo]}
            </span>
            <span className="notif-detalle__fecha">{fmtFechaCompleta(notif.fecha)}</span>
          </div>

          <h3 className="notif-detalle__titulo">{notif.titulo}</h3>
          <p  className="notif-detalle__mensaje">{notif.mensaje}</p>

          {notif.refNombre && (
            <div className="notif-detalle__ref">
              <span className="notif-detalle__ref-label">Referencia</span>
              <span className="notif-detalle__ref-value">{notif.refNombre}</span>
            </div>
          )}

          {esFechaPropuesta && !accionDone && (
            <div style={{ marginTop: 20, background: "linear-gradient(135deg,#e8eaf6 0%,#ede7f6 100%)", border: "2px solid #9fa8da", borderRadius: 14, padding: "16px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <Calendar size={20} />
                <p style={{ fontWeight: 800, fontSize: 13, color: "#283593", margin: 0 }}>¿Confirmas esta fecha de entrega?</p>
              </div>

              {notif.fechaEntrega && (
                <div style={{ background: "#fff", border: "1.5px solid #9fa8da", borderRadius: 10, padding: "10px 14px", marginBottom: 10, textAlign: "center" }}>
                  <p style={{ fontSize: 10, fontWeight: 700, color: "#7986cb", letterSpacing: 1, textTransform: "uppercase", margin: "0 0 4px" }}>
                    Fecha estimada de entrega
                  </p>
                  <p style={{ fontSize: 17, fontWeight: 900, color: "#283593", margin: 0, lineHeight: 1.25, textTransform: "capitalize" }}>
                    {new Date(notif.fechaEntrega.slice(0, 10) + "T00:00:00").toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                  </p>
                </div>
              )}

              <p style={{ fontSize: 12, color: "#3949ab", marginBottom: 12 }}>
                Si no puedes recibirlo ese día, proponé tu propia fecha desde "Mis pedidos".
              </p>
              {accionError && (
                <p style={{ fontSize: 11, color: "#c62828", fontWeight: 700, marginBottom: 8, display:"flex", alignItems:"center", gap:4 }}><AlertTriangle size={11} />{accionError}</p>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  disabled={!!accionando}
                  onClick={handleAceptar}
                  style={{ flex: 1, padding: "11px 0", borderRadius: 10, border: "none", background: "#2e7d32", color: "#fff", fontWeight: 800, fontSize: 13, cursor: accionando ? "not-allowed" : "pointer" }}
                >
                  {accionando === "aceptar" ? "Aceptando…" : <><Check size={14} /> Sí, acepto</>}
                </button>
                <button
                  disabled={!!accionando}
                  onClick={handleRechazar}
                  style={{ flex: 1, padding: "11px 0", borderRadius: 10, border: "none", background: "#c62828", color: "#fff", fontWeight: 800, fontSize: 13, cursor: accionando ? "not-allowed" : "pointer" }}
                >
                  <X size={14} /> Proponer otra fecha
                </button>
              </div>
            </div>
          )}

          {esFechaPropuesta && accionDone && (
            <div className="info-box info-box--success" style={{ marginTop: 20 }}>
              <CheckCircle2 size={16} className="info-box__icon" />
              <span className="info-box__text">Respuesta enviada. Puedes cerrar esta notificación.</span>
            </div>
          )}

          {!esFechaPropuesta && (
            <div className="info-box info-box--info" style={{ marginTop: 20 }}>
              <Info size={16} className="info-box__icon" />
              <span className="info-box__text">
                Accede directamente al módulo relacionado para gestionar este evento.
              </span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer" style={{ gap: 10 }}>
          {!esFechaPropuesta && (
            <button
              className="btn-save"
              style={{ background: color, border: "none", color: "#fff", display:"inline-flex", alignItems:"center", gap:6 }}
              onClick={handleIrAlRecurso}
            >
              <ExternalLink size={14} /> Ir al módulo
            </button>
          )}

          <button
            className="btn-save"
            onClick={handleListo}
            data-tooltip="Marcar como completado y eliminar de la lista"
          >
            <Check size={14} /> Listo
          </button>

          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}