# -*- coding: utf-8 -*-
"""Aprobar la fecha de un encargo: cuando se puede y que pasa despues.

Aprobar la fecha abre la orden de produccion y reserva insumos. Hacerlo
mientras el cliente todavia puede editar su pedido deja las dos cosas
peleadas: la orden ya existe para unas cantidades y una fecha que el cliente
puede cambiar en el minuto siguiente.

Y despues de aprobarla falta cobrar: un encargo se paga por transferencia,
asi que el pedido tiene que quedar esperando ese pago antes de producir.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase

from src.shared.services.models import Venta, OrdenProduccion
from src.features.ventas.gestion_ventas.services.service import _now

PENDIENTE      = 1
PREPARANDO     = 13
LISTO          = 11
ESPERANDO_PAGO = 20
URL = "https://ejemplo/comprobante.jpg"


class Base(PanelBase):
    def envejecer(self, id_venta, minutos=30):
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=minutos)
        self.db.commit()
        return id_venta

    def encargo(self, cantidad=6):
        """Sobre stock, por transferencia. $60.000: no llega al umbral del
        anticipo, asi que el pago es del total."""
        return self.pedido_con_faltante(
            cantidad=cantidad, Metodo_Pago="Transferencia")["ID_Venta"]

    def ordenes(self, id_venta):
        return (self.db.query(OrdenProduccion)
                .filter(OrdenProduccion.ID_Venta == id_venta).all())


class NoSeApruebaEnLaVentanaTest(Base):
    def test_el_panel_espera_a_que_cierre_el_plazo(self):
        # Si se aprueba antes, la orden de produccion nace para unas
        # cantidades y una fecha que el cliente todavia puede cambiar.
        id_venta = self.encargo()
        r = self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin)
        self.assertEqual(r.status_code, 400, self.detalle(r))
        self.assertIn("edición del cliente", self.detalle(r))

    def test_y_no_deja_ninguna_orden_abierta(self):
        id_venta = self.encargo()
        self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin)
        self.assertEqual(self.ordenes(id_venta), [])
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)

    def test_pasado_el_plazo_si(self):
        id_venta = self.envejecer(self.encargo())
        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin))

    def test_proponer_otra_fecha_si_se_puede_de_una(self):
        # Contraofertar no abre nada: es una pregunta al cliente.
        id_venta = self.encargo()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin,
            {"fecha_entrega": (_now() + timedelta(days=5)).isoformat()}))


class DespuesDeLaFechaFaltaPagarTest(Base):
    def test_el_encargo_queda_esperando_el_pago(self):
        # Se paga por transferencia y todavia no pago nada: no puede entrar a
        # produccion sin respaldo. Antes solo esperaba pago si superaba los
        # $100.000; por debajo se iba derecho a producir y a nadie se le
        # pedia el comprobante.
        id_venta = self.envejecer(self.encargo())
        detalle = self.afirmar_ok(
            self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin))
        self.assertEqual(detalle["Estado"], ESPERANDO_PAGO)

    def test_y_ahi_el_cliente_sube_el_comprobante(self):
        id_venta = self.envejecer(self.encargo())
        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin))
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL}))
        self.assertEqual(detalle["comprobante_pago"], URL)
        self.assertEqual(detalle["estado_pago"], "pendiente_validacion")

    def test_aprobado_el_pago_entra_a_produccion(self):
        id_venta = self.envejecer(self.encargo())
        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin))
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                                   {"comprobante_url": URL}))
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/aprobar-comprobante", self.admin))
        self.assertIn(detalle["Estado"], (PREPARANDO, LISTO))
        self.assertTrue(self.ordenes(id_venta), "la orden se abre al pagar")

    def test_el_grande_sigue_pidiendo_el_anticipo(self):
        # 11 tortas = $110.000: pasa el umbral, y ahi lo que se pide es el 50%.
        id_venta = self.envejecer(self.encargo(cantidad=11))
        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aprobar-fecha", self.admin))
        venta = self.venta(id_venta)
        self.assertEqual(venta.Estado, ESPERANDO_PAGO)
        self.assertTrue(venta.Requiere_Anticipo)


if __name__ == "__main__":
    unittest.main()
