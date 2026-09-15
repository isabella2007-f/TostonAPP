import { createContext, useContext, useState, useEffect, useCallback } from "react";
import {
  AlertTriangle, AlertCircle, Clock, XCircle, ShoppingCart,
  Package, Bell, CornerUpLeft, CheckCircle2, Factory, Calendar, Bike,
  CreditCard,
} from "lucide-react";
import {
  getNotificacionesAdmin,
  marcarLeidaAPI,
  eliminarNotificacionAPI,
  limpiarLeidasAPI,
  getMisNotificacionesCliente,
  getNotificacionesCocina,
  getNotificacionesDomiciliario,
} from "../../../services/notificacionesService";
// El nombre del rol lo escribe quien lo crea en Configuración → Roles, así que
// llega como "Domiciliario", "Repartidor", "domiciliarios"… Aquí se comparaba
// con === 'domiciliario' y cualquier otra forma dejaba al repartidor fuera del
// polling: la campana del navbar nunca le mostraba nada. Misma regla que usan
// el router, el layout y el sidebar.
import { esRolRepartidor } from "../../../utils/roles";

/* ══════════════════════════════════════════════════════════
   TIPOS DE NOTIFICACIÓN
══════════════════════════════════════════════════════════ */
export const TIPOS = {
  STOCK_MINIMO:         "stock_minimo",
  STOCK_AGOTADO:        "stock_agotado",
  LOTE_POR_VENCER:      "lote_por_vencer",
  LOTE_VENCIDO:         "lote_vencido",
  PEDIDO_NUEVO:         "pedido_nuevo",
  COMPRA_PENDIENTE:     "compra_pendiente",
  SISTEMA:              "sistema",
  DEVOLUCION_PENDIENTE: "devolucion_pendiente",
  PEDIDO_CONFIRMADO:    "pedido_confirmado",
  PEDIDO_ENTREGADO:     "pedido_entregado",
  PEDIDO_CANCELADO:     "pedido_cancelado",
  DEVOLUCION_APROBADA:       "devolucion_aprobada",
  DEVOLUCION_RECHAZADA:      "devolucion_rechazada",
  PEDIDO_EN_PRODUCCION:      "pedido_en_produccion",
  FECHA_PROPUESTA:           "fecha_propuesta",
  FECHA_RECHAZADA:           "fecha_rechazada",
  DOMICILIO_ASIGNADO:        "domicilio_asignado",
  ESPERANDO_PAGO:            "esperando_pago",
  PEDIDO_EN_CAMINO:          "pedido_en_camino",
  COMPROBANTE_RECHAZADO:     "comprobante_rechazado",
};

export const TIPO_LABELS = {
  [TIPOS.STOCK_MINIMO]:         "Stock mínimo",
  [TIPOS.STOCK_AGOTADO]:        "Stock agotado",
  [TIPOS.LOTE_POR_VENCER]:      "Por vencer",
  [TIPOS.LOTE_VENCIDO]:         "Vencido",
  [TIPOS.PEDIDO_NUEVO]:         "Pedido nuevo",
  [TIPOS.COMPRA_PENDIENTE]:     "Compra",
  [TIPOS.SISTEMA]:              "Sistema",
  [TIPOS.DEVOLUCION_PENDIENTE]: "Devolución",
  [TIPOS.PEDIDO_CONFIRMADO]:    "Pedido",
  [TIPOS.PEDIDO_ENTREGADO]:     "Pedido",
  [TIPOS.PEDIDO_CANCELADO]:     "Pedido",
  [TIPOS.DEVOLUCION_APROBADA]:  "Devolución",
  [TIPOS.DEVOLUCION_RECHAZADA]: "Devolución",
  [TIPOS.PEDIDO_EN_PRODUCCION]: "Producción",
  [TIPOS.FECHA_PROPUESTA]:      "Fecha propuesta",
  [TIPOS.FECHA_RECHAZADA]:      "Fecha rechazada",
  [TIPOS.DOMICILIO_ASIGNADO]:   "Entrega asignada",
  [TIPOS.ESPERANDO_PAGO]:       "Esperando pago",
  [TIPOS.PEDIDO_EN_CAMINO]:     "Pedido",
  [TIPOS.COMPROBANTE_RECHAZADO]: "Comprobante rechazado",
};

export const TIPO_ICONS = {
  [TIPOS.STOCK_MINIMO]:         AlertTriangle,
  [TIPOS.STOCK_AGOTADO]:        AlertCircle,
  [TIPOS.LOTE_POR_VENCER]:      Clock,
  [TIPOS.LOTE_VENCIDO]:         XCircle,
  [TIPOS.PEDIDO_NUEVO]:         ShoppingCart,
  [TIPOS.COMPRA_PENDIENTE]:     Package,
  [TIPOS.SISTEMA]:              Bell,
  [TIPOS.DEVOLUCION_PENDIENTE]: CornerUpLeft,
  [TIPOS.PEDIDO_CONFIRMADO]:    CheckCircle2,
  [TIPOS.PEDIDO_ENTREGADO]:     CheckCircle2,
  [TIPOS.PEDIDO_CANCELADO]:     XCircle,
  [TIPOS.DEVOLUCION_APROBADA]:  CheckCircle2,
  [TIPOS.DEVOLUCION_RECHAZADA]: XCircle,
  [TIPOS.PEDIDO_EN_PRODUCCION]: Factory,
  [TIPOS.FECHA_PROPUESTA]:      Calendar,
  [TIPOS.FECHA_RECHAZADA]:      XCircle,
  [TIPOS.DOMICILIO_ASIGNADO]:   Bike,
  [TIPOS.ESPERANDO_PAGO]:       CreditCard,
  [TIPOS.PEDIDO_EN_CAMINO]:     Bike,
  [TIPOS.COMPROBANTE_RECHAZADO]: XCircle,
};

