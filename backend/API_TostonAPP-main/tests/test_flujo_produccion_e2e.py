"""Del pedido a la entrega, pasando por el horno. Con base de datos de verdad.

`test_flujo_produccion.py` mira las piezas con dobles de prueba; esto arma una
SQLite en memoria con los modelos reales y recorre el camino entero:

    pedido con faltante
      → orden de producción por el faltante exacto
      → iniciarla descuenta los insumos de la receta (y sus lotes, FEFO)
      → completarla repone el stock del producto y crea su lote
      → recién ahí el pedido pasa a Listo
      → y al entregarlo sale del inventario lo que se llevó el cliente

Es el recorrido que nadie prueba a mano completo y donde se esconden los
descuadres de inventario: cada paso mueve stock en un momento distinto.

Corre sin credenciales:
    DB_USER=u DB_PASSWORD=p DB_HOST=localhost DB_PORT=3306 DB_NAME=test \
        python tests/test_flujo_produccion_e2e.py
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DB_USER", "u")
os.environ.setdefault("DB_PASSWORD", "p")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "test")

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.features.produccion.ordenes_produccion.services.service import (
    anular_orden,
    cambiar_estado as cambiar_estado_orden,
    crear_orden,
    editar_orden,
)
from src.features.produccion.ordenes_produccion.services.schemas import OrdenCreate, OrdenUpdate
from src.features.produccion.productos.services.service import gestionar_ficha
from src.features.produccion.productos.services.schemas import FichaTecnicaInput, FichaTecnicaInsumoInput
from src.features.ventas.gestion_ventas.services.schemas import (
    DomicilioVentaInput,
    ProductoVentaInput,
    VentaCreate,
)
from src.features.ventas.gestion_ventas.services.service import (
    cambiar_estado,
    crear_venta,
    registrar_pago_final,
)
from src.features.ventas.pedidos.services.estados import EstadoPedido
from src.shared.services.models import (
    Barrio,
    Base,
    Ciudad,
    Departamento,
    Domicilio,
    FichaTecnica,
    FichaTecnicaInsumo,
    Insumo,
    LoteCompra,
    LoteProducto,
    OrdenProduccion,
    Producto,
    UnidadMedida,
    Usuario,
    Venta,
    VentaXProducto,
)

PRECIO = Decimal("10000")
ID_CLIENTE = 1
ID_TORTA = 1
ID_HARINA = 1
ID_BARRIO = 1

STOCK_TORTA = 2       # hay 2 en vitrina
PEDIDAS = 6           # el cliente pide 6 → faltan 4, y son $60.000
FALTANTE = PEDIDAS - STOCK_TORTA

GRAMOS_POR_TORTA = 200.0
STOCK_HARINA = 2000.0
GASTO_ESPERADO = GRAMOS_POR_TORTA * FALTANTE   # 800 g

ORDEN_PENDIENTE = 1
ORDEN_EN_PROCESO = 13
ORDEN_COMPLETADA = 11
ORDEN_CANCELADA = 5


class FlujoProduccionE2EBase(unittest.TestCase):
    """Panadería sembrada: una torta con receta y harina en lotes."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self._sembrar()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _sembrar(self):
        self.db.add(Departamento(ID_Departamento=1, Nombre="Antioquia", Estado=1))
        self.db.add(Ciudad(ID_Ciudad=1, ID_Departamento=1, Nombre="Medellín", Estado=1))
        self.db.add(Barrio(
            ID_Barrio=ID_BARRIO, ID_Ciudad=1, Nombre="Centro",
            Precio=5000, Es_Base=True, Estado=1,
        ))
        self.db.add(Usuario(
            ID_Usuario=ID_CLIENTE, Nombre="Cliente", Apellidos="De Prueba",
            Correo="cliente@prueba.test", Telefono="3001234567",
            ID_Rol=3, Estado=1,
        ))
        self.db.add(Producto(
            ID_Producto=ID_TORTA, nombre="Torta Tropical",
            Precio_venta=PRECIO, Stock=STOCK_TORTA, Stock_Minimo=1,
            Estado=1, Publicado=1,
        ))
        self.db.add(UnidadMedida(ID_Unidad_Medida=1, Simbolo="g", Unidad_Medida="Gramos"))
        self.db.add(Insumo(
            ID_Insumo=ID_HARINA, Nombre="Harina", Unidad_Medida=1,
            Stock_Actual=STOCK_HARINA, Stock_Minimo=100, Estado=1,
        ))
        # Dos lotes: el que vence antes tiene que salir primero (FEFO).
        hoy = datetime.now()
        self.db.add(LoteCompra(
            ID_Lote_Compra=1, ID_Insumo=ID_HARINA,
            Fecha_Vencimiento=hoy + timedelta(days=10),
            Cantidad_Inicial=500.0, Cantidad_Actual=500.0, Estado=1,
        ))
        self.db.add(LoteCompra(
            ID_Lote_Compra=2, ID_Insumo=ID_HARINA,
            Fecha_Vencimiento=hoy + timedelta(days=90),
            Cantidad_Inicial=1500.0, Cantidad_Actual=1500.0, Estado=1,
        ))
        # La receta: 200 g de harina por torta.
        self.db.add(FichaTecnica(
            ID_Ficha=1, ID_Producto=ID_TORTA, Version="1", Estado=1,
            Dias_Vida_Util=5, Vida_Util_Unidad="dias",
        ))
        self.db.add(FichaTecnicaInsumo(
            ID_Ficha_Insumo=1, ID_Ficha=1, ID_Insumo=ID_HARINA,
            Cantidad=GRAMOS_POR_TORTA, Unidad="g",
        ))
        self.db.commit()

    # ── Ayudas ───────────────────────────────────────────────────────────
    def pedido(self, cantidad=PEDIDAS, **kwargs):
        """Pedido que pide anticipo: hay que hornear y pasa de $50.000."""
        base = dict(
            ID_Usuario=ID_CLIENTE,
            Metodo_Pago="Transferencia",
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=cantidad)],
            requiere_anticipo=True,
            anticipo_monto=30000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        )
        base.update(kwargs)
        return VentaCreate(**base)

    def domicilio(self, **kwargs):
        base = dict(
            Direccion_entrega="Calle 10 #20-30",
            ID_Barrio=ID_BARRIO,
        )
        base.update(kwargs)
        return DomicilioVentaInput(**base)

    def crear(self, datos=None):
        datos = datos if datos is not None else self.pedido()
        # Fecha límite obligatoria para lo que hay que fabricar (ver
        # test_crear_venta_e2e.py: mismo criterio, mismo motivo).
        if getattr(datos, "Fecha_entrega_esperada", None) is None and not datos.creado_por_admin:
            from datetime import datetime, timedelta
            datos.Fecha_entrega_esperada = datetime.now() + timedelta(days=2)
        resultado = crear_venta(self.db, datos)
        self.db.commit()
        return resultado

    def venta(self):
        return self.db.query(Venta).first()

    def orden(self):
        return self.db.query(OrdenProduccion).first()

    def harina(self):
        return self.db.query(Insumo).filter(Insumo.ID_Insumo == ID_HARINA).first()

    def stock_torta(self):
        return self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TORTA
        ).first().Stock

    def lote_compra(self, id_lote):
        return self.db.query(LoteCompra).filter(
            LoteCompra.ID_Lote_Compra == id_lote
        ).first()

    def mover_orden(self, estado):
        resultado = cambiar_estado_orden(self.db, self.orden().ID_Orden_Produccion, estado)
        self.db.commit()
        return resultado

    def hornear(self):
        """Inicia y completa la orden: el faltante ya existe."""
        self.mover_orden(ORDEN_EN_PROCESO)
        self.mover_orden(ORDEN_COMPLETADA)

    def pagar_saldo(self):
        """El saldo tras el anticipo; sin él no se puede entregar."""
        from src.features.ventas.gestion_ventas.services.schemas import PagoFinalCreate
        registrar_pago_final(self.db, self.venta().ID_Venta, PagoFinalCreate(
            monto=30000.0,
            metodo_pago="Efectivo",
        ))
        self.db.commit()


