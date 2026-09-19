# -*- coding: utf-8 -*-
"""Despues de subir el comprobante, el pedido tiene que dejar de pedirlo.

Reportado desde la app: el cliente sube el comprobante, la imagen queda
guardada y se ve en el detalle, pero la pantalla sigue diciendo que falta el
pago. La app decide ese texto con `estado_pago` y explica el rechazo con
`motivo_rechazo_comprobante`: lo que se prueba aca es que los dos lleguen al
detalle que la app consulta (`/ventas/mis-ventas/{id}`), que es otro modulo
-y otro esquema- que el que atiende el POST del comprobante.
"""
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase

URL = "https://ejemplo/comprobante.jpg"


class ComprobanteYaEnviadoTest(PanelBase):
    def _pedido_esperando_pago(self):
        # El camino completo: el pedido nace PENDIENTE y llega a "Esperando
        # pago" cuando el panel lo acepta, no al crearlo.
        id_venta = self.pedido_esperando_pago()
        self.assertEqual(self.venta(id_venta).Estado, 20)
        return id_venta

    def _detalle_del_cliente(self, id_venta):
        return self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{id_venta}", self.cliente))

    def test_el_detalle_dice_que_esta_en_revision(self):
        id_venta = self._pedido_esperando_pago()
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                                   {"comprobante_url": URL}))

        detalle = self._detalle_del_cliente(id_venta)
        self.assertEqual(detalle.get("comprobante_pago"), URL)
        self.assertEqual(
            detalle.get("estado_pago"), "pendiente_validacion",
            "sin esto la app sigue pidiendo un comprobante que ya recibio")

    def test_el_detalle_trae_el_motivo_del_rechazo(self):
        id_venta = self._pedido_esperando_pago()
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                                   {"comprobante_url": URL}))
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/rechazar-comprobante", self.admin,
            {"motivo": "La captura no se ve"}))

        detalle = self._detalle_del_cliente(id_venta)
        self.assertEqual(detalle.get("estado_pago"), "comprobante_rechazado")
        self.assertEqual(
            detalle.get("motivo_rechazo_comprobante"), "La captura no se ve",
            "sin el motivo el cliente vuelve a mandar la misma captura")


if __name__ == "__main__":
    unittest.main()