export const TIPO_COLORS = {
  [TIPOS.STOCK_MINIMO]:         "#f57f17",
  [TIPOS.STOCK_AGOTADO]:        "#c62828",
  [TIPOS.LOTE_POR_VENCER]:      "#e65100",
  [TIPOS.LOTE_VENCIDO]:         "#b71c1c",
  [TIPOS.PEDIDO_NUEVO]:         "#1565c0",
  [TIPOS.COMPRA_PENDIENTE]:     "#6a1b9a",
  [TIPOS.SISTEMA]:              "#2e7d32",
  [TIPOS.DEVOLUCION_PENDIENTE]: "#8e24aa",
  [TIPOS.PEDIDO_CONFIRMADO]:    "#2e7d32",
  [TIPOS.PEDIDO_ENTREGADO]:     "#2e7d32",
  [TIPOS.PEDIDO_CANCELADO]:     "#c62828",
  [TIPOS.DEVOLUCION_APROBADA]:  "#2e7d32",
  [TIPOS.DEVOLUCION_RECHAZADA]: "#c62828",
  [TIPOS.PEDIDO_EN_PRODUCCION]: "#1565c0",
  [TIPOS.FECHA_PROPUESTA]:      "#283593",
  [TIPOS.FECHA_RECHAZADA]:      "#c62828",
  [TIPOS.DOMICILIO_ASIGNADO]:   "#1565c0",
  [TIPOS.ESPERANDO_PAGO]:       "#e65100",
  [TIPOS.PEDIDO_EN_CAMINO]:     "#1565c0",
  [TIPOS.COMPROBANTE_RECHAZADO]: "#c62828",
};

const DISMISSED_CLAVES_KEY  = 'notif_descartadas_claves';
const DISMISSED_BACKEND_KEY = 'notif_descartadas_backend';

// Tipos backend → tipos frontend
const BACKEND_TYPE_MAP = {
  stock_agotado_insumo:   TIPOS.STOCK_AGOTADO,
  stock_agotado_producto: TIPOS.STOCK_AGOTADO,
  stock_minimo_insumo:    TIPOS.STOCK_MINIMO,
  stock_minimo_producto:  TIPOS.STOCK_MINIMO,
  pedido_nuevo:           TIPOS.PEDIDO_NUEVO,
  produccion_requerida:   TIPOS.SISTEMA,
  domicilio_pendiente:    TIPOS.PEDIDO_NUEVO,
  domicilio_asignado:     TIPOS.DOMICILIO_ASIGNADO,
  devolucion_pendiente:   TIPOS.DEVOLUCION_PENDIENTE,
  pedido_en_produccion:   TIPOS.PEDIDO_EN_PRODUCCION,
  pedido_sobre_stock:     TIPOS.SISTEMA,
  comprobante_rechazado:  TIPOS.SISTEMA,
  fecha_propuesta:        TIPOS.FECHA_PROPUESTA,
  fecha_rechazada:        TIPOS.FECHA_RECHAZADA,
};

// Tipos propios de notificaciones de cliente (no van a localStorage de admin)
const TIPOS_CLIENTE = new Set([
  TIPOS.PEDIDO_CONFIRMADO,
  TIPOS.PEDIDO_ENTREGADO,
  TIPOS.PEDIDO_CANCELADO,
  TIPOS.DEVOLUCION_APROBADA,
  TIPOS.DEVOLUCION_RECHAZADA,
  TIPOS.FECHA_PROPUESTA,
  TIPOS.PEDIDO_EN_PRODUCCION, // también llega al cliente como notif propia
  TIPOS.ESPERANDO_PAGO,
  TIPOS.PEDIDO_EN_CAMINO,
  TIPOS.COMPROBANTE_RECHAZADO,
]);

// Tipos derivados por rol — efímeros, se rehidratan por polling
const TIPOS_COCINA = new Set([
  TIPOS.PEDIDO_NUEVO,
  TIPOS.PEDIDO_EN_PRODUCCION,
]);

const TIPOS_DOMICILIARIO = new Set([
  TIPOS.DOMICILIO_ASIGNADO,
  TIPOS.PEDIDO_CANCELADO,
]);