# ══════════════════════════════════════════════════════════════════════════
# 1. La orden nace del faltante
# ══════════════════════════════════════════════════════════════════════════
class OrdenDelFaltanteTests(FlujoProduccionE2EBase):

    def test_se_abre_una_orden_por_las_unidades_que_faltan(self):
        """6 pedidas, 2 en vitrina: la orden es por 4, no por 6."""
        self.crear()
        orden = self.orden()
        self.assertIsNotNone(orden)
        self.assertEqual(orden.Cantidad, FALTANTE)
        self.assertEqual(orden.ID_Producto, ID_TORTA)
        self.assertEqual(orden.Estado, ORDEN_PENDIENTE)

    def test_la_orden_nace_con_la_receta_enganchada(self):
        """Sin ficha la orden ni se puede iniciar: se resuelve al crearla."""
        self.crear()
        self.assertEqual(self.orden().ID_Ficha, 1)

    def test_el_pedido_queda_atado_a_su_orden(self):
        self.crear()
        self.assertEqual(self.orden().ID_Venta, self.venta().ID_Venta)
        self.assertEqual(self.venta().Necesita_Produccion, 1)
        self.assertEqual(self.venta().Sobre_Stock, 1)

    def test_lo_que_cabe_en_el_stock_no_abre_ninguna_orden(self):
        self.crear(self.pedido(
            cantidad=2,
            requiere_anticipo=False,
            anticipo_monto=None,
            anticipo_metodo_pago=None,
            anticipo_comprobante_url=None,
            anticipo_registrado=False,
        ))
        self.assertIsNone(self.orden())
        self.assertEqual(self.venta().Necesita_Produccion, 0)

    def test_confirmar_dos_veces_no_duplica_la_produccion(self):
        """La creación ya la abrió; confirmar no puede abrir otra igual."""
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        self.assertEqual(self.db.query(OrdenProduccion).count(), 1)


