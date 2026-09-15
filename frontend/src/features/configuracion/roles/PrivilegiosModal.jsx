/**
 * PrivilegiosModal — navegación dos niveles SIN scroll
 *
 * Acciones personalizadas por módulo:
 * - Landing Page:         Ver, Editar
 * - Compras:              Ver, Crear, Editar, Anular
 * - Insumos:              Ver, Crear, Editar, Eliminar, Generar Salida
 * - Cat. Productos:       Ver, Crear, Editar, Eliminar, Generar Salida
 * - Gestión Prod.:        Ver, Crear, Editar, Eliminar, Generar Salida
 * - Órdenes Producción:   Ver, Crear, Editar, Cancelar
 * - Gestión Ventas:       Ver, Crear, Editar, Eliminar
 * - Devoluciones:         Ver, Crear, Editar, Aprobar, Desaprobar
 * - Domicilios:           Ver, Ver Detalles, Cambiar Estado
 * - Liquidaciones:        Ver, Crear, Editar, Eliminar, Anular
 * - Gestión Salidas:      Ver, Crear, Editar, Eliminar  (grupo Configuración)
 */

import { useState } from "react";
import { X, AlertTriangle, Check, Lock, Eye, Plus, PenLine, Trash2, Ban, Upload, Search, RefreshCw, CheckCircle2, XCircle, Globe, Settings, Shield, Users, Package, FolderOpen, Truck, ClipboardList, Factory, Banknote, ShoppingCart, CornerUpLeft, Bike, BarChart2, MapPin } from "lucide-react";
import { createPortal } from "react-dom";

// ── Catálogo completo de acciones posibles ──────────────────────────────────
const TODAS_ACCIONES = {
  ver:            { key: "ver",            label: "Ver",            Icon: Eye,          color: "#2e7d32", bg: "#e8f5e9", border: "#a5d6a7" },
  crear:          { key: "crear",          label: "Crear",          Icon: Plus,         color: "#1565c0", bg: "#e3f2fd", border: "#90caf9" },
  editar:         { key: "editar",         label: "Editar",         Icon: PenLine,      color: "#e65100", bg: "#fff3e0", border: "#ffcc80" },
  eliminar:       { key: "eliminar",       label: "Eliminar",       Icon: Trash2,       color: "#c62828", bg: "#ffebee", border: "#ef9a9a" },
  anular:         { key: "anular",         label: "Anular",         Icon: Ban,          color: "#6a1b9a", bg: "#f3e5f5", border: "#ce93d8" },
  generar_salida: { key: "generar_salida", label: "Generar Salida", Icon: Upload,       color: "#00695c", bg: "#e0f2f1", border: "#80cbc4" },
  ver_detalles:   { key: "ver_detalles",   label: "Ver Detalles",   Icon: Search,       color: "#1565c0", bg: "#e3f2fd", border: "#90caf9" },
  cambiar_estado: { key: "cambiar_estado", label: "Cambiar Estado", Icon: RefreshCw,    color: "#f57f17", bg: "#fff8e1", border: "#ffe082" },
  cambiar_rol:    { key: "cambiar_rol",    label: "Cambiar Rol",    Icon: Shield,       color: "#6a1b9a", bg: "#f3e5f5", border: "#ce93d8" },
  aprobar:        { key: "aprobar",        label: "Aprobar",        Icon: CheckCircle2, color: "#1b5e20", bg: "#e8f5e9", border: "#81c784" },
  desaprobar:     { key: "desaprobar",     label: "Desaprobar",     Icon: XCircle,      color: "#b71c1c", bg: "#ffebee", border: "#ef5350" },
  cancelar:       { key: "cancelar",       label: "Cancelar",       Icon: X,            color: "#4e342e", bg: "#efebe9", border: "#bcaaa4" },
};

const STD = ["ver", "crear", "editar", "eliminar", "cambiar_estado"];

