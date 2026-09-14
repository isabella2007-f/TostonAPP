# -*- coding: utf-8 -*-
"""Los 10 minutos que el pedido es del cliente.

Recién hecho el pedido, el cliente puede arrepentirse: cancelarlo o
corregirlo sin pedirle permiso a nadie. Pasados 10 minutos el pedido pasa a
ser de la panadería y hay que escribir.

La ventana se medía restándole a `datetime.utcnow()` una fecha guardada en
hora de Bogotá (UTC-5). O sea que un pedido recién creado nacía con cinco
horas de antigüedad: la ventana estaba vencida siempre y el cliente no podía
cancelar nunca, ni un segundo después de hacer el pedido.
"""
import unittest
from datetime import datetime, timedelta

from panel import PanelBase

from src.features.ventas.pedidos.services.service import (
    _dentro_ventana_edicion, _VENTANA_EDICION,
)
from src.features.ventas.gestion_ventas.services.service import _now


class _Venta:
    """Lo único que mira la ventana: cuándo se creó."""

    def __init__(self, fecha):
        self.Fecha_Venta = fecha


class VentanaEdicionTest(unittest.TestCase):
    def test_un_pedido_recien_creado_esta_dentro(self):
        # Es el caso de todos los días: el cliente confirma y a los diez
        # segundos se da cuenta de que pidió mal.
        self.assertTrue(_dentro_ventana_edicion(_Venta(_now())))

    def test_a_los_nueve_minutos_todavia(self):
        self.assertTrue(
            _dentro_ventana_edicion(_Venta(_now() - timedelta(minutes=9)))
        )

    def test_a_los_once_minutos_ya_no(self):
        self.assertFalse(
            _dentro_ventana_edicion(_Venta(_now() - timedelta(minutes=11)))
        )

    def test_sin_fecha_no_hay_ventana(self):
        self.assertFalse(_dentro_ventana_edicion(_Venta(None)))

    def test_no_se_mide_contra_utc(self):
        # La raíz del problema: `Fecha_Venta` se escribe con `_now()` (hora de
        # Bogotá, sin zona) y la ventana la comparaba contra `utcnow()`, cinco
        # horas más adelante. Con esa resta, un pedido de hace un minuto daba
        # 5:01 de antigüedad.
        recien = _now()
        self.assertGreater(
            (datetime.utcnow() - recien).total_seconds(),
            _VENTANA_EDICION.total_seconds(),
            "si esto deja de ser cierto, el servidor cambió de zona horaria",
        )
        # Y aun así, medido bien, el pedido está dentro.
        self.assertTrue(_dentro_ventana_edicion(_Venta(recien)))


class CancelarMiPedidoTest(PanelBase):
    """El cliente cancelando su propio pedido, por la API."""

    def test_puede_cancelar_recien_hecho(self):
        # Un pedido con producción: queda Pendiente de Aprobación, que es
        # donde el cliente todavía manda sobre su pedido.
        pedido = self.pedido_con_faltante()
        r = self.patch(
            f"/pedidos/{pedido['ID_Venta']}/cancelar-mi-pedido", self.cliente
        )
        self.assertEqual(r.status_code, 200, self.detalle(r))
        self.assertEqual(r.json()["Estado"], 5)

    def test_el_pedido_de_otro_no(self):
        pedido = self.pedido_con_faltante()
        r = self.patch(
            f"/pedidos/{pedido['ID_Venta']}/cancelar-mi-pedido", self.admin
        )
        # El admin no cancela por esta puerta: tiene la suya.
        self.assertIn(r.status_code, (400, 403), self.detalle(r))


if __name__ == "__main__":
    unittest.main()
