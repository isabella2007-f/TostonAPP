import { useCallback, useEffect, useState } from "react";
import { formatCOP } from "../../../utils/formato";
import {
  Search, ChevronRight, Plus, Pencil, Trash2, Eye, MapPin, Building2, Layers,
  Banknote, RefreshCw,
} from "lucide-react";
import { usePrivilegios } from "../../../context/PrivilegiosContext";
import {
  getResumen, getDepartamentos, getCiudades, getBarrios, getBarrio,
  cambiarEstadoDepartamento, cambiarEstadoCiudad, cambiarEstadoBarrio,
  accionMasivaEstado, eliminarBarrio,
} from "../../../services/ubicacionesService";
import ModalBarrio from "./ModalBarrio";
import ModalConfirmar from "./ModalConfirmar";
import DetalleBarrio from "./DetalleBarrio";

const fmt = formatCOP;

const PER_PAGE = 10;
const PER_PAGE_DEP = 8;   // departamentos por página en la vista de árbol
const PER_PAGE_CIU = 8;   // ciudades por página dentro de un departamento

/** Pager compacto reutilizable (‹ Página X de Y ›). */
function Pager({ pagina, totalPags, onPagina, className = "ub-pager", extra }) {
  if (totalPags <= 1) return null;
  return (
    <div className={className}>
      <button disabled={pagina <= 1} onClick={() => onPagina(pagina - 1)}>‹</button>
      <span>Página {pagina} de {totalPags}{extra ? ` · ${extra}` : ""}</span>
      <button disabled={pagina >= totalPags} onClick={() => onPagina(pagina + 1)}>›</button>
    </div>
  );
}

