import { useState, useEffect, useCallback } from "react";
import { getUser } from "../../../services/authService";
import { getDomicilios, getDomicilio, cambiarEstadoDomicilio, registrarPagoEfectivo } from "../../../services/domiciliosService";
import { ESTADO_DOMICILIO, ESTADO_DOM_CONFIG, labelEstadoDom, cobroEfectivoPendiente, esDomicilioActivo, esPagoMixto, montoACobrar, transicionesDom } from "./estadosDomicilio";
import "./DomiciliarioUI.css";
import "./PedidoActual.css";
import { formatCOP } from "../../../utils/formato";
import {
  Package, CheckCircle2, Truck, XCircle, MapPin, CreditCard,
  Clock, X, Check, Navigation, Map, Banknote, Bike, Wallet,
  RefreshCw, AlertCircle, Route, ShoppingBag,
} from "lucide-react";

const fmt = formatCOP;

// Cual es "el pedido actual" cuando hay varios: primero el que ya va en ruta.
const ESTADO_ORDEN = [
  ESTADO_DOMICILIO.EN_CAMINO,
  ESTADO_DOMICILIO.ASIGNADO,
  ESTADO_DOMICILIO.PENDIENTE,
];

/* Recorrido que dibuja el stepper. Solo se pinta: el orden real y las
   transiciones válidas siguen viviendo en estadosDomicilio.js. La lista
   nunca trae pedidos entregados ni cancelados (se filtra por activos), así
   que el último paso siempre queda por delante. */
const PASOS = [
  { id: ESTADO_DOMICILIO.ASIGNADO,  label: "Asignado",  Icono: Package },
  { id: ESTADO_DOMICILIO.EN_CAMINO, label: "En camino", Icono: Truck },
  { id: ESTADO_DOMICILIO.ENTREGADO, label: "Entregado", Icono: CheckCircle2 },
];

/* Las variables de color viajan al CSS: la hoja no repite ningún hex de
   estado, así sigue mandando estadosDomicilio.js como fuente única. */
const varsEstado = (estadoId) => {
  const cfg = ESTADO_DOM_CONFIG[estadoId] ||
    { dot: "#757575", bg: "#f5f5f5", border: "#e0e0e0", label: "—" };
  return { cfg, vars: { "--e-dot": cfg.dot, "--e-bg": cfg.bg, "--e-border": cfg.border } };
};

const ICONO_ESTADO = { 3: Clock, 10: Package, 9: Truck, 8: CheckCircle2, 5: XCircle };

/* Los pasos que puede dar el repartidor salen de la fuente única de estados.
   Aquí había una tabla propia con un paso "Llegué al local" que mandaba el
   estado 13: ese número es "En producción" de una venta, no un estado de
   domicilio, así que era un paso de más que además no correspondía. El
   recorrido real es Asignado → En camino → Entregado (o Cancelado). */
const ACCION_UI = {
  [ESTADO_DOMICILIO.EN_CAMINO]: { label: "Iniciar entrega",   Icono: Truck },
  [ESTADO_DOMICILIO.ENTREGADO]: { label: "Marcar entregado",  Icono: CheckCircle2 },
  [ESTADO_DOMICILIO.CANCELADO]: { label: "Cancelar entrega",  Icono: XCircle, secundaria: true },
};

const accionesDe = (estadoId) =>
  transicionesDom(estadoId, true).map(tr => ({
    valor: tr.id,
    ...(ACCION_UI[tr.id] || { label: tr.label, Icono: Truck }),
  }));

/* Waze y Google Maps conservan su color de marca solo en el icono y el borde:
   así se reconocen de un vistazo sin romper el verde del resto. */
const NAVEGADORES = [
  { tipo: "google", label: "Google Maps", Icono: Map,        color: "#1a73e8", bg: "#eef4fe" },
  { tipo: "waze",   label: "Waze",        Icono: Navigation, color: "#0b93bd", bg: "#e9f7fb" },
];

