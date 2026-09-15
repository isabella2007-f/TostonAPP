import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getPedidos, getMiCredito } from '../../../services/pedidosService.js';
import { fmtFecha } from '../../../utils/dateUtils.js';
import { getProductos } from '../../../services/productosService.js';
import { addToCartWithQty } from '../../sales/orders/services/cartService';
import { getCurrentUser } from '../profile/services/profileService.js';
import { Package, Clock, CheckCircle, UserCircle, Leaf, Gift, ShoppingCart } from 'lucide-react';
import '../../../styles/Client.css';
import { formatCOP as COP } from '../../../utils/formato';


const InicioPage = () => {
  const [productos,   setProductos]   = useState([]);
  const [user,        setUser]        = useState(null);
  const [userPedidos, setUserPedidos] = useState([]);
  const [credito,     setCredito]     = useState(0);

  useEffect(() => {
    const currentUser = getCurrentUser();
    setUser(currentUser);
    getProductos({ porPagina: 100 }).then(data => {
      const lista = (data.productos || data || []).map(p => ({
        id:          p.ID_Producto || p.id,
        nombre:      p.Nombre      || p.nombre      || "",
        precio:      p.Precio_venta || p.Precio_Venta || p.precio || 0,
        stock:       p.Stock       || p.stock       || 0,
        publicado:   !!p.Publicado,
        imagen:      p.Imagen      || p.imagen      || null,
        categoria:          p.nombre_categoria || "",
        requiereProduccion: !!(p.Requiere_Produccion || p.requiere_produccion),
      }));
      setProductos(lista.filter(p => p.publicado));
    }).catch(() => {});
    if (currentUser) {
      getPedidos({ porPagina: 100 }).then(data => {
        const todos = data.pedidos || [];
        setUserPedidos(todos.filter(p => p.cliente?.correo === currentUser.correo || p.idCliente === currentUser.id));
      }).catch(() => {});
      getMiCredito().then(d => setCredito(d?.saldo || 0)).catch(() => {});
    }
  }, []);

  const getCategoriaNombre = (p) => p.categoria || 'Sin categoría';

  const getEstadoColor = (estado) => {
    switch (estado) {
      case 'Entregado': return { bg: 'var(--green-100)', color: 'var(--green-800)' };
      case 'En camino': return { bg: 'var(--blue-100)', color: 'var(--blue-800)' };
      case 'En producción': return { bg: 'var(--yellow-100)', color: 'var(--yellow-800)' };
      default: return { bg: 'var(--gray-100)', color: 'var(--gray-800)' };
    }
  };

  if (!user) return <div className="toston-page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
    <div style={{ textAlign: 'center', color: 'var(--gray-500)' }}>
      <Clock size={36} strokeWidth={1} style={{color:"#bdbdbd", marginBottom: 12}} />
      <p>Cargando...</p>
    </div>
  </div>;

  return (
    <div className="toston-page">

      {/* Hero */}
      <header className="page-hero">
        <div className="page-hero__inner">
          <div>
            <span className="page-hero__label">
              <Leaf size={11} /> Tostón App
            </span>
            <h1 className="page-hero__title">
              ¡Hola, <em>{user.nombre}</em>!
            </h1>
            <p className="page-hero__sub">
              Bienvenido de vuelta. Explora nuestros productos y revisa tus pedidos.
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="page-hero__badge">
              <span className="page-hero__badge-icon">
                <UserCircle size={18} color="white" />
              </span>
              {user.nombre} {user.apellidos}
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="page-content">
        <div style={{ display: 'grid', gap: 32 }}>

          {/* Estadísticas rápidas */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            <div className="card" style={{ padding: 20, textAlign: 'center' }}>
              <Package size={32} color="var(--green-600)" style={{ marginBottom: 8 }} />
              <p style={{ margin: 0, fontSize: 24, fontWeight: 800, color: 'var(--gray-900)' }}>{userPedidos.length}</p>
              <p style={{ margin: 0, fontSize: 14, color: 'var(--gray-500)' }}>Pedidos realizados</p>
            </div>

            {credito > 0 && (
              <div className="card" style={{ padding: 20, textAlign: 'center', background: 'linear-gradient(135deg, #f3e5f5 0%, #fff 100%)', border: '1.5px solid #ce93d8' }}>
                <Gift size={32} color="#7b1fa2" style={{ marginBottom: 8 }} />
                <p style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#4a148c' }}>{COP(credito)}</p>
                <p style={{ margin: 0, fontSize: 13, color: '#7b1fa2', fontWeight: 600 }}>Saldo a favor</p>
                <p style={{ margin: '4px 0 0', fontSize: 11, color: '#9e9e9e' }}>Aplica en tu próxima compra</p>
              </div>
            )}

            <div className="card" style={{ padding: 20, textAlign: 'center' }}>
              <Clock size={32} color="var(--blue-600)" style={{ marginBottom: 8 }} />
              <p style={{ margin: 0, fontSize: 24, fontWeight: 800, color: 'var(--gray-900)' }}>
                {userPedidos.filter(p => p.estado === 'En producción' || p.estado === 'Pendiente').length}
              </p>
              <p style={{ margin: 0, fontSize: 14, color: 'var(--gray-500)' }}>Pedidos activos</p>
            </div>

            <div className="card" style={{ padding: 20, textAlign: 'center' }}>
              <CheckCircle size={32} color="var(--green-600)" style={{ marginBottom: 8 }} />
              <p style={{ margin: 0, fontSize: 24, fontWeight: 800, color: 'var(--gray-900)' }}>
                {userPedidos.filter(p => p.estado === 'Entregado').length}
              </p>
              <p style={{ margin: 0, fontSize: 14, color: 'var(--gray-500)' }}>Pedidos completados</p>
            </div>
          </div>

          {/* Nuestros productos */}
          <section>
            <h2 style={{ marginBottom: 16, fontSize: 20, fontWeight: 700, color: 'var(--gray-900)' }}>
              Nuestros productos
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 20 }}>
              {productos.map(producto => {
                const agotado = producto.stock === 0;
                return (
                  <div key={producto.id} className="card" style={{ padding: 20, cursor: agotado ? 'default' : 'pointer', transition: 'transform 0.2s', opacity: agotado ? 0.75 : 1 }}
                       onMouseEnter={e => { if (!agotado) e.currentTarget.style.transform = 'translateY(-2px)'; }}
                       onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div style={{ position: 'relative', width: '100%', height: 150, background: 'var(--gray-100)', borderRadius: 8, marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', filter: agotado ? 'grayscale(0.6)' : 'none' }}>
                      <Package size={48} strokeWidth={1} style={{color:"#bdbdbd"}} />
                      {agotado && (
                        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.25)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <span style={{ background: '#d32f2f', color: '#fff', fontWeight: 800, fontSize: 12, padding: '4px 14px', borderRadius: 99, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                            Agotado
                          </span>
                        </div>
                      )}
                    </div>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--gray-900)', marginBottom: 8 }}>
                      {producto.nombre}
                    </h3>
                    <p style={{ margin: 0, fontSize: 12, color: 'var(--gray-500)', marginBottom: 8 }}>
                      {getCategoriaNombre(producto)}
                    </p>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 18, fontWeight: 800, color: agotado ? 'var(--gray-400)' : 'var(--green-700)' }}>
                        {COP(producto.precio)}
                      </span>
                      <span style={{ fontSize: 12, color: agotado ? '#d32f2f' : 'var(--gray-500)', fontWeight: agotado ? 700 : 400 }}>
                        {agotado ? 'Sin stock' : `Stock: ${producto.stock}`}
                      </span>
                    </div>
                    <button
                      className="btn-primary"
                      disabled={agotado}
                      data-tooltip={agotado ? 'Producto sin stock' : 'Agregar al carrito'}
                      onClick={() => !agotado && addToCartWithQty(producto, 1)}
                      style={{ width: '100%', marginTop: 12, justifyContent: 'center', opacity: agotado ? 0.5 : 1, cursor: agotado ? 'not-allowed' : 'pointer' }}
                    >
                      <ShoppingCart size={14} /> {agotado ? 'Sin stock' : 'Agregar al carrito'}
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Pedidos recientes */}
          <section>
            <h2 style={{ marginBottom: 16, fontSize: 20, fontWeight: 700, color: 'var(--gray-900)' }}>
              Tus pedidos recientes
            </h2>
            {userPedidos.length === 0 ? (
              <div className="card" style={{ padding: 40, textAlign: 'center' }}>
                <Package size={48} color="var(--gray-300)" style={{ marginBottom: 16 }} />
                <p style={{ margin: 0, color: 'var(--gray-500)' }}>No tienes pedidos aún</p>
                <p style={{ margin: '8px 0 0', fontSize: 14, color: 'var(--gray-400)' }}>
                  ¡Explora nuestros productos y haz tu primer pedido!
                </p>
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 12 }}>
                {userPedidos.slice(0, 5).map(pedido => {
                  const estadoStyle = getEstadoColor(pedido.estado);
                  return (
                    <div key={pedido.id} className="card" style={{ padding: 20 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                        <div>
                          <h4 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--gray-900)' }}>
                            {pedido.numero}
                          </h4>
                          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--gray-500)' }}>
                            {fmtFecha(pedido.fecha_pedido)} • {pedido.productosItems.length} producto{pedido.productosItems.length !== 1 ? 's' : ''}
                          </p>
                        </div>
                        <span style={{
                          padding: '4px 12px', borderRadius: 99, fontSize: 11, fontWeight: 700,
                          background: estadoStyle.bg, color: estadoStyle.color
                        }}>
                          {pedido.estado}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-900)' }}>
                          Total: {COP(pedido.total)}
                        </span>
                        <button className="btn-secondary" data-tooltip="Ver detalles del pedido" style={{ fontSize: 12, padding: '6px 12px' }}>
                          Ver detalles
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

        </div>
      </main>
    </div>
  );
};

export default InicioPage;