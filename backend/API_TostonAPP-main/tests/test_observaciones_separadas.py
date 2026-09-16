# -*- coding: utf-8 -*-
"""Las observaciones de una entrega: una por autor, sin pisarse.

`Domicilios.Observaciones` lo escribían tres manos distintas:

- el cliente, al pedir (el complemento de la dirección y cómo llegar),
- el administrador, al editar el pedido,
- el domiciliario, al dejar una novedad en la entrega.

El que escribía último se llevaba lo anterior. El caso caro: el domiciliario
anota "no había nadie" y borra el "apartamento 302, portón verde" que había
puesto el cliente — justo el dato que necesita el que va mañana.

Ahora cada uno tiene su columna y las tres viajan juntas en la respuesta.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_REPARTIDOR

from src.shared.services.models import Venta, Domicilio
from src.features.ventas.gestion_ventas.services.service import _now

DOM_EN_CAMINO = 9


class ObservacionesSeparadasTest(PanelBase):
    def _pedido_con_domicilio(self):
        """Un pedido con domicilio, ya fuera de la ventana de edición.

        La ventana de 10 minutos bloquea los cambios de estado, y acá lo que
        se prueba es qué pasa cuando el domiciliario escribe.
        """
        pedido = self.crear_pedido(
            domicilio=self.direccion(Observaciones="Apto 302, portón verde"))
        id_venta = pedido["ID_Venta"]
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=30)
        self.db.commit()
        return id_venta

    def test_la_novedad_del_domiciliario_no_borra_la_del_cliente(self):
        id_venta = self._pedido_con_domicilio()
        self.confirmar_si_pendiente(id_venta)
        dom = self.domicilio(id_venta)

        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/repartidor",
            self.admin, {"ID_Empleado": ID_REPARTIDOR}))
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/estado", self.admin,
            {"Estado": DOM_EN_CAMINO, "Observaciones": "No había nadie"}))

        guardado = self.db.query(Domicilio).filter(
            Domicilio.ID_Domicilio == dom.ID_Domicilio).first()
        self.db.refresh(guardado)
        self.assertEqual(guardado.Observaciones_Repartidor, "No había nadie")
        self.assertIn("portón verde", guardado.Observaciones or "",
                      "la del cliente tiene que seguir ahí")

    def test_la_nota_del_admin_tampoco(self):
        id_venta = self._pedido_con_domicilio()
        # `Domicilio: true` es lo que hace entrar al bloque del domicilio en
        # `editar_pedido`; sin eso la nota no llega a ninguna parte.
        self.afirmar_ok(self.put(
            f"/pedidos/{id_venta}", self.admin,
            {"Domicilio": True, "Notas": "Cliente pidió llamarlo antes"}))

        dom = self.domicilio(id_venta)
        self.db.refresh(dom)
        self.assertEqual(dom.Observaciones_Admin, "Cliente pidió llamarlo antes")
        self.assertIn("portón verde", dom.Observaciones or "")

    def test_las_tres_viajan_en_el_detalle_del_domicilio(self):
        id_venta = self._pedido_con_domicilio()
        dom = self.domicilio(id_venta)
        datos = self.afirmar_ok(
            self.get(f"/domicilios/{dom.ID_Domicilio}", self.admin))
        for campo in ("Observaciones", "observaciones_admin",
                      "observaciones_repartidor", "indicaciones_cliente"):
            self.assertIn(campo, datos, campo)

    def test_y_en_el_detalle_del_pedido(self):
        # Es donde las mira el administrador, sin abrir el domicilio.
        id_venta = self._pedido_con_domicilio()
        datos = self.afirmar_ok(self.get(f"/pedidos/{id_venta}", self.admin))
        for campo in ("observaciones_domicilio", "observaciones_admin",
                      "observaciones_repartidor"):
            self.assertIn(campo, datos, campo)


if __name__ == "__main__":
    unittest.main()
