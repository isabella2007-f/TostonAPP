import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { getUser } from "../../../services/authService";
import { getDomicilios, getResumenDia } from "../../../services/domiciliosService";
import { ESTADO_DOMICILIO, ESTADO_DOM_CONFIG, esDomicilioActivo } from "./estadosDomicilio";
import "./DomiciliarioUI.css";
import "./DashboardDomiciliario.css";
import {
  Package, CheckCircle2, BarChart2, Banknote, Bike, MapPin,
  ClipboardList, Truck, CalendarDays, RefreshCw,
  ChevronRight, AlertCircle,
} from "lucide-react";
import { formatCOP } from "../../../utils/formato";


// Prioridad para elegir el pedido en curso: primero el que ya va en ruta.
const ESTADO_ORDEN = [
  ESTADO_DOMICILIO.EN_CAMINO,
  ESTADO_DOMICILIO.ASIGNADO,
  ESTADO_DOMICILIO.PENDIENTE,
];

const fmtCOP = formatCOP;

/* Las variables de color viajan al CSS: la hoja no repite ningún hex de
   estado, así sigue mandando estadosDomicilio.js como fuente única. */
const varsEstado = (estadoId) => {
  const cfg = ESTADO_DOM_CONFIG[estadoId] ||
    { dot: "#757575", bg: "#f5f5f5", border: "#e0e0e0", label: "—" };
  return { cfg, vars: { "--e-dot": cfg.dot, "--e-bg": cfg.bg, "--e-border": cfg.border } };
};

