import { esEmpleadoRepartidor } from "../../../utils/roles.js";
import { useState, useEffect, useRef } from "react";
import { flushSync } from "react-dom";
import { useNavigate, useLocation } from "react-router-dom";
import { fmtFecha, getRecordDate } from "../../../utils/dateUtils.js";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import SelectorBarrioEntrega from "../../../shared/components/SelectorBarrioEntrega";
import { descargarFacturaPedido } from "../../../utils/facturaGenerator.js";
import { getPedidos, getPedido, getHistorialPedidos, confirmarPedido, cancelarPedido, crearPedido, editarPedido, cambiarEstadoVenta, proponerFechaProduccion, aprobarFechaDirecta, registrarPagoFinal, aprobarComprobante, rechazarComprobante, registrarCobroPedido, resolverEscaladoAcuerdo, resolverEscaladoCancelar, aprobarPagoFinal, rechazarPagoFinal } from "../../../services/pedidosService.js";
import { subirImagenCloudinary } from "../../../utils/cloudinary.js";
import { asignarRepartidor } from "../../../services/domiciliosService.js";
import { registrarSalida } from "../../../services/salidasService.js";
import { getUsuarios } from "../../../services/usuariosService.js";
import { getProductos } from "../../../services/productosService.js";
import CrearPedido from "./CrearPedido.jsx";
import EditarPedido from "./EditarPedido.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { puedeEditarsePedido } from "./permisosEdicion.js";
import { esPagoEfectivo, esPagoMixto, esPagoTransferencia, montoACobrar, montoTransferido } from "../../../utils/metodosPago.js";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import ImageLightbox from "../../../shared/components/ImageLightbox.jsx";
import { formatCOP } from "../../../utils/formato.js";
import {
  Trash2, Truck, Package,
  RotateCcw, X, AlertCircle,
  CheckCircle2, ArrowRight, MapPin, Search,
  Eye, Pencil, Check, Calendar, Store, Bike,
  Banknote, CreditCard, Clock, Ban, Phone, Mail,
  PenLine, ClipboardList, FileText, Paperclip, XCircle,
  Info, Building2, AlertTriangle, Scale
} from 'lucide-react';
import "./Pedidos.css";

/* ─── Datos de transferencia ─────────────────────────────── */
const CUENTA_TRANSFERENCIA = {
  banco:   "Bancolombia",
  titular: "TostonApp S.A.S",
  tipo:    "Ahorros",
  numero:  import.meta.env.VITE_CUENTA_TRANSFERENCIA ?? "54213570938",
};

/* ─── Helpers ────────────────────────────────────────────── */
const fmt = formatCOP;

const PER_PAGE = 5;

const normalizeProductoId = (value) => {
  if (value === null || value === undefined || value === "") return null;
  return String(value).trim();
};

const esProductoConProduccion = (producto) => {
  const rawValue = producto?.Requiere_Produccion ?? producto?.requiereProduccion ?? producto?.requiere_produccion;
  return rawValue === 1 || rawValue === true || rawValue === "1" || rawValue === "true";
};

