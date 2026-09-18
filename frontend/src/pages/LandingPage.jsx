import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShoppingBag, Leaf, Sparkles,
  Plus, Minus, ShoppingCart, CheckCircle2, X, ChevronLeft, ChevronRight, Eye,
} from 'lucide-react';
import { getUser } from '../services/authService.js';
import { API_URL } from '../config/api.js';
import { useNotificaciones, TIPOS } from '../features/notificaciones/context/NotificacionesContext.jsx';
import Navbar from '../shared/components/Navbar.jsx';
import Footer from '../shared/components/Footer.jsx';

import CartAside from '../features/sales/orders/components/CartAside';
import CheckoutModal from '../features/sales/orders/components/CheckoutModal';
import { crearPedidoCliente } from '../features/sales/orders/services/crearPedidoCliente';
import {
  addToCartWithQty,
  getCart,
  saveCart,
  getCartCount,
  sanitizeCart,
  clearCart
} from '../features/sales/orders/services/cartService';
import { getLandingConfig, LANDING_DEFAULTS } from '../services/landingConfigService';
import { formatCOP } from '../utils/formato';
import { MAX_QTY } from '../features/sales/orders/services/cartService';
import { urlProductImg, urlProductImgSrcset } from '../utils/avatar';

/** Input de cantidad editable por teclado (máx. 4 dígitos). */
function QtyInput({ value, onChange, className = '' }) {
  const [draft, setDraft] = useState(null);
  return (
    <input
      type="text"
      inputMode="numeric"
      maxLength={4}
      value={draft ?? String(value)}
      onChange={e => setDraft(e.target.value.replace(/\D/g, '').slice(0, 4))}
      onBlur={() => {
        const n = Math.min(MAX_QTY, Math.max(1, parseInt(draft ?? '', 10) || 1));
        setDraft(null);
        onChange(n);
      }}
      onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }}
      className={className}
    />
  );
}

