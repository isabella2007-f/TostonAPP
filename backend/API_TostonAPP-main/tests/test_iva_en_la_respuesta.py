# -*- coding: utf-8 -*-
"""El IVA discriminado tiene que llegar hasta la pantalla.

Los precios de venta ya incluyen el 19%, así que el impuesto se extrae del
total (`base = total / 1.19`) y se guarda en el pedido. El servicio lo
devolvía, pero `VentaResponse` y `PedidoResponse` no lo declaraban: Pydantic
descarta en silencio todo lo que no esté en el esquema, así que el valor
guardado no salía nunca y la web terminaba estimando el impuesto por su
cuenta.
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase

from src.features.ventas.gestion_ventas.services.service import _desglosar_iva


class DesgloseTest(unittest.TestCase):
    def test_base_mas_iva_da_el_total(self):
        # La cuenta no puede perder ni un peso por el redondeo.
        for total in ("100000.00", "23800.00", "0.01", "999999.99"):
            with self.subTest(total=total):
                base, iva = _desglosar_iva(Decimal(total))
                self.assertEqual(base + iva, Decimal(total))

    def test_el_iva_es_el_19_por_ciento_de_la_base(self):
        base, iva = _desglosar_iva(Decimal("119000.00"))
        self.assertEqual(base, Decimal("100000.00"))
        self.assertEqual(iva, Decimal("19000.00"))


class IvaEnLaRespuestaTest(PanelBase):
    def test_el_pedido_trae_el_iva_ya_calculado(self):
        pedido = self.crear_pedido()
        for campo in ("iva_total", "subtotal_base"):
            self.assertIn(campo, pedido, campo)
        self.assertIsNotNone(pedido["iva_total"])

    def test_y_cuadra_con_el_total(self):
        pedido = self.crear_pedido()
        total = Decimal(str(pedido["Total"]))
        base = Decimal(str(pedido["subtotal_base"]))
        iva = Decimal(str(pedido["iva_total"]))
        self.assertEqual(base + iva, total)

    def test_también_en_el_detalle(self):
        # Es donde lo mira el cliente y de donde sale la factura.
        pedido = self.crear_pedido()
        detalle = self.afirmar_ok(
            self.get(f"/pedidos/{pedido['ID_Venta']}", self.admin))
        self.assertIsNotNone(detalle.get("iva_total"))


if __name__ == "__main__":
    unittest.main()