const GRUPOS_MODULOS = [
    {
    grupo: "Sitio web",
    Icon: Globe,
    modulos: [
      { key: "LandingPage",       label: "Landing Page",      Icon: Globe,        acciones: ["editar"] },
    ],
  },
  {
    grupo: "Configuración",
    Icon: Settings,
    modulos: [
      { key: "Dashboard",       label: "Dashboard",       Icon: BarChart2,     acciones: ["ver"] },
      { key: "Roles",           label: "Roles",           Icon: Shield,        acciones: STD },
      { key: "Usuarios",        label: "Usuarios",        Icon: Users,         acciones: [...STD, "cambiar_rol"] },
      { key: "Ubicaciones",     label: "Ubicaciones",     Icon: MapPin,        acciones: STD },
      { key: "GestionSalidas",  label: "Gestión Salidas", Icon: Upload,        acciones: ["ver", "crear", "editar", "eliminar"] },
    ],
  },
  {
    grupo: "Compras",
    Icon: Package,
    modulos: [
      { key: "CategoriaInsumos", label: "Cat. Insumos",  Icon: FolderOpen,    acciones: STD },
      { key: "Insumos",          label: "Insumos",       Icon: Package,       acciones: ["ver", "crear", "editar", "eliminar", "cambiar_estado", "generar_salida"] },
      { key: "Proveedores",      label: "Proveedores",   Icon: Truck,         acciones: STD },
      // FIX: "cambiar estado" (con espacio) → "cambiar_estado" (con guión bajo)
      { key: "Compras",          label: "Compras",       Icon: ClipboardList, acciones: ["ver", "crear", "editar", "cambiar_estado", "anular"] },
    ],
  },
  {
    grupo: "Producción",
    Icon: Factory,
    modulos: [
      { key: "CategoriaProductos", label: "Cat. Productos", Icon: Package,       acciones: ["ver", "crear", "editar", "eliminar", "cambiar_estado"] },
      { key: "GestionProductos",   label: "Gestión Prod.",  Icon: ClipboardList, acciones: ["ver", "crear", "editar", "eliminar", "cambiar_estado", "generar_salida"] },
      { key: "OrdenesProduccion",  label: "Órdenes Prod.",  Icon: Factory,       acciones: ["ver", "crear", "editar", "cambiar_estado", "anular"] },
    ],
  },
  {
    grupo: "Ventas",
    Icon: Banknote,
    modulos: [
      { key: "Pedidos",       label: "Pedidos",        Icon: ShoppingCart,  acciones: ["ver", "crear", "editar", "cancelar", "cambiar_estado"] },
      { key: "Devoluciones",  label: "Devoluciones",   Icon: CornerUpLeft,  acciones: ["ver", "crear", "editar", "aprobar", "desaprobar"] },
      { key: "Domicilios",    label: "Domicilios",     Icon: Bike,          acciones: ["ver", "ver_detalles", "crear", "editar", "cambiar_estado"] },
    ],
  },
];

const MODULOS = GRUPOS_MODULOS.flatMap(g => g.modulos);
const TOTAL_PRIVILEGIOS = MODULOS.reduce((acc, m) => acc + m.acciones.length, 0);

export function buildAdminPrivilegios() {
  const allClaves = MODULOS.flatMap(m => m.acciones.map(a => `${m.key}_${a}`));
  return buildPrivilegios(allClaves);
}

export function buildPrivilegios(overrides = []) {
  const map = {};

  overrides.forEach(p => {
    if (typeof p === "string") {
      map[p] = true;
    } else if (p && p.modulo) {
      map[p.id] = p.estado;
    } else if (p && (p.Clave || p.clave)) {
      // API returns {ID_Permiso, Clave, ...}
      map[p.Clave || p.clave] = true;
    }
  });

  return MODULOS.flatMap(m =>
    (m.acciones || [])
      .filter(aKey => TODAS_ACCIONES[aKey])
      .map(aKey => {
        const a  = TODAS_ACCIONES[aKey];
        const id = `${m.key}_${aKey}`;
        return {
          id,
          modulo: m.key,
          accion: aKey,
          nombre: `${a.label} ${m.label.toLowerCase()}`,
          estado: map[id] ?? false,
        };
      })
  );
}

