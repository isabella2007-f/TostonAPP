import { useState, useEffect } from "react";
import { getTodosLosDomicilios, cambiarEstadoDomicilio, registrarPagoEfectivo } from "../../../services/domiciliosService.js";
import { getUser } from "../../../services/authService.js";
import { fmtFechaHora as fmtFecha } from "../../../utils/dateUtils.js";
import { ESTADO_DOMICILIO, ESTADO_DOM_CONFIG, cobroEfectivoPendiente, esDomicilioActivo, esPagoMixto, montoACobrar, transicionesDom } from "./estadosDomicilio";
import "./DomiciliarioUI.css";
import "./MisEntregas.css";
import { formatCOP } from "../../../utils/formato";
import { enlaceWhatsApp, saludoDomiciliario } from "../../../utils/whatsapp";
import {
  Search, RefreshCw, Truck, Package, CheckCircle2, XCircle, Clock,
  MapPin, MessageSquare, X, Check, Phone, Banknote, Bike, Wallet, MessageCircle,
  AlertCircle, ChevronRight,
} from "lucide-react";

const fmt = formatCOP;

// Los colores salen de la fuente única de estados; aquí solo el icono.
const ICONO_ESTADO = {
  3:  Clock,
  10: Package,
  9:  Truck,
  8:  CheckCircle2,
  5:  XCircle,
};

const IconoEstado = ({ estadoId, size = 12 }) => {
  const Icono = ICONO_ESTADO[estadoId];
  return Icono ? <Icono size={size} /> : null;
};

/* Las variables de color viajan al CSS: la hoja no repite ningún hex de
   estado, así sigue mandando estadosDomicilio.js como fuente única. */
const varsEstado = (estadoId) => {
  const cfg = ESTADO_DOM_CONFIG[estadoId] ||
    { dot: "#757575", bg: "#f5f5f5", border: "#e0e0e0", label: "—" };
  return { cfg, vars: { "--e-dot": cfg.dot, "--e-bg": cfg.bg, "--e-border": cfg.border } };
};

const ESTADO_PAGO_INFO = {
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

// Flujo real del domicilio: Asignado → En camino → Entregado (o Cancelado).
// Antes había un paso "Llegué al local" que enviaba el estado 13, que es "En
// producción" del PEDIDO, no un estado de domicilio: el backend lo rechaza.
const ICONO_TRANSICION = { 9: Truck, 8: CheckCircle2, 5: XCircle };
const LABEL_TRANSICION = { 9: "Iniciar entrega", 8: "Entregado", 5: "Cancelado" };

const proximosEstados = (estadoId) =>
  transicionesDom(estadoId, true).map(t => ({
    valor: t.id,
    label: LABEL_TRANSICION[t.id] || t.label,
    Icono: ICONO_TRANSICION[t.id] || Truck,
  }));

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={`du-toast du-toast--${toast.type === "error" ? "error" : "ok"}`}>
      <span className="du-toast__icon">{toast.type === "error" ? <X size={15} /> : <Check size={15} />}</span>
      {toast.message}
    </div>
  );
}

function EstadoBadge({ estadoId }) {
  const { cfg, vars } = varsEstado(estadoId);
  return (
    <span
      className={`du-badge${estadoId === ESTADO_DOMICILIO.EN_CAMINO ? " du-badge--vivo" : ""}`}
      style={vars}
    >
      <IconoEstado estadoId={estadoId} /> {cfg.label}
    </span>
  );
}

/* Cobro en efectivo. El repartidor es quien recibe el dinero, así que registra
   aquí si lo cobró. El backend exige el monto exacto del pedido cuando se
   cobró, o un motivo de 10+ caracteres cuando no.

   Se abre en dos momentos: al marcar Entregado un pedido en efectivo (y ahí
   cierra la entrega en el mismo paso) o suelto desde la tarjeta, para cuando
   el repartidor cobra antes de dar por terminada la entrega. */
