import React, { useState, useEffect } from 'react';
import { X, CreditCard, Banknote, Scale, User, MapPin, ShoppingBag, CheckCircle2, Sparkles, ShieldCheck, ChevronRight, Gift, Truck, Phone, Save, Package, AlertTriangle, Home, MapPinned } from 'lucide-react';
import { CartItem } from '../services/cartService';
import { getUser } from '../../../../services/authService';
import { getMiCredito } from '../../../../services/pedidosService';
import { apiFetch } from '../../../../utils/api';
import { getCobertura } from '../../../../services/ubicacionesService';
import SelectorBarrioEntrega from '../../../../shared/components/SelectorBarrioEntrega';
import FormularioDireccion from '../../../../shared/components/FormularioDireccion';
import { desdeTexto, lineaVia } from '../../../../utils/direccionEntrega';
// La regla del anticipo vive en un solo lugar, espejo del servidor.
import { pideAnticipo } from '../../../../utils/anticipo';
import SaldoMonto from '../../../../shared/components/SaldoMonto';
import SplitPagoMonto from '../../../../shared/components/SplitPagoMonto';
import TerminosCondicionesModal from '../../../../shared/components/TerminosCondicionesModal';
import { getLandingConfig, LANDING_DEFAULTS } from '../../../../services/landingConfigService';
import { estaAbierto, mensajeFueraHorario, rangoHorario, primeraFechaValida, fechaMinimaPedido, fechaMaximaPedido } from '../../../../utils/horario';
import { formatCOP } from '../../../../utils/formato';
import './CheckoutModal.css';

// Datos de la cuenta bancaria — actualiza en GestionPedidos.jsx también
const CUENTA = {
  banco:   'Bancolombia',
  numero:  '54213570938',
  tipo:    'Cuenta de ahorros',
  titular: 'TostonApp S.A.S',
};


const COP = formatCOP;

interface CheckoutModalProps {
  isOpen: boolean;
  onClose: () => void;
  orderDetails: {
    address: string;
    municipio?: string;
    departamento?: string;
    date?: string;
    clientName: string;
    items: CartItem[];
    total: number;
    observaciones?: string;
    tieneDomicilio?: boolean;
  } | null;
  // El comprobante ya no se sube en el checkout: se adjunta después, desde
  // "Mis pedidos" (pagarPedido) — por eso ya no viaja por acá.
  onConfirm: (paymentMethod: string, saldoAFavor?: { usar: boolean; monto: number; efectivoMonto?: number }, deliveryInfo?: { tieneDomicilio: boolean; address: string; idBarrio: number | null; municipio: string; departamento: string; date: string; time: string; observaciones: string }) => Promise<void> | void;
}

/** Saldo a favor: lo que el cliente tiene abonado de devoluciones anteriores.
 *  No es todo o nada — con la barra decide que parte gasta en este pedido y
 *  cuanta se guarda para el siguiente. El porcentaje va sobre lo maximo que se
 *  puede aplicar (su saldo o el total del pedido, lo que sea menor), asi que
 *  el 100% siempre cae justo y nunca sobra plata aplicada. */
