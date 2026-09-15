// src/features/produccion/Productos/GestionProductos.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Módulo de Gestión de Productos conectado a la API real.
// Ya NO depende de AppContext para productos ni categorías.
// Mantiene AppContext solo para: canDeleteProducto, registrarSalidaProducto,
// guardarFicha, calcularCostoProduccion, sugerirPrecioConGanancia
// (funciones que aún pueden vivir en contexto local mientras se migran).
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { Search, X, AlertTriangle, Package, ClipboardList, Eye, PenLine, Trash2, Truck, Clock, AlertCircle, Scale, Utensils, CornerUpLeft, ChevronDown, RefreshCw } from "lucide-react";
import { fmtFecha } from "../../../utils/dateUtils.js";
import { crearFicha, editarFicha } from "../../../services/fichaTecnicaService.js";
import { Toast } from "./ui.jsx";
import CrearProducto from "./CrearProducto.jsx";
import EditarProducto from "./EditarProducto.jsx";
import FilasRelleno from "../../../shared/components/FilasRelleno";
import EditarFicha from "./ficha_tecnica/EditarFicha.jsx";
import CrearFicha from "./ficha_tecnica/CrearFicha.jsx";
import SalidaModal from "./SalidaModal.jsx";
import ModalEliminarValidado from "../../../ModalEliminarValidado";
import { getLotesProducto } from "../../../services/productosService";
import {
  getProductos,
  getCategorias,
  eliminarProducto as apiEliminarProducto,
  toggleEstadoProducto as apiToggleEstado,
  togglePublicadoProducto as apiTogglePublicado,
  editarProducto as apiEditarProducto,
  validarEliminarProducto,
} from "../../../services/productosService";
import { registrarSalida, procesarVencidos } from "../../../services/salidasService";
import { usePrivilegio } from "../../../context/PrivilegiosContext";
import { formatCOP } from "../../../utils/formato.js";
import "./Productos.css";

const ITEMS_PER_PAGE = 5;

