import { useState, useEffect, useRef, useCallback } from 'react';
import { getMisVentas, getMiVenta, cancelarMiPedido, editarMiPedido, aceptarFechaProduccion, rechazarFechaProduccion, solicitarEscalado, pagarPedido } from '../../../services/pedidosService';
import { getLandingConfig } from '../../../services/landingConfigService';
import { subirImagenCloudinary } from '../../../utils/cloudinary.js';
import { crearDevolucion } from '../../../services/devolucionesService';
import { fmtFecha } from '../../../utils/dateUtils.js';
import { getCurrentUser } from '../../client/profile/services/profileService.js';
import { descargarFacturaPedido } from '../../../utils/facturaGenerator.js';
import SelectorBarrioEntrega from '../../../shared/components/SelectorBarrioEntrega';
import ImageLightbox from '../../../shared/components/ImageLightbox.jsx';
import { formatCOP } from "../../../utils/formato";
import {
  Package, Calendar, MapPin, DollarSign, Leaf, Search,
  ChevronRight, Clock, CheckCircle2, Truck, AlertTriangle,
  XCircle, ShoppingBag, RefreshCw, ChefHat, Inbox, Store,
  Gift, Check, X, FileText, Ban, CreditCard, Building2,
  Banknote, ClipboardList, CornerUpLeft, AlertCircle, PenLine,
  Upload, Paperclip, Download,
} from 'lucide-react';
import '../../../styles/Client.css';

const CUENTA_TRANSFERENCIA = {
  banco:   "Bancolombia",
  titular: "TostonApp S.A.S",
  tipo:    "Ahorros",
  numero:  import.meta.env.VITE_CUENTA_TRANSFERENCIA ?? "54213570938",
};

/* ── Stepper de seguimiento ───────────────────────────── */
const PASOS_DOMICILIO = [
  { key: 'Pendiente',     label: 'Recibido',         Icon: Inbox },
  { key: 'En producción', label: 'Preparación',      Icon: ChefHat },
  { key: 'Confirmado',    label: 'Listo',            Icon: CheckCircle2 },
  { key: 'En camino',     label: 'En camino',        Icon: Truck },
  { key: 'Entregado',     label: 'Entregado',        Icon: Gift },
];
const PASOS_TIENDA = [
  { key: 'Pendiente',     label: 'Recibido',         Icon: Inbox },
  { key: 'En producción', label: 'Preparando',       Icon: ChefHat },
  { key: 'Confirmado',    label: 'Listo en\ntienda', Icon: Store },
  { key: 'Entregado',     label: 'Recogido',         Icon: CheckCircle2 },
];

const getEstadoDisplay = (pedido) =>
  (pedido?.ordenes_en_espera > 0 && pedido?.estado === 'En producción')
    ? 'Pendiente de producción'
    : (pedido?.estado ?? 'Pendiente');

function PedidoStepper({ estado, domicilio }) {
  const pasos = domicilio ? PASOS_DOMICILIO : PASOS_TIENDA;
  // "Pendiente de producción" se muestra en el mismo paso que "En producción"
  const estadoNorm = estado === 'Pendiente de producción' ? 'En producción' : estado;
  const estadoMapped = (domicilio && (estadoNorm === 'Listo' || estadoNorm === 'Asignado')) ? 'Confirmado' : estadoNorm;
  const idx = pasos.findIndex(p => p.key === estadoMapped);
  const activoIdx = idx === -1 ? 0 : idx;
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, marginBottom: 16 }}>
      {pasos.map((paso, i) => {
        const done   = i < activoIdx;
        const active = i === activoIdx;
        return (
          <div key={paso.key} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>
            {i > 0 && (
              <div style={{
                position: 'absolute', top: 14, right: '50%', width: '100%', height: 2,
                background: done || active ? '#2e7d32' : '#e0e0e0', zIndex: 0,
              }} />
            )}
            <div style={{
              width: 28, height: 28, borderRadius: '50%', zIndex: 1, flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: done ? '#2e7d32' : active ? '#e8f5e9' : '#f5f5f5',
              border: `2px solid ${done ? '#2e7d32' : active ? '#2e7d32' : '#e0e0e0'}`,
              transition: 'all 0.3s',
            }}>
              {done ? <Check size={12} color="#fff" strokeWidth={3} /> : <paso.Icon size={13} />}
            </div>
            <p style={{
              fontSize: 8, fontWeight: active ? 800 : 600, marginTop: 4, textAlign: 'center',
              color: done ? '#2e7d32' : active ? '#1a1a1a' : '#9e9e9e',
              lineHeight: 1.3, whiteSpace: 'pre-line',
            }}>{paso.label}</p>
          </div>
        );
      })}
    </div>
  );
}

const VENTANA_EDICION_MS = 10 * 60 * 1000;