const SaldoAFavorPicker: React.FC<{
  saldo: number;
  maximo: number;
  activo: boolean;
  monto: number | '';
  onToggle: () => void;
  onMonto: (m: number | '') => void;
}> = ({ saldo, maximo, activo, monto, onToggle, onMonto }) => {
  return (
    <div className={`rounded-2xl border-2 transition-all ${activo ? 'border-green-500 bg-green-50' : 'border-gray-100 bg-white hover:border-green-200'}`}>
      <div onClick={onToggle} className="flex items-center gap-3 p-3 cursor-pointer">
        <div className={`p-2 rounded-xl shrink-0 ${activo ? 'bg-green-600 text-white' : 'bg-green-50 text-green-700'}`}>
          <Gift size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-black text-gray-700">Usar saldo a favor</p>
          <p className="text-[10px] font-bold text-green-700">{COP(saldo)} disponibles</p>
        </div>
        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${activo ? 'bg-green-600 border-green-600' : 'border-gray-300'}`}>
          {activo && <CheckCircle2 size={10} className="text-white" />}
        </div>
      </div>

      {activo && (
        <div className="px-3 pb-3 pt-2.5 border-t border-green-200">
          <SaldoMonto
            saldo={saldo}
            maximo={maximo}
            monto={monto}
            onMonto={onMonto}
          />
        </div>
      )}
    </div>
  );
};

const CheckoutModal: React.FC<CheckoutModalProps> = ({ isOpen, onClose, orderDetails, onConfirm }) => {
  const [paymentMethod,      setPaymentMethod]      = useState('digital');
  // Pago mixto: cuánta plata va en efectivo, en pesos. El comprobante de la
  // parte transferida se adjunta después (Mis pedidos); el efectivo se
  // entrega al recibir el pedido.
  const [efectivoMonto,      setEfectivoMonto]      = useState<number | ''>('');
  const [mixtoError,         setMixtoError]         = useState('');
  const [isConfirming,       setIsConfirming]       = useState(false);
  const [credito,            setCredito]            = useState(0);
  const [usarCredito,        setUsarCredito]        = useState(false);
  // Cuanto saldo a favor se aplica, EN PESOS. Arranca vacio y el tope lo
  // pone creditoMaximo; el atajo "Todo" cubre el caso mas comun.
  const [creditoMonto,       setCreditoMonto]       = useState<number | ''>('');
  const [tieneDomicilio,     setTieneDomicilio]     = useState(false);
  /// Si el pedido va a la dirección de siempre o a otra.
  ///
  /// La guardada se muestra y no se toca: para cambiarla está "Mis datos".
  /// Antes venía precargada en un campo editable y corregirla ahí terminaba
  /// pisando la del perfil sin que nadie lo pidiera.
  const [usarRegistrada,     setUsarRegistrada]     = useState(true);
  /// La otra dirección, en campos separados. Vale solo para este pedido.
  const [otraVia,            setOtraVia]            = useState(() => desdeTexto(''));
  /// Barrio de entrega elegido + su cobertura ({ disponible, base, final, ... }).
  const [idBarrio,           setIdBarrio]           = useState<number | null>(null);
  const [coberturaBarrio,    setCoberturaBarrio]    = useState<any>(null);
  /// Mientras se pregunta la cobertura del barrio guardado.
  const [cargandoBarrio,     setCargandoBarrio]     = useState(false);
  const [date,               setDate]               = useState('');
  const [fechaTocada,        setFechaTocada]        = useState(false);
  const [time,               setTime]               = useState('');
  const [observaciones,      setObservaciones]      = useState('');
  // Teléfono
  const [telefono,           setTelefono]           = useState('');
  const [telefonoTocado,     setTelefonoTocado]     = useState(false);
  const [telefonoRegistrado, setTelefonoRegistrado] = useState(false);
  const [guardarTelefono,    setGuardarTelefono]    = useState(true);
  // Dirección guardada
  /// Lo que el cliente tiene guardado en su perfil. No se toca desde acá.
  const [registrada,     setRegistrada]     = useState<any>(null);
  /// Si ya se intentó confirmar: hasta entonces no se marca nada en rojo.
  const [direccionTocada,     setDireccionTocada]     = useState(false);
  const [terminosAceptados,  setTerminosAceptados]   = useState(false);
  const [verTerminos,        setVerTerminos]         = useState(false);
  const [cfgHorario,         setCfgHorario]          = useState<any>({ ...LANDING_DEFAULTS });
  // Banners deslizantes: se pueden descartar; vuelven a salir al reabrir.
  const [bannerHorario,      setBannerHorario]       = useState(true);
  const [bannerProduccion,   setBannerProduccion]    = useState(true);

  useEffect(() => { getLandingConfig().then(setCfgHorario); }, []);

  useEffect(() => {
    if (!isOpen || !orderDetails) return;
    setTieneDomicilio(orderDetails.tieneDomicilio ?? false);
    setIdBarrio(null);
    setCoberturaBarrio(null);
    setDate(orderDetails.date || '');
    setFechaTocada(false);
    setTime('');
    setObservaciones(orderDetails.observaciones || '');
    setTelefonoTocado(false);
    setDireccionTocada(false);

    // Cargar perfil para verificar teléfono y prefill de dirección / barrio.
    apiFetch('/auth/perfil')
      .then((perfil: any) => {
        const tel = perfil?.Telefono || '';
        setTelefono(tel);
        setTelefonoRegistrado(!!tel);
        setRegistrada({
          direccion:    perfil?.Direccion || '',
          ID_Barrio:    perfil?.ID_Barrio || null,
          barrio:       perfil?.Barrio || null,
          // Para no preguntar el departamento al elegir otra dirección.
          departamento: perfil?.Departamento || '',
        });
        // Con dirección guardada se arranca en ella; sin ella, no hay nada
        // que elegir y se pide directamente.
        setUsarRegistrada(!!perfil?.Direccion);
        // El barrio ya no se pregunta: es el de sus datos, y de ahí sale la
        // tarifa. Preguntarlo en cada pedido era pedir dos veces lo mismo.
        if (perfil?.ID_Barrio) {
          setCargandoBarrio(true);
          getCobertura(perfil.ID_Barrio)
            .then((cob: any) => { setIdBarrio(perfil.ID_Barrio); setCoberturaBarrio(cob); })
            .catch(() => { setIdBarrio(null); setCoberturaBarrio(null); })
            .finally(() => setCargandoBarrio(false));
        } else {
          setIdBarrio(null);
          setCoberturaBarrio(null);
        }
      })
      .catch(() => {
        setTelefonoRegistrado(false);
        setRegistrada(null);
      });

    getMiCredito()
      .then((data: any) => setCredito(data?.saldo || 0))
      .catch(() => setCredito(0));
    setUsarCredito(false);
    setCreditoMonto('');
    setEfectivoMonto('');
    setMixtoError('');
    setTerminosAceptados(false);
    setVerTerminos(false);
    setBannerHorario(true);
    setBannerProduccion(true);
  }, [isOpen]);

  // El anticipo ya no se cobra en el checkout: se pide después, cuando el
  // admin apruebe la fecha de entrega (pantalla "Esperando pago" en Mis
  // pedidos). Esto solo previene el método mixto y avisa de antemano —el
  // servidor decide lo mismo con la misma regla al aprobar la fecha.
  //
  // Se calcula acá arriba, antes del early return, porque el efecto de abajo
  // lo necesita y los hooks no pueden quedar detrás de un return; de ahí el
  // encadenado opcional sobre orderDetails.
  const requiereAnticipo = pideAnticipo(
    (orderDetails?.items || []).map((it: CartItem) => ({
      cantidad:           it.cantidad,
      stock:              it.stock,
      requiereProduccion: it.requiereProduccion,
    })),
    (orderDetails?.total || 0) + (tieneDomicilio && coberturaBarrio?.disponible ? (coberturaBarrio.final ?? 0) : 0),
  );

  // Un pedido con anticipo no admite mixto: la parte en efectivo del mixto se
  // paga AL RECIBIR y el anticipo tiene que estar cubierto ANTES de producir,
  // así que no respalda nada. El backend lo rechaza; acá se resuelve al leer y
  // no tocando el estado, para que el cliente que baje la cantidad recupere el
  // método que había elegido.
  const permiteMixto = !requiereAnticipo;
  const esMixto      = permiteMixto && paymentMethod === 'mixto';

  if (!isOpen || !orderDetails) return null;

  const itemsConDeficit = (orderDetails.items || []).filter(
    (it: CartItem) => it.requiereProduccion && it.cantidad > (it.stock ?? 0)
  );

  const soloDigitos = (tel: string) => tel.replace(/\D/g, '');
  const telefonoValido = soloDigitos(telefono).length === 10;
  const telefonoError = telefonoTocado && !telefonoValido
    ? soloDigitos(telefono).length === 0 ? 'El teléfono es obligatorio' : 'Debe tener exactamente 10 dígitos'
    : null;

  // La entrega necesita: una dirección exacta (texto) y un barrio con cobertura.
  // El barrio determina el precio del domicilio (SelectorBarrioEntrega ya
  // consultó la cobertura contra el backend).
  /// Deja puesto el barrio del perfil, con su tarifa.
  const aplicarBarrioDelPerfil = (id: number | null) => {
    if (!id) { setIdBarrio(null); setCoberturaBarrio(null); setCargandoBarrio(false); return; }
    setCargandoBarrio(true);
    getCobertura(id)
      .then((cob: any) => { setIdBarrio(id); setCoberturaBarrio(cob); })
      .catch(() => { setIdBarrio(null); setCoberturaBarrio(null); })
      .finally(() => setCargandoBarrio(false));
  };

  const barrioDisponible = !!coberturaBarrio?.disponible;
  /// Solo se puede usar la guardada si hay una.
  const conRegistrada = usarRegistrada && !!registrada?.direccion;
  /// A dónde va el pedido: la de siempre, o la que se escribió para hoy.
  const address = conRegistrada
    ? String(registrada.direccion).trim()
    : lineaVia(otraVia);
  const faltaDireccion =
    !address ? 'Escribe la dirección exacta (calle, número, complemento)'
    : !idBarrio             ? (conRegistrada
        ? 'Tu barrio no está en tus datos. Agrégalo en "Mis datos" para pedir a domicilio.'
        : 'Elige el barrio de esta entrega')
    : !barrioDisponible     ? 'Ese barrio no tiene cobertura de domicilio: elige otro o recoge en tienda'
    : null;
  const direccionValida = faltaDireccion === null;
  const direccionError  = direccionTocada ? faltaDireccion : null;

  const user = getUser();
  const costoDomicilio   = (tieneDomicilio && barrioDisponible) ? (coberturaBarrio.final ?? 0) : 0;
  const costoDomicilioBase = (tieneDomicilio && barrioDisponible) ? (coberturaBarrio.base ?? 0) : 0;
  // Tope real: no se puede aplicar mas saldo del que hay ni mas de lo que
  // cuesta el pedido. Sobre ese tope corre la barra.
  const creditoMaximo    = Math.min(credito, orderDetails.total + costoDomicilio);
  const creditoAplicar   = usarCredito
    ? Math.min(Math.max(Number(creditoMonto) || 0, 0), creditoMaximo)
    : 0;
  const totalFinal       = Math.max(0, orderDetails.total + costoDomicilio - creditoAplicar);

  // Fecha límite obligatoria: solo para lo que hay que fabricar.
  // Mín: primer día hábil o hoy + DIAS_MIN_PRODUCCION (lo que sea más tarde).
  // Máx: hoy + MESES_MAX_PEDIDO meses.
  // La misma regla la valida el servidor al crear el pedido.
  const fechaMinima = fechaMinimaPedido(cfgHorario);
  const fechaMaxima = fechaMaximaPedido();
  const faltaFecha  = itemsConDeficit.length > 0 && !date
    ? 'Elige para cuándo necesitas tu pedido'
    : itemsConDeficit.length > 0 && date < fechaMinima
    ? `La fecha más próxima disponible es ${fechaMinima}`
    : itemsConDeficit.length > 0 && date > fechaMaxima
    ? `La fecha no puede ser después del ${fechaMaxima}`
    : null;
  const fechaError = fechaTocada ? faltaFecha : null;

  const handleFinalConfirm = async () => {
    setTelefonoTocado(true);
    setFechaTocada(true);
    if (tieneDomicilio) setDireccionTocada(true);
    if (!telefonoValido) return;
    if (tieneDomicilio && !direccionValida) return;
    if (faltaFecha) return;

    // Un mixto tiene que tener las dos partes: si una queda en cero, lo que
    // el cliente quiere es el otro método a secas.
    if (esMixto) {
      const enEfectivo = Number(efectivoMonto) || 0;
      if (enEfectivo <= 0) {
        setMixtoError('Escribe cuánto vas a pagar en efectivo.');
        return;
      }
      if (enEfectivo >= totalFinal) {
        setMixtoError(`El efectivo debe ser menor que ${COP(totalFinal)}. Si vas a pagar todo en efectivo, elige ese método.`);
        return;
      }
      setMixtoError('');
    }

    setIsConfirming(true);

    // Guardar teléfono si el usuario lo pidió y no estaba registrado (o cambió)
    if (guardarTelefono && (!telefonoRegistrado || telefono !== (user as any)?.telefono)) {
      await apiFetch('/auth/perfil', {
        method: 'PUT',
        body: JSON.stringify({ Telefono: telefono }),
      }).catch(() => {});
    }

    // La dirección del perfil solo se escribe cuando NO había ninguna: una
    // dirección puntual —"hoy déjalo donde mi mamá"— no puede pisar la de
    // siempre. Para cambiarla está "Mis datos". El barrio del perfil (dato guía)
    // se guarda igual: no condiciona nada.
    if (tieneDomicilio && !registrada?.direccion && address) {
      await apiFetch('/auth/perfil', {
        method: 'PUT',
        body: JSON.stringify({
          Direccion: address,
          ID_Barrio: idBarrio || undefined,
          Municipio: coberturaBarrio?.ciudad || undefined,
          Departamento: coberturaBarrio?.departamento || undefined,
        }),
      }).catch(() => {});
    }

    try {
      // El comprobante ya no se sube acá: se adjunta después, cuando el
      // pedido llegue a "Esperando pago" (sin producción) o al aprobarse la
      // fecha (con producción y anticipo).
      await onConfirm(paymentMethod, { usar: usarCredito, monto: creditoAplicar, efectivoMonto: Number(efectivoMonto) || 0 }, {
        tieneDomicilio,
        address,
        idBarrio,
        municipio: coberturaBarrio?.ciudad || '',
        departamento: coberturaBarrio?.departamento || '',
        date,
        time,
        observaciones,
      });
    } catch {
      // el padre ya muestra el error al usuario
    } finally {
      setIsConfirming(false);
    }
  };

  const inputCls = "w-full bg-gray-50 border border-gray-200 rounded-xl py-2.5 px-3 text-sm text-gray-700 font-medium placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-green-400 transition-all";

  return (
    <div className="modal-overlay">
      {verTerminos && <TerminosCondicionesModal onClose={() => setVerTerminos(false)} />}
      <div className="modal-box co-card relative shadow-2xl overflow-hidden flex flex-col max-h-[95vh] border-none">

        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-5 py-4" style={{ background: 'linear-gradient(135deg, var(--green-800) 0%, var(--green-700) 100%)' }}>
          <div className="flex items-center gap-3">
            <div className="bg-white/10 p-2 rounded-xl border border-white/20">
              <ShoppingBag size={18} className="text-white" />
            </div>
            <div>
              <h2 className="text-base font-black text-white leading-none mb-0.5">Confirmar Pedido</h2>
              <p className="text-white/60 text-[10px] font-bold flex items-center gap-1">
                <ShieldCheck size={9} /> Pago 100% Seguro
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-white/20 rounded-full transition-all text-white/70 hover:text-white">
            <X size={16} />
          </button>
        </div>

        {/* Banners deslizantes: quedan fijos arriba hasta cerrar el modal */}
        <div className="co-banners">
          {!estaAbierto(cfgHorario) && bannerHorario && (
            <div className="co-banner co-banner--warn">
              <AlertTriangle size={15} className="shrink-0 mt-0.5" />
              <div>
                <strong>Fuera del horario de atención.</strong>{' '}
                {mensajeFueraHorario(cfgHorario)}{' '}
                <span style={{ opacity: 0.8 }}>Horario: {rangoHorario(cfgHorario)}.</span>
              </div>
              <button className="co-banner__x" onClick={() => setBannerHorario(false)} aria-label="Descartar">
                <X size={13} />
              </button>
            </div>
          )}
          {itemsConDeficit.length > 0 && bannerProduccion && (
            <div className="co-banner co-banner--info">
              <Package size={15} className="shrink-0 mt-0.5" />
              <div>
                <strong>Pedido programado.</strong> Algunos productos no tienen stock inmediato
                ({itemsConDeficit.map((it: CartItem) => it.nombre).join(', ')}). Elige para cuándo
                lo necesitas: el administrador revisa la fecha y la aprueba o te propone otra.
              </div>
              <button className="co-banner__x" onClick={() => setBannerProduccion(false)} aria-label="Descartar">
                <X size={13} />
              </button>
            </div>
          )}
        </div>

        <div className="co-split">

        {/* Body */}
        <div className="co-main flex-1 overflow-y-auto custom-scrollbar bg-gray-50 px-4 py-3 space-y-3">

          {/* Quién recibe. Al lado había un "A nombre de" que se guardaba
              en una columna que nadie lee: no sale en el detalle, ni en el
              panel, ni en el domicilio. */}
          <div className="bg-white rounded-2xl border border-gray-100 px-3 py-2.5">
            <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-1">Quién recibe</p>
            <div className="flex items-center gap-1.5">
              <User size={12} className="text-green-700 shrink-0" />
              <p className="text-xs font-black text-gray-800 truncate">{user?.nombre} {user?.apellidos}</p>
            </div>
          </div>

          {/* Fecha límite: obligatoria solo para lo que hay que fabricar. */}
          {itemsConDeficit.length > 0 && (
            <div className={`bg-white rounded-2xl border px-3 py-3 space-y-2 ${fechaError ? 'border-red-200' : date ? 'border-green-200' : 'border-gray-100'}`}>
              <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <Package size={10} /> ¿Para cuándo necesitas tu pedido?
                <span className="text-red-400">*</span>
              </p>
              <input
                type="date"
                value={date}
                min={fechaMinima}
                max={fechaMaxima}
                onChange={e => setDate(e.target.value)}
                onBlur={() => setFechaTocada(true)}
                className={inputCls}
              />
              {fechaError && (
                <p className="text-[11px] font-bold text-red-600">{fechaError}</p>
              )}
            </div>
          )}

          {/* Teléfono de contacto */}
          <div className={`bg-white rounded-2xl border px-3 py-3 space-y-2 ${telefonoError ? 'border-red-200' : telefonoValido ? 'border-green-200' : 'border-gray-100'}`}>
            <div className="flex items-center justify-between">
              <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                <Phone size={10} /> Teléfono de contacto
                <span className="text-red-400">*</span>
              </p>
              {telefonoRegistrado && telefonoValido && (
                <span className="text-[9px] font-bold text-green-600 flex items-center gap-1">
                  <CheckCircle2 size={10} /> Registrado
                </span>
              )}
            </div>
            <div className="relative">
              <Phone size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="tel"
                placeholder="Ej: 300 123 4567"
                value={telefono}
                onChange={e => {
                  setTelefono(e.target.value);
                  setTelefonoTocado(true);
                }}
                onBlur={() => setTelefonoTocado(true)}
                className={inputCls + " pl-8"}
              />
            </div>
            {telefonoError && (
              <p className="text-[10px] font-bold text-red-500">{telefonoError}</p>
            )}
            {!telefonoError && telefonoValido && !telefonoRegistrado && telefono.trim() && (
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={guardarTelefono}
                  onChange={e => setGuardarTelefono(e.target.checked)}
                  className="w-3.5 h-3.5 rounded accent-green-600"
                />
                <span className="text-xs font-bold text-gray-500 flex items-center gap-1">
                  <Save size={11} className="text-green-600" /> Guardar como teléfono principal
                </span>
              </label>
            )}
          </div>

          {/* Tipo de entrega */}
          <div className="bg-white rounded-2xl border border-gray-100 px-3 py-3 space-y-2.5">
            <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Tipo de entrega</p>
            <div className="grid grid-cols-2 bg-gray-100 rounded-xl p-1 gap-1">
              <button
                onClick={() => { setTieneDomicilio(false); setDireccionTocada(false); }}
                className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-black transition-all duration-200 ${!tieneDomicilio ? 'bg-white text-green-800 shadow' : 'text-gray-400 hover:text-gray-600'}`}
              >
                <ShoppingBag size={13} /> Recogida
              </button>
              <button
                onClick={() => { setTieneDomicilio(true); setDireccionTocada(false); }}
                className={`flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-black transition-all duration-200 ${tieneDomicilio ? 'bg-white text-green-800 shadow' : 'text-gray-400 hover:text-gray-600'}`}
              >
                <Truck size={13} /> Domicilio
              </button>
            </div>

            {!tieneDomicilio && (
              <div className="flex items-start gap-2 bg-green-50 border border-green-100 rounded-xl px-3 py-2.5">
                <MapPin size={14} className="text-green-700 mt-0.5 shrink-0" />
                <div>
                  <p className="text-[10px] font-black text-green-700 uppercase tracking-widest mb-0.5">Dirección de recogida</p>
                  <p className="text-xs font-bold text-gray-700">CARRERA 38 A NO. 80 12</p>
                </div>
              </div>
            )}


            {tieneDomicilio && (
              <div className="space-y-2">
                {/* Una sola tarjeta: arriba de dónde sale la dirección,
                    adentro lo que corresponda. Dos botones sueltos con un
                    formulario debajo se leían como cosas sin relación. */}
                <div className="rounded-2xl border border-gray-200 overflow-hidden bg-white">
                  {!!registrada?.direccion && (
                    <div className="flex p-1 gap-1 bg-gray-50 border-b border-gray-100">
                      {[
                        { id: true,  icono: <Home size={13} />,      titulo: 'La de siempre' },
                        { id: false, icono: <MapPinned size={13} />, titulo: 'Otra dirección' },
                      ].map(op => {
                        const activa = usarRegistrada === op.id;
                        return (
                          <button
                            key={String(op.id)}
                            type="button"
                            onClick={() => {
                              setUsarRegistrada(op.id);
                              setDireccionTocada(true);
                              // Cada dirección tiene su barrio: el de siempre
                              // vuelve solo, y para otra se elige abajo.
                              if (op.id) {
                                aplicarBarrioDelPerfil(registrada?.ID_Barrio || null);
                              } else {
                                setIdBarrio(null);
                                setCoberturaBarrio(null);
                              }
                            }}
                            className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2 text-[11px] font-black transition ${
                              activa
                                ? 'bg-white text-green-700 shadow-sm ring-1 ring-green-200'
                                : 'text-gray-400 hover:text-gray-600'
                            }`}
                          >
                            {op.icono}
                            {op.titulo}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  <div className="p-3">
                    {conRegistrada ? (
                      /* Se muestra como es y no se edita: para cambiarla está
                         "Mis datos", que es donde se cambia de verdad. */
                      <>
                        <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-1">
                          Se entrega en
                        </p>
                        <p className="text-sm font-black text-gray-800 leading-snug">
                          {registrada.direccion}
                        </p>
                        {coberturaBarrio && (
                          <div className="flex items-center gap-1.5 mt-1.5 text-[11px] font-bold text-gray-500">
                            <MapPin size={11} className="text-green-600 shrink-0" />
                            <span>
                              {coberturaBarrio.barrio}
                              {coberturaBarrio.ciudad ? ` · ${coberturaBarrio.ciudad}` : ''}
                            </span>
                            {barrioDisponible && (
                              <span className="ml-auto text-green-700 bg-green-50 rounded-full px-2 py-0.5">
                                {COP(coberturaBarrio.final ?? 0)}
                              </span>
                            )}
                          </div>
                        )}
                        <p className="text-[10px] font-semibold text-gray-300 mt-2">
                          Para cambiarla, entra a «Mis datos».
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-2">
                          Solo para este pedido
                        </p>
                        <FormularioDireccion
                          valor={otraVia}
                          onCambio={(d: any) => { setOtraVia(d); setDireccionTocada(true); }}
                          tema="checkout"
                          soloVia
                        />
                      </>
                    )}
                  </div>
                </div>

                {/* Con la dirección de siempre no hay nada que elegir: su
                    barrio ya está en sus datos y el costo sale en el total.
                    Con otra dirección sí, y vale solo para este pedido. */}
                {!conRegistrada && (
                  <SelectorBarrioEntrega
                    compacto
                    // El departamento no se pregunta: no se manda un domicilio
                    // a otro departamento. Se toma el suyo, no el primero de
                    // la lista, que alfabéticamente es Amazonas.
                    sinDepartamento
                    nombreDepartamentoPreferido={registrada?.departamento || null}
                    onChange={(id: number | null, cob: any) => {
                      setIdBarrio(id);
                      setCoberturaBarrio(cob);
                      setDireccionTocada(true);
                    }}
                  />
                )}
                {/* Tres cosas distintas: que no tenga barrio, que se esté
                    consultando, y que la consulta haya fallado. Decir siempre
                    "no tienes barrio" mandaba a arreglar lo que no estaba mal. */}
                {conRegistrada && !coberturaBarrio && (
                  <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-2xl px-3 py-2.5">
                    <AlertTriangle size={14} className="text-amber-600 mt-0.5 shrink-0" />
                    <p className="text-[11px] font-bold text-amber-700 leading-relaxed">
                      {!registrada?.ID_Barrio
                        ? 'Todavía no tienes barrio en tus datos. Agrégalo en «Mis datos» o elige otra dirección para este pedido.'
                        : cargandoBarrio
                          ? 'Consultando el costo del domicilio a tu barrio…'
                          : 'No pudimos consultar el costo del domicilio a tu barrio. Intenta de nuevo o elige otra dirección.'}
                    </p>
                  </div>
                )}
                {direccionError && (
                  <p className="text-[10px] font-bold text-red-500 mt-1 pl-1">
                    {direccionError}
                  </p>
                )}
                {direccionValida && !registrada?.direccion && (
                  <p className="text-xs font-bold text-gray-500 flex items-center gap-1.5">
                    <Save size={12} className="text-green-600 shrink-0" />
                    Como es tu primera dirección, la guardamos en tu perfil como referencia.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Resumen productos */}
          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-50">
              <span className="text-[9px] font-black text-gray-400 uppercase tracking-widest">Productos</span>
              <span className="text-[9px] font-black text-green-700 bg-green-50 px-2 py-0.5 rounded-full">{orderDetails.items.length} items</span>
            </div>
            <div className="max-h-28 overflow-y-auto custom-scrollbar px-3 py-1">
              {orderDetails.items.map(item => (
                <div key={item.id} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                  <span className="text-xs font-bold text-gray-700 flex-1 truncate">{item.nombre}</span>
                  <span className="text-[10px] text-gray-400 font-black mx-2">×{item.cantidad}</span>
                  <span className="text-xs font-black text-gray-900">{COP(item.precio * item.cantidad)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Método de pago. El comprobante ya no se sube acá: si el pedido no
              necesita producción pasa a "Esperando pago" y se adjunta desde
              "Mis pedidos"; si necesita producción, se pide recién cuando el
              admin apruebe la fecha (y solo si el pedido pide anticipo). */}
          <div className="bg-white rounded-2xl border border-gray-100 px-3 py-3 space-y-2.5">
            <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest">
              Método de pago del pedido
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[
                { id: 'digital',  icon: <CreditCard size={14} />, label: 'Transferencia' },
                { id: 'efectivo', icon: <Banknote size={14} />,   label: 'Efectivo' },
                { id: 'mixto',    icon: <Scale size={14} />,      label: 'Mixto' },
              ].filter(m => m.id !== 'mixto' || permiteMixto).map(m => (
                <button key={m.id} onClick={() => setPaymentMethod(m.id)}
                  className={`flex flex-col items-center gap-1.5 p-2.5 rounded-xl border-2 transition-all text-[11px] font-black ${paymentMethod === m.id ? 'border-green-600 bg-green-50 text-green-800' : 'border-gray-100 bg-white text-gray-400 hover:border-gray-200'}`}>
                  <div className={`p-1.5 rounded-lg ${paymentMethod === m.id ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-400'}`}>{m.icon}</div>
                  {m.label}
                </button>
              ))}
            </div>

            {requiereAnticipo && (
              <div className="flex items-start gap-2 bg-yellow-50 border border-yellow-200 rounded-xl px-3 py-2.5">
                <Banknote size={16} className="text-yellow-600 shrink-0 mt-0.5" />
                <p className="text-[10px] font-bold text-yellow-800">
                  Este pedido incluye producción y supera $100.000: una vez el administrador
                  apruebe tu fecha de entrega vas a necesitar pagar un anticipo del 50%
                  (o más) por transferencia antes de que empecemos a producir. Por eso el
                  método mixto no está disponible aquí.
                </p>
              </div>
            )}

            {/* Reparto entre las dos formas de pago */}
            {esMixto && (
              <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                <p className="text-[10px] font-bold text-gray-500 mb-2">
                  Pagas una parte ahora por transferencia y el resto en efectivo al recibir
                </p>
                <SplitPagoMonto
                  total={totalFinal}
                  montoEfectivo={efectivoMonto}
                  onMonto={(v: number | '') => { setEfectivoMonto(v); setMixtoError(''); }}
                  error={mixtoError}
                />
              </div>
            )}

            {(paymentMethod === 'digital' || esMixto) && totalFinal === 0 && (
              <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl px-3 py-2.5">
                <CheckCircle2 size={14} className="text-green-600 shrink-0" />
                <p className="text-xs font-bold text-green-800">Tu saldo a favor cubre el total — no necesitas realizar ningún pago.</p>
              </div>
            )}

            {(paymentMethod === 'digital' || esMixto) && totalFinal > 0 && (
              <div className="space-y-2">
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-3">
                  <p className="text-[9px] font-black text-blue-400 uppercase tracking-widest mb-1.5">
                    Vas a transferir a esta cuenta
                  </p>
                  <div className="space-y-1">
                    {[['Banco', CUENTA.banco], ['Número', CUENTA.numero], ['Tipo', CUENTA.tipo], ['Titular', CUENTA.titular]].map(([l, v]) => (
                      <div key={l} className="flex gap-2">
                        <span className="text-[9px] font-black text-blue-400 uppercase w-12 shrink-0">{l}</span>
                        <span className="text-[10px] font-black text-blue-900">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <p className="text-[10px] font-bold text-blue-700 bg-blue-50 rounded-xl px-3 py-2">
                  {esMixto
                    ? `Vas a transferir ${COP(totalFinal - (Number(efectivoMonto) || 0))} y tener listos ${COP(Number(efectivoMonto) || 0)} en efectivo. `
                    : `Vas a transferir ${COP(totalFinal)}. `}
                  {requiereAnticipo
                    ? 'Sube el comprobante del anticipo cuando el admin apruebe tu fecha (en "Mis pedidos").'
                    : 'Una vez creado el pedido, súbelo desde "Mis pedidos".'}
                </p>
              </div>
            )}
          </div>

          {/* Saldo a favor */}
          {credito > 0 && (
            <SaldoAFavorPicker
              saldo={credito}
              maximo={creditoMaximo}
              activo={usarCredito}
              monto={creditoMonto}
              onToggle={() => {
                const prender = !usarCredito;
                setUsarCredito(prender);
                if (prender) setCreditoMonto(creditoMaximo);
              }}
              onMonto={setCreditoMonto}
            />
          )}

          {/* Observaciones */}
          <div className="bg-white rounded-2xl border border-gray-100 px-3 py-3">
            <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest mb-2">Observaciones del pedido</p>
            <textarea
              rows={2}
              placeholder="Ej: Sin picante, toque el timbre, entregar después de las 5pm..."
              value={observaciones}
              onChange={e => setObservaciones(e.target.value)}
              className="w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-sm text-gray-700 font-medium placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-green-400 transition-all resize-none"
            />
          </div>
        </div>

        {/* Panel de totales — lateral en desktop, sticky abajo en móvil */}
        <aside className="co-side">
          <div className="co-side-inner space-y-1">
            <div className="flex justify-between text-xs text-gray-500 font-bold">
              <span>Subtotal</span><span>{COP(orderDetails.total)}</span>
            </div>
            {tieneDomicilio && barrioDisponible && (
              <div className="flex justify-between text-xs font-bold text-purple-700">
                <span>Domicilio</span>
                <span>
                  {costoDomicilio !== costoDomicilioBase && (
                    <span className="line-through text-gray-400 font-medium mr-1">{COP(costoDomicilioBase)}</span>
                  )}
                  {costoDomicilio === 0 ? 'gratis' : `+${COP(costoDomicilio)}`}
                </span>
              </div>
            )}
            {paymentMethod === 'mixto' && Number(efectivoMonto) > 0 && (
              <>
                <div className="flex justify-between text-[11px] font-bold text-gray-500">
                  <span>En efectivo al recibir</span>
                  <span>{COP(Number(efectivoMonto))}</span>
                </div>
                <div className="flex justify-between text-[11px] font-bold text-gray-500">
                  <span>Por transferencia</span>
                  <span>{COP(totalFinal - Number(efectivoMonto))}</span>
                </div>
              </>
            )}
            {usarCredito && creditoAplicar > 0 && (
              <div className="flex justify-between text-xs font-bold text-green-700">
                <span>Saldo a favor</span><span>−{COP(creditoAplicar)}</span>
              </div>
            )}
            {/* Términos y condiciones */}
            <label style={{
              display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer',
              padding: '10px 12px', borderRadius: 10,
              background: terminosAceptados ? '#f1f8e9' : '#fff8e1',
              border: `1px solid ${terminosAceptados ? '#aed581' : '#ffe082'}`,
              transition: 'background 0.2s, border-color 0.2s',
            }}>
              <input
                type="checkbox"
                checked={terminosAceptados}
                onChange={e => setTerminosAceptados(e.target.checked)}
                style={{ marginTop: 2, accentColor: '#388e3c', width: 15, height: 15, flexShrink: 0 }}
              />
              <span style={{ fontSize: 11, color: '#5d4037', lineHeight: 1.5 }}>
                He leído y acepto los{' '}
                <button
                  type="button"
                  className="co-link"
                  onClick={e => { e.preventDefault(); e.stopPropagation(); setVerTerminos(true); }}
                >
                  términos y condiciones
                </button>
              </span>
            </label>

            <div className="flex items-center justify-between pt-2 border-t border-gray-100">
              <div>
                <p className="text-[9px] font-black text-gray-400 uppercase tracking-widest">
                  Total a pagar
                </p>
                <p className="text-2xl font-black text-gray-900 tracking-tighter leading-none">
                  {COP(totalFinal)}
                </p>
              </div>
              <button
                onClick={handleFinalConfirm}
                disabled={isConfirming || !terminosAceptados}
                title={!terminosAceptados ? 'Debes aceptar los términos y condiciones' : undefined}
                className={`flex items-center gap-2 px-6 py-3 rounded-2xl font-black text-sm transition-all shadow-lg active:scale-95 ${isConfirming || !terminosAceptados ? 'bg-gray-300 text-gray-500 cursor-not-allowed shadow-none' : 'text-white hover:shadow-xl hover:-translate-y-0.5'}`}
                style={(!isConfirming && terminosAceptados) ? { background: 'linear-gradient(135deg, var(--green-800) 0%, var(--green-700) 100%)' } : {}}
              >
                {isConfirming
                  ? <><div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Procesando</>
                  : <>Confirmar <ChevronRight size={14} /></>}
              </button>
            </div>
          </div>
        </aside>
        </div>{/* /co-split */}
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 10px; }
      `}</style>
    </div>
  );
};

export default CheckoutModal;
