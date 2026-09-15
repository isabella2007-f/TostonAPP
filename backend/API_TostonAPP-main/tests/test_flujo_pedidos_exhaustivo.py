"""
tests/test_flujo_pedidos_exhaustivo.py

Revisión exhaustiva del flujo de pedidos — pruebas automatizadas.
NO corrige nada: si un caso falla lo reporta con evidencia.

Secciones:
  1. Máquina de estados — TODAS las transiciones inválidas
  2. Bloqueos por reglas de negocio en cambiar_estado
  3. Matriz pago × entrega × producción (16 combinaciones)
  4. Consistencia de datos entre pantallas

Corre sin credenciales:
    python -m unittest tests/test_flujo_pedidos_exhaustivo.py -v
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

from src.features.ventas.gestion_ventas.services.schemas import (
    DomicilioVentaInput,
    ProductoVentaInput,
    VentaCreate,
)
from src.features.ventas.gestion_ventas.services.service import (
    cambiar_estado,
    crear_venta,
    obtener_venta,
)
from src.features.ventas.domicilios.services.service import (
    cambiar_estado as cambiar_estado_domicilio,
    obtener_domicilio,
)
from src.features.ventas.pedidos.services.estados import (
    EstadoPedido,
    TRANSICIONES,
    validar_transicion,
)
from src.features.ventas.pedidos.services.schemas import RegistroCobro
from src.features.ventas.pedidos.services.service import (
    aprobar_comprobante,
    rechazar_comprobante,
    registrar_cobro_pedido,
    obtener_pedido,
)
from src.shared.services.models import (
    Barrio,
    Base,
    Ciudad,
    CreditoCliente,
    Departamento,
    Domicilio,
    FichaTecnica,
    OrdenProduccion,
    Producto,
    Usuario,
    Venta,
    VentaXProducto,
)

# ─── Constantes ─────────────────────────────────────────────────────────────
PRECIO = Decimal("10000")
ID_CLI = 1
ID_P1  = 1   # Tostón, stock=10, sin producción por defecto
ID_P2  = 2   # Torta,  stock=2,  se marca por encargo en los tests que lo necesitan

# Zona de entrega. El precio del barrio es el costo del domicilio: antes era
# la constante COSTO_DOMICILIO, que dejó de existir cuando pasó a depender
# del barrio.
ID_BARRIO = 1
COSTO_DOMICILIO = 5000
ADMIN  = 99  # ID ficticio para auditorías


# ─── Base ────────────────────────────────────────────────────────────────────
class BaseTest(unittest.TestCase):
    """SQLite en memoria limpio para cada test."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self._sembrar()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _sembrar(self):
        self.db.add(Usuario(
            ID_Usuario=ID_CLI, Nombre="Cliente", Apellidos="Test",
            Correo="c@t.co", Telefono="3001234567", ID_Rol=3, Estado=1,
        ))
        self.db.add(Producto(
            ID_Producto=ID_P1, nombre="Tostón",
            Precio_venta=PRECIO, Stock=10, Estado=1, Publicado=1,
        ))
        self.db.add(Producto(
            ID_Producto=ID_P2, nombre="Torta",
            Precio_venta=PRECIO, Stock=2, Estado=1, Publicado=1,
        ))
        # Zona de entrega: el precio del domicilio sale del barrio y se congela
        # al crear la venta. Sin barrio no hay pedido a domicilio posible.
        self.db.add(Departamento(ID_Departamento=1, Nombre="Antioquia", Estado=1))
        self.db.add(Ciudad(ID_Ciudad=1, ID_Departamento=1, Nombre="Medellín", Estado=1))
        self.db.add(Barrio(
            ID_Barrio=ID_BARRIO, ID_Ciudad=1, Nombre="Centro",
            Precio=COSTO_DOMICILIO, Estado=1,
        ))
        self.db.commit()

    # ── Builders ────────────────────────────────────────────────────────────
    def pedido(self, **kw):
        base = dict(
            ID_Usuario=ID_CLI,
            Metodo_Pago="Efectivo",
            productos=[ProductoVentaInput(ID_Producto=ID_P1, Cantidad=2)],
        )
        base.update(kw)
        return VentaCreate(**base)

    def dom_input(self, **kw):
        base = dict(
            Direccion_entrega="Calle 1",
            ID_Barrio=ID_BARRIO,
            Municipio_entrega="Medellín",
            Departamento_entrega="Antioquia",
        )
        base.update(kw)
        return DomicilioVentaInput(**base)

    def pedido_anticipo(self, **kw):
        """6 Tortas por encargo: 4 en preorden, $60k > umbral → requiere anticipo."""
        self.marcar_por_encargo(ID_P2)
        base = dict(
            ID_Usuario=ID_CLI,
            Metodo_Pago="Transferencia",
            productos=[ProductoVentaInput(ID_Producto=ID_P2, Cantidad=6)],
            requiere_anticipo=True,
            anticipo_monto=30000.0,
            anticipo_metodo_pago="Transferencia",
            anticipo_comprobante_url="https://cdn/ant.jpg",
            anticipo_registrado=True,
        )
        base.update(kw)
        return VentaCreate(**base)

    def fecha_futura(self, dias=10):
        return datetime.now() + timedelta(days=dias)

    # ── Acciones ─────────────────────────────────────────────────────────────
    def crear(self, datos):
        # Fecha límite obligatoria para lo que hay que fabricar (ver
        # test_crear_venta_e2e.py: mismo criterio, mismo motivo).
        if getattr(datos, "Fecha_entrega_esperada", None) is None and not datos.creado_por_admin:
            datos.Fecha_entrega_esperada = self.fecha_futura()
        r = crear_venta(self.db, datos)
        self.db.commit()
        return r

    def avanzar(self, id_venta, *estados):
        for e in estados:
            cambiar_estado(self.db, id_venta, e)

    def cobrar(self, id_venta, recibido=True, motivo=None):
        return registrar_cobro_pedido(
            self.db, id_venta,
            RegistroCobro(recibido=recibido, monto=None, motivo=motivo),
            ADMIN,
        )

    def aprobar_comp(self, id_venta):
        aprobar_comprobante(self.db, id_venta)

    def rechazar_comp(self, id_venta, motivo="imagen borrosa"):
        rechazar_comprobante(self.db, id_venta, motivo, ADMIN)

    # ── Configuración ────────────────────────────────────────────────────────
    def marcar_por_encargo(self, id_producto):
        p = self.db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
        p.Requiere_Produccion = 1
        if not self.db.query(FichaTecnica).filter(FichaTecnica.ID_Producto == id_producto).first():
            self.db.add(FichaTecnica(ID_Producto=id_producto, Version="1", Estado=1))
        self.db.commit()

    def set_stock(self, id_producto, stock):
        p = self.db.query(Producto).filter(Producto.ID_Producto == id_producto).first()
        p.Stock = stock
        self.db.commit()

    def dar_saldo(self, monto):
        self.db.add(CreditoCliente(ID_Usuario=ID_CLI, Saldo=Decimal(str(monto))))
        self.db.commit()

    def completar_op(self, id_venta, id_producto=None):
        q = self.db.query(OrdenProduccion).filter(OrdenProduccion.ID_Venta == id_venta)
        if id_producto:
            q = q.filter(OrdenProduccion.ID_Producto == id_producto)
        op = q.first()
        if op:
            op.Estado = 11
            self.db.commit()

    def cancelar_op(self, id_venta, id_producto=None):
        q = self.db.query(OrdenProduccion).filter(OrdenProduccion.ID_Venta == id_venta)
        if id_producto:
            q = q.filter(OrdenProduccion.ID_Producto == id_producto)
        op = q.first()
        if op:
            op.Estado = 5
            self.db.commit()

    # ── Lecturas ─────────────────────────────────────────────────────────────
    def venta(self):
        return self.db.query(Venta).first()

    def stock_prod(self, id_p):
        return self.db.query(Producto).filter(Producto.ID_Producto == id_p).first().Stock

    def saldo(self):
        c = self.db.query(CreditoCliente).filter(CreditoCliente.ID_Usuario == ID_CLI).first()
        return c.Saldo if c else Decimal("0")

    def primer_dom(self):
        return self.db.query(Domicilio).first()

    def ops(self, id_venta):
        return self.db.query(OrdenProduccion).filter(OrdenProduccion.ID_Venta == id_venta).all()

    # ── Mocks de usuario ─────────────────────────────────────────────────────
    def mock_admin(self):
        return {"tipo": "admin", "registro": type("U", (), {"ID_Usuario": ADMIN, "ID_Rol": 1})()}

    def mock_cliente(self, uid=ID_CLI):
        return {"tipo": "cliente", "registro": type("U", (), {"ID_Usuario": uid, "ID_Rol": 3})()}