function CobroEfectivoModal({ domicilio, saving, entregarDespues, onClose, onConfirm }) {
  const [recibido, setRecibido] = useState(null);
  const [motivo,   setMotivo]   = useState("");
  const [error,    setError]    = useState(null);

  const confirmar = () => {
    if (recibido === null) return setError("Indica si recibiste el efectivo.");
    if (!recibido && motivo.trim().length < 10) {
      return setError("Explica por qué no se cobró (mínimo 10 caracteres).");
    }
    setError(null);
    onConfirm({ recibido, motivo: motivo.trim() });
  };

  const opcion = (valor, Icono, titulo, color) => (
    <button
      type="button"
      onClick={() => { setRecibido(valor); setError(null); }}
      className={`du-opcion${recibido === valor ? " du-opcion--on" : ""}`}
      style={{ "--op-color": color, "--op-bg": `${color}14`, "--op-sombra": `${color}2e` }}
    >
      <Icono size={19} /> {titulo}
    </button>
  );

  return (
    <div className="modal-overlay">
      <div className="du-modal" onClick={e => e.stopPropagation()}>
        <div className="du-modal__head">
          <span className="du-modal__head-icon"><Wallet size={20} /></span>
          <div className="du-modal__head-txt">
            <p className="du-modal__eyebrow">{domicilio.numero}</p>
            <h2 className="du-modal__titulo">Cobro en efectivo</h2>
          </div>
          <button className="du-modal__cerrar" onClick={onClose} aria-label="Cerrar"><X size={17} /></button>
        </div>

        <div className="du-modal__body">
          <div className="du-dato du-dato--total">
            <div className="du-dato__label">Total a cobrar</div>
            <div className="du-dato__valor">{fmt(montoACobrar(domicilio))}</div>
            {/* En un pedido mixto solo se cobra en mano una parte: el resto ya
                entró por transferencia al hacer el pedido. */}
            {esPagoMixto(domicilio.metodo_pago) && (
              <div className="du-dato__sub">
                Parte en efectivo de un pedido de {fmt(domicilio.total)} — el resto ya se transfirió.
              </div>
            )}
          </div>

          <div>
            <label className="du-campo-label">¿Recibiste el pago completo del cliente?</label>
            <div className="du-opciones">
              {opcion(true,  CheckCircle2, "Sí, recibido", "#2e7d32")}
              {opcion(false, XCircle,      "No lo recibí", "#c62828")}
            </div>
          </div>

          {recibido === false && (
            <div>
              <textarea
                className="du-textarea"
                rows={3}
                value={motivo}
                onChange={e => { setMotivo(e.target.value); setError(null); }}
                placeholder="Ej: el cliente no tenía el efectivo completo"
              />
              <div className={`du-contador${motivo.trim().length < 10 ? " du-contador--falta" : ""}`}>
                {motivo.trim().length}/10 caracteres mínimos
              </div>
            </div>
          )}

          {error && (
            <div className="du-error"><AlertCircle size={15} /> {error}</div>
          )}
        </div>

        <div className="du-modal__foot">
          <button className="du-btn du-btn--fantasma" onClick={onClose} disabled={saving}>
            Cancelar
          </button>
          <button className="du-btn du-btn--primario" onClick={confirmar} disabled={saving}>
            <Banknote size={15} />
            {saving ? "Registrando…" : entregarDespues ? "Registrar y entregar" : "Registrar cobro"}
          </button>
        </div>
      </div>
    </div>
  );
}