# ══════════════════════════════════════════════════════════════════════════
# 2. Iniciar la orden descuenta los insumos
# ══════════════════════════════════════════════════════════════════════════
class InsumosTests(FlujoProduccionE2EBase):

    def test_iniciar_aparta_los_insumos_pero_no_los_descuenta(self):
        """La harina sigue en bodega hasta que la orden se completa.

        Arrancar solo la pisa: nadie más puede contar con ella, pero todavía
        está ahí. Antes se descontaba al arrancar, y una orden anulada a mitad
        obligaba a devolverla a mano al inventario.
        """
        self.crear()
        self.mover_orden(ORDEN_EN_PROCESO)
        self.assertAlmostEqual(float(self.harina().Stock_Actual), STOCK_HARINA, places=3)

    def test_completar_descuenta_la_receta_por_la_cantidad_de_la_orden(self):
        """200 g por torta × 4 tortas = 800 g de harina."""
        self.crear()
        self.hornear()
        self.assertAlmostEqual(
            float(self.harina().Stock_Actual), STOCK_HARINA - GASTO_ESPERADO, places=3
        )

    def test_el_descuento_sale_del_lote_que_vence_primero(self):
        """FEFO: se gastan los 500 g del lote corto y 300 del largo."""
        self.crear()
        self.hornear()
        self.assertAlmostEqual(float(self.lote_compra(1).Cantidad_Actual), 0.0, places=3)
        self.assertAlmostEqual(float(self.lote_compra(2).Cantidad_Actual), 1200.0, places=3)

    def test_sin_insumos_suficientes_la_orden_no_arranca(self):
        """Y no deja el pedido a medio producir: se rechaza antes de tocar nada."""
        self.crear()
        harina = self.harina()
        harina.Stock_Actual = 100.0
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            self.mover_orden(ORDEN_EN_PROCESO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("stock insuficiente", ctx.exception.detail.lower())
        self.assertEqual(self.orden().Estado, ORDEN_PENDIENTE)
        self.assertAlmostEqual(float(self.harina().Stock_Actual), 100.0, places=3)

    def test_sin_receta_la_orden_no_arranca(self):
        """La ficha es la receta: sin ella no hay nada que descontar ni que hornear."""
        self.crear()
        orden = self.orden()
        orden.ID_Ficha = None
        self.db.query(FichaTecnica).delete()
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            self.mover_orden(ORDEN_EN_PROCESO)
        self.assertIn("ficha técnica", ctx.exception.detail.lower())

    def test_cancelar_el_pedido_en_proceso_devuelve_los_insumos_de_su_orden(self):
        """3.13 — cancelar el pedido cancela su orden en cadena y le devuelve
        los insumos (la orden ligada a un pedido no se cancela por separado)."""
        self.crear()
        self.mover_orden(ORDEN_EN_PROCESO)
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CANCELADO)
        self.db.commit()
        self.assertEqual(self.orden().Estado, ORDEN_CANCELADA)
        self.assertAlmostEqual(float(self.harina().Stock_Actual), STOCK_HARINA, places=3)
        self.assertAlmostEqual(float(self.lote_compra(1).Cantidad_Actual), 500.0, places=3)

    def test_completar_no_vuelve_a_descontar_insumos(self):
        """Los insumos salen una sola vez, al empezar a producir."""
        self.crear()
        self.hornear()
        self.assertAlmostEqual(
            float(self.harina().Stock_Actual), STOCK_HARINA - GASTO_ESPERADO, places=3
        )


