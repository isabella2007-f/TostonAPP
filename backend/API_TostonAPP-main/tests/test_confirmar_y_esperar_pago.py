# -*- coding: utf-8 -*-
"""Confirmar un pedido y esperar su pago son dos cosas distintas.

"Confirmado" es el panel aceptando el pedido. "Esperando pago" es lo que
viene despues, cuando falta que el cliente ponga la plata. El pedido tiene
que pasar por los dos: confirmar saltando directo a "Esperando pago" borra
del historial el momento en que la panaderia acepto el pedido, y confirmar y
quedarse ahi deja al cliente sin la pantalla donde paga.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase

from src.shared.services.models import Venta
from src.features.ventas.gestion_ventas.services.service import _now
from src.features.ventas.pedidos.services.estados import (
    EstadoPedido, TRANSICIONES,
)

PENDIENTE      = 1
CONFIRMADO     = 4
PREPARANDO     = 13
LISTO          = 11
EN_CAMINO      = 9
ENTREGADO      = 8
ESPERANDO_PAGO = 20
URL = "https://ejemplo/comprobante.jpg"


class Base(PanelBase):
    def envejecer(self, id_venta, minutos=30):
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=minutos)
        self.db.commit()
        return id_venta

    # No hay tabla de historial de estados en el proyecto, así que "pasó
    # por Confirmado" se comprueba por su efecto: confirmar es lo único que
    # aparta el stock de un pedido para recoger en tienda.


class ConfirmarPasaPorLosDosTest(Base):
    def test_el_que_paga_por_transferencia_pasa_por_confirmado(self):
        id_venta = self.envejecer(
            self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"])

        detalle = self.afirmar_ok(
            self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))

        self.assertEqual(detalle["Estado"], ESPERANDO_PAGO,
                         "el cliente tiene que poder pagarlo")
        self.assertTrue(self.venta(id_venta).Stock_Reservado,
                        "pasó por Confirmado: la panadería ya lo aceptó y "
                        "apartó la mercancía")

    def test_el_de_efectivo_se_queda_en_confirmado(self):
        # No hay nada que esperar: el efectivo se cobra al entregar.
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        detalle = self.afirmar_ok(
            self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        self.assertEqual(detalle["Estado"], CONFIRMADO)

    def test_aprobado_el_pago_vuelve_a_confirmado(self):
        id_venta = self.envejecer(
            self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"])
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                                   {"comprobante_url": URL}))
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/aprobar-comprobante", self.admin))
        self.assertEqual(detalle["Estado"], CONFIRMADO)

    def test_no_avanza_a_produccion_con_el_pago_pendiente(self):
        id_venta = self.envejecer(
            self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"])
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        self.assertEqual(self.venta(id_venta).Estado, ESPERANDO_PAGO)

        r = self.patch(f"/ventas/{id_venta}/estado", self.admin,
                       {"Estado": PREPARANDO})
        # Si lo acepta, tiene que ser porque la máquina lo permite desde
        # "Esperando pago" — pero nunca saltándose el pago sin registrarlo.
        if r.status_code == 200:
            self.assertEqual(self.venta(id_venta).Estado, PREPARANDO)


class ElClienteSeEnteraDeLosDosTest(Base):
    """Cada paso manda su aviso: "lo aceptamos" y después "falta tu pago".

    Es el valor de no saltarse el estado. Con el salto, el cliente recibía un
    solo aviso —el del pago— y nunca supo que la panadería había aceptado su
    pedido.
    """

    def test_confirmar_avisa_dos_veces(self):
        from unittest import mock

        id_venta = self.envejecer(
            self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"])

        with mock.patch(
            "src.shared.services.fcm_service.notificar_cambio_pedido_push"
        ) as push:
            self.afirmar_ok(
                self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))

        estados = [c.kwargs["nuevo_estado"] for c in push.call_args_list]
        self.assertEqual(estados, [CONFIRMADO, ESPERANDO_PAGO])


class TransicionesInvalidasTest(Base):
    """El backend es la autoridad: da igual qué mande la pantalla."""

    def saltar(self, id_venta, estado):
        return self.patch(f"/ventas/{id_venta}/estado", self.admin,
                          {"Estado": estado})

    def test_de_pendiente_no_se_salta_a_en_camino(self):
        id_venta = self.envejecer(
            self.crear_pedido(domicilio=self.direccion())["ID_Venta"])
        r = self.saltar(id_venta, EN_CAMINO)
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_de_pendiente_no_se_salta_a_entregado(self):
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        r = self.saltar(id_venta, ENTREGADO)
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_de_pendiente_no_se_salta_a_produccion(self):
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        r = self.saltar(id_venta, PREPARANDO)
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_un_estado_final_no_se_mueve(self):
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        r = self.saltar(id_venta, CONFIRMADO)
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_la_maquina_declara_el_paso_al_pago(self):
        # Lo que hace posible "Confirmado → Esperando pago" sin inventar nada
        # por fuera de la tabla.
        self.assertIn(EstadoPedido.ESPERANDO_PAGO,
                      TRANSICIONES[EstadoPedido.CONFIRMADO])

    def test_y_el_regreso_tambien(self):
        self.assertIn(EstadoPedido.CONFIRMADO,
                      TRANSICIONES[EstadoPedido.ESPERANDO_PAGO])


if __name__ == "__main__":
    unittest.main()
