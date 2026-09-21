"""Qué falta cobrar y qué falta aprobar en un pedido.

Estas preguntas viven en tres capas —web, app móvil y API— y tienen que
contestar lo mismo. Si la app le muestra al repartidor el botón de cobrar pero
el servidor no exige ese cobro, el pedido se entrega sin la plata; si el
servidor exige algo que la app no sabe pedir, el repartidor queda trabado.

El caso que más se colaba es el pedido mixto: lleva comprobante Y efectivo en
mano, y aprobar el comprobante lo dejaba en 'anticipo_pagado', que se leía como
"ya está pago" aunque la plata en mano siguiera sin cobrarse.

Desde la migración a `Pagos` (ver models.py / pagos_utils.py), estas dos
funciones consultan la BD (la fila `anticipo`/`saldo` de la venta), así que
las pruebas usan una sesión SQLite en memoria real en vez de un objeto Venta
simulado con atributos sueltos.
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("DB_USER", "u")
os.environ.setdefault("DB_PASSWORD", "p")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "test")

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.shared.services.database import Base
from src.shared.services.models import Venta, Pago
from src.shared.services.pagos_utils import (
    cobro_efectivo_pendiente,
    comprobante_sin_aprobar,
    es_pago_efectivo,
    es_pago_mixto,
    es_pago_transferencia,
)


class MetodoDePagoTests(unittest.TestCase):
    """Las tres preguntas básicas, con las variantes que se escriben de verdad."""

    def test_el_mixto_lleva_las_dos_cargas(self):
        self.assertTrue(es_pago_mixto("Mixto"))
        self.assertTrue(es_pago_transferencia("Mixto"))
        self.assertTrue(es_pago_efectivo("Mixto"))

    def test_reconoce_las_billeteras_como_transferencia(self):
        for metodo in ("Transferencia", "Nequi", "Daviplata", "Bancolombia", "QR"):
            self.assertTrue(es_pago_transferencia(metodo), metodo)
            self.assertFalse(es_pago_efectivo(metodo), metodo)

    def test_reconoce_el_contra_entrega_como_efectivo(self):
        for metodo in ("Efectivo", "Contra entrega", "cash"):
            self.assertTrue(es_pago_efectivo(metodo), metodo)
            self.assertFalse(es_pago_transferencia(metodo), metodo)

    def test_el_metodo_vacio_no_rompe(self):
        self.assertFalse(es_pago_efectivo(None))
        self.assertFalse(es_pago_transferencia(""))


class _DBTestCase(unittest.TestCase):
    """Base con una sesión SQLite en memoria para las pruebas que sí tocan `Pagos`."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def crear_venta(self, metodo, estado_pago="pendiente"):
        v = Venta(Metodo_Pago=metodo, Estado_Pago=estado_pago, Total=100000, Estado=1)
        self.db.add(v)
        self.db.flush()
        return v

    def crear_pago(self, venta, tipo, metodo_pago, estado="pendiente", comprobante_url=None):
        p = Pago(
            ID_Venta=venta.ID_Venta, Tipo=tipo, Metodo_Pago=metodo_pago,
            Estado=estado, Comprobante_Url=comprobante_url,
        )
        self.db.add(p)
        self.db.flush()
        return p


