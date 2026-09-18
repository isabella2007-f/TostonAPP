import { useState, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { getUser, logout } from "../../services/authService";
import { getMiCredito } from "../../services/pedidosService";
import { formatCOP } from "../../utils/formato";
import Avatar from "./Avatar";
import { crearPedidoCliente, resolverEntrega } from "../../features/sales/orders/services/crearPedidoCliente";
import { Menu, X, ShoppingCart, Bell, LogOut, Gift, CheckCircle2, AlertCircle } from "lucide-react";
import "./Navbar.css";
import { getCartCount, getCart, getTotal, clearCart } from "../../features/sales/orders/services/cartService";
import CartAside from "../../features/sales/orders/components/CartAside";
import CheckoutModal from "../../features/sales/orders/components/CheckoutModal";
import LogoutModal from "./LogoutModal";
import { useNotificaciones } from "../../features/notificaciones/context/NotificacionesContext";
import NotificacionesPanel from "../../features/notificaciones/components/NotificacionesPanel";
import AlertaBanner from "../../features/notificaciones/components/AlertaBanner";
import "../../features/notificaciones/components/notificaciones.css";

export default function Navbar({ isLanding = false, onToggleSidebar }) {
  const [menuOpen,         setMenuOpen]         = useState(false);
  const [user,             setUser]             = useState(null);
  const [cartCount,        setCartCount]        = useState(0);
  const [isCartOpen,       setIsCartOpen]       = useState(false);
  const [isCheckoutOpen,   setIsCheckoutOpen]   = useState(false);
  const [orderDetails,     setOrderDetails]     = useState(null);
  const [cartUpdateToggle, setCartUpdateToggle] = useState(false);
  const [showLogoutModal,  setShowLogoutModal]  = useState(false);
  const [notifOpen,        setNotifOpen]        = useState(false);
  const [credito,          setCredito]          = useState(0);
  const [navToast,         setNavToast]         = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  const { noLeidas, agregarNotificacion } = useNotificaciones();
  useEffect(() => {
    const u = getUser();
    setUser(u);
    updateCartCount();

    if (u?.tipo === 'cliente') {
      getMiCredito().then(d => setCredito(d?.saldo || 0)).catch(() => {});
    }

    const handleCartUpdate = () => {
      updateCartCount();
      setCartUpdateToggle(prev => !prev);
    };
    const handleCreditoUpdate = () => {
      getMiCredito().then(d => setCredito(d?.saldo || 0)).catch(() => {});
    };

    const handleProfileUpdate = () => setUser(getUser());

    window.addEventListener('cart-updated', handleCartUpdate);
    window.addEventListener('credito-updated', handleCreditoUpdate);
    window.addEventListener('profileUpdated', handleProfileUpdate);
    return () => {
      window.removeEventListener('cart-updated', handleCartUpdate);
      window.removeEventListener('credito-updated', handleCreditoUpdate);
      window.removeEventListener('profileUpdated', handleProfileUpdate);
    };
  }, []);

  const updateCartCount = () => setCartCount(getCartCount());

  const handleLogout = () => setShowLogoutModal(true);
  const confirmLogout = () => { logout(); navigate("/login"); };

  const handleCheckout = (details) => {
    const currentUser = getUser();
    if (!currentUser) { navigate("/login"); return; }
    setOrderDetails({
      ...details,
      clientName: currentUser.nombre || 'Cliente',
      address: details.address || currentUser.direccion || '',
      departamento: details.departamento || currentUser.departamento || '',
      items: getCart(),
      total: getTotal(),
    });
    setIsCartOpen(false);
    setIsCheckoutOpen(true);
  };

  const handleLoginRequired = () => navigate("/login");

  const showNavToast = (msg, type = 'success') => {
    setNavToast({ msg, type });
    setTimeout(() => setNavToast(null), 3500);
  };

  const handleConfirmOrder = async (paymentMethod, saldoAFavor, deliveryInfo) => {
    try {
      await crearPedidoCliente({
        paymentMethod, saldoAFavor,
        deliveryInfo, orderDetails,
      });
      clearCart();
      setIsCheckoutOpen(false);
      updateCartCount();
      showNavToast('¡Pedido creado exitosamente!');
      navigate('/cliente/pedidos');
    } catch (err) {
      showNavToast(err.message || 'Error al registrar el pedido', 'error');
    }
  };

  const isOnLanding = location.pathname === '/';

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
    setMenuOpen(false);
  };

  const mostrarCampana = !!user;

  return (
    <>
      {navToast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 99999,
          background: navToast.type === 'error' ? '#c62828' : '#2e7d32',
          color: '#fff', padding: '12px 20px', borderRadius: 12,
          display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 14,
          boxShadow: '0 8px 32px rgba(0,0,0,.18)',
        }}>
          {navToast.type === 'error' ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
          {navToast.msg}
        </div>
      )}
      <nav className={`navbar ${isLanding ? 'is-landing' : ''}`}>
        <div className="navbar-inner">

          {/* CENTER — Logo */}
          <div
            className="logo-wrapper"
            onClick={() => navigate('/')}
            style={{ cursor: 'pointer' }}
            data-tooltip="Ir a la página principal"
          >
            <img src="/Logo.png" alt="Logo" width={713} height={350} className="logo" />
          </div>

          {/* RIGHT — íconos de acción */}
          <div className="nav-right">
            {/* Navegación de página */}
            {(isLanding || user?.tipo === 'cliente' || user?.tipo === 'empleado') && (
              <div className="nav-links">
                {isLanding && (
                  <>
                    <button
                      onClick={() => isOnLanding ? scrollToSection('inicio')    : navigate('/')}
                      className="nav-link"
                    >Inicio</button>
                    <button
                      onClick={() => isOnLanding ? scrollToSection('productos') : navigate({ pathname: '/', hash: '#productos' })}
                      className="nav-link"
                    >Productos</button>
                    <button
                      onClick={() => isOnLanding ? scrollToSection('contacto')  : navigate({ pathname: '/', hash: '#contacto' })}
                      className="nav-link"
                    >Nosotros</button>
                  </>
                )}
                {user?.tipo === 'cliente' && (
                  <>
                    <button onClick={() => navigate('/cliente/inicio')}  className="nav-link">Página Principal</button>
                    <button onClick={() => navigate('/cliente/pedidos')} className="nav-link">Mis Pedidos</button>
                  </>
                )}
                {user?.tipo === 'empleado' && (
                  <Link to="/admin" className="nav-link" style={{ fontWeight: 700, color: 'var(--g)' }}>Dashboard</Link>
                )}
              </div>
            )}

            {/* Campanita */}
            {mostrarCampana && (
              <button
                className="bell-btn"
                onClick={() => setNotifOpen(true)}
                data-tooltip="Notificaciones"
                aria-label={`${noLeidas} notificaciones sin leer`}
              >
                <Bell size={22} />
                {noLeidas > 0 && (
                  <span className="bell-badge">
                    {noLeidas > 99 ? "99+" : noLeidas}
                  </span>
                )}
              </button>
            )}

            {/* Carrito */}
            {(user?.tipo === "cliente" || (!user && isLanding)) && (
              <button
                className="cart-btn"
                onClick={() => setIsCartOpen(prev => !prev)}
                data-tooltip={isCartOpen ? "Cerrar carrito" : "Ver carrito"}
              >
                <ShoppingCart size={22} />
                {cartCount > 0 && <span className="cart-badge">{cartCount}</span>}
              </button>
            )}

            {/* Saldo a favor (solo clientes) */}
            {user?.tipo === 'cliente' && credito > 0 && (
              <button
                className="credito-chip"
                onClick={() => navigate('/cliente/perfil')}
                data-tooltip="Ver mi saldo a favor"
              >
                <Gift size={14} style={{ marginRight: 4 }} />{formatCOP(credito)}
              </button>
            )}

            {/* Avatar usuario logueado */}
            {user && (
              <div
                className="user-area"
                onClick={() => navigate(user.tipo === "cliente" ? "/cliente/perfil" : "/admin/perfil")}
                style={{ cursor: 'pointer' }}
              >
                <div className="avatar">
                  {(user.fotoPerfil || user.Foto_perfil)
                    ? <Avatar url={user.fotoPerfil || user.Foto_perfil}
                              lado={32} alt={user.nombre} />
                    : user.nombre.charAt(0)
                  }
                </div>
                <div className="user-info-text">
                  <div className="user-name">{user.nombre}</div>
                  <div className="user-role">{user.rol}</div>
                </div>
              </div>
            )}

            {/* Botones login/register para invitados en landing */}
            {isLanding && !user && (
              <div className="auth-btns">
                <button onClick={() => navigate("/login")} className="btn-login-nav">Iniciar sesión</button>
                <button onClick={() => navigate("/register")} className="btn-register-nav">Registrarse</button>
              </div>
            )}

            {/* Logout */}
            {user && (
              <button className="logout-btn" data-tooltip="Cerrar sesión" onClick={handleLogout}><LogOut size={20} /></button>
            )}
          </div>
        </div>
      </nav>

      {/* Panel notificaciones */}
      {mostrarCampana && (
        <>
          <NotificacionesPanel
            isOpen={notifOpen}
            onClose={() => setNotifOpen(false)}
          />
          <AlertaBanner onVerTodas={() => { setNotifOpen(true); }} />
        </>
      )}

      {/* Cart */}
      <CartAside
        isOpen={isCartOpen}
        onClose={() => setIsCartOpen(false)}
        onCheckout={handleCheckout}
        onLoginRequired={handleLoginRequired}
        cartUpdateToggle={cartUpdateToggle}
      />

      {orderDetails && (
        <CheckoutModal
          isOpen={isCheckoutOpen}
          onClose={() => setIsCheckoutOpen(false)}
          orderDetails={orderDetails}
          onConfirm={handleConfirmOrder}
        />
      )}

      {showLogoutModal && (
        <LogoutModal
          onConfirm={confirmLogout}
          onCancel={() => setShowLogoutModal(false)}
        />
      )}
    </>
  );
}