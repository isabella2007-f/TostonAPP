# -*- coding: utf-8 -*-
"""El encargo con anticipo, de punta a punta.

Crear → 10 minutos del cliente → acordar la fecha → anticipo del 50% →
aprobarlo → pagar el saldo → aprobarlo. En cada paso se comprueba lo que el
pedido SI deja hacer y lo que no: pedir el saldo antes del anticipo, o el
comprobante antes de la fecha, es saltarse una etapa.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase

from src.shared.services.models import Venta
from src.shared.services.pagos_utils import (
    obtener_pago, TIPO_ANTICIPO, TIPO_SALDO,
)
from src.features.ventas.gestion_ventas.services.service import _now

PENDIENTE      = 1
ESPERANDO_PAGO = 20
ANTICIPO = "https://ejemplo/anticipo.jpg"
SALDO    = "https://ejemplo/saldo.jpg"


class FlujoDelAnticipoTest(PanelBase):
    def setUp(self):
        super().setUp()
        # 12 tortas = $120.000: por encargo y por encima del umbral.
        self.id_venta = self.pedido_con_faltante(
            cantidad=12, Metodo_Pago="Transferencia")["ID_Venta"]

    def envejecer(self):
        venta = self.db.query(Venta).filter(
            Venta.ID_Venta == self.id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=30)
        self.db.commit()

    def pagar(self, url, monto=None):
        cuerpo = {"comprobante_url": url}
        if monto is not None:
            cuerpo["monto"] = monto
        return self.patch(f"/pedidos/{self.id_venta}/pagar", self.cliente, cuerpo)

    def pagar_saldo(self, url=SALDO):
        return self.patch(f"/pedidos/{self.id_venta}/pagar-saldo", self.cliente,
                          {"comprobante_url": url})

    # ── Etapa 1: los 10 minutos ──────────────────────────────────────
    def test_recien_creado_no_hay_nada_que_pagar(self):
        # El anticipo vive en su fila de pago, no en una columna de Ventas.
        # La fila nace con el pedido, vacía: lo que dice si alguien pagó es
        # el monto, y esa es la pregunta que tienen que hacer las guardas.
        self.assertEqual(self.venta(self.id_venta).Estado, PENDIENTE)
        pago = obtener_pago(self.db, self.id_venta, TIPO_ANTICIPO)
        self.assertFalse(pago and pago.Monto, "nadie pagó nada todavía")

    def test_en_la_ventana_no_se_paga_el_anticipo(self):
        r = self.pagar(ANTICIPO, 60000)
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_ni_se_pide_el_saldo(self):
        # El aviso "ya recibimos tu anticipo, falta el saldo" sale de acá.
        r = self.pagar_saldo()
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_en_la_ventana_si_se_edita(self):
        self.afirmar_ok(self.patch(
            f"/pedidos/{self.id_venta}/editar-mi-pedido", self.cliente,
            {"Metodo_Pago": "Mixto", "Monto_Efectivo": 10000}))

    def test_pasada_la_ventana_ya_no(self):
        self.envejecer()
        r = self.patch(f"/pedidos/{self.id_venta}/editar-mi-pedido",
                       self.cliente, {"quiere_domicilio": True})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    # ── Etapa 2: la fecha ────────────────────────────────────────────
    def test_negociando_la_fecha_tampoco_se_paga(self):
        self.envejecer()
        self.afirmar_ok(self.patch(
            f"/ventas/{self.id_venta}/proponer-fecha", self.admin,
            {"fecha_entrega": (_now() + timedelta(days=6)).isoformat(),
             "motivo": "Ese día no hay horno libre"}))
        r = self.pagar(ANTICIPO, 60000)
        self.assertEqual(r.status_code, 400, self.detalle(r))

    # ── Etapa 3: el anticipo ─────────────────────────────────────────
    def acordar_fecha(self):
        self.envejecer()
        self.afirmar_ok(self.aprobar_fecha(self.id_venta))
        return self.venta(self.id_venta)

    def test_acordada_la_fecha_se_pide_el_anticipo(self):
        venta = self.acordar_fecha()
        self.assertEqual(venta.Estado, ESPERANDO_PAGO)
        self.assertTrue(venta.Requiere_Anticipo)

    def test_el_anticipo_queda_registrado(self):
        venta = self.acordar_fecha()
        self.afirmar_ok(self.pagar(ANTICIPO, float(venta.Anticipo_Requerido)))
        self.afirmar_ok(self.patch(
            f"/pedidos/{self.id_venta}/aprobar-comprobante", self.admin))

        pago = obtener_pago(self.db, self.id_venta, TIPO_ANTICIPO)
        self.assertIsNotNone(pago, "el anticipo tiene su propia fila")
        self.assertEqual(pago.Comprobante_Url, ANTICIPO)
        self.assertEqual(pago.Estado, "aprobado")

    # ── Etapa 4: el saldo ────────────────────────────────────────────
    def test_con_el_anticipo_pagado_el_saldo_se_puede_subir(self):
        # El error reportado: decía "primero hay que pagar el anticipo"
        # aunque el anticipo ya estaba pagado y aprobado.
        venta = self.acordar_fecha()
        self.afirmar_ok(self.pagar(ANTICIPO, float(venta.Anticipo_Requerido)))
        self.afirmar_ok(self.patch(
            f"/pedidos/{self.id_venta}/aprobar-comprobante", self.admin))

        detalle = self.afirmar_ok(self.pagar_saldo())
        self.assertEqual(detalle["estado_pago"], "saldo_pendiente_validacion")

    def test_el_saldo_no_pisa_el_comprobante_del_anticipo(self):
        venta = self.acordar_fecha()
        self.afirmar_ok(self.pagar(ANTICIPO, float(venta.Anticipo_Requerido)))
        self.afirmar_ok(self.patch(
            f"/pedidos/{self.id_venta}/aprobar-comprobante", self.admin))
        self.afirmar_ok(self.pagar_saldo())

        anticipo = obtener_pago(self.db, self.id_venta, TIPO_ANTICIPO)
        saldo    = obtener_pago(self.db, self.id_venta, TIPO_SALDO)
        self.assertEqual(anticipo.Comprobante_Url, ANTICIPO)
        self.assertEqual(saldo.Comprobante_Url, SALDO)

    def test_los_dos_comprobantes_llegan_al_detalle(self):
        venta = self.acordar_fecha()
        self.afirmar_ok(self.pagar(ANTICIPO, float(venta.Anticipo_Requerido)))
        self.afirmar_ok(self.patch(
            f"/pedidos/{self.id_venta}/aprobar-comprobante", self.admin))
        self.afirmar_ok(self.pagar_saldo())

        detalle = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{self.id_venta}", self.cliente))
        self.assertEqual(detalle["comprobante_pago"], ANTICIPO)
        self.assertEqual(detalle["saldo_comprobante_url"], SALDO)

    def test_pagando_el_100_no_queda_saldo(self):
        venta = self.acordar_fecha()
        self.afirmar_ok(self.pagar(ANTICIPO, float(venta.Total)))
        self.afirmar_ok(self.patch(
            f"/pedidos/{self.id_venta}/aprobar-comprobante", self.admin))

        r = self.pagar_saldo()
        self.assertEqual(r.status_code, 400, self.detalle(r))


if __name__ == "__main__":
    unittest.main()
