import { useState, useEffect, useRef } from "react";
import { Search, X, AlertTriangle, Package, ClipboardList, Check, Eye, PenLine, Ban, RefreshCw, Building2, FolderOpen, ShoppingCart, ShoppingBag, Lock } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { fmtFecha } from "../../../utils/dateUtils.js";
import DateRangeFilter from "../../../shared/components/DateRangeFilter";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import { formatCOP } from "../../../utils/formato";
import {
  getOrdenes, crearOrden, editarOrden, anularOrden, cambiarEstadoOrden,
} from "../../../services/ordenesProduccionService.js";
import { getProducto, getProductos } from "../../../services/productosService.js";
import { getInsumos }   from "../../../services/insumosService.js";
import { convertir, formatCantidad } from "../../../utils/unidades.js";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import "./OrdenesProduccion.css";

const PER_PAGE = 5;
const MAX_CANTIDAD = 999;   // 3 dígitos

const ESTADOS_ORDEN = ["Pendiente", "En proceso", "Completada", "Cancelada"];

// IDs reales en la tabla Estados del backend
const ESTADO_TO_NUM = {
  "Pendiente":  1,
  "En proceso": 13,
  "Completada": 11,
  "Cancelada":  5,
};

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const ESTADO_CONFIG = {
  "Pendiente":  { dot: "#f9a825" },
  "En proceso": { dot: "#1976d2" },
  "Completada": { dot: "#43a047" },
  "Cancelada":  { dot: "#e53935" },
};

const VALID_TRANSITIONS = {
  "Pendiente":  ["En proceso", "Cancelada"],
  "En proceso": ["Completada", "Cancelada"],
  "Completada": [],
  "Cancelada":  [],
};

// "Cambiar estado" no cancela una orden: eso es "Anular" (permiso aparte). Y la
// orden de un pedido solo se cancela cancelando el pedido (3.12).
const transicionesPermitidas = (orden) =>
  (VALID_TRANSITIONS[orden?.estado] || []).filter(e => e !== "Cancelada");

// Estados del pedido (Venta) en los que su producción ya está habilitada:
// Confirmado (4), En producción (13), Fecha propuesta (16). Mientras el pedido
// no llegue a alguno de estos, su orden no se puede avanzar a mano.
const ESTADOS_VENTA_PRODUCIENDO = [4, 13, 16];
const produccionBloqueadaPorPedido = (orden) =>
  !!orden?.idVenta && !ESTADOS_VENTA_PRODUCIENDO.includes(orden?.ventaEstado);

// La orden solo es editable mientras está Pendiente Y no depende de un pedido
// (una orden generada por un pedido se gestiona desde el pedido; validado en backend).
const esEditable = (orden) => orden?.estado === "Pendiente" && !orden?.idVenta;

const fmt = formatCOP;

const urgenciaFecha = (fechaISO) => {
  if (!fechaISO) return "normal";
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const dias = Math.round((new Date(fechaISO + "T00:00:00") - hoy) / 86_400_000);
  if (dias < 0)  return "vencida";
  if (dias <= 1) return "urgente";
  if (dias <= 3) return "pronto";
  return "normal";
};

/* ─── Componentes base ─────────────────────────────────── */
function EstadoBadge({ estado }) {
  const COLORS = {
    "Pendiente":  { bg: "#f5f5f5", color: "#757575", border: "#e0e0e0" },
    "En proceso": { bg: "#e3f2fd", color: "#1565c0", border: "#90caf9" },
    "Pausada":    { bg: "#f3e5f5", color: "#6a1b9a", border: "#ce93d8" },
    "Completada": { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7" },
    "Cancelada":  { bg: "#ffebee", color: "#c62828", border: "#ef9a9a" },
  };
  const c = COLORS[estado] || { bg: "#f5f5f5", color: "#757575", border: "#e0e0e0" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
      borderRadius: 20, padding: "3px 10px",
      fontSize: 11, fontWeight: 700, whiteSpace: "nowrap",
    }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.color, flexShrink: 0 }} />
      {estado}
    </span>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div style={{
      position: "fixed", bottom: 28, right: 28, zIndex: 99999,
      padding: "12px 20px", borderRadius: 12, color: "#fff",
      background: toast.type === "error" ? "#c62828" : toast.type === "warn" ? "#e65100" : "#2e7d32",
      fontWeight: 600, fontSize: 13,
      boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
      display: "flex", alignItems: "center", gap: 8,
    }}>
      <span style={{ fontSize: 15, display: "flex", alignItems: "center" }}>{toast.type === "error" ? <X size={15} /> : toast.type === "warn" ? <AlertTriangle size={13} /> : <Check size={14} />}</span>
      {toast.message}
    </div>
  );
}

function SkeletonRows() {
  return Array.from({ length: 5 }, (_, i) => (
    <tr key={i}>
      {Array.from({ length: 7 }, (_, j) => (
        <td key={j}><div className="skeleton-cell" /></td>
      ))}
    </tr>
  ));
}

/* ═══════════════════════════════════════════════════════════
   MODAL VER DETALLES
   ═══════════════════════════════════════════════════════════ */