export default function DashboardDomiciliario() {
  const user = getUser();
  const [resumen, setResumen] = useState({
    activos: 0, entregados_hoy: 0, total_hoy: 0, efectivo_hoy: 0,
  });
  const [ordenActiva, setOrdenActiva] = useState(null);
  const [loading, setLoading]       = useState(true);
  const [errorCarga, setErrorCarga] = useState(null);

  const cargar = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    setErrorCarga(null);
    try {
      const [res, doms] = await Promise.all([
        getResumenDia(),
        getDomicilios({ porPagina: 100, idEmpleado: user.id }),
      ]);
      // Los números del día los calcula el servidor (ver obtener_resumen_dia):
      // acá se sacaban a mano sobre la primera página de domicilios, y el
      // efectivo se contaba mal en los pedidos mixtos —sumaba el pedido
      // entero cuando solo la mitad se cobra en mano, y el estado de pago
      // de un mixto nunca es "efectivo_recibido", así que casi siempre
      // quedaba en cero—.
      setResumen(res);
      const mios = doms.domicilios || [];
      const activos = mios.filter(d => esDomicilioActivo(d.estadoId));
      activos.sort(
        (a, b) => ESTADO_ORDEN.indexOf(a.estadoId) - ESTADO_ORDEN.indexOf(b.estadoId)
      );
      setOrdenActiva(activos[0] || null);
    } catch (e) {
      setErrorCarga(e?.message || "No se pudo cargar el resumen. Intenta de nuevo.");
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  useEffect(() => { cargar(); }, [cargar]);

  const hoy = new Date().toLocaleDateString("es-CO", {
    weekday: "long", day: "numeric", month: "long",
  });

  /* Las tres primeras métricas se quedan en la gama verde; el efectivo va en
     dorado porque es la plata que el repartidor lleva en mano — el mismo
     código de color que usan Mis Entregas y Pedido Actual. */
  const STATS = [
    { label: "Pedidos activos",    value: resumen.activos,        Icon: Package,      color: "#2e7d32", bg: "#e8f5e9", borde: "#c6e5c9" },
    { label: "Entregados hoy",     value: resumen.entregados_hoy, Icon: CheckCircle2, color: "#1b5e20", bg: "#e2f0e4", borde: "#bcdec1" },
    // Los pesos que movió en las entregas de hoy. Antes esta tarjeta decía
    // "Total del día" y mostraba un CONTEO de domicilios creados hoy: un
    // número que no era plata ni era del repartidor.
    { label: "Entregado hoy",      value: fmtCOP(resumen.total_hoy),    money: true, Icon: BarChart2, color: "#558b2f", bg: "#eef6e4", borde: "#d5e8bf" },
    // Lo que debe entregar en caja al cerrar el día.
    { label: "Efectivo recaudado", value: fmtCOP(resumen.efectivo_hoy), money: true, Icon: Banknote,  color: "#b26a00", bg: "#fff5da", borde: "#ffe082" },
  ];

  /* Los mismos dos destinos que tiene el menú, y nada más. Estos accesos
     seguían ofreciendo seis: cuatro llevaban a pantallas que ya no forman
     parte del panel —el pedido actual, lo que entregó, las notificaciones y
     el perfil— y un acceso directo a algo que no está en ninguna parte es
     peor que no tenerlo.

     Lo que ofrecían sigue a mano, donde se busca: el pedido en curso está
     arriba en esta misma pantalla y se trabaja desde Mis Entregas, la plata
     del día son las dos tarjetas de arriba, las notificaciones están en la
     campanita, y el perfil en el menú del usuario. */
  const ACCESOS = [
    { label: "Mis Entregas", Icon: Bike,          link: "/admin/mis-entregas",       desc: "Pedidos asignados" },
    { label: "Historial",    Icon: ClipboardList,  link: "/admin/historial-entregas", desc: "Entregas anteriores" },
  ];

  const curso = ordenActiva ? varsEstado(ordenActiva.estadoId) : null;

  return (
    <div className="dom-ui dash-domi">
      <header className="du-hero">
        <div className="du-hero__top">
          <div>
            <span className="du-hero__eyebrow"><CalendarDays size={14} /> {hoy}</span>
            <h1 className="du-hero__title">¡Hola, {user?.nombre}!</h1>
            <p className="du-hero__sub">
              Panel de domiciliario. Este es el resumen de tu jornada y todo lo que tienes a mano.
            </p>
          </div>
          <button
            className={`du-hero__refresh${loading ? " du-hero__refresh--girando" : ""}`}
            onClick={cargar}
            disabled={loading}
          >
            <RefreshCw size={15} /> Actualizar
          </button>
        </div>
      </header>

      <div className="du-inner">
        {errorCarga && (
          <div className="du-error" style={{ marginBottom: 22 }}>
            <AlertCircle size={15} /> {errorCarga}
          </div>
        )}

        <div className="db-col">
          {/* ── Resumen del día ── */}
          <section>
            <h2 className="db-seccion__titulo">Tu día de hoy</h2>
            {loading ? (
              <div className="db-stats">
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className="du-skel-card">
                    <div className="du-skel" style={{ width: 44, height: 44, borderRadius: 14 }} />
                    <div className="du-skel" style={{ width: "55%", height: 26 }} />
                    <div className="du-skel" style={{ width: "80%", height: 11 }} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="db-stats">
                {STATS.map(stat => (
                  <div
                    key={stat.label}
                    className="db-stat"
                    style={{ "--s-color": stat.color, "--s-bg": stat.bg, "--s-borde": stat.borde }}
                  >
                    <span className="db-stat__icon"><stat.Icon size={21} strokeWidth={1.8} /></span>
                    <div className={`db-stat__valor${stat.money ? " db-stat__valor--money" : ""}`}>
                      {stat.value}
                    </div>
                    <div className="db-stat__label">{stat.label}</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Pedido en curso ── */}
          {!loading && ordenActiva && (
            <section>
              <h2 className="db-seccion__titulo">Pedido en curso</h2>
              <div className="db-curso" style={curso.vars}>
                <span className="db-curso__avatar">
                  {ordenActiva.estadoId === ESTADO_DOMICILIO.EN_CAMINO
                    ? <Truck size={25} />
                    : <Package size={25} />}
                </span>
                <div className="db-curso__txt">
                  <div className="db-curso__num">{ordenActiva.numero}</div>
                  <div className="db-curso__cliente">{ordenActiva.cliente?.nombre || "Cliente"}</div>
                  <div className="db-curso__dir">
                    <MapPin size={14} />
                    <span>{ordenActiva.direccion_entrega || "Sin dirección"}</span>
                  </div>
                </div>
                <div className="db-curso__lado">
                  <span
                    className={`du-badge du-badge--lg${ordenActiva.estadoId === ESTADO_DOMICILIO.EN_CAMINO ? " du-badge--vivo" : ""}`}
                    style={curso.vars}
                  >
                    {ordenActiva.estadoId === ESTADO_DOMICILIO.EN_CAMINO
                      ? <Bike size={14} />
                      : <Package size={14} />}
                    {curso.cfg.label}
                  </span>
                  {/* A Mis Entregas, que es donde el repartidor lo mueve:
                      marca en camino, entregado y registra el efectivo. */}
                  <Link to="/admin/mis-entregas" className="du-btn du-btn--primario">
                    Ver pedido <ChevronRight size={15} />
                  </Link>
                </div>
              </div>
            </section>
          )}

          {/* ── Accesos rápidos ── */}
          <section>
            <h2 className="db-seccion__titulo">Accesos rápidos</h2>
            <div className="db-accesos">
              {ACCESOS.map(item => (
                <Link key={item.label} to={item.link} className="db-acceso">
                  <span className="db-acceso__icon"><item.Icon size={22} strokeWidth={1.7} /></span>
                  <div className="db-acceso__txt">
                    <div className="db-acceso__label">{item.label}</div>
                    <div className="db-acceso__desc">{item.desc}</div>
                  </div>
                  <ChevronRight size={17} className="db-acceso__flecha" />
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