function tieneTodosLosPrivilegios(privilegios) {
  return privilegios.filter(p => p.estado).length >= TOTAL_PRIVILEGIOS;
}

const S = {
  overlay: {
    position: "fixed", inset: 0,
    background: "rgba(0,0,0,0.55)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 30000,
  },
  box: {
    background: "#fff",
    borderRadius: 14,
    boxShadow: "0 8px 40px rgba(0,0,0,0.22)",
    display: "flex",
    flexDirection: "column",
    width: "min(740px, 96vw)",
    maxHeight: "90vh",
    overflow: "hidden",
  },
  header: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "16px 20px 12px",
    borderBottom: "1px solid #f0f0f0",
    flexShrink: 0,
  },
  gruposBar: {
    display: "flex",
    gap: 6,
    padding: "10px 20px 0",
    flexShrink: 0,
    flexWrap: "wrap",
  },
  grupoChip: (activo) => ({
    display: "flex", alignItems: "center", gap: 5,
    padding: "5px 13px",
    borderRadius: 20,
    border: activo ? "1.5px solid #4caf50" : "1.5px solid #e0e0e0",
    background: activo ? "#f1f8e9" : "#fafafa",
    color: activo ? "#2e7d32" : "#757575",
    fontSize: 13,
    fontWeight: activo ? 700 : 400,
    cursor: "pointer",
    transition: "all 0.15s",
    whiteSpace: "nowrap",
  }),
  modulosBar: {
    display: "flex",
    gap: 4,
    padding: "8px 20px 0",
    flexShrink: 0,
    flexWrap: "wrap",
  },
  moduloTab: (activo) => ({
    display: "flex", alignItems: "center", gap: 5,
    padding: "6px 12px",
    borderRadius: 8,
    border: "none",
    borderBottom: activo ? "2px solid #4caf50" : "2px solid transparent",
    background: activo ? "#fff" : "transparent",
    color: activo ? "#212121" : "#9e9e9e",
    fontSize: 12,
    fontWeight: activo ? 600 : 400,
    cursor: "pointer",
    transition: "all 0.12s",
    whiteSpace: "nowrap",
  }),
  panelBody: {
    flex: 1,
    padding: "16px 20px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    overflow: "auto",
  },
  accionesGrid: (n) => ({
    display: "grid",
    gridTemplateColumns: `repeat(${Math.min(n, 4)}, 1fr)`,
    gap: 10,
  }),
  accionCard: (on, accion) => ({
    display: "flex", flexDirection: "column", alignItems: "center",
    gap: 6,
    padding: "14px 8px",
    borderRadius: 10,
    border: `1.5px solid ${on ? accion.border : "#e8e8e8"}`,
    background: on ? accion.bg : "#fafafa",
    cursor: "pointer",
    transition: "all 0.15s",
    userSelect: "none",
  }),
  accionCheck: (on, accion) => ({
    width: 18, height: 18,
    borderRadius: 4,
    border: `1.5px solid ${on ? accion.color : "#ccc"}`,
    background: on ? accion.color : "transparent",
    display: "flex", alignItems: "center", justifyContent: "center",
  }),
  footer: {
    display: "flex", justifyContent: "flex-end", gap: 10,
    padding: "12px 20px",
    borderTop: "1px solid #f0f0f0",
    flexShrink: 0,
  },
};

// ¿el módulo tiene alguna acción ≠ "ver" activa?
const tieneOtraAccion = (lista, moduloKey) =>
  lista.some(p => p.modulo === moduloKey && p.accion !== "ver" && p.estado);