class CobroEfectivoPendienteTests(_DBTestCase):
    def test_el_efectivo_recien_pedido_esta_pendiente(self):
        v = self.crear_venta("Efectivo")
        self.assertTrue(cobro_efectivo_pendiente(self.db, v))

    def test_cobrado_ya_no_esta_pendiente(self):
        v = self.crear_venta("Efectivo", estado_pago="efectivo_recibido")
        self.assertFalse(cobro_efectivo_pendiente(self.db, v))

    def test_declarar_que_no_se_cobro_tambien_cuenta_como_registrado(self):
        # 'no_recibido' exige motivo de 10+ caracteres y queda auditado: el
        # repartidor dijo qué pasó, que es lo que se le pide antes de entregar.
        v = self.crear_venta("Efectivo", estado_pago="no_recibido")
        self.assertFalse(cobro_efectivo_pendiente(self.db, v))

    def test_la_transferencia_pura_no_tiene_nada_que_cobrar_en_mano(self):
        v = self.crear_venta("Transferencia", estado_pago="pendiente")
        self.assertFalse(cobro_efectivo_pendiente(self.db, v))

    def test_el_mixto_con_el_comprobante_aprobado_sigue_debiendo_el_efectivo(self):
        # Regresión: 'anticipo_pagado' se leía como pagado y el pedido mixto se
        # entregaba sin recibir la plata en mano.
        v = self.crear_venta("Mixto", estado_pago="anticipo_pagado")
        self.assertTrue(cobro_efectivo_pendiente(self.db, v))

    def test_el_mixto_con_el_efectivo_ya_registrado_no_esta_pendiente(self):
        # El admin puede cobrar la mitad en efectivo antes de que se apruebe el
        # comprobante: ahí el estado queda 'anticipo_pagado' pero la plata entró.
        v = self.crear_venta("Mixto", estado_pago="anticipo_pagado")
        self.crear_pago(v, "saldo", "Efectivo", estado="recibido")
        self.assertFalse(cobro_efectivo_pendiente(self.db, v))

    def test_el_mixto_saldado_no_esta_pendiente(self):
        v = self.crear_venta("Mixto", estado_pago="pagado_completo")
        self.assertFalse(cobro_efectivo_pendiente(self.db, v))

    def test_el_mixto_esperando_validacion_sigue_debiendo_el_efectivo(self):
        v = self.crear_venta("Mixto", estado_pago="pendiente_validacion")
        self.assertTrue(cobro_efectivo_pendiente(self.db, v))


class ComprobanteSinAprobarTests(_DBTestCase):
    def test_el_comprobante_recien_subido_esta_sin_aprobar(self):
        v = self.crear_venta("Transferencia", estado_pago="pendiente_validacion")
        self.crear_pago(v, "anticipo", "Transferencia", estado="pendiente_validacion",
                         comprobante_url="https://cloudinary.test/c.jpg")
        self.assertTrue(comprobante_sin_aprobar(self.db, v))

    def test_el_comprobante_aprobado_ya_no_frena(self):
        v = self.crear_venta("Transferencia", estado_pago="pagado_completo")
        self.crear_pago(v, "anticipo", "Transferencia", estado="aprobado",
                         comprobante_url="https://cloudinary.test/c.jpg")
        self.assertFalse(comprobante_sin_aprobar(self.db, v))

    def test_el_comprobante_rechazado_sigue_frenando(self):
        v = self.crear_venta("Transferencia", estado_pago="comprobante_rechazado")
        self.crear_pago(v, "anticipo", "Transferencia", estado="rechazado",
                         comprobante_url="https://cloudinary.test/c.jpg")
        self.assertTrue(comprobante_sin_aprobar(self.db, v))

    def test_sin_comprobante_adjunto_no_hay_nada_que_aprobar(self):
        # No se puede exigir aprobar algo que el admin no tiene forma de
        # aprobar: dejaria el pedido sin salida.
        v = self.crear_venta("Transferencia", estado_pago="pendiente")
        self.assertFalse(comprobante_sin_aprobar(self.db, v))

    def test_el_efectivo_puro_no_pasa_por_esta_puerta(self):
        v = self.crear_venta("Efectivo", estado_pago="pendiente")
        self.assertFalse(comprobante_sin_aprobar(self.db, v))

    def test_el_mixto_tambien_trae_comprobante_que_aprobar(self):
        v = self.crear_venta("Mixto", estado_pago="pendiente_validacion")
        self.crear_pago(v, "anticipo", "Transferencia", estado="pendiente_validacion",
                         comprobante_url="https://cloudinary.test/c.jpg")
        self.assertTrue(comprobante_sin_aprobar(self.db, v))

    def test_en_el_mixto_aprobar_el_comprobante_lo_deja_pasar(self):
        v = self.crear_venta("Mixto", estado_pago="anticipo_pagado")
        self.crear_pago(v, "anticipo", "Transferencia", estado="aprobado",
                         comprobante_url="https://cloudinary.test/c.jpg")
        self.assertFalse(comprobante_sin_aprobar(self.db, v))


if __name__ == "__main__":
    unittest.main()
