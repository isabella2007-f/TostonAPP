"""Al dividir la entrega, el domicilio original deja de ser un viaje.

Cuando el cliente pide recibir primero lo que está listo, el pedido se parte en
dos grupos y cada uno paga y hace SU propio domicilio. El domicilio original
—el que no pertenece a ningún grupo— se queda como plantilla: de él salen la
dirección y el precio que se descuenta del total.

Lo que no puede seguir siendo es un viaje pendiente. Nadie lo va a tomar nunca:
su plata ya salió del total y los productos los llevan los grupos. Mientras
figure como pendiente, el tablero de domicilios muestra una entrega fantasma
que nadie puede asignar y que infla la cuenta del día.
"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from panel import *  # noqa: F401,F403
from panel import ID_BARRIO, PanelBase

from src.shared.services.models import Domicilio

DOM_CANCELADO = 5


class DomicilioHuerfanoTests(PanelBase):
    def dividir(self, id_venta, tipo_a="domicilio", tipo_b="domicilio"):
        fecha = (datetime.now() + timedelta(days=1)).isoformat()
        return self.post(
            f"/ventas/{id_venta}/crear-grupos-envio", self.cliente,
            {
                "fecha_anticipada": fecha,
                "tipo_entrega_a": tipo_a,
                "tipo_entrega_b": tipo_b,
                "id_barrio_a": ID_BARRIO,
                "id_barrio_b": ID_BARRIO,
            },
        )

    def domicilios_de(self, id_venta):
        return self.db.query(Domicilio).filter(
            Domicilio.ID_Venta == id_venta).all()

    def referencia(self, id_venta):
        return self.db.query(Domicilio).filter(
            Domicilio.ID_Venta == id_venta,
            Domicilio.ID_Grupo.is_(None),
        ).first()

    def pedido_dividido(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        # Dividir exige una fecha ya acordada con el cliente.
        venta = self.venta(id_venta)
        venta.Fecha_entrega_esperada = datetime.now() + timedelta(days=5)
        self.db.commit()
        respuesta = self.dividir(id_venta)
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.db.expire_all()
        return id_venta

    def test_la_plantilla_no_queda_como_viaje_pendiente(self):
        id_venta = self.pedido_dividido()
        ref = self.referencia(id_venta)
        self.assertIsNotNone(ref, "la plantilla se conserva: de ella salen la "
                                  "dirección y el precio que se descontó")
        self.assertEqual(
            ref.Estado, DOM_CANCELADO,
            "quedó como domicilio pendiente: aparece en el tablero para "
            "asignar y nadie lo va a llevar nunca")

    def test_los_grupos_sí_son_viajes(self):
        id_venta = self.pedido_dividido()
        de_grupo = [d for d in self.domicilios_de(id_venta)
                    if d.ID_Grupo is not None]
        # Uno por grupo que va a domicilio. Sin nada en producción hay un solo
        # grupo, y ese sí es un viaje de verdad.
        self.assertGreaterEqual(len(de_grupo), 1)
        for d in de_grupo:
            self.assertNotEqual(d.Estado, DOM_CANCELADO)

    def test_no_aparece_en_el_tablero_para_asignar(self):
        id_venta = self.pedido_dividido()
        cuerpo = self.afirmar_ok(
            self.get("/domicilios/?por_pagina=100", self.admin))
        ref = self.referencia(id_venta)
        pendientes = [d for d in cuerpo["domicilios"]
                      if d.get("Estado") != DOM_CANCELADO]
        self.assertNotIn(
            ref.ID_Domicilio, [d["ID_Domicilio"] for d in pendientes],
            "el tablero ofrece para asignar una entrega que no existe")

    def test_la_direccion_sigue_saliendo_de_la_plantilla(self):
        # Es lo que hace que los grupos hereden a dónde va el pedido: por eso
        # la fila se conserva en vez de borrarse.
        id_venta = self.pedido_dividido()
        ref = self.referencia(id_venta)
        for d in self.domicilios_de(id_venta):
            if d.ID_Grupo is not None:
                self.assertEqual(d.Direccion_entrega, ref.Direccion_entrega)


if __name__ == "__main__":
    unittest.main()