function ModalDetallesOrden({ orden, onClose }) {
  const navigate = useNavigate();
  const [fichaInsumos, setFichaInsumos] = useState(null);
  const [fichaLoading, setFichaLoading] = useState(false);
  const [fichaError, setFichaError] = useState("");
  const [insumosDataMap, setInsumosDataMap] = useState({});
  const [multiplier, setMultiplier] = useState(Number(orden?.cantidad || 1));
  const [showInsumos, setShowInsumos] = useState(true);

  useEffect(() => {
    setMultiplier(Number(orden?.cantidad || 1));
    setShowInsumos(false);
  }, [orden?.cantidad, orden?.idFicha]);

  useEffect(() => {
    let active = true;
    if (!orden?.idFicha || !orden?.idProducto) {
      setFichaInsumos(null);
      setFichaError("");
      setFichaLoading(false);
      return () => { active = false; };
    }

    setFichaLoading(true);
    setFichaError("");
    setFichaInsumos(null);

    getProducto(orden.idProducto)
      .then(prod => {
        if (!active) return;
        const ficha = prod?.ficha_tecnica;
        if (!ficha || !Array.isArray(ficha.insumos)) {
          setFichaInsumos([]);
          return;
        }
        const mapped = ficha.insumos.map(i => ({
          id: i.ID_Ficha_Insumo || `${Date.now()}-${Math.random()}`,
          idInsumo: i.ID_Insumo || null,
          nombre: i.nombre_insumo || "",
          cantidad: Number(i.Cantidad ?? 0),
          unidad: i.Unidad || "",
          stockActual: i.Stock_Actual ?? null,
        }));
        setFichaInsumos(mapped);

        // Cargar stock y precio de insumos (max 100 por límite del backend)
        getInsumos({ porPagina: 100 })
          .then(res => {
            if (!active) return;
            const map = {};
            (res.insumos || []).forEach(ins => {
              map[ins.ID_Insumo] = {
                stock:  ins.Stock_Actual ?? ins.Stock ?? 0,
                precio: ins.precio_unitario ?? 0,
              };
            });
            setInsumosDataMap(map);
          })
          .catch(() => { if (active) setInsumosDataMap({}); });
      })
      .catch(() => {
        if (!active) return;
        setFichaError("No se pudo cargar la ficha técnica.");
      })
      .finally(() => { if (active) setFichaLoading(false); });

    return () => { active = false; };
  }, [orden?.idFicha, orden?.idProducto]);

  if (!orden) return null;

  const costoDisplay = orden.costo > 0 ? fmt(orden.costo) : "—";
  const costoConProblemas = (orden.costoDetalle || []).some(d => d.error);
  const detalleCostoPorNombre = Object.fromEntries(
    (orden.costoDetalle || []).map(d => [d.nombre, d])
  );

  return (
    <div className="modal-overlay">
      <div
        className="modal-box"
        style={{ maxWidth: 480, width: "100%" }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Producción</p>
            <h2 className="modal-header__title">Orden #{orden.id}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <EstadoBadge estado={orden.estado} />
            <button className="modal-close-btn" onClick={onClose} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><X size={16} /></button>
          </div>
        </div>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Stats */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {[
              { label: "Cantidad",   value: orden.cantidad, bg: "#e8f5e9", color: "#2e7d32" },
              { label: "Costo est.", value: costoDisplay,   bg: "#f5f5f5", color: "#616161" },
            ].map(s => (
              <div key={s.label} style={{ background: s.bg, borderRadius: 12, padding: "12px 14px" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: s.color, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{s.label}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: s.color }}>{s.value}</div>
              </div>
            ))}
          </div>
          {costoConProblemas && (
            <div style={{ background: "#fff3e0", borderRadius: 10, padding: "8px 12px", fontSize: 12, color: "#e65100", display: "flex", gap: 8, alignItems: "flex-start" }}>
              <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>Algunos insumos no tienen precio de compra registrado o tienen unidades incompatibles. El costo puede estar incompleto — revisa el detalle de insumos.</span>
            </div>
          )}

          {orden.idVenta && (
            <div style={{ background: "#e3f2fd", border: "1px solid #90caf9", borderRadius: 10, padding: "10px 12px", display: "flex", alignItems: "center", gap: 10 }}>
              <Lock size={16} style={{ flexShrink: 0, color: "#1565c0" }} />
              <div style={{ flex: 1, fontSize: 12, color: "#1565c0" }}>
                Generada por el pedido <strong>#{orden.idVenta}</strong>
                {orden.ventaEstadoLabel ? <> · pedido «{orden.ventaEstadoLabel}»</> : null}. Su estado lo controla el pedido.
              </div>
              <button
                onClick={() => { onClose(); navigate(`/admin/pedidos?search=${orden.idVenta}`); }}
                style={{ background: "#1976d2", color: "#fff", border: "none", borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}
              >
                Ver pedido
              </button>
            </div>
          )}

          {/* Producto */}
          <div className="field-input field-input--disabled" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Package size={18} />
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: 1 }}>Producto</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1a1a" }}>
                {orden.nombreProducto || "—"} <span style={{ color: "#2e7d32" }}>×{orden.cantidad}</span>
              </div>
            </div>
          </div>

          {/* Pedido de venta vinculado */}
          {orden.idVenta && (
            <div className="field-input field-input--disabled" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <ShoppingBag size={18} />
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: 1 }}>Pedido de venta</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#1565c0" }}>#{orden.idVenta}</div>
              </div>
            </div>
          )}

          {/* Fechas — siempre visible, antes del bloque de insumos */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div className="field-input field-input--disabled" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: 1 }}>Inicio</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{fmtFecha(orden.fechaInicio)}</div>
            </div>
            <div className="field-input field-input--disabled" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#2e7d32", textTransform: "uppercase", letterSpacing: 1 }}>Entrega</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#2e7d32" }}>{fmtFecha(orden.fechaEntrega)}</div>
            </div>
            <div className="field-input field-input--disabled" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: 1 }}>Creada el</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{orden.fechaCreacion ? fmtFecha(orden.fechaCreacion) : "—"}</div>
            </div>
            <div className="field-input field-input--disabled" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: 1 }}>Completada el</div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{orden.fechaFin ? fmtFecha(orden.fechaFin) : "—"}</div>
            </div>
          </div>

          {(orden.idFicha || orden.nombreInsumo) && (
            <div style={{ display: "grid", gap: 10 }}>
              <div className="field-input field-input--disabled" style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {orden.idFicha ? <FolderOpen size={18} /> : <Package size={18} />}
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", letterSpacing: 1 }}>
                    {orden.idFicha ? "Insumos de ficha técnica" : "Insumo"}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#424242" }}>
                    {orden.idFicha ? "Los insumos de esta orden se extraen de la ficha técnica asociada." : orden.nombreInsumo || "—"}
                  </div>
                </div>
              </div>

              {orden.idFicha ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <button
                    type="button"
                    onClick={() => setShowInsumos(v => !v)}
                    style={{
                      width: "100%", textAlign: "left", display: "flex", justifyContent: "space-between",
                      alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: 12,
                      border: "1px solid #e0e0e0", background: showInsumos ? "#e8f5e9" : "#fff",
                      cursor: "pointer", fontSize: 13, fontWeight: 700,
                    }}
                  >
                    <span>Ver insumos de la ficha técnica</span>
                    <span style={{ fontSize: 12, color: "#2e7d32" }}>{showInsumos ? "Ocultar" : "Mostrar"}</span>
                  </button>
                  {showInsumos && (
                    <div style={{ overflowX: "auto", padding: "6px 0" }}>
                      {fichaLoading ? (
                        <p style={{ margin: 0, color: "#616161" }}>Cargando insumos de la ficha técnica…</p>
                      ) : fichaError ? (
                        <p style={{ margin: 0, color: "#c62828" }}>{fichaError}</p>
                      ) : fichaInsumos?.length > 0 ? (
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, gap: 8, alignItems: "center" }}>
                            <div style={{ fontSize: 12, color: "#616161" }}>Escala</div>
                            <select value={multiplier} onChange={e => setMultiplier(Number(e.target.value))} style={{ padding: "6px 8px", borderRadius: 6 }}>
                              {(() => {
                                const opts = [];
                                for (let i = 1; i <= 10; i++) opts.push(i);
                                if (!opts.includes(Number(orden?.cantidad || 0))) opts.push(Number(orden?.cantidad || 1));
                                return opts.sort((a,b)=>a-b).map(n => (
                                  <option key={n} value={n}>×{n}</option>
                                ));
                              })()}
                            </select>
                          </div>
                          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
                            <thead>
                              <tr>
                                <th style={{ textAlign: "left", padding: "10px", fontSize: 12, color: "#616161" }}>Insumo</th>
                                <th style={{ textAlign: "right", padding: "10px", fontSize: 12, color: "#616161" }}>Necesario</th>
                                <th style={{ textAlign: "right", padding: "10px", fontSize: 12, color: "#616161" }}>Stock</th>
                                <th style={{ textAlign: "right", padding: "10px", fontSize: 12, color: "#616161" }}>Costo</th>
                              </tr>
                            </thead>
                            <tbody>
                              {fichaInsumos.map((item, index) => {
                                const requerido = Number(item.cantidad || 0) * Number(multiplier || 1);
                                const stock = item.stockActual !== null ? item.stockActual : (item.idInsumo ? (insumosDataMap[item.idInsumo]?.stock ?? null) : null);
                                const agotado = stock !== null ? (stock < requerido) : null;
                                const detalleItem = detalleCostoPorNombre[item.nombre] || null;
                                const costoItem = detalleItem && !detalleItem.error
                                  ? (detalleItem.costo / Math.max(1, orden.cantidad)) * Number(multiplier || 1)
                                  : null;
                                return (
                                  <tr key={item.id} style={{ background: index % 2 === 0 ? "#fafafa" : "#fff" }}>
                                    <td style={{ padding: "10px", fontSize: 13, color: "#1a1a1a" }}>{item.nombre || "—"}</td>
                                    <td style={{ padding: "10px", textAlign: "right", fontSize: 13, color: "#424242" }}>{requerido} {item.unidad || ""}</td>
                                    <td style={{ padding: "10px", textAlign: "right", fontSize: 13 }}>
                                      {stock === null || stock === undefined ? (
                                        <span style={{ color: "#9e9e9e" }}>—</span>
                                      ) : (
                                        <span style={{ fontWeight: 700, color: agotado ? "#c62828" : "#2e7d32" }}>{stock}{" "}{item.unidad || ""}</span>
                                      )}
                                    </td>
                                    <td style={{ padding: "10px", textAlign: "right", fontSize: 13 }}>
                                      {detalleItem?.error ? (
                                        <span title={detalleItem.error} style={{ color: "#e65100", cursor: "help", fontSize: 12, display: "inline-flex", alignItems: "center", gap: 3 }}><AlertTriangle size={12} /> S/P</span>
                                      ) : costoItem != null ? (
                                        <span style={{ fontWeight: 700, color: "#616161" }}>{fmt(costoItem)}</span>
                                      ) : (
                                        <span style={{ color: "#9e9e9e" }}>—</span>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p style={{ margin: 0, color: "#616161" }}>No hay insumos registrados en la ficha técnica.</p>
                      )}
                    </div>
                  )}
                </div>
              ) : orden.nombreInsumo && (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "10px 14px", background: "#fafafa", borderRadius: 12 }}>
                  <div style={{ fontSize: 13, color: "#424242" }}>{orden.nombreInsumo}</div>
                  {orden.stockInsumo !== null && (
                    <div style={{ fontSize: 12, fontWeight: 700, color: orden.stockInsumo >= orden.cantidad ? "#2e7d32" : "#c62828" }}>
                      Disponible: {orden.stockInsumo}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Lote — solo si la orden está completada */}
          {orden.lote && (
            <div style={{ background: "#e8f5e9", border: "1px solid #a5d6a7", borderRadius: 12, padding: "14px 16px" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#2e7d32", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                Lote generado
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 10, color: "#616161", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Nº Lote</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1a1a" }}>{orden.lote.numeroLote}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "#616161", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Cantidad</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#2e7d32" }}>{orden.lote.cantidad}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "#616161", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Producción</div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{fmtFecha(orden.lote.fechaProduccion)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "#616161", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Vencimiento</div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{fmtFecha(orden.lote.fechaVencimiento)}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {orden.idFicha && (
          <div style={{ background: "#e8f5e9", border: "1px solid #a5d6a7", borderRadius: 12, padding: "12px 16px", display: "flex", alignItems: "center", gap: 12 }}>
            <ClipboardList size={20} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#2e7d32", marginBottom: 2 }}>Ficha técnica disponible</div>
              <div style={{ fontSize: 12, color: "#388e3c" }}>Consulta los insumos, cantidades y procedimiento detallado del producto.</div>
            </div>
            <button
              onClick={() => { onClose(); navigate("/admin/products", { state: { openFicha: orden.idProducto } }); }}
              style={{ background: "#2e7d32", color: "#fff", border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>
              Ver ficha
            </button>
          </div>
        )}
        <div className="modal-footer" style={{ justifyContent: "flex-end" }}>
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL CAMBIAR ESTADO
   ═══════════════════════════════════════════════════════════ */
const ESTADO_COLORS = {
  "Pendiente":  { bg: "#f5f5f5", color: "#757575", border: "#e0e0e0" },
  "En proceso": { bg: "#e3f2fd", color: "#1565c0", border: "#90caf9" },
  "Completada": { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7" },
  "Cancelada":  { bg: "#ffebee", color: "#c62828", border: "#ef9a9a" },
};


function ModalCambiarEstado({ orden, onClose, onConfirm, saving }) {
  const navigate = useNavigate();
  const [estadoSel,        setEstadoSel]        = useState(null);
  const [confirmStep,      setConfirmStep]      = useState(false);
  const [fechaVencimiento, setFechaVencimiento] = useState("");
  const [stockCheck,       setStockCheck]       = useState(null);
  const [stockLoading,     setStockLoading]     = useState(false);

  const today = localToday();

  useEffect(() => {
    const necesitaCheck = estadoSel === "En proceso" || estadoSel === "Completada";
    if (!necesitaCheck || !confirmStep || !orden?.idFicha || !orden?.idProducto) {
      setStockCheck(null);
      return;
    }
    let active = true;
    setStockLoading(true);
    Promise.all([
      getProducto(orden.idProducto),
      getInsumos({ porPagina: 100 }),
    ]).then(([prod, insData]) => {
      if (!active) return;
      // El stock y la unidad de cada insumo vienen en la propia ficha. Antes
      // ese dato no llegaba —el esquema del servidor lo borraba al responder—
      // y esta pantalla lo buscaba en un listado aparte de insumos, limitado a
      // los primeros 100: al insumo que no estuviera ahí le daba stock CERO y
      // bloqueaba la orden por "insumos insuficientes" con el depósito lleno.
      // El listado queda solo como respaldo para fichas viejas.
      const respaldo = {};
      (insData.insumos || []).forEach(ins => {
        respaldo[ins.ID_Insumo] = {
          stock:   ins.Stock_Actual ?? ins.Stock ?? 0,
          simbolo: ins.simbolo_unidad || "",
        };
      });

      const fichaInsumos = (prod?.ficha_tecnica?.insumos || []).map(i => {
        const alterno = respaldo[i.ID_Insumo] || {};
        return {
          idInsumo:    i.ID_Insumo || null,
          nombre:      i.nombre_insumo || "",
          cantidadUnitaria: Number(i.Cantidad ?? 0),
          unidad:      i.Unidad || "",
          // Lo que queda LIBRE, no el stock a secas: la harina que ya apartó
          // una orden en proceso tiene dueño, y el servidor la va a rechazar.
          stock:         i.Stock_Disponible ?? i.Stock_Actual ?? alterno.stock ?? 0,
          simboloInsumo: i.simbolo_unidad || alterno.simbolo || i.Unidad || "",
        };
      });

      const cantidadOrden = Number(orden.cantidad || 1);

      // La misma conversión que hace el servidor al iniciar la orden
      // (utils/unidades.js espeja su tabla). Con una tabla propia y más corta,
      // esta pantalla y el servidor no siempre daban el mismo veredicto.
      const fichaConCheck = fichaInsumos.map(item => {
        const pedido = item.cantidadUnitaria * cantidadOrden;
        const { valor, error } = convertir(pedido, item.unidad, item.simboloInsumo);
        const necesario = valor ?? pedido;
        return {
          ...item,
          necesario,
          error,
          faltante: error ? 0 : Math.max(0, necesario - item.stock),
        };
      });
      // Las unidades incompatibles también frenan: no es que falte insumo, es
      // que la ficha no se puede leer, y el servidor lo va a rechazar igual.
      const insuficientes = fichaConCheck.filter(i => i.faltante > 0.0001 || i.error);
      // Sin `stockMap`: esa variable no existe —quedó de cuando se llamaba
      // así— y la línea reventaba en silencio, dejando la revisión sin hacer.
      setStockCheck({ insuficientes, fichaConCheck, cantidadOrden });

      // Fecha vencimiento automática solo al completar: sale de la ficha técnica
      // (Dias_Vida_Util + Vida_Util_Unidad), igual que el backend.
      if (estadoSel === "Completada") {
        const vidaUtil = Number(prod?.ficha_tecnica?.Dias_Vida_Util || 0);
        const unidad   = (prod?.ficha_tecnica?.Vida_Util_Unidad || "dias").toLowerCase();
        if (vidaUtil && !fechaVencimiento) {
          const venc = new Date(today + "T00:00:00");
          if (unidad === "meses")        venc.setMonth(venc.getMonth() + vidaUtil);
          else if (unidad === "semanas") venc.setDate(venc.getDate() + vidaUtil * 7);
          else                           venc.setDate(venc.getDate() + vidaUtil);
          setFechaVencimiento(venc.toISOString().split("T")[0]);
        }
      }
    }).catch(() => { if (active) setStockCheck(null); })
      .finally(() => { if (active) setStockLoading(false); });
    return () => { active = false; };
  }, [estadoSel, confirmStep, orden?.idFicha, orden?.idProducto]);

  if (!orden) return null;

  const transicionesValidas = transicionesPermitidas(orden);
  const bloqueadaPorPedido  = produccionBloqueadaPorPedido(orden);

  const handleConfirm = () => {
    const loteData = {};
    if (estadoSel === "Completada") {
      loteData.Fecha_Produccion = today;
      if (fechaVencimiento) loteData.Fecha_Vencimiento = fechaVencimiento;
    }
    onConfirm(orden.id, estadoSel, loteData);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 420 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Producción</p>
            <h2 className="modal-header__title">Cambiar Estado</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><X size={16} /></button>
        </div>

        <div className="modal-body">
          {!confirmStep ? (
            <>
              <p className="section-label" style={{ marginTop: 0 }}>Orden #{orden.id} — selecciona el nuevo estado</p>
              {orden.idVenta && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, background: bloqueadaPorPedido ? "#fff8e1" : "#e3f2fd", border: `1px solid ${bloqueadaPorPedido ? "#ffe082" : "#90caf9"}`, borderRadius: 10, padding: "10px 12px", marginBottom: 10, fontSize: 12, color: bloqueadaPorPedido ? "#8a6d00" : "#1565c0" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                    <Lock size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                    <span>
                      {bloqueadaPorPedido
                        ? <>Esta orden pertenece al pedido <strong>#{orden.idVenta}</strong>{orden.ventaEstadoLabel ? <>, que está «{orden.ventaEstadoLabel}»</> : null}. Podrás iniciar o completar su producción cuando el pedido esté <strong>confirmado o en producción</strong>. Para cancelarla, cancela el pedido.</>
                        : <>Esta orden pertenece al pedido <strong>#{orden.idVenta}</strong>. Su producción se gestiona aquí, pero <strong>no se cancela</strong> desde esta pantalla: para cancelarla, cancela el pedido (la orden se cancela en cadena).</>}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => { onClose(); navigate(`/admin/pedidos?search=${orden.idVenta}`); }}
                    style={{ alignSelf: "flex-start", background: bloqueadaPorPedido ? "#f9a825" : "#1976d2", color: "#fff", border: "none", borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}
                  >
                    Ir al pedido #{orden.idVenta}
                  </button>
                </div>
              )}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {ESTADOS_ORDEN.map(est => {
                  const c = ESTADO_COLORS[est] || {};
                  const isCurrent = est === orden.estado;
                  const isValid   = transicionesValidas.includes(est) && !bloqueadaPorPedido;
                  const isDisabled = isCurrent || !isValid;
                  return (
                    <button
                      key={est}
                      disabled={isDisabled}
                      onClick={() => { setEstadoSel(est); setConfirmStep(true); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "11px 14px", borderRadius: 10,
                        border: `1.5px solid ${isCurrent ? c.border : isValid ? "#e0e0e0" : "#f0f0f0"}`,
                        background: isCurrent ? c.bg : "#fff",
                        cursor: isDisabled ? "default" : "pointer",
                        opacity: !isCurrent && !isValid ? 0.35 : 1,
                        fontFamily: "inherit", width: "100%", textAlign: "left",
                        transition: "all 0.15s",
                      }}
                    >
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: !isValid && !isCurrent ? "#ccc" : c.color, flexShrink: 0 }} />
                      <span style={{ fontSize: 13, fontWeight: 700, color: isCurrent ? c.color : !isValid ? "#bdbdbd" : "#1a1a1a", flex: 1 }}>{est}</span>
                      {isCurrent  && <span style={{ fontSize: 10, fontWeight: 700, color: "#2e7d32", textTransform: "uppercase" }}>Actual</span>}
                      {!isCurrent && isValid  && <span style={{ color: "#bdbdbd", fontSize: 16 }}>›</span>}
                      {!isCurrent && !isValid && <span style={{ fontSize: 10, color: "#bdbdbd" }}>No disponible</span>}
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ background: "#fff8e1", border: "1px solid #ffe082", borderRadius: 12, padding: "14px", textAlign: "center" }}>
                <div style={{ marginBottom: 6, display: "flex", justifyContent: "center" }}><AlertTriangle size={26} style={{ color: "#f9a825" }} /></div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#6d4c00", marginBottom: 4 }}>¿Confirmar cambio de estado?</div>
                <div style={{ fontSize: 12, color: "#9a6400" }}>Esta acción actualizará el flujo de producción.</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", background: "#fafafa", borderRadius: 10, padding: "14px", border: "1px solid #e0e0e0" }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", marginBottom: 6 }}>Actual</div>
                  <EstadoBadge estado={orden.estado} />
                </div>
                <span style={{ fontSize: 20, color: "#bdbdbd" }}>→</span>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#9e9e9e", textTransform: "uppercase", marginBottom: 6 }}>Nuevo</div>
                  <EstadoBadge estado={estadoSel} />
                </div>
              </div>

              {/* Stock check — solo al pasar a "En proceso" (aquí se descuentan los insumos) */}
              {estadoSel === "En proceso" && orden.idFicha && (
                stockLoading ? (
                  <div style={{ fontSize: 12, color: "#616161", padding: "8px 0" }}>Verificando disponibilidad de insumos…</div>
                ) : stockCheck ? (
                  stockCheck.insuficientes.length > 0 ? (
                    <div style={{ background: "#ffebee", border: "1px solid #ef9a9a", borderRadius: 12, padding: "14px" }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#c62828", marginBottom: 10 }}>
                        {stockCheck.insuficientes.every(i => i.error)
                          ? `Revisa las unidades de la ficha (${stockCheck.insuficientes.length})`
                          : `Insumos insuficientes (${stockCheck.insuficientes.length})`}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
                        {stockCheck.insuficientes.map((item, i) => (
                          <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "center", background: "#fff5f5", borderRadius: 8, padding: "8px 10px" }}>
                            <div>
                              <div style={{ fontSize: 12, fontWeight: 700, color: "#b71c1c" }}>{item.nombre}</div>
                              {/* Unidades que no se pueden comparar: no es que falte
                                  insumo, es que la ficha no se puede leer. Decirlo
                                  así evita mandar a comprar algo que sobra. */}
                              <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2 }}>
                                {item.error ? (
                                  <span style={{ color: "#c62828" }}>
                                    La receta pide <strong>{item.unidad || "—"}</strong> y el insumo
                                    se mide en <strong>{item.simboloInsumo || "—"}</strong>: no se
                                    pueden convertir.
                                  </span>
                                ) : (
                                  <>
                                    Stock: <strong style={{ color: "#c62828" }}>{formatCantidad(item.stock, item.simboloInsumo)}</strong>
                                    {" · "}Necesario: <strong>{formatCantidad(item.necesario, item.simboloInsumo)}</strong>
                                  </>
                                )}
                              </div>
                            </div>
                            <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                              {!item.error && (
                                <>
                                  <div style={{ fontSize: 10, color: "#9e9e9e", textTransform: "uppercase" }}>Faltante</div>
                                  <div style={{ fontSize: 13, fontWeight: 800, color: "#c62828" }}>{formatCantidad(item.faltante, item.simboloInsumo)}</div>
                                </>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div style={{ background: "#fff3e0", border: "1px solid #ffcc80", borderRadius: 10, padding: "10px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                        <div>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#e65100" }}>¿Faltan materias primas?</div>
                          <div style={{ fontSize: 11, color: "#bf360c", marginTop: 2 }}>Registra una compra al proveedor para reponer el stock.</div>
                        </div>
                        <button
                          type="button"
                          onClick={() => { onClose(); navigate("/admin/compras"); }}
                          style={{ background: "#e65100", color: "#fff", border: "none", borderRadius: 8, padding: "8px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}
                        >
                          Ir a Compras →
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ background: "#e8f5e9", border: "1px solid #a5d6a7", borderRadius: 10, padding: "10px 14px", fontSize: 12, color: "#2e7d32", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
                      <Check size={14} /> Todos los insumos tienen stock suficiente
                    </div>
                  )
                ) : null
              )}

              {/* Configuración del lote al completar */}
              {estadoSel === "Completada" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ background: "#e8f5e9", border: "1px solid #a5d6a7", borderRadius: 10, padding: "12px 14px" }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#2e7d32", marginBottom: 2 }}>Se generará un lote automáticamente</div>
                    <div style={{ fontSize: 11, color: "#388e3c" }}>Código: L-{today.replace(/-/g, "")} · Fecha producción: {today}</div>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#616161", display: "block", marginBottom: 4 }}>Fecha de vencimiento del lote</label>
                    <input type="date" value={fechaVencimiento} onChange={e => setFechaVencimiento(e.target.value)}
                      style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #e0e0e0", fontSize: 13, width: "100%", boxSizing: "border-box" }} />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer" style={{ justifyContent: confirmStep ? "space-between" : "flex-end" }}>
          {confirmStep
            ? <>
                <button className="btn-ghost" onClick={() => { setConfirmStep(false); setStockCheck(null); }}>← Volver</button>
                <button
                  className="btn-save"
                  onClick={handleConfirm}
                  disabled={saving || stockLoading || (estadoSel === "En proceso" && stockCheck?.insuficientes?.length > 0)}
                >
                  {saving ? "Guardando…" : "Confirmar cambio"}
                </button>
              </>
            : <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          }
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL ERROR — CAMBIO DE ESTADO
   ═══════════════════════════════════════════════════════════ */
function ModalErrorEstado({ mensaje, orden, onClose }) {
  const navigate = useNavigate();
  if (!mensaje) return null;

  const esFichaTecnica      = /ficha t[eé]cnica/i.test(mensaje);
  const esStockInsuficiente = /stock insuficiente/i.test(mensaje);
  const esTimeout           = /procesándose|procesandose|recarga/i.test(mensaje);
  const esPedido            = /pedido #?\d+/i.test(mensaje) &&
    /(lo controla el pedido|pertenece al pedido|cancela el pedido|confirma el pedido|depende del pedido)/i.test(mensaje);
  const esTransicion        = /no puede pasar a|estado final|no admite (más|mas) cambios/i.test(mensaje);

  const mPedido    = mensaje.match(/pedido #?(\d+)/i);
  const numPedido  = mPedido ? mPedido[1] : (orden?.idVenta || null);

  const titulo = esStockInsuficiente
    ? "Stock insuficiente"
    : esFichaTecnica
    ? "Ficha técnica requerida"
    : esPedido
    ? "Esta orden depende de un pedido"
    : esTransicion
    ? "Cambio de estado no disponible"
    : esTimeout
    ? "La operación tardó demasiado"
    : "No se pudo cambiar el estado";

  const irAFicha = () => {
    onClose();
    navigate("/admin/products", { state: { openFicha: orden?.idProducto } });
  };
  const irACompras = () => { onClose(); navigate("/admin/compras"); };
  const irAlPedido = () => { onClose(); navigate(`/admin/pedidos?search=${numPedido}`); };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()}>
        <div style={{ padding: "28px 24px 18px", textAlign: "center" }}>
          <div style={{
            width: 52, height: 52, borderRadius: 14,
            background: "#ffebee", border: "1px solid #ef9a9a",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 24, margin: "0 auto 14px",
          }}><AlertTriangle size={24} style={{ color: "#c62828" }} /></div>
          <h3 style={{ margin: "0 0 10px", fontSize: 16, fontWeight: 700, color: "#1a1a1a" }}>
            {titulo}
          </h3>
          <p style={{ margin: "0 0 16px", fontSize: 13, color: "#616161", lineHeight: 1.5 }}>
            {mensaje}
          </p>
          {esFichaTecnica && orden && (
            <div style={{
              background: "#e8f5e9", border: "1px solid #a5d6a7",
              borderRadius: 10, padding: "12px 16px",
              display: "flex", alignItems: "center", gap: 10,
              textAlign: "left", marginBottom: 8,
            }}>
              <ClipboardList size={20} style={{ flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#2e7d32", marginBottom: 2 }}>
                  Producto: {orden.nombreProducto}
                </div>
                <div style={{ fontSize: 11, color: "#388e3c" }}>
                  Puedes crear o editar la ficha técnica desde Gestión de Productos.
                </div>
              </div>
              <button
                onClick={irAFicha}
                style={{
                  background: "#2e7d32", color: "#fff", border: "none",
                  borderRadius: 8, padding: "7px 14px",
                  fontSize: 12, fontWeight: 700, cursor: "pointer",
                  whiteSpace: "nowrap", flexShrink: 0,
                }}
              >
                Ir a ficha técnica
              </button>
            </div>
          )}
          {esStockInsuficiente && (
            <div style={{
              background: "#fff3e0", border: "1px solid #ffcc80",
              borderRadius: 10, padding: "12px 16px",
              display: "flex", alignItems: "center", gap: 10,
              textAlign: "left", marginBottom: 8,
            }}>
              <ShoppingCart size={20} style={{ flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#e65100", marginBottom: 2 }}>
                  ¿Faltan materias primas?
                </div>
                <div style={{ fontSize: 11, color: "#bf360c" }}>
                  Registra una compra al proveedor para reponer el stock de los insumos que faltan.
                </div>
              </div>
              <button
                onClick={irACompras}
                style={{
                  background: "#e65100", color: "#fff", border: "none",
                  borderRadius: 8, padding: "7px 14px",
                  fontSize: 12, fontWeight: 700, cursor: "pointer",
                  whiteSpace: "nowrap", flexShrink: 0,
                }}
              >
                Ir a Compras
              </button>
            </div>
          )}
          {esPedido && numPedido && (
            <div style={{
              background: "#e3f2fd", border: "1px solid #90caf9",
              borderRadius: 10, padding: "12px 16px",
              display: "flex", alignItems: "center", gap: 10,
              textAlign: "left", marginBottom: 8,
            }}>
              <Lock size={20} style={{ flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#1565c0", marginBottom: 2 }}>
                  Pedido #{numPedido}
                </div>
                <div style={{ fontSize: 11, color: "#1976d2" }}>
                  El estado de esta orden lo gobierna el pedido. Gestiónalo desde Gestión de Pedidos.
                </div>
              </div>
              <button
                onClick={irAlPedido}
                style={{
                  background: "#1976d2", color: "#fff", border: "none",
                  borderRadius: 8, padding: "7px 14px",
                  fontSize: 12, fontWeight: 700, cursor: "pointer",
                  whiteSpace: "nowrap", flexShrink: 0,
                }}
              >
                Ir al pedido #{numPedido}
              </button>
            </div>
          )}
        </div>
        <div className="modal-footer modal-footer--center">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL ANULAR ORDEN
   ═══════════════════════════════════════════════════════════ */
function ModalAnularOrden({ orden, onClose, onConfirm }) {
  const [confirmText, setConfirmText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  if (!orden) return null;

  const handleConfirm = async () => {
    if (String(confirmText).toUpperCase().trim() !== "ANULAR") return;
    try {
      setSubmitting(true);
      await onConfirm(orden.id);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()}>
        <div style={{ padding: "28px 24px 18px", textAlign: "center" }}>
          <div style={{
            width: 52, height: 52, borderRadius: 14,
            background: "#ffebee", border: "1px solid #ef9a9a",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 24, margin: "0 auto 14px",
          }}><Ban size={24} style={{ color: "#c62828" }} /></div>
          <h3 style={{ margin: "0 0 8px", fontSize: 17, fontWeight: 700, color: "#1a1a1a" }}>Anular orden</h3>
          <p style={{ margin: "0 0 4px", fontSize: 14, color: "#616161" }}>
            ¿Anular la orden <strong>#{orden.id}</strong>?
          </p>
          <p style={{ margin: "0 0 8px", fontSize: 12, color: "#9e9e9e" }}>
            <strong>{orden.nombreProducto}</strong> × {orden.cantidad}
          </p>
          <p style={{ margin: "0 0 12px", fontSize: 12, color: "#9e9e9e" }}>
            La orden pasa a <strong>Cancelada</strong> y conserva su historial.
            {orden.estado === "En proceso" && " Los insumos reservados se devuelven al stock."}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 6 }}>
            <div style={{ fontSize: 12, color: "#616161" }}>Para confirmar escribe <strong>ANULAR</strong> en la casilla:</div>
            <input
              value={confirmText}
              onChange={e => setConfirmText(e.target.value)}
              placeholder="Escribe ANULAR para confirmar"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #e0e0e0", fontSize: 13 }}
            />
          </div>
        </div>
        <div className="modal-footer modal-footer--center">
          <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            onClick={handleConfirm}
            disabled={submitting || String(confirmText).toUpperCase().trim() !== "ANULAR"}
            style={{
              padding: "9px 20px", borderRadius: 9, border: "none",
              background: "#c62828", color: "#fff",
              fontWeight: 700, fontSize: 13, cursor: submitting ? "default" : "pointer",
              fontFamily: "inherit", opacity: submitting ? 0.7 : 1,
            }}
          >
            {submitting ? "Anulando…" : "Sí, anular orden"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL FORMULARIO — CREAR / EDITAR ORDEN
   ═══════════════════════════════════════════════════════════ */
function ModalFormOrden({ orden, productos, onClose, onSave }) {
  const [form, setForm] = useState({
    idProducto:   orden?.idProducto   ?? "",
    cantidad:     orden?.cantidad     ?? 1,
    // 3.2 — por defecto la fecha de inicio es hoy (editable hacia el futuro).
    fechaInicio:  orden?.fechaInicio  ?? localToday(),
    fechaEntrega: orden?.fechaEntrega ?? "",
  });
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [productLoading, setProductLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);

  const loadProduct = async (productId) => {
    if (!productId) {
      setSelectedProduct(null);
      return;
    }
    setProductLoading(true);
    try {
      const product = await getProducto(Number(productId));
      setSelectedProduct(product);
    } catch {
      setSelectedProduct(null);
    } finally {
      setProductLoading(false);
    }
  };

  useEffect(() => {
    if (form.idProducto) {
      loadProduct(form.idProducto);
    } else {
      setSelectedProduct(null);
    }
  }, [form.idProducto]);

  const set = (k, v) => {
    setForm(f => {
      const next = { ...f, [k]: v };
      // 3.5 — la fecha de inicio se confirma primero: si se cambia después de
      // haber puesto una fecha de entrega, la entrega se limpia y se vuelve a pedir.
      if (k === "fechaInicio" && f.fechaEntrega) next.fechaEntrega = "";
      return next;
    });
    setErrors(e => ({ ...e, [k]: "" }));
  };

  const sinFicha = !productLoading && form.idProducto && !selectedProduct?.ficha_tecnica;

  const handleSave = async () => {
    const today = localToday();
    const cantNum = Number(form.cantidad);
    const e = {};
    if (!form.idProducto)                      e.idProducto = "Seleccione un producto";
    if (!cantNum || cantNum < 1)               e.cantidad   = "Ingrese una cantidad válida";
    else if (cantNum > MAX_CANTIDAD)           e.cantidad   = `El máximo es ${MAX_CANTIDAD}`;
    // 3.10 — sin ficha técnica no se puede generar la orden.
    if (sinFicha)                              e.idProducto = "Este producto no tiene ficha técnica. Créala en Gestión de Productos.";

    if (!form.fechaEntrega)                    e.fechaEntrega = "La fecha de entrega es obligatoria";
    else if (form.fechaEntrega < today)        e.fechaEntrega = "La fecha no puede ser anterior a hoy";

    // 3.2 / 3.5 — fecha de inicio de hoy hacia adelante; al editar tampoco
    // antes de la original de la orden.
    if (form.fechaInicio) {
      if (form.fechaInicio < today && form.fechaInicio !== orden?.fechaInicio)
        e.fechaInicio = "La fecha de inicio no puede ser anterior a hoy";
      else if (orden?.fechaInicio && form.fechaInicio < orden.fechaInicio)
        e.fechaInicio = "No puede ser anterior a la fecha de inicio original de la orden";
      else if (form.fechaEntrega && form.fechaInicio > form.fechaEntrega)
        e.fechaInicio = "La fecha de inicio no puede ser después de la entrega";
    }
    if (Object.keys(e).length) { setErrors(e); return; }

    // 3.2 — al editar sin cambios no se dispara ninguna escritura.
    if (orden?.id) {
      const sinCambios =
        Number(form.idProducto)     === Number(orden.idProducto) &&
        cantNum                     === Number(orden.cantidad) &&
        (form.fechaInicio  || "")   === (orden.fechaInicio  || "") &&
        (form.fechaEntrega || "")   === (orden.fechaEntrega || "");
      if (sinCambios) { onSave({ sinCambios: true }); return; }
    }

    setSaving(true);
    const payload = {
      ID_Producto:   Number(form.idProducto),
      Cantidad:      cantNum,
      Fecha_Entrega: form.fechaEntrega,
    };
    if (form.fechaInicio) payload.Fecha_inicio = form.fechaInicio;

    try {
      if (orden?.id) await editarOrden(orden.id, payload);
      else           await crearOrden(payload);
      onSave();
    } catch (err) {
      const msg = Array.isArray(err?.detail)
        ? err.detail.map(v => v.msg).join(", ")
        : (err?.detail || err?.message || "Error al guardar");
      setErrors({ _api: msg });
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: 460 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="modal-header__eyebrow">Producción</p>
            <h2 className="modal-header__title">{orden ? `Editar Orden #${orden.id}` : "Nueva Orden"}</h2>
          </div>
          <button className="modal-close-btn" onClick={onClose} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><X size={16} /></button>
        </div>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Producto */}
          <div className="form-group">
            <label className="form-label">Producto <span className="required">*</span></label>
            <SearchableSelect
              options={productos}
              value={form.idProducto}
              onChange={e => set("idProducto", e.target.value)}
              getValue={p => p.id}
              getLabel={p => p.nombre}
              placeholder="Seleccione un producto…"
              searchPlaceholder="Buscar producto…"
              error={!!errors.idProducto}
            />
            {errors.idProducto && <span className="field-error">{errors.idProducto}</span>}
          </div>

          {/* Ficha técnica */}
          <div className="form-group">
            <label className="form-label">Ficha técnica</label>
            <div className="field-input field-input--disabled" style={{ padding: "11px 14px", minHeight: 42, display: "flex", alignItems: "center", gap: 8 }}>
              {productLoading ? (
                <span style={{ color: "#616161" }}>Cargando ficha…</span>
              ) : selectedProduct?.ficha_tecnica ? (
                <span style={{ color: "#2e7d32", fontWeight: 700 }}>Sí — versión {selectedProduct.ficha_tecnica.Version || "1.0"}</span>
              ) : form.idProducto ? (
                <span style={{ color: "#c62828", fontWeight: 600 }}>No disponible</span>
              ) : (
                <span style={{ color: "#616161" }}>Selecciona un producto para ver la ficha</span>
              )}
            </div>
            {sinFicha && (
              <p className="field-error" style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 4 }}>
                ⚠ Este producto no tiene ficha técnica. No se puede crear una orden hasta cargarla en Gestión de Productos.
              </p>
            )}
          </div>

          {/* Cantidad */}
          <div className="form-group">
            <label className="form-label">Cantidad <span className="required">*</span></label>
            <input
              type="number"
              min={1}
              max={MAX_CANTIDAD}
              className={`field-input${errors.cantidad ? " error" : ""}`}
              value={form.cantidad}
              onChange={e => {
                const v = e.target.value;
                set("cantidad", v === "" ? "" : String(Math.min(MAX_CANTIDAD, Math.max(0, Math.floor(Number(v) || 0)))));
              }}
            />
            {errors.cantidad && <span className="field-error">{errors.cantidad}</span>}
          </div>

          {/* Fechas */}
          <div className="form-grid-2">
            <div className="form-group">
              <label className="form-label">Fecha de inicio</label>
              <input
                type="date"
                className={`field-input${errors.fechaInicio ? " error" : ""}`}
                min={orden ? (orden.fechaInicio || localToday()) : localToday()}
                value={form.fechaInicio}
                onChange={e => set("fechaInicio", e.target.value)}
              />
              {errors.fechaInicio && <span className="field-error">{errors.fechaInicio}</span>}
            </div>
            <div className="form-group">
              <label className="form-label">Fecha de entrega <span className="required">*</span></label>
              <input
                type="date"
                className={`field-input${errors.fechaEntrega ? " error" : ""}`}
                min={form.fechaInicio || localToday()}
                value={form.fechaEntrega}
                onChange={e => set("fechaEntrega", e.target.value)}
              />
              {errors.fechaEntrega && <span className="field-error">{errors.fechaEntrega}</span>}
            </div>
          </div>

          {errors._api && (
            <div style={{
              display: "flex", alignItems: "flex-start", gap: 10,
              background: "#ffebee", border: "1.5px solid #ef9a9a",
              borderRadius: 10, padding: "12px 14px",
            }}>
              <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
              <div>
                <div style={{ fontSize: 12, fontWeight: 800, color: "#c62828", marginBottom: 2 }}>
                  Error al guardar
                </div>
                <div style={{ fontSize: 12, fontWeight: 500, color: "#b71c1c", lineHeight: 1.4 }}>
                  {errors._api}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer" style={{ justifyContent: "space-between" }}>
          <button className="btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn-save" onClick={handleSave} disabled={saving || sinFicha || productLoading}>
            {saving ? "Guardando…" : orden ? "Guardar cambios" : "Crear orden"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   COMPONENTE PRINCIPAL
   ═══════════════════════════════════════════════════════════ */
export default function GestionOrdenesProduccion() {
  const location      = useLocation();
  const initialSearch = new URLSearchParams(location.search).get("search") || "";

  const [ordenes,      setOrdenes]      = useState([]);
  const [productos,    setProductos]    = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [tab,          setTab]          = useState("activas");
  const [search,       setSearch]       = useState(initialSearch);
  const [filterEstado, setFilterEstado] = useState("todos");
  const [filterDesde,  setFilterDesde]  = useState("");
  const [filterHasta,  setFilterHasta]  = useState("");
  const [showFilter,   setShowFilter]   = useState(false);
  const [page,         setPage]         = useState(1);
  const [modal,        setModal]        = useState(null);
  const [toast,        setToast]        = useState(null);
  const [actionSaving, setActionSaving] = useState(false);
  const filterRef = useRef();

  const ESTADOS_ACTIVAS   = ["Pendiente", "En proceso"];
  const ESTADOS_HISTORIAL = ["Completada", "Cancelada"];

  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3200);
  };

  const cargarDatos = async () => {
    setLoading(true);
    try {
      const [ordenesData, pData] = await Promise.all([
        getOrdenes(),
        getProductos().catch(() => ({ productos: [] })),
      ]);
      setOrdenes([...(ordenesData || [])].sort((a, b) => b.id - a.id));
      setProductos(
        (pData.productos || [])
          .filter(p => p.Estado !== 0)
          .map(p => ({ id: p.ID_Producto, nombre: p.nombre || p.Nombre || "" }))
      );
    } catch (e) {
      showToast(e.message || "Error al cargar órdenes", "error");
    } finally {
      setLoading(false);
    }
  };

  // Recarga solo las órdenes (tras cambiar estado o anular): el catálogo de
  // productos no cambia por esas acciones, no hace falta volver a pedirlo.
  const recargarOrdenes = async () => {
    try {
      const data = await getOrdenes();
      setOrdenes([...(data || [])].sort((a, b) => b.id - a.id));
    } catch (e) {
      showToast(e.message || "Error al recargar órdenes", "error");
    }
  };

  useEffect(() => { cargarDatos(); }, []);

  useEffect(() => {
    const h = e => {
      if (filterRef.current && !filterRef.current.contains(e.target)) setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const estadosPorTab = tab === "activas" ? ESTADOS_ACTIVAS : ESTADOS_HISTORIAL;

  const filtered = ordenes.filter(o => {
    if (!estadosPorTab.includes(o.estado)) return false;
    const q = search.toLowerCase();
    const matchQ = [
      String(o.id ?? ""),
      String(o.idVenta ?? ""),
      o.idVenta ? `v-${o.idVenta}` : "",
      o.nombreProducto ?? "",
      o.nombreInsumo   ?? "",
    ].some(v => v && v.toLowerCase().includes(q));
    const matchE = filterEstado === "todos" || o.estado === filterEstado;

    let matchFecha = true;
    if (filterDesde || filterHasta) {
      const fechaRaw = String(o.fechaInicio || "").slice(0, 10);
      const fecha = fechaRaw ? new Date(`${fechaRaw}T00:00:00`) : null;
      if (!fecha) matchFecha = false;
      if (filterDesde && fecha && new Date(`${filterDesde}T00:00:00`) > fecha) matchFecha = false;
      if (filterHasta && fecha && new Date(`${filterHasta}T00:00:00`) < fecha) matchFecha = false;
    }
    return matchQ && matchE && matchFecha;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const safePage   = Math.min(page, totalPages);

  const paged      = filtered.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);

  useEffect(() => setPage(1), [search, filterEstado, filterDesde, filterHasta, tab]);
  useEffect(() => { setFilterEstado("todos"); setPage(1); }, [tab]);

  const handleSaveOrder = async (info) => {
    // 3.2 — al guardar "editar orden" sin cambios no se hizo ninguna petición.
    if (info?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    await cargarDatos();
    showToast(modal?.orden ? "Orden actualizada" : "Orden creada");
    setModal(null);
  };

  const handleCambiarEstado = async (idOrden, nuevoEstado, loteData = {}) => {
    if (actionSaving) return;
    const estadoNum = ESTADO_TO_NUM[nuevoEstado];
    const ordenActual = ordenes.find(o => o.id === idOrden);
    setActionSaving(true);
    try {
      // El backend sincroniza el estado del pedido asociado (si lo hay) al
      // completar o cancelar la orden — no se hace desde el frontend.
      await cambiarEstadoOrden(idOrden, estadoNum, loteData);

      showToast(`Estado cambiado a "${nuevoEstado}"`);
      setModal(null);
      await recargarOrdenes();
    } catch (e) {
      const isApiError = typeof e.statusCode === "number";
      const errorMsg = isApiError
        ? (e.message || "Error al cambiar estado")
        : "La operación puede estar procesándose en el servidor. Recarga la página antes de reintentar para evitar aplicar el cambio dos veces.";
      setModal({ type: "errorEstado", mensaje: errorMsg, orden: ordenActual });
    } finally {
      setActionSaving(false);
    }
  };

  const handleAnular = async (idOrden) => {
    if (actionSaving) return;
    setActionSaving(true);
    try {
      await anularOrden(idOrden);
      showToast("Orden anulada", "warn");
      await recargarOrdenes();
    } catch (e) {
      showToast(e.message || e.detail || "Error al anular la orden", "error");
    } finally {
      setActionSaving(false);
      setModal(null);
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Órdenes de Producción</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        {/* ── Pestañas activas / historial ── */}
        <div style={{ display: "flex", gap: 0, marginBottom: 18, borderBottom: "2px solid #e0e0e0" }}>
          {[
            { key: "activas",   label: "Activas", count: ordenes.filter(o => ESTADOS_ACTIVAS.includes(o.estado)).length },
            { key: "historial", label: "Completadas y canceladas", count: ordenes.filter(o => ESTADOS_HISTORIAL.includes(o.estado)).length },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: "10px 20px", border: "none", background: "none",
                fontFamily: "inherit", fontSize: 14, fontWeight: 700, cursor: "pointer",
                color: tab === t.key ? "#2e7d32" : "#9e9e9e",
                borderBottom: tab === t.key ? "2px solid #2e7d32" : "2px solid transparent",
                marginBottom: -2, transition: "color 0.15s",
                display: "flex", alignItems: "center", gap: 8,
              }}
            >
              {t.label}
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 7px", borderRadius: 20,
                background: tab === t.key ? "#e8f5e9" : "#f5f5f5",
                color: tab === t.key ? "#2e7d32" : "#9e9e9e",
              }}>{t.count}</span>
            </button>
          ))}
        </div>

        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar orden, producto…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar órdenes">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative", zIndex: 200 }}>
            <button
              className={`filter-icon-btn${filterEstado !== "todos" || filterDesde || filterHasta ? " has-filter" : ""}`}
              onClick={() => setShowFilter(v => !v)}
              data-tooltip="Filtrar órdenes"
            >▼</button>
            {showFilter && (
              <div className="filter-dropdown" style={{ minWidth: 220, zIndex: 200 }}>
                <p className="filter-section-title">Estado</p>
                {["todos", ...estadosPorTab].map(f => (
                  <button
                    key={f}
                    className={`filter-option${filterEstado === f ? " active" : ""}`}
                    onClick={() => { setFilterEstado(f); setPage(1); setShowFilter(false); }}
                  >
                    <span className="filter-dot" style={{ background: ESTADO_CONFIG[f]?.dot || "#bdbdbd" }} />
                    {f === "todos" ? "Todos" : f}
                  </button>
                ))}
                <div style={{ height: 1, background: "#f0f0f0", margin: "8px 0" }} />
                <DateRangeFilter
                  desde={filterDesde}
                  hasta={filterHasta}
                  label="Fecha de inicio"
                  onApply={({ desde, hasta }) => {
                    setFilterDesde(desde || "");
                    setFilterHasta(hasta || "");
                  }}
                  onClear={() => {
                    setFilterDesde("");
                    setFilterHasta("");
                  }}
                />
              </div>
            )}
          </div>

          {(filterEstado !== "todos" || filterDesde || filterHasta || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilterEstado("todos"); setFilterDesde(""); setFilterHasta(""); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          {tab === "activas" && (
            <button className="btn-agregar" onClick={() => setModal({ type: "form" })} data-tooltip="Crear nueva orden de producción">
              Agregar Orden <span style={{ fontSize: 18 }}>+</span>
            </button>
          )}
        </div>

        <div className="card">
          <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "80px", "--tbl-rows": 5 }}>
            <table className="tbl tbl--fixed-rows">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>Nº</th>
                  <th>Producto</th>
                  <th>Pedido</th>
                  <th>Cantidad</th>
                  <th>Entrega</th>
                  <th>Costo</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <SkeletonRows />
                ) : paged.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="empty-state">
                        <div className="empty-state__icon"><Building2 size={32} strokeWidth={1} style={{ color: "#bdbdbd" }} /></div>
                        <p className="empty-state__text">
                          {search || filterEstado !== "todos"
                            ? "Sin órdenes que coincidan."
                            : tab === "activas"
                            ? "No hay órdenes activas."
                            : "No hay órdenes completadas ni canceladas."}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : paged.map((orden, idx) => (
                  <tr key={orden.id} className="tbl-row">
                    <td>
                      <span className="row-num">
                        {String((safePage - 1) * PER_PAGE + idx + 1).padStart(2, "0")}
                      </span>
                    </td>
                    <td>
                      <div className="orden-num" style={{ fontSize: 13, fontWeight: 700, color: "#1a1a1a" }}>
                        {orden.nombreProducto || "—"}
                      </div>
                      <div style={{ fontSize: 10, color: "#9e9e9e" }}>#{orden.id}</div>
                      {orden.idVenta && (
                        <span className="orden-pedido-tag" data-tooltip="Su estado lo controla el pedido">
                          <Lock size={9} style={{ verticalAlign: "-1px" }} /> Ligada al pedido #{orden.idVenta}
                        </span>
                      )}
                    </td>
                    <td>
                      {orden.idVenta
                        ? <span style={{ fontSize: 12, fontWeight: 700, color: "#1565c0", background: "#e3f2fd", border: "1px solid #90caf9", borderRadius: 6, padding: "3px 8px", whiteSpace: "nowrap" }}>#{orden.idVenta}</span>
                        : <span style={{ fontSize: 12, color: "#bdbdbd" }}>—</span>
                      }
                    </td>
                    <td style={{ fontSize: 14, fontWeight: 700, color: "#2e7d32" }}>{orden.cantidad}</td>
                    <td>
                      <span className={`date-badge${urgenciaFecha(orden.fechaEntrega) === "urgente" ? " date-badge--urgente" : urgenciaFecha(orden.fechaEntrega) === "pronto" ? " date-badge--pronto" : ""}`}>
                        {fmtFecha(orden.fechaEntrega)}
                      </span>
                    </td>
                    <td style={{ fontSize: 13, fontWeight: 700 }}>
                      {orden.costo > 0 ? fmt(orden.costo) : <span style={{ color: "#9e9e9e" }}>—</span>}
                    </td>
                    <td><EstadoBadge estado={orden.estado} /></td>
                    <td>
                      <div className="actions-cell">
                        {(() => {
                          const editable       = esEditable(orden);
                          const ligadaAPedido  = !!orden.idVenta;
                          const anulable       = !ligadaAPedido && ["Pendiente", "En proceso"].includes(orden.estado);
                          const editTooltip    = ligadaAPedido
                            ? `Depende del pedido #${orden.idVenta} — se edita desde el pedido`
                            : editable ? "Editar" : "Solo se editan las órdenes pendientes";
                          return (
                            <>
                              <button className="act-btn act-btn--view" data-tooltip="Ver detalles" onClick={() => setModal({ type: "detalles", orden })}><Eye size={15} /></button>
                              <button
                                className="act-btn act-btn--edit"
                                data-tooltip={editTooltip}
                                onClick={() => editable && setModal({ type: "form", orden })}
                                disabled={!editable}
                                style={{ opacity: editable ? 1 : 0.35, cursor: editable ? "pointer" : "default" }}
                              ><PenLine size={15} /></button>
                              <button className="act-btn act-btn--status" data-tooltip="Cambiar estado" onClick={() => setModal({ type: "estado", orden })} disabled={actionSaving}><RefreshCw size={15} /></button>
                              <button
                                className="act-btn act-btn--delete"
                                data-tooltip={ligadaAPedido ? `Controlada por el pedido #${orden.idVenta}` : anulable ? "Anular" : "No se puede anular"}
                                onClick={() => anulable && setModal({ type: "anular", orden })}
                                disabled={!anulable}
                                style={{ opacity: anulable ? 1 : 0.35, cursor: anulable ? "pointer" : "default" }}
                              >{ligadaAPedido ? <Lock size={15} /> : <Ban size={15} />}</button>
                            </>
                          );
                        })()}
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && (
                  <FilasRelleno current={paged.length} perPage={PER_PAGE} colSpan={7} />
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar">
            <span className="pagination-count">
              {filtered.length} {filtered.length === 1 ? "orden" : "órdenes"} en total
            </span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
            </div>
          </div>
        </div>
      </div>

      {modal?.type === "form" && (
        <ModalFormOrden
          orden={modal.orden}
          productos={productos}
          onClose={() => setModal(null)}
          onSave={handleSaveOrder}
        />
      )}
      {modal?.type === "detalles" && (
        <ModalDetallesOrden orden={modal.orden} onClose={() => setModal(null)} />
      )}
      {modal?.type === "estado" && (
        <ModalCambiarEstado
          orden={modal.orden}
          saving={actionSaving}
          onClose={() => setModal(null)}
          onConfirm={handleCambiarEstado}
        />
      )}
      {modal?.type === "anular" && (
        <ModalAnularOrden orden={modal.orden} onClose={() => setModal(null)} onConfirm={handleAnular} />
      )}
      {modal?.type === "errorEstado" && (
        <ModalErrorEstado
          mensaje={modal.mensaje}
          orden={modal.orden}
          onClose={() => setModal(null)}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}
