import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { X, MapPin, Trash2, Plus, Minus, ShoppingBag, LogIn, Sparkles, ChevronRight, ShoppingCart, FileText, Truck, Clock, AlertTriangle, Package } from 'lucide-react';
import { CartItem, removeFromCart, updateQuantity, clearCart, getCart, MAX_QTY } from '../services/cartService';
import { isAuthenticated } from '../../../../services/authService';
import { apiFetch } from '../../../../utils/api';
import { getLandingConfig, LANDING_DEFAULTS } from '../../../../services/landingConfigService';
import { estaAbierto, mensajeFueraHorario, rangoHorario } from '../../../../utils/horario';
import { formatCOP } from '../../../../utils/formato';

interface CartAsideProps {
  isOpen: boolean;
  onClose: () => void;
  onCheckout: (details: { address: string; date: string; departamento: string; municipio: string; observaciones: string; tieneDomicilio: boolean }) => void;
  onLoginRequired: () => void;
  cartUpdateToggle?: boolean;
}

const COP = formatCOP;

const CartAside: React.FC<CartAsideProps> = ({ isOpen, onClose, onCheckout, onLoginRequired }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [cart, setCart]               = useState<CartItem[]>(() => getCart());
  const [qtyDrafts, setQtyDrafts]     = useState<{[id: number]: string}>({});
  const [tieneDomicilio,    setTieneDomicilio]    = useState(false);
  const [observaciones,     setObservaciones]     = useState('');
  const [checkoutError,     setCheckoutError]     = useState('');
  const [confirmVaciar,     setConfirmVaciar]     = useState(false);
  const [stockLimitMsg,  setStockLimitMsg]  = useState('');
  /// Dirección exacta de entrega (texto). El barrio y el precio del domicilio se
  /// eligen y confirman en el siguiente paso (CheckoutModal), contra el módulo
  /// Ubicaciones. Acá solo se pregunta si es domicilio o recogida.
  /// La dirección del perfil, solo para pasarla al checkout como punto de
  /// partida. Acá no se edita.
  const [direccionExacta, setDireccionExacta] = useState('');
  const [total, setTotal]             = useState(() =>
    getCart().reduce((acc, i) => acc + i.precio * i.cantidad, 0)
  );
  const [cfgHorario, setCfgHorario]   = useState<any>({ ...LANDING_DEFAULTS });
  const abierto = estaAbierto(cfgHorario);

  useEffect(() => { getLandingConfig().then(setCfgHorario); }, []);

  const syncCart = useCallback(() => {
    const c = getCart();
    setCart(c);
    setTotal(c.reduce((acc, i) => acc + i.precio * i.cantidad, 0));
    setQtyDrafts({});
  }, []);

  useEffect(() => { syncCart(); }, [isOpen, syncCart]);
  useEffect(() => {
    window.addEventListener('cart-updated', syncCart);
    return () => window.removeEventListener('cart-updated', syncCart);
  }, [syncCart]);

  const mostrarLimiteStock = (nombre: string, stock: number) => {
    setStockLimitMsg(`En este momento no puedes pedir más de ${stock} unidad${stock !== 1 ? 'es' : ''} de "${nombre}". Inténtalo más tarde o contáctanos.`);
    setTimeout(() => setStockLimitMsg(''), 12000);
  };

  const handleQty = (id: number, delta: number) => {
    const item = cart.find(i => i.id === id);
    if (!item) return;
    const newQty = Math.min(MAX_QTY, item.cantidad + delta);
    if (newQty <= 0) { removeFromCart(id); return; }
    if (item.stock && !((item as any).pedidoProgramado) && !((item as any).requiereProduccion) && newQty > item.stock) {
      mostrarLimiteStock(item.nombre, item.stock);
      return;
    }
    updateQuantity(id, newQty);
  };

  const handleQtyDirect = (id: number, value: string) => {
    const num = Math.min(MAX_QTY, parseInt(value, 10));
    if (isNaN(num) || num < 1) { removeFromCart(id); return; }
    const item = cart.find(i => i.id === id);
    if (item?.stock && !((item as any).pedidoProgramado) && !((item as any).requiereProduccion) && num > item.stock) {
      mostrarLimiteStock(item.nombre, item.stock);
      updateQuantity(id, item.stock);
      return;
    }
    updateQuantity(id, num);
  };

  // La dirección exacta guardada se trae al abrir el carrito como punto de
  // partida. El barrio y el precio se confirman en el siguiente paso.
  useEffect(() => {
    if (!isOpen || !isAuthenticated()) return;
    let vigente = true;
    apiFetch('/auth/perfil')
      .then((perfil: any) => {
        if (!vigente) return;
        if (perfil?.Direccion) setDireccionExacta(perfil.Direccion);
      })
      .catch(() => {});
    return () => { vigente = false; };
  }, [isOpen]);

  const address = direccionExacta.trim();

  // El precio del domicilio depende del barrio y se calcula en el checkout.
  const costoTotal = total;

  /// Cierra el carrito y lleva al catálogo.
  ///
  /// Antes solo cerraba: desde la landing eso alcanzaba —el catálogo está
  /// debajo— pero desde los pedidos o el perfil no pasaba nada y el botón
  /// parecía roto.
  ///
  /// El catálogo es la sección "productos" del inicio. No es una pantalla
  /// aparte: /cliente/hacer-pedidos existe en las rutas pero es una copia
  /// vieja que no enlaza nadie más y que lee campos que la API ya no manda,
  /// así que le faltan las imágenes y el precio sale mal.
  ///
  /// Estando ya en el inicio no se navega —el componente no se vuelve a montar
  /// y no pasaría nada—: se baja a la sección a mano.
  const verProductos = () => {
    onClose();
    const enElInicio = ['/', '/cliente', '/cliente/inicio']
      .includes(location.pathname);

    if (enElInicio) {
      // Después de que el panel termine de cerrarse, o el salto se ve raro.
      setTimeout(() => {
        document.getElementById('productos')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 320);
      return;
    }
    navigate(isAuthenticated() ? '/cliente/inicio#productos' : '/#productos');
  };

  const handleCheckout = () => {
    if (cart.length === 0) return;
    setCheckoutError('');
    if (!isAuthenticated()) { onClose(); onLoginRequired(); return; }
    const minimo = Number((cfgHorario as any).pedidoMinimo) || 0;
    if (tieneDomicilio && minimo > 0 && total < minimo) {
      setCheckoutError(`El mínimo para domicilio es $${minimo.toLocaleString('es-CO')} COP. Agrega más productos o elige recogida en tienda.`);
      return;
    }
    onCheckout({ address, departamento: '', municipio: '', date: '', observaciones, tieneDomicilio });
  };

  if (!isOpen) return null;
  const loggedIn = isAuthenticated();

  return (
    <div className="fixed inset-0 z-[9000] overflow-hidden">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] transition-all duration-500 animate-in fade-in" onClick={onClose} />

      <div className="absolute right-0 top-0 bottom-0 w-full max-w-lg bg-white shadow-2xl flex flex-col animate-in slide-in-from-right duration-500 ease-out border-l border-emerald-100">

        {/* Header */}
        <div className="text-white px-5 py-4 relative overflow-hidden shrink-0" style={{ background: 'linear-gradient(135deg, var(--green-900) 0%, var(--green-800) 50%, var(--green-700) 100%)' }}>
          <div className="absolute top-[-20px] right-[-20px] w-48 h-48 bg-white/5 rounded-full blur-3xl animate-pulse" />
          <div className="flex items-center justify-between relative z-10">
            <div className="flex items-center gap-3">
              <div className="bg-white/10 backdrop-blur-xl p-2.5 rounded-xl border border-white/20 shadow-inner">
                <ShoppingBag size={20} className="text-white" />
              </div>
              <div>
                <h2 className="text-xl font-black tracking-tight leading-none mb-1">Tu Carrito</h2>
                <p className="text-[10px] text-emerald-200 font-bold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                  {cart.length} {cart.length === 1 ? 'producto' : 'productos'}
                </p>
              </div>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-white/20 rounded-full transition-all text-white/80 hover:text-white border border-white/10">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Aviso horario */}
        {!abierto && (
          <div className="px-4 py-3 bg-amber-50 border-b border-amber-100 shrink-0 flex items-start gap-2.5">
            <Clock size={18} className="shrink-0 mt-0.5 text-amber-600" />
            <div>
              <p className="text-xs font-black text-amber-700">Fuera del horario de atención</p>
              <p className="text-[11px] font-medium text-amber-600 mt-0.5 leading-snug">{mensajeFueraHorario(cfgHorario)}</p>
              <p className="text-[10px] text-amber-500 mt-1">Horario de atención: {rangoHorario(cfgHorario)}</p>
            </div>
          </div>
        )}

        {/* Toggle Recogida / Domicilio */}
        <div className="px-5 py-4 bg-white border-b border-gray-100 shrink-0">
          <div className="grid grid-cols-2 bg-gray-100 rounded-2xl p-1.5 gap-1.5">
            <button
              onClick={() => { setTieneDomicilio(false); setCheckoutError(''); }}
              className={`flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-black uppercase tracking-wider transition-all duration-200 ${!tieneDomicilio ? 'bg-white text-green-800 shadow-md' : 'text-gray-400 hover:text-gray-600'}`}
            >
              <ShoppingBag size={16} />
              Recogida
            </button>
            <button
              onClick={() => { setTieneDomicilio(true); setCheckoutError(''); }}
              className={`flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-black uppercase tracking-wider transition-all duration-200 ${tieneDomicilio ? 'bg-white text-green-800 shadow-md' : 'text-gray-400 hover:text-gray-600'}`}
            >
              <Truck size={16} />
              Domicilio
            </button>
          </div>

          {/* Entrega (solo si domicilio). El barrio y el costo del domicilio se
              eligen en el siguiente paso. */}
          {tieneDomicilio && (
            <div className="mt-3 space-y-2">
              {loggedIn ? (
                /* La dirección se elige en el checkout, un paso después: ahí
                   se puede usar la de siempre o poner otra. Preguntarla acá
                   era preguntar dos veces y lo de acá no se usaba. */
                <p className="text-[11px] font-medium text-gray-400 flex items-start gap-1.5">
                  <MapPin size={11} className="shrink-0 mt-0.5" />
                  En el siguiente paso eliges la dirección y el barrio, y te
                  decimos el costo del domicilio.
                </p>
              ) : null}
              {(() => {
                const minimo = Number((cfgHorario as any).pedidoMinimo) || 0;
                if (minimo > 0 && total < minimo) {
                  return (
                    <p className="text-[11px] font-bold text-amber-700 flex items-start gap-1.5 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
                      <AlertTriangle size={11} className="shrink-0 mt-0.5" />
                      Mínimo para domicilio: ${minimo.toLocaleString('es-CO')} COP. Te faltan ${(minimo - total).toLocaleString('es-CO')} COP.
                    </p>
                  );
                }
                return null;
              })()}

              {!loggedIn && (
                <div className="flex items-center gap-2 py-2 px-3 bg-amber-50 border border-amber-200 rounded-xl">
                  <LogIn size={13} className="text-amber-500 shrink-0" />
                  <p className="text-xs font-bold text-amber-700">Inicia sesión para continuar con el pedido</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Cuerpo */}
        <div className="flex-1 overflow-y-auto p-4 bg-gray-50/20 custom-scrollbar relative">
          {cart.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-4">
              <div className="w-16 h-16 bg-white rounded-2xl shadow-xl flex items-center justify-center border border-emerald-50">
                <ShoppingCart size={24} className="text-emerald-200" />
              </div>
              <div>
                <h3 className="text-base font-black text-gray-800 mb-1">Carrito vacío</h3>
                <p className="text-gray-400 text-[13px] max-w-[220px] leading-relaxed font-medium">Explora nuestro menú y elige algo delicioso.</p>
              </div>
              <button onClick={verProductos} className="btn-primary" style={{ padding: '10px 24px', fontSize: '13px' }}>Ver productos</button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <span className="text-[11px] font-black text-gray-400 uppercase tracking-widest">Resumen del pedido</span>
                {confirmVaciar ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[11px] font-bold text-gray-500">¿Vaciar todo?</span>
                    <button
                      onClick={() => { clearCart(); setConfirmVaciar(false); }}
                      className="text-[11px] font-black text-white bg-red-500 hover:bg-red-600 px-2.5 py-1 rounded-lg transition-colors"
                    >Sí</button>
                    <button
                      onClick={() => setConfirmVaciar(false)}
                      className="text-[11px] font-black text-gray-500 hover:text-gray-700 px-2.5 py-1 rounded-lg border border-gray-200 transition-colors"
                    >No</button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmVaciar(true)}
                    className="flex items-center gap-1.5 text-[11px] font-black text-red-400 hover:text-red-600 transition-colors uppercase tracking-widest"
                  >
                    <Trash2 size={13} /> Vaciar
                  </button>
                )}
              </div>

              {stockLimitMsg && (
                <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-2xl p-3 text-[11px] font-semibold text-amber-800">
                  <AlertTriangle size={14} className="flex-shrink-0 mt-0.5 text-amber-500" />
                  <span>{stockLimitMsg}</span>
                </div>
              )}

              <div className="grid gap-2.5">
                {cart.map((item) => (
                  <div key={item.id} className="group bg-white rounded-2xl p-3.5 border border-gray-100 shadow-sm hover:shadow-md hover:border-emerald-100 transition-all duration-300 relative overflow-hidden">
                    <div className="flex gap-3.5 relative z-10">
                      <div className="w-[72px] h-[72px] bg-gray-50 rounded-xl overflow-hidden flex-shrink-0 border border-gray-100">
                        {(item as any).imagenPreview || (item as any).imagen ? (
                          <img src={(item as any).imagenPreview || (item as any).imagen} alt={item.nombre} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-gray-50"><Package size={24} className="text-gray-300" /></div>
                        )}
                      </div>
                      <div className="flex-1 flex flex-col justify-between py-0.5 min-w-0">
                        <div className="pr-7">
                          <h4 className="font-black text-gray-800 text-[15px] leading-tight mb-1 truncate">{item.nombre}</h4>
                          <p className="font-black text-[13px]" style={{ color: 'var(--green-700)' }}>{COP(item.precio)} c/u</p>
                          {(item as any).pedidoProgramado && (
                            <span className="mt-1 text-[11px] font-black text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md inline-flex items-center gap-1"><Clock size={12} /> Pedido programado</span>
                          )}
                        </div>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center bg-gray-50 rounded-xl p-1 border border-gray-100">
                            <button onClick={() => handleQty(item.id, -1)} aria-label="Quitar uno" className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white hover:text-red-500 transition-all text-gray-500">
                              <Minus size={14} strokeWidth={3} />
                            </button>
                            <input
                              type="number"
                              min="1"
                              maxLength={4}
                              value={qtyDrafts[item.id] ?? String(item.cantidad)}
                              onChange={e => setQtyDrafts(prev => ({ ...prev, [item.id]: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                              onBlur={e => {
                                const val = e.target.value;
                                setQtyDrafts(prev => { const n = { ...prev }; delete n[item.id]; return n; });
                                handleQtyDirect(item.id, val);
                              }}
                              className="w-10 text-center text-[15px] font-black text-gray-800 bg-transparent border-none outline-none"
                              style={{ appearance: 'textfield', MozAppearance: 'textfield', WebkitAppearance: 'none' } as React.CSSProperties}
                            />
                            <button onClick={() => handleQty(item.id, 1)} aria-label="Agregar uno" className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white hover:text-emerald-600 transition-all text-gray-500">
                              <Plus size={14} strokeWidth={3} />
                            </button>
                          </div>
                          <p className="text-[16px] font-black text-gray-900">{COP(item.precio * item.cantidad)}</p>
                        </div>
                      </div>
                    </div>
                    <button onClick={() => removeFromCart(item.id)} aria-label={`Quitar ${item.nombre}`} className="absolute top-2 right-2 z-20 w-9 h-9 flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-all">
                      <X size={18} strokeWidth={2.5} />
                    </button>
                  </div>
                ))}
              </div>

              {/* Observaciones */}
              <div className="bg-white rounded-2xl p-3 border border-gray-100 shadow-sm">
                <div className="flex items-center gap-1.5 mb-2">
                  <FileText size={14} className="text-gray-400" />
                  <span className="text-[11px] font-black text-gray-400 uppercase tracking-widest">Observaciones del pedido</span>
                </div>
                <textarea
                  rows={2}
                  placeholder="Sin picante, tocar el timbre, dejar en portería…"
                  className="w-full text-sm font-medium text-gray-700 placeholder:text-gray-300 resize-none outline-none bg-transparent border-none p-0"
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={`bg-white border-t border-gray-100 shadow-[0_-10px_40px_rgba(0,0,0,0.04)] relative z-20 ${tieneDomicilio ? 'px-4 py-3' : 'p-4'}`}>

          {tieneDomicilio ? (
            <div className="flex items-center justify-between mb-3">
              <div className="space-y-0.5">
                <div className="flex items-center gap-3 text-[13px] text-gray-400 font-medium">
                  <span>Productos <span className="font-black text-gray-700">{COP(total)}</span></span>
                  <span>+</span>
                  <span>Domicilio <span className="font-bold" style={{ color: '#7b1fa2' }}>según barrio</span></span>
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-[11px] font-black text-gray-400 uppercase tracking-widest">Subtotal</span>
                  <span className="text-2xl font-black text-gray-900 tracking-tighter leading-none">{COP(costoTotal)}</span>
                </div>
              </div>
              <div className="text-amber-400"><Sparkles size={16} /></div>
            </div>
          ) : (
            <div className="space-y-1.5 mb-4">
              <div className="flex justify-between items-center text-[13px]">
                <span className="text-gray-500 font-bold">Subtotal productos</span>
                <span className="text-gray-800 font-black">{COP(total)}</span>
              </div>
              <div className="relative py-0.5">
                <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-dashed border-gray-100" /></div>
              </div>
              <div className="flex justify-between items-end">
                <div>
                  <span className="block text-[11px] font-black text-gray-400 uppercase tracking-widest mb-1">Total del pedido</span>
                  <span className="text-3xl font-black text-gray-900 tracking-tighter leading-none">{COP(costoTotal)}</span>
                </div>
                <div className="text-amber-500 pb-1"><Sparkles size={18} /></div>
              </div>
            </div>
          )}

          {checkoutError && (
            <p className="text-xs font-bold text-red-600 mb-2 text-center">{checkoutError}</p>
          )}
          <button
            onClick={handleCheckout}
            disabled={cart.length === 0}
            className={`w-full group relative overflow-hidden flex items-center justify-center gap-3 rounded-xl font-black text-base transition-all duration-300 shadow-lg active:scale-[0.98] ${tieneDomicilio ? 'py-2.5' : 'py-3.5'} ${
              cart.length === 0 ? 'bg-gray-100 text-gray-300 cursor-not-allowed border border-gray-200 shadow-none' : 'btn-primary shadow-emerald-200/50 hover:shadow-xl hover:-translate-y-0.5'
            }`}
            style={cart.length > 0 ? { background: 'linear-gradient(135deg, var(--green-700) 0%, var(--green-600) 100%)' } : {}}
          >
            {loggedIn ? (
              <>Finalizar Pedido <ChevronRight size={17} strokeWidth={3} /></>
            ) : (
              <><LogIn size={17} /> Identificarse</>
            )}
          </button>
        </div>
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 10px; }
        input[type=number]::-webkit-inner-spin-button,
        input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
      `}</style>
    </div>
  );
};

export default CartAside;