const ESTADO_PAGO_INFO = {
  pendiente:             { label: "Pago pendiente",          color: "#757575", bg: "#f5f5f5" },
  pendiente_validacion:  { label: "Comprobante en revisión", color: "#e65100", bg: "#fff3e0" },
  pagado_completo:       { label: "Pago completo",           color: "#2e7d32", bg: "#e8f5e9" },
  anticipo_pagado:       { label: "Anticipo pagado",         color: "#f57f17", bg: "#fff8e1" },
  efectivo_recibido:     { label: "Efectivo recibido",       color: "#1565c0", bg: "#e3f2fd" },
  no_recibido:           { label: "Efectivo no recibido",    color: "#c62828", bg: "#ffebee" },
  comprobante_rechazado: { label: "Comprobante rechazado",   color: "#c62828", bg: "#ffebee" },
};

function EstadoPagoBadge({ estadoPago }) {
  if (!estadoPago || estadoPago === "pendiente") return null;
  const cfg = ESTADO_PAGO_INFO[estadoPago] || { label: estadoPago, color: "#757575", bg: "#f5f5f5" };
  return (
    <span
      className="du-badge-pago"
      style={{ "--p-color": cfg.color, "--p-bg": cfg.bg, "--p-border": `${cfg.color}33` }}
    >
      {cfg.label}
    </span>
  );
}

function EstadoBadge({ estadoId }) {
  const { cfg, vars } = varsEstado(estadoId);
  const Icono = ICONO_ESTADO[estadoId];
  return (
    <span
      className={`du-badge du-badge--lg${estadoId === ESTADO_DOMICILIO.EN_CAMINO ? " du-badge--vivo" : ""}`}
      style={vars}
    >
      {Icono && <Icono size={14} />} {cfg.label}
    </span>
  );
}

/* El recorrido del pedido, de un vistazo: dónde está y qué falta. */
function Recorrido({ estadoId }) {
  const actual = PASOS.findIndex(p => p.id === estadoId);
  return (
    <div className="pa-pasos">
      {PASOS.map((paso, i) => (
        <div
          key={paso.id}
          /* `--hecho` pinta también la barra hacia el siguiente paso, así que
             el paso actual no la lleva: ese tramo todavía no se ha recorrido. */
          className={`pa-paso${i < actual ? " pa-paso--hecho" : ""}${i === actual ? " pa-paso--activo" : ""}`}
        >
          <span className="pa-paso__punto"><paso.Icono size={17} /></span>
          <span className="pa-paso__label">{paso.label}</span>
        </div>
      ))}
    </div>
  );
}

