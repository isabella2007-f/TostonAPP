# -*- coding: utf-8 -*-
"""Los dos flujos, separados: el pedido normal y el programado.

- NORMAL (hay stock, no hay que hornear): Pendiente → 10 minutos del cliente
  → el panel lo confirma → Esperando pago → paga.
- PROGRAMADO (sobre stock): Pendiente → 10 minutos → se acuerda la fecha →
  recien ahi se habilita el pago, siempre por transferencia, 50% o 100%.

Lo que se prueba aca es que el servidor no deje saltarse ninguno de esos
pasos, aunque la pantalla lo intente.
"""
import sys
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_BARRIO, ID_CLIENTE, ID_TORTA

from src.shared.services.models import Venta, Usuario
from src.features.ventas.gestion_ventas.services.service import _now

PENDIENTE       = 1
CONFIRMADO      = 4
FECHA_PROPUESTA = 16
ESPERANDO_PAGO  = 20
URL = "https://ejemplo/comprobante.jpg"


class Base(PanelBase):
    def setUp(self):
        super().setUp()
        cliente = self.db.query(Usuario).filter(
            Usuario.ID_Usuario == ID_CLIENTE).first()
        cliente.ID_Barrio = ID_BARRIO
        self.db.commit()

    def envejecer(self, id_venta, minutos=30):
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=minutos)
        self.db.commit()
        return id_venta

    def editar(self, id_venta, cuerpo):
        return self.patch(f"/pedidos/{id_venta}/editar-mi-pedido",
                          self.cliente, cuerpo)

    def programado(self, cantidad=11, **kw):
        """Sobre stock y por encima del umbral: pide anticipo del 50%."""
        cuerpo = dict(cantidad=cantidad, Metodo_Pago="Transferencia")
        cuerpo.update(kw)
        return self.pedido_con_faltante(**cuerpo)["ID_Venta"]


# ══════════════════════════════════════════════════════════════════════
# 1. El pedido normal no se adelanta a "Esperando pago"
# ══════════════════════════════════════════════════════════════════════
class PedidoNormalTest(Base):
    def test_por_transferencia_tambien_nace_pendiente(self):
        # Nacia directo en "Esperando pago": la app le pedia el comprobante
        # de un pedido que el panel todavia no habia aceptado, y el cliente
        # perdia su ventana de edicion.
        id_venta = self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"]
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)

    def test_en_efectivo_igual(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)

    def test_todavia_no_se_puede_pagar(self):
        id_venta = self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"]
        r = self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                       {"comprobante_url": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_confirmado_por_el_panel_pasa_a_esperar_el_pago(self):
        id_venta = self.envejecer(
            self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"])
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        self.assertEqual(self.venta(id_venta).Estado, ESPERANDO_PAGO)

    def test_y_ahi_si_puede_pagar(self):
        id_venta = self.envejecer(
            self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"])
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL}))
        self.assertEqual(detalle["comprobante_pago"], URL)

    def test_en_efectivo_el_panel_lo_confirma_y_listo(self):
        # Sin transferencia no hay nada que esperar: no pasa por el paso de
        # pago.
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        self.assertEqual(self.venta(id_venta).Estado, CONFIRMADO)


