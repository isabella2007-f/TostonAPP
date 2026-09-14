"""Un pedido con anticipo no se entrega con el saldo sin pagar.

El anticipo es la mitad: cubre los insumos, no el pedido. Entregar con solo
esa mitad registrada es despachar la mercancía y quedarse esperando el resto,
que es justo lo que el anticipo existe para evitar.
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from panel import *  # noqa: F401,F403
from panel import (
    DOM_EN_CAMINO, DOM_ENTREGADO, ID_REPARTIDOR, PEDIDO_LISTO, PanelBase,
)


class EntregaConAnticipoTests(PanelBase):
    def pedido_con_anticipo_en_camino(self, metodo="Transferencia"):
        """Pedido que exige anticipo, con el anticipo cobrado y en la calle."""
        # Por encima del umbral del anticipo ($100.000): por debajo el pedido
        # no lo pide y la prueba no ejercería nada. Y aprobado por el admin,
        # que es cuando se exige el anticipo en el flujo nuevo: al crearlo
        # todavía no existe.
        pedido = self.pedido_con_faltante_aprobado(
            cantidad=12, domicilio=self.direccion(), metodo_pago=metodo)
        id_venta = pedido["ID_Venta"]
        venta = self.venta(id_venta)
        self.assertTrue(
            Decimal(str(venta.Anticipo_Requerido or 0)) > 0,
            "el pedido tiene que exigir anticipo")
        # El cliente manda el comprobante del anticipo y el admin lo aprueba:
        # recién ahí se abre la producción. El saldo sigue debiéndose.
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": "https://cloudinary.test/anticipo.jpg",
             "monto": float(venta.Anticipo_Requerido)}))
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/aprobar-comprobante", self.admin))
        venta = self.venta(id_venta)
        venta.Anticipo_Monto      = venta.Anticipo_Requerido
        venta.Anticipo_Registrado = 1
        venta.Pago_Final_Registrado = 0
        venta.Estado_Pago         = "anticipo_pagado"
        self.db.commit()

        # `hornear` deja el pedido listo para salir.
        self.hornear(id_venta)
        dom = self.domicilio(id_venta)
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/repartidor", self.admin,
            {"ID_Empleado": ID_REPARTIDOR}))
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/estado", self.repartidor,
            {"Estado": DOM_EN_CAMINO}))
        return id_venta, dom.ID_Domicilio

    def test_con_solo_el_anticipo_no_se_entrega(self):
        _, id_dom = self.pedido_con_anticipo_en_camino()
        respuesta = self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO})
        self.assertEqual(
            respuesta.status_code, 400,
            "se entregó un pedido con la mitad del dinero sin cobrar")
        self.assertIn("saldo", self.detalle(respuesta).lower())

    def test_con_el_saldo_pagado_sí_se_entrega(self):
        id_venta, id_dom = self.pedido_con_anticipo_en_camino()
        venta = self.venta(id_venta)
        venta.Pago_Final_Registrado = 1
        venta.Estado_Pago = "pagado_completo"
        self.db.commit()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO}))

    def test_un_pedido_sin_anticipo_no_cambia(self):
        # La regla nueva no puede trabar los pedidos normales, que son la
        # mayoría: ahí "pagado_completo" basta como siempre.
        pedido = self.crear_pedido(domicilio=self.direccion(),
                                   metodo_pago="Transferencia")
        id_venta = pedido["ID_Venta"]
        venta = self.venta(id_venta)
        venta.Estado_Pago = "pagado_completo"
        self.db.commit()
        self.confirmar_si_pendiente(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_LISTO}))
        dom = self.domicilio(id_venta)
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/repartidor", self.admin,
            {"ID_Empleado": ID_REPARTIDOR}))
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/estado", self.repartidor,
            {"Estado": DOM_EN_CAMINO}))
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO}))


if __name__ == "__main__":
    unittest.main()
