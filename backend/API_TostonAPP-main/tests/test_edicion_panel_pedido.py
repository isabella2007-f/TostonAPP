# -*- coding: utf-8 -*-
"""Lo que el panel puede cambiar de un pedido, y lo que no.

Editar un pedido es corregir COMO se paga y COMO se entrega. Todo lo demas
—el estado, los productos, el total— tiene su propio camino, con sus propias
validaciones: dejarlo entrar por el formulario de edicion es dejar que se
salte esas validaciones.
"""
import sys
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_BARRIO

from src.shared.services.models import Venta, DetalleVenta
from src.features.ventas.gestion_ventas.services.service import _now

CONFIRMADO = 4
EN_CAMINO = 9


class Base(PanelBase):
    def envejecer(self, id_venta, minutos=30):
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=minutos)
        self.db.commit()
        return id_venta

    def detalle_de(self, id_venta):
        return (self.db.query(DetalleVenta)
                .filter(DetalleVenta.ID_Venta == id_venta).first())


class ElTotalLoLlevaElServidorTest(Base):
    def test_el_formulario_no_puede_declarar_el_total(self):
        # El total sale de las líneas, el domicilio y lo que ya se descontó.
        # Aceptarlo del request es dejar que la pantalla cobre lo que quiera.
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        antes = Decimal(str(self.venta(id_venta).Total))

        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin,
                                 {"Total": 1}))
        self.assertEqual(Decimal(str(self.venta(id_venta).Total)), antes)

    def test_el_credito_aplicado_no_se_pisa(self):
        # `DetalleVenta.Descuento` guarda el CRÉDITO que el cliente usó, no un
        # descuento comercial. El formulario mandaba ahí su campo "Descuento"
        # y borraba el saldo a favor que el pedido ya había consumido.
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        detalle = self.detalle_de(id_venta)
        detalle.Descuento = Decimal("7000")
        self.db.commit()

        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin,
                                 {"Descuento": 0}))

        self.db.refresh(detalle)
        self.assertEqual(Decimal(str(detalle.Descuento)), Decimal("7000"))

    def test_el_domicilio_sigue_moviendo_el_total(self):
        # Lo que sí cambia el total desde acá: agregar o quitar el envío.
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        antes = Decimal(str(self.venta(id_venta).Total))

        self.afirmar_ok(self.put(
            f"/pedidos/{id_venta}", self.admin,
            {"Domicilio": True, "ID_Barrio": ID_BARRIO,
             "Direccion_Entrega": "Cl 10 #20-30"}))

        self.assertGreater(Decimal(str(self.venta(id_venta).Total)), antes)


class ElEstadoNoSeEditaTest(Base):
    def test_el_formulario_de_edicion_no_cambia_el_estado(self):
        # Los estados se mueven con sus acciones, que validan la transición.
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        r = self.put(f"/pedidos/{id_venta}", self.admin, {"Estado": EN_CAMINO})
        # El campo ni siquiera existe en el esquema: llega y se ignora.
        self.assertIn(r.status_code, (200, 422))
        self.assertNotEqual(self.venta(id_venta).Estado, EN_CAMINO)

    def test_ni_los_productos(self):
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        lineas_antes = len(self.lineas(id_venta))
        r = self.put(f"/pedidos/{id_venta}", self.admin,
                     {"productos": [{"ID_Producto": 1, "Cantidad": 99}]})
        self.assertIn(r.status_code, (200, 422))
        self.assertEqual(len(self.lineas(id_venta)), lineas_antes)
        self.assertEqual(self.lineas(id_venta)[0].Cantidad, 2)


if __name__ == "__main__":
    unittest.main()