# ══════════════════════════════════════════════════════════════════════════════
# 1. MÁQUINA DE ESTADOS — transiciones inválidas
#    Prueba validar_transicion() directamente: no necesita BD real.
# ══════════════════════════════════════════════════════════════════════════════
class TransicionesInvalidasTest(unittest.TestCase):
    """
    Verifica que CADA transición no listada en TRANSICIONES sea rechazada con
    HTTPException 400. Cubre 11 estados × hasta 10 destinos inválidos cada uno.
    """

    ALL = list(EstadoPedido)

    def _invalida(self, actual, nuevo, domicilio=False, msg=None):
        with self.assertRaises(HTTPException, msg=msg) as ctx:
            validar_transicion(int(actual), int(nuevo), domicilio)
        self.assertEqual(ctx.exception.status_code, 400, msg=msg)

    # ── Desde PENDIENTE (1) ───────────────────────────────────────────────
    def test_pendiente_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.PREPARANDO)

    def test_pendiente_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.LISTO)

    def test_pendiente_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.EN_CAMINO)

    def test_pendiente_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.ENTREGADO)

    def test_pendiente_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.FECHA_PROPUESTA)

    def test_pendiente_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.FECHA_RECHAZADA)

    def test_pendiente_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_pendiente_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.PENDIENTE, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde CONFIRMADO (4) ──────────────────────────────────────────────
    def test_confirmado_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.PENDIENTE)

    def test_confirmado_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.EN_CAMINO)

    def test_confirmado_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.ENTREGADO)

    def test_confirmado_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.FECHA_PROPUESTA)

    def test_confirmado_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.FECHA_RECHAZADA)

    def test_confirmado_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_confirmado_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.CONFIRMADO, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde PREPARANDO (13) ─────────────────────────────────────────────
    def test_preparando_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.PENDIENTE)

    def test_preparando_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.CONFIRMADO)

    def test_preparando_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.EN_CAMINO)

    def test_preparando_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.ENTREGADO)

    def test_preparando_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.FECHA_PROPUESTA)

    def test_preparando_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.FECHA_RECHAZADA)

    def test_preparando_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_preparando_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.PREPARANDO, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde LISTO (11) ──────────────────────────────────────────────────
    def test_listo_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.PENDIENTE)

    def test_listo_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.CONFIRMADO)

    def test_listo_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.PREPARANDO)

    def test_listo_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.FECHA_PROPUESTA)

    def test_listo_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.FECHA_RECHAZADA)

    def test_listo_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_listo_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.LISTO, EstadoPedido.ESCALADO_A_ADMIN)

    # Reglas de dominio desde LISTO
    def test_listo_a_en_camino_sin_domicilio_invalido(self):
        """EN_CAMINO solo tiene sentido para pedidos con domicilio."""
        self._invalida(EstadoPedido.LISTO, EstadoPedido.EN_CAMINO, domicilio=False)

    def test_listo_a_entregado_con_domicilio_invalido(self):
        """Un domicilio debe pasar por EN_CAMINO antes de marcarse entregado."""
        self._invalida(EstadoPedido.LISTO, EstadoPedido.ENTREGADO, domicilio=True)

    # ── Desde EN_CAMINO (9) ───────────────────────────────────────────────
    def test_en_camino_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.PENDIENTE)

    def test_en_camino_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.CONFIRMADO)

    def test_en_camino_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.PREPARANDO)

    def test_en_camino_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.LISTO)

    def test_en_camino_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.FECHA_PROPUESTA)

    def test_en_camino_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.FECHA_RECHAZADA)

    def test_en_camino_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_en_camino_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.EN_CAMINO, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde ENTREGADO (8) — estado terminal ─────────────────────────────
    def test_entregado_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.PENDIENTE)

    def test_entregado_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.CONFIRMADO)

    def test_entregado_no_puede_ir_a_cancelado(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.CANCELADO)

    def test_entregado_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.PREPARANDO)

    def test_entregado_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.LISTO)

    def test_entregado_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.EN_CAMINO)

    def test_entregado_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.FECHA_PROPUESTA)

    def test_entregado_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.FECHA_RECHAZADA)

    def test_entregado_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_entregado_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.ENTREGADO, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde CANCELADO (5) — estado terminal ─────────────────────────────
    def test_cancelado_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.PENDIENTE)

    def test_cancelado_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.CONFIRMADO)

    def test_cancelado_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.ENTREGADO)

    def test_cancelado_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.PREPARANDO)

    def test_cancelado_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.LISTO)

    def test_cancelado_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.EN_CAMINO)

    def test_cancelado_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.FECHA_PROPUESTA)

    def test_cancelado_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.FECHA_RECHAZADA)

    def test_cancelado_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_cancelado_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.CANCELADO, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde FECHA_PROPUESTA (16) ────────────────────────────────────────
    def test_fecha_propuesta_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.PENDIENTE)

    def test_fecha_propuesta_no_puede_ir_a_cancelado(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.CANCELADO)

    def test_fecha_propuesta_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.PREPARANDO)

    def test_fecha_propuesta_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.LISTO)

    def test_fecha_propuesta_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.EN_CAMINO)

    def test_fecha_propuesta_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.ENTREGADO)

    def test_fecha_propuesta_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.PARCIALMENTE_ENTREGADO)

    def test_fecha_propuesta_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.FECHA_PROPUESTA, EstadoPedido.ESCALADO_A_ADMIN)

    # ── Desde FECHA_RECHAZADA (17) ────────────────────────────────────────
    def test_fecha_rechazada_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.PENDIENTE)

    def test_fecha_rechazada_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.CONFIRMADO)

    def test_fecha_rechazada_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.PREPARANDO)

    def test_fecha_rechazada_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.LISTO)

    def test_fecha_rechazada_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.EN_CAMINO)

    def test_fecha_rechazada_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.ENTREGADO)

    def test_fecha_rechazada_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.FECHA_RECHAZADA, EstadoPedido.PARCIALMENTE_ENTREGADO)

    # ── Desde ESCALADO_A_ADMIN (19) ───────────────────────────────────────
    def test_escalado_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.PENDIENTE)

    def test_escalado_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.PREPARANDO)

    def test_escalado_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.LISTO)

    def test_escalado_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.EN_CAMINO)

    def test_escalado_no_puede_ir_a_entregado(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.ENTREGADO)

    def test_escalado_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.FECHA_PROPUESTA)

    def test_escalado_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.FECHA_RECHAZADA)

    def test_escalado_no_puede_ir_a_parcialmente_entregado(self):
        self._invalida(EstadoPedido.ESCALADO_A_ADMIN, EstadoPedido.PARCIALMENTE_ENTREGADO)

    # ── Desde PARCIALMENTE_ENTREGADO (18) ────────────────────────────────
    def test_parcialmente_entregado_no_puede_ir_a_pendiente(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.PENDIENTE)

    def test_parcialmente_entregado_no_puede_ir_a_confirmado(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.CONFIRMADO)

    def test_parcialmente_entregado_no_puede_ir_a_preparando(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.PREPARANDO)

    def test_parcialmente_entregado_no_puede_ir_a_listo(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.LISTO)

    def test_parcialmente_entregado_no_puede_ir_a_en_camino(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.EN_CAMINO)

    def test_parcialmente_entregado_no_puede_ir_a_fecha_propuesta(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.FECHA_PROPUESTA)

    def test_parcialmente_entregado_no_puede_ir_a_fecha_rechazada(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.FECHA_RECHAZADA)

    def test_parcialmente_entregado_no_puede_ir_a_escalado(self):
        self._invalida(EstadoPedido.PARCIALMENTE_ENTREGADO, EstadoPedido.ESCALADO_A_ADMIN)

    def test_todas_las_transiciones_validas_son_aceptadas(self):
        """Verificación inversa: ninguna transición válida debe ser rechazada."""
        for e_actual, validas in TRANSICIONES.items():
            for e_nuevo in validas:
                tiene_dom = (
                    e_actual == EstadoPedido.LISTO and e_nuevo == EstadoPedido.EN_CAMINO
                )
                # Desde LISTO, tanto "entregado directo" como "retenido en
                # tienda" (3.7, cobro fallido) solo aplican a recoger en
                # tienda, no a domicilio.
                no_dom = e_actual == EstadoPedido.LISTO and e_nuevo in (
                    EstadoPedido.ENTREGADO, EstadoPedido.RETENIDO_EN_TIENDA,
                )
                domicilio = tiene_dom or (not no_dom)
                with self.subTest(desde=e_actual, hacia=e_nuevo):
                    try:
                        validar_transicion(e_actual, e_nuevo, domicilio)
                    except HTTPException:
                        self.fail(
                            f"validar_transicion({e_actual}, {e_nuevo}, {domicilio}) "
                            "lanzó HTTPException pero era una transición válida"
                        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. BLOQUEOS POR REGLAS DE NEGOCIO en cambiar_estado()
# ══════════════════════════════════════════════════════════════════════════════
class BloqueosNegocioTest(BaseTest):
    """Prueba que cambiar_estado() rechaza operaciones cuando las reglas de
    negocio no se cumplen — no es solo la máquina de estados."""

    # ── Confirmar con comprobante sin revisar ─────────────────────────────
    def test_confirmar_con_comprobante_pendiente_de_validar_es_rechazado(self):
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
        ))
        v = self.venta()
        self.assertEqual(v.Estado_Pago, "pendiente_validacion")
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("comprobante", ctx.exception.detail.lower())
        self.assertEqual(self.venta().Estado, EstadoPedido.PENDIENTE)

    def test_confirmar_con_comprobante_rechazado_da_mensaje_especifico(self):
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
        ))
        v = self.venta()
        self.rechazar_comp(v.ID_Venta)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("rechazado", ctx.exception.detail.lower())

    def test_confirmar_efectivo_sin_comprobante_es_permitido(self):
        self.crear(self.pedido())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.CONFIRMADO)

    # ── Entregado con cobro en efectivo pendiente ─────────────────────────
    def test_tienda_efectivo_entregado_sin_cobro_es_rechazado(self):
        self.crear(self.pedido())
        v = self.venta()
        self.avanzar(v.ID_Venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("efectivo", ctx.exception.detail.lower())

    def test_tienda_efectivo_entregado_con_cobro_registrado_es_permitido(self):
        self.crear(self.pedido())
        v = self.venta()
        self.avanzar(v.ID_Venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)
        self.cobrar(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    def test_tienda_efectivo_entregado_declarando_no_cobrado_con_motivo_es_permitido(self):
        """Declarar que no se pudo cobrar (con motivo) también cierra la venta."""
        self.crear(self.pedido())
        v = self.venta()
        self.avanzar(v.ID_Venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)
        self.cobrar(v.ID_Venta, recibido=False, motivo="cliente no tenía el efectivo disponible")
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    def test_domicilio_efectivo_entregado_sin_cobro_es_rechazado(self):
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        self.avanzar(
            v.ID_Venta,
            EstadoPedido.CONFIRMADO, EstadoPedido.LISTO, EstadoPedido.EN_CAMINO,
        )
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertIn("efectivo", ctx.exception.detail.lower())

    def test_domicilio_efectivo_entregado_via_repartidor_sin_cobro_es_rechazado(self):
        """El módulo de domicilios también bloquea si falta el cobro."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        dom = self.primer_dom()
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cobro", ctx.exception.detail.lower())

    # ── Entregado con anticipo pendiente de pago final ────────────────────
    def test_tienda_anticipo_entregado_sin_pago_final_es_rechazado(self):
        # Anticipo Transferencia: el anticipo auto-registra el cobro al crear.
        # No hay efectivo que cobrar por separado — el bloqueo viene de pago_final.
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.completar_op(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("pago final", ctx.exception.detail.lower())

    # ── Listo bloqueado por producción incompleta ─────────────────────────
    def test_listo_bloqueado_con_op_activa(self):
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)
        self.assertIn("producción", ctx.exception.detail.lower())

    def test_listo_permitido_con_op_completada(self):
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.completar_op(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)
        self.assertEqual(self.venta().Estado, EstadoPedido.LISTO)

    def test_listo_bloqueado_con_op_cancelada_y_sin_stock(self):
        """Cancelar la OP no es producir: el faltante sigue sin cubrirse."""
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.cancelar_op(v.ID_Venta)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)
        self.assertIn("Torta", ctx.exception.detail)

    def test_listo_permitido_tras_reponer_stock_aunque_op_este_cancelada(self):
        """Si entró stock por otra vía, el faltante ya existe aunque la OP se canceló."""
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.cancelar_op(v.ID_Venta)
        # La preorden era 4 (6 pedidas - 2 en stock); reponer esas 4
        self.set_stock(ID_P2, 4)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)
        self.assertEqual(self.venta().Estado, EstadoPedido.LISTO)

    def test_mixto_no_puede_respaldar_anticipo(self):
        """El efectivo del mixto se cobra al entregar, no al pedir: no respalda anticipo."""
        self.marcar_por_encargo(ID_P2)
        with self.assertRaises(HTTPException) as ctx:
            self.crear(VentaCreate(
                ID_Usuario=ID_CLI,
                Metodo_Pago="Mixto",
                pago_efectivo_monto=Decimal("5000"),
                comprobante_pago="https://cdn/comp.jpg",
                productos=[ProductoVentaInput(ID_Producto=ID_P2, Cantidad=6)],
            ))
        self.assertIn("mixto", ctx.exception.detail.lower())


# ══════════════════════════════════════════════════════════════════════════════
# 3. MATRIZ PAGO × ENTREGA × PRODUCCIÓN
#    16 combinaciones: 4 métodos × 2 entregas × 2 estados de producción
#    Para cada una se verifica que "Entregado" se bloquea/permite correctamente.
# ══════════════════════════════════════════════════════════════════════════════
class MatrizPagoEntregaTest(BaseTest):
    """
    Nomenclatura de los tests:
      test_[metodo]_[entrega]_[produccion]_[resultado]
      metodo: efectivo | transferencia | mixto | anticipo
      entrega: tienda | domicilio
      produccion: sin_prod | con_prod (producción ya completada)
      resultado: permite_entregado | bloquea_sin_X
    """

    # ── Helpers de flujo ──────────────────────────────────────────────────
    def _avanzar_hasta_listo_tienda(self, id_venta):
        self.avanzar(id_venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)

    def _avanzar_hasta_en_camino_domicilio(self, id_venta):
        self.avanzar(
            id_venta,
            EstadoPedido.CONFIRMADO, EstadoPedido.LISTO, EstadoPedido.EN_CAMINO,
        )

    # ── EFECTIVO × TIENDA ─────────────────────────────────────────────────
    def test_efectivo_tienda_sin_prod_bloquea_sin_cobro(self):
        self.crear(self.pedido())
        v = self.venta()
        self._avanzar_hasta_listo_tienda(v.ID_Venta)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertIn("efectivo", ctx.exception.detail.lower())

    def test_efectivo_tienda_sin_prod_permite_entregado_con_cobro(self):
        self.crear(self.pedido())
        v = self.venta()
        self._avanzar_hasta_listo_tienda(v.ID_Venta)
        self.cobrar(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    # ── EFECTIVO × DOMICILIO ──────────────────────────────────────────────
    def test_efectivo_domicilio_sin_prod_bloquea_sin_cobro(self):
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        self._avanzar_hasta_en_camino_domicilio(v.ID_Venta)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertIn("efectivo", ctx.exception.detail.lower())

    def test_efectivo_domicilio_sin_prod_permite_entregado_con_cobro(self):
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        self._avanzar_hasta_en_camino_domicilio(v.ID_Venta)
        self.cobrar(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    def test_efectivo_domicilio_sin_prod_via_repartidor_bloquea_sin_cobro(self):
        """El módulo de domicilios también aplica el bloqueo."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        dom = self.primer_dom()
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_efectivo_domicilio_sin_prod_via_repartidor_permite_con_cobro(self):
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        self.cobrar(v.ID_Venta)
        dom = self.primer_dom()
        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.db.refresh(v)
        self.assertEqual(v.Estado, EstadoPedido.ENTREGADO)

    # ── TRANSFERENCIA × TIENDA ────────────────────────────────────────────
    def test_transferencia_tienda_sin_prod_bloquea_confirmar_sin_comp_aprobado(self):
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
        ))
        v = self.venta()
        with self.assertRaises(HTTPException):
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.PENDIENTE)

    def test_transferencia_tienda_sin_prod_permite_entregado_con_comp_aprobado(self):
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        self._avanzar_hasta_listo_tienda(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    # ── TRANSFERENCIA × DOMICILIO ─────────────────────────────────────────
    def test_transferencia_domicilio_sin_prod_permite_entregado_con_comp_aprobado(self):
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
            domicilio=self.dom_input(),
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        self._avanzar_hasta_en_camino_domicilio(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    def test_transferencia_domicilio_sin_prod_via_repartidor_permite_con_comp_aprobado(self):
        """El repartidor puede entregar un pedido por transferencia sin cobro en mano."""
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
            domicilio=self.dom_input(),
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        dom = self.primer_dom()
        # El repartidor lo pone directamente en ENTREGADO desde PENDIENTE
        # (cobro pendiente no aplica porque no es efectivo)
        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.db.refresh(v)
        self.assertEqual(v.Estado, EstadoPedido.ENTREGADO)

    # ── MIXTO × TIENDA ────────────────────────────────────────────────────
    def test_mixto_tienda_sin_prod_bloquea_sin_cobro_aunque_comp_aprobado(self):
        """El comprobante cubre la transferencia, pero la parte en efectivo sigue pendiente."""
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            comprobante_pago="https://cdn/comp.jpg",
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        self._avanzar_hasta_listo_tienda(v.ID_Venta)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertIn("efectivo", ctx.exception.detail.lower())

    def test_mixto_tienda_sin_prod_permite_entregado_con_comp_aprobado_y_cobro(self):
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            comprobante_pago="https://cdn/comp.jpg",
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        self._avanzar_hasta_listo_tienda(v.ID_Venta)
        self.cobrar(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertEqual(self.venta().Estado, EstadoPedido.ENTREGADO)

    # ── MIXTO × DOMICILIO ────────────────────────────────────────────────
    def test_mixto_domicilio_sin_prod_bloquea_sin_cobro_aunque_comp_aprobado(self):
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            comprobante_pago="https://cdn/comp.jpg",
            domicilio=self.dom_input(),
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        self._avanzar_hasta_en_camino_domicilio(v.ID_Venta)
        with self.assertRaises(HTTPException):
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)

    def test_mixto_domicilio_sin_prod_via_repartidor_bloquea_sin_cobro(self):
        """El repartidor tampoco puede entregar un mixto sin registrar el efectivo."""
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            comprobante_pago="https://cdn/comp.jpg",
            domicilio=self.dom_input(),
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        dom = self.primer_dom()
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.assertIn("efectivo", ctx.exception.detail.lower())

    def test_mixto_domicilio_sin_prod_via_repartidor_permite_con_cobro(self):
        self.crear(self.pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=Decimal("5000"),
            comprobante_pago="https://cdn/comp.jpg",
            domicilio=self.dom_input(),
        ))
        v = self.venta()
        self.aprobar_comp(v.ID_Venta)
        self.cobrar(v.ID_Venta)
        dom = self.primer_dom()
        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.db.refresh(v)
        self.assertEqual(v.Estado, EstadoPedido.ENTREGADO)

    # ── ANTICIPO × TIENDA ─────────────────────────────────────────────────
    def test_anticipo_tienda_con_prod_bloquea_entregado_sin_pago_final(self):
        # Anticipo Transferencia: cobro auto-registrado al crear; el bloqueo
        # al entregar viene de Pago_Final_Registrado=False.
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.completar_op(v.ID_Venta)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertIn("pago final", ctx.exception.detail.lower())

    def test_anticipo_tienda_con_prod_bloquea_listo_con_op_incompleta(self):
        self.crear(self.pedido_anticipo())
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        with self.assertRaises(HTTPException):
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.LISTO)

    # ── ANTICIPO × DOMICILIO ──────────────────────────────────────────────
    def test_anticipo_domicilio_con_prod_bloquea_entregado_sin_pago_final(self):
        # Anticipo Transferencia: cobro auto-registrado al crear.
        self.crear(self.pedido_anticipo(domicilio=self.dom_input()))
        v = self.venta()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.completar_op(v.ID_Venta)
        self.avanzar(v.ID_Venta, EstadoPedido.LISTO, EstadoPedido.EN_CAMINO)
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado(self.db, v.ID_Venta, EstadoPedido.ENTREGADO)
        self.assertIn("pago final", ctx.exception.detail.lower())

    def test_anticipo_domicilio_via_repartidor_bloquea_sin_pago_final(self):
        """El repartidor no puede entregar un domicilio con anticipo cuando el pago
        final aún no está registrado — el estado_pago 'anticipo_pagado' no está en
        los estados de pago aceptados por el módulo de domicilios.
        Nota: Anticipo+Mixto está bloqueado en creación; solo Transferencia aplica."""
        self.crear(self.pedido_anticipo(domicilio=self.dom_input()))
        dom = self.primer_dom()
        with self.assertRaises(HTTPException) as ctx:
            cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        self.assertEqual(ctx.exception.status_code, 400)


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONSISTENCIA DE DATOS ENTRE PANTALLAS
#    Verifica que un cambio de estado hecho desde cualquier camino se refleje
#    correctamente en TODOS los endpoints que muestran ese pedido.
# ══════════════════════════════════════════════════════════════════════════════
class ConsistenciaDatosTest(BaseTest):
    """
    Causa de varios bugs reportados: un cambio de estado (desde Domicilios o desde
    el flujo normal) no se reflejaba en todas las pantallas.

    Cada test verifica que tanto obtener_venta() como obtener_domicilio() retornen
    el mismo estado después de cada transición, independientemente del camino
    usado para llegar a él.
    """

    def test_cambio_via_gestion_pedidos_reflejado_en_domicilio(self):
        """Confirmar el pedido vía gestión → el domicilio debe ver la venta actualizada."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()

        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        datos_dom = obtener_domicilio(self.db, dom.ID_Domicilio)
        self.assertEqual(datos_dom["venta_estado"], EstadoPedido.CONFIRMADO)

    def test_cambio_via_gestion_pedidos_listo_reflejado_en_domicilio(self):
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()
        self.avanzar(v.ID_Venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)

        datos_dom = obtener_domicilio(self.db, dom.ID_Domicilio)
        self.assertEqual(datos_dom["venta_estado"], EstadoPedido.LISTO)

    def test_cambio_via_domicilio_en_camino_reflejado_en_venta(self):
        """Poner el domicilio EN_CAMINO → la venta también debe quedar EN_CAMINO."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()
        self.avanzar(v.ID_Venta, EstadoPedido.CONFIRMADO, EstadoPedido.LISTO)

        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 9)  # EN_CAMINO
        datos_venta = obtener_venta(self.db, v.ID_Venta)
        self.assertEqual(datos_venta["Estado"], EstadoPedido.EN_CAMINO)

    def test_cambio_via_domicilio_entregado_reflejado_en_venta(self):
        """Marcar el domicilio como entregado → la venta queda ENTREGADO."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()
        self.cobrar(v.ID_Venta)

        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)  # ENTREGADO
        datos_venta = obtener_venta(self.db, v.ID_Venta)
        self.assertEqual(datos_venta["Estado"], EstadoPedido.ENTREGADO)

    def test_cambio_via_domicilio_cancelado_reflejado_en_venta(self):
        """Cancelar el domicilio → la venta queda CANCELADO."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()

        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 5)  # CANCELADO
        datos_venta = obtener_venta(self.db, v.ID_Venta)
        self.assertEqual(datos_venta["Estado"], EstadoPedido.CANCELADO)

    def test_entregado_via_domicilio_refleja_en_venta_estado_pago(self):
        """El estado_pago del pedido es visible en ambas pantallas tras la entrega."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()
        self.cobrar(v.ID_Venta)

        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)
        datos_venta = obtener_venta(self.db, v.ID_Venta)
        datos_dom = obtener_domicilio(self.db, dom.ID_Domicilio)

        # Ambas pantallas deben mostrar el mismo estado de pago
        self.assertEqual(datos_venta["estado_pago"], datos_dom["estado_pago"])

    def test_estado_pago_consistente_entre_vista_venta_y_vista_domicilio(self):
        """Si el comprobante se aprueba vía gestión, el domicilio también lo ve."""
        self.crear(self.pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cdn/comp.jpg",
            domicilio=self.dom_input(),
        ))
        v = self.venta()
        dom = self.primer_dom()
        self.aprobar_comp(v.ID_Venta)

        datos_dom = obtener_domicilio(self.db, dom.ID_Domicilio)
        datos_venta = obtener_venta(self.db, v.ID_Venta)
        self.assertEqual(datos_dom["estado_pago"], datos_venta["estado_pago"])
        self.assertEqual(datos_dom["estado_pago"], "pagado_completo")

    def test_cancelar_via_gestion_reflejado_en_domicilio(self):
        """Cancelar el pedido vía gestión → el domicilio también reporta la venta cancelada."""
        self.crear(self.pedido(domicilio=self.dom_input()))
        v = self.venta()
        dom = self.primer_dom()
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CANCELADO)

        datos_dom = obtener_domicilio(self.db, dom.ID_Domicilio)
        self.assertEqual(datos_dom["venta_estado"], EstadoPedido.CANCELADO)

    def test_stock_se_descuenta_exactamente_una_vez_al_entregar_domicilio(self):
        """Entregar el domicilio descuenta el stock una sola vez, sin duplicar."""
        stock_inicial = self.stock_prod(ID_P1)  # 10
        self.crear(self.pedido(domicilio=self.dom_input()))  # pide 2 de P1
        v = self.venta()
        self.cobrar(v.ID_Venta)
        dom = self.primer_dom()

        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 8)  # ENTREGADO
        stock_final = self.stock_prod(ID_P1)
        self.assertEqual(stock_final, stock_inicial - 2)

    def test_stock_se_restaura_al_cancelar_tienda_desde_confirmado(self):
        """Cancelar un pedido de tienda que ya estaba CONFIRMADO restaura el stock."""
        self.crear(self.pedido(creado_por_admin=True))  # nace CONFIRMADO, descuenta stock
        v = self.venta()
        stock_tras_confirmar = self.stock_prod(ID_P1)
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CANCELADO)
        stock_tras_cancelar = self.stock_prod(ID_P1)
        self.assertGreater(stock_tras_cancelar, stock_tras_confirmar)

    def test_stock_no_se_descuenta_al_cancelar_domicilio_pendiente(self):
        """Un domicilio cancelado desde PENDIENTE no debió descontar stock: queda igual."""
        stock_inicial = self.stock_prod(ID_P1)
        self.crear(self.pedido(domicilio=self.dom_input()))
        dom = self.primer_dom()
        cambiar_estado_domicilio(self.db, dom.ID_Domicilio, 5)
        self.assertEqual(self.stock_prod(ID_P1), stock_inicial)


# ══════════════════════════════════════════════════════════════════════════════
# 7. CIERRE DE LA VENTANA DE 10 MIN — reserva perezosa de stock (3.6)
#    La porción en stock de un pedido para recoger en tienda se reserva al
#    cerrarse la ventana de 10 min (evaluación perezosa, sin scheduler), no
#    solo al llegar a CONFIRMADO — así otro pedido no puede consumirla
#    mientras el primero sigue en negociación de fecha/pago.
# ══════════════════════════════════════════════════════════════════════════════
class VentanaCierreStockTest(BaseTest):
    """Un pedido nace realmente PENDIENTE ("Pendiente de Aprobación") solo
    cuando pide producción (Necesita_Produccion): hace falta un faltante real
    contra el stock. Se deja el stock de P1 en 4 y se piden 6 → 4 en stock
    reservable (lo que 3.6 mueve al cierre de ventana) y 2 en preorden (para
    la OP), con un total de $60.000 que no cruza el umbral de anticipo."""

    def _pedido_en_negociacion(self, cantidad=6, stock=4):
        self.marcar_por_encargo(ID_P1)
        self.set_stock(ID_P1, stock)
        return self.pedido(
            productos=[ProductoVentaInput(ID_Producto=ID_P1, Cantidad=cantidad)],
            Fecha_entrega_esperada=self.fecha_futura(),
        )

    def _vencer_ventana(self, id_venta):
        """Simula que ya pasaron los 10 minutos desde que se creó el pedido."""
        v = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        v.Fecha_Venta = datetime.utcnow() - timedelta(minutes=11)
        self.db.commit()

    def test_no_reserva_stock_dentro_de_la_ventana(self):
        """Recién creado (dentro de los 10 min), el stock sigue completo."""
        self.crear(self._pedido_en_negociacion())
        v = self.venta()
        self.assertEqual(v.Estado, EstadoPedido.PENDIENTE)
        self.assertFalse(bool(v.Stock_Reservado))
        self.assertEqual(self.stock_prod(ID_P1), 4)

    def test_reserva_stock_al_tocar_el_pedido_tras_vencer_la_ventana(self):
        """Al cerrarse la ventana, la próxima vez que alguien mire el pedido
        (ver detalle) se reserva la porción en stock, sin que nadie lo haya
        confirmado todavía."""
        self.crear(self._pedido_en_negociacion())
        v = self.venta()
        self._vencer_ventana(v.ID_Venta)

        obtener_pedido(self.db, v.ID_Venta)  # "tocar" el pedido

        self.db.refresh(v)
        self.assertTrue(bool(v.Stock_Reservado))
        self.assertEqual(v.Estado, EstadoPedido.PENDIENTE)  # no cambia de estado
        self.assertEqual(self.stock_prod(ID_P1), 0)  # 4 - 4 en stock reservadas

    def test_reserva_perezosa_no_aplica_a_domicilio(self):
        """Un pedido a domicilio no reserva nada antes de ENTREGADO, ni
        siquiera al cerrarse la ventana: ese camino no cambia con 3.6."""
        pedido = self._pedido_en_negociacion()
        pedido.domicilio = self.dom_input()
        self.crear(pedido)
        v = self.venta()
        self._vencer_ventana(v.ID_Venta)

        obtener_pedido(self.db, v.ID_Venta)

        self.db.refresh(v)
        self.assertFalse(bool(v.Stock_Reservado))
        self.assertEqual(self.stock_prod(ID_P1), 4)

    def test_no_descuenta_dos_veces_si_confirma_despues_de_la_ventana(self):
        """Si el stock ya se reservó de forma perezosa, aprobar la fecha (que
        lleva el pedido a Confirmado/Preparando) no debe volver a
        descontarlo."""
        self.crear(self._pedido_en_negociacion())
        v = self.venta()
        self._vencer_ventana(v.ID_Venta)
        obtener_pedido(self.db, v.ID_Venta)  # reserva perezosa
        stock_tras_reserva = self.stock_prod(ID_P1)

        from src.features.ventas.gestion_ventas.services.service import aprobar_fecha_directa
        aprobar_fecha_directa(self.db, v.ID_Venta, self.mock_admin())

        self.assertEqual(self.stock_prod(ID_P1), stock_tras_reserva)

    def test_orden_de_produccion_se_crea_al_cerrar_la_ventana(self):
        """El faltante también abre su orden de producción (fila en BD) al
        cerrarse la ventana, sin esperar a que el pedido avance de estado."""
        pedido = self._pedido_en_negociacion()  # stock=4, pide 6 → faltan 2
        self.crear(pedido)
        v = self.venta()
        self.assertEqual(len(self.ops(v.ID_Venta)), 0)  # todavía no hay OP
        self._vencer_ventana(v.ID_Venta)

        obtener_pedido(self.db, v.ID_Venta)

        ops = self.ops(v.ID_Venta)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].Cantidad, 2)
        self.assertEqual(ops[0].Estado, 1)  # Pendiente: nace sin arrancar

    def test_cancelar_tras_reserva_perezosa_restaura_el_stock(self):
        """Si el pedido se cancela DESPUÉS de que la ventana lo reservó (pero
        sin haber llegado nunca a CONFIRMADO), el stock reservado se
        devuelve igual — la marca Stock_Reservado es la fuente de verdad,
        no el Estado."""
        self.crear(self._pedido_en_negociacion())
        v = self.venta()
        self._vencer_ventana(v.ID_Venta)
        obtener_pedido(self.db, v.ID_Venta)  # reserva perezosa, Estado sigue Pendiente
        self.assertEqual(self.stock_prod(ID_P1), 0)

        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CANCELADO)

        self.assertEqual(self.stock_prod(ID_P1), 4)
        self.db.refresh(v)
        self.assertFalse(bool(v.Stock_Reservado))


if __name__ == "__main__":
    unittest.main(verbosity=2)
