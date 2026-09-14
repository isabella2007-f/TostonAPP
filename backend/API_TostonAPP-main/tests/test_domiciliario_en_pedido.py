"""El pedido dice quién lo lleva.

En el panel salía "Sin asignar" en pedidos que ya iban en camino. El nombre y
el id del repartidor salen del domicilio, y el panel los lee de la respuesta
del pedido: si alguno no llega, la pantalla no tiene con qué mostrarlo.
"""
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from panel import *  # noqa: F401,F403
from panel import (
    DOM_EN_CAMINO, ID_REPARTIDOR, PEDIDO_LISTO, PanelBase,
)


class DomiciliarioEnPedidoTests(PanelBase):
    def pedido_en_camino(self):
        """Un pedido con domicilio, repartidor asignado y en la calle."""
        pedido = self.crear_pedido(domicilio=self.direccion())
        id_venta = pedido["ID_Venta"]
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
        return id_venta

    def venta_api(self, id_venta):
        """El pedido como lo devuelve la API.

        Se llama distinto del `venta()` del harness, que devuelve la fila de la
        base: con el mismo nombre lo tapaba y los ayudantes compartidos
        recibían un dict donde esperaban un modelo.
        """
        return self.afirmar_ok(self.get(f"/ventas/{id_venta}", self.admin))

    def test_el_detalle_trae_el_nombre_del_domiciliario(self):
        cuerpo = self.venta_api(self.pedido_en_camino())
        self.assertTrue(
            cuerpo.get("nombre_domiciliario"),
            "sin el nombre, el panel escribe 'Sin asignar' en un pedido que "
            "ya va en camino")

    def test_el_detalle_trae_el_id_del_repartidor(self):
        # Es el respaldo del panel cuando el nombre no viene: sin él, la única
        # forma de resolverlo contra la lista de empleados queda muerta.
        cuerpo = self.venta_api(self.pedido_en_camino())
        self.assertEqual(cuerpo.get("ID_Empleado"), ID_REPARTIDOR)

    def test_el_listado_tambien(self):
        # La tabla de pedidos lee de acá, no del detalle.
        id_venta = self.pedido_en_camino()
        cuerpo = self.afirmar_ok(
            self.get("/ventas/?por_pagina=100", self.admin))
        fila = next(v for v in cuerpo["ventas"] if v["ID_Venta"] == id_venta)
        self.assertTrue(fila.get("nombre_domiciliario"))
        self.assertEqual(fila.get("ID_Empleado"), ID_REPARTIDOR)

    def test_sin_repartidor_sigue_diciendo_que_no_hay(self):
        # "Sin asignar" tiene que seguir siendo posible: es cierto hasta que
        # alguien lo toma.
        pedido = self.crear_pedido(domicilio=self.direccion())
        cuerpo = self.venta_api(pedido["ID_Venta"])
        self.assertIsNone(cuerpo.get("nombre_domiciliario"))
        self.assertIsNone(cuerpo.get("ID_Empleado"))


if __name__ == "__main__":
    unittest.main()