function CountdownBanner({ fechaVenta }) {
  const [secsLeft, setSecsLeft] = useState(() => {
    if (!fechaVenta) return 0;
    const diff = VENTANA_EDICION_MS - (Date.now() - new Date(fechaVenta).getTime());
    return Math.max(0, Math.floor(diff / 1000));
  });

  useEffect(() => {
    const id = setInterval(() => setSecsLeft(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  if (secsLeft <= 0) return null;
  const m = String(Math.floor(secsLeft / 60)).padStart(2, '0');
  const s = String(secsLeft % 60).padStart(2, '0');
  return (
    <div style={{
      background: '#fffde7', borderBottom: '1px solid #fff176',
      padding: '6px 16px', display: 'flex', alignItems: 'center', gap: 6,
    }}>
      <Clock size={12} style={{ color: '#f59e0b', flexShrink: 0 }} />
      <span style={{ fontSize: 11, fontWeight: 700, color: '#92400e' }}>
        Puedes editar o cancelar este pedido durante {m}:{s}
      </span>
    </div>
  );
}

const COP = formatCOP;

const ESTADO_CONFIG = {
  'Pendiente': {
    color: 'amber',
    icon: Clock,
    label: 'Pendiente',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    badge: 'bg-amber-100 text-amber-700'
  },
  'Pendiente de producción': {
    color: 'orange',
    icon: ChefHat,
    label: 'Pendiente de producción',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    badge: 'bg-orange-100 text-orange-700'
  },
  'En producción': {
    color: 'blue',
    icon: Package,
    label: 'En producción',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    badge: 'bg-blue-100 text-blue-700'
  },
  'Esperando pago': {
    color: 'orange',
    icon: Banknote,
    label: 'Esperando pago',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    badge: 'bg-orange-100 text-orange-700'
  },
  'Confirmado': {
    color: 'emerald',
    icon: CheckCircle2,
    label: 'Confirmado',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700'
  },
  'Asignado': {
    color: 'purple',
    icon: Truck,
    label: 'Asignado',
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    badge: 'bg-purple-100 text-purple-700'
  },
  'Listo': {
    color: 'emerald',
    icon: CheckCircle2,
    label: 'Listo',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700'
  },
  'En camino': {
    color: 'purple',
    icon: Truck,
    label: 'En camino',
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    badge: 'bg-purple-100 text-purple-700'
  },
  'Entregado': {
    color: 'emerald',
    icon: CheckCircle2,
    label: 'Entregado',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700'
  },
  'Cancelado': {
    color: 'red',
    icon: XCircle,
    label: 'Cancelado',
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    badge: 'bg-red-100 text-red-700'
  },
  'Fecha propuesta': {
    color: 'indigo',
    icon: Calendar,
    label: 'Fecha propuesta',
    bg: 'bg-indigo-50',
    text: 'text-indigo-700',
    border: 'border-indigo-200',
    badge: 'bg-indigo-100 text-indigo-700'
  },
  'Fecha rechazada': {
    color: 'orange',
    icon: AlertTriangle,
    label: 'Fecha rechazada',
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    badge: 'bg-orange-100 text-orange-700'
  },
  'Escalado a admin': {
    color: 'red',
    icon: AlertTriangle,
    label: 'Escalado a admin',
    bg: 'bg-red-50',
    text: 'text-red-800',
    border: 'border-red-300',
    badge: 'bg-red-200 text-red-800'
  },
  'Parcialmente entregado': {
    color: 'emerald',
    icon: Package,
    label: 'Parcialmente entregado',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700'
  },
};

const normalizeComprobanteSrc = (c) => {
  if (!c) return null;
  if (typeof c !== 'string') return null;
  const s = c.trim();
  // already a data URI or absolute/relative URL
  if (s.startsWith('data:') || s.startsWith('http://') || s.startsWith('https://') || s.startsWith('/')) return s;
  // likely a raw base64 string stored in DB (no data: prefix)
  // try to detect base64: long string with only base64 chars and maybe padding
  const base64Like = /^[A-Za-z0-9+/=\n\r]+$/.test(s) && s.length > 100;
  if (base64Like) return 'data:image/jpeg;base64,' + s.replace(/\s+/g, '');
  // fallback: return as-is
  return s;
};

const DEVOLUCION_WINDOW_MS = 60 * 60 * 1000; // 1 hora

const puedeDevolver = (pedido) => {
  if (pedido.estado !== 'Entregado') return false;
  const ref = pedido.fecha_actualizacion || pedido.fecha_pedido;
  if (!ref) return false;
  return Date.now() - new Date(ref).getTime() <= DEVOLUCION_WINDOW_MS;
};

const MOTIVOS_DEV = [
  "Producto en mal estado",
  "Producto incorrecto",
  "Producto vencido",
  "No cumple con lo solicitado",
  "Error en el pedido",
  "Otro",
];

const COP_DEV = formatCOP;

function SolicitarDevolucionModal({ pedido, onClose, onSuccess }) {
  const [items,      setItems]      = useState(
    (pedido.productosItems || []).map(p => ({ ...p, cantDev: 0 }))
  );
  const [motivo,     setMotivo]     = useState('');
  const [comentario, setComentario] = useState('');
  const [saving,     setSaving]     = useState(false);
  const [error,      setError]      = useState('');

  const setCant = (idx, val) => {
    const n = Math.max(0, Math.min(items[idx].cantidad, Number(val) || 0));
    setItems(prev => { const a = [...prev]; a[idx] = { ...a[idx], cantDev: n }; return a; });
  };

  const seleccionados = items.filter(i => i.cantDev > 0);
  const total = seleccionados.reduce((s, i) => s + i.precio * i.cantDev, 0);

  const handleSubmit = async () => {
    if (!motivo)              { setError('Selecciona el motivo de la devolución.'); return; }
    if (seleccionados.length === 0) { setError('Selecciona al menos un producto.'); return; }
    setError('');
    setSaving(true);
    try {
      await crearDevolucion({
        idPedido:  pedido.id,
        motivo,
        comentario,
        productos: seleccionados.map(i => ({
          idProducto:     i.idProducto,
          nombre:         i.nombre,
          cantidad:       i.cantDev,
          precioUnitario: i.precio,
        })),
      });
      onSuccess();
    } catch (e) {
      setError(e.message || 'Error al enviar la solicitud.');
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div
        className="modal-box bg-white w-full max-w-lg shadow-2xl flex flex-col"
        style={{ borderRadius: 24, maxHeight: '90vh', overflow: 'hidden' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ background: 'linear-gradient(135deg,#b71c1c,#c62828)', padding: '18px 22px', borderRadius: '24px 24px 0 0', flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <p style={{ fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.6)', letterSpacing: 1, textTransform: 'uppercase', margin: 0 }}>Devolución · Pedido #{pedido.numero}</p>
            <h2 style={{ margin: '2px 0 0', fontSize: 17, fontWeight: 800, color: '#fff' }}>Solicitar devolución</h2>
          </div>
          <button onClick={onClose} style={{ background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: '50%', width: 32, height: 32, cursor: 'pointer', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><X size={16} /></button>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '18px 22px' }}>
          {/* Plazo info */}
          <div style={{ background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 10, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: '#f57f17', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={14} style={{ flexShrink: 0 }} /> Tienes hasta <strong>1 hora</strong> desde la entrega para solicitar una devolución.
          </div>

          {/* Productos */}
          <p style={{ fontSize: 11, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>¿Qué productos deseas devolver?</p>
          <div style={{ border: '1px solid #f0f0f0', borderRadius: 12, overflow: 'hidden', marginBottom: 16 }}>
            {items.map((item, idx) => (
              <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderBottom: idx < items.length - 1 ? '1px solid #f5f5f5' : 'none', background: item.cantDev > 0 ? '#f9fdf9' : '#fff' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#212121' }}>{item.nombre}</div>
                  <div style={{ fontSize: 11, color: '#9e9e9e' }}>{COP_DEV(item.precio)} c/u · comprado: ×{item.cantidad}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <button onClick={() => setCant(idx, item.cantDev - 1)} disabled={item.cantDev === 0}
                    style={{ width: 28, height: 28, borderRadius: '50%', border: '1.5px solid #e0e0e0', background: '#fff', cursor: item.cantDev === 0 ? 'not-allowed' : 'pointer', fontSize: 16, color: '#616161', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>−</button>
                  <span style={{ minWidth: 24, textAlign: 'center', fontWeight: 800, fontSize: 14, color: item.cantDev > 0 ? '#c62828' : '#bdbdbd' }}>{item.cantDev}</span>
                  <button onClick={() => setCant(idx, item.cantDev + 1)} disabled={item.cantDev >= item.cantidad}
                    style={{ width: 28, height: 28, borderRadius: '50%', border: '1.5px solid #e0e0e0', background: '#fff', cursor: item.cantDev >= item.cantidad ? 'not-allowed' : 'pointer', fontSize: 16, color: '#616161', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>+</button>
                </div>
                {item.cantDev > 0 && (
                  <div style={{ minWidth: 72, textAlign: 'right', fontSize: 13, fontWeight: 700, color: '#c62828' }}>{COP_DEV(item.precio * item.cantDev)}</div>
                )}
              </div>
            ))}
            {total > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', background: '#fff3f3', borderTop: '1.5px solid #ffcdd2' }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#c62828', textTransform: 'uppercase' }}>Total a devolver</span>
                <span style={{ fontSize: 15, fontWeight: 800, color: '#c62828' }}>{COP_DEV(total)}</span>
              </div>
            )}
          </div>

          {/* Motivo */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Motivo <span style={{ color: '#c62828' }}>*</span></label>
            <select value={motivo} onChange={e => setMotivo(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', outline: 'none', background: '#fff' }}>
              <option value="">Selecciona el motivo…</option>
              {MOTIVOS_DEV.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>

          {/* Comentario */}
          <div style={{ marginBottom: 4 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Comentario adicional (opcional)</label>
            <textarea rows={2} value={comentario} onChange={e => setComentario(e.target.value)}
              placeholder="Describe el problema con más detalle…"
              style={{ width: '100%', padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', resize: 'vertical', outline: 'none', boxSizing: 'border-box' }} />
          </div>

          {error && (
            <div style={{ background: '#ffebee', border: '1px solid #ffcdd2', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: '#c62828', fontWeight: 600, marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <AlertTriangle size={13} /> {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ flexShrink: 0, padding: '14px 22px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '10px 20px', borderRadius: 10, border: '1px solid #e0e0e0', background: '#fff', color: '#616161', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
            Cancelar
          </button>
          <button onClick={handleSubmit} disabled={saving || total === 0}
            style={{ padding: '10px 22px', borderRadius: 10, border: 'none', background: saving || total === 0 ? '#ef9a9a' : '#c62828', color: '#fff', fontSize: 13, fontWeight: 700, cursor: saving || total === 0 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
            {saving ? 'Enviando…' : <><CornerUpLeft size={14} /> Solicitar devolución</>}
          </button>
        </div>
      </div>
    </div>
  );
}

const PedidosClientePage = () => {
  const [pedidos,        setPedidos]        = useState([]);
  const [user,           setUser]           = useState(null);
  const [searchTerm,     setSearchTerm]     = useState('');
  const [selectedPedido, setSelectedPedido] = useState(null);
  const [filterEstado,   setFilterEstado]   = useState('todos');
  const [cancelando,     setCancelando]     = useState(false);
  const [confirmCancel,  setConfirmCancel]  = useState(false);
  const [cancelError,    setCancelError]    = useState('');
  const [accionFecha,    setAccionFecha]    = useState(null); // "aceptar" | "rechazar"
  const [accionFechaErr, setAccionFechaErr] = useState('');
  /// Por qué el cliente no puede recibir en la fecha propuesta.
  ///
  /// Es opcional, pero es lo que le permite al administrador proponer algo que
  /// sirva en vez de tirar otra fecha a ver si pega.
  const [motivoRechazo, setMotivoRechazo] = useState('');
  const [devModal,             setDevModal]             = useState(null);
  const [devToast,             setDevToast]             = useState(null);
  const [modalDetailLoading,   setModalDetailLoading]   = useState(false);
  const [editModal,            setEditModal]            = useState(null);
  const [editMetodoPago,       setEditMetodoPago]       = useState('');
  const [editQuiereDomicilio,  setEditQuiereDomicilio]  = useState(null);
  const [editIdBarrio,         setEditIdBarrio]         = useState(null);
  const [editDireccion,        setEditDireccion]        = useState('');
  const [editNotas,            setEditNotas]            = useState('');
  const [editGuardando,        setEditGuardando]        = useState(false);
  const [editError,            setEditError]            = useState('');
  // Comprobante para Transferencia / Mixto
  const [editComprobante,      setEditComprobante]      = useState(null);   // File | null
  const [editComprobantePreview, setEditComprobantePreview] = useState(null); // URL | dataURL | null
  // Monto en efectivo para Mixto
  const [editMontoEfectivo,    setEditMontoEfectivo]    = useState('');
  // Cantidades + fecha al reabrir la negociación desde "Editar pedido"
  // (Pendiente de Aprobación / Fecha propuesta).
  const [editCantidades,       setEditCantidades]       = useState({});
  const [editFechaEntrega,     setEditFechaEntrega]     = useState('');

  // Pagar el pedido (o su anticipo) mientras está 'Esperando pago'
  const [pagoArchivo,     setPagoArchivo]     = useState(null);
  const [pagoPreview,     setPagoPreview]     = useState(null);
  const [pagoMonto,       setPagoMonto]       = useState('');
  const [pagoGuardando,   setPagoGuardando]   = useState(false);
  const [pagoError,       setPagoError]       = useState('');

  // Canal de excepción: el cliente pide hablar directo con el admin en vez
  // de seguir rechazando la fecha contraofrecida.
  const [escalando,       setEscalando]       = useState(false);
  const [contactoAdmin,   setContactoAdmin]   = useState(null);

  // Ref para acceder al pedido seleccionado dentro del interval sin recrear el callback
  const selectedPedidoRef = useRef(null);
  selectedPedidoRef.current = selectedPedido;

  const fetchPedidos = useCallback(() => {
    getMisVentas({ porPagina: 100 }).then(data => {
      const lista = data.pedidos || [];
      setPedidos(lista);
      // Actualizar el modal si está abierto.
      const curr = selectedPedidoRef.current;
      if (curr) {
        const actualizado = lista.find(p => p.id === curr.id);
        if (actualizado) {
          setSelectedPedido(actualizado);
        }
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    getLandingConfig().then(cfg => setContactoAdmin({
      telefono1: cfg?.contactPhone1 || '',
      telefono2: cfg?.contactPhone2 || '',
    })).catch(() => {});
  }, []);

  useEffect(() => {
    const currentUser = getCurrentUser();
    setUser(currentUser);
    fetchPedidos();
    // Polling cada 30s para actualizar estados
    const timer = setInterval(fetchPedidos, 30000);
    return () => clearInterval(timer);
  }, [fetchPedidos]);

  // getMisVentas ya devuelve solo los pedidos del usuario autenticado
  const userPedidos = pedidos;

  const filteredPedidos = userPedidos.filter(p => {
    const matchSearch =
      (p.numero || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.cliente?.nombre || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchEstado = filterEstado === 'todos' || p.estado === filterEstado;
    return matchSearch && matchEstado;
  }).sort((a, b) => new Date(b.fecha_pedido) - new Date(a.fecha_pedido));

  const handleRequestReturn = (pedido) => {
    closeModal();
    setDevModal(pedido);
  };

  const handleCancelarPedido = async (pedido) => {
    setCancelando(true);
    setCancelError('');
    try {
      await cancelarMiPedido(pedido.id);
      setSelectedPedido(null);
      setConfirmCancel(false);
      fetchPedidos();
    } catch (err) {
      setCancelError(err.message || 'No se pudo cancelar el pedido. Intenta de nuevo.');
    } finally {
      setCancelando(false);
    }
  };

  const ESTADOS_CANCELABLES = ['Pendiente', 'Fecha propuesta', 'Fecha rechazada', 'Escalado a admin'];

  const abrirEditModal = (pedido) => {
    const metodo = pedido.metodo_pago || pedido.Metodo_Pago || '';
    const lleva = metodo === 'Transferencia' || metodo === 'Mixto';
    setEditMetodoPago(metodo);
    setEditQuiereDomicilio(null);
    setEditIdBarrio(null);
    setEditDireccion('');
    setEditNotas('');
    setEditError('');
    setEditComprobante(null);
    // Pre-poblar el preview si ya tienen comprobante con ese método
    setEditComprobantePreview(lleva ? (pedido.comprobante || null) : null);
    setEditMontoEfectivo(pedido.monto_efectivo != null ? String(pedido.monto_efectivo) : '');
    // Reabrir negociación (Pendiente de Aprobación / Fecha propuesta): cantidades
    // de las líneas ya pedidas + la fecha límite deseada.
    setEditCantidades(Object.fromEntries((pedido.productosItems || []).map(it => [it.idProducto, it.cantidad])));
    setEditFechaEntrega(pedido.fecha_propuesta ? pedido.fecha_propuesta.slice(0, 10) : '');
    setEditModal(pedido);
  };

  const puedeReabrirNegociacion = (pedido) => ['Pendiente', 'Fecha propuesta'].includes(pedido?.estado) && pedido?.requiereFechaPropuesta;

  const handleEditarPedido = async () => {
    setEditGuardando(true);
    setEditError('');

    const metodoPagoActual = editModal.metodo_pago || editModal.Metodo_Pago || '';
    const cambioMetodo = editMetodoPago !== metodoPagoActual;
    const requiereComprobante = editMetodoPago === 'Transferencia' || editMetodoPago === 'Mixto';

    // Validar comprobante cuando se cambia a un método con transferencia
    if (cambioMetodo && requiereComprobante && !editComprobantePreview) {
      setEditError('Adjunta el comprobante de la transferencia antes de guardar.');
      setEditGuardando(false);
      return;
    }

    // Validar monto efectivo para Mixto
    if (editMetodoPago === 'Mixto') {
      const ef = Number(editMontoEfectivo) || 0;
      const totalPedido = Number(editModal.total) || 0;
      if (ef <= 0 || ef >= totalPedido) {
        setEditError(`El monto en efectivo debe ser mayor a $0 y menor al total (${COP(totalPedido)}).`);
        setEditGuardando(false);
        return;
      }
    }

    try {
      const datos = {};

      if (cambioMetodo) datos.Metodo_Pago = editMetodoPago;

      // Subir comprobante a Cloudinary si es un archivo nuevo
      if (editComprobante instanceof File) {
        try {
          datos.Comprobante_Pago = await subirImagenCloudinary(editComprobante);
        } catch {
          setEditError('Error al subir el comprobante. Inténtalo de nuevo.');
          setEditGuardando(false);
          return;
        }
      } else if (requiereComprobante && editComprobantePreview && cambioMetodo) {
        // URL existente que venía pre-poblada al abrir el modal
        datos.Comprobante_Pago = editComprobantePreview;
      }

      // Montos para Mixto
      if (editMetodoPago === 'Mixto') {
        datos.Monto_Efectivo = Number(editMontoEfectivo) || 0;
      }

      if (editQuiereDomicilio !== null) {
        datos.quiere_domicilio = editQuiereDomicilio;
        if (editQuiereDomicilio) {
          if (!editIdBarrio) {
            setEditError('Selecciona el barrio de entrega para el domicilio');
            setEditGuardando(false);
            return;
          }
          datos.ID_Barrio = editIdBarrio;
          if (editDireccion) datos.Direccion_Entrega = editDireccion;
          if (editNotas) datos.Notas = editNotas;
        }
      }

      // Reabrir negociación: cantidades y/o fecha límite deseada. Solo mientras
      // el pedido está Pendiente de Aprobación o con una fecha propuesta.
      if (puedeReabrirNegociacion(editModal)) {
        const cantidadesOriginales = Object.fromEntries((editModal.productosItems || []).map(it => [it.idProducto, it.cantidad]));
        const cambioCantidades = Object.entries(editCantidades).some(
          ([id, cant]) => Number(cant) !== Number(cantidadesOriginales[id])
        );
        if (cambioCantidades) {
          datos.productos = Object.entries(editCantidades).map(([id, cant]) => ({
            ID_Producto: Number(id), Cantidad: Number(cant),
          }));
        }
        const fechaOriginal = editModal.fecha_propuesta ? editModal.fecha_propuesta.slice(0, 10) : '';
        if (editFechaEntrega && editFechaEntrega !== fechaOriginal) {
          datos.Fecha_entrega_esperada = `${editFechaEntrega}T00:00:00`;
        }
      }

      if (!Object.keys(datos).length) {
        setEditModal(null);
        return;
      }

      await editarMiPedido(editModal.id, datos);
      setEditModal(null);
      fetchPedidos();
    } catch (err) {
      setEditError(err.message || 'No se pudo guardar. Intenta de nuevo.');
    } finally {
      setEditGuardando(false);
    }
  };

  const handleAceptarFecha = async (pedido) => {
    setAccionFecha("aceptar");
    setAccionFechaErr('');
    try {
      const actualizado = await aceptarFechaProduccion(pedido.id);
      setSelectedPedido(actualizado);
      fetchPedidos();
    } catch (e) {
      setAccionFechaErr(e.message || 'No se pudo aceptar la fecha');
    } finally {
      setAccionFecha(null);
    }
  };

  const handleRechazarFecha = async (pedido) => {
    setAccionFecha("rechazar");
    setAccionFechaErr('');
    try {
      const actualizado = await rechazarFechaProduccion(pedido.id, motivoRechazo.trim() || null);
      setMotivoRechazo('');
      setSelectedPedido(actualizado);
      fetchPedidos();
      // keep modal open so user sees the "Pendiente de Aprobación" state again
    } catch (e) {
      setAccionFechaErr(e.message || 'No se pudo rechazar la fecha');
    } finally {
      setAccionFecha(null);
    }
  };

  // Canal de excepción: pide hablar directo con el admin en vez de seguir
  // rechazando la contraoferta de fecha.
  const handleSolicitarEscalado = async (pedido) => {
    setEscalando(true);
    setAccionFechaErr('');
    try {
      const actualizado = await solicitarEscalado(pedido.id);
      setSelectedPedido(actualizado);
      fetchPedidos();
    } catch (e) {
      setAccionFechaErr(e.message || 'No se pudo enviar la solicitud');
    } finally {
      setEscalando(false);
    }
  };

  // Sube el comprobante (o el anticipo) de un pedido 'Esperando pago'.
  const handlePagarPedido = async (pedido) => {
    if (!pagoArchivo) { setPagoError('Adjunta el comprobante de la transferencia.'); return; }
    const minimo = pedido.requiere_anticipo ? Number(pedido.anticipo_requerido || 0) : null;
    const monto  = pedido.requiere_anticipo ? Number(pagoMonto || 0) : null;
    if (pedido.requiere_anticipo && monto < minimo) {
      setPagoError(`El anticipo mínimo es ${COP(minimo)} (50% del pedido).`);
      return;
    }
    setPagoGuardando(true);
    setPagoError('');
    try {
      const comprobante_url = await subirImagenCloudinary(pagoArchivo);
      const actualizado = await pagarPedido(pedido.id, { comprobante_url, monto });
      setSelectedPedido(actualizado);
      setPagoArchivo(null);
      setPagoPreview(null);
      setPagoMonto('');
      fetchPedidos();
    } catch (e) {
      setPagoError(e.message || 'No se pudo enviar el pago. Intenta de nuevo.');
    } finally {
      setPagoGuardando(false);
    }
  };

  const closeModal = () => {
    setSelectedPedido(null);
    setConfirmCancel(false);
    setCancelError('');
    setAccionFechaErr('');
  };

  const openModal = (pedido) => {
    // Muestra el pedido del listado de inmediato (el modal no queda en blanco).
    setSelectedPedido(pedido);
    setConfirmCancel(false);
    setCancelError('');
    setPagoArchivo(null);
    setPagoPreview(null);
    setPagoMonto('');
    setPagoError('');
    // Carga el detalle completo en segundo plano.
    setModalDetailLoading(true);
    getMiVenta(pedido.id)
      .then(full => {
        if (selectedPedidoRef.current?.id === full.id) setSelectedPedido(full);
      })
      .catch(() => {})
      .finally(() => setModalDetailLoading(false));
  };

  if (!user)
    return (
      <div className="flex items-center justify-center min-h-[60vh] bg-gray-50/50">
        <div className="text-center">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse">
            <Clock className="text-green-600" size={32} />
          </div>
          <p className="font-black text-gray-400 uppercase tracking-widest text-sm">Cargando tus pedidos...</p>
        </div>
      </div>
    );

  return (
    <div className="toston-page min-h-screen bg-gray-50/30">
      {/* ── Hero Refinado ── */}
      <header className="page-hero">
        <div className="page-hero__inner">
          <div className="relative z-10">
            <span className="page-hero__label inline-flex items-center gap-1.5 px-3 py-1 bg-white/10 backdrop-blur-md rounded-full text-[10px] font-black uppercase tracking-widest text-white border border-white/10 mb-4">
              <Leaf size={12} className="text-white" /> Tostón App
            </span>
            <h1 className="page-hero__title text-4xl md:text-5xl font-black text-white tracking-tight mb-2">
              Mis <em className="not-italic text-white opacity-90">Pedidos</em>
            </h1>
            <p className="page-hero__sub text-white/70 max-w-lg font-medium">
              Sigue el progreso de tus antojos en tiempo real.
            </p>
          </div>

          <div className="relative group">
            <div className="absolute inset-0 bg-white rounded-2xl blur-xl opacity-20 group-hover:opacity-40 transition-opacity"></div>
            <div className="page-hero__badge relative bg-white/10 backdrop-blur-xl border border-white/20 p-4 rounded-2xl flex items-center gap-4">
              <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center shadow-lg">
                <ShoppingBag size={24} className="text-white" />
              </div>
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-white/60 leading-none mb-1">Total pedidos</p>
                <p className="text-2xl font-black text-white leading-none">{userPedidos.length}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="page-content max-w-6xl mx-auto px-4 py-8">
        {/* Toolbar Moderna */}
        <div className="flex flex-col md:flex-row gap-4 mb-8">
          <div className="relative flex-1 group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-green-600 transition-colors" size={20} />
            <input
              type="text"
              placeholder="Buscar por número de pedido..."
              className="w-full bg-white border-2 border-gray-100 rounded-2xl py-4 pl-12 pr-10 text-sm font-bold focus:border-green-500 outline-none shadow-sm hover:shadow-md transition-all"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
                title="Limpiar búsqueda"
              >
                <X size={16} />
              </button>
            )}
          </div>

          <div className="flex gap-2 overflow-x-auto pb-2 md:pb-0 no-scrollbar items-center">
            <div className="flex items-center gap-2 bg-white p-1.5 rounded-2xl border-2 border-gray-100 shadow-sm">
              <button
                className={`px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${
                  filterEstado === 'todos'
                    ? 'bg-green-700 text-white shadow-lg shadow-green-200'
                    : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                }`}
                onClick={() => setFilterEstado('todos')}
              >
                Todos
              </button>
              {['Pendiente', 'Esperando pago', 'En producción', 'Fecha propuesta', 'Fecha rechazada', 'Escalado a admin', 'En camino', 'Entregado', 'Cancelado'].map(estado => (
                <button
                  key={estado}
                  className={`px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${
                    filterEstado === estado
                      ? 'bg-green-700 text-white shadow-lg shadow-green-200'
                      : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                  }`}
                  onClick={() => setFilterEstado(estado)}
                >
                  {estado}
                </button>
              ))}
            </div>

            <button
              onClick={fetchPedidos}
              data-tooltip="Actualizar pedidos"
              className="p-3 bg-white border-2 border-gray-100 rounded-2xl text-gray-400 hover:text-green-700 hover:border-green-200 transition-all shadow-sm"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>

        {/* Grid de Pedidos */}
        {filteredPedidos.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredPedidos.map(pedido => {
              const config = ESTADO_CONFIG[getEstadoDisplay(pedido)] || ESTADO_CONFIG['Pendiente'];
              const StatusIcon = config.icon;

              return (
                <div
                  key={pedido.id}
                  className="group bg-white rounded-[32px] border border-gray-100 shadow-sm hover:shadow-xl transition-all duration-500 overflow-hidden flex flex-col hover:-translate-y-1"
                >
                  {/* Card Header */}
                  <div className={`p-6 ${config.bg} border-b border-gray-100/50 flex justify-between items-start`}>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Pedido</span>
                        <span className="px-2 py-0.5 bg-white/60 backdrop-blur-sm rounded-lg text-[11px] font-black text-gray-800 border border-white">
                          #{pedido.numero}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-gray-500">
                        <Calendar size={12} />
                        <span className="text-[11px] font-bold">
                          {fmtFecha(pedido.fecha_pedido)}
                        </span>
                      </div>
                    </div>
                    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl ${config.badge} border border-white shadow-sm`}>
                      <StatusIcon size={12} strokeWidth={3} />
                      <span className="text-[9px] font-black uppercase tracking-widest leading-none">{config.label}</span>
                    </div>
                  </div>

                  {!pedido.requiere_anticipo && <CountdownBanner fechaVenta={pedido.fecha_venta} />}

                  {/* Card Body */}
                  <div className="p-6 flex-1 space-y-4">
                    <div className="flex justify-between items-end">
                      <div>
                        <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-1 leading-none">Total</p>
                        <p className="text-2xl font-black text-gray-900 tracking-tight leading-none">
                          {COP(pedido.total || (
                            (pedido.productosItems || []).reduce((s, p) => s + p.precio * p.cantidad, 0)
                            + (pedido.precio_domicilio_final ?? 0)
                            - (pedido.descuento || 0)
                          ))}
                        </p>
                      </div>
                      <div className="flex flex-col items-end">
                        <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-1 leading-none">Productos</p>
                        <div className="flex -space-x-2">
                           {(pedido.productosItems || []).slice(0, 3).map((_, i) => (
                             <div key={i} className="w-6 h-6 rounded-full bg-green-50 border-2 border-white flex items-center justify-center text-green-600">
                               <Package size={10} />
                             </div>
                           ))}
                           {(pedido.productosItems || []).length > 3 && (
                             <div className="w-6 h-6 rounded-full bg-gray-50 border-2 border-white flex items-center justify-center text-[8px] font-black text-gray-400">
                               +{pedido.productosItems.length - 3}
                             </div>
                           )}
                        </div>
                      </div>
                    </div>

                    <div className="pt-4 border-t border-gray-50">
                      {pedido.estado === 'Fecha propuesta' && pedido.fecha_propuesta && (
                        <div style={{ background: '#e8eaf6', border: '1px solid #9fa8da', borderRadius: 10, padding: '7px 12px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <Calendar size={14} />
                          <span style={{ fontSize: 11, fontWeight: 700, color: '#283593', textTransform: 'capitalize' }}>
                            {new Date(pedido.fecha_propuesta.slice(0, 10) + 'T00:00:00').toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' })}
                          </span>
                        </div>
                      )}
                      <div className="flex items-center gap-2 text-gray-400 mb-4">
                        <MapPin size={14} style={{ color: 'var(--green-600)' }} />
                        <span className="text-[10px] font-bold truncate max-w-[200px]">
                          {pedido.domicilio
                            ? (pedido.direccion_entrega || 'Domicilio')
                            : 'Recogida en local'}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => openModal(pedido)}
                          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-gray-50 hover:bg-green-700 hover:text-white rounded-2xl text-[10px] font-black uppercase tracking-widest transition-all duration-300 group/btn shadow-sm"
                        >
                          Ver detalles
                          <ChevronRight size={12} className="group-hover/btn:translate-x-1 transition-transform" strokeWidth={3} />
                        </button>
                        {!['Cancelado', 'Entregado'].includes(pedido.estado) && !pedido.requiere_anticipo && (
                          <button
                            onClick={() => abrirEditModal(pedido)}
                            className="w-10 h-10 flex items-center justify-center bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded-xl transition-colors shadow-sm"
                            title="Editar pedido"
                          >
                            <PenLine size={15} />
                          </button>
                        )}
                        <button
                          onClick={() => descargarFacturaPedido(pedido, user)}
                          className="w-10 h-10 flex items-center justify-center bg-emerald-50 hover:bg-emerald-100 text-emerald-600 rounded-xl transition-colors shadow-sm"
                          title="Descargar factura"
                        >
                          <Download size={15} />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="bg-white rounded-[40px] p-12 text-center border border-gray-100 shadow-xl max-w-lg mx-auto">
            <div className="w-24 h-24 bg-gray-50 rounded-full flex items-center justify-center mx-auto mb-6">
              <Package size={48} className="text-gray-200" />
            </div>
            <h3 className="text-2xl font-black text-gray-800 mb-2">No hay pedidos</h3>
            <p className="text-gray-400 font-medium mb-8">
              {searchTerm || filterEstado !== 'todos'
                ? 'No encontramos pedidos con estos filtros.'
                : 'Aún no has realizado pedidos deliciosos.'}
            </p>
            {(searchTerm || filterEstado !== 'todos') && (
              <button
                className="btn-primary"
                style={{ padding: '16px 32px' }}
                onClick={() => { setSearchTerm(''); setFilterEstado('todos'); }}
              >
                Ver todos los pedidos
              </button>
            )}
          </div>
        )}
      </main>

      {/* ── Toast devolución ── */}
      {devToast && (
        <div style={{
          position: 'fixed', bottom: 32, left: '50%', transform: 'translateX(-50%)',
          zIndex: 9999, background: '#2e7d32', color: '#fff', borderRadius: 14,
          padding: '14px 24px', fontSize: 14, fontWeight: 700,
          boxShadow: '0 8px 32px rgba(0,0,0,0.2)', whiteSpace: 'nowrap',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <Check size={16} style={{ flexShrink: 0 }} /> {devToast}
        </div>
      )}

      {/* ── Modal Detalle ── */}
      {selectedPedido && (
        <div className="modal-overlay">
          <div
            className="modal-box relative bg-white w-full max-w-lg shadow-2xl overflow-hidden max-h-[90vh] flex flex-col border-none"
            style={{ borderRadius: 28 }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="modal-header shrink-0" style={{ background: 'linear-gradient(135deg, var(--green-900) 0%, var(--green-800) 100%)', padding: '20px 24px' }}>
              <div>
                <p className="modal-header__eyebrow">Pedido #{selectedPedido.numero}</p>
                <h2 className="modal-header__title">Detalle de Compra</h2>
              </div>
              <button onClick={closeModal} className="modal-close-btn"><X size={16} /></button>
            </div>

            {/* Stepper de seguimiento */}
            <div style={{ padding: '16px 20px 0', background: '#fff', flexShrink: 0 }}>
              <p style={{ fontSize: 10, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>Seguimiento del pedido</p>
              <PedidoStepper estado={getEstadoDisplay(selectedPedido)} domicilio={selectedPedido.domicilio} />
            </div>

            {/* Body */}
            <div className="modal-body" style={{ flex: 1, overflowY: 'auto' }}>

              {/* Pendiente de Aprobación: el cliente ya puso su fecha, falta que el
                  admin la apruebe o proponga otra. */}
              {selectedPedido.estado === 'Pendiente' && selectedPedido.requiereFechaPropuesta && (
                <div style={{ background: '#fff8e1', border: '1.5px solid #ffe082', borderRadius: 12, padding: '12px 14px' }}>
                  <p style={{ fontSize: 12, fontWeight: 800, color: '#f57f17', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 5 }}><Package size={13} /> Pendiente de aprobación</p>
                  <p style={{ fontSize: 11, color: '#e65100', lineHeight: 1.5, margin: 0 }}>
                    Uno o más productos requieren producción.
                    {selectedPedido.fecha_propuesta && (
                      <> Pediste tenerlo para el <strong>{new Date(selectedPedido.fecha_propuesta.slice(0, 10) + 'T00:00:00').toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' })}</strong>.</>
                    )} {' '}El administrador va a revisar esa fecha contra la capacidad de la planta y la aprueba o te propone otra.
                  </p>
                </div>
              )}
              {/* Legado: pedidos que ya tenían orden de producción antes de este cambio. */}
              {selectedPedido.orden_produccion && selectedPedido.estado === 'Pendiente' && !selectedPedido.requiereFechaPropuesta && (
                <div style={{ background: '#e3f2fd', border: '1px solid #90caf9', borderRadius: 12, padding: '12px 14px' }}>
                  <p style={{ fontSize: 12, fontWeight: 800, color: '#1565c0', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 5 }}><Package size={13} /> Pedido en espera de producción</p>
                  <p style={{ fontSize: 11, color: '#1976d2', lineHeight: 1.5, margin: 0 }}>
                    Uno o más productos requieren producción. El equipo te avisará cuando avance.
                  </p>
                </div>
              )}

              {/* Esperando pago: el total (sin producción) o el anticipo (con
                  fecha ya aprobada) — siempre por transferencia. */}
              {selectedPedido.estado === 'Esperando pago' && (() => {
                const yaSubido   = selectedPedido.estado_pago === 'pendiente_validacion';
                const rechazado  = selectedPedido.estado_pago === 'comprobante_rechazado';
                const minimo     = selectedPedido.requiere_anticipo ? Number(selectedPedido.anticipo_requerido || 0) : Number(selectedPedido.total || 0);
                return (
                  <div style={{ background: 'linear-gradient(135deg,#fff3e0 0%,#fff8e1 100%)', border: '2px solid #ffb74d', borderRadius: 16, padding: '16px 18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <Banknote size={20} color="#e65100" />
                      <p style={{ fontSize: 13, fontWeight: 800, color: '#e65100', margin: 0 }}>
                        {selectedPedido.requiere_anticipo ? 'Falta el anticipo' : 'Falta el pago'}
                      </p>
                    </div>

                    {rechazado && (
                      <div style={{ background: '#fff', border: '1.5px solid #ef9a9a', borderRadius: 10, padding: '10px 12px', marginBottom: 10 }}>
                        <p style={{ fontSize: 12, fontWeight: 800, color: '#c62828', margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 5 }}>
                          <AlertTriangle size={13} /> El comprobante anterior fue rechazado
                        </p>
                        {selectedPedido.motivo_rechazo_comprobante && (
                          <p style={{ fontSize: 11, color: '#b71c1c', margin: 0 }}>{selectedPedido.motivo_rechazo_comprobante}</p>
                        )}
                      </div>
                    )}

                    {yaSubido ? (
                      <div style={{ background: '#e8f5e9', border: '1.5px solid #a5d6a7', borderRadius: 10, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <CheckCircle2 size={16} color="#2e7d32" />
                        <p style={{ fontSize: 12, fontWeight: 700, color: '#2e7d32', margin: 0 }}>
                          Comprobante enviado. El administrador lo está revisando.
                        </p>
                      </div>
                    ) : (
                      <>
                        {selectedPedido.requiere_anticipo && (
                          <div style={{ marginBottom: 10 }}>
                            <p style={{ fontSize: 11, color: '#e65100', lineHeight: 1.5, marginBottom: 8 }}>
                              Tu fecha de entrega ya quedó aprobada. Este pedido pide un anticipo mínimo del
                              50% (<strong>{COP(minimo)}</strong>) por transferencia antes de empezar a producir; puedes anticipar más si quieres.
                            </p>
                            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                              <button type="button" onClick={() => setPagoMonto(String(minimo))}
                                style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `2px solid ${Number(pagoMonto) === minimo ? '#f9a825' : '#e0e0e0'}`, background: Number(pagoMonto) === minimo ? '#fff8e1' : '#fff', fontWeight: 700, fontSize: 11, cursor: 'pointer' }}>
                                Mínimo (50%)
                              </button>
                              <button type="button" onClick={() => setPagoMonto(String(Number(selectedPedido.total || 0)))}
                                style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `2px solid ${Number(pagoMonto) === Number(selectedPedido.total || 0) ? '#f9a825' : '#e0e0e0'}`, background: Number(pagoMonto) === Number(selectedPedido.total || 0) ? '#fff8e1' : '#fff', fontWeight: 700, fontSize: 11, cursor: 'pointer' }}>
                                Pagar todo
                              </button>
                            </div>
                            <input
                              type="number" min={minimo} step={100} placeholder={`Mínimo ${COP(minimo)}`}
                              value={pagoMonto} onChange={e => setPagoMonto(e.target.value)}
                              style={{ width: '100%', boxSizing: 'border-box', padding: '9px 11px', borderRadius: 10, border: '1.5px solid #ffcc80', fontFamily: 'inherit', fontSize: 12 }}
                            />
                          </div>
                        )}

                        <div style={{ background: '#e3f2fd', border: '1px solid #90caf9', borderRadius: 10, padding: '10px 12px', marginBottom: 10 }}>
                          {[
                            ['Banco', CUENTA_TRANSFERENCIA.banco], ['Titular', CUENTA_TRANSFERENCIA.titular],
                            ['Tipo', CUENTA_TRANSFERENCIA.tipo], ['Número', CUENTA_TRANSFERENCIA.numero],
                          ].map(([l, v]) => (
                            <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                              <span style={{ fontSize: 11, color: '#1565c0', fontWeight: 600 }}>{l}</span>
                              <span style={{ fontSize: 12, color: '#0d47a1', fontWeight: 800 }}>{v}</span>
                            </div>
                          ))}
                        </div>

                        {pagoPreview ? (
                          <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', marginBottom: 8 }}>
                            <ImageLightbox src={pagoPreview} alt="Comprobante" label="Ver comprobante"
                              thumbStyle={{ width: '100%', maxHeight: 150, objectFit: 'contain', display: 'block', borderRadius: 10 }} />
                            <button type="button" onClick={() => { setPagoArchivo(null); setPagoPreview(null); }}
                              style={{ position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,0.6)', color: '#fff', border: 'none', borderRadius: '50%', width: 24, height: 24, cursor: 'pointer' }}>
                              <X size={11} />
                            </button>
                          </div>
                        ) : (
                          <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 76, borderRadius: 10, border: '2px dashed #ffb74d', background: '#fff', cursor: 'pointer', gap: 4, marginBottom: 8 }}>
                            <input type="file" accept="image/*" hidden onChange={e => {
                              const f = e.target.files[0];
                              if (!f) return;
                              const r = new FileReader();
                              r.onload = ev => { setPagoArchivo(f); setPagoPreview(ev.target.result); };
                              r.readAsDataURL(f);
                            }} />
                            <Upload size={18} style={{ color: '#e65100' }} />
                            <span style={{ fontSize: 11, fontWeight: 700, color: '#e65100' }}>Subir comprobante</span>
                          </label>
                        )}

                        {pagoError && <p style={{ fontSize: 11, color: '#c62828', fontWeight: 700, marginBottom: 8 }}>{pagoError}</p>}

                        <button disabled={pagoGuardando} onClick={() => handlePagarPedido(selectedPedido)}
                          style={{ width: '100%', padding: '11px 0', borderRadius: 10, border: 'none', background: '#e65100', color: '#fff', fontWeight: 800, fontSize: 13, cursor: pagoGuardando ? 'not-allowed' : 'pointer' }}>
                          {pagoGuardando ? 'Enviando…' : 'Enviar comprobante'}
                        </button>
                      </>
                    )}
                  </div>
                );
              })()}

              {/* Aviso de fecha propuesta */}
              {selectedPedido.estado === 'Fecha propuesta' && (
                <div style={{ background: 'linear-gradient(135deg,#e8eaf6 0%,#ede7f6 100%)', border: '2px solid #9fa8da', borderRadius: 16, padding: '16px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Calendar size={20} />
                    <p style={{ fontSize: 13, fontWeight: 800, color: '#283593', margin: 0 }}>El equipo propuso una fecha de entrega</p>
                  </div>
                  {selectedPedido.fecha_propuesta && (
                    <div style={{ background: '#fff', border: '1.5px solid #9fa8da', borderRadius: 12, padding: '10px 14px', marginBottom: 10, textAlign: 'center' }}>
                      <p style={{ fontSize: 10, fontWeight: 700, color: '#7986cb', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 4px' }}>Fecha estimada de entrega</p>
                      <p style={{ fontSize: 17, fontWeight: 900, color: '#283593', margin: 0, lineHeight: 1.25, textTransform: 'capitalize' }}>
                        {new Date(selectedPedido.fecha_propuesta.slice(0, 10) + 'T00:00:00').toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                      </p>
                    </div>
                  )}
                  <p style={{ fontSize: 11, color: '#3949ab', marginBottom: 12, lineHeight: 1.5 }}>
                    ¿Puedes recibir tu pedido en esta fecha? Si rechazas, te propondremos una nueva fecha.
                  </p>
                  {/* Si rechaza, por qué. Sin esto el administrador propone la
                      siguiente fecha a ciegas: no es lo mismo "ese día viajo"
                      que "la necesito antes". */}
                  <textarea
                    value={motivoRechazo}
                    onChange={e => setMotivoRechazo(e.target.value)}
                    rows={2}
                    maxLength={255}
                    placeholder="Si no te sirve, cuéntanos por qué (opcional)"
                    style={{
                      width: '100%', boxSizing: 'border-box', marginBottom: 10,
                      padding: '9px 11px', borderRadius: 10,
                      border: '1.5px solid #c5cae9', background: '#fff',
                      fontFamily: 'inherit', fontSize: 12, color: '#1a237e',
                      resize: 'vertical', outline: 'none',
                    }}
                  />
                  {accionFechaErr && <p style={{ fontSize: 11, color: '#c62828', fontWeight: 700, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}><AlertTriangle size={12} /> {accionFechaErr}</p>}
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <button disabled={!!accionFecha} onClick={() => handleAceptarFecha(selectedPedido)}
                      style={{ flex: 1, padding: '11px 0', borderRadius: 10, border: 'none', background: '#2e7d32', color: '#fff', fontWeight: 800, fontSize: 13, cursor: accionFecha ? 'not-allowed' : 'pointer', opacity: accionFecha === 'rechazar' ? 0.5 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                      {accionFecha === 'aceptar' ? 'Aceptando…' : <><Check size={14} /> Sí, acepto esta fecha</>}
                    </button>
                    <button disabled={!!accionFecha} onClick={() => handleRechazarFecha(selectedPedido)}
                      style={{ flex: 1, padding: '11px 0', borderRadius: 10, border: 'none', background: '#c62828', color: '#fff', fontWeight: 800, fontSize: 13, cursor: accionFecha ? 'not-allowed' : 'pointer', opacity: accionFecha === 'aceptar' ? 0.5 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                      {accionFecha === 'rechazar' ? 'Rechazando…' : <><X size={14} /> Rechazar fecha</>}
                    </button>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button disabled={editGuardando} onClick={() => abrirEditModal(selectedPedido)}
                      style={{ flex: 1, padding: '9px 0', borderRadius: 10, border: '1.5px solid #9fa8da', background: '#fff', color: '#3949ab', fontWeight: 700, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                      <PenLine size={13} /> Editar cantidades o fecha
                    </button>
                  </div>
                  {/* Canal de excepción: en vez de rechazar de nuevo, negociar por
                      teléfono. Se resalta más a partir de cierto número de intentos,
                      pero siempre está disponible. */}
                  <div style={{
                    marginTop: 10, padding: '10px 12px', borderRadius: 10,
                    background: selectedPedido.resaltarCanalExcepcion ? '#fff3e0' : '#f5f5ff',
                    border: `1.5px solid ${selectedPedido.resaltarCanalExcepcion ? '#ffb74d' : '#c5cae9'}`,
                  }}>
                    <p style={{ fontSize: 11, fontWeight: 700, color: '#4a4a4a', margin: '0 0 8px', lineHeight: 1.5 }}>
                      {selectedPedido.resaltarCanalExcepcion
                        ? 'Ya llevas varios intentos: mejor hablemos directo y lo resolvemos por teléfono.'
                        : '¿Prefieres resolverlo hablando directo con nosotros?'}
                    </p>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {contactoAdmin?.telefono1 && (
                        <a href={`https://wa.me/57${contactoAdmin.telefono1.replace(/\D/g, '')}`} target="_blank" rel="noreferrer"
                          style={{ flex: '1 1 auto', textAlign: 'center', padding: '8px 10px', borderRadius: 8, background: '#25d366', color: '#fff', fontWeight: 700, fontSize: 11, textDecoration: 'none' }}>
                          WhatsApp {contactoAdmin.telefono1}
                        </a>
                      )}
                      <button disabled={escalando} onClick={() => handleSolicitarEscalado(selectedPedido)}
                        style={{ flex: '1 1 auto', padding: '8px 10px', borderRadius: 8, border: '1.5px solid #f9a825', background: '#fff', color: '#e65100', fontWeight: 700, fontSize: 11, cursor: escalando ? 'not-allowed' : 'pointer' }}>
                        {escalando ? 'Enviando…' : 'Avisar al admin que voy a llamar'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Aviso: fecha rechazada */}
              {selectedPedido.estado === 'Fecha rechazada' && (
                <div style={{ background: 'linear-gradient(135deg,#fff3e0 0%,#fbe9e7 100%)', border: '2px solid #ffb74d', borderRadius: 16, padding: '16px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <AlertTriangle size={20} color="#e65100" />
                    <p style={{ fontSize: 13, fontWeight: 800, color: '#bf360c', margin: 0 }}>Rechazaste la fecha propuesta</p>
                  </div>
                  <p style={{ fontSize: 11, color: '#e65100', lineHeight: 1.5, margin: 0 }}>
                    El equipo te propondrá una nueva fecha pronto.
                    {selectedPedido.intentos_rechazo > 0 && ` (intento ${selectedPedido.intentos_rechazo} de 3)`}
                  </p>
                </div>
              )}

              {/* Aviso: escalado a admin */}
              {selectedPedido.estado === 'Escalado a admin' && (
                <div style={{ background: 'linear-gradient(135deg,#fce4ec 0%,#f3e5f5 100%)', border: '2px solid #f48fb1', borderRadius: 16, padding: '16px 18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <AlertTriangle size={20} color="#880e4f" />
                    <p style={{ fontSize: 13, fontWeight: 800, color: '#880e4f', margin: 0 }}>Pedido en revisión por el administrador</p>
                  </div>
                  <p style={{ fontSize: 11, color: '#ad1457', lineHeight: 1.5, margin: 0 }}>
                    Pediste hablar directo sobre la fecha de entrega. Un administrador te contactará
                    para acordarla por teléfono; en cuanto quede lista, tu pedido sigue su curso normal.
                  </p>
                </div>
              )}

              {/* Spinner mientras se carga el detalle */}
              {modalDetailLoading && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: '#f3f4f6', borderRadius: 10 }}>
                  <RefreshCw size={14} className="animate-spin" style={{ color: '#9ca3af' }} />
                  <span style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Cargando detalle del pedido…</span>
                </div>
              )}

              {/* ── Sección: Información del pedido ── */}
              <div style={{ background: '#f9fdf9', border: '1px solid #e8f5e9', borderRadius: 14, padding: '14px 16px' }}>
                <p style={{ fontSize: 9, fontWeight: 800, color: '#2e7d32', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}><ClipboardList size={12} /> Información del pedido</p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 3px' }}>Número</p>
                    <p style={{ fontSize: 13, fontWeight: 800, color: '#1a1a1a', margin: 0 }}>#{selectedPedido.numero}</p>
                  </div>
                  <div>
                    <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 3px' }}>Fecha del pedido</p>
                    <p style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>{fmtFecha(selectedPedido.fecha_pedido) || '—'}</p>
                  </div>
                  <div>
                    <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 3px' }}>Método de pago</p>
                    <p style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>{selectedPedido.metodo_pago || '—'}</p>
                  </div>
                  <div>
                    <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 3px' }}>Tipo de entrega</p>
                    <p style={{ fontSize: 13, fontWeight: 600, color: '#1a1a1a', margin: 0, display: 'flex', alignItems: 'center', gap: 5 }}>{selectedPedido.domicilio ? <><Truck size={14} /> Domicilio</> : <><Store size={14} /> Retiro en tienda</>}</p>
                  </div>
                  {selectedPedido.fecha_propuesta && selectedPedido.estado !== 'Fecha propuesta' && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 3px' }}>Fecha de entrega estimada</p>
                      <p style={{ fontSize: 13, fontWeight: 700, color: '#283593', margin: 0, textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Calendar size={13} /> {new Date(selectedPedido.fecha_propuesta.slice(0, 10) + 'T00:00:00').toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* ── Sección: Entrega ── */}
              <div style={{ background: '#fff', border: '1px solid #f0f0f0', borderRadius: 14, padding: '14px 16px' }}>
                <p style={{ fontSize: 9, fontWeight: 800, color: '#424242', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}>
                  {selectedPedido.domicilio ? <><Truck size={12} /> Entrega a domicilio</> : <><Store size={12} /> Retiro en tienda</>}
                </p>
                {selectedPedido.domicilio ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      <div>
                        <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 2px' }}>Dirección</p>
                        <p style={{ fontSize: 12, fontWeight: 600, color: '#1a1a1a', margin: 0, lineHeight: 1.4 }}>{selectedPedido.direccion_entrega || '—'}</p>
                      </div>
                      {(selectedPedido.municipio || selectedPedido.departamento) && (
                        <div>
                          <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 2px' }}>Ciudad</p>
                          <p style={{ fontSize: 12, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>{[selectedPedido.municipio, selectedPedido.departamento].filter(Boolean).join(', ')}</p>
                        </div>
                      )}
                    </div>
                    {selectedPedido.nombre_domiciliario ? (
                      <div style={{ background: '#f3e5f5', border: '1px solid #ce93d8', borderRadius: 10, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Truck size={18} />
                        <div>
                          <p style={{ fontSize: 9, fontWeight: 700, color: '#6a1b9a', letterSpacing: 1, textTransform: 'uppercase', margin: 0 }}>Tu domiciliario</p>
                          <p style={{ fontSize: 13, fontWeight: 700, color: '#1a1a1a', margin: 0 }}>{selectedPedido.nombre_domiciliario}</p>
                          <p style={{ fontSize: 10, color: '#9e9e9e', margin: 0 }}>Tiempo estimado: 30–45 min</p>
                        </div>
                      </div>
                    ) : ['Confirmado', 'Listo'].includes(selectedPedido.estado) ? (
                      <div style={{ background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 10, padding: '8px 12px', fontSize: 12, color: '#f57f17', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Clock size={13} /> Asignando domiciliario...
                      </div>
                    ) : null}
                    {selectedPedido.observaciones_domicilio && (
                      <div style={{ background: '#fffde7', border: '1px solid #fff176', borderRadius: 10, padding: '10px 12px', display: 'flex', gap: 8 }}>
                        <PenLine size={14} style={{ flexShrink: 0 }} />
                        <div>
                          <p style={{ fontSize: 9, fontWeight: 700, color: '#f9a825', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 3px' }}>Observaciones</p>
                          <p style={{ fontSize: 12, color: '#5d4037', lineHeight: 1.5, margin: 0 }}>{selectedPedido.observaciones_domicilio}</p>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Store size={22} />
                    <div>
                      <p style={{ fontSize: 12, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>Retiro en el local</p>
                      <p style={{ fontSize: 11, color: '#9e9e9e', margin: 0 }}>Te avisaremos cuando tu pedido esté listo para recoger.</p>
                    </div>
                  </div>
                )}
              </div>

              {/* ── Sección: Pago ── */}
              <div style={{ background: '#fff', border: '1px solid #f0f0f0', borderRadius: 14, padding: '14px 16px' }}>
                <p style={{ fontSize: 9, fontWeight: 800, color: '#424242', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}><CreditCard size={12} /> Información del pago</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

                  {/* Método + cuándo pagar */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 2px' }}>Método</p>
                      <p style={{ fontSize: 13, fontWeight: 700, color: '#1a1a1a', margin: 0, display: 'flex', alignItems: 'center', gap: 5 }}>
                        {(selectedPedido.metodo_pago || '').toLowerCase().includes('transfer') ? <Building2 size={13} /> : <Banknote size={13} />} {selectedPedido.metodo_pago || '—'}
                      </p>
                    </div>
                    <div>
                      <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 2px' }}>Cuándo pagar</p>
                      <p style={{ fontSize: 12, fontWeight: 600, color: '#424242', margin: 0 }}>
                        {(selectedPedido.metodo_pago || '').toLowerCase().includes('transfer')
                          ? 'Comprobante al confirmar'
                          : selectedPedido.domicilio ? 'Al recibir el domicilio' : 'Al retirar en tienda'}
                      </p>
                    </div>
                  </div>
                  {/* Desglose efectivo / transferencia para pago mixto */}
                  {(selectedPedido.metodo_pago || '').toLowerCase() === 'mixto' &&
                    (selectedPedido.monto_efectivo != null || selectedPedido.monto_transferencia != null) && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      <div style={{ background: '#f9f9f9', borderRadius: 8, padding: '8px 12px' }}>
                        <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 2px', display: 'flex', alignItems: 'center', gap: 4 }}><Banknote size={10} /> Efectivo</p>
                        <p style={{ fontSize: 13, fontWeight: 700, color: '#1a1a1a', margin: 0 }}>
                          {COP(selectedPedido.monto_efectivo ?? 0)}
                        </p>
                      </div>
                      <div style={{ background: '#f0f7ff', borderRadius: 8, padding: '8px 12px' }}>
                        <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 2px', display: 'flex', alignItems: 'center', gap: 4 }}><Building2 size={10} /> Transferencia</p>
                        <p style={{ fontSize: 13, fontWeight: 700, color: '#1565c0', margin: 0 }}>
                          {COP(selectedPedido.monto_transferencia ?? 0)}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Estado del pago (anticipo / completo) */}
                  {(selectedPedido.anticipo_registrado || selectedPedido.pago_final_registrado || selectedPedido.sobre_stock || selectedPedido.requiere_anticipo) && (() => {
                    const montoPagado = selectedPedido.pago_final_registrado
                      ? Number(selectedPedido.total || 0)
                      : selectedPedido.anticipo_registrado
                        ? Number(selectedPedido.anticipo_monto ?? selectedPedido.anticipo_requerido ?? 0)
                        : 0;
                    const saldo = Math.max(0, Number(selectedPedido.total || 0) - montoPagado);
                    const esPagoCompleto  = selectedPedido.pago_final_registrado;
                    const esPagoVerde     = esPagoCompleto || !!selectedPedido.anticipo_registrado;
                    return (
                      <div style={{ background: esPagoVerde ? '#e8f5e9' : '#fff8e1', border: `1.5px solid ${esPagoVerde ? '#a5d6a7' : '#ffe082'}`, borderRadius: 10, padding: '10px 12px' }}>
                        <p style={{ fontSize: 10, fontWeight: 800, color: esPagoVerde ? '#2e7d32' : '#e65100', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 5 }}>
                          {esPagoCompleto ? <><Check size={11} /> Pago completo</> : selectedPedido.anticipo_registrado ? <><Check size={11} /> Anticipo pagado</> : <><AlertTriangle size={11} /> Anticipo pendiente</>}
                        </p>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: '#5d4037' }}>Abonado:</span>
                          <span style={{ fontSize: 13, fontWeight: 800, color: '#2e7d32' }}>{COP(montoPagado)}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: '#5d4037' }}>Saldo pendiente:</span>
                          <span style={{ fontSize: 13, fontWeight: 800, color: saldo > 0 ? '#c62828' : '#2e7d32' }}>{COP(saldo)}</span>
                        </div>
                        {selectedPedido.pago_final_fecha && (
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: '#5d4037' }}>Fecha del pago:</span>
                            <span style={{ fontSize: 12, fontWeight: 600, color: '#1a1a1a', display: 'inline-flex', alignItems: 'center', gap: 4 }}><Calendar size={11} /> {fmtFecha(selectedPedido.pago_final_fecha)}</span>
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Info adicional sobre_stock */}
                  {selectedPedido.sobre_stock && (
                    <div style={{ background: '#fff3e0', border: '1px solid #ffcc02', borderRadius: 10, padding: '10px 12px', fontSize: 11, color: '#e65100', lineHeight: 1.5, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                      <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} /> Este pedido tiene productos por encargo y supera los $100.000: requirió un anticipo del 50% para procesarlo.
                    </div>
                  )}

                  {/* Banner anticipo: no puede editarse ni cancelarse */}
                  {selectedPedido.requiere_anticipo && !['Cancelado', 'Entregado'].includes(selectedPedido.estado) && (
                    <div style={{ background: '#f3e5f5', border: '1.5px solid #ce93d8', borderRadius: 10, padding: '10px 12px', fontSize: 11, color: '#6a1b9a', lineHeight: 1.6, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                      <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                      <span>Este pedido no puede editarse ni cancelarse porque requiere anticipo. Si necesitas un cambio, escríbenos directamente.</span>
                    </div>
                  )}

                  {/* Comprobante rechazado — banner prominente */}
                  {selectedPedido.estado_pago === 'comprobante_rechazado' && (
                    <div style={{ background: 'linear-gradient(135deg,#fce4ec 0%,#fff3e0 100%)', border: '2px solid #ef9a9a', borderRadius: 14, padding: '14px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <AlertTriangle size={18} color="#c62828" style={{ flexShrink: 0 }} />
                        <p style={{ fontSize: 13, fontWeight: 800, color: '#c62828', margin: 0 }}>Comprobante rechazado</p>
                      </div>
                      {selectedPedido.motivo_rechazo_comprobante && (
                        <div style={{ background: '#fff', border: '1px solid #ffcdd2', borderRadius: 10, padding: '8px 12px', marginBottom: 8, fontSize: 12, color: '#b71c1c', lineHeight: 1.5 }}>
                          <strong>Motivo:</strong> {selectedPedido.motivo_rechazo_comprobante}
                        </div>
                      )}
                      <p style={{ fontSize: 11, color: '#e53935', margin: 0, lineHeight: 1.5 }}>
                        Sube un nuevo comprobante de pago para continuar con tu pedido.
                      </p>
                    </div>
                  )}

                  {/* Comprobante */}
                  {(() => {
                    const mp = (selectedPedido.metodo_pago || '').toLowerCase();
                    const esTransferencia = mp.includes('transfer') || mp === 'digital';
                    return esTransferencia || !!selectedPedido.comprobante;
                  })() && (
                    <div>
                      <p style={{ fontSize: 9, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 6 }}>Comprobante de pago</p>
                      {selectedPedido.comprobante ? (
                        <div style={{
                          background: selectedPedido.estado_pago === 'comprobante_rechazado' ? '#fff5f5' : '#f0fdf4',
                          border: `1px solid ${selectedPedido.estado_pago === 'comprobante_rechazado' ? '#fca5a5' : '#bbf7d0'}`,
                          borderRadius: 10, padding: '10px 12px',
                        }}>
                          <p style={{ fontSize: 11, fontWeight: 700, color: selectedPedido.estado_pago === 'comprobante_rechazado' ? '#dc2626' : '#15803d', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5 }}>
                            {selectedPedido.estado_pago === 'comprobante_rechazado'
                              ? <><AlertCircle size={13} /> Comprobante rechazado</>
                              : <><Check size={13} /> Comprobante adjuntado</>
                            }
                          </p>
                          <ImageLightbox
                            src={normalizeComprobanteSrc(selectedPedido.comprobante)}
                            alt="Comprobante de pago"
                            label="Ver comprobante"
                            thumbStyle={{ width: '100%', maxHeight: 160, objectFit: 'contain', borderRadius: 8, background: '#fff', cursor: 'zoom-in' }}
                          />
                        </div>
                      ) : !selectedPedido.pago_final_registrado && (
                        <div style={{ background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 10, padding: '8px 12px', fontSize: 12, color: '#f57f17', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <AlertTriangle size={13} /> Aún no se ha adjuntado comprobante de pago
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* ── Sección: Productos ── */}
              <div>
              <p style={{ fontSize: 10, fontWeight: 700, color: '#9e9e9e', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>Productos</p>
              <div style={{ background: '#fff', border: '1px solid #f0f0f0', borderRadius: 12, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f9fdf9' }}>
                      <th style={{ padding: '8px 14px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#2e7d32', textTransform: 'uppercase' }}>Producto</th>
                      <th style={{ padding: '8px 14px', textAlign: 'center', fontSize: 10, fontWeight: 700, color: '#2e7d32', textTransform: 'uppercase' }}>Cant.</th>
                      <th style={{ padding: '8px 14px', textAlign: 'right', fontSize: 10, fontWeight: 700, color: '#2e7d32', textTransform: 'uppercase' }}>Subtotal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selectedPedido.productosItems || []).map((item, idx) => (
                      <tr key={idx} style={{ borderTop: '1px solid #f5f5f5' }}>
                        <td style={{ padding: '8px 14px', fontWeight: 600 }}>
                          {item.nombre}
                          <span style={{ display: 'block', fontSize: 10, color: '#9e9e9e' }}>{COP(item.precio)} c/u</span>
                        </td>
                        <td style={{ padding: '8px 14px', textAlign: 'center' }}>
                          <span style={{ background: '#f1f8f1', border: '1px solid #c8e6c9', borderRadius: 6, padding: '1px 7px', fontSize: 11, fontWeight: 700, color: '#2e7d32' }}>×{item.cantidad}</span>
                        </td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700, color: '#2e7d32' }}>{COP(item.precio * item.cantidad)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    {selectedPedido.domicilio && (() => {
                      const desg = selectedPedido.desglose_domicilio;
                      const base = desg?.base ?? selectedPedido.precio_domicilio_base ?? 0;
                      const final = selectedPedido.precio_domicilio_final ?? base;
                      return (
                        <>
                          <tr style={{ borderTop: '1px solid #f0f0f0', background: '#fafafa' }}>
                            <td colSpan={2} style={{ padding: '8px 14px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#9e9e9e' }}>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Truck size={11} /> Domicilio {selectedPedido.barrio_entrega ? `· ${selectedPedido.barrio_entrega}` : ''}</span>
                            </td>
                            <td style={{ padding: '8px 14px', textAlign: 'right', fontSize: 12, fontWeight: 700, color: '#7b1fa2' }}>
                              {(desg?.ofertas || []).length > 0 && base !== final && (
                                <span style={{ textDecoration: 'line-through', color: '#bdbdbd', fontWeight: 500, marginRight: 4 }}>{COP(base)}</span>
                              )}
                              {final === 0 ? 'Gratis' : COP(final)}
                            </td>
                          </tr>
                          {(desg?.ofertas || []).map((o, i) => (
                            <tr key={i} style={{ background: '#fafafa' }}>
                              <td colSpan={2} style={{ padding: '2px 14px 2px', textAlign: 'right', fontSize: 10.5, color: o.efecto < 0 ? '#2e7d32' : '#e65100' }}>{o.nombre}</td>
                              <td style={{ padding: '2px 14px 2px', textAlign: 'right', fontSize: 10.5, color: o.efecto < 0 ? '#2e7d32' : '#e65100' }}>{o.efecto >= 0 ? '+' : ''}{COP(o.efecto)}</td>
                            </tr>
                          ))}
                        </>
                      );
                    })()}
                    {(selectedPedido.descuento || 0) > 0 && (
                      <tr style={{ borderTop: '1px solid #f0f0f0', background: '#fafafa' }}>
                        <td colSpan={2} style={{ padding: '8px 14px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#1976d2' }}><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><CreditCard size={11} /> Crédito aplicado</span></td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', fontSize: 12, fontWeight: 700, color: '#1565c0' }}>− {COP(selectedPedido.descuento)}</td>
                      </tr>
                    )}
                    <tr style={{ borderTop: '2px solid #e8f5e9', background: '#f9fdf9' }}>
                      <td colSpan={2} style={{ padding: '10px 14px', textAlign: 'right', fontSize: 11, fontWeight: 700, color: '#9e9e9e', textTransform: 'uppercase' }}>Total</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right', fontSize: 15, fontWeight: 800, color: '#2e7d32' }}>
                        {COP(selectedPedido.total || (
                          (selectedPedido.productosItems || []).reduce((s, p) => s + p.precio * p.cantidad, 0)
                          + (selectedPedido.precio_domicilio_final ?? 0)
                          - (selectedPedido.descuento || 0)
                        ))}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
              </div>

            </div>

            {/* Footer */}
            <div className="modal-footer" style={{ flexWrap: 'nowrap', overflowX: 'auto', gap: 8 }}>
              {confirmCancel ? (
                <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <p style={{ fontSize: 12, fontWeight: 700, color: '#b91c1c', margin: 0, display: 'flex', alignItems: 'flex-start', gap: 5 }}>
                    <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} /> ¿Confirmar la cancelación del pedido #{selectedPedido.numero}? Esta acción no se puede deshacer.
                  </p>
                  {cancelError && (
                    <p style={{ fontSize: 11, color: '#b91c1c', background: '#fee2e2', borderRadius: 8, padding: '6px 10px', margin: 0 }}>
                      {cancelError}
                    </p>
                  )}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}
                      onClick={() => { setConfirmCancel(false); setCancelError(''); }}
                    >
                      No, mantener
                    </button>
                    <button
                      style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: 'none', background: '#dc2626', color: '#fff', fontWeight: 700, fontSize: 12, cursor: cancelando ? 'not-allowed' : 'pointer', opacity: cancelando ? 0.7 : 1 }}
                      onClick={() => handleCancelarPedido(selectedPedido)}
                      disabled={cancelando}
                    >
                      {cancelando ? 'Cancelando...' : 'Sí, cancelar pedido'}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <button className="btn-ghost" onClick={closeModal}>Cerrar</button>
                  <button
                    className="btn-cancel"
                    style={{ background: '#f1f8f1', color: '#2e7d32', border: '1.5px solid #c8e6c9', display: 'flex', alignItems: 'center', gap: 6 }}
                    onClick={() => descargarFacturaPedido(selectedPedido, user)}
                  >
                    <FileText size={14} /> Descargar factura
                  </button>
                  {ESTADOS_CANCELABLES.includes(selectedPedido.estado) && !selectedPedido.requiere_anticipo && (
                    <button
                      className="btn-cancel"
                      style={{ background: '#fff5f5', color: '#dc2626', border: '1.5px solid #fca5a5', display: 'flex', alignItems: 'center', gap: 6 }}
                      onClick={() => setConfirmCancel(true)}
                    >
                      <Ban size={14} /> Cancelar pedido
                    </button>
                  )}
                  {selectedPedido.estado_pago === 'comprobante_rechazado' && !['Cancelado', 'Entregado'].includes(selectedPedido.estado) && (
                    <button
                      className="btn-save"
                      style={{ background: '#1565c0', border: 'none', display: 'flex', alignItems: 'center', gap: 6 }}
                      onClick={() => abrirEditModal(selectedPedido)}
                    >
                      <Upload size={14} /> Enviar comprobante
                    </button>
                  )}
                  {!['Cancelado', 'Entregado'].includes(selectedPedido.estado) && !selectedPedido.requiere_anticipo && (
                    <button
                      className="btn-cancel"
                      style={{ background: '#f0f4ff', color: '#3730a3', border: '1.5px solid #a5b4fc', display: 'flex', alignItems: 'center', gap: 6 }}
                      onClick={() => abrirEditModal(selectedPedido)}
                    >
                      <PenLine size={14} /> Editar pedido
                    </button>
                  )}
                  {puedeDevolver(selectedPedido) && (
                    <button className="btn-save" onClick={() => handleRequestReturn(selectedPedido)}>Solicitar devolución</button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
      {/* ── Modal editar pedido ── */}
      {editModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 18, width: '100%', maxWidth: 440, boxShadow: '0 8px 40px rgba(0,0,0,0.18)', display: 'flex', flexDirection: 'column', maxHeight: '90vh' }}>
            {/* Header */}
            <div style={{ padding: '18px 22px 14px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <p style={{ fontWeight: 800, fontSize: 15, color: '#212121', margin: 0 }}>Editar pedido #{editModal.numero}</p>
              <button onClick={() => setEditModal(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9e9e9e' }}><X size={18} /></button>
            </div>

            {/* Body */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px' }}>
              {/* Reabrir negociación: cantidades de lo que ya pediste + fecha límite.
                  No se pueden agregar productos nuevos, solo ajustar cuánto de
                  cada uno. */}
              {puedeReabrirNegociacion(editModal) && (
                <div style={{ marginBottom: 18 }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Cantidades
                  </label>
                  <div style={{ background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 10, padding: '4px 12px', marginBottom: 12 }}>
                    {(editModal.productosItems || []).map(item => (
                      <div key={item.idProducto} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#424242', flex: 1 }}>{item.nombre}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <button type="button"
                            onClick={() => setEditCantidades(prev => ({ ...prev, [item.idProducto]: Math.max(1, (Number(prev[item.idProducto]) || 1) - 1) }))}
                            style={{ width: 24, height: 24, borderRadius: 6, border: '1px solid #e0e0e0', background: '#fff', cursor: 'pointer', fontWeight: 800 }}>−</button>
                          <span style={{ fontSize: 13, fontWeight: 800, minWidth: 20, textAlign: 'center' }}>{editCantidades[item.idProducto] ?? item.cantidad}</span>
                          <button type="button"
                            onClick={() => setEditCantidades(prev => ({ ...prev, [item.idProducto]: (Number(prev[item.idProducto]) || 1) + 1 }))}
                            style={{ width: 24, height: 24, borderRadius: 6, border: '1px solid #e0e0e0', background: '#fff', cursor: 'pointer', fontWeight: 800 }}>+</button>
                        </div>
                      </div>
                    ))}
                  </div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    ¿Para cuándo lo necesitas?
                  </label>
                  <input type="date" value={editFechaEntrega} onChange={e => setEditFechaEntrega(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', outline: 'none', marginBottom: 4 }} />
                  <p style={{ fontSize: 10, color: '#9e9e9e', margin: 0 }}>
                    Guardar cambios aquí vuelve a poner el pedido en "Pendiente de Aprobación".
                  </p>
                </div>
              )}

              {/* Método de pago */}
              <div style={{ marginBottom: 18 }}>
                <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Método de pago</label>
                <select
                  value={editMetodoPago}
                  onChange={e => {
                    const m = e.target.value;
                    setEditMetodoPago(m);
                    // Limpiar comprobante si cambian a Efectivo
                    if (m === 'Efectivo') {
                      setEditComprobante(null);
                      setEditComprobantePreview(null);
                    }
                    setEditError('');
                  }}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', outline: 'none', background: '#fff' }}
                >
                  <option value="Efectivo">Efectivo</option>
                  <option value="Transferencia">Transferencia bancaria</option>
                  {/* Mixto solo disponible si el pedido no requiere anticipo */}
                  {!editModal?.requiere_anticipo && (
                    <option value="Mixto">Mixto (efectivo + transferencia)</option>
                  )}
                </select>
              </div>

              {/* ── Datos bancarios + comprobante (Transferencia o Mixto) ── */}
              {(editMetodoPago === 'Transferencia' || editMetodoPago === 'Mixto') && (
                <div style={{ marginBottom: 18 }}>
                  {/* Datos de la cuenta */}
                  <div style={{ background: '#e3f2fd', border: '1px solid #90caf9', borderRadius: 12, padding: '12px 14px', marginBottom: 12 }}>
                    <p style={{ fontSize: 10, fontWeight: 800, color: '#1565c0', letterSpacing: 1, textTransform: 'uppercase', margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <Building2 size={12} /> Datos para la transferencia
                    </p>
                    {[
                      { label: 'Banco',          value: CUENTA_TRANSFERENCIA.banco },
                      { label: 'Titular',        value: CUENTA_TRANSFERENCIA.titular },
                      { label: 'Tipo de cuenta', value: CUENTA_TRANSFERENCIA.tipo },
                      { label: 'Número',         value: CUENTA_TRANSFERENCIA.numero },
                    ].map(({ label, value }) => (
                      <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 0', borderBottom: '1px solid #bbdefb' }}>
                        <span style={{ fontSize: 11, color: '#1565c0', fontWeight: 600 }}>{label}</span>
                        <span style={{ fontSize: 12, color: '#0d47a1', fontWeight: 800 }}>{value}</span>
                      </div>
                    ))}
                  </div>

                  {/* Monto en efectivo para Mixto */}
                  {editMetodoPago === 'Mixto' && (
                    <div style={{ marginBottom: 12 }}>
                      <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        ¿Cuánto pagas en efectivo? <span style={{ color: '#c62828' }}>*</span>
                      </label>
                      <div style={{ fontSize: 10, color: '#9e9e9e', marginBottom: 6, lineHeight: 1.4 }}>
                        Total del pedido: <strong>{COP(Number(editModal?.total) || 0)}</strong>. El resto va por transferencia.
                      </div>
                      <input
                        type="number"
                        min={1}
                        max={Number(editModal?.total) - 1}
                        value={editMontoEfectivo}
                        onChange={e => setEditMontoEfectivo(e.target.value)}
                        placeholder="Ej: 5000"
                        style={{ width: '100%', padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box' }}
                      />
                      {editMontoEfectivo && Number(editMontoEfectivo) > 0 && Number(editMontoEfectivo) < Number(editModal?.total) && (
                        <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                          <div style={{ flex: 1, background: '#e8f5e9', borderRadius: 8, padding: '6px 10px', textAlign: 'center' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: '#2e7d32', textTransform: 'uppercase' }}>Efectivo</div>
                            <div style={{ fontSize: 13, fontWeight: 800, color: '#1b5e20' }}>{COP(Number(editMontoEfectivo))}</div>
                          </div>
                          <div style={{ flex: 1, background: '#e3f2fd', borderRadius: 8, padding: '6px 10px', textAlign: 'center' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: '#1565c0', textTransform: 'uppercase' }}>Transferencia</div>
                            <div style={{ fontSize: 13, fontWeight: 800, color: '#0d47a1' }}>{COP(Math.max(0, Number(editModal?.total) - Number(editMontoEfectivo)))}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Comprobante de transferencia */}
                  <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Comprobante de {editMetodoPago === 'Mixto' ? 'la transferencia' : 'pago'} <span style={{ color: '#c62828' }}>*</span>
                  </label>
                  {editComprobantePreview ? (
                    <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', marginBottom: 6 }}>
                      <ImageLightbox
                        src={editComprobantePreview}
                        alt="Comprobante"
                        label="Ver comprobante"
                        thumbStyle={{ width: '100%', maxHeight: 160, objectFit: 'contain', display: 'block', borderRadius: 10 }}
                      />
                      <button
                        type="button"
                        onClick={() => { setEditComprobante(null); setEditComprobantePreview(null); }}
                        style={{ position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,0.6)', color: '#fff', border: 'none', borderRadius: '50%', width: 26, height: 26, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      ><X size={12} /></button>
                    </div>
                  ) : (
                    <label style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 80, borderRadius: 10, border: '2px dashed #90caf9', background: '#f3f8ff', cursor: 'pointer', gap: 4 }}>
                      <input
                        type="file"
                        accept="image/*"
                        hidden
                        onChange={e => {
                          const f = e.target.files[0];
                          if (!f) return;
                          const r = new FileReader();
                          r.onload = ev => { setEditComprobante(f); setEditComprobantePreview(ev.target.result); };
                          r.readAsDataURL(f);
                        }}
                      />
                      <Upload size={20} style={{ color: '#1565c0' }} />
                      <span style={{ fontSize: 11, fontWeight: 700, color: '#1565c0' }}>Subir comprobante</span>
                      <span style={{ fontSize: 10, color: '#9e9e9e' }}>JPG, PNG o WEBP</span>
                    </label>
                  )}
                </div>
              )}

              {/* Tipo de entrega */}
              <div style={{ marginBottom: 18 }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: '#616161', display: 'block', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Tipo de entrega</label>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    {[
                      { value: false, label: 'Recoger en tienda', icon: '🏪' },
                      { value: true,  label: 'Domicilio',         icon: '🛵' },
                    ].map(opt => (
                      <button
                        key={String(opt.value)}
                        onClick={() => setEditQuiereDomicilio(prev => prev === opt.value ? null : opt.value)}
                        style={{
                          flex: 1, padding: '10px 8px', borderRadius: 10, border: '1.5px solid',
                          borderColor: editQuiereDomicilio === opt.value ? '#6366f1' : '#e0e0e0',
                          background: editQuiereDomicilio === opt.value ? '#eef2ff' : '#fff',
                          color: editQuiereDomicilio === opt.value ? '#4338ca' : '#616161',
                          fontWeight: 700, fontSize: 12, cursor: 'pointer',
                        }}
                      >
                        {opt.icon} {opt.label}
                      </button>
                    ))}
                  </div>

                  {editQuiereDomicilio === true && !editModal.tiene_domicilio && (
                    <div style={{ marginTop: 4 }}>
                      <SelectorBarrioEntrega
                        onChange={(id, cob) => setEditIdBarrio(cob?.disponible ? id : null)}
                        mostrarCobertura
                        compacto
                      />
                      <input
                        type="text"
                        placeholder="Dirección de entrega (vía, apto, referencia…)"
                        value={editDireccion}
                        onChange={e => setEditDireccion(e.target.value)}
                        style={{ width: '100%', marginTop: 8, padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box' }}
                      />
                      <input
                        type="text"
                        placeholder="Nota para el repartidor (opcional)"
                        value={editNotas}
                        onChange={e => setEditNotas(e.target.value)}
                        style={{ width: '100%', marginTop: 6, padding: '10px 12px', borderRadius: 10, border: '1.5px solid #e0e0e0', fontSize: 13, fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box' }}
                      />
                      {editIdBarrio && (
                        <p style={{ fontSize: 11, color: '#2e7d32', background: '#f1f8e9', borderRadius: 8, padding: '6px 10px', marginTop: 6, margin: 0 }}>
                          Se sumará el costo del domicilio al total del pedido.
                        </p>
                      )}
                    </div>
                  )}

                  {editQuiereDomicilio === true && editModal.tiene_domicilio && (
                    <p style={{ fontSize: 12, color: '#616161', background: '#f5f5f5', borderRadius: 8, padding: '8px 12px', margin: 0 }}>
                      Tu pedido ya tiene domicilio. Si quieres cambiar el barrio o la dirección, contacta a un empleado.
                    </p>
                  )}

                  {editQuiereDomicilio === false && editModal.tiene_domicilio && (
                    <div style={{ background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 10, padding: '10px 14px', fontSize: 12, color: '#f57f17', fontWeight: 600, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                      <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                      El costo del domicilio se restará del total. Si pagaste anticipo superior al nuevo total, el exceso se acreditará a tu cuenta.
                    </div>
                  )}

                  {editQuiereDomicilio === false && !editModal.tiene_domicilio && (
                    <p style={{ fontSize: 12, color: '#616161', background: '#f5f5f5', borderRadius: 8, padding: '8px 12px', margin: 0 }}>
                      Tu pedido ya es de recogida en tienda.
                    </p>
                  )}
                </div>

              {editError && (
                <div style={{ background: '#ffebee', border: '1px solid #ffcdd2', borderRadius: 8, padding: '8px 12px', fontSize: 12, color: '#c62828', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertTriangle size={13} /> {editError}
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ flexShrink: 0, padding: '14px 22px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setEditModal(null)} style={{ padding: '10px 20px', borderRadius: 10, border: '1px solid #e0e0e0', background: '#fff', color: '#616161', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
                Cancelar
              </button>
              <button
                onClick={handleEditarPedido}
                disabled={editGuardando}
                style={{ padding: '10px 22px', borderRadius: 10, border: 'none', background: editGuardando ? '#a5b4fc' : '#4f46e5', color: '#fff', fontSize: 13, fontWeight: 700, cursor: editGuardando ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                {editGuardando ? 'Guardando…' : <><Check size={14} /> Guardar cambios</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal solicitar devolución ── */}
      {devModal && (
        <SolicitarDevolucionModal
          pedido={devModal}
          onClose={() => setDevModal(null)}
          onSuccess={() => {
            setDevModal(null);
            setDevToast('Solicitud de devolución enviada. El equipo la revisará pronto.');
            setTimeout(() => setDevToast(null), 5000);
          }}
        />
      )}
    </div>
  );
};

export default PedidosClientePage;