export default function PrivilegiosModal({
  privilegios,
  esAdmin    = false,
  isView     = false,
  misClaves  = null,   // Set de claves que posee el usuario actual; null = sin límite
  bypass     = false,  // el usuario actual es Admin → sin anti-escalación
  onChange,
  onClose,
}) {
  const normalizar = (raw) => {
    if (esAdmin) {
      // Admin tiene todos los permisos por bypass — mostrarlos todos activos
      const allClaves = MODULOS.flatMap(m => m.acciones.map(a => `${m.key}_${a}`));
      return buildPrivilegios(allClaves);
    }
    return raw.length > 0 && raw[0].modulo ? raw : buildPrivilegios(raw);
  };

  const [local, setLocal]   = useState(() => normalizar(privilegios));
  // Por módulo: ¿el "ver" quedó activo por elección directa del usuario (clic
  // sobre el propio "ver"), no como efecto de marcar otra acción? Si es así,
  // "ver" permanece aunque se apaguen las demás acciones del módulo.
  const [verExplicito, setVerExplicito] = useState(() => {
    const init = {};
    MODULOS.forEach(m => {
      const items = local.filter(p => p.modulo === m.key);
      const ver   = items.find(p => p.accion === "ver");
      if (ver?.estado && !tieneOtraAccion(local, m.key)) init[m.key] = true;
    });
    return init;
  });
  const [grupo, setGrupo]   = useState(GRUPOS_MODULOS[0].grupo);
  const [modKey, setModKey] = useState(GRUPOS_MODULOS[0].modulos[0].key);

  // Anti-escalación: el usuario no puede tocar acciones que él mismo no posee.
  const puedeEditar = (p) => bypass || !misClaves || misClaves.has(p.id);
  // "ver" bloqueado: hay otra acción del módulo activa (no se puede desmarcar).
  const verBloqueado = (moduloKey) => tieneOtraAccion(local, moduloKey);

  const handleGrupo = (g) => {
    setGrupo(g);
    const primerMod = GRUPOS_MODULOS.find(gr => gr.grupo === g)?.modulos[0];
    if (primerMod) setModKey(primerMod.key);
  };

  const toggle = (id) => {
    if (isView) return;
    const target = local.find(p => p.id === id);
    if (!target || !puedeEditar(target)) return;

    const mod = target.modulo;

    if (target.accion === "ver") {
      // Bloqueado mientras haya otra acción del módulo marcada.
      if (verBloqueado(mod)) return;
      const nuevo = !target.estado;
      setVerExplicito(v => ({ ...v, [mod]: nuevo }));
      setLocal(prev => prev.map(p => p.id === id ? { ...p, estado: nuevo } : p));
      return;
    }

    const nuevo = !target.estado;
    setLocal(prev => {
      const next = prev.map(p => p.id === id ? { ...p, estado: nuevo } : p);
      const ver = next.find(p => p.modulo === mod && p.accion === "ver");
      if (!ver) return next;
      if (nuevo) {
        // Marcar cualquier acción ≠ "ver" fuerza el "ver" del módulo.
        return next.map(p => p === ver ? { ...p, estado: true } : p);
      }
      // Se desmarcó la última acción ≠ "ver": el "ver" se apaga salvo que el
      // usuario lo hubiera marcado explícitamente.
      const quedanOtras = next.some(p => p.modulo === mod && p.accion !== "ver" && p.estado);
      if (!quedanOtras && !verExplicito[mod]) {
        return next.map(p => p === ver ? { ...p, estado: false } : p);
      }
      return next;
    });
  };

  const toggleAll = (moduloKey, valor) => {
    if (isView) return;
    setLocal(prev => prev.map(p =>
      p.modulo === moduloKey && puedeEditar(p) ? { ...p, estado: valor } : p
    ));
    if (!valor) setVerExplicito(v => ({ ...v, [moduloKey]: false }));
  };

  const grupoActual = GRUPOS_MODULOS.find(g => g.grupo === grupo);
  const modMeta     = MODULOS.find(m => m.key === modKey);
  const modItems    = local.filter(p => p.modulo === modKey);

  // FIX: .filter(Boolean) elimina cualquier undefined causado por typos en las claves de acciones
  const accionesMod = (modMeta?.acciones ?? [])
    .map(k => TODAS_ACCIONES[k])
    .filter(Boolean);

  const modActivos  = modItems.filter(p => p.estado).length;
  const todosOn     = modActivos === accionesMod.length && accionesMod.length > 0;

  const totalActivos = local.filter(p => p.estado).length;
  const advertencia  = !isView && !esAdmin && tieneTodosLosPrivilegios(local);

  const activosPorGrupo = (g) => {
    const modulos = GRUPOS_MODULOS.find(gr => gr.grupo === g)?.modulos || [];
    return local.filter(p => modulos.some(m => m.key === p.modulo) && p.estado).length;
  };

  const activosPorModulo = (mKey) => {
    const mod   = MODULOS.find(m => m.key === mKey);
    const items = local.filter(p => p.modulo === mKey);
    return { activos: items.filter(p => p.estado).length, total: mod?.acciones.length ?? 0 };
  };

  return createPortal(
    <div style={S.overlay} onClick={onClose}>
      <div style={S.box} onClick={e => e.stopPropagation()}>

        {/* Cabecera */}
        <div style={S.header}>
          <div>
            <p style={{ margin: 0, fontSize: 10, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Gestión de privilegios
            </p>
            <h2 style={{ margin: "2px 0 0", fontSize: 17, fontWeight: 700, color: "#212121" }}>
              Privilegios del rol
            </h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 12, background: "#f5f5f5", color: "#757575", border: "1px solid #e0e0e0" }}>
              {totalActivos}/{local.length} activos
            </span>
            <button onClick={onClose} style={{ background: "none", border: "none", color: "#9e9e9e", cursor: "pointer", display:"flex", alignItems:"center", justifyContent:"center" }}><X size={18} /></button>
          </div>
        </div>

        {/* Advertencia todos los privilegios */}
        {advertencia && (
          <div style={{ margin: "8px 20px 0", padding: "8px 12px", borderRadius: 8, background: "#fff8e1", border: "1px solid #ffe082", color: "#f57f17", fontSize: 12, display: "flex", gap: 7, alignItems: "center", flexShrink: 0 }}>
            <AlertTriangle size={13} /> <span>Este rol no es administrador pero tiene <strong>todos los privilegios</strong> activos.</span>
          </div>
        )}

        {/* Nivel 1: chips de grupo */}
        <div style={S.gruposBar}>
          {GRUPOS_MODULOS.map(g => {
            const activos  = activosPorGrupo(g.grupo);
            const esActivo = grupo === g.grupo;
            return (
              <button key={g.grupo} style={S.grupoChip(esActivo)} onClick={() => handleGrupo(g.grupo)}>
                <g.Icon size={14} />
                <span>{g.grupo}</span>
                {activos > 0 && (
                  <span style={{ fontSize: 10, fontWeight: 700, background: esActivo ? "#c8e6c9" : "#eeeeee", color: esActivo ? "#2e7d32" : "#9e9e9e", borderRadius: 10, padding: "0 5px", marginLeft: 2 }}>
                    {activos}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Nivel 2: tabs de módulo */}
        <div style={{ ...S.modulosBar, borderBottom: "1px solid #f0f0f0", paddingBottom: 0 }}>
          {grupoActual?.modulos.map(m => {
            const { activos, total } = activosPorModulo(m.key);
            const esActivo = modKey === m.key;
            return (
              <button key={m.key} style={S.moduloTab(esActivo)} onClick={() => setModKey(m.key)}>
                <m.Icon size={13} />
                <span>{m.label}</span>
                {activos > 0 && (
                  <span style={{ fontSize: 10, fontWeight: 700, background: activos === total ? "#e8f5e9" : "#fff3e0", color: activos === total ? "#2e7d32" : "#e65100", border: `1px solid ${activos === total ? "#c8e6c9" : "#ffcc80"}`, borderRadius: 10, padding: "0 5px" }}>
                    {activos}/{total}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Panel de acciones */}
        <div style={S.panelBody}>

          {/* Sub-cabecera del módulo */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ lineHeight: 1, background: "#f5f5f5", borderRadius: 8, padding: "5px 7px", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                {modMeta && <modMeta.Icon size={22} />}
              </span>
              <div>
                <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#212121" }}>{modMeta?.label}</p>
                <p style={{ margin: 0, fontSize: 11, color: "#9e9e9e" }}>
                  {isView
                    ? `${modActivos} acciones habilitadas`
                    : `${modActivos} de ${accionesMod.length} acciones habilitadas`}
                </p>
              </div>
            </div>
            {!isView && accionesMod.length > 0 && (
              <button
                onClick={() => toggleAll(modKey, !todosOn)}
                style={{ padding: "5px 12px", borderRadius: 7, border: todosOn ? "1px solid #ef9a9a" : "1px solid #a5d6a7", background: todosOn ? "#ffebee" : "#e8f5e9", color: todosOn ? "#c62828" : "#2e7d32", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
              >
                {todosOn ? "Desactivar todo" : "Activar todo"}
              </button>
            )}
          </div>

          {/* Tarjetas de acciones */}
          <div style={S.accionesGrid(accionesMod.length)}>
            {accionesMod
              .filter(a => !isView || modItems.find(p => p.accion === a.key)?.estado)
              .map(accion => {
                const permiso = modItems.find(p => p.accion === accion.key);
                if (!permiso) return null;
                const on        = permiso.estado;
                const noPosee   = !isView && !bypass && misClaves && !misClaves.has(permiso.id);
                const verLock   = !isView && accion.key === "ver" && verBloqueado(modKey);
                const bloqueado = noPosee || verLock;
                const tip = noPosee
                  ? "No puedes asignar un permiso que tú no tienes"
                  : verLock
                  ? "\"Ver\" es obligatorio mientras haya otras acciones marcadas"
                  : undefined;
                return (
                  <div
                    key={accion.key}
                    data-tooltip={tip}
                    style={{
                      ...S.accionCard(on, accion),
                      cursor: isView || bloqueado ? "default" : "pointer",
                      opacity: noPosee ? 0.4 : 1,
                    }}
                    onClick={() => { if (!bloqueado) toggle(permiso.id); }}
                  >
                    <div style={{ width: 44, height: 44, borderRadius: 10, background: on ? accion.bg : "#f5f5f5", border: `1.5px solid ${on ? accion.border : "#e8e8e8"}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <accion.Icon size={22} />
                    </div>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: on ? accion.color : "#9e9e9e" }}>
                      {accion.label}
                    </p>
                    <div style={S.accionCheck(on, accion)}>
                      {on && !verLock && <Check size={10} color="#fff" strokeWidth={3} />}
                      {verLock && <Lock size={10} color="#fff" strokeWidth={3} />}
                      {noPosee && !on && <Lock size={10} color="#9e9e9e" strokeWidth={3} />}
                    </div>
                  </div>
                );
              })}

            {isView && accionesMod.filter(a => modItems.find(p => p.accion === a.key)?.estado).length === 0 && (
              <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: "28px 0", color: "#bdbdbd", fontSize: 13 }}>
                <Lock size={28} strokeWidth={1} style={{color:"#bdbdbd",marginBottom:6}} />
                Sin acciones habilitadas para este módulo
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={S.footer}>
          <button
            onClick={onClose}
            style={{ padding: "7px 18px", borderRadius: 8, border: "1px solid #e0e0e0", background: "#fff", color: "#555", fontSize: 13, cursor: "pointer" }}
          >
            {isView ? "Cerrar" : "Cancelar"}
          </button>
          {!isView && (
            <button
              onClick={() => { onChange(local); onClose(); }}
              style={{ padding: "7px 18px", borderRadius: 8, border: "none", background: "#4caf50", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              Aplicar privilegios
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}