/* ═══════════════════════════════════════════
   PRODUCT DETAIL MODAL
═══════════════════════════════════════════ */
function ProductDetailModal({ product, cat, onClose, onAddToCart }) {
  const [imgIdx, setImgIdx] = useState(0);
  const [qty, setQty]       = useState(1);

  const imgs    = product.imagenes?.length > 0 ? product.imagenes : (product.imagen ? [product.imagen] : []);
  const agotado = product.stock === 0;
  const stock   = product.stock ?? 0;
  const parcial = !agotado && qty > stock && stock > 0;
  // Sin stock pero producible: se puede pedir igual (se hornea bajo pedido),
  // así que el mensaje debe invitar a pedir, no sonar a "no disponible".
  const sinStockProducible   = agotado && !!product.requiereProduccion;
  const sinStockNoProducible = agotado && !product.requiereProduccion;

  // Cerrar con Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  // Bloquear scroll del fondo
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  const prev = () => setImgIdx(i => (i - 1 + imgs.length) % imgs.length);
  const next = () => setImgIdx(i => (i + 1) % imgs.length);

  // El padre controla si cierra el modal (según stock check)
  const handleAdd = () => { onAddToCart(product, qty); };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        className="relative bg-white w-full sm:max-w-4xl sm:rounded-[32px] rounded-t-[36px] overflow-hidden shadow-2xl flex flex-col md:flex-row pdm-animate"
        style={{ maxHeight: '92vh' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Cerrar */}
        <button
          onClick={onClose}
          data-tooltip="Cerrar"
          className="absolute top-4 right-4 z-20 w-10 h-10 bg-black/20 backdrop-blur-sm rounded-full flex items-center justify-center text-white hover:bg-black/35 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* ── Galería ── */}
        <div className="md:w-[44%] flex-shrink-0 bg-[#f7faf8] flex flex-col">
          {/* Imagen principal */}
          <div className="relative flex-1" style={{ minHeight: 280, maxHeight: 420 }}>
            {imgs.length > 0 ? (
              <img
                src={urlProductImg(imgs[imgIdx], 1200)}
                srcSet={urlProductImgSrcset(imgs[imgIdx], [600, 1200])}
                sizes="(max-width:640px) 100vw, 50vw"
                alt={product.nombre}
                loading="lazy"
                decoding="async"
                className="w-full h-full object-cover"
                style={{ maxHeight: 420 }}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ minHeight: 280 }}>
                <span className="text-9xl">{cat?.icon || '🍌'}</span>
              </div>
            )}

            {/* Flechas */}
            {imgs.length > 1 && (
              <>
                <button onClick={(e) => { e.stopPropagation(); prev(); }} data-tooltip="Imagen anterior" className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/90 backdrop-blur-sm rounded-full flex items-center justify-center shadow-lg hover:bg-white transition-colors text-[#1b5e20] z-10">
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <button onClick={(e) => { e.stopPropagation(); next(); }} data-tooltip="Imagen siguiente" className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/90 backdrop-blur-sm rounded-full flex items-center justify-center shadow-lg hover:bg-white transition-colors text-[#1b5e20] z-10">
                  <ChevronRight className="w-5 h-5" />
                </button>
                {/* Dots */}
                <div className="absolute bottom-3 left-0 right-0 flex justify-center gap-1.5">
                  {imgs.map((_, i) => (
                    <button key={i} onClick={() => setImgIdx(i)}
                      className={`rounded-full transition-all ${i === imgIdx ? 'bg-white w-5 h-2' : 'bg-white/50 w-2 h-2'}`}
                    />
                  ))}
                </div>
              </>
            )}

          </div>

          {/* Thumbnails */}
          {imgs.length > 1 && (
            <div className="flex gap-2 p-3 overflow-x-auto bg-white border-t border-[#f0f0f0]">
              {imgs.map((url, i) => (
                <button
                  key={i}
                  onClick={() => setImgIdx(i)}
                  data-tooltip="Ver imagen"
                  className={`flex-shrink-0 w-14 h-14 rounded-xl overflow-hidden border-2 transition-all ${
                    i === imgIdx ? 'border-[#1b5e20] scale-95' : 'border-transparent opacity-50 hover:opacity-80'
                  }`}
                >
                  <img src={urlProductImg(url, 200)} alt="" loading="lazy" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Info ── */}
        <div className="flex-1 overflow-y-auto flex flex-col p-7 gap-5 min-w-0">
          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-3 py-1 bg-[#e8f5e9] text-[#1b5e20] rounded-lg text-xs font-black uppercase tracking-widest">
              {cat?.icon} {cat?.nombre || 'Producto'}
            </span>
            {!agotado && product.stock <= 10 && (
              <span className="px-3 py-1 bg-amber-50 text-amber-700 rounded-lg text-xs font-black border border-amber-100">
                ¡Solo {product.stock} disponibles!
              </span>
            )}
          </div>

          {/* Nombre + Precio */}
          <div>
            <h2 className="text-3xl font-black text-[#1b5e20] leading-tight mb-2">{product.nombre}</h2>
            <p className="text-4xl font-black text-[#4caf50]">
              {formatCOP(product.precio)}
            </p>
          </div>

          {/* Descripciones */}
          {(product.descripcion_corta || product.descripcion_larga) ? (
            <div className="space-y-3">
              {product.descripcion_corta && (
                <p className="text-[#424242] font-medium leading-relaxed">{product.descripcion_corta}</p>
              )}
              {product.descripcion_larga && (
                <p className="text-[#757575] text-sm leading-relaxed">{product.descripcion_larga}</p>
              )}
            </div>
          ) : (
            <p className="text-[#9e9e9e] text-sm">Sabor auténtico y natural en cada bocado.</p>
          )}

          {/* Info de stock */}
          {sinStockNoProducible && (
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
              <p className="font-black text-amber-700 text-sm mb-1">⏳ Sin stock inmediato</p>
              <p className="text-amber-600 text-xs leading-relaxed">Este producto no está disponible para entrega inmediata. Al pedirlo lo recibirás cuando haya producción disponible.</p>
            </div>
          )}
          {sinStockProducible && (
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
              <p className="font-black text-amber-700 text-sm mb-1">🧡 Se prepara especialmente para ti</p>
              <p className="text-amber-600 text-xs leading-relaxed">Este producto se hornea bajo pedido. Pídelo ahora y te avisamos en cuanto esté listo.</p>
            </div>
          )}
          {parcial && (
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
              <p className="font-black text-amber-700 text-sm mb-1">⚠️ Stock parcial</p>
              <p className="text-amber-600 text-xs leading-relaxed">
                Solo hay <strong>{stock}</strong> unidades disponibles ahora. Las otras <strong>{qty - stock}</strong> se confirmarán como pedido programado al continuar.
              </p>
            </div>
          )}

          {/* Selector de cantidad + botón */}
          <div className="mt-auto pt-2">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1 bg-[#f7faf8] rounded-2xl border border-[#e8f5e9] p-1.5 flex-shrink-0">
                <button onClick={() => setQty(q => Math.max(1, q - 1))} aria-label="Disminuir cantidad" data-tooltip="Disminuir cantidad"
                  className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-[#e8f5e9] transition-colors active:scale-90 text-[#1b5e20] font-bold text-lg">−</button>
                <QtyInput
                  value={qty}
                  onChange={setQty}
                  className="w-10 text-center font-black text-[#1b5e20] text-sm bg-transparent border-none outline-none"
                />
                <button onClick={() => setQty(q => Math.min(MAX_QTY, q + 1))} aria-label="Aumentar cantidad" data-tooltip="Aumentar cantidad"
                  className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-[#e8f5e9] transition-colors active:scale-90 text-[#1b5e20] font-bold text-lg">+</button>
              </div>
              <button
                onClick={handleAdd}
                data-tooltip={agotado ? 'Hacer pedido programado' : parcial ? 'Agregar al carrito (stock parcial)' : 'Agregar al carrito'}
                className={`flex-1 py-4 font-black rounded-2xl active:scale-95 transition-all shadow-lg flex items-center justify-center gap-2 ${
                  agotado
                    ? 'bg-amber-500 hover:bg-amber-600 text-white'
                    : 'bg-[#1b5e20] hover:bg-[#0d3300] text-white'
                }`}
              >
                <ShoppingCart className="w-4 h-4" />
                {agotado ? 'Pedir programado' : parcial ? 'Pedir (stock parcial)' : 'Agregar al carrito'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   CONFIRM STOCK MODAL
═══════════════════════════════════════════ */
function ConfirmStockModal({ product, qty, onConfirm, onCancel }) {
  const disponible = product.stock ?? 0;
  const programado = qty - disponible;
  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onCancel}>
      <div className="bg-white rounded-[28px] p-8 max-w-sm w-full shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="w-14 h-14 bg-amber-100 rounded-2xl flex items-center justify-center mx-auto mb-5 text-2xl">⚠️</div>
        <h3 className="text-xl font-black text-center text-[#1b5e20] mb-3">Stock insuficiente</h3>
        <p className="text-[#555] text-sm text-center leading-relaxed mb-2">
          Pediste <strong className="text-[#1b5e20]">{qty} unidades</strong> de <strong>{product.nombre}</strong>, pero solo hay{' '}
          <strong className="text-[#1b5e20]">{disponible}</strong> disponibles para entrega inmediata.
        </p>
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 mb-6 text-xs text-amber-700 leading-relaxed">
          Las <strong>{programado} unidades restantes</strong> se procesarán como <strong>pedido programado</strong> y se entregarán cuando haya producción disponible. Te avisaremos cuando estén listas.
        </div>
        <div className="flex gap-3">
          <button onClick={onCancel} data-tooltip="Cancelar y volver" className="flex-1 py-3 border-2 border-gray-200 rounded-2xl font-black text-gray-500 hover:bg-gray-50 transition-colors text-sm">
            Cancelar
          </button>
          <button onClick={onConfirm} data-tooltip="Confirmar pedido con stock parcial" className="flex-1 py-3 bg-[#1b5e20] text-white rounded-2xl font-black hover:bg-[#0d3300] transition-colors text-sm">
            Confirmar pedido
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   LANDING PAGE
═══════════════════════════════════════════ */
const PRODUCTS_PER_PAGE = 6;

const LandingPage = ({ hideNavbar = false }) => {
  const navigate = useNavigate();
  const { agregarNotificacion } = useNotificaciones();
  const [content, setContent] = useState({ ...LANDING_DEFAULTS });
  const [activeTab, setActiveTab] = useState('Todos');
  const [productsPage, setProductsPage] = useState(1);
  const productsSectionRef = useRef(null);
  const [user, setUser] = useState(null);
  const [productos, setProductos] = useState([]);
  const [categoriasMap, setCategoriasMap] = useState({});
  const [searchTerm, setSearchTerm] = useState('');

  const [cartCount, setCartCount] = useState(0);
  const [cartOpen, setCartOpen] = useState(false);
  const [quantities, setQuantities] = useState({});
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [orderDetails, setOrderDetails] = useState(null);

  const [errorToast,  setErrorToast]  = useState('');
  const [confirmPending, setConfirmPending] = useState(null);
  const [stockLimitMsg,  setStockLimitMsg]  = useState('');

  // Sincronizar contador del carrito
  const syncCartInfo = useCallback(() => {
    setCartCount(getCartCount());
  }, []);

  useEffect(() => {
    setUser(getUser());
    syncCartInfo();
    window.addEventListener('cart-updated', syncCartInfo);
    return () => window.removeEventListener('cart-updated', syncCartInfo);
  }, [syncCartInfo]);

  // Carga la configuración de la landing desde el backend
  useEffect(() => {
    getLandingConfig().then(setContent);
  }, []);

  const cargarProductos = useCallback(async () => {
    try {
      const res  = await fetch(`${API_URL}/productos/?pagina=1&por_pagina=100`);
      const data = await res.json();
      const lista = data?.productos || [];

      // Construir mapa de categorías desde los datos de productos (ya incluyen nombre e icono)
      const map = {};
      lista.forEach(p => {
        if (p.ID_Categoria && p.nombre_categoria) {
          map[p.ID_Categoria] = {
            nombre: p.nombre_categoria,
            icon:   p.icono_categoria || "📦",
          };
        }
      });
      setCategoriasMap(map);

      const vendibles = lista
        .filter(p => p.Estado !== 0 && p.Publicado !== 0 && !p.lote_vencido && !p.Lote_Vencido)
        .map(p => ({
          id:                 p.ID_Producto,
          nombre:             p.nombre,
          precio:             p.Precio_venta,
          stock:              p.Stock ?? 0,
          idCategoria:        p.ID_Categoria,
          imagen:             p.imagenes?.[0]?.url || null,
          imagenes:           p.imagenes?.map(i => i.url) || [],
          descripcion_corta:  p.Descripcion_Corta ?? "",
          descripcion_larga:  p.Descripcion_Larga ?? "",
          // La lista pública devuelve este campo en snake_case; aceptar ambas
          // formas evita que el checkout pierda la regla de anticipo.
          requiereProduccion: !!(p.Requiere_Produccion ?? p.requiere_produccion),
        }));
      setProductos(vendibles);
      // Sincronizar campos del carrito con datos frescos de la API.
      // Si un producto cambió Requiere_Produccion o Stock desde que se agregó,
      // el item del carrito queda desactualizado y el checkout calcula mal el anticipo.
      const cartActual = getCart();
      const cartSync = cartActual.map(item => {
        const fresco = vendibles.find(p => p.id === item.id);
        if (!fresco) return item;
        return { ...item, requiereProduccion: fresco.requiereProduccion, stock: fresco.stock };
      });
      if (cartSync.some((it, i) =>
        it.requiereProduccion !== cartActual[i]?.requiereProduccion ||
        it.stock !== cartActual[i]?.stock
      )) {
        saveCart(cartSync);
        window.dispatchEvent(new Event('cart-updated'));
      }
      // Lo que dejó de estar publicado sale del carrito de quien ya lo tenía:
      // acá el catálogo se recarga al volver a la pestaña, así que el carrito
      // se pone al día solo.
      sanitizeCart(vendibles.map(p => p.id));
    } catch {
      // silent — show empty grid
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(cargarProductos, 0);
    return () => clearTimeout(id);
  }, [cargarProductos]);

  // Re-fetch al volver a la pestaña (productos pueden haber cambiado)
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') cargarProductos(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [cargarProductos]);

  /* ── Auto-scroll si hay hash en la URL ── */
  useEffect(() => {
    const hash = window.location.hash;
    if (hash) {
      const id = hash.replace('#', '');
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }, 600);
    }
  }, []);

  const getQty = (id) => quantities[id] || 1;
  const setQty = (id, v) => setQuantities(prev => ({ ...prev, [id]: Math.min(MAX_QTY, Math.max(1, v)) }));

  const mostrarLimiteStock = (nombre, stock, enCarrito = 0) => {
    const unidades = (n) => `${n} unidad${n !== 1 ? 'es' : ''}`;
    setStockLimitMsg(
      stock === 0
        ? `No queda nada de "${nombre}" en este momento. Inténtalo más tarde o contáctanos.`
        : enCarrito >= stock
          ? `Ya tienes las ${unidades(stock)} que hay de "${nombre}" en tu carrito.`
          : `En este momento no puedes pedir más de ${unidades(stock)} de "${nombre}". Inténtalo más tarde o contáctanos.`
    );
    setTimeout(() => setStockLimitMsg(''), 12000);
  };

  /// Agrega y avisa si el stock no dio para todo.
  ///
  /// El aviso sale de lo que el carrito hizo de verdad, no de una comprobación
  /// previa: la de antes miraba la cantidad del selector y no lo que ya había
  /// adentro, así que con el carrito lleno el botón seguía sumando.
  const realizarAdd = (product, qty, pedidoProgramado = false) => {
    const r = addToCartWithQty(product, qty, pedidoProgramado);
    setQuantities(prev => ({ ...prev, [product.id]: 1 }));
    syncCartInfo();
    if (r.rechazado > 0) mostrarLimiteStock(product.nombre, r.tope ?? 0, r.total);
    return r;
  };

  const handleAddToCart = (product) => {
    const qty = getQty(product.id);
    const stock = product.stock ?? 0;
    // Lo que la panadería hornea no tiene tope: el faltante se fabrica.
    const programado = product.requiereProduccion && (stock === 0 || qty > stock);
    const r = realizarAdd(product, qty, programado);
    if (r.agregado > 0) setCartOpen(true);
  };

  const handleAddFromModal = (product, qty) => {
    const stock = product.stock ?? 0;
    const programado = product.requiereProduccion && (stock === 0 || qty > stock);
    const r = realizarAdd(product, qty, programado);
    if (r.agregado > 0) { setSelectedProduct(null); setCartOpen(true); }
  };

  const handleConfirmStock = () => {
    if (!confirmPending) return;
    const { product, qty } = confirmPending;
    realizarAdd(product, qty, true);
    setConfirmPending(null);
    setSelectedProduct(null);
    setCartOpen(true);
  };

  /* 🔑 Manejo de Checkout */
  const handleStartCheckout = (details) => {
    const currentUser = getUser();
    setOrderDetails({
      ...details,
      clientName: currentUser?.nombre || '',
      items: getCart(),
      total: getCart().reduce((a, i) => a + i.precio * i.cantidad, 0),
    });
    setCartOpen(false);
    setCheckoutOpen(true);
  };

  // Mismo envío que usa "Hacer pedidos": con un solo camino, una mejora acá
  // vale para las dos pantallas.
  const handleConfirmOrder = async (paymentMethod, saldoAFavor, deliveryInfo) => {
    let res;
    try {
      res = await crearPedidoCliente({
        paymentMethod, saldoAFavor,
        deliveryInfo, orderDetails,
      });
    } catch (err) {
      setErrorToast(err.message || "Error al registrar el pedido");
      setTimeout(() => setErrorToast(''), 4000);
      return;
    }

    clearCart();
    setCheckoutOpen(false);
    cargarProductos(); // actualizar stock tras confirmar pedido

    agregarNotificacion({
      tipo: TIPOS.PEDIDO_NUEVO,
      titulo: "¡Pedido registrado!",
      mensaje: `Hemos recibido tu orden ${res?.Numero_Pedido || res?.numero_pedido || res?.ID_Venta || ""} correctamente.`,
    });

    navigate('/cliente/pedidos');
  };

  const getCat = (id) => categoriasMap[id] || { nombre: 'Sin categoría', descripcion: '', icon: '🍌' };
  const categories = ['Todos', ...Object.values(categoriasMap).map(c => c.nombre)];
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const filteredProducts = productos.filter((p) => {
    const matchesTab = activeTab === 'Todos' || getCat(p.idCategoria).nombre === activeTab;
    const matchesSearch = !normalizedSearch || p.nombre.toLowerCase().includes(normalizedSearch);
    return matchesTab && matchesSearch;
  });

  const totalProductPages  = Math.max(1, Math.ceil(filteredProducts.length / PRODUCTS_PER_PAGE));
  const safeProductsPage   = Math.min(productsPage, totalProductPages);
  const paginatedProducts  = filteredProducts.slice(
    (safeProductsPage - 1) * PRODUCTS_PER_PAGE,
    safeProductsPage * PRODUCTS_PER_PAGE
  );

  const handleProductsPage = (n) => setProductsPage(n);

  // El scroll a la grilla se hace DESPUÉS de renderizar la página nueva: hacerlo
  // en el mismo click medía la posición con el layout viejo (más alto) y el
  // salto caía en la sección de abajo.
  const primerRenderPagina = useRef(true);
  useEffect(() => {
    if (primerRenderPagina.current) { primerRenderPagina.current = false; return; }
    productsSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [productsPage, activeTab]);

  const scrollToSection = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });

  return (
    <div className="min-h-screen bg-[#f7faf8] text-[#1b5e20] font-sans overflow-x-hidden">
      {!hideNavbar && <Navbar isLanding={true} />}

      {/* ── CSS animations ── */}
      <style>{`
        @keyframes slide-down-toast {
          from { transform: translateX(-50%) translateY(-20px); opacity: 0; }
          to { transform: translateX(-50%) translateY(0); opacity: 1; }
        }
        .animate-slide-down-toast { animation: slide-down-toast 0.4s ease both; }
        @keyframes pdm-in {
          from { opacity: 0; transform: translateY(40px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        .pdm-animate { animation: pdm-in 0.35s cubic-bezier(0.16,1,0.3,1) both; }
      `}</style>

      {/* ── Toast de error ── */}
      {errorToast && (
        <div className="fixed top-6 left-1/2 z-[10000] flex items-center gap-3 px-6 py-4 bg-[#b71c1c] text-white rounded-2xl shadow-2xl animate-slide-down-toast">
          <X className="w-5 h-5 text-[#ef9a9a]" />
          <span className="font-black">{errorToast}</span>
        </div>
      )}

      {/* ── Aviso de límite de stock ── */}
      {stockLimitMsg && (
        <div className="fixed top-6 left-1/2 -translate-x-1/2 z-[10000] flex items-center gap-3 px-6 py-4 bg-amber-50 border border-amber-300 text-amber-900 rounded-2xl shadow-2xl max-w-sm text-sm font-semibold">
          <span>⚠️</span>
          <span>{stockLimitMsg}</span>
        </div>
      )}

      {/* ── Checkout Modal Premium ── */}
      <CheckoutModal
        isOpen={checkoutOpen}
        onClose={() => setCheckoutOpen(false)}
        orderDetails={orderDetails}
        onConfirm={handleConfirmOrder}
      />

      {/* ── Confirm Stock Modal ── */}
      {confirmPending && (
        <ConfirmStockModal
          product={confirmPending.product}
          qty={confirmPending.qty}
          onConfirm={handleConfirmStock}
          onCancel={() => setConfirmPending(null)}
        />
      )}

      {/* ── Product Detail Modal ── */}
      {selectedProduct && (
        <ProductDetailModal
          product={selectedProduct}
          cat={getCat(selectedProduct.idCategoria)}
          onClose={() => setSelectedProduct(null)}
          onAddToCart={(p, qty) => handleAddFromModal(p, qty)}
        />
      )}

      {/* ── Cart Drawer Premium ── */}
      <CartAside
        isOpen={cartOpen}
        onClose={() => setCartOpen(false)}
        onCheckout={handleStartCheckout}
        onLoginRequired={() => navigate('/login')}
      />

      {/* ── Floating Cart Button ── */}
      {cartCount > 0 && !cartOpen && (
        <button
          onClick={() => setCartOpen(true)}
          data-tooltip="Abrir carrito de compras"
          className="fixed bottom-8 right-8 z-40 flex items-center gap-3 px-6 py-4 bg-[#1b5e20] text-white font-black rounded-2xl shadow-[0_10px_40px_rgba(27,94,32,0.4)] hover:bg-[#0d3300] transition-all hover:-translate-y-1 active:scale-95 group"
        >
          <div className="relative">
            <ShoppingCart className="w-5 h-5 group-hover:rotate-12 transition-transform" />
            <span className="absolute -top-2 -right-2 bg-amber-500 text-white text-[10px] font-black w-4 h-4 rounded-full flex items-center justify-center border border-[#1b5e20]">
              {cartCount}
            </span>
          </div>
          <span>Ver Carrito</span>
          <span className="bg-white/20 backdrop-blur-md text-white px-3 py-1 rounded-xl text-sm font-black border border-white/20">
            {formatCOP(getCart().reduce((s, i) => s + i.precio * i.cantidad, 0))}
          </span>
        </button>
      )}

      {/* ─── HERO ─── */}
      <section id="inicio" className={`relative ${hideNavbar ? 'pt-10' : 'pt-32'} pb-20 lg:pt-48 lg:pb-32 overflow-hidden`}>
        <div className="absolute top-0 right-0 -z-10 w-1/2 h-full bg-gradient-to-l from-[#4caf50]/10 to-transparent rounded-l-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-24 -left-24 -z-10 w-96 h-96 bg-[#81c784]/10 rounded-full blur-3xl" />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col lg:flex-row items-center gap-16">
            <div className="flex-1 text-center lg:text-left space-y-8 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-[#e8f5e9] text-[#1b5e20] rounded-full text-xs font-black tracking-widest shadow-sm border border-[#c8e6c9]">
                <Sparkles className="w-4 h-4 text-[#4caf50]" />
                {content.heroBadge}
              </div>
              <h1 className="text-6xl lg:text-8xl font-black text-[#1b5e20] leading-tight tracking-tighter">
                {content.heroTitle}
              </h1>
              <p className="text-xl text-[#388e3c] leading-relaxed max-w-xl mx-auto lg:mx-0 font-medium">
                {content.heroDescription}
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-5">
                <button onClick={() => scrollToSection('productos')} data-tooltip="Ver nuestros productos" className="group relative flex items-center gap-3 px-10 py-5 bg-[#1b5e20] text-white font-black rounded-2xl hover:bg-[#0d3300] shadow-[0_10px_30px_rgba(27,94,32,0.3)] transition-all hover:-translate-y-1 active:scale-95 w-full sm:w-auto justify-center overflow-hidden">
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                  Explorar menú
                  <ShoppingBag className="w-5 h-5 group-hover:rotate-12 transition-transform" />
                </button>
              </div>
            </div>
            <div className="flex-1 relative">
              <div className="relative z-10 w-full aspect-square max-w-[550px] mx-auto">
                <div className="absolute -top-10 -right-10 w-32 h-32 bg-[#a5d6a7] rounded-3xl rotate-12 -z-10 opacity-40" />
                <div className="w-full h-full bg-gradient-to-br from-[#1b5e20] to-[#4caf50] rounded-[60px] p-1 shadow-[0_30px_60px_rgba(27,94,32,0.2)] rotate-2 hover:rotate-0 transition-transform duration-700 overflow-hidden group">
                  <div className="w-full h-full bg-white rounded-[58px] overflow-hidden relative">
                    <img
                      src="/torta-platano.jpg"
                      alt="Producto Tostón App"
                      fetchpriority="high"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CATEGORÍAS ─── */}
      {/* ─── PRODUCTOS ─── */}
      <section id="productos" ref={productsSectionRef} className="py-20 bg-white relative">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center space-y-4 mb-10">
            <h2 className="text-[#4caf50] font-black tracking-[0.3em] uppercase text-sm">Nuestro Menú</h2>
            <h3 className="text-5xl lg:text-6xl font-black text-[#1b5e20]">Nuestros Productos</h3>
            <div className="w-24 h-2 bg-[#1b5e20] mx-auto rounded-full" />
          </div>
          <p className="text-center text-xs font-black uppercase tracking-[0.25em] text-[#4caf50] mb-4">Categorías</p>
          <div className="flex flex-wrap justify-center gap-3 mb-8">
            {categories.map(cat => (
              <button key={cat} onClick={() => { setActiveTab(cat); setProductsPage(1); }}
                data-tooltip={cat === 'Todos' ? 'Ver todos los productos' : `Filtrar por ${cat}`}
                className={`px-8 py-3 rounded-2xl font-bold transition-all ${activeTab === cat ? 'bg-[#1b5e20] text-white shadow-lg scale-105' : 'bg-[#f1f8f1] text-[#1b5e20] hover:bg-[#e8f5e9]'}`}>
                {cat}
              </button>
            ))}
          </div>

          <div className="mb-16 max-w-xl mx-auto">
            <label className="block text-left text-xs font-black uppercase tracking-[0.25em] text-[#4caf50] mb-3">
              Buscar producto
            </label>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setProductsPage(1); }}
              placeholder="Escribe el nombre del producto..."
              className="w-full rounded-2xl border border-[#c8e6c9] bg-[#f7faf8] px-4 py-3 text-sm text-[#1b5e20] placeholder:text-[#9e9e9e] focus:outline-none focus:border-[#4caf50] focus:ring-2 focus:ring-[#4caf50]/20"
            />
          </div>

          {filteredProducts.length === 0 ? (
            <div className="rounded-[28px] border border-dashed border-[#c8e6c9] bg-[#f7faf8] p-12 text-center">
              <p className="text-lg font-black text-[#1b5e20] mb-2">No encontramos productos que coincidan con tu búsqueda.</p>
              <p className="text-sm text-[#6b7d6a]">Prueba con otro nombre o limpia el filtro para volver a ver todos los productos.</p>
              <button
                onClick={() => { setSearchTerm(''); setActiveTab('Todos'); setProductsPage(1); }}
                className="mt-5 px-5 py-3 rounded-2xl bg-[#1b5e20] text-white font-black hover:bg-[#0d3300] transition-colors"
              >
                Limpiar búsqueda
              </button>
            </div>
          ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-10">
            {paginatedProducts.map((p) => {
              const cat = getCat(p.idCategoria);
              const qty = getQty(p.id);
              const inCartItem = getCart().find(i => i.id === p.id);
              const agotado = p.stock === 0;
              const sinStockProducible   = agotado && !!p.requiereProduccion;
              const sinStockNoProducible = agotado && !p.requiereProduccion;
              return (
                <div
                  key={p.id}
                  className={`group bg-white rounded-[40px] overflow-hidden border transition-all duration-500 flex flex-col ${
                    sinStockNoProducible
                      ? 'border-gray-200 opacity-75'
                      : sinStockProducible
                        ? 'border-amber-200 hover:shadow-[0_30px_60px_rgba(27,94,32,0.1)]'
                        : 'border-[#f1f8f1] hover:border-[#c8e6c9] hover:shadow-[0_30px_60px_rgba(27,94,32,0.1)]'
                  }`}
                  style={sinStockNoProducible ? { filter: 'grayscale(0.65)' } : undefined}
                >
                  <div className="relative h-72 overflow-hidden cursor-pointer" data-tooltip="Ver detalles del producto" onClick={() => setSelectedProduct(p)}>
                    {p.imagenPreview || p.imagen
                      ? <img
                          src={urlProductImg(p.imagenPreview || p.imagen, 800)}
                          srcSet={urlProductImgSrcset(p.imagenPreview || p.imagen)}
                          sizes="(max-width:640px) 95vw, (max-width:1024px) 45vw, 32vw"
                          alt={p.nombre}
                          loading="lazy"
                          decoding="async"
                          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                        />
                      : <div className="w-full h-full bg-[#f7faf8] flex items-center justify-center"><span className="text-7xl group-hover:scale-125 transition-transform duration-500">{cat.icon || '🍌'}</span></div>
                    }
                    {/* Overlay Ver detalles */}
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-all duration-300 flex items-center justify-center">
                      <div className="flex items-center gap-2 bg-white/90 backdrop-blur-sm text-[#1b5e20] font-black text-sm px-5 py-2.5 rounded-2xl shadow-xl opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300">
                        <Eye className="w-4 h-4" /> Ver detalles
                      </div>
                    </div>
                    <div className="absolute top-6 right-6 bg-white/95 backdrop-blur-sm px-5 py-2.5 rounded-2xl font-black text-[#1b5e20] shadow-lg">
                      {formatCOP(p.precio)}
                    </div>
                    {sinStockNoProducible && (
                      <div className="absolute top-6 left-6 bg-gray-600 text-white px-3 py-1.5 rounded-xl text-xs font-black shadow-lg">
                        ⏳ Sin stock
                      </div>
                    )}
                    {!sinStockNoProducible && inCartItem && (
                      <div className="absolute top-6 left-6 bg-[#1b5e20] text-white px-3 py-1.5 rounded-xl text-xs font-black flex items-center gap-1.5 shadow-lg border border-white/20">
                        <ShoppingCart className="w-3 h-3" />
                        {inCartItem.cantidad} en carrito
                      </div>
                    )}
                  </div>
                  <div className="p-8 flex flex-col flex-1">
                    <div className="flex justify-between items-start mb-4">
                      <h4 className="text-2xl font-black text-[#1b5e20] group-hover:text-[#388e3c] transition-colors">{p.nombre}</h4>
                      <span className="px-3 py-1 bg-[#e8f5e9] text-[#1b5e20] rounded-lg text-[10px] font-black uppercase tracking-widest">{cat.nombre}</span>
                    </div>
                    {sinStockNoProducible && (
                      <p className="text-amber-600 text-xs font-bold mb-3 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
                        No disponible para entrega inmediata — puedes hacer un pedido programado.
                      </p>
                    )}
                    {sinStockProducible && (
                      <p className="text-amber-700 text-xs font-bold mb-3 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2">
                        🧡 Se prepara especialmente para ti — pídelo y te avisamos cuando esté listo.
                      </p>
                    )}
                    <p className="text-[#555] font-medium text-sm mb-4 flex-1 leading-relaxed">{cat.descripcion || 'Sabor auténtico y natural en cada bocado.'}</p>
                    <div className="mb-4">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-black px-3 py-1.5 rounded-xl border ${
                        p.requiereProduccion
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : p.stock <= 5
                            ? 'bg-red-50 text-red-600 border-red-100'
                            : p.stock <= 15
                              ? 'bg-amber-50 text-amber-700 border-amber-100'
                              : 'bg-green-50 text-[#1b5e20] border-green-100'
                      }`}>
                        {p.requiereProduccion ? '🛠️ Requiere producción' : `📦 ${p.stock} disponible${p.stock !== 1 ? 's' : ''} en stock`}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1 bg-[#f7faf8] rounded-2xl border border-[#e8f5e9] p-1.5">
                        <button onClick={() => setQty(p.id, qty - 1)} aria-label="Disminuir cantidad" data-tooltip="Disminuir cantidad" className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-[#e8f5e9] transition-colors active:scale-90">
                          <Minus className="w-3.5 h-3.5 text-[#1b5e20]" />
                        </button>
                        <QtyInput
                          value={qty}
                          onChange={(n) => setQty(p.id, n)}
                          className="w-8 text-center font-black text-[#1b5e20] text-sm bg-transparent border-none outline-none"
                        />
                        <button onClick={() => setQty(p.id, qty + 1)} aria-label="Aumentar cantidad" data-tooltip="Aumentar cantidad" className="w-8 h-8 flex items-center justify-center rounded-xl hover:bg-[#e8f5e9] transition-colors active:scale-90">
                          <Plus className="w-3.5 h-3.5 text-[#1b5e20]" />
                        </button>
                      </div>
                      <button
                        onClick={() => handleAddToCart(p)}
                        data-tooltip={agotado ? 'Hacer pedido programado' : 'Agregar al carrito'}
                        className={`flex-1 flex items-center justify-center gap-2 py-4 font-black rounded-2xl transition-all shadow-sm active:scale-95 ${
                          agotado
                            ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                            : 'bg-[#f1f8f1] text-[#1b5e20] group-hover:bg-[#1b5e20] group-hover:text-white'
                        }`}
                      >
                        <ShoppingCart className="w-4 h-4" />
                        {agotado ? 'Pedir programado' : 'Agregar'}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          )}

          {/* ── Paginación ── */}
          {totalProductPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-14 flex-wrap">
              {/* Anterior */}
              <button
                onClick={() => handleProductsPage(safeProductsPage - 1)}
                disabled={safeProductsPage === 1}
                data-tooltip="Página anterior"
                className="flex items-center gap-2 px-5 py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-[#f1f8f1] text-[#1b5e20] hover:bg-[#e8f5e9] active:scale-95"
              >
                <ChevronLeft className="w-4 h-4" /> Anterior
              </button>

              {/* Páginas */}
              {(() => {
                const pages = [];
                const show = (n) => pages.push(
                  <button
                    key={n}
                    onClick={() => handleProductsPage(n)}
                    data-tooltip={`Ir a página ${n}`}
                    className={`w-10 h-10 rounded-xl font-black text-sm transition-all active:scale-95 ${
                      n === safeProductsPage
                        ? 'bg-[#1b5e20] text-white shadow-lg scale-110'
                        : 'bg-[#f1f8f1] text-[#1b5e20] hover:bg-[#e8f5e9]'
                    }`}
                  >{n}</button>
                );
                const dots = (key) => pages.push(
                  <span key={key} className="w-10 text-center text-[#9e9e9e] font-bold">…</span>
                );
                if (totalProductPages <= 7) {
                  for (let i = 1; i <= totalProductPages; i++) show(i);
                } else {
                  show(1);
                  if (safeProductsPage > 3) dots('l');
                  const start = Math.max(2, safeProductsPage - 1);
                  const end   = Math.min(totalProductPages - 1, safeProductsPage + 1);
                  for (let i = start; i <= end; i++) show(i);
                  if (safeProductsPage < totalProductPages - 2) dots('r');
                  show(totalProductPages);
                }
                return pages;
              })()}

              {/* Siguiente */}
              <button
                onClick={() => handleProductsPage(safeProductsPage + 1)}
                disabled={safeProductsPage === totalProductPages}
                data-tooltip="Página siguiente"
                className="flex items-center gap-2 px-5 py-3 rounded-2xl font-bold text-sm transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-[#f1f8f1] text-[#1b5e20] hover:bg-[#e8f5e9] active:scale-95"
              >
                Siguiente <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Contador de resultados */}
          {filteredProducts.length > 0 && (
            <p className="text-center text-xs text-[#9e9e9e] font-medium mt-4">
              Mostrando {(safeProductsPage - 1) * PRODUCTS_PER_PAGE + 1}–{Math.min(safeProductsPage * PRODUCTS_PER_PAGE, filteredProducts.length)} de {filteredProducts.length} producto{filteredProducts.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      </section>

      {/* ─── NOSOTROS / NUESTRA HISTORIA ─── */}
      <section id="nosotros" className="py-32 bg-[#1b5e20] text-white relative overflow-hidden">
        <div className="absolute -top-24 -right-24 w-96 h-96 bg-[#4caf50]/10 rounded-full blur-3xl" />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 text-center">
          <div className="flex items-center justify-center gap-3 mb-6">
            <Leaf className="w-8 h-8 text-[#81c784]" />
            <h2 className="text-[#81c784] font-black tracking-[0.4em] uppercase text-sm">El origen</h2>
          </div>
          <h3 className="text-5xl lg:text-7xl font-black leading-tight tracking-tighter mb-8">
            {content.historyTitle}
          </h3>
          <p className="text-xl lg:text-2xl text-[#c8e6c9] leading-relaxed font-medium max-w-3xl mx-auto">
            {content.historyDescription}
          </p>
          <div className="w-24 h-2 bg-[#81c784] mx-auto rounded-full mt-12" />
        </div>
      </section>

      {/* ─── ÚNETE (CTA de registro, solo invitados) ─── */}
      {!user && (
        <section id="unete" className="py-24 bg-[#0d3300] text-white relative overflow-hidden">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <h4 className="text-3xl lg:text-4xl font-black mb-4">{content.ctaTitle}</h4>
            <p className="text-[#c8e6c9] mb-10 text-lg">{content.ctaDescription}</p>
            <button onClick={() => navigate('/register')} data-tooltip="Crear una cuenta para hacer pedidos" className="px-12 py-5 bg-white text-[#1b5e20] font-black rounded-3xl hover:bg-[#e8f5e9] transition-all shadow-xl">
              Crear mi cuenta gratis
            </button>
          </div>
        </section>
      )}

      <Footer onExplorar={() => scrollToSection('productos')} />
    </div>
  );
};

export default LandingPage;