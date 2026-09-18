import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import MainLayout from "../layouts/MainLayout";

/* ─── PÚBLICO — carga inmediata ─── */
import LandingPage from "../pages/LandingPage";
import Login from "../pages/Login";
import Register from "../pages/Register";
import ForgotPassword from "../pages/Forgotpassword";
import SinAcceso from "../pages/SinAcceso";
import ProtectedRoute from "../components/ProtectedRoute";
import PrivilegioRoute from "../components/PrivilegioRoute";
import RepartidorRoute from "../components/RepartidorRoute";
import { usePrivilegio } from "../context/PrivilegiosContext";
import { esRolRepartidor, INICIO_REPARTIDOR } from "../utils/roles";
import { initUsers } from "../services/userService";
import { getUser } from "../services/authService";

/* ─── ADMIN — carga diferida por ruta ─── */
const Dashboard                  = lazy(() => import("../features/dashboard/Dashboard"));
const PanelInicio                = lazy(() => import("../features/dashboard/PanelInicio"));
const GestionUsuarios            = lazy(() => import("../features/configuracion/Usuarios/GestionUsuarios"));
const Empleados                  = lazy(() => import("../features/configuracion/empleados/Empleados"));
const Roles                      = lazy(() => import("../features/configuracion/roles/Roles"));
const GestionSalidas             = lazy(() => import("../features/salidas/GestionSalidas"));
const Ubicaciones                = lazy(() => import("../features/configuracion/ubicaciones/Ubicaciones"));
const CategoriaProductos         = lazy(() => import("../features/produccion/categoria_productos/Categoriaproductos"));
const Productos                  = lazy(() => import("../features/produccion/Productos/Productos"));
const GestionOrdenesProduccion   = lazy(() => import("../features/produccion/orden_produccion/GestionOrdenesProduccion"));
const DashboardCocina            = lazy(() => import("../features/produccion/cocina/DashboardCocina"));
const GestionPedidos             = lazy(() => import("../features/ventas/pedidos/GestionPedidos"));
const GestionDevoluciones        = lazy(() => import("../features/ventas/devoluciones/GestionDevoluciones"));
const GestionDomicilios          = lazy(() => import("../features/ventas/domicilios/Gestiondomicilios"));
const GestionDomiciliosRepartidor = lazy(() => import("../features/ventas/domicilios/GestionDomiciliosRepartidor"));
const DashboardDomiciliario      = lazy(() => import("../features/ventas/domicilios/DashboardDomiciliario"));
const PedidoActual               = lazy(() => import("../features/ventas/domicilios/PedidoActual"));
const HistorialEntregas          = lazy(() => import("../features/ventas/domicilios/HistorialEntregas"));
const PerfilDomiciliario         = lazy(() => import("../features/ventas/domicilios/PerfilDomiciliario"));
const GananciasDomiciliario      = lazy(() => import("../features/ventas/domicilios/GananciasDomiciliario"));
const NotificacionesDomiciliario = lazy(() => import("../features/ventas/domicilios/NotificacionesDomiciliario"));
const CategoriaInsumos           = lazy(() => import("../features/compras/categoriainsumos/CategoriaInsumos"));
const GestionInsumos             = lazy(() => import("../features/compras/insumos/GestionInsumos"));
const GestionCompras             = lazy(() => import("../features/compras/gestioncompras/GestionCompras"));
const Proveedores                = lazy(() => import("../features/compras/proveedores/Proveedores"));
const EditarLanding              = lazy(() => import("../features/configuracion/landing/EditarLanding"));

/* ─── CLIENTE — carga diferida por ruta ─── */
const PedidosClientePage = lazy(() => import("../features/sales/orders/PedidosClientePage"));
const ReturnsPage        = lazy(() => import("../features/sales/returns/ReturnsPage"));
const DeliveryPage       = lazy(() => import("../features/sales/delivery/DeliveryPage"));
const ProfilePage        = lazy(() => import("../features/client/profile/ProfilePage"));

/* ─── INIT ─── */
initUsers();

/* ─── HELPERS ─── */
const PR = ({ clave, el }) => <PrivilegioRoute clave={clave}>{el}</PrivilegioRoute>;
const RR = ({ el }) => <RepartidorRoute>{el}</RepartidorRoute>;

function CocinaRoute() {
  const user = getUser();
  if (user?.rol?.toLowerCase() !== "cocinero") {
    return <Navigate to="/sin-acceso" replace />;
  }
  return <DashboardCocina />;
}