# ══════════════════════════════════════════════════════════════════════════
# 3. Completar la orden repone el producto
# ══════════════════════════════════════════════════════════════════════════
class ProductoProducidoTests(FlujoProduccionE2EBase):

    def test_completar_suma_al_stock_lo_que_se_horneo(self):
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        # Confirmado (recoger en tienda): salieron las 2 que había en vitrina.
        self.assertEqual(self.stock_torta(), 0)

        self.hornear()
        self.assertEqual(self.stock_torta(), FALTANTE)

    def test_completar_crea_el_lote_del_producto_con_su_vencimiento(self):
        self.crear()
        self.hornear()
        lote = self.db.query(LoteProducto).first()
        self.assertIsNotNone(lote)
        self.assertEqual(lote.Cantidad, FALTANTE)
        self.assertEqual(lote.ID_Producto, ID_TORTA)
        self.assertEqual(lote.ID_Orden_Produccion, self.orden().ID_Orden_Produccion)
        # 5 días de vida útil según la ficha.
        self.assertEqual(
            (lote.Fecha_Vencimiento.date() - lote.Fecha_Produccion.date()).days, 5
        )

    def test_completar_deja_el_pedido_listo(self):
        """El módulo de producción es el que mueve el pedido cuando termina."""
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        self.hornear()
        self.assertEqual(self.venta().Estado, EstadoPedido.LISTO)


