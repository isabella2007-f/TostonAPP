import { useState, useEffect, useRef } from "react";
import { getUsuarios, editarUsuario } from "../../../services/usuariosService.js";
import SearchableSelect from "../../../shared/components/SearchableSelect.jsx";
import { soloLetras, soloDigitos } from "../../../utils/inputFilters";
import { getProductos } from "../../../services/productosService.js";
import { MUNICIPIOS_VALLE_ABURRA } from "../../../utils/departamentosYCiudades.js";
import { subirImagenCloudinary } from "../../../utils/cloudinary.js";
import { registrarPagoFinal, editarPedido } from "../../../services/pedidosService.js";
import { PERMISOS_POR_ESTADO, puedeEditarsePedido } from "./permisosEdicion.js";
import { X, Ban, AlertTriangle, CheckCircle2, CreditCard, PenLine, Check, Paperclip, Upload, Bike, Store, Truck, Pencil, Calendar, AlertCircle } from "lucide-react";
import SelectorBarrioEntrega from "../../../shared/components/SelectorBarrioEntrega.jsx";
import ImageLightbox from "../../../shared/components/ImageLightbox.jsx";
import "./Pedidos.css";
import { formatCOP } from "../../../utils/formato";

/* ─── Helpers ────────────────────────────────────────────── */
const fmt = formatCOP;

const METODOS_PAGO = ["Efectivo", "Transferencia"];

/* ─── Campo solo lectura ─────────────────────────────────── */
function FieldReadOnly({ label, value }) {
  return (
    <div className="field-wrap">
      <label className="field-label">{label}</label>
      <div className="field-input--disabled">{value || "—"}</div>
    </div>
  );
}

/* ─── ProductoItemEditable ───────────────────────────────── */
function ProductoItemEditable({ item, onChange, onRemove }) {
  const sinStock  = item.stockActual === 0;
  const pocoStock = item.stockActual > 0 && item.cantidad > item.stockActual;

  const setQty = (val) => {
    const n = Math.max(1, Math.min(999, Number(val) || 1));
    onChange({ ...item, cantidad: n, stockOk: item.stockActual >= n });
  };

  return (
    <div className="producto-item">
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="producto-item__name">{item.nombre}</div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 3 }}>
          <span className="producto-item__price">{fmt(item.precio)} c/u</span>
          {sinStock && (
            <span className="producto-item__stock-warn producto-item__stock-warn--none">Sin stock</span>
          )}
          {!sinStock && pocoStock && (
            <span className="producto-item__stock-warn producto-item__stock-warn--low">
              Stock insuf. ({item.stockActual} disp.)
            </span>
          )}
        </div>
      </div>
      <div className="producto-item__qty-wrap">
        <button className="qty-btn" onClick={() => setQty(item.cantidad - 1)}>−</button>
        <input
          type="number" min={1} className="qty-input"
          value={item.cantidad}
          onChange={e => setQty(e.target.value)}
        />
        <button className="qty-btn" onClick={() => setQty(item.cantidad + 1)}>+</button>
      </div>
      <div className="producto-item__total">{fmt(item.precio * item.cantidad)}</div>
      <button className="producto-item__remove" onClick={onRemove}><X size={16}/></button>
    </div>
  );
}

/* ─── ProductoItemFijo (solo lectura) ────────────────────── */
function ProductoItemFijo({ item }) {
  return (
    <div className="producto-item" style={{ opacity: 0.75, cursor: "default" }}>
      <div style={{ flex: 1 }}>
        <div className="producto-item__name">{item.nombre}</div>
        <div style={{ fontSize: 11, color: "#9e9e9e", marginTop: 2 }}>{fmt(item.precio)} c/u</div>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "#757575", padding: "0 10px" }}>
        × {item.cantidad}
      </div>
      <div className="producto-item__total">{fmt(item.precio * item.cantidad)}</div>
    </div>
  );
}

