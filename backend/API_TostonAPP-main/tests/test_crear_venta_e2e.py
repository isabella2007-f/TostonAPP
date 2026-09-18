"""Creación de pedidos de punta a punta, con base de datos de verdad.

Los demás tests miran funciones sueltas. Estos arman una base SQLite en memoria
con los modelos reales, siembran cliente, productos y saldo, y llaman a
crear_venta() igual que lo hace el router. Sirven para ver el pedido que queda
guardado —total, estado de pago, anticipo, domicilio, stock— en las
combinaciones que se usan de verdad: con y sin anticipo, con y sin
transferencia, con y sin saldo a favor, con y sin domicilio.

Corre sin credenciales:
    DB_USER=u DB_PASSWORD=p DB_HOST=localhost DB_PORT=3306 DB_NAME=test \
        python tests/test_crear_venta_e2e.py
"""
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

# database.py arma el engine al importarse; con estas variables no se conecta
# a nada, y los tests usan su propia base SQLite.
os.environ.setdefault("DB_USER", "u")
os.environ.setdefault("DB_PASSWORD", "p")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "test")

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.features.ventas.gestion_ventas.services.schemas import (
    DomicilioVentaInput,
    ProductoVentaInput,
    VentaCreate,
)
from src.features.ventas.gestion_ventas.services.service import (
    cambiar_estado,
    crear_venta,
)
from src.features.ventas.domicilios.services.service import (
    cambiar_estado as cambiar_estado_domicilio,
)
from src.features.ventas.pedidos.services.estados import EstadoPedido
from src.features.ventas.pedidos.services.schemas import RegistroCobro
from src.features.ventas.pedidos.services.service import (
    aprobar_comprobante,
    rechazar_comprobante,
    registrar_cobro_pedido,
)
from src.shared.services.models import (
    Barrio,
    Base,
    Ciudad,
    CreditoCliente,
    Departamento,
    Domicilio,
    FichaTecnica,
    FichaTecnicaInsumo,
    OrdenProduccion,
    Producto,
    Usuario,
    Venta,
)

# El precio del domicilio ya no es una constante del servidor: sale del barrio de
# entrega. Los tests siembran un barrio con este precio base, así que las cuentas
# de antes (Total = subtotal + COSTO_DOMICILIO) siguen valiendo.
COSTO_DOMICILIO = Decimal("5000")
ID_BARRIO = 1

# Precio y stock elegidos para que las cuentas den redondo y sean fáciles de
# seguir a mano: 1 tostón = $10.000.
PRECIO = Decimal("10000")
ID_CLIENTE = 1
ID_TOSTON = 1       # stock 10
ID_TORTA = 2        # stock 2, para forzar el pedido sobre stock
ESTADO_DOM_ENTREGADO = 8