# ══════════════════════════════════════════════════════════════════════════
# 4. El pedido no adelanta sin su producción
# ══════════════════════════════════════════════════════════════════════════
class PedidoEsperaLaProduccionTests(FlujoProduccionE2EBase):

    def test_confirmar_deja_el_pedido_en_produccion_y_no_en_confirmado(self):
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        self.assertEqual(self.venta().Estado, EstadoPedido.PREPARANDO)

    def test_no_se_puede_marcar_listo_con_la_orden_pendiente(self):
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.LISTO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("producción", ctx.exception.detail.lower())

    def test_tampoco_con_la_orden_a_medio_hornear(self):
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        self.mover_orden(ORDEN_EN_PROCESO)

        with self.assertRaises(HTTPException):
            cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.LISTO)

    def _se_quedo_sin_ficha(self):
        """Un pedido confirmado que después pierde la forma de fabricarse.

        Pedir de entrada algo que no se fabrica y no hay en stock ya no se
        puede: el servidor lo rechaza al crearlo. Pero un pedido legal puede
        quedarse sin receta después —alguien la borra— y su orden puede
        cancelarse. Ahí el faltante se queda sin quién lo cubra.
        """
        self.crear()
        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()

        self.db.query(FichaTecnicaInsumo).delete()
        self.db.query(FichaTecnica).delete()
        producto = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TORTA
        ).first()
        producto.Requiere_Produccion = 0
        for orden in self.db.query(OrdenProduccion).all():
            orden.Estado = 5          # Cancelada
        self.db.commit()

    def test_el_pedido_sin_quien_lo_fabrique_no_pasa_a_listo(self):
        """3.10 — sin nadie que fabrique el faltante, el pedido no está listo.

        Es el control de fondo: no se da por listo lo que no existe.
        """
        self._se_quedo_sin_ficha()

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.LISTO)
        self.assertIn("falta producto", ctx.exception.detail.lower())

    def test_sin_ficha_ni_stock_el_pedido_ni_se_crea(self):
        """La puerta de antes: lo que no se fabrica y no hay, no se vende.

        Antes el pedido se creaba y quedaba trabado esperando a que alguien
        repusiera; ahora se rechaza de entrada.
        """
        self.db.query(FichaTecnicaInsumo).delete()
        self.db.query(FichaTecnica).delete()
        producto = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TORTA
        ).first()
        producto.Requiere_Produccion = 0
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            self.crear()
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("no se fabrican por encargo", ctx.exception.detail)

    def test_reponiendo_el_stock_a_mano_destraba_el_pedido(self):
        """Aunque el faltante no se fabricó, si entra mercadería el pedido pasa."""
        self._se_quedo_sin_ficha()

        producto = self.db.query(Producto).filter(Producto.ID_Producto == ID_TORTA).first()
        producto.Stock = FALTANTE
        self.db.commit()

        cambiar_estado(self.db, self.venta().ID_Venta, EstadoPedido.LISTO)
        self.db.commit()
        self.assertEqual(self.venta().Estado, EstadoPedido.LISTO)


