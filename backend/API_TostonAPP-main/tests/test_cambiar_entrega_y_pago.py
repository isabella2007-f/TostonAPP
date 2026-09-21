# -*- coding: utf-8 -*-
"""Cambiar cómo se paga y cómo se entrega un pedido.

Dos cosas que se reportaron desde la app:

- Al pasar de transferencia a efectivo, el comprobante de la transferencia
  quedaba guardado en el pedido. El método ya no lleva transferencia: esa
  imagen respalda un pago que no existe, y el panel la sigue mostrando como
  si hubiera algo que aprobar.
- No se podía cambiar el tipo de entrega.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_BARRIO

from src.shared.services.models import Venta, Domicilio
from src.features.ventas.gestion_ventas.services.service import _now


class CambiarPagoTest(PanelBase):
    def _pedido_por_transferencia(self):
        pedido = self.crear_pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://ejemplo/comprobante.jpg",
        )
        return pedido["ID_Venta"]

    def test_pasar_a_efectivo_borra_el_comprobante_cliente(self):
        id_venta = self._pedido_por_transferencia()
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/editar-mi-pedido", self.cliente,
            {"Metodo_Pago": "Efectivo"}))

        pago = self.pago(id_venta, "anticipo")
        self.assertIsNone(
            pago.Comprobante_Url if pago else None,
            "el comprobante respalda un pago que ya no existe",
        )

    def test_pasar_a_efectivo_borra_el_comprobante_admin(self):
        id_venta = self._pedido_por_transferencia()
        self.afirmar_ok(self.put(
            f"/pedidos/{id_venta}", self.admin, {"Metodo_Pago": "Efectivo"}))

        pago = self.pago(id_venta, "anticipo")
        self.assertIsNone(pago.Comprobante_Url if pago else None)

    def test_seguir_en_transferencia_lo_conserva(self):
        # Cambiar otra cosa no puede llevarse el comprobante por delante.
        id_venta = self._pedido_por_transferencia()
        self.afirmar_ok(self.put(
            f"/pedidos/{id_venta}", self.admin, {"Notas": "Llamar antes"}))
        pago = self.pago(id_venta, "anticipo")
        self.assertIsNotNone(pago.Comprobante_Url if pago else None)


class CambiarEntregaTest(PanelBase):
    def _pedido_fuera_de_ventana(self, **kw):
        pedido = self.crear_pedido(**kw)
        id_venta = pedido["ID_Venta"]
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=30)
        self.db.commit()
        return id_venta

    def test_el_cliente_pasa_de_recoger_a_domicilio(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        total_antes = float(self.venta(id_venta).Total)

        r = self.patch(
            f"/pedidos/{id_venta}/editar-mi-pedido", self.cliente,
            {"quiere_domicilio": True, "ID_Barrio": ID_BARRIO,
             "Direccion_Entrega": "Cl 10 #20-30"})
        self.assertEqual(r.status_code, 200, self.detalle(r))

        dom = self.domicilio(id_venta)
        self.assertIsNotNone(dom, "debería haberse creado el domicilio")
        self.assertGreater(float(self.venta(id_venta).Total), total_antes,
                           "el domicilio se cobra")

    def test_el_cliente_pasa_de_domicilio_a_recoger(self):
        id_venta = self.crear_pedido(domicilio=self.direccion())["ID_Venta"]
        total_antes = float(self.venta(id_venta).Total)

        r = self.patch(
            f"/pedidos/{id_venta}/editar-mi-pedido", self.cliente,
            {"quiere_domicilio": False})
        self.assertEqual(r.status_code, 200, self.detalle(r))
        self.assertLess(float(self.venta(id_venta).Total), total_antes,
                        "se devuelve el costo del domicilio")

    def test_el_panel_pasa_de_recoger_a_domicilio(self):
        id_venta = self._pedido_fuera_de_ventana()
        r = self.put(f"/pedidos/{id_venta}", self.admin,
                     {"Domicilio": True, "ID_Barrio": ID_BARRIO,
                      "Direccion_Entrega": "Cl 10 #20-30"})
        self.assertEqual(r.status_code, 200, self.detalle(r))
        self.assertIsNotNone(self.domicilio(id_venta))

    def test_el_panel_pasa_de_domicilio_a_recoger(self):
        id_venta = self._pedido_fuera_de_ventana(domicilio=self.direccion())
        r = self.put(f"/pedidos/{id_venta}", self.admin, {"Domicilio": False})
        self.assertEqual(r.status_code, 200, self.detalle(r))
        self.assertIsNone(
            self.db.query(Domicilio).filter(
                Domicilio.ID_Venta == id_venta).first())


class CostoDomicilioEnLaRespuestaTest(PanelBase):
    def test_el_detalle_dice_cuanto_cuesta_el_domicilio(self):
        # La app lo lee de `costo_domicilio_total`; si el esquema no lo
        # declara, Pydantic lo descarta y el detalle muestra $0.
        pedido = self.crear_pedido(domicilio=self.direccion())
        detalle = self.afirmar_ok(
            self.get(f"/pedidos/{pedido['ID_Venta']}", self.admin))
        self.assertIn("costo_domicilio_total", detalle)
        self.assertGreater(detalle["costo_domicilio_total"], 0)


if __name__ == "__main__":
    unittest.main()
