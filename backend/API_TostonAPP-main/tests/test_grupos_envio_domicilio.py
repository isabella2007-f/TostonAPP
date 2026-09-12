"""Pedido dividido — un domicilio por viaje.

El cliente que pide más de lo que hay puede recibir antes lo disponible: el
pedido se parte en Grupo A (anticipado) y Grupo B (programado), y cada grupo
elige su método de entrega. Regla nueva verificada acá: **cada viaje a domicilio
paga su propio domicilio**, con snapshot propio (su barrio + ofertas de su día).

    DB_USER=u DB_PASSWORD=p DB_HOST=localhost DB_PORT=3306 DB_NAME=test \
        python -m unittest tests.test_grupos_envio_domicilio
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
os.environ.setdefault("SECRET_KEY", "clave-de-prueba")
os.environ.setdefault("ALGORITHM", "HS256")

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.features.ventas.gestion_ventas.services.schemas import (
    DomicilioVentaInput, ProductoVentaInput, VentaCreate,
)
from src.features.ventas.gestion_ventas.services.service import (
    crear_venta, crear_grupos_envio, actualizar_tipo_entrega_grupo,
    cancelar_grupo_pendiente, cambiar_estado,
)
from src.features.ventas.pedidos.services.estados import EstadoPedido
from src.shared.services.models import (
    Barrio, Base, Ciudad, Departamento, Domicilio, FichaTecnica,
    FichaTecnicaInsumo, GrupoEnvio, Insumo, LoteCompra, OfertaDomicilio,
    OfertaXBarrio, Producto, UnidadMedida, Usuario, Venta, VentaXProducto,
)

ID_CLIENTE = 1
ID_TORTA = 1
ID_HARINA = 1
ID_BARRIO = 1
PRECIO = Decimal("5000")          # 6 × 5000 = 30.000 → sin anticipo obligatorio
PRECIO_BARRIO = 5000
STOCK = 2
PEDIDAS = 6                        # faltan 4 → preorden


class _Base(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self._sembrar()
        self.actual_cliente = {"tipo": "cliente", "registro": self.cliente}
        self.actual_admin = {"tipo": "admin", "registro": self.cliente}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _sembrar(self):
        self.db.add(Departamento(ID_Departamento=1, Nombre="Antioquia", Estado=1))
        self.db.add(Ciudad(ID_Ciudad=1, ID_Departamento=1, Nombre="Medellín", Estado=1))
        self.db.add(Barrio(ID_Barrio=ID_BARRIO, ID_Ciudad=1, Nombre="Centro",
                           Precio=PRECIO_BARRIO, Es_Base=True, Estado=1))
        self.cliente = Usuario(
            ID_Usuario=ID_CLIENTE, Nombre="Cliente", Apellidos="Prueba",
            Correo="c@p.test", Telefono="3001234567", ID_Rol=3, Estado=1,
        )
        self.db.add(self.cliente)
        self.db.add(Producto(ID_Producto=ID_TORTA, nombre="Torta", Precio_venta=PRECIO,
                             Stock=STOCK, Stock_Minimo=1, Estado=1, Publicado=1))
        self.db.add(UnidadMedida(ID_Unidad_Medida=1, Simbolo="g", Unidad_Medida="Gramos"))
        self.db.add(Insumo(ID_Insumo=ID_HARINA, Nombre="Harina", Unidad_Medida=1,
                           Stock_Actual=5000.0, Stock_Minimo=100, Estado=1))
        self.db.add(LoteCompra(ID_Lote_Compra=1, ID_Insumo=ID_HARINA,
                               Fecha_Vencimiento=datetime.now() + timedelta(days=30),
                               Cantidad_Inicial=5000.0, Cantidad_Actual=5000.0, Estado=1))
        self.db.add(FichaTecnica(ID_Ficha=1, ID_Producto=ID_TORTA, Version="1",
                                 Estado=1, Dias_Vida_Util=5, Vida_Util_Unidad="dias"))
        self.db.add(FichaTecnicaInsumo(ID_Ficha_Insumo=1, ID_Ficha=1, ID_Insumo=ID_HARINA,
                                       Cantidad=100.0, Unidad="g"))
        self.db.commit()

    # ── helpers ──────────────────────────────────────────────────────────
    def crear(self, con_domicilio=True):
        datos = dict(
            ID_Usuario=ID_CLIENTE, Metodo_Pago="Efectivo",
            productos=[ProductoVentaInput(ID_Producto=ID_TORTA, Cantidad=PEDIDAS)],
            # Fecha límite obligatoria para lo que hay que fabricar (checkout
            # nuevo); se reemplaza más abajo por una fecha lejana de todos
            # modos, esto solo evita el 400 al crear.
            Fecha_entrega_esperada=datetime.now() + timedelta(days=2),
        )
        if con_domicilio:
            datos["domicilio"] = DomicilioVentaInput(
                Direccion_entrega="Calle 10 #20-30", ID_Barrio=ID_BARRIO,
            )
        crear_venta(self.db, VentaCreate(**datos))
        self.db.commit()
        v = self.db.query(Venta).first()
        v.Fecha_entrega_esperada = datetime.now() + timedelta(days=10)
        self.db.commit()
        # Confirmar el pedido: abre la orden de producción del faltante y deja
        # el pedido en un estado válido para solicitar entrega anticipada.
        cambiar_estado(self.db, v.ID_Venta, EstadoPedido.CONFIRMADO)
        self.db.commit()
        return v

    def dividir(self, tipo_a="domicilio", tipo_b="domicilio", **kw):
        v = self.db.query(Venta).first()
        crear_grupos_envio(
            self.db, v.ID_Venta,
            datetime.now() + timedelta(days=3),
            tipo_a, tipo_b, self.actual_cliente, **kw,
        )
        self.db.commit()

    def total(self):
        return int(self.db.query(Venta).first().Total)

    def doms_grupo(self):
        return self.db.query(Domicilio).filter(Domicilio.ID_Grupo.isnot(None)).all()

    def grupo(self, tipo):
        return self.db.query(GrupoEnvio).filter(GrupoEnvio.Tipo == tipo).first()


# ═══════════════════════════════════════════════════════════════════════
# 1. El flujo de división funciona
# ═══════════════════════════════════════════════════════════════════════
class FlujoBaseTests(_Base):

    def test_se_crean_los_dos_grupos_con_el_reparto_correcto(self):
        self.crear()
        self.dividir(tipo_a="tienda", tipo_b="tienda")
        a, b = self.grupo("anticipado"), self.grupo("programado")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        # 2 en vitrina → grupo A; 4 en producción → grupo B
        self.assertEqual(sum(i.Cantidad for i in a.items), STOCK)
        self.assertEqual(sum(i.Cantidad for i in b.items), PEDIDAS - STOCK)

    def test_dos_grupos_a_tienda_no_cobran_domicilio(self):
        self.crear()
        base = 30000  # 6 × 5000
        self.dividir(tipo_a="tienda", tipo_b="tienda")
        self.assertEqual(self.total(), base)
        self.assertEqual(self.doms_grupo(), [])


# ═══════════════════════════════════════════════════════════════════════
# 2. Un domicilio por viaje
# ═══════════════════════════════════════════════════════════════════════
class UnDomicilioPorViajeTests(_Base):

    def test_dos_grupos_a_domicilio_cobran_dos_domicilios(self):
        self.crear()
        # Total original: 30.000 + 5.000 (un domicilio) = 35.000
        self.assertEqual(self.total(), 35000)
        self.dividir(tipo_a="domicilio", tipo_b="domicilio")
        # 30.000 + 5.000 (A) + 5.000 (B) = 40.000
        self.assertEqual(self.total(), 40000)
        doms = self.doms_grupo()
        self.assertEqual(len(doms), 2)
        for d in doms:
            self.assertEqual(int(d.Precio_Domicilio_Final), PRECIO_BARRIO)
            self.assertEqual(d.ID_Barrio, ID_BARRIO)

    def test_un_grupo_domicilio_y_otro_tienda_cobra_un_domicilio(self):
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="tienda")
        self.assertEqual(self.total(), 35000)          # sin cambio
        self.assertEqual(len(self.doms_grupo()), 1)

    def test_pedido_de_recogida_dividido_con_un_grupo_a_domicilio_suma_ese_domicilio(self):
        self.crear(con_domicilio=False)
        self.assertEqual(self.total(), 30000)
        # Pedido de recogida: no hay barrio heredado, hay que elegirlo.
        self.dividir(tipo_a="domicilio", tipo_b="tienda", id_barrio_a=ID_BARRIO)
        self.assertEqual(self.total(), 35000)

    def test_barrio_distinto_por_grupo(self):
        # Un segundo barrio, más caro, para el grupo B.
        self.db.add(Barrio(ID_Barrio=2, ID_Ciudad=1, Nombre="El Poblado",
                           Precio=8000, Es_Base=True, Estado=1))
        self.db.commit()
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="domicilio", id_barrio_b=2)
        # 30.000 + 5.000 (Centro) + 8.000 (El Poblado) = 43.000
        self.assertEqual(self.total(), 43000)


# ═══════════════════════════════════════════════════════════════════════
# 3. Ofertas y snapshot inmutable
# ═══════════════════════════════════════════════════════════════════════
class OfertasYSnapshotTests(_Base):

    def _oferta_todos_los_dias(self, tipo="descuento", pesos=2000):
        of = OfertaDomicilio(
            Nombre="Promo", Tipo=tipo, Monto_Pesos=pesos, Porcentaje=None,
            Dias_Semana="1,2,3,4,5,6,7", Dias_Mes=None, Estado=1,
            Fecha_Creacion=datetime.now(),
        )
        self.db.add(of)
        self.db.flush()
        self.db.add(OfertaXBarrio(ID_Oferta=of.ID_Oferta, ID_Barrio=ID_BARRIO))
        self.db.commit()
        return of

    def test_cada_grupo_aplica_las_ofertas_en_su_propio_snapshot(self):
        self._oferta_todos_los_dias()          # -2.000 → domicilio 3.000
        self.crear()
        # Original ya con oferta: 30.000 + 3.000 = 33.000
        self.assertEqual(self.total(), 33000)
        self.dividir(tipo_a="domicilio", tipo_b="domicilio")
        # 30.000 + 3.000 + 3.000 = 36.000
        self.assertEqual(self.total(), 36000)
        for d in self.doms_grupo():
            self.assertEqual(int(d.Precio_Domicilio_Final), 3000)
            self.assertEqual(int(d.Precio_Domicilio_Base), PRECIO_BARRIO)

    def test_snapshot_no_se_recalcula_si_cambia_el_barrio_despues(self):
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="domicilio")
        total_antes = self.total()
        finales_antes = sorted(int(d.Precio_Domicilio_Final) for d in self.doms_grupo())
        # El admin sube el precio del barrio y crea una oferta nueva.
        self.db.query(Barrio).filter(Barrio.ID_Barrio == ID_BARRIO).first().Precio = 99999
        self._oferta_todos_los_dias(tipo="recargo", pesos=10000)
        self.db.commit()
        v = self.db.query(Venta).first()
        self.assertEqual(int(v.Total), total_antes)
        self.assertEqual(
            sorted(int(d.Precio_Domicilio_Final) for d in self.doms_grupo()),
            finales_antes,
        )


# ═══════════════════════════════════════════════════════════════════════
# 4. Cambiar el tipo de entrega de un grupo / cancelarlo
# ═══════════════════════════════════════════════════════════════════════
class CambiosDeGrupoTests(_Base):

    def test_pasar_grupo_a_domicilio_suma_su_domicilio(self):
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="tienda")
        self.assertEqual(self.total(), 35000)
        b = self.grupo("programado")
        actualizar_tipo_entrega_grupo(
            self.db, self.db.query(Venta).first().ID_Venta, b.ID_Grupo,
            "domicilio", self.actual_cliente, id_barrio=ID_BARRIO,
        )
        self.db.commit()
        self.assertEqual(self.total(), 40000)
        self.assertEqual(len(self.doms_grupo()), 2)

    def test_pasar_grupo_a_tienda_resta_su_domicilio(self):
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="domicilio")
        self.assertEqual(self.total(), 40000)
        b = self.grupo("programado")
        actualizar_tipo_entrega_grupo(
            self.db, self.db.query(Venta).first().ID_Venta, b.ID_Grupo,
            "tienda", self.actual_cliente,
        )
        self.db.commit()
        self.assertEqual(self.total(), 35000)
        # El domicilio del grupo queda cancelado (Estado 5), no borrado.
        dom_b = self.db.query(Domicilio).filter(Domicilio.ID_Grupo == b.ID_Grupo).first()
        self.assertEqual(dom_b.Estado, 5)

    def test_cancelar_grupo_b_quita_su_domicilio_del_total(self):
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="domicilio")
        self.assertEqual(self.total(), 40000)
        a, b = self.grupo("anticipado"), self.grupo("programado")
        a.Estado = "entregado"          # requisito de cancelar_grupo_pendiente
        self.db.commit()
        cancelar_grupo_pendiente(
            self.db, self.db.query(Venta).first().ID_Venta, b.ID_Grupo, self.actual_admin,
        )
        self.db.commit()
        self.assertEqual(self.total(), 35000)

    def test_no_se_puede_cambiar_tipo_de_grupo_ya_enviado(self):
        self.crear()
        self.dividir(tipo_a="domicilio", tipo_b="domicilio")
        b = self.grupo("programado")
        b.Estado = "enviado"
        self.db.commit()
        with self.assertRaises(HTTPException):
            actualizar_tipo_entrega_grupo(
                self.db, self.db.query(Venta).first().ID_Venta, b.ID_Grupo,
                "tienda", self.actual_cliente,
            )


if __name__ == "__main__":
    unittest.main()
