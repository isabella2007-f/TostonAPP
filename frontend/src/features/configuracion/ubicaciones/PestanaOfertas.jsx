import { useEffect, useState } from "react";
import { Search, Plus, Pencil, Trash2, Eye, RefreshCw } from "lucide-react";
import { usePrivilegios } from "../../../context/PrivilegiosContext";
import { formatCOP } from "../../../utils/formato";
import {
  getOfertas, getOferta, cambiarEstadoOferta, eliminarOferta, DIAS_SEMANA,
} from "../../../services/ubicacionesService";
import ModalOferta from "./ModalOferta";
import ModalConfirmar from "./ModalConfirmar";
import DetalleOferta from "./DetalleOferta";

const fmt = formatCOP;

const PER_PAGE = 15;

const resumenDias = (o) => {
  const sem = (o.diasSemana || []).map((d) => DIAS_SEMANA.find((x) => x.valor === d)?.corto || d);
  const partes = [];
  if (sem.length) partes.push(sem.join(","));
  if ((o.diasMes || []).length) partes.push(`días ${o.diasMes.join(",")}`);
  return partes.join(" · ") || "—";
};

const resumenValor = (o) => {
  const p = [];
  if (o.montoPesos != null) p.push(fmt(o.montoPesos));
  if (o.porcentaje != null) p.push(`${o.porcentaje}%`);
  return p.join(" + ") || "—";
};

