# -*- coding: utf-8 -*-
"""La negociacion de la fecha, con sus motivos, tiene que poder leerse.

El admin propone un dia y escribe por que; el cliente contraoferta otro y
escribe por que. Todo eso se guarda en Historial_Fechas_Propuestas desde
hace tiempo... y no se devolvia en ninguna respuesta. El cliente veia la
fecha sin el motivo, el admin no veia la contraoferta, y no habia forma de
mostrar mas de una propuesta.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase

from src.shared.services.models import Venta
from src.features.ventas.gestion_ventas.services.service import _now


class Base(PanelBase):
    def setUp(self):
        super().setUp()
        self.id_venta = self.pedido_con_faltante(
            cantidad=6, Metodo_Pago="Transferencia")["ID_Venta"]
        venta = self.db.query(Venta).filter(
            Venta.ID_Venta == self.id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=30)
        self.db.commit()

    def en(self, dias):
        return (_now() + timedelta(days=dias)).isoformat()

    def proponer(self, dias, motivo):
        return self.afirmar_ok(self.patch(
            f"/ventas/{self.id_venta}/proponer-fecha", self.admin,
            {"fecha_entrega": self.en(dias), "motivo": motivo}))

    def contraofertar(self, dias, motivo):
        return self.afirmar_ok(self.patch(
            f"/ventas/{self.id_venta}/rechazar-fecha", self.cliente,
            {"fecha_propuesta": self.en(dias), "motivo": motivo}))

    def detalle_cliente(self):
        return self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{self.id_venta}", self.cliente))

    def detalle_panel(self):
        return self.afirmar_ok(
            self.get(f"/pedidos/{self.id_venta}", self.admin))


class ElClienteVeElMotivoTest(Base):
    def test_la_propuesta_del_admin_llega_con_su_motivo(self):
        self.proponer(6, "Ese día el horno está copado")

        propuestas = self.detalle_cliente()["propuestas_fecha"]
        self.assertEqual(len(propuestas), 1)
        self.assertEqual(propuestas[0]["tipo"], "propuesta")
        self.assertEqual(propuestas[0]["motivo"], "Ese día el horno está copado")
        self.assertIsNotNone(propuestas[0]["fecha"])

    def test_dice_quien_la_hizo(self):
        self.proponer(6, "No hay horno libre")
        self.assertEqual(self.detalle_cliente()["propuestas_fecha"][0]["de"],
                         "panaderia")


class ElPanelVeLaContraofertaTest(Base):
    def test_la_contraoferta_del_cliente_llega_con_su_motivo(self):
        self.proponer(6, "No hay horno libre")
        self.contraofertar(9, "Ese día viajo, el martes sí puedo")

        propuestas = self.detalle_panel()["propuestas_fecha"]
        self.assertEqual(len(propuestas), 2)
        ultima = propuestas[-1]
        self.assertEqual(ultima["tipo"], "propuesta_final")
        self.assertEqual(ultima["motivo"], "Ese día viajo, el martes sí puedo")
        self.assertEqual(ultima["de"], "cliente")

    def test_las_dos_partes_ven_lo_mismo(self):
        self.proponer(6, "No hay horno libre")
        self.contraofertar(9, "Ese día viajo")
        del_cliente = self.detalle_cliente()["propuestas_fecha"]
        del_panel   = self.detalle_panel()["propuestas_fecha"]
        self.assertEqual(
            [(p["tipo"], p["motivo"]) for p in del_cliente],
            [(p["tipo"], p["motivo"]) for p in del_panel],
        )


class ElHistorialSeLeeEnOrdenTest(Base):
    def test_las_propuestas_salen_de_la_primera_a_la_ultima(self):
        self.proponer(6, "Primera del horno")
        self.contraofertar(9, "Respuesta del cliente")

        propuestas = self.detalle_cliente()["propuestas_fecha"]
        self.assertEqual([p["motivo"] for p in propuestas],
                         ["Primera del horno", "Respuesta del cliente"])

    def test_aceptar_queda_anotado(self):
        self.proponer(6, "Esa semana sí")
        self.afirmar_ok(self.patch(
            f"/ventas/{self.id_venta}/aceptar-fecha", self.cliente))

        propuestas = self.detalle_cliente()["propuestas_fecha"]
        self.assertEqual(propuestas[-1]["tipo"], "aceptada")
        self.assertEqual(propuestas[-1]["de"], "cliente")

    def test_un_pedido_sin_negociacion_no_trae_nada(self):
        detalle = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{self.crear_pedido()['ID_Venta']}",
                     self.cliente))
        self.assertEqual(detalle["propuestas_fecha"], [])


if __name__ == "__main__":
    unittest.main()