/** Tira de tarjetas de resumen del catálogo. Se recarga con `refreshKey`. */
function ResumenStats({ refreshKey }) {
  const [r, setR] = useState(null);

  useEffect(() => {
    getResumen().then(setR).catch(() => setR(null));
  }, [refreshKey]);

  if (!r) return null;

  const cards = [
    { icon: <Layers size={19} />, mod: "dep", num: r.departamentos,
      label: "Departamentos", hint: `${r.departamentos_activos} activos` },
    { icon: <Building2 size={19} />, mod: "ciu", num: r.ciudades,
      label: "Ciudades / municipios" },
    { icon: <MapPin size={19} />, mod: "bar", num: r.barrios,
      label: "Barrios", hint: `${r.barrios_con_cobertura} con cobertura` },
    { icon: <Banknote size={19} />, mod: "pre", num: fmt(r.precio_promedio),
      label: "Domicilio promedio",
      hint: r.precio_min !== r.precio_max ? `${fmt(r.precio_min)} – ${fmt(r.precio_max)}` : null },
  ];

  return (
    <div className="ub-stats">
      {cards.map((c) => (
        <div className="ub-stat" key={c.label}>
          <div className={`ub-stat__icon ub-stat__icon--${c.mod}`}>{c.icon}</div>
          <div style={{ minWidth: 0 }}>
            <div className="ub-stat__num">{c.num}</div>
            <div className="ub-stat__label">{c.label}</div>
            {c.hint && <div className="ub-stat__hint">{c.hint}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

function Toggle({ on, disabled, onClick, title }) {
  return (
    <button
      type="button"
      className={`ub-toggle${on ? " ub-toggle--on" : ""}`}
      disabled={disabled}
      title={title}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
    />
  );
}

/** Fila de un barrio en el listado (accordion o resultados planos). */
function BarrioRow({ b, perms, onEstado, onEditar, onEliminar, onDetalle }) {
  return (
    <div className="ub-node">
      <div className="ub-node__row ub-node__row--barrio">
        <MapPin size={13} style={{ color: "#9e9e9e", flexShrink: 0 }} />
        <span className="ub-node__name">
          {b.Nombre}
          {b.ciudad && <span className="ub-muted"> · {b.ciudad}</span>}
          {"  "}
          <span className="ub-price">{fmt(b.Precio)}</span>
        </span>
        <span className={`ub-badge ub-badge--${b.Es_Base ? "base" : "creado"}`}>
          {b.Es_Base ? "Base" : "Creado"}
        </span>
        <span className={`ub-badge ub-badge--${b.estado_efectivo ? "activo" : "inactivo"}`}>
          {b.estado_efectivo ? "Disponible" : "No disponible"}
        </span>
        {!b.estado_efectivo && b.motivo_inactivo && (
          <span className="ub-motivo">{b.motivo_inactivo}</span>
        )}
        <span className="ub-node__actions">
          {perms.cambiarEstado && (
            <Toggle
              on={b.Estado === 1}
              onClick={() => onEstado(b, b.Estado === 1 ? 2 : 1)}
              title={b.Estado === 1 ? "Desactivar barrio" : "Activar barrio"}
            />
          )}
          {perms.ver && (
            <button className="ub-icon-btn" title="Ver detalle" onClick={() => onDetalle(b)}>
              <Eye size={13} />
            </button>
          )}
          {perms.editar && (
            <button className="ub-icon-btn" title="Editar" onClick={() => onEditar(b)}>
              <Pencil size={13} />
            </button>
          )}
          {perms.eliminar && !b.Es_Base && (
            <button className="ub-icon-btn ub-icon-btn--danger" title="Eliminar" onClick={() => onEliminar(b)}>
              <Trash2 size={13} />
            </button>
          )}
        </span>
      </div>
    </div>
  );
}

/** Barrios de una ciudad, paginados server-side. */
function BarriosDeCiudad({ idCiudad, perms, refreshKey, handlers }) {
  const [data, setData] = useState({ barrios: [], total: 0 });
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    setCargando(true);
    getBarrios({ idCiudad, pagina, porPagina: PER_PAGE })
      .then(setData)
      .catch(() => setData({ barrios: [], total: 0 }))
      .finally(() => setCargando(false));
  }, [idCiudad, pagina, refreshKey]);

  const totalPags = Math.max(1, Math.ceil(data.total / PER_PAGE));

  if (cargando) return <div className="ub-loading">Cargando barrios…</div>;
  if (data.total === 0) return <div className="ub-empty">Esta ciudad no tiene barrios registrados.</div>;

  return (
    <>
      {data.barrios.map((b) => (
        <BarrioRow key={b.ID_Barrio} b={b} perms={perms} {...handlers} />
      ))}
      {totalPags > 1 && (
        <div className="ub-pager">
          <button disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>‹</button>
          <span>Página {pagina} de {totalPags}</span>
          <button disabled={pagina >= totalPags} onClick={() => setPagina((p) => p + 1)}>›</button>
        </div>
      )}
    </>
  );
}

export default function PestanaUbicaciones() {
  const { hasPrivilegio, isAdmin } = usePrivilegios();
  const perms = {
    ver: true,
    crear: isAdmin || hasPrivilegio("Ubicaciones_crear"),
    editar: isAdmin || hasPrivilegio("Ubicaciones_editar"),
    eliminar: isAdmin || hasPrivilegio("Ubicaciones_eliminar"),
    cambiarEstado: isAdmin || hasPrivilegio("Ubicaciones_cambiar_estado"),
  };

  const [departamentos, setDepartamentos] = useState([]);
  const [ciudadesPorDep, setCiudadesPorDep] = useState({});
  const [expandidoDep, setExpandidoDep] = useState({});
  const [expandidoCiu, setExpandidoCiu] = useState({});
  const [pagDep, setPagDep] = useState(1);          // página del nivel departamentos
  const [pagCiu, setPagCiu] = useState({});         // { [idDepartamento]: página }
  const [refreshKey, setRefreshKey] = useState(0);

  // Búsqueda / filtros → resultados planos
  const [texto, setTexto] = useState("");
  const [debText, setDebText] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("");
  const [filtroBase, setFiltroBase] = useState("");
  const [planos, setPlanos] = useState({ barrios: [], total: 0 });
  const [pagPlanos, setPagPlanos] = useState(1);

  const [modalBarrio, setModalBarrio] = useState(null);   // {} nuevo | barrio editar
  const [detalle, setDetalle] = useState(null);
  const [confirmar, setConfirmar] = useState(null);
  const [aviso, setAviso] = useState("");

  const modoBusqueda = !!debText || !!filtroEstado || !!filtroBase;

  useEffect(() => {
    getDepartamentos().then(setDepartamentos).catch(() => setDepartamentos([]));
  }, [refreshKey]);

  useEffect(() => {
    const t = setTimeout(() => { setDebText(texto.trim()); setPagPlanos(1); }, 350);
    return () => clearTimeout(t);
  }, [texto]);

  useEffect(() => {
    if (!modoBusqueda) return;
    getBarrios({
      texto: debText || null, estadoEfectivo: filtroEstado || null,
      esBase: filtroBase === "" ? null : filtroBase === "base",
      pagina: pagPlanos, porPagina: PER_PAGE,
    }).then(setPlanos).catch(() => setPlanos({ barrios: [], total: 0 }));
  }, [modoBusqueda, debText, filtroEstado, filtroBase, pagPlanos, refreshKey]);

  const toggleDep = async (dep) => {
    const abierto = !expandidoDep[dep.ID_Departamento];
    setExpandidoDep((s) => ({ ...s, [dep.ID_Departamento]: abierto }));
    if (abierto && !ciudadesPorDep[dep.ID_Departamento]) {
      const ciudades = await getCiudades(dep.ID_Departamento).catch(() => []);
      setCiudadesPorDep((s) => ({ ...s, [dep.ID_Departamento]: ciudades }));
    }
  };

  const refrescar = useCallback(() => setRefreshKey((k) => k + 1), []);

  const cambiarEstado = async (tipo, entidad, nuevo) => {
    try {
      if (tipo === "dep") await cambiarEstadoDepartamento(entidad.ID_Departamento, nuevo);
      if (tipo === "ciu") await cambiarEstadoCiudad(entidad.ID_Ciudad, nuevo);
      if (tipo === "bar") await cambiarEstadoBarrio(entidad.ID_Barrio, nuevo);
      // Invalidar cachés de ciudades para reflejar la cascada.
      setCiudadesPorDep({});
      refrescar();
    } catch (e) {
      setAviso(e?.message || "No se pudo cambiar el estado");
    }
  };

  const ejecutarMasiva = async ({ nivel, idPadre, estado }) => {
    try {
      const r = await accionMasivaEstado({ nivel, idPadre, estado });
      setConfirmar(null);
      setCiudadesPorDep({});
      refrescar();
      setAviso(`Listo: ${r.afectados} cambiados${r.omitidos ? `, ${r.omitidos} omitidos por padre inactivo` : ""}.`);
    } catch (e) {
      setAviso(e?.message || "No se pudo aplicar la acción masiva");
    }
  };

  const pedirEliminar = (b) => setConfirmar({
    titulo: "Eliminar barrio",
    mensaje: `¿Eliminar "${b.Nombre}"? Esta acción no se puede deshacer. Si algo lo referencia, se bloqueará y podrás desactivarlo en su lugar.`,
    peligro: true,
    confirmarLabel: "Eliminar",
    accion: async () => {
      try {
        await eliminarBarrio(b.ID_Barrio);
        setConfirmar(null);
        refrescar();
      } catch (e) {
        setConfirmar(null);
        setAviso(e?.message || "No se pudo eliminar");
      }
    },
  });

  const handlers = {
    onEstado: (b, nuevo) => cambiarEstado("bar", b, nuevo),
    onEditar: (b) => setModalBarrio(b),
    onEliminar: pedirEliminar,
    onDetalle: async (b) => {
      const full = await getBarrio(b.ID_Barrio).catch(() => b);
      setDetalle(full);
    },
  };

  const totalPagPlanos = Math.max(1, Math.ceil(planos.total / PER_PAGE));

  const depTotalPags = Math.max(1, Math.ceil(departamentos.length / PER_PAGE_DEP));
  const pagDepSafe = Math.min(pagDep, depTotalPags);
  const depSlice = departamentos.slice(
    (pagDepSafe - 1) * PER_PAGE_DEP, pagDepSafe * PER_PAGE_DEP,
  );

  return (
    <div>
      <ResumenStats refreshKey={refreshKey} />

      {aviso && (
        <div className="ub-info" style={{ marginBottom: 12 }}>
          <span>{aviso}</span>
          <button className="ub-modal__x" style={{ marginLeft: "auto" }} onClick={() => setAviso("")}>✕</button>
        </div>
      )}

      <div className="ub-toolbar">
        <div className="ub-search">
          <Search size={15} className="ub-search__icon" />
          <input
            placeholder="Buscar barrio, ciudad o departamento…"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
        </div>
        <button className="ub-icon-btn" onClick={refrescar} data-tooltip="Actualizar ubicaciones">
          <RefreshCw size={14} />
        </button>
        <select className="ub-select" value={filtroEstado}
          onChange={(e) => { setFiltroEstado(e.target.value); setPagPlanos(1); }}>
          <option value="">Estado efectivo: todos</option>
          <option value="activo">Disponibles</option>
          <option value="inactivo">No disponibles</option>
        </select>
        <select className="ub-select" value={filtroBase}
          onChange={(e) => { setFiltroBase(e.target.value); setPagPlanos(1); }}>
          <option value="">Origen: todos</option>
          <option value="base">Base (quemado)</option>
          <option value="creado">Creado</option>
        </select>
        {perms.crear && (
          <button className="ub-btn ub-btn--primary" onClick={() => setModalBarrio({})}>
            <Plus size={14} /> Crear barrio
          </button>
        )}
        {perms.cambiarEstado && (
          <select className="ub-select" value=""
            onChange={(e) => {
              const v = e.target.value;
              if (!v) return;
              const [, estado] = v.split(":");
              setConfirmar({
                titulo: "Acción masiva de estado",
                mensaje: estado === "1"
                  ? "Se activarán todos los departamentos (respetando la regla de padre activo en los niveles inferiores). ¿Continuar?"
                  : "Se desactivarán TODOS los departamentos. Ningún barrio quedará disponible para domicilio. ¿Continuar?",
                peligro: estado === "2",
                confirmarLabel: estado === "1" ? "Activar todos" : "Desactivar todos",
                accion: () => ejecutarMasiva({ nivel: "departamentos", idPadre: null, estado: Number(estado) }),
              });
              e.target.value = "";
            }}>
            <option value="">Acciones masivas…</option>
            <option value="departamentos:2">Desactivar todos los departamentos</option>
            <option value="departamentos:1">Activar todos los departamentos</option>
          </select>
        )}
      </div>

      {modoBusqueda ? (
        <div className="ub-tree">
          {planos.total === 0
            ? <div className="ub-empty">Sin resultados.</div>
            : planos.barrios.map((b) => (
              <BarrioRow key={b.ID_Barrio} b={b} perms={perms} {...handlers} />
            ))}
        </div>
      ) : (
        <div className="ub-tree">
          {departamentos.length === 0 && <div className="ub-loading">Cargando…</div>}
          {depSlice.map((dep) => {
            const abierto = expandidoDep[dep.ID_Departamento];
            const ciudades = ciudadesPorDep[dep.ID_Departamento] || [];
            const ciuPag = Math.min(pagCiu[dep.ID_Departamento] || 1,
              Math.max(1, Math.ceil(ciudades.length / PER_PAGE_CIU)));
            const ciuTotalPags = Math.max(1, Math.ceil(ciudades.length / PER_PAGE_CIU));
            const ciuSlice = ciudades.slice((ciuPag - 1) * PER_PAGE_CIU, ciuPag * PER_PAGE_CIU);
            return (
              <div className="ub-node" key={dep.ID_Departamento}>
                <div className="ub-node__row ub-node__row--depto" onClick={() => toggleDep(dep)}>
                  <ChevronRight size={15} className={`ub-node__caret${abierto ? " ub-node__caret--open" : ""}`} />
                  <Layers size={13} style={{ color: "#546e7a", flexShrink: 0 }} />
                  <span className="ub-node__name">{dep.Nombre}</span>
                  <span className={`ub-badge ub-badge--${dep.Estado === 1 ? "activo" : "inactivo"}`}>
                    {dep.Estado === 1 ? "Activo" : "Inactivo"}
                  </span>
                  <span className="ub-node__actions">
                    {perms.cambiarEstado && (
                      <>
                        <Toggle on={dep.Estado === 1}
                          onClick={() => cambiarEstado("dep", dep, dep.Estado === 1 ? 2 : 1)}
                          title={dep.Estado === 1 ? "Desactivar departamento" : "Activar departamento"} />
                        <button className="ub-icon-btn" title="Desactivar todas las ciudades"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmar({
                              titulo: `Ciudades de ${dep.Nombre}`,
                              mensaje: `Se desactivarán todas las ciudades de ${dep.Nombre}. ¿Continuar?`,
                              peligro: true, confirmarLabel: "Desactivar",
                              accion: () => ejecutarMasiva({ nivel: "ciudades", idPadre: dep.ID_Departamento, estado: 2 }),
                            });
                          }}>
                          <Building2 size={13} />
                        </button>
                      </>
                    )}
                  </span>
                </div>

                {abierto && (
                  <div className="ub-node__children">
                    {ciudades.length === 0 && <div className="ub-loading">Cargando ciudades…</div>}
                    {ciuSlice.map((ciu) => {
                      const ciuAbierto = expandidoCiu[ciu.ID_Ciudad];
                      return (
                        <div className="ub-node" key={ciu.ID_Ciudad}>
                          <div className="ub-node__row ub-node__row--ciudad"
                            onClick={() => setExpandidoCiu((s) => ({ ...s, [ciu.ID_Ciudad]: !s[ciu.ID_Ciudad] }))}>
                            <ChevronRight size={14} className={`ub-node__caret${ciuAbierto ? " ub-node__caret--open" : ""}`} />
                            <Building2 size={12} style={{ color: "#78909c", flexShrink: 0 }} />
                            <span className="ub-node__name">{ciu.Nombre}</span>
                            <span className={`ub-badge ub-badge--${ciu.estado_efectivo ? "activo" : "inactivo"}`}>
                              {ciu.estado_efectivo ? "Activa" : "Inactiva"}
                            </span>
                            {!ciu.estado_efectivo && ciu.motivo_inactivo && (
                              <span className="ub-motivo">{ciu.motivo_inactivo}</span>
                            )}
                            <span className="ub-node__actions">
                              {perms.cambiarEstado && (
                                <>
                                  <Toggle on={ciu.Estado === 1}
                                    onClick={() => cambiarEstado("ciu", ciu, ciu.Estado === 1 ? 2 : 1)}
                                    title={ciu.Estado === 1 ? "Desactivar ciudad" : "Activar ciudad"} />
                                  <button className="ub-icon-btn" title="Desactivar todos los barrios"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setConfirmar({
                                        titulo: `Barrios de ${ciu.Nombre}`,
                                        mensaje: `Se desactivarán todos los barrios de ${ciu.Nombre}. ¿Continuar?`,
                                        peligro: true, confirmarLabel: "Desactivar",
                                        accion: () => ejecutarMasiva({ nivel: "barrios", idPadre: ciu.ID_Ciudad, estado: 2 }),
                                      });
                                    }}>
                                    <MapPin size={13} />
                                  </button>
                                </>
                              )}
                            </span>
                          </div>
                          {ciuAbierto && (
                            <div className="ub-node__children">
                              <BarriosDeCiudad idCiudad={ciu.ID_Ciudad} perms={perms}
                                refreshKey={refreshKey} handlers={handlers} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                    <Pager
                      className="ub-pager ub-pager--nested"
                      pagina={ciuPag}
                      totalPags={ciuTotalPags}
                      extra={`${ciudades.length} ciudades`}
                      onPagina={(p) => setPagCiu((s) => ({ ...s, [dep.ID_Departamento]: p }))}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {!modoBusqueda && (
        <Pager
          pagina={pagDepSafe}
          totalPags={depTotalPags}
          extra={`${departamentos.length} departamentos`}
          onPagina={setPagDep}
        />
      )}

      {modoBusqueda && totalPagPlanos > 1 && (
        <div className="ub-pager">
          <button disabled={pagPlanos <= 1} onClick={() => setPagPlanos((p) => p - 1)}>‹</button>
          <span>Página {pagPlanos} de {totalPagPlanos} · {planos.total} barrios</span>
          <button disabled={pagPlanos >= totalPagPlanos} onClick={() => setPagPlanos((p) => p + 1)}>›</button>
        </div>
      )}

      {modalBarrio && (
        <ModalBarrio
          barrio={modalBarrio.ID_Barrio ? modalBarrio : null}
          onCerrar={() => setModalBarrio(null)}
          onGuardado={(res) => {
            setModalBarrio(null);
            if (res?.sinCambios) { setAviso("No se hicieron cambios."); return; }
            setCiudadesPorDep({});
            refrescar();
          }}
        />
      )}

      {detalle && (
        <DetalleBarrio barrio={detalle} onCerrar={() => setDetalle(null)} />
      )}

      {confirmar && (
        <ModalConfirmar
          titulo={confirmar.titulo}
          mensaje={confirmar.mensaje}
          peligro={confirmar.peligro}
          confirmarLabel={confirmar.confirmarLabel}
          onConfirmar={confirmar.accion}
          onCancelar={() => setConfirmar(null)}
        />
      )}
    </div>
  );
}
