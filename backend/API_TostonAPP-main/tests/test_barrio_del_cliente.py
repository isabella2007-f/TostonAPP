# -*- coding: utf-8 -*-
"""El barrio del cliente tiene que viajar en la lista de clientes.

Cuando el personal arma un pedido a nombre de alguien, elige al cliente y la
pantalla debería traer sola su dirección guardada: el barrio —que es de donde
sale el precio del domicilio— y las indicaciones para llegar.

No llegaban. `ClienteResponse` no declaraba `ID_Barrio`, y Pydantic descarta
en silencio todo lo que no esté en el esquema: el campo salía del servidor y
se perdía antes de llegar a la app. El resultado era que el panel pedía
"elige el barrio de entrega" por un cliente que ya tenía el suyo guardado.
"""
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_CLIENTE, ID_BARRIO


class BarrioDelClienteTest(PanelBase):
    def setUp(self):
        super().setUp()
        # El cliente del arnés nace sin barrio; acá se le pone uno porque es
        # justo lo que se está probando: que viaje hasta la app.
        from src.shared.services.models import Usuario
        u = self.db.query(Usuario).filter(
            Usuario.ID_Usuario == ID_CLIENTE).first()
        u.ID_Barrio = ID_BARRIO
        self.db.commit()

    def _cliente(self, datos):
        for c in datos["clientes"]:
            if c["ID_Usuario"] == ID_CLIENTE:
                return c
        self.fail("el cliente de prueba no salió en la lista")

    def test_la_lista_trae_el_barrio(self):
        datos = self.afirmar_ok(self.get("/clientes/", self.admin))
        cliente = self._cliente(datos)
        self.assertIn("ID_Barrio", cliente,
                      "sin esto el panel pide el barrio de un cliente que ya lo tiene")
        self.assertEqual(cliente["ID_Barrio"], ID_BARRIO)

    def test_tambien_las_indicaciones_para_llegar(self):
        # Son las del perfil del cliente: cómo llegar a su casa. Si no viajan,
        # el domiciliario sale sin ellas cuando el pedido lo arma el personal.
        datos = self.afirmar_ok(self.get("/clientes/", self.admin))
        self.assertIn("Indicaciones", self._cliente(datos))

    def test_el_detalle_de_un_cliente_también(self):
        cliente = self.afirmar_ok(self.get(f"/clientes/{ID_CLIENTE}", self.admin))
        self.assertEqual(cliente["ID_Barrio"], ID_BARRIO)

    def test_un_cliente_sin_barrio_no_rompe(self):
        # El campo es opcional: hay clientes viejos que nunca lo llenaron.
        from src.shared.services.models import Usuario

        u = self.db.query(Usuario).filter(Usuario.ID_Usuario == ID_CLIENTE).first()
        u.ID_Barrio = None
        self.db.commit()

        datos = self.afirmar_ok(self.get("/clientes/", self.admin))
        self.assertIsNone(self._cliente(datos)["ID_Barrio"])


if __name__ == "__main__":
    unittest.main()