const ESTADO_CONFIG = {
  "Pendiente":               { bg: "#fff8e1", color: "#f9a825", border: "#ffe082", dot: "#f9a825" },
  "Pendiente de Aprobación": { bg: "#fff8e1", color: "#f9a825", border: "#ffe082", dot: "#f9a825" },
  "Pendiente de producción": { bg: "#fff3e0", color: "#e65100", border: "#ffcc80", dot: "#ef6c00" },
  "En producción":           { bg: "#e3f2fd", color: "#1565c0", border: "#90caf9", dot: "#1976d2" },
  "Esperando pago":          { bg: "#fff3e0", color: "#ef6c00", border: "#ffcc80", dot: "#fb8c00" },
  "Confirmado":              { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
  "En Alistamiento":         { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
  "Listo":                   { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
  "Asignado":                { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
  "En camino":               { bg: "#f3e5f5", color: "#6a1b9a", border: "#ce93d8", dot: "#8e24aa" },
  "Fecha propuesta":         { bg: "#e8eaf6", color: "#283593", border: "#9fa8da", dot: "#3949ab" },
  "Fecha rechazada":         { bg: "#fff3e0", color: "#e65100", border: "#ffcc80", dot: "#fb8c00" },
  "Escalado a admin":        { bg: "#fce4ec", color: "#880e4f", border: "#f48fb1", dot: "#e91e63" },
  "Parcialmente entregado":  { bg: "#e8f5e9", color: "#1b5e20", border: "#a5d6a7", dot: "#43a047" },
  "Cancelado":               { bg: "#ffebee", color: "#c62828", border: "#ef9a9a", dot: "#e53935" },
  "Entregado":               { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
  "Retenido en tienda":      { bg: "#fff3e0", color: "#bf360c", border: "#ffcc80", dot: "#e64a19" },
};

const getEstadoDisplay = (pedido) => {
  if (pedido?.ordenes_en_espera > 0 && ["En producción", "Confirmado"].includes(pedido?.estado)) {
    return "Pendiente de producción";
  }
  const estado = pedido?.estado ?? "Pendiente";
  // "Pendiente" solo existe hoy para pedidos que necesitan aprobación de
  // planta (fecha de entrega obligatoria); "Confirmado" sin producción es
  // simple alistamiento, sin nada que fabricar. Es solo la etiqueta: el
  // valor real de estado (para filtros, comparaciones, endpoints) no cambia.
  if (estado === "Pendiente" && pedido?.requiereProduccion) return "Pendiente de Aprobación";
  if (estado === "Confirmado" && !pedido?.requiereProduccion) return "En Alistamiento";
  return estado;
};

/* ─── EstadoBadge ────────────────────────────────────────── */
function EstadoBadge({ estado }) {
  const c = ESTADO_CONFIG[estado] || { bg: "#f5f5f5", color: "#757575", border: "#e0e0e0", dot: "#bdbdbd" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
      borderRadius: 20, padding: "3px 10px", fontSize: 10, fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.05em",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot, flexShrink: 0 }} />
      {estado}
    </span>
  );
}

/* ─── Toast ──────────────────────────────────────────────── */
function Toast({ toast }) {
  if (!toast) return null;
  const bg = toast.type === "error" ? "bg-red-600" : toast.type === "warn" ? "bg-orange-600" : "bg-green-600";
  return (
    <div className={`fixed bottom-8 right-8 ${bg} text-white px-6 py-3 rounded-xl shadow-2xl z-[30000] flex items-center gap-3 animate-in slide-in-from-right`}>
      {toast.type === "error" ? <X size={18} /> : toast.type === "warn" ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
      <span className="font-bold text-sm">{toast.message}</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — CAMBIAR ESTADO (Confirmación)
   ═══════════════════════════════════════════════════════════ */
function ModalConfirmarEstado({ pedido, nuevoEstado, onClose, onConfirm }) {
  if (!pedido || !nuevoEstado) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: '28px', maxWidth: '420px' }}>
        
        {/* Cabecera */}
        <div className="modal-header shrink-0" style={{ background: 'linear-gradient(135deg, var(--green-800) 0%, var(--green-700) 100%)', padding: '20px 24px' }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Confirmar Cambio</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">Pedido #{pedido.numero}</p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>

        <div className="modal-body p-6 text-center">
          <div className="bg-amber-50 border-2 border-amber-200 p-5 rounded-3xl mb-6">
            <div className="w-12 h-12 bg-amber-100 rounded-2xl flex items-center justify-center mx-auto mb-3 text-amber-600">
              <RotateCcw size={28} />
            </div>
            <h3 className="text-sm font-black text-amber-900 uppercase tracking-tight">¿Actualizar estado del pedido?</h3>
            <p className="text-xs text-amber-700/80 mt-2 font-medium">Estás a punto de avanzar este pedido en el flujo de ventas.</p>
          </div>

          <div className="flex items-center justify-between px-6 py-4 bg-gray-50 rounded-2xl border border-gray-100 relative overflow-hidden mb-6">
            <div className="text-center flex-1">
              <p className="text-[8px] font-black text-gray-400 uppercase tracking-widest mb-2">Actual</p>
              <EstadoBadge estado={getEstadoDisplay(pedido)} />
            </div>
            <div className="px-4 text-gray-300 animate-pulse">
              <ArrowRight size={20} strokeWidth={3} />
            </div>
            <div className="text-center flex-1">
              <p className="text-[8px] font-black text-gray-400 uppercase tracking-widest mb-2">Nuevo</p>
              <EstadoBadge estado={nuevoEstado} />
            </div>
          </div>

          <div className="space-y-2">
            <button 
              onClick={() => onConfirm(pedido.id, nuevoEstado)}
              className="btn-primary w-full py-4 text-xs font-black uppercase tracking-widest shadow-lg"
              style={{ background: 'linear-gradient(135deg, var(--green-700) 0%, var(--green-600) 100%)' }}
            >
              Confirmar y Actualizar
            </button>
            <button 
              onClick={onClose}
              className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* Comprobante adjunto: aviso + imagen con zoom. Se usa para el del pedido y
   para el del anticipo, que el cliente sube por separado desde su checkout. */
function ComprobanteAdjunto({ url, titulo }) {
  return (
    <div>
      <div className="info-box info-box--success" style={{ marginBottom: 10 }}>
        <span className="info-box__icon"><CheckCircle2 size={16} /></span>
        <span className="info-box__text">{titulo}</span>
      </div>
      <ImageLightbox
        src={url}
        alt={titulo}
        label="Ver imagen completa"
        thumbStyle={{ width: "100%", maxHeight: 320, objectFit: "contain", borderRadius: 10, border: "1.5px solid #c8e6c9", background: "#f9fdf9", cursor: "zoom-in" }}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — VER DETALLE
   ═══════════════════════════════════════════════════════════ */
function ModalVerPedido({ pedido: pedidoProp, empleados, onClose, onEdit }) {
  const [pedido, setPedido] = useState(pedidoProp);

  useEffect(() => {
    let cancelado = false;
    getPedido(pedidoProp.id)
      .then(data => { if (!cancelado) setPedido(data); })
      .catch(() => {});
    return () => { cancelado = true; };
  }, [pedidoProp.id]);

  const navigate = useNavigate();
  const comprobantes = [
    { url: pedido.comprobante || pedido.anticipo_comprobante_url, titulo: "Comprobante de pago adjuntado." },
    { url: pedido.pago_final_comprobante_url,                     titulo: "Comprobante del saldo adjuntado." },
  ].filter((c, i, todos) => c.url && todos.findIndex(o => o.url === c.url) === i);
  const esMixto         = esPagoMixto(pedido.metodo_pago);
  const esTransferencia = esPagoTransferencia(pedido.metodo_pago);
  // Total $0 con método transferencia → el crédito cubrió todo; no hay nada
  // que transferir ni comprobante que pedir.
  const pagoTotalConCredito = esTransferencia && Number(pedido.total || 0) === 0;
  const epInicial = pedido.estado_pago;
  const [tab, setTab] = useState(
    (esTransferencia && !pagoTotalConCredito) || epInicial === "pendiente_validacion" || epInicial === "comprobante_rechazado"
      ? "pago"
      : "resumen"
  );

  const emp = empleados.find(e => e.id === pedido.idEmpleado);
  if (!pedido) return null;

  return (
    <div className="modal-overlay">
      <div
        className="modal-box modal-box--wide"
        onClick={e => e.stopPropagation()}
        style={{ maxHeight: "calc(100vh - 40px)", display: "flex", flexDirection: "column" }}
      >
        {/* Header */}
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Pedido</p>
            <h2 className="modal-header__title">{pedido.numero}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <EstadoBadge estado={getEstadoDisplay(pedido)} />
            <button className="modal-close-btn" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        {/* Tabs */}
        <div className="ver-ped-tabs">
          <button className={`ver-ped-tab${tab === "resumen"   ? " ver-ped-tab--active" : ""}`} onClick={() => setTab("resumen")} style={{display:"inline-flex",alignItems:"center",gap:5}}><ClipboardList size={14} /> Resumen</button>
          <button className={`ver-ped-tab${tab === "productos" ? " ver-ped-tab--active" : ""}`} onClick={() => setTab("productos")} style={{display:"inline-flex",alignItems:"center",gap:5}}><Package size={14} /> Productos</button>
          <button className={`ver-ped-tab${tab === "pago"      ? " ver-ped-tab--active" : ""}`} onClick={() => setTab("pago")} style={{display:"inline-flex",alignItems:"center",gap:5}}>
            <CreditCard size={14} /> Pago{" "}
            {esTransferencia && <span style={{ marginLeft: 4, fontSize: 10, fontWeight: 700, background: "#e3f2fd", color: "#1565c0", border: "1px solid #90caf9", borderRadius: 4, padding: "1px 5px" }}>Transferencia</span>}
            {(() => {
              const ep = pedido.estado_pago;
              const badges = {
                pagado_completo:      { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", label: "Completo" },
                anticipo_pagado:      { bg: "#fff8e1", color: "#e65100", border: "#ffe082", label: "Anticipo" },
                pendiente_validacion: { bg: "#e3f2fd", color: "#1565c0", border: "#90caf9", label: "Validar" },
                comprobante_rechazado:{ bg: "#ffebee", color: "#c62828", border: "#ef9a9a", label: "Rechazado" },
              };
              const b = badges[ep];
              return b ? <span style={{ marginLeft: 4, fontSize: 10, fontWeight: 700, background: b.bg, color: b.color, border: `1px solid ${b.border}`, borderRadius: 4, padding: "1px 5px" }}>{b.label}</span> : null;
            })()}
          </button>
        </div>

        {/* Body */}
        <div className="modal-body" style={{ flex: 1, overflowY: "auto" }}>

          {/* ── Tab Resumen ── */}
          {tab === "resumen" && (
            <div className="form-grid-2" style={{ gap: 24 }}>
              {/* Banner: fecha deseada por el cliente cuando está pendiente de negociación */}
              {pedido.estado === "Pendiente" && pedido.requiereFechaPropuesta && pedido.fecha_propuesta && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <div className="info-box info-box--info" style={{ borderColor: "#90caf9", background: "#e3f2fd" }}>
                    <span className="info-box__icon"><Calendar size={16} /></span>
                    <div>
                      <span className="info-box__label">Fecha de entrega deseada por el cliente</span>
                      <span className="info-box__text" style={{ display: "block", fontWeight: 700, color: "#1565c0", fontSize: 15, marginTop: 2 }}>
                        {fmtFecha(pedido.fecha_propuesta)}
                      </span>
                    </div>
                  </div>
                </div>
              )}
              {/* Cliente */}
              <div>
                <p className="section-label">Información del Cliente</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div className="ver-ped-field">
                    <span className="ver-ped-field__label">Nombre</span>
                    <span className="ver-ped-field__value">{pedido.cliente?.nombre || "—"}</span>
                  </div>
                  <div className="ver-ped-field">
                    <span className="ver-ped-field__label">Correo</span>
                    <span className="ver-ped-field__value">
                      {pedido.cliente?.correo
                        ? <a href={`mailto:${pedido.cliente.correo}`} style={{ color: "#1565c0", textDecoration: "none", fontWeight: 600, display:"inline-flex", alignItems:"center", gap:4 }}><Mail size={12} /> {pedido.cliente.correo}</a>
                        : "—"}
                    </span>
                  </div>
                  <div className="ver-ped-field">
                    <span className="ver-ped-field__label">Teléfono</span>
                    <span className="ver-ped-field__value">
                      {pedido.cliente?.telefono
                        ? <a href={`https://wa.me/${pedido.cliente.telefono.replace(/\D/g, "")}`} target="_blank" rel="noopener noreferrer" style={{ color: "#2e7d32", textDecoration: "none", fontWeight: 600, display:"inline-flex", alignItems:"center", gap:4 }}><Phone size={12} /> {pedido.cliente.telefono}</a>
                        : "—"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Entrega */}
              <div>
                <p className="section-label">Entrega</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div className="ver-ped-field">
                    <span className="ver-ped-field__label">Tipo</span>
                    <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5}}>{pedido.domicilio ? <><Bike size={14} /> Domicilio</> : <><Store size={14} /> Recogida en tienda</>}</span>
                  </div>
                  {pedido.domicilio && (
                    <>
                      <div className="ver-ped-field">
                        <span className="ver-ped-field__label">Dirección</span>
                        <span className="ver-ped-field__value">{pedido.direccion_entrega || "—"}</span>
                      </div>
                      {(pedido.municipio || pedido.departamento) && (
                        <div className="ver-ped-field">
                          <span className="ver-ped-field__label">Ciudad</span>
                          <span className="ver-ped-field__value">{[pedido.municipio, pedido.departamento].filter(Boolean).join(", ")}</span>
                        </div>
                      )}
                      <div className="ver-ped-field">
                        <span className="ver-ped-field__label">Domiciliario</span>
                        <span className="ver-ped-field__value">
                          {pedido.nombre_domiciliario
                            || (emp ? `${emp.nombre} ${emp.apellidos}` : null)
                            || (pedido.estado === "Entregado" ? "Sin información" : "Sin asignar")}
                        </span>
                      </div>
                      {pedido.observaciones_domicilio && (
                        <div className="info-box info-box--warn" style={{ marginTop: 4 }}>
                          <span className="info-box__icon"><PenLine size={16} /></span>
                          <div>
                            <span className="info-box__label">Observaciones del cliente</span>
                            <span className="info-box__text" style={{ display: "block" }}>{pedido.observaciones_domicilio}</span>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                  <div className="ver-ped-field">
                    <span className="ver-ped-field__label">Fecha del pedido</span>
                    <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5}}><Calendar size={14} /> {fmtFecha(pedido.fecha_pedido)}</span>
                  </div>
                  {pedido.fecha_propuesta && (
                    <div className="ver-ped-field">
                      <span className="ver-ped-field__label">
                        {['Fecha propuesta', 'Fecha rechazada', 'Escalado a admin'].includes(pedido.estado)
                          ? 'Fecha propuesta al cliente'
                          : 'Fecha deseada por el cliente'}
                      </span>
                      <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5,color:"#1565c0",fontWeight:700}}>
                        <Calendar size={14} /> {fmtFecha(pedido.fecha_propuesta)}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Notas (ancho completo) */}
              {pedido.notas && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <div className="info-box info-box--warn">
                    <span className="info-box__icon"><PenLine size={16} /></span>
                    <div>
                      <span className="info-box__label">Notas del pedido</span>
                      <span className="info-box__text" style={{ display: "block" }}>{pedido.notas}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Enlace producción (ancho completo) */}
              {pedido.orden_produccion && (
                <div style={{ gridColumn: "1 / -1" }}>
                  <button
                    className="info-box info-box--info"
                    style={{ width: "100%", cursor: "pointer", textAlign: "left", border: "1px solid #90caf9" }}
                    // Por id, que es lo que la lista de órdenes conoce del
                    // pedido. Con el número formateado no coincidía nada.
                    onClick={() => { onClose(); navigate(`/admin/ordenes-produccion?search=${pedido.id}`); }}
                  >
                    <span className="info-box__icon"><Package size={16} /></span>
                    <div>
                      <span className="info-box__label">Producción activa</span>
                      <span className="info-box__text" style={{ display: "block" }}>Ver detalles de fabricación →</span>
                    </div>
                  </button>
                </div>
              )}

            </div>
          )}

          {/* ── Tab Productos ── */}
          {tab === "productos" && (
            <div>
              <table className="ver-productos-table" style={{ marginBottom: 20 }}>
                <thead>
                  <tr>
                    <th>Producto</th>
                    <th style={{ textAlign: "center" }}>Cant.</th>
                    {pedido.sobre_stock && <th style={{ textAlign: "center" }}>Preorden</th>}
                    <th style={{ textAlign: "right" }}>Precio</th>
                    <th style={{ textAlign: "right" }}>Subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  {(pedido.productosItems || []).map((p, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600, display:"flex", alignItems:"center", gap:5 }}><Package size={14} /> {p.nombre}</td>
                      <td style={{ textAlign: "center" }}>
                        <span style={{ background: "#f1f8f1", border: "1px solid #c8e6c9", borderRadius: 6, padding: "2px 8px", fontSize: 12, fontWeight: 700, color: "#2e7d32" }}>×{p.cantidad}</span>
                      </td>
                      {pedido.sobre_stock && (
                        <td style={{ textAlign: "center" }}>
                          {p.cantidad_preorden > 0
                            ? <span style={{ background: "#fff3e0", border: "1px solid #ffcc02", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#e65100" }}>×{p.cantidad_preorden} preorden</span>
                            : <span style={{ color: "#9e9e9e", fontSize: 11 }}>—</span>}
                        </td>
                      )}
                      <td style={{ textAlign: "right", color: "#757575" }}>{fmt(p.precio)}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, color: "#2e7d32" }}>{fmt(p.precio * p.cantidad)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="totales-box">
                <div className="totales-row">
                  <span>Subtotal</span>
                  <span>{fmt(pedido.subtotal)}</span>
                </div>
                {pedido.descuento > 0 && (
                  <div className="totales-row totales-row--descuento">
                    <span style={{display:"inline-flex",alignItems:"center",gap:5}}><CreditCard size={14} /> Crédito aplicado</span>
                    <span>− {fmt(pedido.descuento)}</span>
                  </div>
                )}
                <div className="totales-row totales-row--total">
                  <span>Total a pagar</span>
                  <span>{fmt(pedido.total)}</span>
                </div>
              </div>
            </div>
          )}

          {/* ── Tab Pago ── */}
          {tab === "pago" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {(() => {
                const totalPedido = Number(pedido.total || 0);

                const ep = pedido.estado_pago;

                // Un pedido con anticipo se cobra en dos partes. Antes solo se
                // contaba una: al registrar el saldo, el total pagado pasaba a ser
                // ese saldo y el anticipo desaparecía, así que un pedido saldado
                // seguía mostrando el 50% como pendiente.
                const anticipoCobrado = pedido.anticipo_registrado
                  ? Number(pedido.anticipo_monto ?? 0)
                  : (pedido.sobre_stock && pedido.anticipo_pagado != null ? Number(pedido.anticipo_pagado) : 0);
                const saldoCobrado = pedido.pago_final_registrado
                  ? Number(pedido.pago_final_monto ?? Math.max(0, totalPedido - anticipoCobrado))
                  : 0;

                /* Pago mixto: cada mitad entra por su lado y puede llegar
                   primero cualquiera de las dos. El efectivo se sabe por su
                   propio registro; la transferencia, porque el comprobante ya
                   pasó por revisión. Sin esto la tarjeta decía "$0 pagado" con
                   media plata adentro. */
                const efectivoMixto = esMixto && pedido.pago_final_registrado
                  ? montoACobrar(pedido) : 0;
                const transferMixto = esMixto && (
                  ep === "pagado_completo" ||
                  (ep === "anticipo_pagado" && !pedido.pago_final_registrado)
                ) ? montoTransferido(pedido) : 0;

                // Estados con los que el backend da el pago por cerrado: no queda
                // saldo aunque los montos registrados no cuadren al peso.
                const pagoCerrado = !!pedido.pago_final_registrado
                  || ["pagado_completo", "efectivo_recibido"].includes(ep);

                let totalPagado = esMixto
                  ? efectivoMixto + transferMixto
                  : anticipoCobrado + saldoCobrado;
                if (pagoCerrado) totalPagado = Math.max(totalPagado, totalPedido);

                const saldo = Math.max(0, totalPedido - totalPagado);
                const pct = totalPedido > 0 ? Math.min(100, Math.round((totalPagado / totalPedido) * 100)) : 0;

                let estadoLabel, estadoColor, estadoBg, estadoBorder, EstadoIcon;
                if (ep === "pagado_completo" || (!ep && totalPagado >= totalPedido && totalPedido > 0 && totalPagado > 0)) {
                  estadoLabel = "Pago completo";    estadoColor = "#2e7d32"; estadoBg = "#e8f5e9"; estadoBorder = "#a5d6a7"; EstadoIcon = CheckCircle2;
                } else if (ep === "anticipo_pagado" || (!ep && totalPagado > 0 && totalPagado < totalPedido)) {
                  // En un mixto no hay anticipo: hay una de las dos mitades.
                  estadoLabel = esMixto ? "Pago parcial" : "Anticipo";
                  estadoColor = "#e65100"; estadoBg = "#fff8e1"; estadoBorder = "#ffe082"; EstadoIcon = AlertCircle;
                } else if (ep === "pendiente_validacion") {
                  estadoLabel = "Pendiente de validación"; estadoColor = "#1565c0"; estadoBg = "#e3f2fd"; estadoBorder = "#90caf9"; EstadoIcon = Clock;
                } else if (ep === "comprobante_rechazado") {
                  estadoLabel = "Comprobante rechazado"; estadoColor = "#c62828"; estadoBg = "#ffebee"; estadoBorder = "#ef9a9a"; EstadoIcon = XCircle;
                } else {
                  estadoLabel = "Pendiente";        estadoColor = "#9e9e9e"; estadoBg = "#f5f5f5"; estadoBorder = "#e0e0e0"; EstadoIcon = Clock;
                }

                const modalidad = !esTransferencia || esMixto
                  ? (pedido.domicilio ? "Contraentrega" : "En tienda")
                  : null;
                const fechaPago = pedido.pago_final_fecha || null;

                return (
                  <>
                    {/* ── Estado del pago (siempre visible) ── */}
                    <div style={{ background: estadoBg, border: `1.5px solid ${estadoBorder}`, borderRadius: 14, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <p style={{ margin: 0, fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.8, color: "#9e9e9e" }}>Estado del pago</p>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "#fff", color: estadoColor, border: `1px solid ${estadoBorder}`, borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.4 }}>
                          {EstadoIcon && <EstadoIcon size={12} />} {estadoLabel}
                        </span>
                      </div>

                      {/* Pago mixto: el pedido entra por dos vías y cada una se
                          salda por su lado, así que aquí importa el reparto y
                          no solo el total. */}
                      {esMixto && (
                        <div style={{ background: "#fff", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#616161", fontWeight: 600 }}>
                              <Building2 size={13} /> Transferencia
                            </span>
                            <span style={{ fontSize: 14, fontWeight: 900, color: "#1565c0" }}>
                              {fmt(montoTransferido(pedido))}
                            </span>
                          </div>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#616161", fontWeight: 600 }}>
                              <Banknote size={13} /> Efectivo
                            </span>
                            <span style={{ fontSize: 14, fontWeight: 900, color: "#2e7d32" }}>
                              {fmt(montoACobrar(pedido))}
                            </span>
                          </div>
                          <div style={{ borderTop: "1px solid #f0f0f0", paddingTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: 12, color: "#9e9e9e", fontWeight: 700 }}>Suman</span>
                            <span style={{ fontSize: 13, fontWeight: 800, color: "#616161" }}>{fmt(totalPedido)}</span>
                          </div>
                          <p style={{ margin: 0, fontSize: 11, color: "#9e9e9e", lineHeight: 1.4 }}>
                            {ep === "pagado_completo"
                              ? "Las dos partes están cobradas."
                              : transferMixto > 0
                                ? "La transferencia está aprobada; falta registrar el efectivo."
                                : efectivoMixto > 0
                                  ? "El efectivo está cobrado; falta aprobar el comprobante de la transferencia."
                                  : "Se salda en dos pasos: aprobar el comprobante de la transferencia y registrar el efectivo."}
                          </p>
                        </div>
                      )}

                      {/* Barra de progreso del pago */}
                      {totalPedido > 0 && (
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: estadoColor }}>{fmt(totalPagado)} pagado</span>
                            <span style={{ fontSize: 11, fontWeight: 600, color: "#9e9e9e" }}>{pct}%</span>
                          </div>
                          <div style={{ height: 7, background: "#fff", borderRadius: 99, overflow: "hidden", border: `1px solid ${estadoBorder}` }}>
                            <div style={{ height: "100%", width: `${pct}%`, background: estadoColor, borderRadius: 99 }} />
                          </div>
                        </div>
                      )}

                      {/* Grid de montos y método */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px" }}>
                        <div className="ver-ped-field">
                          <span className="ver-ped-field__label">Total del pedido</span>
                          <span className="ver-ped-field__value" style={{ fontWeight: 800 }}>{fmt(totalPedido)}</span>
                        </div>
                        <div className="ver-ped-field">
                          <span className="ver-ped-field__label">Total pagado</span>
                          <span className="ver-ped-field__value" style={{ fontWeight: 800, color: totalPagado > 0 ? "#2e7d32" : "#9e9e9e" }}>{fmt(totalPagado)}</span>
                        </div>
                        <div className="ver-ped-field">
                          <span className="ver-ped-field__label">Saldo pendiente</span>
                          <span className="ver-ped-field__value" style={{ fontWeight: 800, color: saldo > 0 ? "#c62828" : "#2e7d32" }}>{fmt(saldo)}</span>
                        </div>
                        <div className="ver-ped-field">
                          <span className="ver-ped-field__label">Método de pago</span>
                          <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5}}>{esMixto ? <><Scale size={14} /> Mixto</> : esTransferencia ? <><Building2 size={14} /> Transferencia</> : <><Banknote size={14} /> Efectivo</>}</span>
                        </div>
                        {esMixto && pedido.monto_efectivo != null && (
                          <div className="ver-ped-field">
                            <span className="ver-ped-field__label">Efectivo</span>
                            <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5}}><Banknote size={14} />{fmt(pedido.monto_efectivo)}</span>
                          </div>
                        )}
                        {esMixto && pedido.monto_transferencia != null && (
                          <div className="ver-ped-field">
                            <span className="ver-ped-field__label">Transferencia</span>
                            <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5}}><Building2 size={14} />{fmt(pedido.monto_transferencia)}</span>
                          </div>
                        )}
                        {modalidad && (
                          <div className="ver-ped-field">
                            <span className="ver-ped-field__label">Modalidad</span>
                            <span className="ver-ped-field__value">{modalidad}</span>
                          </div>
                        )}
                        {pedido.pago_final_metodo_pago && (
                          <div className="ver-ped-field">
                            <span className="ver-ped-field__label">Método pago final</span>
                            <span className="ver-ped-field__value">{pedido.pago_final_metodo_pago}</span>
                          </div>
                        )}
                        {fechaPago && (
                          <div className="ver-ped-field" style={{ gridColumn: "1 / -1" }}>
                            <span className="ver-ped-field__label">Fecha del pago</span>
                            <span className="ver-ped-field__value" style={{display:"inline-flex",alignItems:"center",gap:5}}><Calendar size={14} /> {fmtFecha(fechaPago)}</span>
                          </div>
                        )}
                      </div>

                      {/* Comprobante pendiente de validación */}
                      {ep === "pendiente_validacion" && pedido.comprobante && (
                        <div className="info-box info-box--info" style={{ marginTop: 0 }}>
                          <span className="info-box__icon"><Paperclip size={16} /></span>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
                            <span className="info-box__text">Comprobante cargado — pendiente de validación</span>
                            <a href={pedido.comprobante} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, fontWeight: 700, color: "#1565c0", flexShrink: 0, marginLeft: 8 }}>Ver →</a>
                          </div>
                        </div>
                      )}

                      {/* Comprobante rechazado */}
                      {ep === "comprobante_rechazado" && (
                        <div className="info-box info-box--danger" style={{ background: "#ffebee", borderColor: "#ef9a9a", color: "#c62828" }}>
                          <span className="info-box__icon"><XCircle size={16} /></span>
                          <span className="info-box__text">El comprobante fue rechazado. El cliente debe subir uno nuevo.</span>
                        </div>
                      )}
                    </div>

                    {/* El recuadro de "pedido sobre stock" mostraba el anticipo
                        pagado con Anticipo_Pagado, que solo cuenta el crédito
                        descontado en el servidor: quien pagó por transferencia
                        veía "$0 — Pendiente" con el pedido ya saldado. Lo que se
                        pagó sale arriba, en el estado del pago. */}

                    {/* ── Transferencia: datos bancarios + comprobante ── */}
                    {pagoTotalConCredito ? (
                      <div className="info-box info-box--success">
                        <span className="info-box__icon"><CheckCircle2 size={16} /></span>
                        <span className="info-box__text">El saldo a favor del cliente cubrió el total del pedido. No se requiere comprobante de transferencia.</span>
                      </div>
                    ) : esTransferencia ? (
                      <>
                        <p className="section-label" style={{ marginTop: 4 }}>Datos para realizar la transferencia</p>
                        <div className="cuenta-card">
                          <div className="cuenta-card__rows">
                            {[
                              { label: "Banco",          value: CUENTA_TRANSFERENCIA.banco },
                              { label: "Titular",        value: CUENTA_TRANSFERENCIA.titular },
                              { label: "Tipo de cuenta", value: CUENTA_TRANSFERENCIA.tipo },
                              { label: "Número",         value: CUENTA_TRANSFERENCIA.numero },
                            ].map(({ label, value }) => (
                              <div key={label} className="cuenta-card__row">
                                <span className="cuenta-card__label">{label}</span>
                                <span className="cuenta-card__value">{value}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                        {comprobantes.length === 0 && (
                          <div className="info-box info-box--warn" style={{ marginTop: 0 }}>
                            <span className="info-box__icon"><Info size={16} /></span>
                            <span className="info-box__text">Recuerda adjuntar el comprobante de pago al confirmar el pedido.</span>
                          </div>
                        )}
                        {comprobantes.map(c => (
                          <ComprobanteAdjunto key={c.url} url={c.url} titulo={c.titulo} />
                        ))}
                        {comprobantes.length === 0 && (
                          <div className="info-box info-box--danger" style={{ background: "#ffebee", borderColor: "#ef9a9a", color: "#c62828" }}>
                            <span className="info-box__icon"><AlertCircle size={16} /></span>
                            <span className="info-box__text">Aún no se ha adjuntado comprobante de pago.</span>
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="info-box info-box--success">
                          <span className="info-box__icon"><Banknote size={16} /></span>
                          <span className="info-box__text">
                            Pago en efectivo {pedido.domicilio ? "al momento de la entrega (contraentrega)" : "en tienda al retirar el pedido"}.
                          </span>
                        </div>
                        {/* El pedido es en efectivo, pero el anticipo o el saldo
                            pudieron transferirse: ahí sí hay comprobante. */}
                        {comprobantes.map(c => (
                          <ComprobanteAdjunto key={c.url} url={c.url} titulo={c.titulo} />
                        ))}
                      </>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
          <button
            className="btn-cancel"
            style={{ background: '#f1f8f1', color: '#2e7d32', border: '1.5px solid #c8e6c9', display:"inline-flex", alignItems:"center", gap:6 }}
            onClick={() => descargarFacturaPedido(pedido, pedido.cliente)}
          >
            <FileText size={14} /> Ver / Imprimir factura
          </button>
          {puedeEditarsePedido(pedido.estado) && (
            <button className="btn-save" style={{display:"inline-flex",alignItems:"center",gap:6}} onClick={() => onEdit(pedido)}><Pencil size={14} /> Editar Pedido</button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — PROPONER FECHA DE ENTREGA (producción)
   ═══════════════════════════════════════════════════════════ */
function ModalProponerFecha({ pedido, saving, onClose, onConfirm }) {
  const hoy = new Date().toISOString().split("T")[0];
  const [fecha, setFecha] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = () => {
    if (!fecha) { setError("Selecciona una fecha de entrega"); return; }
    if (fecha < hoy) { setError("La fecha no puede ser anterior a hoy"); return; }
    onConfirm(pedido.id, fecha);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: "28px", maxWidth: "440px" }}>
        <div className="modal-header shrink-0" style={{ background: "linear-gradient(135deg, #283593 0%, #3949ab 100%)", padding: "20px 24px" }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Proponer fecha de entrega</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">Pedido #{pedido.numero}</p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>

        <div className="modal-body p-6 space-y-4">
          <div className="bg-blue-50 border border-blue-200 p-4 rounded-2xl">
            <p className="text-xs font-black text-blue-800 mb-1" style={{display:"flex",alignItems:"center",gap:5}}><Calendar size={14} /> Fecha estimada de entrega</p>
            <p className="text-[11px] text-blue-700 font-medium leading-snug">
              El cliente recibirá una notificación con esta fecha y podrá aceptarla o rechazarla.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
              Fecha propuesta <span className="text-red-500">*</span>
            </label>
            <input
              type="date"
              min={hoy}
              value={fecha}
              onChange={e => { setFecha(e.target.value); setError(""); }}
              className={`w-full bg-gray-50 border-2 rounded-2xl p-4 text-sm font-medium text-gray-700 outline-none transition-all ${
                error ? "border-red-400 bg-red-50" : "border-transparent focus:border-blue-400 focus:bg-white"
              }`}
            />
            {error && (
              <p className="text-[10px] font-bold text-red-500 flex items-center gap-1">
                <AlertCircle size={10} /> {error}
              </p>
            )}
          </div>

          <div className="space-y-2 pt-2">
            <button
              disabled={saving}
              onClick={handleSubmit}
              className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
              style={{ background: "linear-gradient(135deg, #283593, #3949ab)" }}
            >
              {saving ? "Enviando…" : <span style={{display:"inline-flex",alignItems:"center",gap:6}}><Calendar size={14} /> Proponer fecha</span>}
            </button>
            <button
              onClick={onClose}
              className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — RESOLVER PEDIDO ESCALADO A ADMIN
   Dos opciones: acordar una fecha manualmente (→ Confirmado/En producción)
   o cancelar el pedido (→ Cancelado + devuelve crédito).
   ═══════════════════════════════════════════════════════════ */
function ModalResolverEscalado({ pedido, saving, onClose, onConfirmarAcuerdo, onConfirmarCancelacion }) {
  const hoy = new Date().toISOString().split("T")[0];
  const [opcion, setOpcion] = useState(null); // "acuerdo" | "cancelar"
  const [fecha, setFecha]   = useState("");
  const [error, setError]   = useState("");

  const handleAcuerdo = () => {
    if (!fecha) { setError("Selecciona una fecha acordada"); return; }
    if (fecha < hoy) { setError("La fecha no puede ser anterior a hoy"); return; }
    onConfirmarAcuerdo(pedido.id, fecha);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: "28px", maxWidth: "460px" }}>
        <div className="modal-header shrink-0" style={{ background: "linear-gradient(135deg, #880e4f 0%, #c2185b 100%)", padding: "20px 24px" }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Pedido escalado a admin</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">Pedido #{pedido.numero}</p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>

        <div className="modal-body p-6 space-y-4">
          <div className="bg-pink-50 border border-pink-200 p-4 rounded-2xl">
            <p className="text-xs font-black text-pink-800 mb-1" style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <AlertTriangle size={14} /> El cliente rechazó la fecha demasiadas veces
            </p>
            <p className="text-[11px] text-pink-700 font-medium leading-snug">
              Este pedido requiere gestión manual. Elige si acordás una fecha directamente con el cliente o cancelás el pedido.
            </p>
          </div>

          {!opcion && (
            <div className="space-y-3">
              <button
                onClick={() => setOpcion("acuerdo")}
                className="w-full py-4 px-5 rounded-2xl border-2 border-transparent text-left transition-all"
                style={{ background: "#e8f5e9", border: "2px solid #a5d6a7" }}
              >
                <p className="text-xs font-black text-green-800 flex items-center gap-2"><Calendar size={14} /> Acordar fecha manualmente</p>
                <p className="text-[10px] text-green-700 mt-1">El pedido pasa directamente a Confirmado o En producción. El cliente no puede rechazar de nuevo.</p>
              </button>
              <button
                onClick={() => setOpcion("cancelar")}
                className="w-full py-4 px-5 rounded-2xl border-2 border-transparent text-left transition-all"
                style={{ background: "#ffebee", border: "2px solid #ef9a9a" }}
              >
                <p className="text-xs font-black text-red-800 flex items-center gap-2"><X size={14} /> Cancelar pedido</p>
                <p className="text-[10px] text-red-700 mt-1">El pedido se cancela. Se devuelve el saldo a favor del cliente si lo usó. El anticipo, si existe, se acuerda con el cliente por fuera del sistema.</p>
              </button>
            </div>
          )}

          {opcion === "acuerdo" && (
            <div className="space-y-4">
              <button onClick={() => { setOpcion(null); setError(""); setFecha(""); }} className="text-[10px] font-bold text-gray-400 hover:text-gray-600 flex items-center gap-1">
                ← Volver
              </button>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
                  Fecha acordada <span className="text-red-500">*</span>
                </label>
                <input
                  type="date"
                  min={hoy}
                  value={fecha}
                  onChange={e => { setFecha(e.target.value); setError(""); }}
                  className={`w-full bg-gray-50 border-2 rounded-2xl p-4 text-sm font-medium text-gray-700 outline-none transition-all ${
                    error ? "border-red-400 bg-red-50" : "border-transparent focus:border-green-400 focus:bg-white"
                  }`}
                />
                {error && <p className="text-[10px] font-bold text-red-500 flex items-center gap-1"><AlertCircle size={10} /> {error}</p>}
              </div>
              <button
                disabled={saving}
                onClick={handleAcuerdo}
                className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
                style={{ background: "linear-gradient(135deg, #2e7d32, #43a047)" }}
              >
                {saving ? "Guardando…" : <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Calendar size={14} /> Confirmar fecha acordada</span>}
              </button>
            </div>
          )}

          {opcion === "cancelar" && (
            <div className="space-y-4">
              <button onClick={() => setOpcion(null)} className="text-[10px] font-bold text-gray-400 hover:text-gray-600 flex items-center gap-1">
                ← Volver
              </button>
              <div className="bg-red-50 border border-red-200 p-4 rounded-2xl">
                <p className="text-xs font-black text-red-800 mb-1">¿Confirmás que querés cancelar este pedido?</p>
                <p className="text-[11px] text-red-700 leading-snug">Esta acción no se puede deshacer. El saldo a favor aplicado vuelve al cliente automáticamente.</p>
              </div>
              <button
                disabled={saving}
                onClick={() => onConfirmarCancelacion(pedido.id)}
                className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
                style={{ background: "linear-gradient(135deg, #c62828, #e53935)" }}
              >
                {saving ? "Cancelando…" : <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><X size={14} /> Cancelar pedido</span>}
              </button>
            </div>
          )}

          {!opcion && (
            <button onClick={onClose} className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors">
              Cerrar sin hacer nada
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── ModalRegistrarSaldo ────────────────────────────────── */
function ModalRegistrarSaldo({ pedido, saving, onClose, onConfirm }) {
  const [metodo,    setMetodo]    = useState("");
  const [efectivo,  setEfectivo]  = useState(false);
  const [archivo,   setArchivo]   = useState(null);
  const [preview,   setPreview]   = useState(null);
  const [uploading, setUploading] = useState(false);
  const [errors,    setErrors]    = useState({});

  const anticipo    = pedido.anticipo_monto ?? (pedido.anticipo_requerido ?? 0);
  const saldo       = Math.max(0, (pedido.total ?? 0) - anticipo);

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => { setArchivo(file); setPreview(ev.target.result); setErrors(x => ({ ...x, archivo: "" })); };
    reader.readAsDataURL(file);
  };

  const handleSubmit = async () => {
    const e = {};
    if (!metodo) e.metodo = "Selecciona el método de pago del saldo";
    if (metodo === "Efectivo" && !efectivo) e.efectivo = "Confirma que recibiste el saldo en efectivo";
    if (metodo === "Transferencia" && !preview) e.archivo = "Adjunta el comprobante del saldo";
    if (Object.keys(e).length) { setErrors(e); return; }

    setUploading(true);
    let comprobanteUrl = null;
    if (archivo) {
      try {
        const { subirImagenCloudinary } = await import("../../../utils/cloudinary.js");
        comprobanteUrl = await subirImagenCloudinary(archivo);
      } catch {
        setErrors(x => ({ ...x, archivo: "Error al subir el comprobante. Intenta de nuevo." }));
        setUploading(false);
        return;
      }
    }
    setUploading(false);
    onConfirm(pedido.id, { metodo, comprobanteUrl, saldo });
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()} style={{ overflow: "hidden", padding: 0, maxWidth: 420 }}>
        <div style={{ background: "linear-gradient(135deg, #1b5e20 0%, #2e7d32 100%)", padding: "24px 24px 18px", position: "relative" }}>
          <button onClick={onClose} style={{ position: "absolute", top: 12, right: 12, color: "rgba(255,255,255,0.8)", background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.3)", borderRadius: 8, width: 30, height: 30, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><X size={14} /></button>
          <div style={{ display:"flex", justifyContent:"center", marginBottom: 10 }}><CreditCard size={30} color="white" /></div>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: "#fff", textAlign: "center" }}>Registrar pago del saldo</h3>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "rgba(255,255,255,0.85)", textAlign: "center" }}>Pedido {pedido.numero}</p>
        </div>

        <div style={{ padding: "18px 22px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div style={{ background: "#f5f5f5", borderRadius: 10, padding: "10px 14px", textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#999", fontWeight: 700, textTransform: "uppercase", marginBottom: 3 }}>Total pedido</div>
              <div style={{ fontSize: 16, fontWeight: 900, color: "#333" }}>{fmt(pedido.total)}</div>
            </div>
            <div style={{ background: "#e8f5e9", borderRadius: 10, padding: "10px 14px", textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#4caf50", fontWeight: 700, textTransform: "uppercase", marginBottom: 3 }}>Anticipo pagado</div>
              <div style={{ fontSize: 16, fontWeight: 900, color: "#2e7d32" }}>{fmt(anticipo)}</div>
            </div>
          </div>

          <div style={{ background: "#fff8e1", border: "1.5px solid #f9a825", borderRadius: 10, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "#e65100" }}>Saldo a cobrar ahora</span>
            <span style={{ fontSize: 20, fontWeight: 900, color: "#e65100" }}>{fmt(saldo)}</span>
          </div>

          <div>
            <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700, color: "#555" }}>Método de pago del saldo <span style={{ color: "#e53935" }}>*</span></p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {/* El valor viaja a la API (que compara contra "transferencia"): el
                  emoji se queda en la etiqueta y no en lo que se guarda. */}
              {[{ id: "Efectivo", label: "Efectivo" }, { id: "Transferencia", label: "Transferencia" }].map(m => (
                <button key={m.id} onClick={() => { setMetodo(m.id); setEfectivo(false); setArchivo(null); setPreview(null); setErrors(x => ({ ...x, metodo: "", efectivo: "", archivo: "" })); }}
                  style={{ padding: "11px 8px", borderRadius: 10, border: `2px solid ${metodo === m.id ? "#2e7d32" : "#e0e0e0"}`, background: metodo === m.id ? "#f1f8f1" : "#fff", color: metodo === m.id ? "#1b5e20" : "#888", fontWeight: metodo === m.id ? 700 : 500, fontSize: 13, cursor: "pointer" }}>
                  {m.label}
                </button>
              ))}
            </div>
            {errors.metodo && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginTop: 4 }}>{errors.metodo}</span>}
          </div>

          {metodo === "Efectivo" && (
            <div className="fade-in">
              <label style={{ display: "flex", gap: 10, alignItems: "center", cursor: "pointer", background: efectivo ? "#f1f8f1" : "#fafafa", padding: "12px 14px", borderRadius: 10, border: `2px solid ${efectivo ? "#2e7d32" : "#e0e0e0"}` }}>
                <input type="checkbox" checked={efectivo} onChange={e => { setEfectivo(e.target.checked); setErrors(x => ({ ...x, efectivo: "" })); }} style={{ width: 18, height: 18, accentColor: "#2e7d32" }} />
                <span style={{ fontSize: 13, color: efectivo ? "#1b5e20" : "#555", fontWeight: efectivo ? 700 : 400 }}>
                  Confirmo que recibí <strong>{fmt(saldo)}</strong> en efectivo
                </span>
              </label>
              {errors.efectivo && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginTop: 4 }}>{errors.efectivo}</span>}
            </div>
          )}

          {metodo === "Transferencia" && (
            <div className="fade-in">
              {preview ? (
                <div style={{ position: "relative", height: 120, borderRadius: 10, overflow: "hidden", background: "#000" }}>
                  <img src={preview} alt="Comprobante saldo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                  <button style={{ position: "absolute", top: 6, right: 6, background: "rgba(0,0,0,0.6)", color: "#fff", border: "none", borderRadius: "50%", width: 26, height: 26, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => { setArchivo(null); setPreview(null); }}><X size={12} /></button>
                </div>
              ) : (
                <label className={`comprobante-dropzone${errors.archivo ? " error" : ""}`} style={{ height: 100 }}>
                  <input type="file" accept="image/*" onChange={handleFile} hidden />
                  <div style={{ textAlign: "center" }}>
                    <Paperclip size={24} color="#1565c0" />
                    <p style={{ margin: "6px 0 0", fontSize: 12, fontWeight: 700, color: "#1565c0" }}>Comprobante del saldo</p>
                  </div>
                </label>
              )}
              {errors.archivo && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginTop: 4 }}>{errors.archivo}</span>}
            </div>
          )}
        </div>

        <div style={{ padding: "0 22px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
          <button
            onClick={handleSubmit}
            disabled={saving || uploading}
            style={{ width: "100%", padding: "12px", borderRadius: 10, border: "none", background: "#2e7d32", color: "#fff", fontWeight: 700, fontSize: 14, cursor: saving || uploading ? "not-allowed" : "pointer", opacity: saving || uploading ? 0.7 : 1, fontFamily: "inherit" }}
          >
            {uploading ? "Subiendo comprobante…" : saving ? "Procesando…" : <><CheckCircle2 size={14} /> Confirmar entrega y registrar pago</>}
          </button>
          <button onClick={onClose} style={{ width: "100%", padding: "10px", borderRadius: 10, border: "1.5px solid #e0e0e0", background: "#fff", color: "#616161", fontWeight: 700, fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Cancelar</button>
        </div>
      </div>
    </div>
  );
}

function ModalErrorEstadoPedido({ mensaje, onClose }) {
  if (!mensaje) return null;
  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()} style={{ overflow: "hidden", padding: 0 }}>
        <div style={{ background: "linear-gradient(135deg, #e65100 0%, #f57f17 100%)", padding: "28px 24px 22px", textAlign: "center", position: "relative" }}>
          <button onClick={onClose} style={{ position: "absolute", top: 12, right: 12, color: "rgba(255,255,255,0.8)", background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.3)", borderRadius: 8, width: 30, height: 30, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><X size={14} /></button>
          <div style={{ width: 64, height: 64, borderRadius: "50%", background: "rgba(255,255,255,0.15)", border: "2px solid rgba(255,255,255,0.3)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px" }}><AlertCircle size={28} color="white" /></div>
          <h3 style={{ margin: 0, fontSize: 19, fontWeight: 800, color: "#fff", letterSpacing: -0.3 }}>No se pudo avanzar</h3>
        </div>
        <div style={{ padding: "18px 24px" }}>
          <div style={{ padding: "12px 14px", background: "#fff8e1", border: "1.5px solid #ffe082", borderRadius: 10, color: "#e65100", fontSize: 13, fontWeight: 600, lineHeight: 1.6 }}>
            <span style={{display:"inline-flex",alignItems:"center",gap:6}}><AlertCircle size={14} /></span> {mensaje}
          </div>
        </div>
        <div style={{ padding: "0 24px 20px" }}>
          <button onClick={onClose} style={{ width: "100%", padding: "11px", borderRadius: 10, border: "none", background: "#f57f17", color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>Entendido</button>
        </div>
      </div>
    </div>
  );
}

function ModalAvisoProduccion({ items, pedidoNumero, onClose }) {
  if (!items?.length) return null;
  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()} style={{ overflow: "hidden", padding: 0 }}>
        <div style={{ background: "linear-gradient(135deg, #1565c0 0%, #1976d2 100%)", padding: "24px 24px 20px", textAlign: "center", position: "relative" }}>
          <button onClick={onClose} style={{ position: "absolute", top: 12, right: 12, color: "rgba(255,255,255,0.8)", background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.3)", borderRadius: 8, width: 30, height: 30, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><X size={14} /></button>
          <div style={{ width: 56, height: 56, borderRadius: "50%", background: "rgba(255,255,255,0.15)", border: "2px solid rgba(255,255,255,0.3)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}><Package size={26} color="white" /></div>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#fff" }}>Pedido #{pedidoNumero} confirmado</h3>
          <p style={{ margin: "6px 0 0", fontSize: 11, color: "rgba(255,255,255,0.7)", fontWeight: 600 }}>Los siguientes productos irán a producción</p>
        </div>
        <div style={{ padding: "16px 24px" }}>
          <div style={{ background: "#e3f2fd", border: "1.5px solid #90caf9", borderRadius: 10, padding: "10px 14px", marginBottom: 12 }}>
            {items.map((it, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: i < items.length - 1 ? "1px solid #bbdefb" : "none" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#1565c0" }}>{it.nombre}</span>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#0d47a1", background: "#bbdefb", borderRadius: 6, padding: "2px 8px" }}>×{it.cantidad_preorden} a producir</span>
              </div>
            ))}
          </div>
          <p style={{ margin: 0, fontSize: 11, color: "#546e7a", lineHeight: 1.5 }}>El equipo de producción recibirá la orden automáticamente. Propone una fecha de entrega cuando esté listo.</p>
        </div>
        <div style={{ padding: "0 24px 20px" }}>
          <button onClick={onClose} style={{ width: "100%", padding: "11px", borderRadius: 10, border: "none", background: "#1976d2", color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}>Entendido</button>
        </div>
      </div>
    </div>
  );
}

function ModalAsignarDomiciliario({ pedido, empleados, repartidores, onClose, onConfirm }) {
  const [empId, setEmpId] = useState(pedido.idEmpleado || "");
  const [error, setError] = useState("");
  const empActual = empleados.find(e => e.id === pedido.idEmpleado);

  const handleSubmit = () => {
    if (!empId) {
      setError("Selecciona un domiciliario");
      return;
    }
    const id = parseInt(empId, 10);
    if (pedido.idEmpleado && pedido.idEmpleado === id) {
      setError("El pedido ya tiene asignado este domiciliario");
      return;
    }
    onConfirm(pedido.id, id);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: '32px', maxWidth: '440px' }}>

        <div className="modal-header shrink-0" style={{ background: 'linear-gradient(135deg, var(--green-900) 0%, var(--green-800) 100%)', padding: '24px' }}>
          <div className="flex items-center gap-4">
            <div className="bg-white/10 backdrop-blur-xl p-3 rounded-2xl border border-white/20">
              <Truck size={24} className="text-white" />
            </div>
            <div>
              <h2 className="text-xl font-black tracking-tight leading-none mb-1 text-white">Asignar Repartidor</h2>
              <p className="text-white/60 text-[10px] font-bold uppercase tracking-widest">Pedido #{pedido.numero}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full transition-all text-white/70">
            <X size={20} />
          </button>
        </div>

        <div className="modal-body p-6 space-y-5">
          <div className="bg-gray-50 border border-gray-100 p-4 rounded-2xl flex items-start gap-4">
            <div className="p-2 bg-white rounded-xl text-indigo-600 shadow-sm border border-indigo-100">
              <MapPin size={18} />
            </div>
            <div className="min-w-0">
              <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest leading-none mb-1">Lugar de Entrega</p>
              <p className="text-xs font-bold text-gray-700 leading-tight">{pedido.direccion_entrega || "Recogida en tienda"}</p>
            </div>
          </div>

          {empActual && (
            <div className="bg-amber-50 border border-amber-100 p-4 rounded-2xl flex items-center gap-4 animate-in slide-in-from-top-2">
              <div className="p-2 bg-white rounded-xl text-amber-600 shadow-sm border border-amber-100">
                <Truck size={18} />
              </div>
              <div>
                <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest leading-none mb-1">Repartidor Actual</p>
                <p className="text-xs font-black text-amber-800">{empActual.nombre} {empActual.apellidos}</p>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest px-1">Seleccionar Nuevo Repartidor <span className="text-red-500">*</span></label>
            <SearchableSelect
              options={repartidores}
              value={empId}
              onChange={e => { setEmpId(e.target.value); setError(""); }}
              getValue={e => e.id}
              getLabel={e => `${e.nombre} ${e.apellidos}${e.id === pedido.idEmpleado ? " (actual)" : ""}`}
              placeholder="— Elegir de la lista —"
              searchPlaceholder="Buscar repartidor…"
              className={`field-input${error ? " error" : ""}`}
            />
            {error && <p className="text-[10px] font-bold text-red-500 px-2 flex items-center gap-1"><AlertCircle size={10} /> {error}</p>}
          </div>
        </div>

        <div className="modal-footer p-6 bg-gray-50/50 border-t border-gray-100 shrink-0 flex gap-3">
          <button className="btn-secondary flex-1 py-4 text-xs font-black uppercase" onClick={onClose}>Cancelar</button>
          <button className="btn-primary flex-1 py-4 text-xs font-black uppercase shadow-lg" style={{ background: 'var(--green-600)' }} onClick={handleSubmit}>Asignar Ahora</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — CANCELAR PEDIDO (con motivo obligatorio)
   ═══════════════════════════════════════════════════════════ */
function ModalCancelarPedido({ pedido, saving, onClose, onConfirm }) {
  const [motivo, setMotivo] = useState("");
  const [error,  setError]  = useState("");
  const desdeListo = pedido.estado === "Listo";

  const handleSubmit = () => {
    if (!motivo.trim()) {
      setError("El motivo es obligatorio para cancelar un pedido");
      return;
    }
    onConfirm(pedido.id, motivo.trim());
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: "28px", maxWidth: "440px" }}>
        <div className="modal-header shrink-0" style={{ background: "linear-gradient(135deg, #b71c1c 0%, #e53935 100%)", padding: "20px 24px" }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Cancelar Pedido</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">Pedido #{pedido.numero}</p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>

        <div className="modal-body p-6 space-y-4">
          {desdeListo && (
            <div className="bg-amber-50 border border-amber-200 p-4 rounded-2xl flex items-start gap-3">
              <AlertCircle size={18} className="text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-black text-amber-800">El pedido ya está Listo</p>
                <p className="text-[11px] text-amber-700 mt-1 font-medium leading-snug">
                  Al cancelar se registrará una salida de inventario por los productos de este pedido.
                </p>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
              Motivo de cancelación <span className="text-red-500">*</span>
            </label>
            <textarea
              className={`w-full bg-gray-50 border-2 rounded-2xl p-4 text-sm font-medium text-gray-700 outline-none transition-all resize-none h-24 ${
                error ? "border-red-400 bg-red-50" : "border-transparent focus:border-red-400 focus:bg-white"
              }`}
              placeholder="Describe el motivo de cancelación…"
              value={motivo}
              onChange={e => { setMotivo(e.target.value); setError(""); }}
            />
            {error && (
              <p className="text-[10px] font-bold text-red-500 flex items-center gap-1">
                <AlertCircle size={10} /> {error}
              </p>
            )}
          </div>

          <div className="space-y-2 pt-2">
            <button
              disabled={saving}
              onClick={handleSubmit}
              className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
              style={{ background: "linear-gradient(135deg, #b71c1c, #e53935)" }}
            >
              {saving ? "Cancelando…" : "Confirmar Cancelación"}
            </button>
            <button
              onClick={onClose}
              className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors"
            >
              Volver
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — REGISTRAR COBRO EFECTIVO (contra entrega / en tienda)
   ═══════════════════════════════════════════════════════════ */
function ModalRegistrarCobro({ pedido, saving, onClose, onConfirm }) {
  const [recibido, setRecibido] = useState(null);
  const [error,    setError]    = useState(null);

  const handleConfirm = () => {
    if (recibido === null) { setError("Indica si el efectivo fue recibido"); return; }
    setError(null);
    onConfirm(pedido.id, { recibido });
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: "28px", maxWidth: "420px" }}>
        <div className="modal-header shrink-0" style={{ background: "linear-gradient(135deg, #2e7d32 0%, #388e3c 100%)", padding: "20px 24px" }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Registrar Cobro en Efectivo</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">
              Pedido #{pedido.numero} · {fmt(montoACobrar(pedido))}
            </p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>
        <div className="modal-body p-6 space-y-4">
          <p style={{ fontSize: 13, color: "#424242" }}>¿Se recibió el pago en efectivo?</p>
          {/* Pago mixto: en mano va solo una parte del pedido. */}
          {esPagoMixto(pedido.metodo_pago) && (
            <p style={{ fontSize: 12, color: "#757575", background: "#f5f5f5", borderRadius: 8, padding: "8px 10px" }}>
              Son <strong>{fmt(montoACobrar(pedido))}</strong> de
              un pedido de {fmt(pedido.total || 0)}: el resto va por transferencia.
            </p>
          )}
          <div style={{ display: "flex", gap: 10 }}>
            {[{ val: true, label: "Sí, recibido", color: "#2e7d32" }, { val: false, label: "No recibido", color: "#c62828" }].map(({ val, label, color }) => (
              <button
                key={String(val)}
                onClick={() => { setRecibido(val); setError(null); }}
                style={{
                  flex: 1, padding: "14px 10px", borderRadius: 12, border: `2px solid ${recibido === val ? color : "#e0e0e0"}`,
                  background: recibido === val ? color + "15" : "#fafafa",
                  color: recibido === val ? color : "#757575", fontWeight: 800, fontSize: 13, cursor: "pointer",
                }}
              >{label}</button>
            ))}
          </div>
          {error && <p style={{ fontSize: 12, color: "#c62828", background: "#ffebee", padding: "8px 12px", borderRadius: 8 }}>{error}</p>}
          <div className="space-y-2 pt-2">
            <button
              disabled={saving || recibido === null}
              onClick={handleConfirm}
              className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
              style={{ background: saving ? "#a5d6a7" : "linear-gradient(135deg, #2e7d32, #388e3c)", cursor: saving ? "not-allowed" : "pointer" }}
            >
              {saving ? "Guardando…" : "Confirmar"}
            </button>
            <button onClick={onClose} className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors">
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — SUBIR COMPROBANTE (para pedidos ya confirmados)
   ═══════════════════════════════════════════════════════════ */
function ModalSubirComprobante({ pedido, saving, onClose, onConfirm }) {
  const [file,      setFile]      = useState(null);
  const [preview,   setPreview]   = useState(pedido.comprobante || null);
  const [uploading, setUploading] = useState(false);
  const [error,     setError]     = useState(null);

  const handleFile = (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => setPreview(ev.target.result);
    reader.readAsDataURL(f);
  };

  const handleConfirm = async () => {
    if (!file && !pedido.comprobante) { setError("Selecciona un archivo"); return; }
    setError(null);
    setUploading(true);
    try {
      const url = file ? await subirImagenCloudinary(file) : pedido.comprobante;
      await onConfirm(pedido.id, url);
    } catch (e) {
      setError(e.message || "Error al subir el comprobante");
      setUploading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: "28px", maxWidth: "440px" }}>
        <div className="modal-header shrink-0" style={{ background: "linear-gradient(135deg, #1565c0 0%, #1976d2 100%)", padding: "20px 24px" }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Subir Comprobante</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">Pedido #{pedido.numero}</p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>
        <div className="modal-body p-6 space-y-4">
          <label style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
            padding: 20, borderRadius: 12, cursor: "pointer",
            border: `2px dashed ${file ? "#2e7d32" : "#e0e0e0"}`,
            background: file ? "#f1f8f1" : "#fafafa",
          }}>
            {preview
              ? <img src={preview} alt="Comprobante" style={{ width: "100%", maxHeight: 220, objectFit: "contain", borderRadius: 8 }} />
              : <><Paperclip size={32} color="#9e9e9e" /><span style={{ fontSize: 13, color: "#9e9e9e" }}>Seleccionar imagen del comprobante</span></>
            }
            <input type="file" accept="image/*" onChange={handleFile} style={{ display: "none" }} />
          </label>
          {file && <p style={{ fontSize: 11, color: "#2e7d32", fontWeight: 700, display:"flex", alignItems:"center", gap:4 }}><Check size={12} /> {file.name}</p>}
          {error && <p style={{ fontSize: 12, color: "#c62828", background: "#ffebee", padding: "8px 12px", borderRadius: 8 }}>{error}</p>}
          <div className="space-y-2 pt-2">
            <button
              disabled={uploading || saving || (!file && !pedido.comprobante)}
              onClick={handleConfirm}
              className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
              style={{ background: uploading ? "#90caf9" : "linear-gradient(135deg, #1565c0, #1976d2)", cursor: uploading ? "not-allowed" : "pointer" }}
            >
              {uploading ? "Subiendo…" : "Guardar Comprobante"}
            </button>
            <button onClick={onClose} className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors">
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — RECHAZAR COMPROBANTE (con motivo)
   ═══════════════════════════════════════════════════════════ */
function ModalRechazarComprobante({ pedido, saving, onClose, onConfirm }) {
  const [motivo, setMotivo] = useState("");
  const [error,  setError]  = useState("");

  const handleSubmit = () => {
    if (!motivo.trim()) { setError("El motivo es obligatorio"); return; }
    onConfirm(pedido.id, motivo.trim());
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box relative bg-white shadow-2xl overflow-hidden flex flex-col border-none" style={{ borderRadius: "28px", maxWidth: "440px" }}>
        <div className="modal-header shrink-0" style={{ background: "linear-gradient(135deg, #b71c1c 0%, #e53935 100%)", padding: "20px 24px" }}>
          <div>
            <h2 className="text-lg font-black text-white leading-none">Rechazar Comprobante</h2>
            <p className="text-white/60 text-[9px] font-bold uppercase tracking-widest mt-1">Pedido #{pedido.numero}</p>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white"><X size={18} /></button>
        </div>
        <div className="modal-body p-6 space-y-4">
          <div className="space-y-2">
            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
              Motivo del rechazo <span className="text-red-500">*</span>
            </label>
            <textarea
              className={`w-full bg-gray-50 border-2 rounded-2xl p-4 text-sm font-medium text-gray-700 outline-none transition-all resize-none h-24 ${
                error ? "border-red-400 bg-red-50" : "border-transparent focus:border-red-400 focus:bg-white"
              }`}
              placeholder="Ej: El comprobante está borroso o no coincide con el monto..."
              value={motivo}
              onChange={e => { setMotivo(e.target.value); setError(""); }}
            />
            {error && <p className="text-[10px] font-bold text-red-500">{error}</p>}
          </div>
          <div className="space-y-2 pt-2">
            <button
              disabled={saving}
              onClick={handleSubmit}
              className="w-full py-4 text-xs font-black uppercase tracking-widest rounded-2xl text-white shadow-lg"
              style={{ background: "linear-gradient(135deg, #b71c1c, #e53935)" }}
            >
              {saving ? "Rechazando…" : "Confirmar Rechazo"}
            </button>
            <button onClick={onClose} className="w-full py-3 text-[10px] font-black text-gray-400 hover:text-gray-600 uppercase tracking-widest transition-colors">
              Volver
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL — VER COMPROBANTE (con zoom + Aprobar / Rechazar)
   ═══════════════════════════════════════════════════════════ */
function ModalVerComprobante({ pedido, saving, onClose, onAprobar, onRechazar }) {
  return (
    <div className="modal-overlay">
      <div
        className="modal-box bg-white w-full max-w-md shadow-2xl flex flex-col"
        style={{ borderRadius: 24, maxHeight: '90vh', overflow: 'hidden' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ background: 'linear-gradient(135deg,#1565c0,#1976d2)', padding: '18px 22px', borderRadius: '24px 24px 0 0', flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <p style={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.6)', letterSpacing: 1, textTransform: 'uppercase', margin: 0 }}>Pedido #{pedido.numero}</p>
            <h2 style={{ margin: '2px 0 0', fontSize: 17, fontWeight: 800, color: '#fff' }}>Comprobante de pago</h2>
          </div>
          <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: '50%', width: 32, height: 32, cursor: 'pointer', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><X size={16} /></button>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '18px 22px' }}>
          {pedido.comprobante ? (
            <ImageLightbox
              src={pedido.comprobante}
              alt="Comprobante de pago"
              label="Ver imagen completa"
              thumbStyle={{ width: '100%', maxHeight: 380, objectFit: 'contain', borderRadius: 12, background: '#f0f4f8', cursor: 'zoom-in' }}
            />
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#9e9e9e' }}>
              <AlertCircle size={32} style={{ margin: '0 auto 8px', display: 'block' }} />
              <p style={{ fontSize: 13, margin: 0 }}>Sin comprobante adjuntado</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ flexShrink: 0, padding: '14px 22px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 10 }}>
          <button onClick={onClose} style={{ padding: '10px 20px', borderRadius: 10, border: '1px solid #e0e0e0', background: '#fff', color: '#616161', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
            Cerrar
          </button>
          <button
            onClick={onRechazar}
            disabled={saving}
            style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: 'none', background: saving ? '#ef9a9a' : '#c62828', color: '#fff', fontSize: 13, fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
          >
            <Ban size={14} /> Rechazar
          </button>
          <button
            onClick={onAprobar}
            disabled={saving}
            style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: 'none', background: saving ? '#a5d6a7' : '#2e7d32', color: '#fff', fontSize: 13, fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
          >
            <Check size={14} /> Aprobar
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MENÚ DE ACCIONES POR FILA
   ═══════════════════════════════════════════════════════════ */
function AccionesCell({ ped, saving, onVer, onEditar, onConfirmar, onMarcarListo, onEntregar, onAsignarDomicilio, onCancelar, onAprobarFecha, onProponerFecha, onResolverEscalado, onVerComprobante, onSubirComprobante, onRegistrarCobro, onAprobarPagoFinal, onRechazarPagoFinal, onRetenerEnTienda }) {
  const necesitaProduccion  = ped.requiereFechaPropuesta;
  const canEdit             = puedeEditarsePedido(ped.estado);
  const canAdvance          = ped.estado === "Pendiente" && !necesitaProduccion
    && (!esPagoTransferencia(ped.metodo_pago)
        || ["pagado_completo", "anticipo_pagado"].includes(ped.estado_pago));
  // Camino A: aprobar de una la fecha que el cliente ya pidió. Camino B (más
  // abajo, canProponerFecha): contraofrecer otra.
  const canAprobarFecha     = ped.estado === "Pendiente" && necesitaProduccion && !!ped.fecha_propuesta;
  const canProponerFecha    = ["Pendiente", "Fecha rechazada"].includes(ped.estado) && necesitaProduccion;
  const canResolverEscalado = ped.estado === "Escalado a admin";
  // canMarcarListo: no debe quedar desbloqueado solo porque no hay OPs pendientes.
  // sobre_stock indica que el pedido se creó con más unidades de las que había en
  // stock, por lo tanto sí necesitaba OPs. Si además no hay ninguna OP creada
  // (total_ordenes_produccion = 0), la OP nunca se generó y el pedido no puede
  // marcarse como listo. Esto distingue "OP terminada" de "OP nunca creada".
  // requiereProduccion solo señala el tipo de producto, no si había stock:
  // un producto que requiere producción con stock disponible no genera OP.
  const opsPendientes       = ped.orden_produccion;
  const opsCreadas          = ped.total_ordenes_produccion > 0;
  const canMarcarListo      = ped.estado === "Confirmado"
    && !opsPendientes
    && (!ped.sobre_stock || opsCreadas);
  const canEntregarTienda   = ped.estado === "Listo" && !ped.domicilio;
  const canAsignarDomicilio = ped.estado === "Listo" && ped.domicilio;
  const canEntregar         = ped.estado === "En camino";
  const canCancel           = !["Entregado", "Cancelado"].includes(ped.estado);
  // Un pedido mixto tiene comprobante QUE REVISAR y plata QUE COBRAR: con las
  // preguntas sueltas de antes ("¿dice transfer?", "¿dice efectivo?") no
  // coincidía con ninguna y se quedaba sin los dos botones.
  const esTransferencia     = esPagoTransferencia(ped.metodo_pago);
  const esEfectivo          = esPagoEfectivo(ped.metodo_pago);
  const canVerComprobante   = esTransferencia && ped.comprobante && ped.estado_pago === "pendiente_validacion";
  const _terminalState      = ["Entregado","Cancelado"].includes(ped.estado);
  const _pagoRegistrado     = ["efectivo_recibido","pagado_completo","anticipo_pagado"].includes(ped.estado_pago);
  const _fechaSinConfirmar  = ['Fecha propuesta', 'Fecha rechazada', 'Escalado a admin'].includes(ped.estado)
    || (ped.estado === 'Pendiente' && ped.requiereFechaPropuesta);
  const canSubirComprobante = esTransferencia && !_terminalState && !_fechaSinConfirmar &&
    Number(ped.total || 0) > 0 &&
    (!ped.comprobante || ped.estado_pago === "comprobante_rechazado");
  const _faltaEfectivoMixto = esPagoMixto(ped.metodo_pago) && ped.estado_pago === "anticipo_pagado";
  const canRegistrarCobro   = esEfectivo && !_terminalState && (!_pagoRegistrado || _faltaEfectivoMixto);
  const canAprobarPagoFinal = ped.estado_pago === "pago_final_pendiente_validacion";
  const canRechazarPagoFinal = ped.estado_pago === "pago_final_pendiente_validacion";
  const canRetenerEnTienda  = ped.estado === "Listo" && !ped.domicilio;
  const esRetenido          = ped.estado === "Retenido en tienda";

  return (
    <div className="actions-cell">
      <button className="act-btn act-btn--view"   data-tooltip="Ver detalle"           onClick={() => onVer(ped)}><Eye size={15} /></button>
      {canEdit          && <button className="act-btn act-btn--edit"    data-tooltip="Editar pedido"          disabled={saving} onClick={() => onEditar(ped)}><Pencil size={15} /></button>}
      {canAdvance       && <button className="act-btn act-btn--success" data-tooltip="Confirmar pedido"       disabled={saving} onClick={() => onConfirmar(ped)}><Check size={15} /></button>}
      {canAprobarFecha     && <button className="act-btn act-btn--success" data-tooltip="Aprobar fecha del cliente" disabled={saving} onClick={() => onAprobarFecha(ped)}><Check size={15} /></button>}
      {canProponerFecha    && <button className="act-btn act-btn--info"    data-tooltip="Proponer otra fecha"    disabled={saving} onClick={() => onProponerFecha(ped)}><Calendar size={15} /></button>}
      {canResolverEscalado && <button className="act-btn act-btn--warning" data-tooltip="Resolver escalado"     disabled={saving} onClick={() => onResolverEscalado(ped)}><AlertTriangle size={15} /></button>}
      {canMarcarListo      && <button className="act-btn act-btn--success" data-tooltip="Marcar como listo"     disabled={saving} onClick={() => onMarcarListo(ped)}><Package size={15} /></button>}
      {canEntregarTienda && !esRetenido && <button className="act-btn act-btn--success" data-tooltip="Entregar en tienda" disabled={saving} onClick={() => onEntregar(ped)}><Store size={15} /></button>}
      {canRetenerEnTienda  && <button className="act-btn act-btn--warning" data-tooltip="Retener en tienda (cobro pendiente)" disabled={saving} onClick={() => onRetenerEnTienda(ped)}><AlertCircle size={15} /></button>}
      {esRetenido          && <button className="act-btn act-btn--info"    data-tooltip="Reintentar entrega en tienda" disabled={saving} onClick={() => onMarcarListo(ped)}><RotateCcw size={15} /></button>}
      {esRetenido          && <button className="act-btn act-btn--info"    data-tooltip="Convertir a domicilio" disabled={saving} onClick={() => onAsignarDomicilio(ped)}><Bike size={15} /></button>}
      {canAsignarDomicilio && !esRetenido && <button className="act-btn act-btn--info" data-tooltip="Asignar domiciliario" disabled={saving} onClick={() => onAsignarDomicilio(ped)}><Bike size={15} /></button>}
      {canEntregar         && <button className="act-btn act-btn--success" data-tooltip="Registrar entrega"      disabled={saving} onClick={() => onEntregar(ped)}><Truck size={15} /></button>}
      {canSubirComprobante && <button className="act-btn act-btn--info"    data-tooltip="Subir comprobante"    disabled={saving} onClick={() => onSubirComprobante(ped)}><Paperclip size={15} /></button>}
      {canRegistrarCobro   && <button className="act-btn act-btn--success" data-tooltip="Registrar cobro efectivo" disabled={saving} onClick={() => onRegistrarCobro(ped)}><Banknote size={15} /></button>}
      {canVerComprobante && <button className="act-btn act-btn--info" data-tooltip="Ver comprobante" disabled={saving} onClick={() => onVerComprobante(ped)}><Eye size={15} /></button>}
      {canAprobarPagoFinal && <button className="act-btn act-btn--success" data-tooltip="Aprobar saldo final" disabled={saving} onClick={() => onAprobarPagoFinal(ped)}><CheckCircle2 size={15} /></button>}
      {canRechazarPagoFinal && <button className="act-btn act-btn--delete" data-tooltip="Rechazar saldo final" disabled={saving} onClick={() => onRechazarPagoFinal(ped)}><XCircle size={15} /></button>}
      {canCancel           && <button className="act-btn act-btn--delete"  data-tooltip="Cancelar pedido"        disabled={saving} onClick={() => onCancelar(ped)}><X size={15} /></button>}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   SKELETON
   ═══════════════════════════════════════════════════════════ */
function SkeletonRows({ cols = 8, rows = 5 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i}>
      {Array.from({ length: cols }).map((__, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

/* ═══════════════════════════════════════════════════════════
   COMPONENTE PRINCIPAL
   ═══════════════════════════════════════════════════════════ */
export default function GestionPedidos() {
  const [usuarios, setUsuarios] = useState([]);
  // Lista amplia: sirve para resolver el nombre de quien ya está asignado,
  // incluso si es alguien que hoy no podría recibir una asignación nueva.
  const empleados = (usuarios || []).filter(u =>
    u.tipo === "empleado" && u.estado && (
      u.idRol === 1 || u.idRol === 4 ||
      ["admin", "administrador", "domiciliario"].includes((u.rol || "").toLowerCase())
    )
  );
  // A quién SÍ se le puede asignar un domicilio. La lista de arriba incluye a
  // los administradores a propósito, y por eso "Administrador Toston" salía
  // como opción al elegir repartidor.
  const repartidores = (usuarios || []).filter(esEmpleadoRepartidor);

  // Búsqueda inicial desde ?search= (p. ej. al llegar desde Órdenes de Producción,
  // que enlaza al pedido de una orden con ?search=<ID_Venta>).
  const location      = useLocation();
  const initialSearch = new URLSearchParams(location.search).get("search") || "";

  const [pedidos,       setPedidos]       = useState([]);
  const [totalPedidos,  setTotalPedidos]  = useState(0);
  const [loading,       setLoading]       = useState(true);
  const [actionSaving,  setActionSaving]  = useState(false);
  const [search,        setSearch]        = useState(initialSearch);
  const [filterEstado, setFilterEstado] = useState("todos");
  const [filterTipo,   setFilterTipo]   = useState("todos");
  const [filterDesde,  setFilterDesde]  = useState("");
  const [filterHasta,  setFilterHasta]  = useState("");
  const [showFilter,   setShowFilter]   = useState(false);
  const [vista,            setVista]            = useState("activos");
  const [historial,        setHistorial]        = useState([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);
  const [historialLoaded,  setHistorialLoaded]  = useState(false);
  const [errorHistorial,   setErrorHistorial]   = useState(null);
  const [page,         setPage]         = useState(1);
  const [modal,        setModal]        = useState(null);
  const [toast,        setToast]        = useState(null);
  const filterRef = useRef();

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3200);
  };

  const cargarHistorial = async () => {
    if (historialLoaded) return;
    setLoadingHistorial(true);
    setErrorHistorial(null);
    try {
      const data = await getHistorialPedidos({ porPagina: 100 });
      setHistorial(data.pedidos);
      setHistorialLoaded(true);
    } catch (err) {
      // El historial se arma con /ventas/, que requiere el permiso ver_pedidos.
      // Si falta, antes la pestaña quedaba vacía sin decir por qué.
      const msg = /403|permiso/i.test(err?.message || "")
        ? "No tienes permiso para ver el historial de pedidos (ver_pedidos)."
        : (err?.message || "No se pudo cargar el historial.");
      setErrorHistorial(msg);
      showToast(msg, "error");
    } finally {
      setLoadingHistorial(false);
    }
  };

  const reintentarHistorial = () => {
    setHistorialLoaded(false);
    setErrorHistorial(null);
    cargarHistorial();
  };

  const handleCambiarVista = (v) => {
    setVista(v);
    setPage(1);
    if (v === "historial") cargarHistorial();
  };

  const cargarDatos = async (busqueda = null) => {
    setLoading(true);
    try {
      const [data, prodData] = await Promise.all([
        getPedidos({ porPagina: 100, busqueda }),
        getProductos({ porPagina: 100 }).catch(() => ({ productos: [] })),
      ]);

      setTotalPedidos(data.total || 0);

      const productosCatalogo = Array.isArray(prodData?.productos)
        ? prodData.productos
        : Array.isArray(prodData)
          ? prodData
          : [];

      const produccionIds = new Set(
        productosCatalogo
          .filter(esProductoConProduccion)
          .map(producto => normalizeProductoId(producto?.ID_Producto ?? producto?.id))
          .filter(Boolean)
      );

      const enhanced = data.pedidos.map(p => ({
        ...p,
        requiereProduccion: Boolean(p.requiereProduccion) ||
          (p.productosItems || []).some(i => produccionIds.has(normalizeProductoId(i.idProducto))),
      }));

      if (busqueda) {
        // Con búsqueda activa mostramos solo los resultados del servidor, sin merge
        setPedidos(enhanced.sort((a, b) => b.id - a.id));
      } else {
        setPedidos(prev => {
          const newIds = new Set(data.pedidos.map(p => p.id));
          const preserved = prev.filter(p =>
            ["Entregado", "Cancelado"].includes(p.estado) && !newIds.has(p.id)
          );
          return [...enhanced, ...preserved].sort((a, b) => b.id - a.id);
        });
      }
    } catch (err) {
      showToast(err.message || "Error al cargar pedidos", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // El texto inicial de ?search= (normalmente un nº de pedido) se filtra en
    // cliente: la búsqueda del servidor es por nombre de cliente, no por nº.
    cargarDatos();
    getUsuarios({ porPagina: 100 }).then(setUsuarios).catch(() => {});
  }, []);

  // Re-buscar en el servidor cuando el texto de búsqueda cambia (debounce 400ms).
  // Se omite el primer render para no duplicar la carga inicial.
  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) { searchMounted.current = true; return; }
    if (vista !== "activos") return;
    const q = search || null;
    const t = setTimeout(() => cargarDatos(q), 400);
    return () => clearTimeout(t);
  }, [search, vista]);

  useEffect(() => {
    const h = e => { if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const listaActual = vista === "activos" ? pedidos : historial;
  const filtered = listaActual.filter(p => {
    const q      = search.toLowerCase();
    // El id además del número: desde producción se llega con el id pelado, y
     // hasta ahora coincidía de casualidad porque "V-43" contiene "43".
    const matchQ = [String(p.id ?? ""), p.numero, p.cliente?.nombre,
                    p.cliente?.correo, p.metodo_pago, p.estado]
      .filter(Boolean).some(v => v.toLowerCase().includes(q));
    const matchE = filterEstado === "todos" || p.estado === filterEstado;
    const matchT =
      filterTipo === "todos"      ? true :
      filterTipo === "domicilio"  ? p.domicilio :
      filterTipo === "tienda"     ? !p.domicilio :
      filterTipo === "produccion" ? p.orden_produccion : true;
    // Fecha range
    let matchFecha = true;
    if (filterDesde || filterHasta) {
      const val = getRecordDate(p) || p.fecha_pedido || p.Fecha_pedido;
      if (!val) matchFecha = false;
      else {
        const d = new Date(String(val).split('T')[0]);
        if (filterDesde && new Date(filterDesde) > d) matchFecha = false;
        if (filterHasta && new Date(filterHasta) < d) matchFecha = false;
      }
    }
    return matchQ && matchE && matchT && matchFecha;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paged      = [...filtered]
    .sort((a, b) => (b.fecha_pedido || '').localeCompare(a.fecha_pedido || ''))
    .slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);

  useEffect(() => setPage(1), [search, filterEstado, filterTipo]);

  const hasFilter = filterEstado !== "todos" || filterTipo !== "todos";

  const handleVerPedido = async (ped) => {
    setModal({ type: "ver", pedido: ped });
    try {
      const fresco = await getPedido(ped.id);
      setModal(prev => prev?.type === "ver" && prev.pedido?.id === ped.id ? { ...prev, pedido: fresco } : prev);
      setPedidos(prev => prev.map(p => p.id === fresco.id ? fresco : p));
    } catch {
      // Si falla el fetch fresco, el modal ya está abierto con el dato cacheado — no hace nada
    }
  };

  const handleCambiarEstadoDirecto = (ped) => {
    setModal({ type: "confirmarEstado", pedido: ped, nuevoEstado: "Confirmado" });
  };

  const handleMarcarListo = (ped) => {
    setModal({ type: "confirmarEstado", pedido: ped, nuevoEstado: "Listo" });
  };

  const handleEntregarPedido = (ped) => {
    // Pedidos con anticipo: mostrar modal de saldo si aún no fue registrado
    if (ped.requiere_anticipo && !ped.pago_final_registrado) {
      setModal({ type: "registrarSaldo", pedido: ped });
      return;
    }
    const esTransferencia = esPagoTransferencia(ped.metodo_pago);
    const estadoPago = ped.estado_pago || "pendiente";
    // Transferencia sin comprobante adjunto (no aplica cuando el crédito cubrió el total)
    if (esTransferencia && Number(ped.total || 0) > 0 && !ped.comprobante) {
      setModal({ type: "errorEstado", mensaje: "No se puede entregar: el pedido no tiene comprobante de pago adjunto. Adjunta el comprobante antes de marcar como entregado." });
      return;
    }
    // Comprobante rechazado
    if (esTransferencia && estadoPago === "comprobante_rechazado") {
      setModal({ type: "errorEstado", mensaje: "El comprobante fue rechazado. El cliente debe subir uno nuevo antes de poder entregar el pedido." });
      return;
    }
    setModal({ type: "confirmarEstado", pedido: ped, nuevoEstado: "Entregado" });
  };

  const handleRegistrarSaldo = async (pedidoId, saldoData) => {
    const ped = pedidos.find(p => p.id === pedidoId);
    if (!ped) return;
    setActionSaving(true);
    try {
      // 1. Registrar el pago final en el backend
      const metodo_pago = saldoData.metodo.includes("Transferencia") ? "Transferencia" : "Efectivo";
      const pedidoActualizado = await registrarPagoFinal(pedidoId, {
        monto:           saldoData.saldo,
        metodo_pago,
        comprobante_url: saldoData.comprobanteUrl ?? null,
      });

      // 2. Marcar como Entregado (el backend ya validó que pago_final_registrado == 1)
      await cambiarEstadoVenta(pedidoId, 8);

      // Fusionar el pedido actualizado (con los datos de pago_final) en el estado local
      setPedidos(prev => prev.map(p =>
        p.id === pedidoId ? { ...p, ...pedidoActualizado, estado: "Entregado" } : p
      ));
      showToast(`Pedido ${ped.numero} entregado — saldo ${fmt(saldoData.saldo)} registrado`);
      setModal(null);
    } catch (err) {
      setModal({ type: "errorEstado", mensaje: err.message || "No se pudo completar la entrega." });
    } finally {
      setActionSaving(false);
    }
  };

  const handleCancelarPedido = (ped) => {
    setModal({ type: "cancelar", pedido: ped });
  };

  const handleProponerFecha = (ped) => {
    setModal({ type: "proponerFecha", pedido: ped });
  };

  // Camino A: aprobar en 1 clic la fecha que el cliente ya pidió al hacer el pedido.
  const handleAprobarFecha = async (ped) => {
    setActionSaving(true);
    try {
      const pedidoActualizado = await aprobarFechaDirecta(ped.id);
      setPedidos(prev => prev.map(p => p.id === ped.id ? pedidoActualizado : p));
      showToast(`Fecha aprobada para ${ped.numero}. El pedido está ahora ${pedidoActualizado.estado}.`);
    } catch (err) {
      showToast(err.message || "No se pudo aprobar la fecha", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleResolverEscalado = (ped) => {
    setModal({ type: "resolverEscalado", pedido: ped });
  };

  const handleConfirmarAcuerdoEscalado = async (id, fecha) => {
    setActionSaving(true);
    try {
      const pedidoActualizado = await resolverEscaladoAcuerdo(id, fecha);
      setPedidos(prev => prev.map(p => p.id === id ? pedidoActualizado : p));
      showToast(`Fecha acordada para el pedido #${modal?.pedido?.numero}. El pedido está ahora ${pedidoActualizado.estado}.`);
      setModal(null);
    } catch (err) {
      showToast(err.message || "No se pudo acordar la fecha", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleConfirmarCancelacionEscalado = async (id) => {
    setActionSaving(true);
    try {
      const pedidoActualizado = await resolverEscaladoCancelar(id);
      setPedidos(prev => prev.map(p => p.id === id ? pedidoActualizado : p));
      showToast(`Pedido #${modal?.pedido?.numero} cancelado.`);
      setModal(null);
    } catch (err) {
      showToast(err.message || "No se pudo cancelar el pedido", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleVerComprobante = (ped) => {
    setModal({ type: "verComprobante", pedido: ped });
  };

  const handleAprobarComprobante = async (ped) => {
    setActionSaving(true);
    try {
      await aprobarComprobante(ped.id);
      setPedidos(prev => prev.map(p => p.id === ped.id ? { ...p, estado_pago: "pagado_completo" } : p));
      showToast(`Comprobante de ${ped.numero} aprobado`);
      setModal(null);
    } catch (err) {
      setModal({ type: "errorEstado", mensaje: err.message || "No se pudo aprobar el comprobante." });
    } finally {
      setActionSaving(false);
    }
  };

  const handleRegistrarCobro = (ped) => {
    setModal({ type: "registrarCobro", pedido: ped });
  };

  const handleConfirmarCobro = async (idPedido, { recibido }) => {
    setActionSaving(true);
    try {
      await registrarCobroPedido(idPedido, { recibido });
      await cargarDatos();
      setModal(null);
      showToast(recibido ? "Cobro en efectivo registrado" : "Pago marcado como no recibido", "success");
    } catch (e) {
      showToast(e.message || "Error al registrar el cobro", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleSubirComprobante = (ped) => {
    setModal({ type: "subirComprobante", pedido: ped });
  };

  const handleConfirmarSubirComprobante = async (idPedido, url) => {
    setActionSaving(true);
    try {
      await editarPedido(idPedido, { Comprobante_Pago: url });
      await cargarDatos();
      setModal(null);
    } catch (e) {
      showToast(e.message || "Error al guardar el comprobante", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleConfirmarRechazoComprobante = async (id, motivo) => {
    const ped = pedidos.find(p => p.id === id);
    if (!ped) return;
    setActionSaving(true);
    try {
      await rechazarComprobante(id, motivo);
      setPedidos(prev => prev.map(p => p.id === id ? { ...p, estado_pago: "comprobante_rechazado" } : p));
      showToast(`Comprobante de ${ped.numero} rechazado`);
      setModal(null);
    } catch (err) {
      setModal({ type: "errorEstado", mensaje: err.message || "No se pudo rechazar el comprobante." });
    } finally {
      setActionSaving(false);
    }
  };

  const handleAprobarPagoFinal = async (ped) => {
    setActionSaving(true);
    try {
      const actualizado = await aprobarPagoFinal(ped.id);
      await cargarDatos();
      showToast(`Saldo final de ${ped.numero} aprobado`);
      setModal(null);
    } catch (err) {
      setModal({ type: "errorEstado", mensaje: err.message || "No se pudo aprobar el pago final." });
    } finally {
      setActionSaving(false);
    }
  };

  const handleRechazarPagoFinal = async (id, motivo) => {
    setActionSaving(true);
    try {
      await rechazarPagoFinal(id, motivo);
      await cargarDatos();
      showToast(`Saldo final rechazado`);
      setModal(null);
    } catch (err) {
      setModal({ type: "errorEstado", mensaje: err.message || "No se pudo rechazar el pago final." });
    } finally {
      setActionSaving(false);
    }
  };

  const handleRetenerEnTienda = async (ped) => {
    setActionSaving(true);
    try {
      await cambiarEstadoVenta(ped.id, 21);
      await cargarDatos();
      showToast(`Pedido ${ped.numero} retenido en tienda`);
    } catch (err) {
      showToast(err.message || "No se pudo retener el pedido", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleConfirmarFechaPropuesta = async (id, fecha) => {
    const ped = pedidos.find(p => p.id === id);
    if (!ped) return;
    setActionSaving(true);
    try {
      await proponerFechaProduccion(id, fecha);
      setPedidos(prev => prev.map(p => p.id === id ? { ...p, estado: "Fecha propuesta", fecha_propuesta: fecha } : p));
      showToast(`Fecha propuesta enviada al cliente para ${ped.numero}`);
      setModal(null);
    } catch (err) {
      showToast(err.message || "No se pudo proponer la fecha", "error");
    } finally {
      setActionSaving(false);
    }
  };

  const handleConfirmarCambioEstado = async (id, nuevoEstado) => {
    const ped = pedidos.find(p => p.id === id);
    if (!ped) return;
    setActionSaving(true);
    try {
      if (nuevoEstado === "Listo") {
        await cambiarEstadoVenta(id, 11);
      } else if (nuevoEstado === "Entregado") {
        await cambiarEstadoVenta(id, 8);
      } else {
        await confirmarPedido(id);
      }
      setPedidos(prev => prev.map(p => p.id === id ? { ...p, estado: nuevoEstado } : p));
      showToast(
        nuevoEstado === "Listo"     ? `Pedido ${ped.numero} marcado como listo` :
        nuevoEstado === "Entregado" ? `Pedido ${ped.numero} marcado como entregado` :
        `Pedido ${ped.numero} confirmado exitosamente`
      );
      // Tras confirmar, avisar qué unidades van a producción para que el admin
      // proponga una fecha de entrega una vez esté listo.
      const itemsProduccion = nuevoEstado === "Confirmado"
        ? (ped.productosItems || []).filter(it => (it.cantidad_preorden || 0) > 0)
        : [];
      if (itemsProduccion.length > 0) {
        setModal({ type: "avisoProduccion", items: itemsProduccion, pedidoNumero: ped.numero });
      } else {
        setModal(null);
      }
    } catch (err) {
      const errorMsg = err.message || "No se pudo cambiar el estado del pedido.";
      setModal({ type: "errorEstado", mensaje: errorMsg });
    } finally {
      setActionSaving(false);
    }
  };

  const handleConfirmarCancelacion = async (id, motivo) => {
    const ped = pedidos.find(p => p.id === id);
    if (!ped) return;
    setActionSaving(true);
    try {
      await cancelarPedido(id, motivo);

      // Un pedido de recoger en tienda que ya estaba preparado (Listo) tenía el
      // stock descontado, y al cancelar el backend lo devuelve al inventario.
      // Pero el producto ya está hecho y no se puede revender: se registra la
      // salida para darlo de baja y dejar el rastro.
      //
      // Va DESPUÉS de cancelar (antes el stock aún estaba descontado y la
      // salida fallaba por "stock insuficiente"), y solo en pedidos sin
      // domicilio: en los de domicilio el stock se descuenta al entregar, así
      // que aquí no hay nada que dar de baja.
      if (ped.estado === "Listo" && !ped.domicilio) {
        for (const prod of ped.productosItems) {
          try {
            await registrarSalida({
              // El backend espera el motivo de la salida, no el tipo de
              // artículo: antes se enviaba "Producto" y respondía
              // "Input should be 'vencimiento', 'daño', ...".
              tipo: "ajuste",
              idProducto: prod.idProducto,
              cantidad: prod.cantidad,
              motivo: `Pedido ${ped.numero} cancelado: ${motivo}`,
            });
          } catch (errSalida) {
            // El pedido ya quedó cancelado: no se revierte por esto, pero se
            // avisa para que se ajuste el inventario a mano.
            showToast(
              `Pedido cancelado, pero no se pudo dar de baja "${prod.nombre}": ${errSalida.message || "error al registrar la salida"}`,
              "warn",
            );
          }
        }
      }

      setPedidos(prev => prev.map(p => p.id === id ? { ...p, estado: "Cancelado" } : p));
      showToast(`Pedido ${ped.numero} cancelado`);
      setModal(null);
      cargarDatos().catch(() => {});
    } catch (err) {
      const errorMsg = err.message || "No se pudo cancelar el pedido.";
      setModal({ type: "errorEstado", mensaje: errorMsg });
    } finally {
      setActionSaving(false);
    }
  };

  const handleAsignarDomiciliario = async (pedidoId, empId) => {
    const ped = pedidos.find(p => p.id === pedidoId);
    if (!ped) return;
    setActionSaving(true);
    try {
      if (!ped.id_domicilio) throw new Error("Este pedido no tiene domicilio asociado.");
      await asignarRepartidor(ped.id_domicilio, empId);
      // La asignación no mueve el estado del pedido (sigue Listo): solo se
      // refleja el domiciliario, y se recargan los datos reales.
      setPedidos(prev => prev.map(p => p.id === pedidoId ? { ...p, idEmpleado: empId } : p));
      showToast(`Domiciliario asignado para ${ped.numero}`);
      cargarDatos();
      setModal(null);
    } catch (err) {
      const errorMsg = err.message || "No se pudo asignar el domiciliario.";
      setModal({ type: "errorEstado", mensaje: errorMsg });
    } finally {
      setActionSaving(false);
    }
  };

  const handleCrearPedido = async (formData) => {
    try {
      const metodoPago = (formData.metodo_pago || "").split(" ")[0]; // strip emoji
      const payload = {
        ID_Usuario: Number(formData.idCliente),
        Metodo_Pago: metodoPago,
        // Con anticipo el soporte que se adjunta es el del anticipo: sin esto el
        // pedido queda "sin comprobante" y no se puede marcar como entregado.
        comprobante_pago: formData.comprobante || formData.anticipo_comprobante_url || null,
        productos: (formData.productosItems || []).map(p => ({
          ID_Producto: Number(p.idProducto),
          Cantidad:    Number(p.cantidad),
        })),
        Fecha_entrega_esperada: formData.fecha_entrega || null,
        // El formulario ofrecia aplicar el saldo a favor del cliente, pero el
        // dato se perdia aqui al armar el request: el saldo nunca se descontaba.
        pago_efectivo_monto: formData.pago_efectivo_monto ?? null,
        usar_credito:     formData.usar_credito  || false,
        credito_monto:    formData.credito_monto ?? null,
        creado_por_admin: true,
        requiere_anticipo:      formData.requiere_anticipo      || false,
        anticipo_monto:         formData.anticipo_monto         || null,
        anticipo_metodo_pago:   formData.anticipo_metodo_pago   || null,
        anticipo_comprobante_url: formData.anticipo_comprobante_url || null,
        anticipo_registrado:    formData.anticipo_registrado    || false,
        domicilio: formData.domicilio
          ? {
              Direccion_entrega:    formData.direccion_entrega || "",
              // El barrio determina el precio del domicilio; el backend resuelve
              // ciudad, departamento y precio a partir de él.
              ID_Barrio:            formData.id_barrio ? Number(formData.id_barrio) : null,
              Municipio_entrega:    formData.municipio         || null,
              Departamento_entrega: formData.departamento      || null,
              // El complemento y las indicaciones van con las notas: es todo lo
              // que lee quien entrega.
              Observaciones: [formData.observaciones_entrega, formData.notas]
                .filter(Boolean).join(". ") || null,
            }
          : null,
      };
      await crearPedido(payload);
      setModal(null);
      cargarDatos().catch(() => {});
      showToast("Pedido creado correctamente");
    } catch (err) {
      showToast(err.message || "Error al crear pedido", "error");
      throw err;
    }
  };

  const handleEditarPedido = async (formData) => {
    if (formData?._pagoFinal) {
      setModal(null);
      cargarDatos().catch(() => {});
      showToast("Pago final registrado");
      return;
    }
    if (formData?.sinCambios) {
      setModal(null);
      showToast("No se hicieron cambios");
      return;
    }
    try {
      const payload = {
        Metodo_Pago:          (formData.metodo_pago || "").split(" ")[0] || null,
        Domicilio:            formData.domicilio,
        Direccion_Entrega:    formData.direccion_entrega    || null,
        // Al cambiar el barrio se recalcula el precio del domicilio y el Total;
        // municipio/departamento los deriva el backend del barrio.
        ID_Barrio:            formData.id_barrio ? Number(formData.id_barrio) : null,
        Subtotal:             formData.subtotal,
        Descuento:            formData.descuento,
        Total:                formData.total,
        Notas:                formData.notas || null,
        Comprobante_Pago:     formData.comprobante || null,
      };
      await editarPedido(formData.id, payload);
      setModal(null);
      cargarDatos().catch(() => {});
      showToast("Pedido actualizado");
    } catch (err) {
      showToast(err.message || "Error al actualizar pedido", "error");
      throw err;
    }
  };

  return (
    <div className="page-wrapper mod-pedidos">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Pedidos</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        {vista === "activos" && totalPedidos > 100 && !search && (
          <div className="info-box info-box--warning" style={{ marginBottom: 12 }}>
            <span className="info-box__icon"><AlertCircle size={14} /></span>
            <span className="info-box__text">
              Mostrando los 100 pedidos más recientes de <strong>{totalPedidos}</strong> en total.
              Usa la búsqueda para encontrar pedidos anteriores.
            </span>
          </div>
        )}
        <div className="toolbar">
          <div className="search-wrap">
            <Search className="search-icon" size={16} />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar pedido, cliente, estado…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button className={`filter-icon-btn${hasFilter ? " has-filter" : ""}`} onClick={() => setShowFilter(v => !v)} data-tooltip="Filtrar pedidos">▼</button>
            {showFilter && (
              <div className="filter-dropdown filter-dropdown--wide" style={{ minWidth: 340 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <div>
                    <p className="filter-section-title">Estado</p>
                    <div style={{ display: "grid", gap: 2 }}>
                      {[
                        { val: "todos",            label: "Todos",            dot: "#bdbdbd" },
                        { val: "Pendiente",        label: "Pendiente de Aprobación", dot: ESTADO_CONFIG["Pendiente"]?.dot },
                        { val: "Esperando pago",   label: "Esperando pago",   dot: ESTADO_CONFIG["Esperando pago"]?.dot },
                        { val: "En producción",    label: "En producción",    dot: ESTADO_CONFIG["En producción"]?.dot },
                        { val: "Fecha propuesta",  label: "Fecha propuesta",  dot: ESTADO_CONFIG["Fecha propuesta"]?.dot },
                        { val: "Fecha rechazada",  label: "Fecha rechazada",  dot: ESTADO_CONFIG["Fecha rechazada"]?.dot },
                        { val: "Escalado a admin", label: "Escalado a admin", dot: ESTADO_CONFIG["Escalado a admin"]?.dot },
                        { val: "Confirmado",       label: "Confirmado / En Alistamiento", dot: ESTADO_CONFIG["Confirmado"]?.dot },
                        { val: "Listo",         label: "Listo",          dot: ESTADO_CONFIG["Listo"]?.dot },
                        { val: "Asignado",      label: "Asignado",       dot: ESTADO_CONFIG["Asignado"]?.dot },
                        { val: "En camino",     label: "En camino",      dot: ESTADO_CONFIG["En camino"]?.dot },
                        { val: "Entregado",     label: "Entregado",      dot: ESTADO_CONFIG["Entregado"]?.dot },
                        { val: "Cancelado",     label: "Cancelado",      dot: ESTADO_CONFIG["Cancelado"]?.dot },
                      ].map(f => (
                        <button key={f.val} className={`filter-option${filterEstado === f.val ? " active" : ""}`} onClick={() => setFilterEstado(f.val)}>
                          <span className="filter-dot" style={{ background: f.dot }} />{f.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div style={{ borderLeft: "1px solid #f0f0f0", paddingLeft: 12 }}>
                    <p className="filter-section-title">Tipo</p>
                    <div style={{ display: "grid", gap: 2 }}>
                      {[
                        { val: "todos",      label: "Todos",           dot: "#bdbdbd" },
                        { val: "domicilio",  label: "Con domicilio",   dot: "#8e24aa" },
                        { val: "tienda",     label: "Retiro en tienda",dot: "#1976d2" },
                        { val: "produccion", label: "En producción",   dot: "#1565c0" },
                      ].map(f => (
                        <button key={f.val} className={`filter-option${filterTipo === f.val ? " active" : ""}`} onClick={() => { setFilterTipo(f.val); setShowFilter(false); }}>
                          <span className="filter-dot" style={{ background: f.dot }} />{f.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <div style={{ marginTop: 12 }}>
                  <DateRangeFilter
                    desde={filterDesde}
                    hasta={filterHasta}
                    onApply={({desde, hasta}) => { setFilterDesde(desde || ''); setFilterHasta(hasta || ''); setShowFilter(false); }}
                    onClear={() => { setFilterDesde(''); setFilterHasta(''); setShowFilter(false); }}
                    label="Filtrar por fecha del pedido"
                  />
                </div>
                {hasFilter && (
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #f0f0f0", textAlign: "center" }}>
                    <button onClick={() => { setFilterEstado("todos"); setFilterTipo("todos"); setShowFilter(false); }} style={{ fontSize: 11, fontWeight: 700, color: "#c62828", background: "none", border: "none", cursor: "pointer" }}>Limpiar filtros</button>
                  </div>
                )}
              </div>
            )}
          </div>

          {(hasFilter || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilterEstado("todos"); setFilterTipo("todos"); }}>
              <X size={12} style={{display:"inline",verticalAlign:"middle"}} /> Limpiar
            </button>
          )}

          {vista === "activos" && (
            <button className="btn-agregar" onClick={() => setModal({ type: "crear" })} data-tooltip="Crear nuevo pedido">
              Nuevo pedido <span style={{ fontSize: 18 }}>+</span>
            </button>
          )}
        </div>

        <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "2px solid #f0f0f0" }}>
          {[
            { val: "activos",   label: "Pedidos activos",  count: pedidos.length },
            { val: "historial", label: "Historial",         count: historialLoaded ? historial.length : null },
          ].map(t => (
            <button
              key={t.val}
              onClick={() => handleCambiarVista(t.val)}
              style={{
                padding: "9px 22px", fontWeight: 700, fontSize: 13, border: "none", background: "none", cursor: "pointer",
                borderBottom: vista === t.val ? "2px solid #2e7d32" : "2px solid transparent",
                color: vista === t.val ? "#2e7d32" : "#888",
                marginBottom: -2, transition: "color 0.15s",
              }}
            >
              {t.label}
              {t.count !== null && (
                <span style={{ marginLeft: 6, background: vista === t.val ? "#e8f5e9" : "#f5f5f5", color: vista === t.val ? "#2e7d32" : "#888", fontWeight: 800, fontSize: 10, borderRadius: 20, padding: "2px 7px", border: `1px solid ${vista === t.val ? "#a5d6a7" : "#e0e0e0"}` }}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "104px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>Nº</th>
                  <th>Pedido</th>
                  <th>Cliente</th>
                  <th>Fecha</th>
                  <th>Total</th>
                  <th>Entrega</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {(vista === "activos" ? loading : loadingHistorial) ? (
                  <SkeletonRows cols={8} rows={5} />
                ) : vista === "historial" && errorHistorial ? (
                  <tr><td colSpan={8}>
                    <div className="empty-state">
                      <div className="empty-state__icon"><AlertCircle size={40} /></div>
                      <p className="empty-state__text">{errorHistorial}</p>
                      <button className="btn-ghost" style={{ marginTop: 10 }} onClick={reintentarHistorial}>
                        Reintentar
                      </button>
                    </div>
                  </td></tr>
                ) : paged.length === 0 ? (
                  <tr><td colSpan={8}><div className="empty-state"><div className="empty-state__icon"><Package size={40} strokeWidth={1} /></div><p className="empty-state__text">
                    {vista === "historial" ? "Aún no hay pedidos entregados ni cancelados." : "Sin pedidos activos."}
                  </p></div></td></tr>
                ) : paged.map((ped, idx) => {
                  const emp = empleados.find(e => e.id === ped.idEmpleado);
                  return (
                    <tr key={ped.id} className="tbl-row group hover:bg-green-50/30 transition-colors">
                      <td><span className="row-num">{String((safePage - 1) * PER_PAGE + idx + 1).padStart(2, "0")}</span></td>
                      <td>
                        <div className="pedido-num font-black text-green-800">{ped.numero}</div>
                        {ped.sobre_stock && (
                          <div className="text-[9px] font-black text-orange-600 uppercase flex items-center gap-1 mt-0.5">
                            <span className="w-1.5 h-1.5 bg-orange-500 rounded-full" /> Preorden
                          </div>
                        )}
                        {ped.anticipo_registrado && (
                          <div className="text-[9px] font-black text-yellow-700 uppercase flex items-center gap-1 mt-0.5">
                            <span className="w-1.5 h-1.5 bg-yellow-500 rounded-full" /> Anticipo pagado
                          </div>
                        )}
                        {(ped.anticipo_monto > 0) && !ped.anticipo_registrado && (
                          <div className="text-[9px] font-black text-red-600 uppercase flex items-center gap-1 mt-0.5">
                            <span className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" /> Anticipo pendiente
                          </div>
                        )}
                        {ped.comprobante && (
                          <div className="text-[9px] font-black text-green-600 uppercase flex items-center gap-1 mt-0.5">
                            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" /> Pago Adjunto
                          </div>
                        )}
                        {ped.fecha_rechazada && (
                          <div className="text-[9px] font-black text-red-700 uppercase flex items-center gap-1 mt-0.5">
                            <span className="w-1.5 h-1.5 bg-red-600 rounded-full animate-pulse" /> Fecha rechazada
                          </div>
                        )}
                      </td>
                      <td>
                        <div className="client-name font-bold text-gray-800">{ped.cliente?.nombre || "—"}</div>
                        <div className="client-email text-[11px] text-gray-400 font-medium">{ped.cliente?.correo || ""}</div>
                      </td>
                      <td><div className="date-badge inline-block px-2 py-1 bg-gray-100 rounded-lg text-[11px] font-bold text-gray-600 border border-gray-200">{fmtFecha(ped.fecha_pedido)}</div></td>
                      <td>
                        <div className="total-amount font-black text-gray-900">{fmt(ped.total)}</div>
                        <div className="total-method text-[10px] font-black uppercase text-green-600/70">
                          {esPagoTransferencia(ped.metodo_pago) && Number(ped.total || 0) === 0
                            ? "Saldo a favor"
                            : ped.metodo_pago}
                        </div>
                      </td>
                      <td>
                        {ped.domicilio ? (
                          <div className="flex flex-col">
                            <div className="tipo-domicilio text-[11px] font-black text-purple-600 flex items-center gap-1"><Bike size={12} /> Domicilio</div>
                            <div className="tipo-sub text-[10px] font-bold text-gray-400 italic">
                              {(() => {
                                const nombre = ped.nombre_domiciliario
                                  || (emp ? `${emp.nombre} ${emp.apellidos}` : null);
                                if (nombre) return nombre.split(" ").slice(0, 2).join(" ");
                                return ped.estado === "Entregado" ? "—" : "Sin asignar";
                              })()}
                            </div>
                          </div>
                        ) : (
                          <div className="tipo-tienda text-[11px] font-black text-blue-600 flex items-center gap-1"><Store size={12} /> Tienda</div>
                        )}
                      </td>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 3 }}>
                          <EstadoBadge estado={getEstadoDisplay(ped)} />
                          {ped.fecha_rechazada && (
                            <span style={{ fontSize: 9, fontWeight: 700, color: "#c62828", letterSpacing: 0.3, display: "flex", alignItems: "center", gap: 3 }}>
                              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#e53935", display: "inline-block", flexShrink: 0 }} />
                              Cliente rechazó fecha
                            </span>
                          )}
                          {ped.estado_pago && ped.estado_pago !== "pendiente" && (() => {
                            const EP = {
                              pendiente_validacion:  { label: "En revisión",        color: "#e65100" },
                              pagado_completo:       { label: "Pago completo",       color: "#2e7d32" },
                              anticipo_pagado:       { label: "Anticipo pagado",     color: "#f57f17" },
                              efectivo_recibido:     { label: "Efectivo recibido",   color: "#1565c0" },
                              no_recibido:           { label: "No recibido",         color: "#c62828" },
                              comprobante_rechazado: { label: "Comprobante rechazado", color: "#c62828" },
                            };
                            const cfg = EP[ped.estado_pago];
                            if (!cfg) return null;
                            return (
                              <span style={{ fontSize: 9, fontWeight: 700, color: cfg.color, letterSpacing: 0.3, display: "flex", alignItems: "center", gap: 3 }}>
                                <span style={{ width: 5, height: 5, borderRadius: "50%", background: cfg.color, display: "inline-block", flexShrink: 0 }} />
                                {cfg.label}
                              </span>
                            );
                          })()}
                        </div>
                      </td>
                      <td>
                        {vista === "historial" ? (
                          <button
                            style={{ padding: "5px 14px", fontSize: 12, border: "1px solid #e0e0e0", borderRadius: 8, cursor: "pointer", background: "#fafafa", fontWeight: 600, color: "#555" }}
                            onClick={() => handleVerPedido(ped)}
                          >Ver detalles</button>
                        ) : (
                          <AccionesCell
                            ped={ped}
                            saving={actionSaving}
                            onVer={handleVerPedido}
                            onEditar={ped => setModal({ type: "editar", pedido: ped })}
                            onConfirmar={handleCambiarEstadoDirecto}
                            onMarcarListo={handleMarcarListo}
                            onEntregar={handleEntregarPedido}
                            onAsignarDomicilio={ped => setModal({ type: "asignarDomiciliario", pedido: ped })}
                            onCancelar={handleCancelarPedido}
                            onAprobarFecha={handleAprobarFecha}
                            onProponerFecha={handleProponerFecha}
                            onResolverEscalado={handleResolverEscalado}
                            onVerComprobante={handleVerComprobante}
                            onSubirComprobante={handleSubirComprobante}
                            onRegistrarCobro={handleRegistrarCobro}
                            onAprobarPagoFinal={handleAprobarPagoFinal}
                            onRechazarPagoFinal={ped => setModal({ type: "rechazarPagoFinal", pedido: ped })}
                            onRetenerEnTienda={handleRetenerEnTienda}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
                {!(vista === "activos" ? loading : loadingHistorial) && (
                  <FilasRelleno current={paged.length} perPage={PER_PAGE} colSpan={8} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <span className="pagination-count">{filtered.length} pedidos</span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>‹‹</button>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>››</button>
            </div>
          </div>
        </div>
      </div>

      {modal?.type === "ver" && <ModalVerPedido pedido={modal.pedido} empleados={empleados} onClose={() => setModal(null)} onEdit={(ped) => { flushSync(() => setModal(null)); setModal({ type: "editar", pedido: ped }); }} onUpdatePedido={(actualizado) => { setPedidos(prev => prev.map(p => p.id === actualizado.id ? actualizado : p)); setModal(prev => ({ ...prev, pedido: actualizado })); }} />}
      {modal?.type === "confirmarEstado" && <ModalConfirmarEstado pedido={modal.pedido} nuevoEstado={modal.nuevoEstado} onClose={() => setModal(null)} onConfirm={handleConfirmarCambioEstado} />}
      {modal?.type === "cancelar" && <ModalCancelarPedido pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirm={handleConfirmarCancelacion} />}
      {modal?.type === "asignarDomiciliario" && <ModalAsignarDomiciliario pedido={modal.pedido} empleados={empleados} repartidores={repartidores} onClose={() => setModal(null)} onConfirm={handleAsignarDomiciliario} />}
      {modal?.type === "crear" && <CrearPedido onClose={() => setModal(null)} onSave={handleCrearPedido} />}
      {modal?.type === "editar" && <EditarPedido pedido={modal.pedido} onClose={() => setModal(null)} onSave={handleEditarPedido} onAprobarComprobante={handleAprobarComprobante} onRechazarComprobante={(ped) => setModal({ type: "rechazarComprobante", pedido: ped })} />}
      {modal?.type === "proponerFecha"    && <ModalProponerFecha    pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirm={handleConfirmarFechaPropuesta} />}
      {modal?.type === "resolverEscalado" && <ModalResolverEscalado pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirmarAcuerdo={handleConfirmarAcuerdoEscalado} onConfirmarCancelacion={handleConfirmarCancelacionEscalado} />}
      {modal?.type === "registrarSaldo" && <ModalRegistrarSaldo pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirm={handleRegistrarSaldo} />}
      {modal?.type === "registrarCobro"      && <ModalRegistrarCobro      pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirm={handleConfirmarCobro} />}
      {modal?.type === "subirComprobante"    && <ModalSubirComprobante    pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirm={handleConfirmarSubirComprobante} />}
      {modal?.type === "rechazarComprobante" && <ModalRechazarComprobante pedido={modal.pedido} saving={actionSaving} onClose={() => setModal(null)} onConfirm={handleConfirmarRechazoComprobante} />}
      {modal?.type === "verComprobante" && (
        <ModalVerComprobante
          pedido={modal.pedido}
          saving={actionSaving}
          onClose={() => setModal(null)}
          onAprobar={() => handleAprobarComprobante(modal.pedido)}
          onRechazar={() => setModal({ type: "rechazarComprobante", pedido: modal.pedido })}
        />
      )}
      {modal?.type === "errorEstado" && <ModalErrorEstadoPedido mensaje={modal.mensaje} onClose={() => setModal(null)} />}
      {modal?.type === "avisoProduccion" && <ModalAvisoProduccion items={modal.items} pedidoNumero={modal.pedidoNumero} onClose={() => setModal(null)} />}
      {modal?.type === "rechazarPagoFinal" && (
        <ModalRechazarComprobante
          pedido={modal.pedido}
          saving={actionSaving}
          onClose={() => setModal(null)}
          onConfirm={(id, motivo) => handleRechazarPagoFinal(id, motivo)}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}