export default function PestanaOfertas() {
  const { hasPrivilegio, isAdmin } = usePrivilegios();
  const perms = {
    crear: isAdmin || hasPrivilegio("Ubicaciones_crear"),
    editar: isAdmin || hasPrivilegio("Ubicaciones_editar"),
    eliminar: isAdmin || hasPrivilegio("Ubicaciones_eliminar"),
    cambiarEstado: isAdmin || hasPrivilegio("Ubicaciones_cambiar_estado"),
  };

  const [data, setData] = useState({ ofertas: [], total: 0 });
  const [pagina, setPagina] = useState(1);
  const [texto, setTexto] = useState("");
  const [debText, setDebText] = useState("");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("");
  const [cargando, setCargando] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  const [modal, setModal] = useState(null);       // {} nuevo | oferta editar
  const [detalle, setDetalle] = useState(null);
  const [confirmar, setConfirmar] = useState(null);
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    const t = setTimeout(() => { setDebText(texto.trim()); setPagina(1); }, 350);
    return () => clearTimeout(t);
  }, [texto]);

  useEffect(() => {
    setCargando(true);
    getOfertas({
      pagina, porPagina: PER_PAGE, texto: debText || null,
      tipo: filtroTipo || null,
      estado: filtroEstado === "" ? null : Number(filtroEstado),
    })
      .then(setData)
      .catch(() => setData({ ofertas: [], total: 0 }))
      .finally(() => setCargando(false));
  }, [pagina, debText, filtroTipo, filtroEstado, refreshKey]);

  const refrescar = () => setRefreshKey((k) => k + 1);
  const totalPags = Math.max(1, Math.ceil(data.total / PER_PAGE));

  // Cambio de estado optimista: se pinta el toggle al instante y solo se
  // revierte esa fila si el backend falla — sin recargar toda la tabla.
  const toggleEstado = async (o) => {
    const nuevo = o.estado === 1 ? 2 : 1;
    setData((d) => ({
      ...d, ofertas: d.ofertas.map((x) => (x.id === o.id ? { ...x, estado: nuevo } : x)),
    }));
    try {
      await cambiarEstadoOferta(o.id, nuevo);
    } catch (e) {
      setData((d) => ({
        ...d, ofertas: d.ofertas.map((x) => (x.id === o.id ? { ...x, estado: o.estado } : x)),
      }));
      setAviso(e?.message || "No se pudo cambiar el estado");
    }
  };

  const pedirEliminar = (o) => setConfirmar({
    titulo: "Eliminar oferta",
    mensaje: `¿Eliminar "${o.nombre}"? Los pedidos ya creados conservan su desglose congelado y no se ven afectados.`,
    peligro: true,
    confirmarLabel: "Eliminar",
    accion: async () => {
      try { await eliminarOferta(o.id); setConfirmar(null); refrescar(); }
      catch (e) { setConfirmar(null); setAviso(e?.message || "No se pudo eliminar"); }
    },
  });

  return (
    <div>
      {aviso && (
        <div className="ub-info" style={{ marginBottom: 12 }}>
          <span>{aviso}</span>
          <button className="ub-modal__x" style={{ marginLeft: "auto" }} onClick={() => setAviso("")}>✕</button>
        </div>
      )}

      <div className="ub-info" style={{ marginBottom: 14 }}>
        <span>Las ofertas y recargos de domicilio son independientes de los descuentos de productos.
          Solo afectan el precio del domicilio (piso $0, techo $50.000). El día se evalúa en hora de Colombia.</span>
      </div>

      <div className="ub-toolbar">
        <div className="ub-search">
          <Search size={15} className="ub-search__icon" />
          <input placeholder="Buscar oferta…" value={texto} onChange={(e) => setTexto(e.target.value)} />
        </div>
        <button className="ub-icon-btn" onClick={refrescar} data-tooltip="Actualizar ofertas">
          <RefreshCw size={14} />
        </button>
        <select className="ub-select" value={filtroTipo} onChange={(e) => { setFiltroTipo(e.target.value); setPagina(1); }}>
          <option value="">Tipo: todos</option>
          <option value="descuento">Descuentos</option>
          <option value="recargo">Recargos</option>
        </select>
        <select className="ub-select" value={filtroEstado} onChange={(e) => { setFiltroEstado(e.target.value); setPagina(1); }}>
          <option value="">Estado: todos</option>
          <option value="1">Activas</option>
          <option value="2">Inactivas</option>
        </select>
        {perms.crear && (
          <button className="ub-btn ub-btn--primary" onClick={() => setModal({})}>
            <Plus size={14} /> Nueva oferta / recargo
          </button>
        )}
      </div>

      <div className="ub-tbl__scroll">
        <table className="ub-tbl">
          <thead>
            <tr>
              <th>Nombre</th><th>Tipo</th><th>Valor</th><th>Días</th>
              <th>Barrios</th><th>Estado</th><th style={{ textAlign: "right" }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {cargando && <tr><td colSpan={7} className="ub-loading">Cargando…</td></tr>}
            {!cargando && data.ofertas.length === 0 && (
              <tr><td colSpan={7} className="ub-empty">No hay ofertas registradas.</td></tr>
            )}
            {!cargando && data.ofertas.map((o) => (
              <tr key={o.id}>
                <td>{o.nombre}</td>
                <td>
                  <span className={`ub-badge ub-badge--${o.tipo === "recargo" ? "recargo" : "descuento"}`}>
                    {o.tipo}
                  </span>
                </td>
                <td>{resumenValor(o)}</td>
                <td>{resumenDias(o)}</td>
                <td>{o.barrios.length}</td>
                <td>
                  {perms.cambiarEstado ? (
                    <button className={`ub-toggle${o.estado === 1 ? " ub-toggle--on" : ""}`}
                      title={o.estado === 1 ? "Desactivar" : "Activar"}
                      onClick={() => toggleEstado(o)} />
                  ) : (
                    <span className={`ub-badge ub-badge--${o.estado === 1 ? "activo" : "inactivo"}`}>
                      {o.estado === 1 ? "Activa" : "Inactiva"}
                    </span>
                  )}
                </td>
                <td>
                  <div className="ub-node__actions" style={{ justifyContent: "flex-end" }}>
                    <button className="ub-icon-btn" title="Ver detalle"
                      onClick={async () => setDetalle(await getOferta(o.id).catch(() => o))}>
                      <Eye size={13} />
                    </button>
                    {perms.editar && (
                      <button className="ub-icon-btn" title="Editar" onClick={() => setModal(o)}>
                        <Pencil size={13} />
                      </button>
                    )}
                    {perms.eliminar && (
                      <button className="ub-icon-btn ub-icon-btn--danger" title="Eliminar" onClick={() => pedirEliminar(o)}>
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPags > 1 && (
        <div className="ub-pager">
          <button disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>‹</button>
          <span>Página {pagina} de {totalPags} · {data.total} ofertas</span>
          <button disabled={pagina >= totalPags} onClick={() => setPagina((p) => p + 1)}>›</button>
        </div>
      )}

      {modal && (
        <ModalOferta
          oferta={modal.id ? modal : null}
          onCerrar={() => setModal(null)}
          onGuardado={(res) => {
            setModal(null);
            if (res?.sinCambios) { setAviso("No se hicieron cambios."); return; }
            refrescar();
          }}
        />
      )}

      {detalle && <DetalleOferta oferta={detalle} onCerrar={() => setDetalle(null)} />}

      {confirmar && (
        <ModalConfirmar
          titulo={confirmar.titulo} mensaje={confirmar.mensaje}
          peligro={confirmar.peligro} confirmarLabel={confirmar.confirmarLabel}
          onConfirmar={confirmar.accion} onCancelar={() => setConfirmar(null)}
        />
      )}
    </div>
  );
}