function CobrarEfectivoModal({ pedido, entregarDespues, onClose, onConfirm }) {
  const [recibido, setRecibido] = useState(true);
  const [monto,    setMonto]    = useState(String(montoACobrar(pedido) || ""));
  const [motivo,   setMotivo]   = useState("");
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState(null);

  const handleConfirm = async () => {
    setError(null);
    if (recibido) {
      const m = parseFloat(monto);
      if (!monto || isNaN(m) || m <= 0) { setError("Ingresa el monto recibido"); return; }
    } else {
      if (motivo.trim().length < 10) { setError("El motivo debe tener al menos 10 caracteres"); return; }
    }
    setSaving(true);
    try {
      await onConfirm({ recibido, monto: recibido ? parseFloat(monto) : null, motivo: recibido ? null : motivo.trim() });
    } catch (e) {
      setError(e.message || "Error al registrar cobro");
      setSaving(false);
    }
  };

  const OPCIONES = [
    { val: true,  label: "Sí, recibí el dinero", Icono: CheckCircle2, color: "#2e7d32" },
    { val: false, label: "No recibí",            Icono: XCircle,      color: "#c62828" },
  ];

  return (
    <div className="modal-overlay">
      <div className="du-modal" onClick={e => e.stopPropagation()}>
        <div className="du-modal__head">
          <span className="du-modal__head-icon"><Wallet size={20} /></span>
          <div className="du-modal__head-txt">
            <p className="du-modal__eyebrow">{pedido.numero}</p>
            <h2 className="du-modal__titulo">Registrar cobro en efectivo</h2>
          </div>
          <button className="du-modal__cerrar" onClick={onClose} aria-label="Cerrar"><X size={17} /></button>
        </div>

        <div className="du-modal__body">
          <div className="du-dato du-dato--total">
            <div className="du-dato__label">{pedido.cliente?.nombre || "Cliente"}</div>
            <div className="du-dato__valor">{fmt(montoACobrar(pedido))}</div>
            {/* Pago mixto: en mano solo va una parte, el resto ya se transfirió. */}
            {esPagoMixto(pedido.metodo_pago) && (
              <div className="du-dato__sub">
                Parte en efectivo de un pedido de {fmt(pedido.total)}
              </div>
            )}
          </div>

          <div>
            <label className="du-campo-label">¿Recibiste el pago?</label>
            <div className="du-opciones">
              {OPCIONES.map(op => (
                <button
                  key={String(op.val)}
                  onClick={() => { setRecibido(op.val); setError(null); }}
                  className={`du-opcion${recibido === op.val ? " du-opcion--on" : ""}`}
                  style={{ "--op-color": op.color, "--op-bg": `${op.color}14`, "--op-sombra": `${op.color}2e` }}
                >
                  <op.Icono size={16} /> {op.label}
                </button>
              ))}
            </div>
          </div>

          {recibido ? (
            <div>
              <label className="du-campo-label">Monto recibido (debe coincidir con el total)</label>
              <input
                className="du-input"
                type="number"
                value={monto}
                onChange={e => setMonto(e.target.value)}
              />
            </div>
          ) : (
            <div>
              <label className="du-campo-label">Motivo (mínimo 10 caracteres)</label>
              <textarea
                className="du-textarea"
                rows={3}
                value={motivo}
                onChange={e => setMotivo(e.target.value)}
                placeholder="Ej: El cliente no tenía efectivo disponible…"
              />
              <div className={`du-contador${motivo.trim().length < 10 ? " du-contador--falta" : ""}`}>
                {motivo.trim().length}/10 mín.
              </div>
            </div>
          )}

          {error && <div className="du-error"><AlertCircle size={15} /> {error}</div>}
        </div>

        <div className="du-modal__foot">
          <button className="du-btn du-btn--fantasma" onClick={onClose} disabled={saving}>Cancelar</button>
          <button className="du-btn du-btn--primario" onClick={handleConfirm} disabled={saving}>
            <Banknote size={15} />
            {saving ? "Registrando…" : entregarDespues ? "Confirmar y entregar" : "Confirmar cobro"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={`du-toast du-toast--${toast.type === "error" ? "error" : "ok"}`}>
      <span className="du-toast__icon">{toast.type === "error" ? <X size={15} /> : <Check size={15} />}</span>
      {toast.message}
    </div>
  );
}

export default function PedidoActual() {
  const user = getUser();
  const [pedido, setPedido]     = useState(null);
  // La cola completa del repartidor. Antes solo se cargaba la primera entrega
  // y el resto era invisible: no había forma de saber cuántas quedaban ni de
  // mirar la siguiente sin terminar la actual.
  const [cola, setCola]         = useState([]);
  const [idActivo, setIdActivo] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]         = useState(false);
  const [toast, setToast]           = useState(null);
  const [confirmando,    setConfirmando]    = useState(null);
  /// La novedad que escribe el repartidor sobre esta entrega.
  ///
  /// Se manda junto con el cambio de estado —que es cuando pasa lo que hay que
  /// contar— y también se puede guardar sola, sin mover el pedido.
  const [novedad,        setNovedad]        = useState("");
  const [guardandoNota,  setGuardandoNota]  = useState(false);
  const [cobrandoOpen,   setCobrandoOpen]   = useState(false);

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const cargar = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    try {
      const doms = await getDomicilios({ porPagina: 100, idEmpleado: user.id });
      const activos = (doms.domicilios || []).filter(d => esDomicilioActivo(d.estadoId));
      activos.sort((a, b) => ESTADO_ORDEN.indexOf(a.estadoId) - ESTADO_ORDEN.indexOf(b.estadoId));

      setCola(activos);

      if (activos.length === 0) {
        setPedido(null);
        setIdActivo(null);
      } else {
        // Se conserva la entrega que el repartidor estaba mirando; si ya se
        // cerró, se pasa a la primera de la cola.
        const sigue = activos.some(d => String(d.id) === String(idActivo));
        const elegido = sigue ? idActivo : activos[0].id;
        setIdActivo(elegido);
        // cargar detalle completo con productos
        const detalle = await getDomicilio(elegido);
        setPedido(detalle);
      }
    } catch {
      showToast("Error al cargar el pedido", "error");
    } finally {
      setLoading(false);
    }
    // idActivo se lee para conservar la selección, pero no dispara la recarga:
    // cambiar de entrega la hace por su cuenta.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  /// Cambia a otra entrega de la cola sin recargar todo.
  const verEntrega = async (id) => {
    if (String(id) === String(idActivo)) return;
    setIdActivo(id);
    setLoading(true);
    try {
      setPedido(await getDomicilio(id));
    } catch {
      showToast("No se pudo abrir esa entrega", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, [cargar]);

  const handleAccion = async (accion) => {
    if (accion.secundaria) { setConfirmando(accion); return; }
    // Lo único que hay que resolver antes de entregar es la plata en mano: el
    // backend no acepta la entrega sin el cobro registrado. La evidencia (OTP,
    // foto, comprobante) ya no se pide.
    if (accion.valor === ESTADO_DOMICILIO.ENTREGADO && cobroEfectivoPendiente(pedido)) {
      setCobrandoOpen("entregar");
      return;
    }
    await ejecutarCambio(accion.valor, accion.label, novedad.trim() || null);
  };

  /* Viniendo del botón de Entregado, el cobro cierra la entrega en el mismo
     paso. Abierto desde el botón suelto, solo registra la plata: el pedido
     sigue en curso hasta que el repartidor lo cierre. */
  const handleCobrarEfectivo = async ({ recibido, monto, motivo }) => {
    const cerrarEntrega = cobrandoOpen === "entregar";
    try {
      await registrarPagoEfectivo(pedido.id, { recibido, monto, motivo });
    } catch (e) {
      showToast(e.message || "No se pudo registrar el cobro", "error");
      return;
    }
    setCobrandoOpen(false);
    // Sin cobro no hay entrega (3.7): el pedido pasó a "En ruta de retorno"
    // del lado del backend, así que no tiene sentido seguir e intentar
    // marcarlo Entregado — eso ahora lo rechaza el propio backend.
    if (cerrarEntrega && recibido) {
      await ejecutarCambio(ESTADO_DOMICILIO.ENTREGADO, "Entregado",
                           novedad.trim() || null);
      return;
    }
    showToast(recibido ? "Cobro registrado" : "Entrega fallida: el pedido vuelve a la tienda");
    await cargar();
  };

  /// Guarda la novedad sin cambiar de estado.
  ///
  /// A veces hay algo que contar antes de cerrar la entrega —el portón no
  /// abre, el cliente pidió esperar— y obligar a cambiar el estado para poder
  /// anotarlo es pedirle al repartidor que mienta sobre dónde va.
  const guardarNovedad = async () => {
    const texto = novedad.trim();
    if (!texto || !pedido) return;
    setGuardandoNota(true);
    try {
      await cambiarEstadoDomicilio(pedido.id, pedido.estadoId, texto);
      showToast("Novedad guardada");
      await cargar();
    } catch (e) {
      showToast(e.message || "No se pudo guardar la novedad", "error");
    } finally {
      setGuardandoNota(false);
    }
  };

  const ejecutarCambio = async (valor, label, observacion = null) => {
    setSaving(true);
    setConfirmando(null);
    try {
      await cambiarEstadoDomicilio(pedido.id, valor, observacion);
      showToast(`Estado actualizado: ${label}`);
      await cargar();
    } catch (e) {
      showToast(e.message || "Error al cambiar el estado", "error");
    } finally {
      setSaving(false);
    }
  };

  const abrirMaps = (tipo) => {
    if (!pedido) return;
    const dir = encodeURIComponent(
      [pedido.direccion_entrega, pedido.municipio_entrega].filter(Boolean).join(", ")
    );
    const url = tipo === "waze"
      ? `https://waze.com/ul?q=${dir}&navigate=yes`
      : `https://www.google.com/maps/dir/?api=1&destination=${dir}`;
    window.open(url, "_blank", "noopener");
  };

  const acciones  = pedido ? accionesDe(pedido.estadoId) : [];
  const faltaPlata = pedido ? cobroEfectivoPendiente(pedido) : false;

  const STATS = pedido ? [
    { Icono: Route,      valor: cola.length,                                        label: "En cola" },
    { Icono: Clock,      valor: labelEstadoDom(pedido.estadoId), money: true,       label: "Estado" },
    { Icono: ShoppingBag, valor: fmt(pedido.total || 0),          money: true,      label: "Total" },
    {
      Icono: Wallet, oro: true, money: true, label: "Por cobrar",
      valor: faltaPlata ? fmt(montoACobrar(pedido)) : "Al día",
    },
  ] : [];

  const subtitulo = loading
    ? "Cargando tu ruta…"
    : !pedido
      ? "No tienes ninguna entrega en curso en este momento."
      : cola.length > 1
        ? `Entrega ${cola.findIndex(d => String(d.id) === String(idActivo)) + 1} de ${cola.length} en tu ruta de hoy.`
        : "Esta es la única entrega que tienes asignada ahora mismo.";

  return (
    <div className="dom-ui pedido-actual">
      <header className="du-hero">
        <div className="du-hero__top">
          <div>
            <span className="du-hero__eyebrow"><Bike size={14} /> Ruta en curso</span>
            <h1 className="du-hero__title">Pedido Actual</h1>
            <p className="du-hero__sub">{subtitulo}</p>
          </div>
          <button
            className={`du-hero__refresh${loading ? " du-hero__refresh--girando" : ""}`}
            onClick={cargar}
            disabled={loading}
          >
            <RefreshCw size={15} /> Actualizar
          </button>
        </div>

        {STATS.length > 0 && (
          <div className="du-stats">
            {STATS.map(s => (
              <div key={s.label} className={`du-stat${s.oro ? " du-stat--oro" : ""}`}>
                <span className="du-stat__icon"><s.Icono size={19} /></span>
                <div>
                  <div className={`du-stat__valor${s.money ? " du-stat__valor--money" : ""}`}>{s.valor}</div>
                  <div className="du-stat__label">{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </header>

      <div className="du-inner du-inner--angosto">
        {loading ? (
          <div className="pa-col">
            {[1, 2].map(i => (
              <div key={i} className="du-skel-card">
                {[60, 90, 45, 75].map((w, j) => (
                  <div key={j} className="du-skel" style={{ width: `${w}%` }} />
                ))}
              </div>
            ))}
          </div>
        ) : !pedido ? (
          <div className="du-vacio">
            <span className="du-vacio__icon"><Truck size={38} strokeWidth={1.4} /></span>
            <p className="du-vacio__titulo">Sin pedido activo</p>
            <p className="du-vacio__texto">
              No tienes ninguna entrega en curso en este momento. Cuando te asignen un domicilio aparecerá aquí.
            </p>
          </div>
        ) : (
          <div className="pa-col">

            {/* ── Cola de entregas ──
                Con más de una asignada hay que poder ver cuáles son y saltar
                entre ellas: antes solo existía la primera y las demás eran
                invisibles hasta cerrarla. */}
            {cola.length > 1 && (
              <div className="pa-cola">
                {cola.map((d, i) => {
                  const activo = String(d.id) === String(idActivo);
                  const faltaCobro = cobroEfectivoPendiente(d);
                  return (
                    <button
                      key={d.id}
                      onClick={() => verEntrega(d.id)}
                      aria-current={activo ? "true" : undefined}
                      className={`pa-cola__chip${activo ? " pa-cola__chip--on" : ""}`}
                    >
                      <span className="pa-cola__n">{i + 1}</span>
                      <span className="pa-cola__num">{d.numero || `#${d.id}`}</span>
                      <span className={`pa-cola__estado${faltaCobro ? " pa-cola__cobro" : ""}`}>
                        {labelEstadoDom(d.estadoId)}{faltaCobro ? " · cobrar" : ""}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* ── Recorrido y cabecera del pedido ── */}
            <section className="du-panel">
              <div className="du-panel__head">
                <h2 className="du-panel__titulo">{pedido.numero}</h2>
                <span style={{ marginLeft: "auto" }}><EstadoBadge estadoId={pedido.estadoId} /></span>
              </div>
              <div className="du-panel__body">
                <Recorrido estadoId={pedido.estadoId} />
                <div className="du-meta-fila" style={{ marginTop: 14, justifyContent: "center" }}>
                  <Clock size={13} />
                  {new Date(pedido.fecha_pedido).toLocaleString("es-CO", {
                    day: "2-digit", month: "2-digit", year: "numeric",
                    hour: "2-digit", minute: "2-digit",
                  })}
                </div>
              </div>
            </section>

            {/* ── Cliente y dirección ── */}
            <section className="du-panel">
              <div className="du-panel__head"><h2 className="du-panel__titulo">Destino</h2></div>
              <div className="du-panel__body">
                <div className="pa-destino">
                  <span className="pa-destino__pin"><MapPin size={21} /></span>
                  <div className="pa-destino__txt">
                    <div className="pa-destino__cliente">{pedido.cliente?.nombre || "—"}</div>
                    <div className="pa-destino__dir">
                      {[pedido.direccion_entrega, pedido.municipio_entrega].filter(Boolean).join(", ") || "Sin dirección"}
                    </div>
                  </div>
                </div>

                <div className="pa-navs">
                  {NAVEGADORES.map(nav => (
                    <button
                      key={nav.tipo}
                      className="pa-nav"
                      onClick={() => abrirMaps(nav.tipo)}
                      style={{ "--nav-color": nav.color, "--nav-bg": nav.bg }}
                    >
                      <nav.Icono size={15} /> {nav.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            {/* ── Productos ── */}
            {pedido.productos?.length > 0 && (
              <section className="du-panel">
                <div className="du-panel__head"><h2 className="du-panel__titulo">Productos</h2></div>
                <div className="du-panel__body">
                  <div className="pa-items">
                    {pedido.productos.map((p, i) => (
                      <div key={i} className="pa-item">
                        <span className="pa-item__qty">×{p.Cantidad}</span>
                        <div className="pa-item__txt">
                          <div className="pa-item__nombre">{p.nombre_producto}</div>
                          <div className="pa-item__unit">{fmt(p.precio_unitario)} c/u</div>
                        </div>
                        <span className="pa-item__sub">{fmt(p.subtotal)}</span>
                      </div>
                    ))}
                  </div>

                  <div className="pa-total">
                    <span className="pa-total__label">Total</span>
                    <span className="pa-total__valor">{fmt(pedido.total)}</span>
                  </div>

                  {pedido.metodo_pago && (
                    <div className="pa-pago">
                      <span className="pa-pago__metodo"><CreditCard size={13} /> Pago: {pedido.metodo_pago}</span>
                      <EstadoPagoBadge estadoPago={pedido.estado_pago} />
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* ── Cobro en efectivo ──
                El repartidor puede registrar la plata apenas la recibe, sin
                tener que cerrar la entrega en el mismo momento. */}
            {faltaPlata && (
              <section className="du-panel du-panel--oro">
                <div className="du-panel__head"><h2 className="du-panel__titulo">Cobro en efectivo</h2></div>
                <div className="du-panel__body">
                  <p style={{ margin: "0 0 14px", fontSize: 13.5, lineHeight: 1.5, color: "#7a5d00" }}>
                    Este pedido se paga en mano. Registra <strong>{fmt(montoACobrar(pedido))}</strong> apenas
                    lo recibas, aunque todavía no cierres la entrega.
                  </p>
                  <button
                    className="du-btn du-btn--oro du-btn--grande"
                    onClick={() => setCobrandoOpen("solo-cobro")}
                    disabled={saving}
                  >
                    <Banknote size={17} /> Registrar cobro
                  </button>
                </div>
              </section>
            )}

            {/* ── Acciones de estado ── */}
            {acciones.length > 0 && (
              <section className="du-panel">
                <div className="du-panel__head"><h2 className="du-panel__titulo">Actualizar estado</h2></div>
                <div className="du-panel__body">
                  <div className="pa-acciones">
                    {acciones.map(ac => (
                      <button
                        key={ac.valor}
                        className={`pa-accion pa-accion--${ac.secundaria ? "secundaria" : "principal"}`}
                        onClick={() => handleAccion(ac)}
                        disabled={saving}
                      >
                        <ac.Icono size={18} />
                        {saving ? "Actualizando…" : ac.label}
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            )}

            {/* ── Observaciones ── */}
            {pedido.obs_domicilio && (
              <div className="du-dato du-dato--obs">
                <div className="du-dato__label">Observaciones</div>
                <div className="du-dato__valor">{pedido.obs_domicilio}</div>
              </div>
            )}

            {/* Dónde contar lo que pasó. Antes esto solo se mostraba: para
                escribirlo había que salir a "Mis entregas", que es otra
                pantalla, así que casi nunca se escribía. */}
            {esDomicilioActivo(pedido.estadoId) && (
              <div className="du-dato du-dato--obs">
                <div className="du-dato__label">
                  {pedido.obs_domicilio ? "Agregar novedad" : "Novedad de la entrega"}
                </div>
                <textarea
                  className="du-textarea"
                  rows={2}
                  value={novedad}
                  onChange={e => setNovedad(e.target.value)}
                  placeholder="No había nadie, se dejó con el portero…"
                />
                <button
                  className="du-btn du-btn--fantasma du-btn--bloque"
                  onClick={guardarNovedad}
                  disabled={guardandoNota || !novedad.trim()}
                  style={{ marginTop: 8 }}
                >
                  {guardandoNota ? "Guardando…" : "Guardar novedad"}
                </button>
                <p className="du-nota" style={{ marginTop: 6 }}>
                  Se guarda también al cambiar el estado del pedido.
                </p>
              </div>
            )}

          </div>
        )}
      </div>

      {/* ── Modal cobro efectivo ── */}
      {cobrandoOpen && pedido && (
        <CobrarEfectivoModal
          pedido={pedido}
          entregarDespues={cobrandoOpen === "entregar"}
          onClose={() => setCobrandoOpen(false)}
          onConfirm={handleCobrarEfectivo}
        />
      )}

      {/* ── Modal confirmación cancelar ── */}
      {confirmando && (
        <div className="modal-overlay">
          <div className="du-modal du-modal--estrecho" onClick={e => e.stopPropagation()}>
            <div className="du-modal__head du-modal__head--peligro">
              <span className="du-modal__head-icon"><AlertCircle size={20} /></span>
              <div className="du-modal__head-txt">
                <p className="du-modal__eyebrow">{pedido?.numero}</p>
                <h2 className="du-modal__titulo">¿Cancelar entrega?</h2>
              </div>
            </div>
            <div className="du-modal__body">
              <p className="du-nota" style={{ padding: "6px 2px" }}>
                Esta acción cambiará el estado del pedido a <strong>Cancelado</strong>.
              </p>
            </div>
            <div className="du-modal__foot">
              <button className="du-btn du-btn--fantasma" onClick={() => setConfirmando(null)}>Volver</button>
              <button
                className="du-btn du-btn--peligro-solido"
                onClick={() => ejecutarCambio(confirmando.valor, confirmando.label)}
              >
                <XCircle size={15} /> Sí, cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      <Toast toast={toast} />
    </div>
  );
}