/* ══════════════════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════════════════ */
function calcEstado(stock, minimo) {
  return stock > 0 && stock >= minimo ? "Disponible" : "No disponible";
}
function calcTooltip(stock, minimo) {
  if (stock === 0)    return "Sin unidades en stock";
  if (stock < minimo) return `Stock por debajo del mínimo (${minimo} uds.)`;
  return `Stock suficiente (mín. ${minimo} uds.)`;
}
const ESTADO_STYLES = {
  "Disponible":    { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7" },
  "No disponible": { bg: "#ffebee", color: "#c62828", border: "#ef9a9a" },
};
function hoyISO() {
  return new Date().toISOString().split("T")[0];
}
function estaVencido(fechaVenc) {
  if (!fechaVenc) return false;
  return fechaVenc < hoyISO();
}
function diasParaVencer(fechaVenc) {
  if (!fechaVenc) return null;
  return Math.ceil(
    (new Date(fechaVenc + "T00:00:00") - new Date(hoyISO() + "T00:00:00")) /
      86400000
  );
}
const TIPO_COLORS = {
  vencido:    { color: "#e65100", bg: "#fff3e0", border: "#ffcc80", Icon: Clock },
  dañado:     { color: "#c62828", bg: "#ffebee", border: "#ef9a9a", Icon: AlertCircle },
  ajuste:     { color: "#1565c0", bg: "#e3f2fd", border: "#90caf9", Icon: Scale },
  consumo:    { color: "#4a148c", bg: "#f3e5f5", border: "#ce93d8", Icon: Utensils },
  devolucion: { color: "#2e7d32", bg: "#e8f5e9", border: "#a5d6a7", Icon: CornerUpLeft },
};

/**
 * Convierte un ProductoResponse de la API al shape interno que usa la UI.
 * Centralizado aquí para que todos los componentes hijos reciban el mismo shape.
 */
function adaptarProducto(p) {
  const ft = p.ficha_tecnica;
  return {
    id:                p.ID_Producto,
    nombre:            p.nombre,
    idCategoria:       p.ID_Categoria ?? null,
    fechaCreacion:     fmtFecha(p.Fecha_Creacion ?? p.Fecha_creacion),
    precio:            parseFloat(p.Precio_venta ?? 0),
    stock:             p.Stock ?? 0,
    stockMinimo:       p.Stock_Minimo ?? 10,
    activo:            p.Estado === 1,
    publicado:         (p.Publicado ?? 0) === 1,
    descripcion_corta: p.Descripcion_Corta ?? "",
    descripcion_larga: p.Descripcion_Larga ?? "",
    estado:            p.estado_label ?? null,
    proxVencimiento:   p.proximo_vencimiento ?? null,
    diasParaVencer:    p.dias_para_vencer ?? null,
    requiereProduccion: (p.Requiere_Produccion ?? 0) === 1,
    imagenesApi:       p.imagenes ?? [],
    imagenesPreview:   (p.imagenes ?? []).map((img) => img.url).filter(Boolean),
    ficha: ft ? {
      id:            ft.ID_Ficha,
      producto:      p.nombre,
      productoId:    String(p.ID_Producto),
      version:       ft.Version       ?? "",
      procedimiento: ft.Procedimiento ?? "",
      observaciones: ft.Observaciones ?? "",
      fecha:            ft.Fecha_Creacion ? String(ft.Fecha_Creacion).split("T")[0] : "",
      estado:           ft.Estado,
      fotoPreview:      (p.imagenes ?? [])[0]?.url || null,
      vidaUtilCantidad: ft.Dias_Vida_Util != null ? String(ft.Dias_Vida_Util) : "",
      vidaUtilUnidad:   ft.Vida_Util_Unidad || "dias",
      insumos:          (ft.insumos || []).map(i => ({
        id:              i.ID_Ficha_Insumo || (Date.now() + Math.random()),
        idInsumo:        i.ID_Insumo,
        idCategoria:     String(i.ID_Categoria || ""),
        nombreCategoria: i.nombre_categoria || "",
        nombre:          i.nombre_insumo || "",
        cantidad:        String(i.Cantidad || ""),
        unidad:          i.Unidad || "",
      })),
    } : null,
  };
}

/* ══════════════════════════════════════════════════════════
   SUB-COMPONENTES
══════════════════════════════════════════════════════════ */

function Toggle({ value, onChange, disabled = false, title }) {
  return (
    <button
      onClick={() => !disabled && onChange && onChange(!value)}
      title={title}
      className="toggle-btn"
      style={{
        background: value ? "#43a047" : "#c62828",
        boxShadow: value
          ? "0 2px 8px rgba(67,160,71,0.45)"
          : "0 2px 8px rgba(198,40,40,0.3)",
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.75 : 1,
      }}
    >
      <span className="toggle-thumb" style={{ left: value ? 27 : 3 }}>
        <span className="toggle-label" style={{ color: "black" }}>
          {value ? "ON" : "OFF"}
        </span>
      </span>
    </button>
  );
}

function StockBar({ actual, minimo }) {
  const [hovered, setHovered] = useState(false);
  const pct   = minimo > 0 ? Math.min(100, Math.round((actual / (minimo * 2)) * 100)) : 100;
  const est   = actual === 0 ? "agotado" : actual < minimo ? "bajo" : "disponible";
  const color = est === "agotado" ? "#ef5350" : est === "bajo" ? "#ffa726" : "#43a047";
  const tipMap = {
    disponible: { label: "Disponible", bg: "#e8f5e9", border: "#a5d6a7", text: "#2e7d32" },
    bajo:       { label: "Stock bajo", bg: "#fff8e1", border: "#ffe082", text: "#f57f17" },
    agotado:    { label: "Agotado",    bg: "#ffebee", border: "#ef9a9a", text: "#c62828" },
  };
  const tip = tipMap[est];
  return (
    <div
      style={{ position: "relative", minWidth: 80 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        style={{
          height: 6, borderRadius: 4,
          background: est === "agotado" ? "#ffcdd2" : "#f0f0f0",
          overflow: "hidden", marginBottom: 4,
        }}
      >
        <div
          style={{
            width: est === "agotado" ? "100%" : pct + "%", height: "100%",
            background: color, borderRadius: 4, transition: "width 0.3s",
          }}
        />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: "#424242" }}>
        <strong style={{ color }}>{actual}</strong>
        <span style={{ color: "#bdbdbd" }}> / mín {minimo}</span>
      </span>
      {hovered && (
        <div
          style={{
            position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
            transform: "translateX(-50%)", background: tip.bg,
            border: `1px solid ${tip.border}`, color: tip.text,
            fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 8,
            whiteSpace: "nowrap", zIndex: 999, pointerEvents: "none",
            display: "flex", alignItems: "center", gap: 5,
            boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
          }}
        >
          <span
            style={{
              width: 7, height: 7, borderRadius: "50%",
              background: color, flexShrink: 0,
            }}
          />
          {tip.label}
          {est === "bajo" && (
            <span style={{ fontWeight: 400, opacity: 0.8 }}>
              {" "}· faltan {minimo - actual}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function VencCellProd({ fecha, dias }) {
  if (!fecha) return <span style={{ fontSize: 13, color: "#bdbdbd", fontWeight: 500 }}>—</span>;
  const [y, m, d] = fecha.split("-");
  const label = `${d}/${m}/${y}`;
  if (dias <= 0) return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 700, color: "#c62828", background: "#ffebee", border: "1px solid #ef9a9a", borderRadius: 6, padding: "3px 8px" }}>
      <AlertTriangle size={13} style={{ flexShrink: 0 }} /> Vencido
    </span>
  );
  if (dias <= 7) return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 700, color: "#e65100", background: "#fff3e0", border: "1px solid #ffcc80", borderRadius: 6, padding: "3px 8px" }}>
      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#e53935", flexShrink: 0 }} /> {label} <span style={{ fontWeight: 400, opacity: 0.8 }}>({dias}d)</span>
    </span>
  );
  if (dias <= 30) return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 700, color: "#f57f17", background: "#fff8e1", border: "1px solid #ffe082", borderRadius: 6, padding: "3px 8px" }}>
      <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#f9a825", flexShrink: 0 }} /> {label} <span style={{ fontWeight: 400, opacity: 0.8 }}>({dias}d)</span>
    </span>
  );
  return <span style={{ fontSize: 12, fontWeight: 600, color: "#616161" }}>{label}</span>;
}

function CatCell({ cat }) {
  const [show, setShow] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span
        style={{
          width: 34, height: 34, borderRadius: 8,
          background: "#f1f8f1", border: "1px solid #c8e6c9",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 17, cursor: "default",
        }}
      >
        {cat?.icon || <Package size={17} />}
      </span>
      {show && (
        <span
          style={{
            position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
            transform: "translateX(-50%)", background: "#1a1a1a", color: "#fff",
            fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 7,
            whiteSpace: "nowrap", zIndex: 999, pointerEvents: "none",
          }}
        >
          {cat?.nombre || "—"}
          <span
            style={{
              position: "absolute", top: "100%", left: "50%",
              transform: "translateX(-50%)", width: 0, height: 0,
              borderLeft: "5px solid transparent",
              borderRight: "5px solid transparent",
              borderTop: "5px solid #1a1a1a",
            }}
          />
        </span>
      )}
    </span>
  );
}

