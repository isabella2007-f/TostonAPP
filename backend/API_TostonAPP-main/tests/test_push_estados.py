# -*- coding: utf-8 -*-
"""Qué cambios de pedido salen como push al celular del cliente.

La tabla de etiquetas tenía cuatro estados: confirmado, cancelado, entregado
y en camino. Todos los demás llamaban igual a `notificar_cambio_pedido_push`
y se iban en silencio, porque sin etiqueta el mensaje no se arma.

Los que faltaban eran justo los que le piden algo al cliente —aprobar una
fecha, subir el comprobante— o sea los únicos por los que el pedido se queda
quieto esperándolo a él. Sin push, se enteraba al abrir la app.
"""
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.shared.services.fcm_service import _LABELS_ESTADO_CLIENTE as ETIQUETAS
from src.features.ventas.pedidos.services.estados import (
    EstadoPedido, ESTADOS_ACTIVOS,
)


class EtiquetasDelPushTest(unittest.TestCase):
    def test_todo_estado_activo_se_puede_avisar(self):
        # Si el servidor gana un estado nuevo y nadie agrega su etiqueta, el
        # push se va en silencio. Esta prueba lo dice antes.
        faltan = sorted(e for e in ESTADOS_ACTIVOS if e not in ETIQUETAS)
        self.assertEqual(faltan, [], f"estados sin etiqueta de push: {faltan}")

    def test_los_finales_tambien(self):
        self.assertIn(EstadoPedido.ENTREGADO, ETIQUETAS)
        self.assertIn(EstadoPedido.CANCELADO, ETIQUETAS)

    def test_los_que_le_piden_algo_al_cliente(self):
        # Son los que más importan: el pedido no avanza hasta que él haga algo.
        for estado in (EstadoPedido.FECHA_PROPUESTA, EstadoPedido.ESPERANDO_PAGO):
            with self.subTest(estado=estado):
                self.assertIn(estado, ETIQUETAS)

    def test_listo_avisa_que_ya_se_puede_recoger(self):
        cuerpo, etiqueta = ETIQUETAS[EstadoPedido.LISTO]
        self.assertIn("listo", cuerpo.lower())
        self.assertIn("Listo", etiqueta)

    def test_esperando_pago_habla_de_plata(self):
        cuerpo, _ = ETIQUETAS[EstadoPedido.ESPERANDO_PAGO]
        self.assertIn("pago", cuerpo.lower())

    def test_cada_entrada_trae_las_dos_partes(self):
        # (cuerpo del push, etiqueta corta que viaja en `data`). Una vacía
        # dejaría una notificación sin texto.
        for estado, valor in ETIQUETAS.items():
            with self.subTest(estado=estado):
                self.assertEqual(len(valor), 2)
                cuerpo, etiqueta = valor
                self.assertTrue(cuerpo.strip(), f"estado {estado} sin cuerpo")
                self.assertTrue(etiqueta.strip(), f"estado {estado} sin etiqueta")


class SinFirebaseTest(unittest.TestCase):
    """Sin credenciales configuradas no se rompe nada: no se manda y se anota.

    Es el caso real cuando falta `FIREBASE_CREDENTIALS_JSON` en el servidor, y
    antes no dejaba ningún rastro: el push no llegaba, nada fallaba, y no
    había forma de saber por qué.
    """

    def test_no_revienta_y_avisa_en_el_log(self):
        try:
            import firebase_admin  # noqa: F401
        except ImportError:
            self.skipTest("firebase-admin no está instalado en este equipo")
        from src.shared.services import fcm_service

        with self.assertLogs("src.shared.services.fcm_service", level="WARNING") as log:
            fcm_service.notificar_cambio_pedido_push(
                id_usuario_cliente=1,
                id_venta=42,
                nuevo_estado=EstadoPedido.LISTO,
                db=None,
            )
        self.assertTrue(
            any("FIREBASE_CREDENTIALS_JSON" in linea for linea in log.output),
            log.output,
        )


if __name__ == "__main__":
    unittest.main()