function CambiarEstadoModal({ domicilio, onClose, onSave }) {
  const posibles = proximosEstados(domicilio.estadoId);
  const [nuevoEstado, setNuevoEstado] = useState(posibles[0]?.valor || "");
  const [obs, setObs] = useState(domicilio.obs_domicilio || "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!nuevoEstado) return;
    setSaving(true);
    try {
      await onSave(domicilio.id, nuevoEstado, obs.trim() || null);
      onClose();
    } catch {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="du-modal" onClick={e => e.stopPropagation()}>
        <div className="du-modal__head">
          <span className="du-modal__head-icon"><Bike size={20} /></span>
          <div className="du-modal__head-txt">
            <p className="du-modal__eyebrow">{domicilio.numero}</p>
            <h2 className="du-modal__titulo">Actualizar entrega</h2>
          </div>
          <button className="du-modal__cerrar" onClick={onClose} aria-label="Cerrar"><X size={17} /></button>
        </div>

        <div className="du-modal__body">
          <div className="du-dato">
            <div className="du-dato__label">Entrega</div>
            <div className="du-dato__valor du-dato__valor--fuerte">{domicilio.cliente?.nombre || "—"}</div>
            <div className="du-dato__sub">{domicilio.direccion_entrega || "Sin dirección"}</div>
          </div>

          {posibles.length === 0 ? (
            <p className="du-nota">
              No hay cambios de estado disponibles para este domicilio.
            </p>
          ) : (
            <>
              <div>
                <label className="du-campo-label">Nuevo estado</label>
                <div className="du-opciones">
                  {posibles.map(op => {
                    const { cfg } = varsEstado(op.valor);
                    return (
                      <button
                        key={op.valor}
                        onClick={() => setNuevoEstado(op.valor)}
                        className={`du-opcion${nuevoEstado === op.valor ? " du-opcion--on" : ""}`}
                        style={{ "--op-color": cfg.dot, "--op-bg": cfg.bg, "--op-sombra": `${cfg.dot}2e` }}
                      >
                        <op.Icono size={16} /> {op.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="du-campo-label">Observaciones (opcional)</label>
                <textarea
                  className="du-textarea"
                  rows={3}
                  value={obs}
                  onChange={e => setObs(e.target.value)}
                  placeholder="Comentario o novedad del domicilio…"
                />
              </div>
            </>
          )}
        </div>

        {posibles.length > 0 && (
          <div className="du-modal__foot">
            <button className="du-btn du-btn--fantasma" onClick={onClose}>Cancelar</button>
            <button className="du-btn du-btn--primario" onClick={handleSave} disabled={saving || !nuevoEstado}>
              <Check size={15} /> {saving ? "Guardando…" : "Confirmar"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function DetallesModal({ domicilio, onClose, onCambiarEstado, onCobrar }) {
  /* El enlace lleva el indicativo 57. Sin él WhatsApp abre igual pero
     contesta que el número no existe, así que parecía que el cliente había
     dado mal el teléfono. Si el número no se entiende, `enlaceWhatsApp`
     devuelve null y el botón no se dibuja: rellenarlo a ojo abre el chat de
     un desconocido. */
  const waCliente = enlaceWhatsApp(
    domicilio.cliente?.telefono,
    saludoDomiciliario({
      nombre: domicilio.cliente?.nombre,
      numeroPedido: domicilio.numero,
      enCamino: domicilio.estadoId === ESTADO_DOMICILIO.EN_CAMINO,
    }),
  );

  return (
    <div className="modal-overlay">
      <div className="du-modal du-modal--ancho" onClick={e => e.stopPropagation()}>
        <div className="du-modal__head">
          <span className="du-modal__head-icon"><Package size={20} /></span>
          <div className="du-modal__head-txt">
            <p className="du-modal__eyebrow">Domicilio</p>
            <h2 className="du-modal__titulo">{domicilio.numero}</h2>
          </div>
          <button className="du-modal__cerrar" onClick={onClose} aria-label="Cerrar"><X size={17} /></button>
        </div>

        <div className="du-modal__body">
          <div className="du-meta-fila">
            <EstadoBadge estadoId={domicilio.estadoId} />
            <EstadoPagoBadge estadoPago={domicilio.estado_pago} />
            <span>{fmtFecha(domicilio.fecha_pedido)}</span>
          </div>

          <div className="du-dato">
            <div className="du-dato__label">Cliente</div>
            <div className="du-dato__valor du-dato__valor--fuerte">{domicilio.cliente?.nombre || "—"}</div>
            {domicilio.cliente?.telefono && (
              <div className="du-contacto">
                <span className="du-contacto__tel">
                  <Phone size={13} /> {domicilio.cliente.telefono}
                </span>
                {waCliente && (
                  <a className="du-wa" href={waCliente} target="_blank" rel="noopener noreferrer">
                    <MessageCircle size={13} /> Escribir por WhatsApp
                  </a>
                )}
              </div>
            )}
          </div>

          <div className="du-dato">
            <div className="du-dato__label">Dirección</div>
            <div className="du-dato__valor">{domicilio.direccion_entrega || "—"}</div>
          </div>

          <div className="du-dato du-dato--total">
            <div className="du-dato__label">Total</div>
            <div className="du-dato__valor">{fmt(domicilio.total || 0)}</div>
          </div>

          {(domicilio.productos || []).length > 0 && (
            <div className="du-dato">
              <div className="du-dato__label">Productos del pedido</div>
              <div className="du-dato__valor" style={{ display: "grid", gap: 8 }}>
                {(domicilio.productos || []).map((p, i) => (
                  <div key={p.ID_Producto ?? i} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "8px 10px", borderRadius: 10,
                    border: "1px solid #ececec", background: "#fafafa"
                  }}>
                    <div style={{
                      width: 34, height: 34, borderRadius: 8, overflow: "hidden",
                      background: "#e8f5e9", display: "flex", alignItems: "center",
                      justifyContent: "center", flexShrink: 0
                    }}>
                      {p.imagen ? (
                        <img src={p.imagen} alt={p.nombre_producto || "Producto"} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                      ) : (
                        <Package size={16} style={{ color: "#2e7d32" }} />
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 700, color: "#1a1a1a" }}>
                        {p.nombre_producto || "Producto"}
                      </div>
                      <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2 }}>
                        {p.Cantidad} × {fmt(p.precio_unitario || 0)}
                      </div>
                    </div>
                    <div style={{ fontSize: 12.5, fontWeight: 800, color: "#2e7d32" }}>
                      {fmt(p.subtotal || 0)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(domicilio.metodo_pago || domicilio.estado_pago || domicilio.comprobante_pago) && (
            <div className="du-dato">
              <div className="du-dato__label">Pago del pedido</div>
              <div className="du-dato__valor" style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-start" }}>
                {domicilio.metodo_pago && <span>{domicilio.metodo_pago}</span>}
                {domicilio.estado_pago && <EstadoPagoBadge estadoPago={domicilio.estado_pago} />}
                {domicilio.comprobante_pago && (
                  <a
                    href={domicilio.comprobante_pago}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 12, fontWeight: 700, color: "#1b5e20", textDecoration: "underline" }}
                  >
                    Ver comprobante
                  </a>
                )}
              </div>
            </div>
          )}

          {domicilio.obs_domicilio && (
            <div className="du-dato du-dato--obs">
              <div className="du-dato__label">Observaciones</div>
              <div className="du-dato__valor">{domicilio.obs_domicilio}</div>
            </div>
          )}

          {cobroEfectivoPendiente(domicilio) && esDomicilioActivo(domicilio.estadoId) && (
            <button
              className="du-btn du-btn--oro du-btn--bloque"
              onClick={() => { onClose(); onCobrar(domicilio); }}
            >
              <Banknote size={16} /> Registrar cobro en efectivo
            </button>
          )}
          {proximosEstados(domicilio.estadoId).length > 0 && (
            <button
              className="du-btn du-btn--primario du-btn--bloque"
              onClick={() => { onClose(); onCambiarEstado(domicilio); }}
            >
              <Truck size={16} /> Actualizar estado de entrega
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function GestionDomiciliosRepartidor() {
  const user = getUser();
  const idEmpleado = user?.id;

  const [domicilios, setDomicilios] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [filtro,  setFiltro]        = useState("activos");
  const [search,  setSearch]        = useState("");
  const [modal,   setModal]         = useState(null);
  const [toast,   setToast]         = useState(null);
  // Entrega en efectivo pendiente de registrar el cobro.
  const [cobrando, setCobrando]     = useState(null);

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const cargar = async () => {
    if (!idEmpleado) return;
    setLoading(true);
    try {
      // Todas las páginas: los contadores de los filtros ("Activos", "Todos")
      // se sacan de esta lista, y con una sola página de 100 empezaban a
      // mentir en cuanto el repartidor acumulaba entregas.
      setDomicilios(await getTodosLosDomicilios({ idEmpleado }));
    } catch (e) {
      showToast(e.message || "Error al cargar entregas", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const esActivo = (d) => esDomicilioActivo(d.estadoId);

  const q = search.trim().toLowerCase();
  const filtrados = domicilios.filter(d => {
    const matchFiltro = filtro === "activos" ? esActivo(d)
      : filtro === "entregados" ? d.estadoId === ESTADO_DOMICILIO.ENTREGADO
      : true;
    const matchSearch = !q
      || String(d.numero || "").toLowerCase().includes(q)
      || (d.cliente?.nombre || "").toLowerCase().includes(q)
      || (d.direccion_entrega || "").toLowerCase().includes(q);
    return matchFiltro && matchSearch;
  });

  const handleCambiarEstado = async (id, nuevoEstado, observaciones) => {
    // Al entregar un pedido en efectivo hay que registrar el cobro primero: el
    // repartidor es quien recibe el dinero y el backend no acepta la entrega
    // sin ese registro. Se pide aquí en vez de dejar que falle la llamada.
    if (nuevoEstado === ESTADO_DOMICILIO.ENTREGADO) {
      const dom = domicilios.find(d => d.id === id);
      if (cobroEfectivoPendiente(dom)) {
        setCobrando({ dom, observaciones, entregarDespues: true });
        return;
      }
    }
    try {
      await cambiarEstadoDomicilio(id, nuevoEstado, observaciones);
      showToast("Estado actualizado");
      await cargar();
    } catch (e) {
      showToast(e.message || "Error al cambiar el estado", "error");
    }
  };

  /* Registrar el cobro. Viniendo de marcar Entregado, cierra la entrega en el
     mismo paso; abierto desde el botón de la tarjeta, solo registra la plata y
     el domicilio sigue su curso. */
  const handleCobrar = async ({ recibido, motivo }) => {
    const { dom, observaciones, entregarDespues } = cobrando;
    try {
      await registrarPagoEfectivo(dom.id, {
        recibido,
        monto: recibido ? montoACobrar(dom) : null,
        motivo: recibido ? null : motivo,
      });
      if (entregarDespues) {
        await cambiarEstadoDomicilio(dom.id, ESTADO_DOMICILIO.ENTREGADO, observaciones);
      }
      setCobrando(null);
      showToast(
        !recibido               ? "Se registró que no se pudo cobrar"
        : entregarDespues       ? `Cobro de ${fmt(montoACobrar(dom))} registrado y entrega cerrada`
        :                         `Cobro de ${fmt(montoACobrar(dom))} registrado`
      );
      await cargar();
    } catch (e) {
      showToast(e.message || "No se pudo registrar el cobro", "error");
    }
  };

  const activos     = domicilios.filter(esActivo);
  const enCamino    = domicilios.filter(d => d.estadoId === ESTADO_DOMICILIO.EN_CAMINO);
  const entregados  = domicilios.filter(d => d.estadoId === ESTADO_DOMICILIO.ENTREGADO);
  // Plata que el repartidor todavía lleva pendiente de cobrar en la calle.
  const porCobrar   = activos
    .filter(cobroEfectivoPendiente)
    .reduce((suma, d) => suma + Number(montoACobrar(d) || 0), 0);

  const FILTROS = [
    { val: "activos",    label: "Activos",    count: activos.length },
    { val: "entregados", label: "Entregados", count: entregados.length },
    { val: "todos",      label: "Todos",      count: domicilios.length },
  ];

  const STATS = [
    { Icono: Package,      valor: activos.length,    label: "Activos" },
    { Icono: Truck,        valor: enCamino.length,   label: "En camino" },
    { Icono: CheckCircle2, valor: entregados.length, label: "Entregados" },
    { Icono: Wallet,       valor: fmt(porCobrar),    label: "Por cobrar", money: true, oro: true },
  ];

  const subtitulo = loading
    ? "Cargando tu ruta…"
    : activos.length === 0
      ? "No tienes entregas pendientes ahora mismo. Buen trabajo."
      : `Tienes ${activos.length} ${activos.length === 1 ? "entrega pendiente" : "entregas pendientes"} en tu ruta.`;

  return (
    <div className="dom-ui mis-entregas">
      <header className="du-hero">
        <div className="du-hero__top">
          <div>
            <span className="du-hero__eyebrow"><Bike size={14} /> Panel del domiciliario</span>
            <h1 className="du-hero__title">Mis Entregas</h1>
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
      </header>

      <div className="du-inner">
        <div className="me-toolbar">
          <div className="du-search">
            <span className="du-search__icon"><Search size={16} /></span>
            <input
              className="du-search__input"
              type="text"
              placeholder="Buscar por número, cliente o dirección…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button className="du-search__clear" onClick={() => setSearch("")} aria-label="Limpiar búsqueda">
                <X size={13} />
              </button>
            )}
          </div>

          <div className="du-filtros">
            {FILTROS.map(f => (
              <button
                key={f.val}
                onClick={() => setFiltro(f.val)}
                className={`du-filtro${filtro === f.val ? " du-filtro--on" : ""}`}
              >
                {f.label}
                <span className="du-filtro__count">{f.count}</span>
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="me-grid">
            {[1, 2, 3].map(i => (
              <div key={i} className="du-skel-card">
                {[70, 50, 90, 40].map((w, j) => (
                  <div key={j} className="du-skel" style={{ width: `${w}%` }} />
                ))}
              </div>
            ))}
          </div>
        ) : filtrados.length === 0 ? (
          <div className="du-vacio">
            <span className="du-vacio__icon"><Truck size={38} strokeWidth={1.4} /></span>
            <p className="du-vacio__titulo">
              {q ? "Sin resultados para esa búsqueda"
                 : filtro === "activos" ? "No tienes entregas pendientes"
                 : "Sin resultados"}
            </p>
            <p className="du-vacio__texto">
              {q ? "Prueba con otro número de pedido, cliente o dirección."
                 : filtro === "activos" ? "Cuando te asignen un domicilio aparecerá aquí."
                 : "No hay domicilios que coincidan con este filtro."}
            </p>
          </div>
        ) : (
          <div className="me-grid">
            {filtrados.map(dom => {
              const { vars } = varsEstado(dom.estadoId);
              const puedeCambiar = proximosEstados(dom.estadoId).length > 0;
              // Avisar que va llegando es lo que más se hace en una entrega,
              // y estaba escondido dentro del detalle. Solo mientras la
              // entrega siga viva: escribirle por una de hace tres días no
              // tiene sentido.
              const wa = esDomicilioActivo(dom.estadoId)
                ? enlaceWhatsApp(
                    dom.cliente?.telefono,
                    saludoDomiciliario({
                      nombre: dom.cliente?.nombre,
                      numeroPedido: dom.numero,
                      enCamino: dom.estadoId === ESTADO_DOMICILIO.EN_CAMINO,
                    }),
                  )
                : null;
              return (
                <div
                  key={dom.id}
                  className="me-card"
                  style={vars}
                  role="button"
                  tabIndex={0}
                  onClick={() => setModal({ type: "detalles", dom })}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setModal({ type: "detalles", dom });
                    }
                  }}
                >
                  <div className="me-card__head">
                    <span className="me-card__avatar"><IconoEstado estadoId={dom.estadoId} size={20} /></span>
                    <div className="me-card__ident">
                      <div className="me-card__num">{dom.numero}</div>
                      <div className="me-card__cliente">{dom.cliente?.nombre || "Cliente"}</div>
                    </div>
                    <EstadoBadge estadoId={dom.estadoId} />
                  </div>

                  <div className="me-card__body">
                    <div className="me-card__dir">
                      <MapPin size={15} />
                      <span>{dom.direccion_entrega || "Sin dirección"}</span>
                    </div>

                    {dom.obs_domicilio && (
                      <div className="me-card__obs">
                        <MessageSquare size={13} /> {dom.obs_domicilio}
                      </div>
                    )}
                  </div>

                  <div className="me-card__foot">
                    <div>
                      <div className="me-card__monto-label">Total</div>
                      <div className="me-card__monto">{fmt(dom.total || 0)}</div>
                      <EstadoPagoBadge estadoPago={dom.estado_pago} />
                    </div>
                    <div className="me-card__acciones">
                      {wa && (
                        <a
                          className="du-btn du-btn--wa du-btn--sm"
                          href={wa}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="Escribirle al cliente por WhatsApp"
                          onClick={e => e.stopPropagation()}
                        >
                          <MessageCircle size={14} /> Escribir
                        </a>
                      )}
                      {/* Cobrar sin cerrar la entrega: a veces el cliente paga
                          y el repartidor todavía tiene algo que resolver. */}
                      {cobroEfectivoPendiente(dom) && esDomicilioActivo(dom.estadoId) && (
                        <button
                          className="du-btn du-btn--oro du-btn--sm"
                          onClick={e => { e.stopPropagation(); setCobrando({ dom, entregarDespues: false }); }}
                          title="Registrar el cobro en efectivo"
                        >
                          <Banknote size={14} /> Cobrar
                        </button>
                      )}
                      {puedeCambiar && (
                        <button
                          className="du-btn du-btn--primario du-btn--sm"
                          onClick={e => { e.stopPropagation(); setModal({ type: "cambiarEstado", dom }); }}
                        >
                          Actualizar <ChevronRight size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {modal?.type === "detalles" && (
        <DetallesModal
          domicilio={modal.dom}
          onClose={() => setModal(null)}
          onCambiarEstado={(dom) => setModal({ type: "cambiarEstado", dom })}
          onCobrar={(dom) => setCobrando({ dom, entregarDespues: false })}
        />
      )}

      {modal?.type === "cambiarEstado" && (
        <CambiarEstadoModal
          domicilio={modal.dom}
          onClose={() => setModal(null)}
          onSave={handleCambiarEstado}
        />
      )}

      {cobrando && (
        <CobroEfectivoModal
          domicilio={cobrando.dom}
          saving={false}
          entregarDespues={cobrando.entregarDespues}
          onClose={() => setCobrando(null)}
          onConfirm={handleCobrar}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