# ══════════════════════════════════════════════════════════════════════
# 2. El pedido programado se paga por transferencia, y no antes de tiempo
# ══════════════════════════════════════════════════════════════════════
class PedidoProgramadoTest(Base):
    def test_no_se_puede_crear_en_efectivo(self):
        # Lo que hay que hornear se respalda con plata antes de encender el
        # horno: el efectivo se cobra al recibir, cuando ya se produjo.
        r = self.post("/ventas/", self.cliente, self.cuerpo_pedido(
            productos=[{"ID_Producto": ID_TORTA, "Cantidad": 6}],
            Metodo_Pago="Efectivo"))
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_ni_cambiarlo_a_efectivo_despues(self):
        id_venta = self.programado(cantidad=6)
        r = self.editar(id_venta, {"Metodo_Pago": "Efectivo"})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_nace_pendiente_sin_pedir_nada(self):
        id_venta = self.programado()
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)

    def test_no_se_paga_antes_de_acordar_la_fecha(self):
        id_venta = self.programado()
        r = self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                       {"comprobante_url": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_ni_el_saldo_antes_de_haber_pagado_el_anticipo(self):
        # No se puede deber un saldo si todavia no entro el anticipo.
        id_venta = self.programado()
        r = self.patch(f"/pedidos/{id_venta}/pagar-saldo", self.cliente,
                       {"comprobante_url": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_negociando_la_fecha_tampoco(self):
        id_venta = self.programado()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin,
            {"fecha_entrega": (_now() + timedelta(days=5)).isoformat()}))
        r = self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                       {"comprobante_url": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_acordada_la_fecha_se_habilita_el_pago(self):
        id_venta = self.programado()
        self.afirmar_ok(self.aprobar_fecha(id_venta))
        venta = self.venta(id_venta)
        self.assertEqual(venta.Estado, ESPERANDO_PAGO)
        self.assertTrue(venta.Requiere_Anticipo)
        self.assertGreater(Decimal(str(venta.Anticipo_Requerido or 0)), 0)


# ══════════════════════════════════════════════════════════════════════
# 3. El 50% y el 100%
# ══════════════════════════════════════════════════════════════════════
class AnticipoOTotalTest(Base):
    def listo_para_pagar(self):
        id_venta = self.programado()
        self.afirmar_ok(self.aprobar_fecha(id_venta))
        return id_venta, self.venta(id_venta)

    def test_el_anticipo_es_la_mitad_del_total(self):
        _, venta = self.listo_para_pagar()
        self.assertEqual(
            Decimal(str(venta.Anticipo_Requerido)),
            (Decimal(str(venta.Total)) / 2).quantize(Decimal("1")),
        )

    def test_pagar_el_50_deja_saldo_pendiente(self):
        id_venta, venta = self.listo_para_pagar()
        anticipo = float(venta.Anticipo_Requerido)
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL, "monto": anticipo}))
        self.assertTrue(detalle["anticipo_registrado"])
        self.assertFalse(detalle["pago_final_registrado"],
                         "queda el saldo por pagar")

    def test_pagar_el_100_lo_deja_saldado(self):
        id_venta, venta = self.listo_para_pagar()
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL, "monto": float(venta.Total)}))
        self.assertTrue(detalle["anticipo_registrado"])
        self.assertTrue(detalle["pago_final_registrado"])

    def test_menos_del_50_no_se_acepta(self):
        id_venta, venta = self.listo_para_pagar()
        r = self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                       {"comprobante_url": URL,
                        "monto": float(venta.Anticipo_Requerido) - 1000})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_el_saldo_se_paga_despues_del_anticipo(self):
        id_venta, venta = self.listo_para_pagar()
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL,
             "monto": float(venta.Anticipo_Requerido)}))
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/aprobar-comprobante", self.admin))

        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar-saldo", self.cliente,
            {"comprobante_url": "https://ejemplo/saldo.jpg"}))
        self.assertEqual(detalle["saldo_comprobante_url"],
                         "https://ejemplo/saldo.jpg")
        self.assertEqual(detalle["estado_pago"], "saldo_pendiente_validacion")

    def test_los_dos_comprobantes_se_distinguen(self):
        # La pantalla del cliente tiene que poder mostrar cuál es cuál.
        id_venta, venta = self.listo_para_pagar()
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL,
             "monto": float(venta.Anticipo_Requerido)}))
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/aprobar-comprobante", self.admin))
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar-saldo", self.cliente,
            {"comprobante_url": "https://ejemplo/saldo.jpg"}))

        detalle = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{id_venta}", self.cliente))
        self.assertEqual(detalle["comprobante_pago"], URL)
        self.assertEqual(detalle["saldo_comprobante_url"],
                         "https://ejemplo/saldo.jpg")


# ══════════════════════════════════════════════════════════════════════
# 4. Un pedido con anticipo sí se edita y sí se cancela
# ══════════════════════════════════════════════════════════════════════
class ConAnticipoPeroSinPagarTest(Base):
    def test_se_puede_editar_dentro_de_la_ventana(self):
        # Exigir anticipo no es haberlo cobrado: el pedido sigue siendo del
        # cliente hasta que entre la plata.
        id_venta = self.programado()
        self.afirmar_ok(self.editar(id_venta, {"quiere_domicilio": True}))

    def test_se_puede_cancelar(self):
        id_venta = self.programado()
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/cancelar-mi-pedido", self.cliente))
        self.assertEqual(self.venta(id_venta).Estado, 5)

    def test_con_el_anticipo_ya_pagado_ya_no(self):
        id_venta = self.programado()
        self.afirmar_ok(self.aprobar_fecha(id_venta))
        venta = self.venta(id_venta)
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL,
             "monto": float(venta.Anticipo_Requerido)}))

        r = self.patch(f"/pedidos/{id_venta}/cancelar-mi-pedido", self.cliente)
        self.assertEqual(r.status_code, 400, self.detalle(r))


if __name__ == "__main__":
    unittest.main()