function DashboardIndex() {
  const user = getUser();
  const puedeVerDashboard = usePrivilegio("Dashboard_ver");
  if (esRolRepartidor(user?.rol)) {
    return <Navigate to={INICIO_REPARTIDOR} replace />;
  }
  if (user?.rol?.toLowerCase() === "cocinero") {
    return <Navigate to="/admin/cocina" replace />;
  }
  return puedeVerDashboard ? <Dashboard /> : <PanelInicio />;
}

/* Indicador de carga mientras se descarga el chunk de la ruta */
function PageLoader() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
      <div style={{
        width: 40, height: 40, borderRadius: "50%",
        border: "3px solid #c8e6c9", borderTopColor: "#1b5e20",
        animation: "spin 0.8s linear infinite",
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

const AppRouter = () => {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>

          {/* ───────────── PÚBLICO ───────────── */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/recuperar" element={<ForgotPassword />} />
          <Route path="/sin-acceso" element={<SinAcceso />} />

          {/* ───────────── ADMIN ───────────── */}
          <Route element={<ProtectedRoute allowedRoles={["empleado"]} />}>
            <Route path="/admin" element={<MainLayout />}>

              <Route index element={<DashboardIndex />} />

              {/* Sitio Web */}
              <Route path="landing"    element={<PR clave="LandingPage_editar" el={<EditarLanding />} />} />

              {/* Configuración */}
              <Route path="usuarios"    element={<PR clave="Usuarios_ver"      el={<GestionUsuarios />} />} />
              <Route path="empleados"   element={<PR clave="Usuarios_ver"      el={<Empleados />} />} />
              <Route path="roles"       element={<PR clave="Roles_ver"         el={<Roles />} />} />
              <Route path="salidas"     element={<PR clave="GestionSalidas_ver" el={<GestionSalidas />} />} />
              <Route path="ubicaciones" element={<PR clave="Ubicaciones_ver"   el={<Ubicaciones />} />} />

              {/* Producción */}
              <Route path="categorias_productos"  element={<PR clave="CategoriaProductos_ver" el={<CategoriaProductos />} />} />
              <Route path="products"              element={<PR clave="GestionProductos_ver"   el={<Productos />} />} />
              <Route path="ordenes-produccion"    element={<PR clave="OrdenesProduccion_ver"  el={<GestionOrdenesProduccion />} />} />
              <Route path="cocina"               element={<CocinaRoute />} />

              {/* Ventas */}
              <Route path="pedidos"       element={<PR clave="Pedidos_ver"      el={<GestionPedidos />} />} />
              <Route path="devoluciones"  element={<PR clave="Devoluciones_ver" el={<GestionDevoluciones />} />} />
              <Route path="domicilios"           element={<PR clave="Domicilios_ver"            el={<GestionDomicilios />} />} />
              <Route path="mis-entregas"         element={<RR el={<GestionDomiciliosRepartidor />} />} />
              <Route path="mi-dashboard"         element={<RR el={<DashboardDomiciliario />} />} />
              <Route path="pedido-actual"        element={<RR el={<PedidoActual />} />} />
              <Route path="historial-entregas"   element={<RR el={<HistorialEntregas />} />} />
              <Route path="mis-ganancias"        element={<RR el={<GananciasDomiciliario />} />} />
              <Route path="mis-notificaciones"   element={<RR el={<NotificacionesDomiciliario />} />} />
              <Route path="mi-perfil-repartidor" element={<RR el={<PerfilDomiciliario />} />} />

              {/* Compras */}
              <Route path="categorias_insumos" element={<PR clave="CategoriaInsumos_ver" el={<CategoriaInsumos />} />} />
              <Route path="gestion-insumos"    element={<PR clave="Insumos_ver"          el={<GestionInsumos />} />} />
              <Route path="compras"            element={<PR clave="Compras_ver"          el={<GestionCompras />} />} />
              <Route path="proveedores"        element={<PR clave="Proveedores_ver"      el={<Proveedores />} />} />

              {/* Perfil — sin restricción */}
              <Route path="perfil" element={<ProfilePage />} />

            </Route>
          </Route>

          {/* ───────────── CLIENTE ───────────── */}
          <Route element={<ProtectedRoute allowedRoles={["cliente"]} />}>
            <Route path="/cliente" element={<MainLayout />}>

              <Route index                  element={<LandingPage hideNavbar={true} />} />
              <Route path="inicio"         element={<LandingPage hideNavbar={true} />} />
              <Route path="pedidos"        element={<PedidosClientePage />} />
              <Route path="domicilios"         element={<DeliveryPage />} />
              <Route path="devoluciones"       element={<ReturnsPage />} />
              <Route path="perfil"             element={<ProfilePage />} />

            </Route>
          </Route>

          {/* ───────────── 404 ───────────── */}
          <Route path="*" element={<h1>404 - Página no encontrada</h1>} />

        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default AppRouter;