function ProductImg({ previews, nombre }) {
  const thumb = previews && previews.length > 0 ? previews[0] : null;
  return thumb ? (
    <img
      src={thumb}
      alt={nombre}
      style={{
        width: 36, height: 36, borderRadius: 8,
        objectFit: "cover", border: "1px solid #c8e6c9", flexShrink: 0,
      }}
    />
  ) : (
    <div
      style={{
        width: 36, height: 36, borderRadius: 8, flexShrink: 0,
        background: "#f1f8f1", border: "1px solid #c8e6c9",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <Package size={17} strokeWidth={1} style={{ color: "#bdbdbd" }} />
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   LOTES PANEL — Solo lectura
══════════════════════════════════════════════════════════ */
function LoteProductoRow({ l, tipo }) {
  const [abierto, setAbierto] = useState(false);
  const fv      = l.fechaVencimiento;
  const dias    = l.diasParaVencer;
  const urgente = !l.vencido && dias !== null && dias <= 7;
  const borderColor = l.vencido ? "#ef9a9a" : urgente ? "#ffe082" : "#c8e6c9";
  const bg          = l.vencido ? "#fff8f8" : urgente ? "#fffdf0" : "#f9fdf9";

  return (
    <div className="lote-item" style={{ borderColor, background: bg }}>
      <div
        className="lote-item__head"
        style={{ cursor: "pointer", marginBottom: abierto ? 10 : 0 }}
        onClick={() => setAbierto(a => !a)}
      >
        <span className="lote-item__id" style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <ChevronDown size={13} style={{ transform: abierto ? "rotate(180deg)" : "none", transition: "transform 0.15s", color: "#9e9e9e" }} />
          {l.numeroLote || `Lote #${l.id}`}
        </span>
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {l.vencido && (
            <span style={{ fontSize: 11, fontWeight: 700, color: "#c62828", background: "#ffebee", padding: "2px 8px", borderRadius: 20, border: "1px solid #ef9a9a" }}>Vencido</span>
          )}
          {urgente && (
            <span style={{ fontSize: 11, fontWeight: 700, color: "#e65100", background: "#fff3e0", padding: "2px 8px", borderRadius: 20, border: "1px solid #ffcc80", display: "flex", alignItems: "center", gap: 4 }}>
              <AlertTriangle size={13} style={{ flexShrink: 0 }} /> Vence en {dias}d
            </span>
          )}
          {fv && <span style={{ fontWeight: 600, fontSize: 12 }}>{l.vencido ? "Venció" : "Vence"}: {fmtFecha(fv)}</span>}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8, marginTop: abierto ? 0 : 8, fontSize: 13 }}>
        <div><strong>Restante:</strong> {l.cantidadRestante} uds.</div>
        <div><strong>Producido:</strong> {l.cantidadProducida} uds.</div>
      </div>

      {abierto && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed #d7e8d7", display: "flex", flexDirection: "column", gap: 6, fontSize: 12.5, color: "#424242" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 6 }}>
            <div><strong>Consumido (usado / vendido):</strong> {l.consumido} uds.</div>
            {tipo === "historial"
              ? <div style={{ color: "#c62828" }}><strong>Vencido sin usar:</strong> {l.vencidoSinUsar} uds.</div>
              : <div><strong>Disponible hoy:</strong> {l.cantidadRestante} uds.</div>}
            {l.fechaProduccion && <div><strong>Producción:</strong> {fmtFecha(l.fechaProduccion)}</div>}
            {fv && <div><strong>Vencimiento:</strong> {fmtFecha(fv)}</div>}
          </div>

          <div style={{ marginTop: 4 }}>
            <strong>Orden de producción que lo generó:</strong>{" "}
            {l.orden
              ? <>#{l.orden.id}{l.orden.fecha ? ` · ${fmtFecha(l.orden.fecha)}` : ""}{l.orden.cantidad != null ? ` · ${l.orden.cantidad} uds. producidas` : ""}{l.orden.idVenta ? ` · pedido #${l.orden.idVenta}` : " · producción manual"}</>
              : <span style={{ color: "#9e9e9e" }}>no registrada</span>}
          </div>

          <p style={{ margin: "2px 0 0", fontSize: 11, color: "#9e9e9e" }}>
            El desglose venta por venta no se registra a nivel de lote; se muestra el total consumido.
          </p>
        </div>
      )}
    </div>
  );
}

function LotesProductoPanel({ idProducto, tipo = "lotes" }) {
  const [lotes,   setLotes]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getLotesProducto(idProducto)
      .then(d => setLotes(d.lotes || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [idProducto]);

  if (loading) return (
    <div style={{ textAlign: "center", padding: "28px 0", color: "#9e9e9e", fontSize: 13 }}>Cargando lotes…</div>
  );

  const activos  = lotes.filter(l => !l.vencido && (l.cantidad ?? 0) > 0);
  const vencidos = lotes.filter(l => l.vencido);
  const mostrar  = tipo === "historial" ? vencidos : activos;

  if (!mostrar.length) return (
    <div className="empty-state" style={{ padding: "28px 20px" }}>
      <div className="empty-state__icon"><Package size={32} strokeWidth={1} style={{ color: "#bdbdbd" }} /></div>
      <p className="empty-state__text">
        {tipo === "historial" ? "Sin lotes vencidos registrados." : "Sin lotes activos registrados."}
      </p>
      {tipo === "lotes" && (
        <p style={{ fontSize: 11, color: "#9e9e9e", marginTop: 6 }}>
          Los lotes se generan al completar una Orden de Producción.
        </p>
      )}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {mostrar.map(l => <LoteProductoRow key={l.id} l={l} tipo={tipo} />)}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   VER PRODUCTO
══════════════════════════════════════════════════════════ */
function VerProducto({ product, catObj, onClose, onOpenFicha }) {
  const [tab, setTab]    = useState("info");
  const [imgIdx, setImgIdx] = useState(0);

  const minimo   = product.stockMinimo ?? 10;
  const estado   = calcEstado(product.stock, minimo);
  const s        = ESTADO_STYLES[estado];
  const salidas  = [];
  const vencidos = [];

  const resumenSalidas = salidas.reduce((acc, sal) => {
    acc[sal.tipo] = (acc[sal.tipo] || 0) + sal.cantidad;
    return acc;
  }, {});

  const previews = product.imagenesPreview ?? [];

  return (
    <div className="modal-overlay">
      <div
        className="modal-box"
        style={{ maxWidth: 500, display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 40px)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <ProductImg previews={previews} nombre={product.nombre} />
            <div>
              <p className="modal-header__eyebrow">Producto</p>
              <h2 className="modal-header__title">{product.nombre}</h2>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} style={{ display: "flex", alignItems: "center", justifyContent: "center" }}><X size={16} /></button>
        </div>

        <div className="ver-ins-tabs">
          {[
            { key: "info",     label: "Información" },
            { key: "lotes",    label: "Lotes" },
            { key: "historial",label: "Vencidos" },
            { key: "ficha",    label: "Ficha técnica" },
          ].map((t) => (
            <button
              key={t.key}
              className={`ver-ins-tab${tab === t.key ? " ver-ins-tab--active" : ""}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="modal-body" style={{ flex: 1, overflowY: "auto" }}>
          {/* ── Tab Info ── */}
          {tab === "info" && (
            <>
              {previews.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <div
                    style={{
                      width: "100%", height: 220, borderRadius: 14,
                      overflow: "hidden", border: "1.5px solid #e8f5e9",
                      background: "#f9fdf9",
                    }}
                  >
                    <img
                      src={previews[imgIdx]}
                      alt={product.nombre}
                      style={{ width: "100%", height: "100%", objectFit: "contain" }}
                    />
                  </div>
                  {previews.length > 1 && (
                    <div
                      style={{
                        display: "flex", gap: 8, marginTop: 10,
                        overflowX: "auto", paddingBottom: 4,
                      }}
                    >
                      {previews.map((url, i) => (
                        <div
                          key={i}
                          onClick={() => setImgIdx(i)}
                          style={{
                            width: 50, height: 50, borderRadius: 8,
                            overflow: "hidden", cursor: "pointer",
                            border: `2px solid ${imgIdx === i ? "#2e7d32" : "#e0e0e0"}`,
                            flexShrink: 0,
                          }}
                        >
                          <img
                            src={url}
                            alt="thumb"
                            style={{ width: "100%", height: "100%", objectFit: "cover" }}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="ver-ins-grid" style={{ marginBottom: 16 }}>
                <div className="ver-ins-field">
                  <span className="ver-ins-field__label">Nombre</span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{product.nombre}</span>
                </div>
                <div className="ver-ins-field">
                  <span className="ver-ins-field__label">Categoría</span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>
                    {catObj?.icon} {catObj?.nombre || "—"}
                  </span>
                </div>
                <div className="ver-ins-field">
                  <span className="ver-ins-field__label">Fecha creación</span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{fmtFecha(product.fechaCreacion)}</span>
                </div>
                <div className="ver-ins-field">
                  <span className="ver-ins-field__label">Precio de venta</span>
                  <span style={{ fontWeight: 700, fontSize: 16, color: "#2e7d32" }}>
                    {formatCOP(product.precio)}
                  </span>
                </div>
                <div className="ver-ins-field">
                  <span className="ver-ins-field__label">Estado stock</span>
                  <span
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      padding: "3px 10px", borderRadius: 20,
                      fontSize: 12, fontWeight: 700,
                      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
                    }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.color }} />
                    {estado}
                  </span>
                </div>
                <div className="ver-ins-field" style={{ gridColumn: "1 / -1" }}>
                  <span className="ver-ins-field__label">Estado</span>
                  <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Toggle value={product.activo !== false} disabled={true} onChange={() => {}} />
                      <span style={{ fontSize: 13, fontWeight: 700, color: product.activo !== false ? "#2e7d32" : "#616161" }}>
                        {product.activo !== false ? "Activo" : "Inactivo"}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Toggle value={product.publicado} disabled={true} onChange={() => {}} />
                      <span style={{ fontSize: 13, fontWeight: 700, color: product.publicado ? "#1565c0" : "#616161" }}>
                        {product.publicado ? "Visible en tienda" : "No publicado"}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Toggle value={product.requiereProduccion} disabled={true} onChange={() => {}} />
                      <span style={{ fontSize: 13, fontWeight: 700, color: product.requiereProduccion ? "#1565c0" : "#616161" }}>
                        {product.requiereProduccion ? "Requiere producción" : "Stock directo"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {(product.descripcion_corta || product.descripcion_larga) && (
                <>
                  <p className="ver-ins-section-label" style={{ textTransform: "none" }}>Descripción</p>
                  {product.descripcion_corta && (
                    <p style={{ fontSize: 13.5, color: "#424242", margin: "0 0 8px", lineHeight: 1.5 }}>
                      {product.descripcion_corta}
                    </p>
                  )}
                  {product.descripcion_larga && (
                    <p style={{ fontSize: 13, color: "#616161", margin: "0 0 16px", lineHeight: 1.6 }}>
                      {product.descripcion_larga}
                    </p>
                  )}
                </>
              )}

              <p className="ver-ins-section-label" style={{ textTransform: "none" }}>Stock</p>
              <div
                style={{
                  display: "grid", gridTemplateColumns: "1fr 1fr",
                  gap: 10, marginBottom: 8,
                }}
              >
                <div className="ver-ins-stock-card ver-ins-stock-card--actual">
                  <span className="ver-ins-stock-card__num">{product.stock}</span>
                  <span className="ver-ins-stock-card__label">Stock actual</span>
                  <span className="ver-ins-stock-card__uni">uds.</span>
                </div>
                <div className="ver-ins-stock-card ver-ins-stock-card--minimo">
                  <span className="ver-ins-stock-card__num">{minimo}</span>
                  <span className="ver-ins-stock-card__label">Stock mínimo</span>
                  <span className="ver-ins-stock-card__uni">uds.</span>
                </div>
              </div>
              <p style={{ margin: "4px 0 0", fontSize: 11, color: "#9e9e9e" }}>
                {calcTooltip(product.stock, minimo)}
              </p>
            </>
          )}

          {/* ── Tab Lotes ── */}
          {tab === "lotes" && <LotesProductoPanel idProducto={product.id} tipo="lotes" />}

          {/* ── Tab Vencidos ── */}
          {tab === "historial" && <LotesProductoPanel idProducto={product.id} tipo="historial" />}

          {/* ── Tab Ficha técnica ── */}
          {tab === "ficha" && (
            product.ficha ? (
              <div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#2e7d32" }}>Versión {product.ficha.version || "1.0"}</span>
                  <button onClick={() => { onClose(); onOpenFicha?.(product); }}
                    style={{ fontSize: 12, fontWeight: 700, color: "#1565c0", background: "#e3f2fd", border: "1px solid #90caf9", borderRadius: 8, padding: "5px 12px", cursor: "pointer" }}>
                    ✎ Editar ficha
                  </button>
                </div>
                {(product.ficha.insumos || []).length > 0 && (
                  <>
                    <p className="ver-ins-section-label" style={{ textTransform: "none", marginBottom: 8 }}>Insumos</p>
                    <div style={{ border: "1px solid #e8f5e9", borderRadius: 10, overflow: "hidden", marginBottom: 14 }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                        <thead>
                          <tr style={{ background: "#f1f8f1" }}>
                            <th style={{ padding: "7px 12px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#2e7d32", textTransform: "uppercase" }}>Insumo</th>
                            <th style={{ padding: "7px 12px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#2e7d32", textTransform: "uppercase" }}>Cantidad</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(product.ficha.insumos || []).map((ins, i) => (
                            <tr key={i} style={{ borderTop: "1px solid #f0f0f0" }}>
                              <td style={{ padding: "7px 12px", fontWeight: 600 }}>{ins.nombre || ins.idInsumo}</td>
                              <td style={{ padding: "7px 12px", color: "#424242" }}>{ins.cantidad} {ins.unidad}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
                {product.ficha.procedimiento && (
                  <>
                    <p className="ver-ins-section-label" style={{ textTransform: "none", marginBottom: 8 }}>Procedimiento</p>
                    <ol style={{ margin: 0, paddingLeft: 20 }}>
                      {product.ficha.procedimiento.split("\n").filter(l => l.trim()).map((paso, i) => (
                        <li key={i} style={{ fontSize: 13, color: "#424242", marginBottom: 4, lineHeight: 1.4 }}>{paso}</li>
                      ))}
                    </ol>
                  </>
                )}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "28px 0" }}>
                <ClipboardList size={32} strokeWidth={1} style={{ color: "#bdbdbd", marginBottom: 8 }} />
                <p style={{ margin: "0 0 12px", fontSize: 13, color: "#9e9e9e" }}>Este producto no tiene ficha técnica.</p>
                <button onClick={() => { onClose(); onOpenFicha?.(product); }}
                  style={{ fontSize: 13, fontWeight: 700, color: "#fff", background: "#2e7d32", border: "none", borderRadius: 8, padding: "8px 18px", cursor: "pointer" }}>
                  + Crear ficha técnica
                </button>
              </div>
            )
          )}

          {false && tab === "historial_legacy" && (
            <>
              {salidas.length > 0 && (
                <>
                  <p className="ver-ins-section-label" style={{ textTransform: "none" }}>
                    Resumen de salidas
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 18 }}>
                    {Object.entries(resumenSalidas).map(([tipo, total]) => {
                      const tc = TIPO_COLORS[tipo] || {
                        color: "#757575", bg: "#f5f5f5", border: "#e0e0e0", Icon: ClipboardList,
                      };
                      return (
                        <div
                          key={tipo}
                          style={{
                            display: "flex", alignItems: "center", gap: 6,
                            padding: "6px 12px", borderRadius: 20,
                            background: tc.bg, border: `1px solid ${tc.border}`,
                            fontSize: 12, fontWeight: 700, color: tc.color,
                          }}
                        >
                          {tc.Icon && <tc.Icon size={12} />}
                          {tipo.charAt(0).toUpperCase() + tipo.slice(1)}:
                          <span style={{ marginLeft: 2 }}>{total} uds.</span>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}

              <p className="ver-ins-section-label" style={{ textTransform: "none" }}>
                Lotes vencidos
              </p>
              {vencidos.length === 0 ? (
                <div className="empty-state" style={{ padding: "14px 20px" }}>
                  <p className="empty-state__text">No hay lotes vencidos registrados.</p>
                </div>
              ) : (
                <div className="lotes-lista" style={{ marginBottom: 18 }}>
                  {vencidos.map((lote) => (
                    <div key={lote.id} className="lote-item" style={{ borderColor: "#ef9a9a" }}>
                      <div className="lote-item__head">
                        <span className="lote-item__id">{lote.id}</span>
                        <span style={{ fontWeight: 600, fontSize: 12 }}>
                          Venció: {fmtFecha(lote.fechaVencimiento)}
                        </span>
                      </div>
                      <div
                        style={{
                          display: "grid", gridTemplateColumns: "repeat(2, 1fr)",
                          gap: 8, marginTop: 8, fontSize: 13,
                        }}
                      >
                        <div><strong>Cantidad actual:</strong> {lote.cantidadActual} uds.</div>
                        <div><strong>Ingreso:</strong> {fmtFecha(lote.fechaIngreso)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <p className="ver-ins-section-label" style={{ textTransform: "none", marginTop: 4 }}>
                Vencidos
              </p>
              {salidas.length === 0 ? (
                <div className="empty-state" style={{ padding: "14px 20px" }}>
                  <p className="empty-state__text">Aún no hay salidas registradas.</p>
                </div>
              ) : (
                <div className="historial-list">
                  {salidas.map((salida) => {
                    const tc = TIPO_COLORS[salida.tipo] || {
                      color: "#757575", bg: "#f5f5f5", Icon: ClipboardList,
                    };
                    return (
                      <div
                        key={salida.id}
                        style={{
                          display: "flex", justifyContent: "space-between",
                          alignItems: "center", padding: "10px 14px",
                          borderRadius: 9, border: "1px solid #f0f0f0",
                          marginBottom: 6, background: "#fafafa",
                        }}
                      >
                        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                          <span
                            style={{
                              padding: "2px 9px", borderRadius: 20,
                              fontSize: 11, fontWeight: 700,
                              color: tc.color, background: tc.bg,
                            }}
                          >
                            {tc.Icon && <tc.Icon size={11} style={{marginRight:3}} />}{salida.tipo}
                          </span>
                          <span style={{ fontSize: 13, color: "#424242" }}>{salida.motivo}</span>
                        </div>
                        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                          <span style={{ fontSize: 13, fontWeight: 700, color: "#c62828" }}>
                            -{salida.cantidad} uds.
                          </span>
                          <span style={{ fontSize: 11, color: "#bdbdbd" }}>{salida.fecha}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   LOADING SKELETON
══════════════════════════════════════════════════════════ */
function LoadingSkeleton() {
  return (
    <div style={{ padding: "20px 0" }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          style={{
            height: 60, borderRadius: 10, background: "#f1f8f1",
            marginBottom: 8, animation: "pulse 1.5s ease-in-out infinite",
            opacity: 1 - i * 0.12,
          }}
        />
      ))}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   PÁGINA PRINCIPAL
══════════════════════════════════════════════════════════ */
export default function GestionProductos() {
  const canDeleteProducto = null;

  const location   = useLocation();
  const puedeCrear    = usePrivilegio("GestionProductos_crear");
  const puedeEditar   = usePrivilegio("GestionProductos_editar");
  const puedeSalida   = usePrivilegio("GestionProductos_generar_salida");
  const puedeEliminar = usePrivilegio("GestionProductos_eliminar");

  /* ── Estado ── */
  const [productosRaw, setProductosRaw] = useState([]); // datos crudos de la API
  const [categorias,   setCategorias]   = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [search,       setSearch]       = useState("");
  const [filterCat,    setFilterCat]    = useState("Todas");
  const [filterEst,    setFilterEst]    = useState("Todos");
  const [showFilter,   setShowFilter]   = useState(false);
  const [page,         setPage]         = useState(1);
  const [modal,        setModal]        = useState(null);
  const [toast,        setToast]        = useState(null);
  const filterRef = useRef();

  /* ── Helpers de categoría ── */
  const getCat = useCallback(
    (idCategoria) => {
      const cat = categorias.find((c) => c.ID_Categoria === idCategoria);
      return cat
        ? { id: cat.ID_Categoria, nombre: cat.Nombre_Categoria, icon: cat.Icono ?? null }
        : { id: null, nombre: "Sin categoría", icon: null };
    },
    [categorias]
  );

  /* ── Productos adaptados (API → UI shape) ── */
  const productos = useMemo(
    () => productosRaw.map(adaptarProducto),
    [productosRaw]
  );

  /* ── Carga de datos ── */
  const cargarDatos = useCallback(async () => {
    setLoading(true);
    try {
      const [resProd, resCat] = await Promise.all([
        getProductos({ porPagina: 100 }),
        getCategorias({ porPagina: 100 }).catch(() => ({ categorias: [] })),
      ]);
      setProductosRaw(resProd.productos ?? []);
      setCategorias(resCat.categorias ?? []);
    } catch (e) {
      showToast("Error cargando datos: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    procesarVencidos()
      .then(res => { if (res?.procesados > 0) cargarDatos(); })
      .catch(() => {});
    cargarDatos();
  }, [cargarDatos]);

  /* ── Deep link: abrir ficha técnica desde otra vista ── */
  useEffect(() => {
    if (location.state?.openFicha && productos.length > 0) {
      const p = productos.find((prod) => prod.id === Number(location.state.openFicha));
      if (p) {
        setModal({ type: "ficha", product: p });
        window.history.replaceState({}, document.title);
      }
    }
  }, [location.state, productos]);

  /* ── Cierre del dropdown de filtros al click fuera ── */
  useEffect(() => {
    const h = (e) => {
      if (filterRef.current && !filterRef.current.contains(e.target))
        setShowFilter(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  /* ── Toast ── */
  const showToast = (msg, type = "success") => {
    setToast({ message: msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  /* ── Filtrado y paginación ── */
  const ESTADOS_FILTER = ["Todos", "Disponible", "No disponible"];
  const ESTADO_DOT     = { "Disponible": "#43a047", "No disponible": "#ef5350" };

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return productos.filter((p) => {
      const cat    = getCat(p.idCategoria);
      const estado = calcEstado(p.stock, p.stockMinimo);
      return (
        (p.nombre.toLowerCase().includes(q) ||
          cat.nombre.toLowerCase().includes(q)) &&
        (filterCat === "Todas" || cat.nombre === filterCat) &&
        (filterEst === "Todos" || estado === filterEst)
      );
    });
  }, [productos, search, filterCat, filterEst, getCat]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
  const safePage   = Math.min(page, totalPages);
  const paginated  = filtered.slice(
    (safePage - 1) * ITEMS_PER_PAGE,
    safePage * ITEMS_PER_PAGE
  );

  useEffect(() => setPage(1), [search, filterCat, filterEst]);

  const hasFilter  = filterCat !== "Todas" || filterEst !== "Todos";
  const catsEnUso  = useMemo(
    () => ["Todas", ...new Set(productos.map((p) => getCat(p.idCategoria).nombre).filter(Boolean))],
    [productos, getCat]
  );

  /* ── Handlers ── */
  const handleCreate = async () => {
    // CrearProducto ya llamó a la API; solo recargamos
    await cargarDatos();
    showToast("Producto creado");
    setModal(null);
  };

  const handleEdit = async (info) => {
    if (info?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    await cargarDatos();
    showToast("Cambios guardados");
    setModal(null);
  };

  const handleOpenDelete = async (product) => {
    try {
      const validation = await validarEliminarProducto(product.id);
      setModal({ type: "eliminar", product, validation });
    } catch {
      setModal({ type: "eliminar", product, validation: { ok: true } });
    }
  };

  const handleDelete = async () => {
    try {
      await apiEliminarProducto(modal.product.id);
      await cargarDatos();
      showToast("Producto eliminado", "warn");
    } catch (e) {
      showToast("Error al eliminar: " + e.message, "error");
    }
    setModal(null);
  };

  const handleToggleActivo = async (producto) => {
    try {
      await apiToggleEstado(producto.id, producto.activo);
      setProductosRaw((prev) =>
        prev.map((p) =>
          p.ID_Producto === producto.id
            ? { ...p, Estado: producto.activo ? 0 : 1 }
            : p
        )
      );
    } catch (e) {
      showToast("Error cambiando estado: " + e.message, "error");
      await cargarDatos();
    }
  };

  const handleTogglePublicado = async (producto) => {
    try {
      await apiTogglePublicado(producto.id, producto.publicado);
      setProductosRaw((prev) =>
        prev.map((p) =>
          p.ID_Producto === producto.id
            ? { ...p, Publicado: producto.publicado ? 0 : 1 }
            : p
        )
      );
    } catch (e) {
      showToast("Error cambiando visibilidad: " + e.message, "error");
      await cargarDatos();
    }
  };

  const handleSaveFicha = async (ficha) => {
    if (ficha?.sinCambios) {
      showToast("No se hicieron cambios");
      setModal(null);
      return;
    }
    try {
      if (modal.product.ficha?.id) {
        await editarFicha(modal.product.id, ficha);
      } else {
        await crearFicha({ ...ficha, ID_Producto: modal.product.id });
      }
    } catch (e) {
      showToast(e.message || "Error al guardar la ficha", "error");
      return;
    }
    await cargarDatos();
    showToast("Ficha técnica guardada");
    setModal(null);
  };

  const handleSalida = async (payload) => {
    try {
      await registrarSalida({
        tipo:       payload.tipo,
        idProducto: payload.id,
        cantidad:   payload.cantidad,
        motivo:     payload.motivo,
      });
      showToast("Salida registrada y stock actualizado");
      setModal(null);
      cargarDatos().catch(() => {});
    } catch (e) {
      showToast(e.message || "Error en la salida", "error");
      setModal(null);
    }
  };

  /* ══════════════════════════════════════════════════════
     RENDER
  ══════════════════════════════════════════════════════ */
  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1 className="page-header__title">Gestión de Productos</h1>
        <div className="page-header__line" />
      </div>

      <div className="page-inner">
        {/* ── Toolbar ── */}
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              className="search-input"
              placeholder="Buscar por nombre o categoría…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <button className="filter-icon-btn" onClick={() => cargarDatos()} data-tooltip="Actualizar productos">
            <RefreshCw size={15} />
          </button>

          <div ref={filterRef} style={{ position: "relative" }}>
            <button
              type="button"
              className={`filter-icon-btn${hasFilter ? " has-filter" : ""}`}
              onClick={() => setShowFilter((v) => !v)}
              data-tooltip="Filtrar productos"
            >
              ▼
            </button>
            {showFilter && (
              <div className="filter-dropdown" style={{ minWidth: 200 }}>
                <div
                  style={{
                    padding: "8px 14px 4px", fontSize: 10,
                    fontWeight: 700, color: "#9e9e9e", letterSpacing: 1.5,
                  }}
                >
                  Categoría
                </div>
                {catsEnUso.map((c) => (
                  <button
                    key={c}
                    className={`filter-option${filterCat === c ? " active" : ""}`}
                    onClick={() => setFilterCat(c)}
                  >
                    <span
                      className="filter-dot"
                      style={{ background: filterCat === c ? "#43a047" : "#bdbdbd" }}
                    />
                    {c}
                  </button>
                ))}
                <div style={{ height: 1, background: "#f5f5f5", margin: "4px 0" }} />
                <div
                  style={{
                    padding: "4px 14px", fontSize: 10,
                    fontWeight: 700, color: "#9e9e9e", letterSpacing: 1.5,
                  }}
                >
                  Estado
                </div>
                {ESTADOS_FILTER.map((st) => (
                  <button
                    key={st}
                    className={`filter-option${filterEst === st ? " active" : ""}`}
                    onClick={() => setFilterEst(st)}
                  >
                    <span
                      className="filter-dot"
                      style={{ background: ESTADO_DOT[st] || "#bdbdbd" }}
                    />
                    {st}
                  </button>
                ))}
                {hasFilter && (
                  <div style={{ padding: "4px 14px 8px" }}>
                    <button
                      onClick={() => {
                        setFilterCat("Todas");
                        setFilterEst("Todos");
                        setShowFilter(false);
                      }}
                      style={{
                        width: "100%", padding: 6, borderRadius: 7,
                        border: "1px solid #e0e0e0", background: "transparent",
                        color: "#e53935", fontSize: 12, fontWeight: 700,
                        cursor: "pointer", fontFamily: "inherit",
                      }}
                    >
                      Limpiar filtros
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {(hasFilter || search) && (
            <button className="btn-limpiar" onClick={() => { setSearch(""); setFilterCat("Todas"); setFilterEst("Todos"); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <X size={14} /> Limpiar
            </button>
          )}

          {puedeCrear && (
            <button className="btn-agregar" onClick={() => setModal({ type: "crear" })} data-tooltip="Agregar nuevo producto">
              Agregar <span style={{ fontSize: 18 }}>+</span>
            </button>
          )}
        </div>

        {/* ── Tabla ── */}
        <div className="card">
          {loading ? (
            <div style={{ padding: "0 20px" }}>
              <LoadingSkeleton />
            </div>
          ) : (
            <div className="tbl-wrapper tbl-wrapper--fixed" style={{ "--tbl-row-h": "80px", "--tbl-rows": 5 }}>
              <table className="tbl tbl--fixed-rows">
                <thead>
                    <tr>
                    <th>Nº</th>
                    <th>Producto</th>
                    <th>Categoría</th>
                    <th>Precio</th>
                    <th>Stock</th>
                    <th>Próx. Venc.</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {paginated.length === 0 ? (
                    <tr>
                      <td colSpan={8}>
                        <div className="empty-state">
                          <div className="empty-state__icon"><Package size={32} strokeWidth={1} style={{ color: "#bdbdbd" }} /></div>
                          <p className="empty-state__text">Sin resultados</p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    paginated.map((p, idx) => {
                      const cat = getCat(p.idCategoria);
                      return (
                        <tr key={p.id} className="tbl-row">
                          <td>
                            <span className="cat-num">
                              {String((safePage - 1) * ITEMS_PER_PAGE + idx + 1).padStart(2, "0")}
                            </span>
                          </td>
                          <td>
                            <div className="cat-cell">
                              <ProductImg previews={p.imagenesPreview} nombre={p.nombre} />
                              <span className="cat-name">{p.nombre}</span>
                            </div>
                          </td>
                          <td><CatCell cat={cat} /></td>
                          <td>
                            <span style={{ fontWeight: 700, color: "#2e7d32", fontSize: 14 }}>
                              {formatCOP(p.precio)}
                            </span>
                          </td>
                          <td>
                            <StockBar actual={p.stock} minimo={p.stockMinimo} />
                          </td>
                          <td><VencCellProd fecha={p.proxVencimiento} dias={p.diasParaVencer} /></td>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <Toggle value={p.activo} onChange={() => handleToggleActivo(p)} title={p.activo ? "Activo" : "Inactivo"} />
                                <span style={{ fontSize: 11, color: p.activo ? "#2e7d32" : "#9e9e9e", fontWeight: 600 }}>Activo</span>
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <Toggle value={p.publicado} onChange={() => handleTogglePublicado(p)} title={p.publicado ? "Visible en tienda" : "No publicado"} />
                                <span style={{ fontSize: 11, color: p.publicado ? "#1565c0" : "#9e9e9e", fontWeight: 600 }}>Tienda</span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="actions-cell">
                              <button
                                className="act-btn act-btn--view"
                                data-tooltip="Ver detalle del producto"
                                onClick={() => setModal({ type: "ver", product: p })}
                              ><Eye size={15} /></button>
                              {puedeEditar && (
                                <button
                                  className="act-btn act-btn--edit"
                                  data-tooltip="Editar producto"
                                  onClick={() => setModal({ type: "editar", product: p })}
                                ><PenLine size={15} /></button>
                              )}
                              <button
                                className="act-btn act-btn--ficha"
                                data-tooltip="Ver ficha técnica"
                                onClick={() => setModal({ type: "ficha", product: p })}
                              ><ClipboardList size={15} /></button>
                              {puedeSalida && (
                                <button
                                  className="act-btn act-btn--salida"
                                  data-tooltip="Registrar salida de producto"
                                  onClick={() => setModal({ type: "salida", product: p })}
                                ><Truck size={15} /></button>
                              )}
                              {puedeEliminar && (
                                <button
                                  className="act-btn act-btn--delete"
                                  data-tooltip="Eliminar producto"
                                  onClick={() => handleOpenDelete(p)}
                                ><Trash2 size={15} /></button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                  <FilasRelleno current={paginated.length} perPage={ITEMS_PER_PAGE} colSpan={8} />
                </tbody>
              </table>
            </div>
          )}

          {/* Paginación */}
          <div className="pagination-bar">
            <span className="pagination-count">
              {filtered.length} {filtered.length === 1 ? "producto" : "productos"} en total
            </span>
            <div className="pagination-btns">
              <button className="pg-btn-arrow" onClick={() => setPage(1)} disabled={safePage === 1}>«</button>
              <button className="pg-btn-arrow" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>‹</button>
              <span className="pg-pill">Página {safePage} de {totalPages}</span>
              <button className="pg-btn-arrow" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage === totalPages}>›</button>
              <button className="pg-btn-arrow" onClick={() => setPage(totalPages)} disabled={safePage === totalPages}>»</button>
            </div>
          </div>
        </div>
      </div>

      {/* ══ Modales ══ */}
      {modal?.type === "crear" && (
        <CrearProducto
          categorias={categorias}
          existingProducts={productos}
          onClose={() => setModal(null)}
          onSave={handleCreate}
        />
      )}
      {modal?.type === "editar" && (
        <EditarProducto
          product={modal.product}
          categorias={categorias}
          existingProducts={productos}
          onClose={() => setModal(null)}
          onSave={handleEdit}
        />
      )}
      {modal?.type === "ver" && (
        <VerProducto
          product={modal.product}
          catObj={getCat(modal.product.idCategoria)}
          onClose={() => setModal(null)}
          onOpenFicha={(p) => setModal({ type: "ficha", product: p })}
        />
      )}
      {modal?.type === "salida" && (
        <SalidaModal
          entidad={modal.product}
          tipo="producto"
          stockActual={modal.product.stock}
          unidadLabel="uds."
          onClose={() => setModal(null)}
          onConfirm={handleSalida}
        />
      )}
      {modal?.type === "eliminar" && (
        <ModalEliminarValidado
          titulo="Eliminar producto"
          descripcion={`¿Está seguro de que desea eliminar el producto "${modal.product.nombre}"?`}
          validacion={modal.validation ?? { ok: true }}
          onClose={() => setModal(null)}
          onConfirm={handleDelete}
        />
      )}
      {modal?.type === "ficha" && (
        modal.product.ficha
          ? (
            <EditarFicha
              ficha={modal.product.ficha}
              mode="edit"
              productoNombre={modal.product.nombre}
              productoFoto={modal.product.imagenesPreview[0] || null}
              onClose={() => setModal(null)}
              onSave={handleSaveFicha}
            />
          )
          : (
            <CrearFicha
              productoNombre={modal.product.nombre}
              productoId={modal.product.id}
              productoCategoria={getCat(modal.product.idCategoria)?.nombre}
              onClose={() => setModal(null)}
              onSave={handleSaveFicha}
            />
          )
      )}

      <Toast toast={toast} />
    </div>
  );
}