/* ─── BuscadorProducto ───────────────────────────────────── */
function BuscadorProducto({ productosSeleccionados, onAgregar, productos = [] }) {
  const [query,   setQuery]   = useState("");
  const [abierto, setAbierto] = useState(false);

  const idsSeleccionados = productosSeleccionados.map(p => p.idProducto);

  const filtrados = productos
    .filter(p => p.nombre.toLowerCase().includes(query.toLowerCase()))
    .filter(p => !idsSeleccionados.includes(p.id));

  const handleSelect = (prod) => {
    onAgregar({
      idProducto:  prod.id,
      nombre:      prod.nombre,
      precio:      prod.precio,
      cantidad:    1,
      stockActual: prod.stock,
      stockOk:     prod.stock > 0,
    });
    setQuery("");
    setAbierto(false);
  };

  return (
    <div className="product-search-wrap">
      <input
        className="field-input"
        placeholder="Agregar producto…"
        value={query}
        onChange={e => { setQuery(e.target.value); setAbierto(true); }}
        onFocus={() => setAbierto(true)}
        onBlur={() => setTimeout(() => setAbierto(false), 150)}
      />
      {abierto && query.length > 0 && (
        <div className="product-dropdown">
          {filtrados.length === 0 ? (
            <div style={{ padding: "12px 14px", fontSize: 13, color: "#9e9e9e" }}>Sin resultados</div>
          ) : filtrados.map(prod => {
            const sinStock  = prod.stock === 0;
            const pocoStock = prod.stock > 0 && prod.stock < prod.stockMinimo;
            return (
              <div key={prod.id} className="product-option" onClick={() => handleSelect(prod)}>
                <div>
                  <div className="product-option__name">{prod.nombre}</div>
                  <div style={{ fontSize: 11, color: "#9e9e9e" }}>
                    {prod.categoria || ""}
                  </div>
                </div>
                <div className="product-option__right">
                  <span className="product-option__price">{fmt(prod.precio)}</span>
                  <span className={
                    sinStock  ? "product-option__stock product-option__stock--none" :
                    pocoStock ? "product-option__stock product-option__stock--low"  :
                                "product-option__stock"
                  }>
                    {sinStock ? "Sin stock" : `Stock: ${prod.stock}`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MODAL EDITAR PEDIDO
═══════════════════════════════════════════════════════════ */
export default function EditarPedido({ pedido, onClose, onSave, onAprobarComprobante, onRechazarComprobante }) {
  const [clientes,  setClientes]  = useState([]);
  const [productos, setProductos] = useState([]);

  useEffect(() => {
    getUsuarios({ porPagina: 100 }).then(u => setClientes(u.filter(x => x.tipo === "cliente"))).catch(() => {});
    getProductos({ porPagina: 100 }).then(data => {
      const lista = (data.productos || data || []).map(p => ({
        id:          p.ID_Producto || p.id,
        nombre:      p.Nombre      || p.nombre      || "",
        precio:      p.Precio_Venta|| p.precio      || 0,
        stock:       p.Stock       || p.stock       || 0,
        stockMinimo: p.Stock_Minimo|| p.stockMinimo || 0,
        categoria:   p.nombre_categoria || p.categoria || "",
      }));
      setProductos(lista);
    }).catch(() => {});
  }, []);

  const ESTADOS_FLUJO = ["Pendiente", "En producción", "Listo", "En camino", "Entregado", "Cancelado"];
  const ESTADO_CFG = {
    "Pendiente":      { bg: "#fff8e1", color: "#f9a825", border: "#ffe082", dot: "#f9a825" },
    "En producción":  { bg: "#e3f2fd", color: "#1565c0", border: "#90caf9", dot: "#1976d2" },
    "Listo":          { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
    "En camino":      { bg: "#f3e5f5", color: "#6a1b9a", border: "#ce93d8", dot: "#8e24aa" },
    "Entregado":      { bg: "#e8f5e9", color: "#2e7d32", border: "#a5d6a7", dot: "#43a047" },
    "Cancelado":      { bg: "#ffebee", color: "#c62828", border: "#ef9a9a", dot: "#e53935" },
  };

  const permisos   = PERMISOS_POR_ESTADO[pedido.estado] || {};
  // La misma regla que decide si Gestión de pedidos muestra el botón de editar.
  const esEditable = puedeEditarsePedido(pedido.estado);

  const [form, setForm] = useState({
    idCliente:         pedido.idCliente,
    productosItems:    pedido.productosItems || [],
    metodo_pago:       pedido.metodo_pago,
    comprobante:       pedido.comprobante || null,
    comprobantePreview: pedido.comprobante || null,
    domicilio:         pedido.domicilio,
    direccion_entrega: pedido.direccion_entrega || "",
    departamento:      pedido.departamento || "",
    municipio:         pedido.municipio || "",
    // Barrio de entrega: null = conservar el snapshot congelado del pedido.
    // Al elegir uno distinto se recalcula el precio del domicilio y el Total.
    id_barrio:         null,
    id_barrio_actual:  pedido.id_barrio || null,
    cobertura_barrio:  null,
    notas:             pedido.notas || "",
    descuento:         pedido.descuento || 0,
    estadoPedido:      pedido.estado,
  });
  const [errors,          setErrors]          = useState({});
  const [saved,           setSaved]           = useState(false);
  const [editandoCliente, setEditandoCliente] = useState(false);

  // Instantánea de los datos que realmente persiste el pedido, para detectar
  // "guardar sin cambios".
  const snap = (o) => {
    const items = (o.productosItems || [])
      .map(p => ({ id: p.idProducto, c: Number(p.cantidad) || 0, precio: Number(p.precio) || 0 }))
      .sort((a, b) => String(a.id).localeCompare(String(b.id)));
    const sub  = items.reduce((a, p) => a + p.precio * p.c, 0);
    const desc = Number(o.descuento) || 0;
    return JSON.stringify({
      metodo:       (o.metodo_pago || "").split(" ")[0] || "",
      domicilio:    !!o.domicilio,
      direccion:    (o.direccion_entrega || "").trim(),
      municipio:    (o.municipio || "").trim(),
      departamento: (o.departamento || "").trim(),
      barrio:       o.id_barrio || null,
      notas:        (o.notas || "").trim(),
      descuento:    desc,
      subtotal:     sub,
      total:        Math.max(0, sub - desc),
      comprobante:  o.comprobante instanceof File ? "__nuevo__" : (o.comprobante || null),
      items,
    });
  };
  const snapshotInicial = useRef(snap({ ...pedido, comprobante: pedido.comprobante || null }));

  // Anticipo: registrar que fue recibido (cuando no se confirmó al crear)
  const [apMetodo,   setApMetodo]   = useState("");
  const [apEfectivo, setApEfectivo] = useState(false);
  const [apSaving,   setApSaving]   = useState(false);
  const [apOk,       setApOk]       = useState(pedido.anticipo_registrado || false);
  const [apErrors,   setApErrors]   = useState({});

  // Pago final (saldo del anticipo al entregar)
  const [pfMetodo,   setPfMetodo]   = useState("");
  const [pfEfectivo, setPfEfectivo] = useState(false);
  const [pfArchivo,  setPfArchivo]  = useState(null);
  const [pfPreview,  setPfPreview]  = useState(null);
  const [pfErrors,   setPfErrors]   = useState({});
  const [pfSaving,   setPfSaving]   = useState(false);
  const [pfOk,       setPfOk]       = useState(false);

  const clienteActual = clientes.find(c => c.id === form.idCliente);
  const [datosCliente, setDatosCliente] = useState(null);

  // Los pedidos en estados no editables muestran un aviso. El return va aquí,
  // después de TODOS los hooks: si se hace antes, React cuenta distinto número
  // de hooks entre renders y lanza "Rendered fewer hooks than expected".
  if (!esEditable) {
    return (
      <div className="modal-overlay">
        <div className="modal-box modal-box--sm" onClick={e => e.stopPropagation()}>
          <div style={{ padding: "28px 24px", textAlign: "center" }}>
            <div style={{
              width: 52, height: 52, borderRadius: 14,
              background: "#ffebee", border: "1px solid #ef9a9a",
              display: "flex", alignItems: "center", justifyContent: "center",
              margin: "0 auto 14px",
            }}><Ban size={24}/></div>
            <h3 style={{ margin: "0 0 8px", fontSize: 17, fontWeight: 700, fontFamily: "var(--font-head)" }}>
              No editable
            </h3>
            <p style={{ margin: "0 0 20px", fontSize: 14, color: "#616161" }}>
              Los pedidos en estado <strong>"{pedido.estado}"</strong> no se pueden editar.
            </p>
            <button className="btn-ghost" onClick={onClose}>Entendido</button>
          </div>
        </div>
      </div>
    );
  }

  const abrirEditorCliente = () => {
    if (!clienteActual) return;
    setDatosCliente({
      id:           clienteActual.id,
      nombre:       clienteActual.nombre,
      apellidos:    clienteActual.apellidos,
      correo:       clienteActual.correo,
      telefono:     clienteActual.telefono,
      direccion:    clienteActual.direccion,
      departamento: clienteActual.departamento,
      municipio:    clienteActual.municipio,
    });
    setEditandoCliente(true);
  };

  const guardarDatosCliente = async () => {
    if (!datosCliente) return;
    try {
      await editarUsuario("cliente", clienteActual.id, {
        Nombre: datosCliente.nombre, Apellidos: datosCliente.apellidos,
        Correo: datosCliente.correo, Telefono: datosCliente.telefono,
        Direccion: datosCliente.direccion, Departamento: datosCliente.departamento,
        Municipio: datosCliente.municipio,
      });
    } catch { /* silencioso — el cambio local ya se aplica */ }
    if (form.domicilio) {
      setForm(f => ({
        ...f,
        direccion_entrega: datosCliente.direccion || f.direccion_entrega,
        departamento:      datosCliente.departamento || f.departamento,
        municipio:         datosCliente.municipio || f.municipio,
      }));
    }
    setEditandoCliente(false);
    setDatosCliente(null);
  };

  const setDato = (k, v) => setDatosCliente(p => ({ ...p, [k]: v }));

  const set = (k, v) => {
    setForm(f => {
      const next = { ...f, [k]: v };
      // Si se cambia a tienda y el estado seleccionado es "En camino", retroceder a "Listo"
      if (k === "domicilio" && !v && f.estadoPedido === "En camino") {
        next.estadoPedido = "Listo";
      }
      return next;
    });
    let err = "";
    if (k === "idCliente"         && !v)        err = "Selecciona un cliente";
    if (k === "metodo_pago"       && !v)        err = "Selecciona método de pago";
    if (k === "direccion_entrega" && !v.trim()) err = "Ingresa la dirección";
    if (k === "departamento"      && !v.trim()) err = "Selecciona el departamento";
    if (k === "municipio"         && !v.trim()) err = "Selecciona el municipio";
    if (k === "descuento"         && Number(v) < 0) err = "El descuento no puede ser negativo";
    setErrors(e => {
      const next = { ...e, [k]: err };
      if (k === "domicilio") {
        next.barrio            = "";
        next.direccion_entrega = "";
        next.telefono_cliente  = "";
      }
      return next;
    });
  };

  const subtotal  = form.productosItems.reduce((a, p) => a + p.precio * p.cantidad, 0);
  const descuento = Number(form.descuento) || 0;
  // El Total que se manda al backend lleva el domicilio congelado del pedido:
  // si el barrio cambió, el backend ajusta por la diferencia (no lo hacemos
  // aquí para no contarlo dos veces). Ver editar_pedido en el servidor.
  const costoDomicilioSnapshot = form.domicilio ? (pedido.precio_domicilio_final ?? 0) : 0;
  const total     = Math.max(0, subtotal - descuento + costoDomicilioSnapshot);
  // Solo para mostrar: si el admin eligió otro barrio, el total estimado nuevo.
  const totalEstimado = form.domicilio && form.id_barrio && form.cobertura_barrio?.disponible
    ? Math.max(0, subtotal - descuento + (form.cobertura_barrio.final ?? 0))
    : total;
  const hayProductosSinStock = form.productosItems.some(p => !p.stockOk || p.cantidad > p.stockActual);

  const validate = () => {
    const e = {};
    if (permisos.cliente && !form.idCliente)                      e.idCliente         = "Selecciona un cliente";
    if (permisos.productos && form.productosItems.length === 0)   e.productos         = "Agrega al menos un producto";
    if (permisos.metodo_pago && !form.metodo_pago)                e.metodo_pago       = "Selecciona método de pago";
    
    if (form.metodo_pago?.includes("Transferencia") && !form.comprobantePreview) {
      e.comprobante = "El comprobante es obligatorio para transferencias";
    }

    if (form.domicilio) {
      if (!form.direccion_entrega.trim()) e.direccion_entrega = "Ingresa la dirección";
      // Barrio: hace falta uno si el pedido no tenía barrio congelado, o si se
      // está activando el domicilio ahora.
      if (!form.id_barrio && !form.id_barrio_actual) e.barrio = "Elige el barrio de entrega";
      if (form.id_barrio && form.cobertura_barrio && !form.cobertura_barrio.disponible)
        e.barrio = "Ese barrio no tiene cobertura de domicilio";
      const clienteTel = (clienteActual?.telefono || pedido.cliente?.telefono || "").replace(/\D/g, "");
      if (clienteTel.length !== 10) e.telefono_cliente = "El cliente debe tener un teléfono de 10 dígitos válido para pedidos con domicilio";
    }
    return e;
  };

  const handleSave = async () => {
    const e = validate();
    if (Object.keys(e).length) { setErrors(e); return; }

    if (snap(form) === snapshotInicial.current) { onSave({ sinCambios: true }); return; }

    let comprobanteUrl = typeof form.comprobante === "string" ? form.comprobante : null;
    if (form.comprobante instanceof File) {
      try {
        comprobanteUrl = await subirImagenCloudinary(form.comprobante);
      } catch (cloudErr) {
        setErrors(e => ({ ...e, comprobante: cloudErr?.message || "Error al subir el comprobante." }));
        return;
      }
    }

    setSaved(true);
    const clienteObj = clientes.find(c => c.id === form.idCliente);
    const payload = {
      id:     pedido.id,
      numero: pedido.numero,
      idCliente: form.idCliente,
      cliente: permisos.cliente && clienteObj
        ? { nombre: `${clienteObj.nombre} ${clienteObj.apellidos}`, correo: clienteObj.correo, telefono: clienteObj.telefono }
        : pedido.cliente,
      productosItems:    permisos.productos ? form.productosItems : pedido.productosItems,
      metodo_pago:       permisos.metodo_pago ? form.metodo_pago : pedido.metodo_pago,
      comprobante:       comprobanteUrl,
      domicilio:         permisos.domicilio  ? form.domicilio    : pedido.domicilio,
      direccion_entrega: form.direccion_entrega,
      // id_barrio solo se manda si cambió: el backend conserva el snapshot si no.
      id_barrio:         form.id_barrio || null,
      departamento:      form.cobertura_barrio?.departamento || form.departamento,
      municipio:         form.cobertura_barrio?.ciudad || form.municipio,
      notas:             form.notas,
      descuento:         permisos.descuento ? descuento : pedido.descuento,
      subtotal:          permisos.productos ? subtotal  : pedido.subtotal,
      total:             permisos.productos ? total     : pedido.total,
      orden_produccion:  permisos.productos ? hayProductosSinStock : pedido.orden_produccion,
      estadoPedido:      form.estadoPedido,
    };
    try {
      await onSave(payload);
    } catch {
      setSaved(false);
    }
  };

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setForm(f => ({ ...f, comprobante: file, comprobantePreview: ev.target.result }));
      setErrors(err => ({ ...err, comprobante: "" }));
    };
    reader.readAsDataURL(file);
  };

  const agregarProducto = (item) =>
    setForm(f => ({ ...f, productosItems: [...f.productosItems, item] }));
  const cambiarProducto = (idx, item) =>
    setForm(f => { const arr = [...f.productosItems]; arr[idx] = item; return { ...f, productosItems: arr }; });
  const quitarProducto  = (idx) =>
    setForm(f => ({ ...f, productosItems: f.productosItems.filter((_, i) => i !== idx) }));

  const saldoAnticipo = Math.max(0, (pedido.total ?? 0) - (pedido.anticipo_monto ?? pedido.anticipo_requerido ?? 0));
  const montoAnticipo = pedido.anticipo_monto ?? pedido.anticipo_requerido ?? 0;

  const handleRegistrarAnticipo = async () => {
    const e = {};
    if (!apMetodo) e.metodo = "Selecciona el método de pago del anticipo";
    if (apMetodo === "Efectivo" && !apEfectivo) e.efectivo = "Confirma que recibiste el anticipo en efectivo";
    if (Object.keys(e).length) { setApErrors(e); return; }
    setApSaving(true);
    try {
      await editarPedido(pedido.id, {
        Anticipo_Registrado:  true,
        Anticipo_Monto:       montoAnticipo,
        Anticipo_Metodo_Pago: apMetodo.includes("Transferencia") ? "Transferencia" : "Efectivo",
      });
      setApOk(true);
    } catch (err) {
      setApErrors(x => ({ ...x, metodo: err.message || "Error al registrar el anticipo" }));
    } finally {
      setApSaving(false);
    }
  };

  const handlePagoFinal = async () => {
    const e = {};
    if (!pfMetodo) e.metodo = "Selecciona el método de pago";
    if (pfMetodo === "Efectivo" && !pfEfectivo) e.efectivo = "Confirma que recibiste el saldo en efectivo";
    if (pfMetodo === "Transferencia" && !pfPreview) e.archivo = "Adjunta el comprobante del saldo";
    if (Object.keys(e).length) { setPfErrors(e); return; }

    setPfSaving(true);
    let comprobanteUrl = null;
    if (pfArchivo) {
      try {
        comprobanteUrl = await subirImagenCloudinary(pfArchivo);
      } catch {
        setPfErrors(x => ({ ...x, archivo: "Error al subir el comprobante. Intenta de nuevo." }));
        setPfSaving(false);
        return;
      }
    }
    try {
      const metodo_pago = pfMetodo.includes("Transferencia") ? "Transferencia" : "Efectivo";
      await registrarPagoFinal(pedido.id, { monto: saldoAnticipo, metodo_pago, comprobante_url: comprobanteUrl });
      setPfOk(true);
      onSave({ _pagoFinal: true });
    } catch (err) {
      setPfErrors({ _api: err.message || "No se pudo registrar el pago final." });
    } finally {
      setPfSaving(false);
    }
  };

  const ec = ESTADO_CFG[pedido.estado] || {};
  const restriccionesMsg = {
    "En producción": "Productos y cantidades no editables — ya están en fabricación.",
    "Listo":         "Solo se pueden modificar la dirección de entrega y las notas.",
    "En camino":     "Solo se pueden modificar la dirección de entrega y las notas.",
  };

  return (
    <div className="modal-overlay">
      <div
        className="modal-card"
        onClick={e => e.stopPropagation()}
        style={{
          maxWidth: 580,
          /* ── Clave: flex column + altura máxima ── */
          display: "flex",
          flexDirection: "column",
          maxHeight: "90vh",
          overflow: "hidden",
        }}
      >
        {/* ── Header (fijo) ── */}
        <div className="modal-header" style={{ flexShrink: 0 }}>
          <div>
            <p className="modal-header__eyebrow">Editar pedido</p>
            <h2 className="modal-header__title">{pedido.numero}</h2>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              background: ec.bg, color: ec.color, border: `1px solid ${ec.border}`,
              borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 700,
            }}>
              {pedido.estado}
            </span>
            <button className="modal-close-btn" onClick={onClose}><X size={16}/></button>
          </div>
        </div>

        {/* ── Body (scroll interno aquí) ── */}
        <div
          className="modal-body"
          style={{
            flex: 1,
            overflowY: "auto",
            overflowX: "hidden",
            padding: "20px 24px",
          }}
        >
          {restriccionesMsg[pedido.estado] && (
            <div className="info-box info-box--warn">
              <span className="info-box__icon"><AlertTriangle size={13}/></span>
              <span className="info-box__text">{restriccionesMsg[pedido.estado]}</span>
            </div>
          )}

          {/* ── Anticipo del 50% ── */}
          {pedido.requiere_anticipo && !apOk && (
            <div style={{ border: "2px solid #ff9800", borderRadius: 14, background: "#fff8e1", padding: "16px 18px", marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#e65100", marginBottom: 10, display:"flex",alignItems:"center",gap:6 }}><AlertTriangle size={14}/> Registrar anticipo del 50%</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                <div style={{ background: "#fff3e0", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                  <div style={{ fontSize: 10, color: "#f57c00", fontWeight: 700, textTransform: "uppercase" }}>Total pedido</div>
                  <div style={{ fontSize: 15, fontWeight: 900, color: "#333" }}>{fmt(pedido.total ?? 0)}</div>
                </div>
                <div style={{ background: "#e8f5e9", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                  <div style={{ fontSize: 10, color: "#4caf50", fontWeight: 700, textTransform: "uppercase" }}>Anticipo (50%)</div>
                  <div style={{ fontSize: 15, fontWeight: 900, color: "#2e7d32" }}>{fmt(montoAnticipo)}</div>
                </div>
              </div>
              <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 700, color: "#555" }}>Método de pago del anticipo <span style={{ color: "#e53935" }}>*</span></p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                {["Efectivo", "Transferencia"].map(m => (
                  <button key={m} type="button" onClick={() => { setApMetodo(m); setApEfectivo(false); setApErrors({}); }}
                    style={{ padding: "10px 8px", borderRadius: 10, border: `2px solid ${apMetodo === m ? "#f57c00" : "#e0e0e0"}`, background: apMetodo === m ? "#fff3e0" : "#fff", color: apMetodo === m ? "#e65100" : "#888", fontWeight: apMetodo === m ? 700 : 500, fontSize: 12, cursor: "pointer" }}>
                    {m}
                  </button>
                ))}
              </div>
              {apMetodo === "Efectivo" && (
                <label style={{ display: "flex", gap: 10, alignItems: "center", cursor: "pointer", background: apEfectivo ? "#f1f8f1" : "#fafafa", padding: "10px 12px", borderRadius: 8, border: `2px solid ${apEfectivo ? "#2e7d32" : "#e0e0e0"}`, marginBottom: 8 }}>
                  <input type="checkbox" checked={apEfectivo} onChange={e => { setApEfectivo(e.target.checked); setApErrors(x => ({ ...x, efectivo: "" })); }} style={{ width: 16, height: 16, accentColor: "#2e7d32" }} />
                  <span style={{ fontSize: 12, color: apEfectivo ? "#1b5e20" : "#555", fontWeight: apEfectivo ? 700 : 400 }}>
                    Confirmo que recibí <strong>{fmt(montoAnticipo)}</strong> en efectivo
                  </span>
                </label>
              )}
              {apMetodo === "Transferencia" && (
                <p style={{ fontSize: 11, color: "#666", background: "#f5f5f5", padding: "8px 10px", borderRadius: 6, marginBottom: 8 }}>
                  Sube el comprobante usando el botón de la tabla después de guardar.
                </p>
              )}
              {(apErrors.metodo || apErrors.efectivo) && (
                <p style={{ fontSize: 11, color: "#e53935", margin: "0 0 8px" }}>{apErrors.metodo || apErrors.efectivo}</p>
              )}
              <button type="button" onClick={handleRegistrarAnticipo} disabled={apSaving}
                style={{ width: "100%", padding: "11px 0", borderRadius: 8, border: "none", background: apSaving ? "#bdbdbd" : "#ff9800", color: "#fff", fontWeight: 800, fontSize: 13, cursor: apSaving ? "not-allowed" : "pointer" }}>
                {apSaving ? "Registrando…" : `Confirmar anticipo ${fmt(montoAnticipo)}`}
              </button>
            </div>
          )}
          {pedido.requiere_anticipo && apOk && (
            <div style={{ border: "1.5px solid #a5d6a7", borderRadius: 12, background: "#e8f5e9", padding: "12px 16px", display: "flex", gap: 10, alignItems: "center", marginBottom: 16 }}>
              <CheckCircle2 size={20} style={{color:"#2e7d32",flexShrink:0}}/>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#2e7d32" }}>Anticipo registrado</div>
                <div style={{ fontSize: 11, color: "#4caf50" }}>50% — {fmt(montoAnticipo)}</div>
              </div>
            </div>
          )}

          {/* ── Pago final (saldo del anticipo) ── */}
          {pedido.requiere_anticipo && !pedido.pago_final_registrado && !pfOk && (
            <div style={{ border: "2px solid #f9a825", borderRadius: 14, background: "#fffdf0", padding: "16px 18px", marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#e65100", marginBottom: 12, display:"flex",alignItems:"center",gap:6 }}>
                <CreditCard size={14}/> Registrar pago del saldo restante
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                <div style={{ background: "#f5f5f5", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                  <div style={{ fontSize: 10, color: "#999", fontWeight: 700, textTransform: "uppercase" }}>Total</div>
                  <div style={{ fontSize: 15, fontWeight: 900, color: "#333" }}>{fmt(pedido.total ?? 0)}</div>
                </div>
                <div style={{ background: "#e8f5e9", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
                  <div style={{ fontSize: 10, color: "#4caf50", fontWeight: 700, textTransform: "uppercase" }}>Anticipo</div>
                  <div style={{ fontSize: 15, fontWeight: 900, color: "#2e7d32" }}>{fmt(pedido.anticipo_monto ?? pedido.anticipo_requerido ?? 0)}</div>
                </div>
              </div>
              <div style={{ background: "#fff3e0", border: "1.5px solid #f9a825", borderRadius: 8, padding: "10px 14px", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#e65100" }}>Saldo a cobrar</span>
                <span style={{ fontSize: 18, fontWeight: 900, color: "#e65100" }}>{fmt(saldoAnticipo)}</span>
              </div>

              <p style={{ margin: "0 0 6px", fontSize: 12, fontWeight: 700, color: "#555" }}>Método <span style={{ color: "#e53935" }}>*</span></p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                {["Efectivo", "Transferencia"].map(m => (
                  <button key={m} type="button"
                    onClick={() => { setPfMetodo(m); setPfEfectivo(false); setPfArchivo(null); setPfPreview(null); setPfErrors({}); }}
                    style={{ padding: "10px 8px", borderRadius: 8, border: `2px solid ${pfMetodo === m ? "#f9a825" : "#e0e0e0"}`, background: pfMetodo === m ? "#fff8e1" : "#fff", color: pfMetodo === m ? "#e65100" : "#888", fontWeight: pfMetodo === m ? 700 : 500, fontSize: 13, cursor: "pointer" }}>
                    {m}
                  </button>
                ))}
              </div>
              {pfErrors.metodo && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginBottom: 6 }}>{pfErrors.metodo}</span>}

              {pfMetodo === "Efectivo" && (
                <label style={{ display: "flex", gap: 10, alignItems: "center", cursor: "pointer", background: pfEfectivo ? "#f1f8f1" : "#fafafa", padding: "10px 12px", borderRadius: 8, border: `2px solid ${pfEfectivo ? "#2e7d32" : "#e0e0e0"}`, marginBottom: 8 }}>
                  <input type="checkbox" checked={pfEfectivo} onChange={e => { setPfEfectivo(e.target.checked); setPfErrors(x => ({ ...x, efectivo: "" })); }} style={{ width: 16, height: 16, accentColor: "#2e7d32" }} />
                  <span style={{ fontSize: 12, color: pfEfectivo ? "#1b5e20" : "#555", fontWeight: pfEfectivo ? 700 : 400 }}>Confirmo que recibí <strong>{fmt(saldoAnticipo)}</strong> en efectivo</span>
                </label>
              )}
              {pfErrors.efectivo && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginBottom: 6 }}>{pfErrors.efectivo}</span>}

              {pfMetodo === "Transferencia" && (
                pfPreview ? (
                  <div style={{ position: "relative", height: 100, borderRadius: 8, overflow: "hidden", background: "#000", marginBottom: 8 }}>
                    <img src={pfPreview} alt="Comprobante saldo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                    <button type="button" style={{ position: "absolute", top: 5, right: 5, background: "rgba(0,0,0,0.6)", color: "#fff", border: "none", borderRadius: "50%", width: 24, height: 24, cursor: "pointer", display:"flex",alignItems:"center",justifyContent:"center" }} onClick={() => { setPfArchivo(null); setPfPreview(null); }}><X size={12}/></button>
                  </div>
                ) : (
                  <label style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 80, borderRadius: 8, border: `2px dashed ${pfErrors.archivo ? "#e53935" : "#f9a825"}`, background: "#fffdf0", cursor: "pointer", marginBottom: 8 }}>
                    <input type="file" accept="image/*" onChange={e => { const f = e.target.files[0]; if (!f) return; const r = new FileReader(); r.onload = ev => { setPfArchivo(f); setPfPreview(ev.target.result); setPfErrors(x => ({ ...x, archivo: "" })); }; r.readAsDataURL(f); }} hidden />
                    <Paperclip size={20} style={{color:"#f9a825"}}/>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#f9a825" }}>Comprobante del saldo</span>
                  </label>
                )
              )}
              {pfErrors.archivo && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginBottom: 6 }}>{pfErrors.archivo}</span>}
              {pfErrors._api && <span style={{ fontSize: 11, color: "#e53935", display: "block", marginBottom: 6 }}>{pfErrors._api}</span>}

              <button type="button" onClick={handlePagoFinal} disabled={pfSaving}
                style={{ width: "100%", padding: "11px 0", borderRadius: 8, border: "none", background: pfSaving ? "#bdbdbd" : "#f9a825", color: "#fff", fontWeight: 800, fontSize: 13, cursor: pfSaving ? "not-allowed" : "pointer" }}>
                {pfSaving ? "Registrando…" : `Registrar saldo ${fmt(saldoAnticipo)}`}
              </button>
            </div>
          )}

          {pedido.requiere_anticipo && (pedido.pago_final_registrado || pfOk) && (
            <div style={{ border: "1.5px solid #a5d6a7", borderRadius: 12, background: "#e8f5e9", padding: "12px 16px", display: "flex", gap: 10, alignItems: "center", marginBottom: 16 }}>
              <CheckCircle2 size={20} style={{color:"#2e7d32",flexShrink:0}}/>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#2e7d32" }}>Pago final registrado</div>
                <div style={{ fontSize: 11, color: "#4caf50" }}>Saldo {fmt(pedido.pago_final_monto ?? saldoAnticipo)} — {pedido.pago_final_metodo_pago || "—"}</div>
              </div>
            </div>
          )}

          {/* ── Cliente ── */}
          <p className="section-label" style={{ textTransform: "none" }}>Cliente</p>
          {permisos.cliente ? (
            <>
              {!editandoCliente && (
                <>
                  <SearchableSelect
                    options={clientes}
                    value={form.idCliente || ""}
                    onChange={e => {
                      const id  = e.target.value;
                      const cli = clientes.find(c => c.id === id);
                      set("idCliente", id);
                      if (cli && form.domicilio) set("direccion_entrega", cli.direccion || "");
                    }}
                    getValue={c => c.id}
                    getLabel={c => `${c.nombre} ${c.apellidos} — ${c.correo}`}
                    placeholder="Seleccione un cliente…"
                    searchPlaceholder="Buscar cliente…"
                    className={`field-select${errors.idCliente ? " error" : ""}`}
                  />
                  {errors.idCliente && <span className="field-error">{errors.idCliente}</span>}

                  {clienteActual && (
                    <div style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      gap: 10, marginTop: 8,
                      padding: "10px 14px",
                      borderRadius: 10,
                      background: "#f9f9f9",
                      border: "1px solid #ebebeb",
                    }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#212121", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {clienteActual.nombre} {clienteActual.apellidos}
                        </span>
                        <span style={{ fontSize: 11, color: "#9e9e9e" }}>
                          {clienteActual.telefono || "Sin teléfono"} · {clienteActual.municipio || "Sin ciudad"}
                        </span>
                        {clienteActual.direccion && form.domicilio && (
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                            <span style={{ fontSize: 11, color: "#757575", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {clienteActual.direccion}
                            </span>
                            <button
                              onClick={() => set("direccion_entrega", clienteActual.direccion)}
                              style={{
                                flexShrink: 0, fontSize: 10, fontWeight: 700,
                                padding: "1px 7px", borderRadius: 5,
                                border: "1px solid #c8e6c9", background: "#f1f8e9",
                                color: "#388e3c", cursor: "pointer", fontFamily: "inherit",
                              }}
                            >Usar ↓</button>
                          </div>
                        )}
                      </div>
                      <button
                        onClick={abrirEditorCliente}
                        style={{
                          flexShrink: 0, padding: "6px 12px", borderRadius: 8,
                          border: "1px solid #e0e0e0", background: "#fff",
                          color: "#616161", fontSize: 12, fontWeight: 600,
                          cursor: "pointer", fontFamily: "inherit",
                        }}
                      >
                        Editar
                      </button>
                    </div>
                  )}
                </>
              )}

              {editandoCliente && datosCliente && (
                <div style={{
                  border: "1.5px solid #ffe082", borderRadius: 12,
                  background: "#fffdf0", padding: "16px",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#f9a825", textTransform: "uppercase", letterSpacing: "0.8px", display:"flex",alignItems:"center",gap:6 }}>
                      <PenLine size={13}/> Editando datos de {clienteActual?.nombre}
                    </div>
                    <button
                      onClick={() => { setEditandoCliente(false); setDatosCliente(null); }}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "#9e9e9e" }}
                    ><X size={14}/></button>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    {[
                      { k: "nombre",    label: "Nombre",    ph: "Ej. Ana"          },
                      { k: "apellidos", label: "Apellidos", ph: "Ej. García López" },
                    ].map(({ k, label, ph }) => (
                      <div key={k} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <label className="form-label">{label}</label>
                        <input className="field-input" value={datosCliente[k] || ""} onChange={e => setDato(k, soloLetras(e.target.value))} placeholder={ph} />
                      </div>
                    ))}
                    <div style={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: 4 }}>
                      <label className="form-label">Correo</label>
                      <input className="field-input" type="email" value={datosCliente.correo || ""} onChange={e => setDato("correo", e.target.value)} placeholder="correo@ejemplo.com" />
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label className="form-label">Teléfono</label>
                      <input className="field-input" value={datosCliente.telefono || ""} onChange={e => setDato("telefono", soloDigitos(e.target.value, 10))} placeholder="300 000 0000" inputMode="numeric" />
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label className="form-label">Municipio</label>
                      <SearchableSelect
                        options={MUNICIPIOS_VALLE_ABURRA.map(m => ({ value: m, label: m }))}
                        value={datosCliente.municipio || ""}
                        onChange={e => { setDato("municipio", e.target.value); setDato("departamento", "Antioquia"); }}
                        getValue={o => o.value}
                        getLabel={o => o.label}
                        placeholder="— Valle de Aburrá —"
                        searchPlaceholder="Buscar municipio…"
                        className="field-select"
                      />
                    </div>
                    <div style={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: 4 }}>
                      <label className="form-label">
                        Dirección
                        {form.domicilio && (
                          <span style={{ color: "#9e9e9e", fontWeight: 400, marginLeft: 6, fontSize: 10 }}>
                            — al guardar se actualiza la dirección de entrega
                          </span>
                        )}
                      </label>
                      <input className="field-input" value={datosCliente.direccion || ""} onChange={e => setDato("direccion", e.target.value)} placeholder="Ej. Cra 5 #12-34, Apto 201" />
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
                    <button className="btn-ghost" onClick={() => { setEditandoCliente(false); setDatosCliente(null); }}>Cancelar</button>
                    <button className="btn-save" onClick={guardarDatosCliente} style={{display:"flex",alignItems:"center",gap:6}}><Check size={14}/> Guardar datos</button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <FieldReadOnly label="Cliente" value={pedido.cliente?.nombre} />
          )}

          {/* ── Productos ── */}
          <p className="section-label" style={{ textTransform: "none" }}>Productos</p>
          {permisos.productos ? (
            <>
              <BuscadorProducto productosSeleccionados={form.productosItems} onAgregar={agregarProducto} productos={productos} />
              {errors.productos && <span className="field-error" style={{ marginTop: -4 }}>{errors.productos}</span>}
              {form.productosItems.length > 0 && (
                <div className="productos-list">
                  {form.productosItems.map((item, idx) => (
                    <ProductoItemEditable key={item.idProducto} item={item} onChange={v => cambiarProducto(idx, v)} onRemove={() => quitarProducto(idx)} />
                  ))}
                </div>
              )}
              {hayProductosSinStock && (
                <div className="info-box info-box--warn">
                  <span className="info-box__icon"><AlertTriangle size={13}/></span>
                  <div className="info-box__text">
                    <span className="info-box__label">Hay productos sin stock suficiente</span>
                    Se generará una orden de producción al guardar.
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="productos-list">
              {pedido.productosItems.map((item) => (
                <ProductoItemFijo key={item.idProducto} item={item} />
              ))}
            </div>
          )}

          {/* ── Descuento y totales ── */}
          {(permisos.productos || permisos.descuento) && (
            <div className="form-grid-2" style={{ alignItems: "end" }}>
              <div className="field-wrap">
                <label className="field-label">
                  Descuento (COP)
                  {!permisos.descuento && <span style={{ marginLeft: 6, fontSize: 10, color: "#9e9e9e", fontWeight: 400 }}>— bloqueado</span>}
                </label>
                <input
                  type="number" min={0}
                  className="field-input"
                  value={permisos.descuento ? form.descuento : pedido.descuento}
                  onChange={e => permisos.descuento && set("descuento", e.target.value)}
                  readOnly={!permisos.descuento}
                  style={!permisos.descuento ? { background: "#fafafa", color: "#9e9e9e" } : {}}
                />
              </div>
              <div className="totales-box">
                <div className="totales-row"><span>Subtotal</span><span>{fmt(permisos.productos ? subtotal : pedido.subtotal)}</span></div>
                {(permisos.descuento ? descuento : pedido.descuento) > 0 && (
                  <div className="totales-row totales-row--descuento">
                    <span>Descuento</span>
                    <span>− {fmt(permisos.descuento ? descuento : pedido.descuento)}</span>
                  </div>
                )}
                {form.domicilio && (
                  <div className="totales-row">
                    <span>Domicilio {pedido.barrio_entrega ? `· ${pedido.barrio_entrega}` : ""}</span>
                    <span>{fmt(costoDomicilioSnapshot)}</span>
                  </div>
                )}
                <div className="totales-row totales-row--total">
                  <span>Total</span>
                  <span>{fmt(permisos.productos ? totalEstimado : pedido.total)}</span>
                </div>
              </div>
            </div>
          )}

          {/* ── Método de pago y entrega ── */}
          <p className="section-label" style={{ textTransform: "none" }}>Pago y entrega</p>
          <div className="form-grid-2">
            {permisos.metodo_pago ? (
              <div className="field-wrap">
                <label className="field-label">Método de pago <span className="required">*</span></label>
                <SearchableSelect
                  options={METODOS_PAGO.map(m => ({ value: m, label: m }))}
                  value={form.metodo_pago}
                  onChange={e => set("metodo_pago", e.target.value)}
                  getValue={o => o.value}
                  getLabel={o => o.label}
                  placeholder="Seleccione…"
                  searchPlaceholder="Método…"
                  className={`field-select${errors.metodo_pago ? " error" : ""}`}
                />
                {errors.metodo_pago && <span className="field-error">{errors.metodo_pago}</span>}
              </div>
            ) : (
              <FieldReadOnly label="Método de pago" value={pedido.metodo_pago} />
            )}

            {permisos.domicilio ? (
              <div className="field-wrap">
                <label className="field-label">Tipo de entrega</label>
                <div style={{ display: "flex", gap: 8, paddingTop: 4 }}>
                  {[
                    { val: false, label: "Tienda",    Icon: Store },
                    { val: true,  label: "Domicilio", Icon: Bike },
                  ].map(opt => (
                    <button
                      key={String(opt.val)}
                      onClick={() => set("domicilio", opt.val)}
                      style={{
                        flex: 1, padding: "8px 10px", borderRadius: 9, cursor: "pointer",
                        fontFamily: "inherit", fontSize: 12, fontWeight: 700,
                        border: form.domicilio === opt.val ? "2px solid #2e7d32" : "1.5px solid #e0e0e0",
                        background: form.domicilio === opt.val ? "#e8f5e9" : "#fff",
                        color:      form.domicilio === opt.val ? "#2e7d32"  : "#616161",
                        transition: "all 0.15s",
                      }}
                    >
                      <opt.Icon size={14}/> {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <FieldReadOnly label="Tipo de entrega" value={pedido.domicilio ? "Domicilio" : "Tienda"} />
            )}
          </div>

          {form.metodo_pago?.includes("Transferencia") && permisos.metodo_pago && (
            <div className="field-wrap" style={{ marginTop: 12 }}>
              <label className="field-label">Comprobante de pago <span className="required">*</span></label>
              {pedido.estado === "Pendiente" && pedido.requiereFechaPropuesta ? (
                <div style={{ padding: "12px 14px", background: "#fff8e1", border: "1.5px solid #ffe082", borderRadius: 10, display: "flex", alignItems: "center", gap: 8 }}>
                  <Calendar size={16} color="#f57f17" />
                  <span style={{ fontSize: 12, color: "#e65100", fontWeight: 600 }}>
                    Debes confirmar la fecha de entrega antes de subir el comprobante de pago.
                  </span>
                </div>
              ) : (
                <>
                  <div className="comprobante-upload">
                    {form.comprobantePreview ? (
                      <div className="comprobante-preview-wrap">
                        <ImageLightbox
                          src={form.comprobantePreview}
                          alt="Comprobante"
                          label="Ver imagen completa"
                          thumbStyle={{ width: "100%", maxHeight: 200, objectFit: "contain", borderRadius: 8, background: "#000", cursor: "zoom-in" }}
                        />
                        <button className="comprobante-remove-btn" onClick={() => setForm(f => ({ ...f, comprobante: null, comprobantePreview: null }))}><X size={14}/></button>
                      </div>
                    ) : (
                      <label className={`comprobante-dropzone${errors.comprobante ? " error" : ""}`}>
                        <input type="file" accept="image/*" onChange={handleFile} hidden />
                        <Upload size={24} style={{color:"#9e9e9e"}}/>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>Subir comprobante</span>
                        <span style={{ fontSize: 10, color: "#9e9e9e" }}>JPG, PNG o WEBP</span>
                      </label>
                    )}
                  </div>
                  {errors.comprobante && <span className="field-error">{errors.comprobante}</span>}

                  {/* Aprobar/Rechazar cuando el comprobante está en revisión */}
                  {pedido.comprobante && pedido.estado_pago === "pendiente_validacion" && onAprobarComprobante && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                      <button
                        type="button"
                        onClick={() => onRechazarComprobante(pedido)}
                        style={{ flex: 1, padding: '9px 0', borderRadius: 9, border: 'none', background: '#c62828', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}
                      >
                        <Ban size={13} /> Rechazar
                      </button>
                      <button
                        type="button"
                        onClick={() => onAprobarComprobante(pedido)}
                        style={{ flex: 1, padding: '9px 0', borderRadius: 9, border: 'none', background: '#2e7d32', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}
                      >
                        <Check size={13} /> Aprobar comprobante
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── Dirección ── */}
          {(pedido.domicilio || form.domicilio) && (
            permisos.direccion_entrega ? (
              <>
                {errors.telefono_cliente && (
                  <div style={{ padding: "10px 14px", background: "#ffebee", borderRadius: 10, border: "1px solid #ef9a9a", color: "#c62828", fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
                    <AlertTriangle size={14} style={{marginRight:6}}/> {errors.telefono_cliente}
                  </div>
                )}
                <div className="field-wrap">
                  <label className="field-label">
                    Dirección de entrega {form.domicilio && <span className="required">*</span>}
                  </label>
                  <input
                    className={`field-input${errors.direccion_entrega ? " error" : ""}`}
                    placeholder="Ej: Cra 5 #12-34, Apto 201"
                    value={form.direccion_entrega}
                    onChange={e => set("direccion_entrega", e.target.value)}
                    onBlur={e => {
                      if (!e.target.value.trim())
                        setErrors(p => ({ ...p, direccion_entrega: "Ingresa la dirección" }));
                    }}
                  />
                  {errors.direccion_entrega && <span className="field-error">{errors.direccion_entrega}</span>}
                </div>

                <div className="field-wrap" style={{ marginTop: 12 }}>
                  <label className="field-label">
                    Barrio de entrega {form.domicilio && <span className="required">*</span>}
                  </label>
                  {form.id_barrio_actual && !form.id_barrio && (
                    <p style={{ fontSize: 12, color: "#757575", margin: "0 0 6px" }}>
                      Barrio actual: <strong>{pedido.barrio_entrega || "—"}</strong>
                      {pedido.precio_domicilio_final != null && ` · domicilio ${fmt(pedido.precio_domicilio_final)}`}.
                      Elige otro solo si quieres cambiarlo (se recalcula el precio).
                    </p>
                  )}
                  <SelectorBarrioEntrega
                    prefillIdBarrio={form.id_barrio_actual}
                    onChange={(id, cob) => {
                      // Solo cuenta como cambio si es un barrio distinto al
                      // congelado en el pedido (el prefill vuelve a seleccionar
                      // el actual y eso no debe disparar recálculo ni "cambios").
                      setForm(f => ({
                        ...f,
                        id_barrio: (id && id !== f.id_barrio_actual) ? id : null,
                        cobertura_barrio: cob,
                      }));
                      setErrors(err => ({ ...err, barrio: "" }));
                    }}
                  />
                  {errors.barrio && <span className="field-error">{errors.barrio}</span>}
                </div>
              </>
            ) : (
              <FieldReadOnly label="Dirección de entrega" value={`${pedido.direccion_entrega}, ${pedido.municipio}, ${pedido.departamento}`} />
            )
          )}

          {/* ── Notas ── */}
          {permisos.notas ? (
            <div className="field-wrap">
              <label className="field-label">Notas del pedido</label>
              <textarea
                className="field-textarea"
                rows={2}
                placeholder="Indicaciones especiales, alergias, personalización…"
                value={form.notas}
                onChange={e => set("notas", e.target.value)}
              />
            </div>
          ) : pedido.notas ? (
            <FieldReadOnly label="Notas" value={pedido.notas} />
          ) : null}

          {/* ── Estado del pedido ── */}
          <p className="section-label" style={{ textTransform: "none" }}>Estado del pedido</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(() => {
              const actualIdx = ESTADOS_FLUJO.indexOf(pedido.estado);
              const validos   = ESTADOS_FLUJO.filter((e, i) => {
                if (e === "En camino" && !form.domicilio) return false;
                if (e === "Cancelado") return !["Entregado", "Cancelado"].includes(pedido.estado);
                return i >= actualIdx;
              });
              return validos.map(e => {
                const c   = ESTADO_CFG[e] || {};
                const sel = form.estadoPedido === e;
                return (
                  <button key={e} onClick={() => set("estadoPedido", e)} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "10px 14px", borderRadius: 10, cursor: "pointer",
                    fontFamily: "inherit", width: "100%", textAlign: "left",
                    border: sel ? `2px solid ${c.border}` : "1.5px solid #e0e0e0",
                    background: sel ? c.bg : "#fff", transition: "all 0.15s",
                  }}>
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: c.dot, flexShrink: 0 }} />
                    <span style={{ fontSize: 13, fontWeight: sel ? 700 : 500, color: sel ? c.color : "#424242", flex: 1 }}>
                      {e}
                    </span>
                    {e === pedido.estado && (
                      <span style={{ fontSize: 10, color: "#9e9e9e", fontWeight: 600 }}>actual</span>
                    )}
                  </button>
                );
              });
            })()}
          </div>
          {form.estadoPedido === "Cancelado" && pedido.estado !== "Cancelado" && (
            <div className="info-box info-box--danger">
              <span className="info-box__icon"><AlertTriangle size={13}/></span>
              <span className="info-box__text">Esta acción restaurará el stock de los productos.</span>
            </div>
          )}
        </div>{/* /modal-body */}

        {/* ── Footer (fijo) ── */}
        <div
          className="modal-footer"
          style={{ flexShrink: 0, borderTop: "1px solid #f5f5f5" }}
        >
          <button className="btn-cancel" onClick={onClose}>Cancelar</button>
          <button className="btn-save" onClick={handleSave} disabled={saved}>
            {saved ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>

        {saved && (
          <div className="modal-success-toast" style={{display:"flex",alignItems:"center",gap:6}}>
            <Check size={14}/>
            <span>Pedido actualizado con éxito</span>
          </div>
        )}
      </div>
    </div>
  );
}