# ══════════════════════════════════════════════════════════════════════════
# 5. El inventario cierra cuando el cliente se lleva el pedido
# ══════════════════════════════════════════════════════════════════════════
class InventarioAlEntregarTests(FlujoProduccionE2EBase):
    """El descuadre que se acaba de cerrar.

    En el pedido para recoger, el stock se descuenta AL CONFIRMAR, o sea antes
    de que la orden exista. Descontando ahí las 6 unidades, las 4 que no había
    se perdían contra el tope de 0; después la orden horneaba esas 4, las sumaba
    al stock y ya nunca salían. El cliente se llevaba 6 tortas y el inventario
    seguía mostrando las 4 que se habían horneado para él.
    """

    def recorrido_completo_en_tienda(self):
        self.crear()
        id_venta = self.venta().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        self.hornear()
        self.pagar_saldo()
        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.db.commit()

    def test_al_entregar_en_tienda_el_inventario_queda_en_cero(self):
        self.recorrido_completo_en_tienda()
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)
        self.assertEqual(self.stock_torta(), 0)

    def test_el_lote_producido_tambien_sale_del_inventario(self):
        self.recorrido_completo_en_tienda()
        self.assertEqual(self.db.query(LoteProducto).first().Cantidad, 0)

    def test_a_domicilio_el_stock_sale_entero_al_entregar(self):
        """Ahí no se descuenta nada antes, así que la línea sale completa."""
        self.crear(self.pedido(domicilio=self.domicilio()))
        id_venta = self.venta().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        # A domicilio el stock no se toca al confirmar: siguen las 2 en vitrina.
        self.assertEqual(self.stock_torta(), STOCK_TORTA)

        self.hornear()
        self.assertEqual(self.stock_torta(), STOCK_TORTA + FALTANTE)

        self.pagar_saldo()
        cambiar_estado(self.db, id_venta, EstadoPedido.EN_CAMINO)
        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.db.commit()
        self.assertEqual(self.stock_torta(), 0)

    def test_el_pedido_sin_faltante_descuenta_todo_al_confirmar(self):
        """El caso de siempre no cambia: sin preorden, se reserva la línea entera."""
        self.crear(self.pedido(
            cantidad=2,
            requiere_anticipo=False,
            anticipo_monto=None,
            anticipo_metodo_pago=None,
            anticipo_comprobante_url=None,
            anticipo_registrado=False,
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        id_venta = self.venta().ID_Venta
        venta = self.venta()
        venta.Estado_Pago = "pagado_completo"   # comprobante ya aprobado
        self.db.commit()

        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        self.assertEqual(self.stock_torta(), 0)

        cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.db.commit()
        # Al entregar no hay preorden que descontar: el stock no se mueve de más.
        self.assertEqual(self.stock_torta(), 0)

    def test_la_preorden_queda_registrada_en_la_linea_del_pedido(self):
        """De ahí sale el reparto del descuento; si se pierde, no cuadra nada."""
        self.crear()
        linea = self.db.query(VentaXProducto).first()
        self.assertEqual(linea.Cantidad, PEDIDAS)
        self.assertEqual(linea.Cantidad_Preorden, FALTANTE)


# ══════════════════════════════════════════════════════════════════════════
# 6. Anular una orden (reemplaza al borrado físico)
# ══════════════════════════════════════════════════════════════════════════
class AnularOrdenTests(FlujoProduccionE2EBase):

    def _orden_manual(self, cantidad=3):
        """Orden creada a mano (sin pedido) para la torta, que tiene ficha."""
        return crear_orden(self.db, OrdenCreate(
            ID_Producto=ID_TORTA, Cantidad=cantidad,
            Fecha_Entrega=datetime.now() + timedelta(days=2),
        ))

    def test_anular_una_orden_pendiente_la_deja_cancelada(self):
        orden = self._orden_manual()
        anular_orden(self.db, orden["ID_Orden_Produccion"])
        self.db.commit()
        fila = self.db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Orden_Produccion == orden["ID_Orden_Produccion"]
        ).first()
        self.assertEqual(fila.Estado, ORDEN_CANCELADA)   # sigue existiendo

    def test_anular_una_orden_en_proceso_no_toca_el_inventario(self):
        """No hay nada que devolver: arrancar solo había apartado.

        La reserva se suelta sola, porque se calcula sobre las órdenes en
        proceso y esta deja de serlo. Sumar de vuelta al inventario, como se
        hacía antes, ahora crearía harina de la nada.
        """
        orden = self._orden_manual()
        id_orden = orden["ID_Orden_Produccion"]
        cambiar_estado_orden(self.db, id_orden, ORDEN_EN_PROCESO)
        self.db.commit()
        self.assertAlmostEqual(float(self.harina().Stock_Actual), STOCK_HARINA, places=3)

        anular_orden(self.db, id_orden)
        self.db.commit()
        self.assertAlmostEqual(float(self.harina().Stock_Actual), STOCK_HARINA, places=3)

    def test_no_se_anula_una_orden_completada(self):
        orden = self._orden_manual()
        id_orden = orden["ID_Orden_Produccion"]
        cambiar_estado_orden(self.db, id_orden, ORDEN_EN_PROCESO)
        cambiar_estado_orden(self.db, id_orden, ORDEN_COMPLETADA)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            anular_orden(self.db, id_orden)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_no_se_anula_por_separado_la_orden_de_un_pedido(self):
        """3.12 — la orden de un pedido se anula cancelando el pedido."""
        self.crear()
        with self.assertRaises(HTTPException) as ctx:
            anular_orden(self.db, self.orden().ID_Orden_Produccion)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("pedido", ctx.exception.detail.lower())

    def test_un_producto_sin_ficha_no_deja_crear_orden_manual(self):
        """3.10 — ni manual ni automáticamente."""
        self.db.query(FichaTecnicaInsumo).delete()
        self.db.query(FichaTecnica).delete()
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self._orden_manual()
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("ficha técnica", ctx.exception.detail.lower())


# ══════════════════════════════════════════════════════════════════════════
# 7. Edición según estado (3.6) y snapshot de ficha técnica (3.8)
# ══════════════════════════════════════════════════════════════════════════
class EdicionYSnapshotTests(FlujoProduccionE2EBase):

    def _orden_manual(self, cantidad=2):
        return crear_orden(self.db, OrdenCreate(
            ID_Producto=ID_TORTA, Cantidad=cantidad,
            Fecha_Entrega=datetime.now() + timedelta(days=3),
        ))

    def _orden(self, id_orden):
        return self.db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Orden_Produccion == id_orden
        ).first()

    def test_pendiente_se_edita_en_proceso_no(self):
        orden = self._orden_manual()
        id_orden = orden["ID_Orden_Produccion"]

        editar_orden(self.db, id_orden, OrdenUpdate(Cantidad=3))
        self.db.commit()
        self.assertEqual(self._orden(id_orden).Cantidad, 3)

        cambiar_estado_orden(self.db, id_orden, ORDEN_EN_PROCESO)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            editar_orden(self.db, id_orden, OrdenUpdate(Cantidad=4))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self._orden(id_orden).Cantidad, 3)

    def test_cantidad_fuera_de_rango_se_rechaza(self):
        with self.assertRaises(Exception):   # ValidationError de pydantic
            OrdenCreate(ID_Producto=ID_TORTA, Cantidad=1000,
                        Fecha_Entrega=datetime.now() + timedelta(days=1))

    def test_editar_una_ficha_con_orden_en_proceso_crea_una_version_nueva(self):
        """3.8 — la orden en proceso conserva su receta; la ficha se versiona."""
        orden = self._orden_manual()
        id_orden = orden["ID_Orden_Produccion"]
        ficha_original = self._orden(id_orden).ID_Ficha

        cambiar_estado_orden(self.db, id_orden, ORDEN_EN_PROCESO)
        self.db.commit()

        # Cambiar la receta del producto mientras la orden está en proceso.
        gestionar_ficha(self.db, ID_TORTA, FichaTecnicaInput(
            Dias_Vida_Util=99,
            insumos=[FichaTecnicaInsumoInput(ID_Insumo=ID_HARINA, Cantidad=1, Unidad="g")],
        ))
        self.db.commit()

        # La orden en proceso sigue apuntando a la ficha con la que arrancó.
        self.assertEqual(self._orden(id_orden).ID_Ficha, ficha_original)
        # Y ahora hay 2 versiones de ficha para el producto.
        versiones = self.db.query(FichaTecnica).filter(
            FichaTecnica.ID_Producto == ID_TORTA
        ).count()
        self.assertEqual(versiones, 2)

    def test_editar_una_ficha_sin_ordenes_en_proceso_no_crea_version(self):
        self._orden_manual()   # queda Pendiente
        self.db.commit()

        gestionar_ficha(self.db, ID_TORTA, FichaTecnicaInput(Dias_Vida_Util=42))
        self.db.commit()

        versiones = self.db.query(FichaTecnica).filter(
            FichaTecnica.ID_Producto == ID_TORTA
        ).count()
        self.assertEqual(versiones, 1)   # se editó in-place


if __name__ == "__main__":
    unittest.main(verbosity=2)