const uid = () => `N-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
const fechaHoy = () => new Date().toISOString();

/* ══════════════════════════════════════════════════════════
   CONTEXT
══════════════════════════════════════════════════════════ */
const NotificacionesContext = createContext(null);

const NOTIF_VERSION = "2";

const loadFromLS = (key, def) => {
  try { const s = localStorage.getItem(key); return s ? JSON.parse(s) : def; }
  catch { return def; }
};

const initNotificaciones = () => {
  if (localStorage.getItem("notif_version") !== NOTIF_VERSION) {
    localStorage.removeItem("notificaciones");
    localStorage.setItem("notif_version", NOTIF_VERSION);
    return [];
  }
  return loadFromLS("notificaciones", []);
};

export function NotificacionesProvider({ children, insumos = [], lotes = [], pedidos = [], compras = [] }) {

  const [notificaciones, setNotificaciones] = useState(() => initNotificaciones());
  const [user, setLocalUser] = useState(() => {
    const session = localStorage.getItem("usuario");
    return session ? JSON.parse(session) : null;
  });

  const [nivelesMinimos, setNivelesMinimos] = useState(() => loadFromLS("notif_nivelesMinimos", {}));
  const [autoActivo, setAutoActivo]         = useState(() => loadFromLS("notif_autoActivo", true));
  const [bannerVisto, setBannerVisto]       = useState(false);

  /* ── Persistencia (excluye notifs efímeras — se rehidratan por polling) ── */
  useEffect(() => {
    // Solo se persisten las alertas locales de admin (stock, lotes, compras):
    // todo lo demás se re-hidrata por polling. Filtrar por idDestinatario en
    // vez de por un set fijo de tipos evita que un tipo nuevo del backend
    // (ej. un tipo de notif de cliente que aún no está en TIPOS_CLIENTE)
    // termine guardándose aquí por error.
    const sinEfimeras = notificaciones.filter(
      n => !n.clave?.startsWith('api-') && n.idDestinatario === 'admin'
    );
    localStorage.setItem("notificaciones", JSON.stringify(sinEfimeras));
  }, [notificaciones]);
  useEffect(() => { localStorage.setItem("notif_nivelesMinimos", JSON.stringify(nivelesMinimos)); }, [nivelesMinimos]);
  useEffect(() => { localStorage.setItem("notif_autoActivo",     JSON.stringify(autoActivo)); },     [autoActivo]);

  useEffect(() => {
    const checkUser = () => {
      const session = localStorage.getItem("usuario");
      setLocalUser(session ? JSON.parse(session) : null);
    };
    const syncNotifs = (e) => {
      if (e.key === "notificaciones" && e.newValue) setNotificaciones(JSON.parse(e.newValue));
      if (e.key === "notif_nivelesMinimos" && e.newValue) setNivelesMinimos(JSON.parse(e.newValue));
      if (e.key === "notif_autoActivo"     && e.newValue) setAutoActivo(JSON.parse(e.newValue));
      if (e.key === "usuario") checkUser();
    };
    window.addEventListener("storage", syncNotifs);
    window.addEventListener("session-changed", checkUser);
    return () => {
      window.removeEventListener("storage", syncNotifs);
      window.removeEventListener("session-changed", checkUser);
    };
  }, []);

  const agregarNotificacion = useCallback((datos) => {
    const destinatario = datos.idDestinatario || 'admin';
    setNotificaciones(prev => {
      if (datos.clave && prev.some(n => n.clave === datos.clave && !n.leida)) return prev;
      return [{ id: uid(), fecha: fechaHoy(), leida: false, ...datos, idDestinatario: destinatario }, ...prev];
    });
  }, []);

  useEffect(() => {
    const handleExternalNotif = (e) => { if (e.detail) agregarNotificacion(e.detail); };
    window.addEventListener("toston-add-notification", handleExternalNotif);
    return () => window.removeEventListener("toston-add-notification", handleExternalNotif);
  }, [agregarNotificacion]);

  /* ══════════════════════════════════════════════════════
     POLLING DE NOTIFICACIONES DESDE EL BACKEND
  ══════════════════════════════════════════════════════ */
  const fetchAPINotifs = useCallback(async () => {
    if (!user) return;
    const rol           = user.rol?.toLowerCase();
    const isAdmin       = rol === 'admin' || rol === 'administrador';
    const isCliente     = user.tipo === 'cliente';
    const isCocinero    = ['cocina', 'cocinero', 'produccion', 'producción'].includes(rol);
    const isDomiciliario = esRolRepartidor(rol);

    if (isAdmin) {
      try {
        const data    = await getNotificacionesAdmin();
        const vistas  = loadFromLS('notif_admin_vistas', []);
        const notifs  = data.notificaciones || [];
        const backendIds = new Set(notifs.map(n => n.ID_Notificacion));
        // Limpiar dismissed: solo conservar IDs que el backend sigue devolviendo
        const dismissedBackend = loadFromLS(DISMISSED_BACKEND_KEY, []);
        const cleanDismissed = dismissedBackend.filter(id => backendIds.has(id));
        if (cleanDismissed.length !== dismissedBackend.length) {
          localStorage.setItem(DISMISSED_BACKEND_KEY, JSON.stringify(cleanDismissed));
        }
        const dismissedSet = new Set(cleanDismissed);
        const backend = notifs
          .filter(n => !dismissedSet.has(n.ID_Notificacion))
          .map(n => ({
            id:             `api-${n.ID_Notificacion}`,
            clave:          `api-${n.ID_Notificacion}`,
            id_backend:     n.ID_Notificacion,
            tipo:           BACKEND_TYPE_MAP[n.Tipo] || TIPOS.SISTEMA,
            titulo:         n.Titulo,
            mensaje:        n.Mensaje || "",
            idReferencia:   n.Referencia_ID,
            ruta:           n.Ruta,
            fecha:          n.Fecha,
            leida:          n.Leida || vistas.includes(n.ID_Notificacion),
            idDestinatario: 'admin',
          }));
        // Limpiar notif_admin_vistas: sólo conservar IDs que siguen existiendo en el backend
        const vistasFiltradas = vistas.filter(id => backendIds.has(id));
        if (vistasFiltradas.length !== vistas.length) {
          localStorage.setItem('notif_admin_vistas', JSON.stringify(vistasFiltradas));
        }
        setNotificaciones(prev => [
          ...backend,
          ...prev.filter(n => !n.clave?.startsWith('api-') && !TIPOS_CLIENTE.has(n.tipo)),
        ]);
      } catch (_) {}

    } else if (isCliente) {
      try {
        const data   = await getMisNotificacionesCliente();
        const vistas = loadFromLS('notif_cliente_vistas', []);
        const dismissedBackendCliente = new Set(loadFromLS(DISMISSED_BACKEND_KEY, []));
        const dismissedClavesCliente  = new Set(loadFromLS(DISMISSED_CLAVES_KEY, []));
        const cliente = (data.notificaciones || [])
          .filter(n => {
            const idB = n.ID_Notificacion || n.id_notificacion || null;
            if (idB && dismissedBackendCliente.has(idB)) return false;
            if (n.id_ref && dismissedClavesCliente.has(n.id_ref)) return false;
            return true;
          })
          .map(n => {
            const parts    = (n.id_ref || '').split('_');
            const idPedido = n.id_venta || (parts[0] === 'venta' ? Number(parts[1]) : null);
            return {
              id:             n.id_ref,
              clave:          n.id_ref,
              id_backend:     n.ID_Notificacion || n.id_notificacion || null,
              tipo:           n.tipo,
              titulo:         n.titulo,
              mensaje:        n.mensaje || "",
              ruta:           n.ruta,
              fecha:          n.fecha,
              leida:          n.leida || n.Leida || vistas.includes(n.id_ref),
              idDestinatario: String(user.id),
              idPedido,
              fechaEntrega:   n.fecha_entrega || null,
            };
          });
        // Reemplaza SOLO las notifs propias del cliente (identificadas por
        // idDestinatario, no por tipo): filtrar por TIPOS_CLIENTE dejaba
        // fuera cualquier tipo no listado ahí (ej. "comprobante_rechazado")
        // y esas quedaban acumulándose sin reemplazo en cada poll — se
        // duplicaban indefinidamente porque el mismo id_ref se volvía a
        // anteponer con [...cliente, ...] sin quitar la copia vieja.
        setNotificaciones(prev => [
          ...cliente,
          ...prev.filter(n => n.idDestinatario === 'admin' || n.idDestinatario === 'produccion' || n.idDestinatario === 'domiciliario'),
        ]);
      } catch (_) {}

    } else if (isCocinero) {
      try {
        const data   = await getNotificacionesCocina();
        const vistas = loadFromLS('notif_cocina_vistas', []);
        const dismissedCocinaClaves = new Set(loadFromLS(DISMISSED_CLAVES_KEY, []));
        const cocina = (data.notificaciones || [])
          .filter(n => !dismissedCocinaClaves.has(n.id_ref))
          .map(n => ({
            id:             n.id_ref,
            clave:          n.id_ref,
            tipo:           n.tipo,
            titulo:         n.titulo,
            mensaje:        n.mensaje || "",
            ruta:           n.ruta,
            fecha:          n.fecha,
            leida:          n.leida || vistas.includes(n.id_ref),
            idDestinatario: 'produccion',
            idPedido:       n.id_venta || null,
          }));
        setNotificaciones(prev => [
          ...cocina,
          ...prev.filter(n => !TIPOS_COCINA.has(n.tipo)),
        ]);
      } catch (_) {}

    } else if (isDomiciliario) {
      try {
        const data  = await getNotificacionesDomiciliario();
        const vistas = loadFromLS('notif_dom_vistas', []);
        const dismissedDomClaves = new Set(loadFromLS(DISMISSED_CLAVES_KEY, []));
        const domNotifs = (data.notificaciones || [])
          .filter(n => !dismissedDomClaves.has(n.id_ref))
          .map(n => ({
            id:             n.id_ref,
            clave:          n.id_ref,
            tipo:           n.tipo,
            titulo:         n.titulo,
            mensaje:        n.mensaje || "",
            ruta:           n.ruta,
            fecha:          n.fecha,
            leida:          vistas.includes(n.id_ref),
            idDestinatario: 'domiciliario',
          }));
        setNotificaciones(prev => [
          ...domNotifs,
          ...prev.filter(n => !TIPOS_DOMICILIARIO.has(n.tipo)),
        ]);
      } catch (_) {}
    }
  }, [user]);

  // Inicia el polling según el rol
  useEffect(() => {
    if (!user) return;
    const rol          = user.rol?.toLowerCase();
    const isAdmin      = rol === 'admin' || rol === 'administrador';
    const isCliente    = user.tipo === 'cliente';
    const isCocinero   = ['cocina', 'cocinero', 'produccion', 'producción'].includes(rol);
    const isDomiciliario = esRolRepartidor(rol);
    if (!isAdmin && !isCliente && !isCocinero && !isDomiciliario) return;

    fetchAPINotifs();
    const ms = (isAdmin || isCocinero) ? 15_000 : 30_000;
    const id = setInterval(fetchAPINotifs, ms);
    // Al volver a la pestaña, refresca de inmediato en vez de esperar al
    // siguiente tick del interval (mismo patrón que MainLayout.jsx).
    const onVisible = () => { if (document.visibilityState === "visible") fetchAPINotifs(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [user, fetchAPINotifs]);

  // Limpia notificaciones efímeras al cambiar de usuario
  useEffect(() => {
    setNotificaciones(prev => prev.filter(
      n => !n.clave?.startsWith('api-')
        && !TIPOS_CLIENTE.has(n.tipo)
        && !TIPOS_COCINA.has(n.tipo)
        && !TIPOS_DOMICILIARIO.has(n.tipo)
    ));
  }, [user?.id]);

  /* ══════════════════════════════════════════════════════
     GENERACIÓN AUTOMÁTICA LOCAL (stock, lotes, compras)
     Solo para administradores
  ══════════════════════════════════════════════════════ */
  const generarNotifAutomaticas = useCallback(() => {
    const rol     = user?.rol?.toLowerCase();
    const isAdmin = rol === 'admin' || rol === 'administrador';
    if (!autoActivo || !isAdmin) return;

    setNotificaciones(prev => {
      const nuevas = [];
      const hoy    = new Date(); hoy.setHours(0, 0, 0, 0);

      const insumosLoaded = insumos.length > 0;
      const lotesLoaded   = lotes.length > 0;
      const comprasLoaded = compras.length > 0;

      // Cargar descartadas y limpiar las que ya no cumplen la condición (así vuelven a aparecer si el problema reaparece)
      const dismissedArr = loadFromLS(DISMISSED_CLAVES_KEY, []);
      const dismissed = new Set(dismissedArr);
      if (insumosLoaded) {
        insumos.forEach(ins => {
          const minimo = nivelesMinimos[ins.id] !== undefined ? nivelesMinimos[ins.id] : ins.stockMinimo;
          if (ins.stockActual > 0)      dismissed.delete(`${TIPOS.STOCK_AGOTADO}-${ins.id}`);
          if (ins.stockActual > minimo) dismissed.delete(`${TIPOS.STOCK_MINIMO}-${ins.id}`);
        });
      }
      if (lotesLoaded) {
        lotes.forEach(lote => {
          if (!lote.fechaVencimiento || lote.cantidadActual <= 0) {
            dismissed.delete(`${TIPOS.LOTE_VENCIDO}-${lote.id}`);
            dismissed.delete(`${TIPOS.LOTE_POR_VENCER}-${lote.id}`);
            return;
          }
          const dias = Math.round((new Date(lote.fechaVencimiento + "T00:00:00") - hoy) / 86_400_000);
          if (dias >= 0) dismissed.delete(`${TIPOS.LOTE_VENCIDO}-${lote.id}`);
          if (dias > 7)  dismissed.delete(`${TIPOS.LOTE_POR_VENCER}-${lote.id}`);
        });
      }
      if (comprasLoaded) {
        compras.forEach(compra => {
          if (compra.estado !== 'pendiente') dismissed.delete(`${TIPOS.COMPRA_PENDIENTE}-${compra.id}`);
        });
      }
      if (dismissed.size !== dismissedArr.length) {
        localStorage.setItem(DISMISSED_CLAVES_KEY, JSON.stringify([...dismissed]));
      }

      const notificacionesActuales = prev.filter(n => {
        if (n.clave?.startsWith('api-') || TIPOS_CLIENTE.has(n.tipo)) return true;
        if (n.tipo === TIPOS.STOCK_AGOTADO) {
          if (!insumosLoaded) return true;
          const ins = insumos.find(i => i.id === n.idReferencia);
          return ins && ins.stockActual <= 0;
        }
        if (n.tipo === TIPOS.STOCK_MINIMO) {
          if (!insumosLoaded) return true;
          const ins = insumos.find(i => i.id === n.idReferencia);
          if (!ins) return false;
          const min = nivelesMinimos[ins.id] !== undefined ? nivelesMinimos[ins.id] : ins.stockMinimo;
          return ins.stockActual > 0 && ins.stockActual <= min;
        }
        if (n.tipo === TIPOS.LOTE_POR_VENCER) {
          if (!lotesLoaded) return true;
          const lote = lotes.find(l => l.id === n.idReferencia);
          if (!lote || lote.cantidadActual <= 0) return false;
          const dias = Math.round((new Date(lote.fechaVencimiento + "T00:00:00") - hoy) / 86_400_000);
          return dias >= 0 && dias <= 7;
        }
        if (n.tipo === TIPOS.LOTE_VENCIDO) {
          if (!lotesLoaded) return true;
          const lote = lotes.find(l => l.id === n.idReferencia);
          if (!lote || lote.cantidadActual <= 0) return false;
          const dias = Math.round((new Date(lote.fechaVencimiento + "T00:00:00") - hoy) / 86_400_000);
          return dias < 0;
        }
        if (n.tipo === TIPOS.COMPRA_PENDIENTE) {
          if (!comprasLoaded) return true;
          const compra = compras.find(c => c.id === n.idReferencia);
          return compra && compra.estado === "pendiente";
        }
        return true;
      });

      insumos.forEach(ins => {
        const minimo = nivelesMinimos[ins.id] !== undefined ? nivelesMinimos[ins.id] : ins.stockMinimo;
        const stock  = ins.stockActual;
        if (stock <= 0) {
          const clave = `${TIPOS.STOCK_AGOTADO}-${ins.id}`;
          if (!dismissed.has(clave) && !notificacionesActuales.some(n => n.clave === clave)) {
            nuevas.push({
              id: uid(), clave, tipo: TIPOS.STOCK_AGOTADO,
              titulo: `Stock agotado: ${ins.nombre}`,
              mensaje: `El insumo "${ins.nombre}" tiene stock en 0. Se requiere realizar una compra urgente.`,
              idReferencia: ins.id, refNombre: ins.nombre,
              fecha: fechaHoy(), leida: false, idDestinatario: 'admin',
            });
          }
        } else if (minimo !== undefined && stock <= minimo) {
          const clave = `${TIPOS.STOCK_MINIMO}-${ins.id}`;
          if (!dismissed.has(clave) && !notificacionesActuales.some(n => n.clave === clave)) {
            nuevas.push({
              id: uid(), clave, tipo: TIPOS.STOCK_MINIMO,
              titulo: `Stock bajo mínimo: ${ins.nombre}`,
              mensaje: `El insumo "${ins.nombre}" tiene ${stock} ${ins.unidad || "und"} disponibles, por debajo del mínimo configurado de ${minimo}. Se requiere realizar una compra.`,
              idReferencia: ins.id, refNombre: ins.nombre,
              fecha: fechaHoy(), leida: false, idDestinatario: 'admin',
            });
          }
        }
      });

      lotes.forEach(lote => {
        if (!lote.fechaVencimiento || lote.cantidadActual <= 0) return;
        const fv   = new Date(lote.fechaVencimiento + "T00:00:00");
        const dias = Math.round((fv - hoy) / 86_400_000);
        const insumo = insumos.find(i => i.id === lote.idInsumo);
        const nombre = insumo?.nombre || `Insumo #${lote.idInsumo}`;
        if (dias < 0) {
          const clave = `${TIPOS.LOTE_VENCIDO}-${lote.id}`;
          if (!dismissed.has(clave) && !notificacionesActuales.some(n => n.clave === clave)) {
            nuevas.push({
              id: uid(), clave, tipo: TIPOS.LOTE_VENCIDO,
              titulo: `Lote vencido: ${nombre}`,
              mensaje: `El lote ${lote.id} de "${nombre}" venció el ${lote.fechaVencimiento}. Contiene ${lote.cantidadActual} unidades. Retírelo del inventario.`,
              idReferencia: lote.id, refNombre: nombre,
              fecha: fechaHoy(), leida: false, idDestinatario: 'admin',
            });
          }
        } else if (dias <= 7) {
          const clave = `${TIPOS.LOTE_POR_VENCER}-${lote.id}`;
          if (!dismissed.has(clave) && !notificacionesActuales.some(n => n.clave === clave)) {
            nuevas.push({
              id: uid(), clave, tipo: TIPOS.LOTE_POR_VENCER,
              titulo: `Lote próximo a vencer: ${nombre}`,
              mensaje: `El lote ${lote.id} de "${nombre}" vence en ${dias} día${dias === 1 ? "" : "s"} (${lote.fechaVencimiento}). Contiene ${lote.cantidadActual} unidades.`,
              idReferencia: lote.id, refNombre: nombre,
              fecha: fechaHoy(), leida: false, idDestinatario: 'admin',
            });
          }
        }
      });

      compras.forEach(compra => {
        if (compra.estado !== "pendiente") return;
        const dias = Math.round((hoy - new Date(compra.fecha + "T00:00:00")) / 86_400_000);
        if (dias >= 5) {
          const clave = `${TIPOS.COMPRA_PENDIENTE}-${compra.id}`;
          if (!dismissed.has(clave) && !notificacionesActuales.some(n => n.clave === clave)) {
            nuevas.push({
              id: uid(), clave, tipo: TIPOS.COMPRA_PENDIENTE,
              titulo: `Compra pendiente: ${compra.id}`,
              mensaje: `La compra ${compra.id} lleva ${dias} días en estado pendiente. Verifique su estado con el proveedor.`,
              idReferencia: compra.id, refNombre: compra.id,
              fecha: fechaHoy(), leida: false, idDestinatario: 'admin',
            });
          }
        }
      });

      if (nuevas.length > 0 || notificacionesActuales.length !== prev.length) {
        return [...nuevas, ...notificacionesActuales];
      }
      return prev;
    });
  }, [autoActivo, insumos, lotes, compras, nivelesMinimos, user]);

  useEffect(() => {
    generarNotifAutomaticas();
  }, [autoActivo, insumos, lotes, compras, user, generarNotifAutomaticas]);

  /* ── Acciones ──────────────────────────────────────────── */
  const marcarLeida = useCallback((id) => {
    // Los efectos (API + localStorage) se calculan y disparan una sola vez,
    // fuera del updater de setNotificaciones: ese updater puede re-ejecutarse
    // más de una vez para el mismo evento (batching de React), y antes
    // duplicaba llamadas a la API y escrituras de localStorage.
    const notif = notificaciones.find(n => n.id === id);
    if (!notif) return;
    if (notif.id_backend) {
      marcarLeidaAPI(notif.id_backend).catch(() => {});
      // fallback local para admin: persiste entre recargas aunque el API falle
      if (notif.idDestinatario === 'admin') {
        const vistas = loadFromLS('notif_admin_vistas', []);
        if (!vistas.includes(notif.id_backend)) {
          localStorage.setItem('notif_admin_vistas', JSON.stringify([...vistas, notif.id_backend]));
        }
      }
    }
    if (notif.idDestinatario === 'produccion') {
      const vistas = loadFromLS('notif_cocina_vistas', []);
      if (!vistas.includes(id)) localStorage.setItem('notif_cocina_vistas', JSON.stringify([...vistas, id]));
    } else if (notif.idDestinatario === 'domiciliario') {
      const vistas = loadFromLS('notif_dom_vistas', []);
      if (!vistas.includes(id)) localStorage.setItem('notif_dom_vistas', JSON.stringify([...vistas, id]));
    } else if (notif.idDestinatario && notif.idDestinatario !== 'admin') {
      // cliente (idDestinatario = String del id numérico)
      const vistas = loadFromLS('notif_cliente_vistas', []);
      if (!vistas.includes(id)) localStorage.setItem('notif_cliente_vistas', JSON.stringify([...vistas, id]));
    }
    setNotificaciones(prev => prev.map(n => n.id === id ? { ...n, leida: true } : n));
  }, [notificaciones]);

  const marcarTodasLeidas = useCallback(() => {
    const currentUser    = JSON.parse(localStorage.getItem("usuario") || "null") || user;
    const rol            = currentUser?.rol?.toLowerCase();
    const isAdmin        = rol === 'admin' || rol === 'administrador';
    const isCook         = ['cocina', 'cocinero', 'produccion', 'producción'].includes(rol);
    const isDomiciliario = esRolRepartidor(rol);

    // Sincronizar lecturas con el backend (fire-and-forget) + fallback localStorage
    if (isAdmin) {
      const adminUnread = notificaciones.filter(n => n.id_backend && !n.leida && n.idDestinatario === 'admin');
      adminUnread.forEach(n => { marcarLeidaAPI(n.id_backend).catch(() => {}); });
      if (adminUnread.length > 0) {
        const vistas = loadFromLS('notif_admin_vistas', []);
        const nuevas = [...new Set([...vistas, ...adminUnread.map(n => n.id_backend)])];
        localStorage.setItem('notif_admin_vistas', JSON.stringify(nuevas));
      }
    }

    // Cocinero: guardar en localStorage para sobrevivir la recarga
    if (isCook) {
      const cocinaUnread = notificaciones.filter(n => TIPOS_COCINA.has(n.tipo) && !n.leida);
      if (cocinaUnread.length > 0) {
        const vistas = loadFromLS('notif_cocina_vistas', []);
        const nuevas = [...new Set([...vistas, ...cocinaUnread.map(n => n.id)])];
        localStorage.setItem('notif_cocina_vistas', JSON.stringify(nuevas));
      }
    }

    // Sincronizar lecturas de cliente con el backend y localStorage. No se
    // filtra por TIPOS_CLIENTE: ese set no cubre todos los tipos que el
    // backend puede mandarle a un cliente (ej. "comprobante_rechazado"), así
    // que una notif de un tipo no listado se marcaba leída solo en memoria y
    // el siguiente polling la traía de vuelta como no leída. idDestinatario
    // ya identifica sin ambigüedad qué notifs son del cliente actual.
    const clienteUnread = notificaciones.filter(n =>
      !n.leida &&
      n.idDestinatario !== 'admin' && n.idDestinatario !== 'produccion' && n.idDestinatario !== 'domiciliario'
    );
    if (clienteUnread.length > 0) {
      clienteUnread.forEach(n => {
        if (n.id_backend) marcarLeidaAPI(n.id_backend).catch(() => {});
      });
      const vistas     = loadFromLS('notif_cliente_vistas', []);
      const nuevasVistas = [...new Set([...vistas, ...clienteUnread.map(n => n.id)])];
      localStorage.setItem('notif_cliente_vistas', JSON.stringify(nuevasVistas));
    }

    // Domiciliario: guardar en localStorage para sobrevivir la recarga
    if (isDomiciliario) {
      const domUnread = notificaciones.filter(n => TIPOS_DOMICILIARIO.has(n.tipo) && !n.leida);
      if (domUnread.length > 0) {
        const vistas = loadFromLS('notif_dom_vistas', []);
        const nuevas = [...new Set([...vistas, ...domUnread.map(n => n.id)])];
        localStorage.setItem('notif_dom_vistas', JSON.stringify(nuevas));
      }
    }

    setNotificaciones(prev => prev.map(n => {
      const isForCurrent = (isAdmin && n.idDestinatario === 'admin')
        || (n.idDestinatario === String(currentUser?.id));
      const isForCook         = isCook         && n.idDestinatario === 'produccion';
      const isForDomiciliario = isDomiciliario && n.idDestinatario === 'domiciliario';
      return (isForCurrent || isForCook || isForDomiciliario) ? { ...n, leida: true } : n;
    }));
  }, [notificaciones, user]);

  const filtrar = useCallback(({ tipo, estado, texto }) => {
    return notificaciones.filter(n => {
      const currentUser    = JSON.parse(localStorage.getItem("usuario") || "null") || user;
      const rol            = currentUser?.rol?.toLowerCase();
      const isAdmin        = rol === 'admin' || rol === 'administrador';
      const isCook         = ['cocina', 'cocinero', 'produccion', 'producción'].includes(rol);
      const isClient       = currentUser?.tipo === 'cliente';
      const isDomiciliario = esRolRepartidor(rol);

      const isForAdmin       = isAdmin       && n.idDestinatario === 'admin';
      const isForCook        = isCook        && n.idDestinatario === 'produccion';
      const isForClient      = isClient      && n.idDestinatario === String(currentUser?.id);
      const isForDomiciliario = isDomiciliario && n.idDestinatario === 'domiciliario';

      if (!isForAdmin && !isForCook && !isForClient && !isForDomiciliario) return false;
      if (tipo   && n.tipo  !== tipo)                                            return false;
      if (estado === "leida"    && !n.leida)                                     return false;
      if (estado === "no_leida" &&  n.leida)                                     return false;
      if (texto  && !n.titulo.toLowerCase().includes(texto.toLowerCase()) &&
                    !(n.mensaje || "").toLowerCase().includes(texto.toLowerCase())) return false;
      return true;
    }).sort((a, b) => new Date(b.fecha) - new Date(a.fecha));
  }, [notificaciones, user]);

  const configurarNivelMinimo = useCallback((idInsumo, nivel) => {
    setNivelesMinimos(prev => ({ ...prev, [idInsumo]: Number(nivel) }));
  }, []);

  const eliminarNotificacion = useCallback((id) => {
    const notif = notificaciones.find(n => n.id === id);
    if (notif?.id_backend) {
      eliminarNotificacionAPI(notif.id_backend).catch(() => {});
      const dismissed = loadFromLS(DISMISSED_BACKEND_KEY, []);
      if (!dismissed.includes(notif.id_backend)) {
        localStorage.setItem(DISMISSED_BACKEND_KEY, JSON.stringify([...dismissed, notif.id_backend]));
      }
    }
    if (notif?.clave && !notif.clave.startsWith('api-')) {
      const dismissed = loadFromLS(DISMISSED_CLAVES_KEY, []);
      if (!dismissed.includes(notif.clave)) {
        localStorage.setItem(DISMISSED_CLAVES_KEY, JSON.stringify([...dismissed, notif.clave]));
      }
    }
    setNotificaciones(prev => prev.filter(n => n.id !== id));
  }, [notificaciones]);

  const eliminarTodasNotificaciones = useCallback(() => {
    const currentUser    = JSON.parse(localStorage.getItem("usuario") || "null") || user;
    const rol            = currentUser?.rol?.toLowerCase();
    const isAdmin        = rol === 'admin' || rol === 'administrador';
    const isCook         = ['cocina', 'cocinero', 'produccion', 'producción'].includes(rol);
    const isDomiciliario = esRolRepartidor(rol);

    const mios = notificaciones.filter(n => (
      (isAdmin && n.idDestinatario === 'admin')
      || (isCook && n.idDestinatario === 'produccion')
      || (isDomiciliario && n.idDestinatario === 'domiciliario')
      || (!isAdmin && !isCook && !isDomiciliario && n.idDestinatario === String(currentUser?.id))
    ));

    if (isAdmin) {
      // El panel de admin/empleado es una bandeja compartida (sin filtro por
      // usuario en el backend): "eliminar todas" ya descartaba TODO lo que
      // hoy trae `obtener_notificaciones`, notif por notif. Vaciar con este
      // único endpoint bulk tiene el mismo alcance, solo que en 1 llamada en
      // vez de N.
      limpiarLeidasAPI().catch(() => {});
    } else {
      const dismissedBackend = loadFromLS(DISMISSED_BACKEND_KEY, []);
      const dismissedClaves  = loadFromLS(DISMISSED_CLAVES_KEY, []);
      let backendChanged = false;
      let clavesChanged  = false;

      mios.forEach(n => {
        if (n.id_backend) {
          eliminarNotificacionAPI(n.id_backend).catch(() => {});
          if (!dismissedBackend.includes(n.id_backend)) { dismissedBackend.push(n.id_backend); backendChanged = true; }
        }
        if (n.clave && !n.clave.startsWith('api-')) {
          if (!dismissedClaves.includes(n.clave)) { dismissedClaves.push(n.clave); clavesChanged = true; }
        }
      });

      if (backendChanged) localStorage.setItem(DISMISSED_BACKEND_KEY, JSON.stringify(dismissedBackend));
      if (clavesChanged)  localStorage.setItem(DISMISSED_CLAVES_KEY,  JSON.stringify(dismissedClaves));
    }

    const idsAEliminar = new Set(mios.map(n => n.id));
    setNotificaciones(prev => prev.filter(n => !idsAEliminar.has(n.id)));
  }, [notificaciones, user]);

  const notifUsuario = notificaciones.filter(n => {
    const rol            = user?.rol?.toLowerCase();
    const isAdmin        = rol === 'admin' || rol === 'administrador';
    const isCook         = ['cocina', 'cocinero', 'produccion', 'producción'].includes(rol);
    const isClient       = user?.tipo === 'cliente';
    const isDomiciliario = esRolRepartidor(rol);
    const isForAdmin       = isAdmin       && n.idDestinatario === 'admin';
    const isForCook        = isCook        && n.idDestinatario === 'produccion';
    const isForClient      = isClient      && n.idDestinatario === String(user?.id);
    const isForDomiciliario = isDomiciliario && n.idDestinatario === 'domiciliario';
    return isForAdmin || isForCook || isForClient || isForDomiciliario;
  });

  const noLeidas       = notifUsuario.filter(n => !n.leida).length;
  const criticas       = notifUsuario.filter(n => !n.leida && [TIPOS.STOCK_AGOTADO, TIPOS.LOTE_VENCIDO].includes(n.tipo));
  const notifOrdenadas = [...notifUsuario].sort((a, b) => new Date(b.fecha) - new Date(a.fecha));

  return (
    <NotificacionesContext.Provider value={{
      notificaciones: notifOrdenadas,
      noLeidas,
      criticas,
      autoActivo,
      nivelesMinimos,
      bannerVisto,
      setBannerVisto,
      marcarLeida,
      marcarTodasLeidas,
      eliminarNotificacion,
      eliminarTodasNotificaciones,
      agregarNotificacion,
      configurarNivelMinimo,
      setAutoActivo,
      filtrar,
      generarNotifAutomaticas,
    }}>
      {children}
    </NotificacionesContext.Provider>
  );
}

export function useNotificaciones() {
  const ctx = useContext(NotificacionesContext);
  if (!ctx) throw new Error("useNotificaciones debe usarse dentro de <NotificacionesProvider>");
  return ctx;
}