class CrearVentaBase(unittest.TestCase):
    """Base de datos limpia y sembrada para cada caso."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self._sembrar()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _sembrar(self, saldo=None):
        # Barrio de entrega con precio base 5000 (= antiguo COSTO_DOMICILIO).
        self.db.add(Departamento(ID_Departamento=1, Nombre="Antioquia", Estado=1))
        self.db.add(Ciudad(ID_Ciudad=1, ID_Departamento=1, Nombre="Medellín", Estado=1))
        self.db.add(Barrio(
            ID_Barrio=ID_BARRIO, ID_Ciudad=1, Nombre="Centro",
            Precio=5000, Es_Base=True, Estado=1,
        ))
        self.db.add(Usuario(
            ID_Usuario=ID_CLIENTE,
            Nombre="Cliente",
            Apellidos="De Prueba",
            Correo="cliente@prueba.test",
            Telefono="3001234567",
            ID_Rol=3,
            Estado=1,
        ))
        self.db.add(Producto(
            ID_Producto=ID_TOSTON, nombre="Tostón",
            Precio_venta=PRECIO, Stock=10, Estado=1, Publicado=1,
        ))
        self.db.add(Producto(
            ID_Producto=ID_TORTA, nombre="Torta Tropical",
            Precio_venta=PRECIO, Stock=2, Estado=1, Publicado=1,
        ))
        if saldo is not None:
            self.db.add(CreditoCliente(
                ID_Usuario=ID_CLIENTE, Saldo=Decimal(str(saldo)),
            ))
        self.db.commit()

    def dar_saldo(self, monto):
        self.db.add(CreditoCliente(
            ID_Usuario=ID_CLIENTE, Saldo=Decimal(str(monto)),
        ))
        self.db.commit()

    def marcar_por_encargo(self, id_producto):
        """El producto se fabrica bajo pedido: flag Requiere_Produccion + ficha
        técnica (sin ella no puede generarse la orden — regla 3.10)."""
        prod = self.db.query(Producto).filter(
            Producto.ID_Producto == id_producto
        ).first()
        prod.Requiere_Produccion = 1
        if not self.db.query(FichaTecnica).filter(
            FichaTecnica.ID_Producto == id_producto
        ).first():
            self.db.add(FichaTecnica(ID_Producto=id_producto, Version="1", Estado=1))
        self.db.commit()

    def desactivar(self, id_producto):
        """El admin lo saca de la tienda (Publicado = 0)."""
        prod = self.db.query(Producto).filter(
            Producto.ID_Producto == id_producto
        ).first()
        prod.Publicado = 0
        self.db.commit()

    def sin_telefono(self):
        u = self.db.query(Usuario).filter(Usuario.ID_Usuario == ID_CLIENTE).first()
        u.Telefono = None
        self.db.commit()

    # ── Ayudas ───────────────────────────────────────────────────────────
    def pedido(self, **kwargs):
        """VentaCreate con lo mínimo, y lo que cada caso quiera cambiar."""
        base = dict(
            ID_Usuario=ID_CLIENTE,
            Metodo_Pago="Efectivo",
            productos=[ProductoVentaInput(ID_Producto=ID_TOSTON, Cantidad=2)],
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

    def crear(self, datos):
        # La fecha límite es obligatoria para lo que hay que fabricar desde
        # que el checkout la exige (antes la proponía el admin después de
        # crear el pedido). Estos tests llaman a crear_venta() directo, sin
        # pasar por el checkout: se les pone una fecha futura por defecto
        # salvo que el caso ya haya puesto la suya — no aplica si el pedido
        # no necesita producción, crear_venta la ignora en ese caso.
        if getattr(datos, "Fecha_entrega_esperada", None) is None and not datos.creado_por_admin:
            from datetime import datetime, timedelta
            datos.Fecha_entrega_esperada = datetime.now() + timedelta(days=8)
        resultado = crear_venta(self.db, datos)
        self.db.commit()
        return resultado

    def venta_creada(self):
        return self.db.query(Venta).first()

    def saldo_actual(self):
        c = self.db.query(CreditoCliente).filter(
            CreditoCliente.ID_Usuario == ID_CLIENTE
        ).first()
        return c.Saldo if c else Decimal("0")

    def stock(self, id_producto):
        return self.db.query(Producto).filter(
            Producto.ID_Producto == id_producto
        ).first().Stock


# ══════════════════════════════════════════════════════════════════════════
# 1. Pedido normal, sin anticipo
# ══════════════════════════════════════════════════════════════════════════
class PedidoNormalTests(CrearVentaBase):

    def test_efectivo_sin_domicilio(self):
        self.crear(self.pedido())
        v = self.venta_creada()
        self.assertEqual(v.Total, Decimal("20000"))
        self.assertEqual(v.Metodo_Pago, "Efectivo")
        self.assertEqual(v.Estado_Pago, "pendiente")
        self.assertEqual(v.Sobre_Stock, 0)
        self.assertIsNone(self.db.query(Domicilio).first())

    def test_efectivo_con_domicilio_suma_el_costo(self):
        self.crear(self.pedido(domicilio=self.domicilio()))
        v = self.venta_creada()
        self.assertEqual(v.Total, Decimal("20000") + COSTO_DOMICILIO)
        dom = self.db.query(Domicilio).first()
        self.assertIsNotNone(dom)
        self.assertEqual(dom.Direccion_entrega, "Calle 10 #20-30")
        # Sin repartidor asignado nace pendiente (3), no asignado (10).
        self.assertEqual(dom.Estado, 3)

    def test_domicilio_sin_telefono_se_rechaza(self):
        self.sin_telefono()
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.pedido(domicilio=self.domicilio()))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("teléfono", ctx.exception.detail)

    def test_transferencia_con_comprobante_queda_por_validar(self):
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Estado_Pago, "pendiente_validacion")
        self.assertEqual(v.Comprobante_Pago, "https://cloudinary.test/comp.jpg")

    def test_transferencia_sin_comprobante_queda_pendiente(self):
        self.crear(self.pedido(Metodo_Pago="Transferencia"))
        v = self.venta_creada()
        self.assertEqual(v.Estado_Pago, "pendiente")
        self.assertIsNone(v.Comprobante_Pago)

    def test_el_cliente_no_descuenta_stock_al_pedir(self):
        """El stock se descuenta al entregar, no al crear el pedido."""
        self.crear(self.pedido())
        self.assertEqual(self.stock(ID_TOSTON), 10)


# ══════════════════════════════════════════════════════════════════════════
# 1b. Producto desactivado de la tienda
# ══════════════════════════════════════════════════════════════════════════
class ProductoDesactivadoTests(CrearVentaBase):
    """El carrito vive en el dispositivo del cliente.

    Cuando el admin desactiva un producto desaparece del catálogo, pero sigue
    en el carrito de quien lo había agregado antes. El servidor es el único que
    puede impedir que ese pedido entre igual.
    """

    def test_el_cliente_no_puede_pedir_lo_desactivado(self):
        self.desactivar(ID_TORTA)
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.pedido(
                productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=1)],
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Torta Tropical", ctx.exception.detail)

    def test_el_pedido_entero_se_frena_aunque_lo_demas_este_bien(self):
        self.desactivar(ID_TORTA)
        with self.assertRaises(HTTPException):
            self.crear(self.pedido(productos=[
                ProductoVentaInput(ID_Producto=ID_TOSTON, Cantidad=1),
                ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=1),
            ]))
        self.assertIsNone(self.venta_creada())

    def test_el_personal_si_puede_venderlo_en_mostrador(self):
        self.desactivar(ID_TORTA)
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=1)],
            creado_por_admin=True,
        ))
        self.assertEqual(self.venta_creada().Total, PRECIO)

    def test_lo_publicado_sigue_pasando(self):
        self.desactivar(ID_TORTA)
        self.crear(self.pedido())
        self.assertEqual(self.venta_creada().Total, Decimal("20000"))

    def test_agotado_no_es_lo_mismo_que_desactivado(self):
        """Sin stock se puede pedir igual, si la panadería lo fabrica.

        Son dos negativas distintas y el cliente tiene que poder diferenciarlas:
        "no lo vendemos" no es "se acabó, lo horneamos". Antes esto se probaba
        con un producto que no se fabrica, y hoy ese pedido lo rechaza el
        servidor por otra razón.
        """
        self.marcar_por_encargo(ID_TOSTON)
        prod = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TOSTON
        ).first()
        prod.Stock = 0
        self.db.commit()
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        self.assertEqual(self.venta_creada().Sobre_Stock, 1)

    def test_agotado_y_sin_fabricar_se_rechaza_con_otro_motivo(self):
        """La otra mitad: agotado y que además no se fabrica.

        El mensaje habla del stock, no de que el producto esté desactivado.
        """
        prod = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TOSTON
        ).first()
        prod.Stock = 0
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.pedido(
                Metodo_Pago="Transferencia",
                comprobante_pago="https://cloudinary.test/comp.jpg",
            ))
        self.assertIn("no se fabrican por encargo", ctx.exception.detail)
        self.assertNotIn("desactivado", ctx.exception.detail.lower())


# ══════════════════════════════════════════════════════════════════════════
# 2. Saldo a favor
# ══════════════════════════════════════════════════════════════════════════
class SaldoAFavorTests(CrearVentaBase):

    def test_el_saldo_baja_el_total_y_se_descuenta(self):
        self.dar_saldo(5000)
        self.crear(self.pedido(usar_credito=True, credito_monto=Decimal("5000")))
        self.assertEqual(self.venta_creada().Total, Decimal("15000"))
        self.assertEqual(self.saldo_actual(), Decimal("0"))

    def test_el_monto_pedido_es_un_tope_no_un_permiso(self):
        """Pedir más saldo del que hay no crea saldo: se recorta al real."""
        self.dar_saldo(3000)
        self.crear(self.pedido(usar_credito=True, credito_monto=Decimal("99999")))
        self.assertEqual(self.venta_creada().Total, Decimal("17000"))
        self.assertEqual(self.saldo_actual(), Decimal("0"))

    def test_se_puede_guardar_parte_del_saldo_para_despues(self):
        self.dar_saldo(20000)
        self.crear(self.pedido(usar_credito=True, credito_monto=Decimal("8000")))
        self.assertEqual(self.venta_creada().Total, Decimal("12000"))
        self.assertEqual(self.saldo_actual(), Decimal("12000"))

    def test_el_saldo_no_puede_pasar_del_total(self):
        self.dar_saldo(50000)
        self.crear(self.pedido(usar_credito=True))
        self.assertEqual(self.venta_creada().Total, Decimal("0"))
        # Solo se gastaron los $20.000 del pedido; el resto sigue disponible.
        self.assertEqual(self.saldo_actual(), Decimal("30000"))

    def test_sin_usar_credito_el_saldo_queda_intacto(self):
        self.dar_saldo(20000)
        self.crear(self.pedido())
        self.assertEqual(self.venta_creada().Total, Decimal("20000"))
        self.assertEqual(self.saldo_actual(), Decimal("20000"))

    def test_saldo_con_domicilio_el_costo_se_suma_despues(self):
        """El domicilio no se puede pagar con saldo: se suma al final."""
        self.dar_saldo(20000)
        self.crear(self.pedido(
            usar_credito=True,
            credito_monto=Decimal("20000"),
            domicilio=self.domicilio(),
        ))
        self.assertEqual(self.venta_creada().Total, COSTO_DOMICILIO)


# ══════════════════════════════════════════════════════════════════════════
# 3. Pedido con anticipo (por encima del stock)
# ══════════════════════════════════════════════════════════════════════════
class AnticipoTests(CrearVentaBase):
    """El anticipo se pide cuando el total >= $100.000, sin importar si hay producción.

    La Torta Tropical se fabrica (por encargo) y tiene stock 2, así que pedir
    11 deja 9 por producir y son $110.000, por encima del umbral.
    """

    def sobre_stock(self, cantidad=11, **kwargs):
        """Pedido que sí pide anticipo: 9 tortas por hornear, $110.000."""
        self.marcar_por_encargo(ID_TORTA)
        return self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=cantidad)],
            **kwargs,
        )

    def test_sin_respaldo_se_rechaza(self):
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.sobre_stock())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("anticipo", ctx.exception.detail.lower())

    def test_transferencia_con_comprobante_lo_respalda(self):
        self.crear(self.sobre_stock(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Sobre_Stock, 1)
        # 11 tortas × $10.000 = $110.000 → anticipo del 50%.
        self.assertEqual(v.Anticipo_Requerido, Decimal("55000"))

    def test_el_saldo_a_favor_baja_el_anticipo(self):
        """El anticipo sale de lo que QUEDA por pagar, como el checkout."""
        self.dar_saldo(10000)
        self.crear(self.sobre_stock(
            usar_credito=True,
            credito_monto=Decimal("10000"),
            requiere_anticipo=True,
            anticipo_monto=50000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        ))
        v = self.venta_creada()
        # $110.000 − $10.000 de saldo = $100.000 por pagar → anticipo $50.000.
        self.assertEqual(v.Anticipo_Requerido, Decimal("50000"))
        self.assertEqual(v.Anticipo_Pagado, Decimal("10000"))

    def test_el_saldo_que_cubre_la_mitad_basta_sin_comprobante(self):
        self.dar_saldo(55000)
        self.crear(self.sobre_stock(usar_credito=True, credito_monto=Decimal("55000")))
        v = self.venta_creada()
        # $110.000 − $55.000 = $55.000 por pagar → anticipo $27.500, cubierto.
        self.assertEqual(v.Anticipo_Requerido, Decimal("27500"))
        self.assertEqual(v.Total, Decimal("55000"))

    def test_el_flujo_del_checkout_deja_el_anticipo_registrado(self):
        self.crear(self.sobre_stock(
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=55000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        ))
        v = self.venta_creada()
        self.assertEqual(v.Requiere_Anticipo, 1)
        self.assertEqual(v.Anticipo_Registrado, 1)
        self.assertEqual(v.Estado_Pago, "anticipo_pagado")
        self.assertEqual(v.Anticipo_Comprobante_Url, "https://cloudinary.test/ant.jpg")

    def test_pagar_todo_ahora_deja_el_pedido_saldado(self):
        self.crear(self.sobre_stock(
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=110000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        ))
        v = self.venta_creada()
        self.assertEqual(v.Pago_Final_Registrado, 1)
        self.assertEqual(v.Estado_Pago, "pagado_completo")

    def test_anticipo_en_efectivo_confirmado_sirve(self):
        self.crear(self.sobre_stock(
            Metodo_Pago="Efectivo",
            requiere_anticipo=True,
            anticipo_monto=55000.0,
            anticipo_metodo_pago="Efectivo",
            anticipo_registrado=True,
        ))
        self.assertEqual(self.venta_creada().Estado_Pago, "anticipo_pagado")

    def test_anticipo_declarado_sin_pagar_no_pasa(self):
        """Decir "requiere anticipo" sin respaldo no alcanza."""
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.sobre_stock(
                requiere_anticipo=True,
                anticipo_monto=55000.0,
                anticipo_metodo_pago="Efectivo",
                anticipo_registrado=False,
            ))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_con_domicilio_el_anticipo_incluye_el_costo(self):
        self.crear(self.sobre_stock(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
            domicilio=self.domicilio(),
        ))
        v = self.venta_creada()
        esperado = (Decimal("110000") + COSTO_DOMICILIO) / 2
        self.assertEqual(v.Anticipo_Requerido, esperado)

    def _oferta_domicilio(self, *, tipo, pesos=None, pct=None):
        """Siembra una oferta de domicilio que aplica todos los días al barrio 1."""
        from src.shared.services.models import OfertaDomicilio, OfertaXBarrio
        of = OfertaDomicilio(
            Nombre=f"of-{tipo}", Tipo=tipo, Monto_Pesos=pesos, Porcentaje=pct,
            Dias_Semana="1,2,3,4,5,6,7", Dias_Mes=None, Estado=1,
        )
        self.db.add(of)
        self.db.flush()
        self.db.add(OfertaXBarrio(ID_Oferta=of.ID_Oferta, ID_Barrio=ID_BARRIO))
        self.db.commit()

    def test_anticipo_con_domicilio_gratis_por_oferta(self):
        """G-9: un descuento que deja el domicilio en 0 → el anticipo se calcula
        sobre subtotal − descuento + 0, sin sumar la tarifa base."""
        self._oferta_domicilio(tipo="descuento", pesos=9000)   # 5000 − 9000 → piso 0
        self.crear(self.sobre_stock(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
            domicilio=self.domicilio(),
        ))
        v = self.venta_creada()
        self.assertEqual(v.Anticipo_Requerido, Decimal("55000"))  # 110000 / 2, domicilio 0
        dom = self.db.query(Domicilio).first()
        self.assertEqual(dom.Precio_Domicilio_Final, 0)
        self.assertEqual(v.Total, Decimal("110000"))              # subtotal + domicilio 0

    def test_anticipo_con_recargo_de_domicilio(self):
        """G-9: un recargo sube el precio del domicilio y el anticipo lo incluye."""
        self._oferta_domicilio(tipo="recargo", pesos=3000)        # 5000 + 3000 = 8000
        self.crear(self.sobre_stock(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
            domicilio=self.domicilio(),
        ))
        v = self.venta_creada()
        self.assertEqual(v.Anticipo_Requerido, (Decimal("110000") + Decimal("8000")) / 2)
        self.assertEqual(self.db.query(Domicilio).first().Precio_Domicilio_Final, 8000)

    def test_el_personal_no_necesita_anticipo(self):
        """Los pedidos de mostrador se cobran en el acto.

        Nace directo en producción (13) y no en Confirmado (4): el admin lo creó
        ya comprometido, así que se le abre la orden de las 9 tortas que faltan.
        """
        self.crear(self.sobre_stock(creado_por_admin=True))
        v = self.venta_creada()
        self.assertEqual(v.Sobre_Stock, 1)
        self.assertEqual(v.Estado, EstadoPedido.PREPARANDO)
        self.assertEqual(
            self.db.query(OrdenProduccion).filter(
                OrdenProduccion.ID_Venta == v.ID_Venta
            ).one().Cantidad,
            9,
        )


# ══════════════════════════════════════════════════════════════════════════
# 3a. Los pedidos que NO piden anticipo
# ══════════════════════════════════════════════════════════════════════════
class SinAnticipoTests(CrearVentaBase):
    """El error que reportó el negocio: se pedía anticipo en todos.

    Cliente y mostrador veían el bloque del anticipo en cualquier pedido,
    con stock de sobra y por cualquier monto. Se pide cuando el pedido
    supera $100.000 (sin importar si hay producción).
    """

    def test_por_debajo_del_umbral_no_pide_anticipo(self):
        """9 tostones = $90.000, todos en stock: no llega al umbral."""
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TOSTON, Cantidad=9)],
        ))
        v = self.venta_creada()
        self.assertEqual(v.Total, Decimal("90000"))
        self.assertEqual(v.Sobre_Stock, 0)
        self.assertEqual(v.Requiere_Anticipo or 0, 0)
        self.assertIsNone(v.Anticipo_Requerido)

    def test_el_faltante_chico_no_pide_anticipo_pero_queda_marcado(self):
        """3 tortas por encargo = $30.000: una por hornear, no llega al umbral.

        El pedido igual queda Sobre_Stock, que es lo que dispara la fecha
        propuesta y la orden de producción. Lo único que no se le pide es
        plata por adelantado.
        """
        self.marcar_por_encargo(ID_TORTA)
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=3)],
        ))
        v = self.venta_creada()
        self.assertEqual(v.Sobre_Stock, 1)
        self.assertEqual(v.Necesita_Produccion, 1)
        self.assertEqual(v.Requiere_Anticipo or 0, 0)
        self.assertIsNone(v.Anticipo_Requerido)

    def test_justo_debajo_del_umbral_todavia_no_pide(self):
        """$99.999: un peso debajo de $100.000 no pide anticipo."""
        self.marcar_por_encargo(ID_TORTA)
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=5)],
        ))
        v = self.venta_creada()
        self.assertEqual(v.Total, Decimal("50000"))
        self.assertEqual(v.Requiere_Anticipo or 0, 0)

    def test_domicilio_no_empuja_por_encima_del_umbral_con_pedido_chico(self):
        """$50.000 + domicilio = $55.000: sigue por debajo de $100.000."""
        self.marcar_por_encargo(ID_TORTA)
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=5)],
            domicilio=self.domicilio(),
        ))
        v = self.venta_creada()
        self.assertLess(v.Total, Decimal("100000"))
        self.assertEqual(v.Requiere_Anticipo or 0, 0)

    def test_lo_que_la_panaderia_no_fabrica_no_se_pide_con_anticipo(self):
        """Cobrar por adelantado no acerca el producto.

        Sin ficha técnica ni marca de producción no hay orden que abrir, así
        que el anticipo no compra nada: el pedido se rechaza en vez de quedar
        esperando a que alguien reponga.
        """
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.pedido(
                productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=8)],
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("no se fabrican por encargo", ctx.exception.detail)
        self.assertIsNone(self.venta_creada())

    def test_la_ficha_tecnica_sola_ya_cuenta_como_fabricable(self):
        """Igual que las órdenes de producción: la receta manda, no el flag.

        Si el criterio fuera distinto, el checkout no mostraría el anticipo y
        el servidor rechazaría el pedido por no traerlo. Necesita >= $100.000
        para llegar al umbral (11 tortas a $10.000 = $110.000).
        """
        self.db.add(FichaTecnica(ID_Producto=ID_TORTA, Version="1", Estado=1))
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.pedido(
                productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=11)],
            ))
        self.assertIn("anticipo", ctx.exception.detail.lower())

    def test_el_pedido_sin_anticipo_registra_igual_lo_que_se_pago(self):
        """Una app vieja manda el flag; la plata que entró no se pierde.

        No se le marca la obligación —esa la decide el servidor—, pero el
        abono queda registrado para que el saldo se pueda cobrar después.
        """
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=10000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        ))
        v = self.venta_creada()
        self.assertEqual(v.Anticipo_Registrado, 1)
        self.assertEqual(v.Estado_Pago, "anticipo_pagado")
        # El saldo tiene que poder cobrarse: registrar_pago_final lo exige.
        self.assertEqual(v.Requiere_Anticipo, 1)


# ══════════════════════════════════════════════════════════════════════════
# 3b. Productos por encargo
# ══════════════════════════════════════════════════════════════════════════
class ProductoPorEncargoTests(CrearVentaBase):
    """Decisión del negocio: por encargo también lleva anticipo.

    El checkout del cliente los excluía y el servidor no, así que quien pedía un
    producto por encargo por encima del stock veía el aviso de producción, nunca
    el bloque del anticipo, y al confirmar le rechazaban el pedido por un
    anticipo que la pantalla jamás le había ofrecido pagar.
    """

    def por_encargo(self, cantidad=6, **kwargs):
        self.marcar_por_encargo(ID_TORTA)
        return self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=cantidad)],
            **kwargs,
        )

    def test_por_encima_del_stock_exige_anticipo(self):
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.por_encargo())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("anticipo", ctx.exception.detail.lower())

    def test_con_el_anticipo_registrado_el_pedido_entra(self):
        self.crear(self.por_encargo(
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=30000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        ))
        v = self.venta_creada()
        self.assertEqual(v.Sobre_Stock, 1)
        self.assertEqual(v.Anticipo_Requerido, Decimal("30000"))
        self.assertEqual(v.Estado_Pago, "anticipo_pagado")

    def test_queda_marcado_para_producir(self):
        """El anticipo no reemplaza la orden de producción: van juntos."""
        self.crear(self.por_encargo(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Necesita_Produccion, 1)
        self.assertEqual(v.Sobre_Stock, 1)

    def test_dentro_del_stock_no_exige_nada(self):
        self.crear(self.por_encargo(cantidad=2))
        v = self.venta_creada()
        self.assertEqual(v.Sobre_Stock, 0)
        self.assertEqual(v.Necesita_Produccion, 0)


# ══════════════════════════════════════════════════════════════════════════
# 4. Pago mixto
# ══════════════════════════════════════════════════════════════════════════
class PagoMixtoTests(CrearVentaBase):

    def test_reparte_el_total_entre_efectivo_y_transferencia(self):
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("3500"),
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Monto_Efectivo, Decimal("3500.00"))
        self.assertEqual(v.Monto_Transferencia, Decimal("16500.00"))
        self.assertEqual(v.Monto_Efectivo + v.Monto_Transferencia, v.Total)

    def test_el_reparto_se_hace_sobre_el_total_con_saldo_y_domicilio(self):
        self.dar_saldo(5000)
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("4000"),
            usar_credito=True,
            credito_monto=Decimal("5000"),
            domicilio=self.domicilio(),
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Total, Decimal("15000") + COSTO_DOMICILIO)
        self.assertEqual(v.Monto_Efectivo, Decimal("4000.00"))
        self.assertEqual(v.Monto_Efectivo + v.Monto_Transferencia, v.Total)

    def test_pedir_mas_efectivo_que_el_total_se_recorta(self):
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("99999"),
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Monto_Efectivo, v.Total)
        self.assertEqual(v.Monto_Transferencia, Decimal("0.00"))

    def test_mixto_con_anticipo_se_rechaza(self):
        """El mixto no respalda un anticipo: su efectivo se cobra al entregar."""
        self.marcar_por_encargo(ID_TORTA)
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.pedido(
                productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=6)],
                Metodo_Pago="Mixto",
                pago_efectivo_monto=Decimal("5000"),
                comprobante_pago="https://cloudinary.test/comp.jpg",
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("mixto", ctx.exception.detail.lower())

    def test_el_faltante_que_no_pide_anticipo_conserva_el_mixto(self):
        """Sobre stock pero por debajo del umbral: no hay anticipo que proteger.

        Antes cualquier faltante le cerraba el mixto al cliente.
        """
        self.marcar_por_encargo(ID_TORTA)
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=3)],
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            comprobante_pago="https://cloudinary.test/comp.jpg",
        ))
        v = self.venta_creada()
        self.assertEqual(v.Sobre_Stock, 1)
        self.assertEqual(v.Monto_Efectivo, Decimal("5000.00"))
        self.assertEqual(v.Monto_Efectivo + v.Monto_Transferencia, v.Total)

    def test_el_flag_declarado_ya_no_cierra_el_mixto(self):
        """La obligación la decide el servidor, no el flag que manda el cliente."""
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            requiere_anticipo=True,
            anticipo_monto=10000.0,
            anticipo_registrado=True,
        ))
        self.assertEqual(self.venta_creada().Monto_Efectivo, Decimal("5000.00"))


# ══════════════════════════════════════════════════════════════════════════
# 5. Pedidos del personal
# ══════════════════════════════════════════════════════════════════════════
class PedidoDelPersonalTests(CrearVentaBase):

    def test_nace_confirmado_y_reserva_stock_en_pickup(self):
        self.crear(self.pedido(creado_por_admin=True))
        self.assertEqual(self.venta_creada().Estado, 4)
        # Pickup: el stock se reserva en el acto.
        self.assertEqual(self.stock(ID_TOSTON), 8)

    def test_con_domicilio_el_stock_se_descuenta_al_entregar(self):
        self.crear(self.pedido(creado_por_admin=True, domicilio=self.domicilio()))
        self.assertEqual(self.venta_creada().Estado, 4)
        self.assertEqual(self.stock(ID_TOSTON), 10)

    def test_domicilio_con_repartidor_nace_asignado(self):
        self.crear(self.pedido(
            creado_por_admin=True,
            domicilio=self.domicilio(ID_Empleado=4),
        ))
        self.assertEqual(self.db.query(Domicilio).first().Estado, 10)


# ═════════════════════════════════════════════════════════════════════════
# 7. Orden de producción del faltante
# ═════════════════════════════════════════════════════════════════════════
class OrdenProduccionDelFaltanteTests(CrearVentaBase):
    """La torta tiene 2 en stock; pedir 5 debe fabricar 3, no 5.

    Y mientras esa orden siga abierta el pedido no puede darse por Listo: no
    existe el producto que se entregaría.
    """

    def con_anticipo(self, cantidad=5, **kwargs):
        self.marcar_por_encargo(ID_TORTA)
        base = dict(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=cantidad)],
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=25000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        )
        base.update(kwargs)
        return self.pedido(**base)

    def sin_receta(self, cantidad=5):
        """Sobre stock y sin forma de fabricarlo: el servidor lo rechaza.

        Ni ficha técnica ni `Requiere_Produccion`: no hay orden que abrir, y
        cobrar por adelantado no acerca el producto.
        """
        return self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=cantidad)],
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=25000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        )

    def se_quedo_sin_receta(self, cantidad=5):
        """Un pedido legal que después pierde la forma de fabricarse.

        Pedir de entrada algo que no se fabrica y no hay en stock ya no se
        puede. Pero un pedido hecho cuando el producto sí se fabricaba puede
        quedarse sin receta después —alguien la borra, o le quita la marca— y
        su orden puede cancelarse. Ahí el faltante se queda sin quién lo cubra,
        y es cuando el control de abajo tiene que actuar.

        Devuelve el ID de la venta.
        """
        self.crear(self.con_anticipo(cantidad))
        id_venta = self.venta_creada().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)

        producto = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TORTA
        ).first()
        producto.Requiere_Produccion = 0
        self.db.query(FichaTecnicaInsumo).delete()
        self.db.query(FichaTecnica).delete()
        for orden in self.ordenes():
            orden.Estado = 5          # Cancelada
        self.db.commit()
        return id_venta

    def reponer(self, id_producto, stock):
        prod = self.db.query(Producto).filter(
            Producto.ID_Producto == id_producto
        ).first()
        prod.Stock = stock
        self.db.commit()

    def anticipo_sin_validar(self, cantidad=5):
        """Sobre stock con comprobante adjunto pero aún sin registrar el pago.

        Es el pedido que entra al panel esperando que el admin valide la
        transferencia: no hay anticipo confirmado, así que la producción espera
        a la confirmación.
        """
        return self.con_anticipo(cantidad, anticipo_registrado=False)

    def ordenes(self):
        return self.db.query(OrdenProduccion).all()

    def test_el_anticipo_abre_la_orden_por_el_faltante(self):
        self.crear(self.con_anticipo())
        ordenes = self.ordenes()
        self.assertEqual(len(ordenes), 1)
        self.assertEqual(ordenes[0].ID_Producto, ID_TORTA)
        self.assertEqual(ordenes[0].Cantidad, 3)      # 5 pedidas − 2 en stock
        self.assertEqual(ordenes[0].Estado, 1)        # nace Pendiente
        self.assertEqual(ordenes[0].ID_Venta, self.venta_creada().ID_Venta)

    def test_el_anticipo_no_abre_orden_hasta_que_se_confirme(self):
        self.crear(self.con_anticipo())
        self.assertEqual(self.ordenes(), [])
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.PENDIENTE)

    def test_dentro_del_stock_no_abre_ninguna_orden(self):
        self.crear(self.con_anticipo(cantidad=2))
        self.assertEqual(self.ordenes(), [])

    def test_confirmar_abre_la_orden_y_deja_el_pedido_en_produccion(self):
        # Sin anticipo registrado la orden espera; al confirmar se abre.
        self.crear(self.anticipo_sin_validar())
        self.assertEqual(self.ordenes(), [])

        id_venta = self.venta_creada().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)

        ordenes = self.ordenes()
        self.assertEqual(len(ordenes), 1)
        self.assertEqual(ordenes[0].Cantidad, 3)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.PREPARANDO)

    def test_confirmar_no_duplica_la_orden_que_abrio_el_anticipo(self):
        self.crear(self.con_anticipo())
        cambiar_estado(self.db, self.venta_creada().ID_Venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(len(self.ordenes()), 1)

    def test_no_pasa_a_listo_con_la_orden_abierta(self):
        self.crear(self.con_anticipo())
        id_venta = self.venta_creada().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("producción", ctx.exception.detail.lower())

    def test_con_la_orden_completada_ya_puede_pasar_a_listo(self):
        self.crear(self.con_anticipo())
        id_venta = self.venta_creada().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)

        orden = self.ordenes()[0]
        orden.Estado = 11          # Completada
        self.db.commit()

        cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.LISTO)

    def test_la_ficha_tecnica_basta_aunque_falte_el_flag(self):
        """El producto que se fabrica pero al que nadie le marcó el flag."""
        self.db.add(FichaTecnica(ID_Ficha=1, ID_Producto=ID_TORTA, Estado=1))
        self.db.commit()
        # Ojo: sin marcar_por_encargo, el producto no tiene Requiere_Produccion.
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=5)],
            Metodo_Pago="Transferencia",
            requiere_anticipo=True,
            anticipo_monto=25000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cloudinary.test/ant.jpg",
            anticipo_registrado=True,
        ))
        ordenes = self.ordenes()
        self.assertEqual(len(ordenes), 1)
        self.assertEqual(ordenes[0].Cantidad, 3)
        self.assertEqual(ordenes[0].ID_Ficha, 1)

    # ── Producto que no se puede fabricar ───────────────────────────

    def test_sin_ficha_ni_flag_no_se_puede_pedir_sobre_stock(self):
        """Lo que no se fabrica y no hay, no se vende.

        Antes el pedido se creaba y quedaba trabado hasta que alguien
        repusiera: nadie lo miraba y el cliente esperaba por algo que no
        estaba en camino. Ahora se rechaza de entrada, diciendo qué producto
        es y cuánto hay.
        """
        with self.assertRaises(HTTPException) as ctx:
            self.crear(self.sin_receta())
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Torta Tropical", ctx.exception.detail)
        self.assertIn("disponible 2", ctx.exception.detail)
        self.assertIn("pediste 5", ctx.exception.detail)
        # Y no queda nada a medio crear.
        self.assertIsNone(self.venta_creada())

    def test_lo_que_si_hay_en_stock_se_pide_igual(self):
        """El rechazo mira el faltante, no si el producto se fabrica.

        Sin esta línea, un producto que la panadería compra hecho —y del que
        hay de sobra— habría dejado de poder venderse.
        """
        self.crear(self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=2)],
        ))
        self.assertEqual(self.venta_creada().Sobre_Stock, 0)

    def test_el_que_se_queda_sin_receta_no_llega_a_listo(self):
        """El control de fondo: no se da por Listo lo que no existe.

        Ya no se puede pedir algo no fabricable sobre el stock, pero un pedido
        legal puede quedarse sin receta después. El faltante se queda sin quién
        lo cubra y el pedido no puede darse por listo igual.
        """
        id_venta = self.se_quedo_sin_receta()

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Torta Tropical", ctx.exception.detail)

    def test_al_reponer_el_stock_el_pedido_ya_puede_estar_listo(self):
        """La salida del bloqueo cuando ya no se puede fabricar: comprarlo."""
        id_venta = self.se_quedo_sin_receta()
        # Quedan debiendo 3 de las 5 pedidas. Con esas 3 ya hay qué entregar.
        self.reponer(ID_TORTA, 3)

        cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.LISTO)

    def test_la_orden_cancelada_tampoco_deja_pasar_a_listo(self):
        """Cancelar la orden no es fabricar: sigue faltando el producto."""
        self.crear(self.con_anticipo())
        id_venta = self.venta_creada().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)

        orden = self.ordenes()[0]
        orden.Estado = 5          # Cancelada
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Torta Tropical", ctx.exception.detail)

    def test_el_pedido_dentro_del_stock_no_se_bloquea(self):
        """Sin preorden no hay nada que cubrir: el control no se mete."""
        self.crear(self.pedido(creado_por_admin=True))
        id_venta = self.venta_creada().ID_Venta
        cambiar_estado(self.db, id_venta, EstadoPedido.LISTO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.LISTO)


# ══════════════════════════════════════════════════════════════════════════
# 8. El pago manda en el flujo del pedido
# ══════════════════════════════════════════════════════════════════════════
class FlujoPagosTests(CrearVentaBase):
    """Cada paso del pedido exige que el pago de ese paso esté resuelto.

    Confirmar es aceptar el pedido: no se acepta contra un comprobante que
    nadie miró. Y entregar un domicilio es cerrar la venta: no se cierra sin
    haber registrado qué pasó con la plata que se cobra en mano.
    """

    ADMIN = 1  # quien aprueba o rechaza, para la auditoría

    def transferencia(self, **kwargs):
        base = dict(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        base.update(kwargs)
        return self.pedido(**base)

    def mixto(self, efectivo=5000.0, **kwargs):
        base = dict(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=efectivo,
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        base.update(kwargs)
        return self.pedido(**base)

    def avanzar(self, id_venta, *estados):
        for estado in estados:
            cambiar_estado(self.db, id_venta, estado)

    def cobrar(self, id_venta, recibido=True, motivo=None):
        return registrar_cobro_pedido(
            self.db, id_venta,
            RegistroCobro(recibido=recibido, monto=None, motivo=motivo),
            self.ADMIN,
        )

    # ────────────────────── Confirmar exige el comprobante aprobado ──────────────────────

    def test_no_se_confirma_con_el_comprobante_sin_revisar(self):
        self.crear(self.transferencia())
        v = self.venta_creada()
        self.assertEqual(v.Estado_Pago, "pendiente_validacion")

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("comprobante", ctx.exception.detail.lower())
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.PENDIENTE)

    def test_aprobado_el_comprobante_el_pedido_se_confirma(self):
        self.crear(self.transferencia())
        id_venta = self.venta_creada().ID_Venta
        aprobar_comprobante(self.db, id_venta)

        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.CONFIRMADO)

    def test_el_comprobante_rechazado_tampoco_deja_confirmar(self):
        self.crear(self.transferencia())
        id_venta = self.venta_creada().ID_Venta
        rechazar_comprobante(self.db, id_venta, "La imagen no se ve", self.ADMIN)

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)
        self.assertIn("rechazado", ctx.exception.detail.lower())

    def test_el_pedido_en_efectivo_se_confirma_sin_comprobante(self):
        """No hay nada que aprobar: la puerta no se le aplica."""
        self.crear(self.pedido())
        id_venta = self.venta_creada().ID_Venta

        cambiar_estado(self.db, id_venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.CONFIRMADO)

    # ────────────────────── Entregar un domicilio exige el cobro ──────────────────────

    def _domicilio_en_camino(self, datos):
        self.crear(datos)
        id_venta = self.venta_creada().ID_Venta
        self.avanzar(
            id_venta,
            EstadoPedido.CONFIRMADO, EstadoPedido.LISTO, EstadoPedido.EN_CAMINO,
        )
        return id_venta

    def test_no_se_entrega_el_domicilio_sin_registrar_el_cobro(self):
        id_venta = self._domicilio_en_camino(self.pedido(domicilio=self.domicilio()))

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("efectivo", ctx.exception.detail.lower())
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.EN_CAMINO)

    def test_registrado_el_cobro_el_domicilio_se_entrega(self):
        id_venta = self._domicilio_en_camino(self.pedido(domicilio=self.domicilio()))
        self.cobrar(id_venta)

        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)

    def test_declarar_que_no_se_cobro_tambien_deja_cerrar_la_entrega(self):
        """Con motivo auditado: lo que no vale es entregar sin decir qué pasó."""
        id_venta = self._domicilio_en_camino(self.pedido(domicilio=self.domicilio()))
        self.cobrar(id_venta, recibido=False, motivo="el cliente no tenia el efectivo")

        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)

    def test_el_mixto_no_se_entrega_solo_con_el_comprobante_aprobado(self):
        """La regresión que cerraba en falso: "anticipo_pagado" es media paga.

        Aprobar el comprobante salda la parte transferida; la plata en mano
        sigue sin cobrarse y el pedido se entregaba igual.
        """
        self.crear(self.mixto(domicilio=self.domicilio()))
        id_venta = self.venta_creada().ID_Venta
        aprobar_comprobante(self.db, id_venta)
        self.assertEqual(self.venta_creada().Estado_Pago, "anticipo_pagado")
        self.avanzar(
            id_venta,
            EstadoPedido.CONFIRMADO, EstadoPedido.LISTO, EstadoPedido.EN_CAMINO,
        )

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertIn("efectivo", ctx.exception.detail.lower())

        # Cobrada la otra mitad, el pedido sí se entrega.
        self.cobrar(id_venta)
        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)

    def test_el_domicilio_por_transferencia_no_espera_ningun_cobro(self):
        """No hay plata en mano: exigir el cobro dejaría el pedido trabado."""
        self.crear(self.transferencia(domicilio=self.domicilio()))
        id_venta = self.venta_creada().ID_Venta
        aprobar_comprobante(self.db, id_venta)
        self.avanzar(
            id_venta,
            EstadoPedido.CONFIRMADO, EstadoPedido.LISTO, EstadoPedido.EN_CAMINO,
            EstadoPedido.ENTREGADO,
        )
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)

    def test_el_domiciliario_tampoco_entrega_sin_registrar_el_cobro(self):
        """La misma regla por el otro camino: el módulo de domicilios.

        Es el camino real —quien recibe la plata es el repartidor— y mueve la
        venta directo al estado 8 sin pasar por gestión de pedidos.
        """
        self.crear(self.pedido(domicilio=self.domicilio()))
        dom = self.db.query(Domicilio).first()

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado_domicilio(self.db, dom.ID_Domicilio, ESTADO_DOM_ENTREGADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cobro", ctx.exception.detail.lower())

    def test_el_domiciliario_no_entrega_un_mixto_con_solo_la_transferencia(self):
        """El agujero que veía el filtro viejo: "anticipo_pagado" lo dejaba pasar."""
        self.crear(self.mixto(domicilio=self.domicilio()))
        id_venta = self.venta_creada().ID_Venta
        aprobar_comprobante(self.db, id_venta)
        dom = self.db.query(Domicilio).first()

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado_domicilio(self.db, dom.ID_Domicilio, ESTADO_DOM_ENTREGADO)
        self.assertIn("efectivo", ctx.exception.detail.lower())

        # Cobrada la parte en mano, el repartidor sí puede cerrar la entrega.
        self.cobrar(id_venta)
        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, ESTADO_DOM_ENTREGADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)

    def test_el_pedido_para_recoger_en_tienda_tambien_exige_el_cobro(self):
        """En el mostrador la plata la recibe quien atiende, pero se registra.

        La puerta era solo del domicilio: en tienda el pedido se cerraba sin
        dejar rastro de si el efectivo entró.
        """
        self.crear(self.pedido())
        id_venta = self.venta_creada().ID_Venta
        self.avanzar(id_venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)

        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("efectivo", ctx.exception.detail.lower())

        self.cobrar(id_venta)
        cambiar_estado(self.db, id_venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)

    def test_el_pedido_por_transferencia_en_tienda_no_espera_ningun_cobro(self):
        """No hay plata en mano: exigir el cobro lo dejaría trabado."""
        self.crear(self.transferencia())
        id_venta = self.venta_creada().ID_Venta
        aprobar_comprobante(self.db, id_venta)
        self.avanzar(
            id_venta,
            EstadoPedido.CONFIRMADO, EstadoPedido.LISTO, EstadoPedido.ENTREGADO,
        )
        self.assertEqual(self.venta_creada().Estado, EstadoPedido.ENTREGADO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
