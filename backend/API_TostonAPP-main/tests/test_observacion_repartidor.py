"""La observación que escribe el repartidor al entregar.

Es lo que deja anotado cuando algo no salió como estaba previsto —"no había
nadie, se dejó con el portero"—. Tiene que quedar guardada y tiene que poder
leerse después, o no sirve de nada haberla escrito.
"""
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from panel import *  # noqa: F401,F403
from panel import (
    DOM_EN_CAMINO, DOM_ENTREGADO, ID_REPARTIDOR, PEDIDO_LISTO, PanelBase,
)

from src.shared.services.models import Domicilio


class ObservacionRepartidorTests(PanelBase):
    def domicilio_en_camino(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_LISTO}))
        dom = self.domicilio(id_venta)
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/repartidor", self.admin,
            {"ID_Empleado": ID_REPARTIDOR}))
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/estado", self.repartidor,
            {"Estado": DOM_EN_CAMINO}))
        # El cobro en efectivo se registra antes de entregar; sin eso el
        # servidor no deja marcar la entrega y no se llega a la observación.
        venta = self.venta(id_venta)
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/registrar-pago-efectivo",
            self.repartidor,
            {"recibido": True, "monto": int(venta.Total or 0)}))
        return dom.ID_Domicilio

    def leer(self, id_dom):
        return self.afirmar_ok(self.get(f"/domicilios/{id_dom}", self.repartidor))

    def test_se_guarda_al_cambiar_de_estado(self):
        id_dom = self.domicilio_en_camino()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO,
             "Observaciones": "No había nadie, se dejó con el portero"}))
        self.assertEqual(
            self.leer(id_dom)["Observaciones"],
            "No había nadie, se dejó con el portero")

    def test_el_listado_del_repartidor_tambien_la_trae(self):
        # Es donde la ve al repasar sus entregas del día.
        id_dom = self.domicilio_en_camino()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO, "Observaciones": "Timbre dañado"}))
        cuerpo = self.afirmar_ok(
            self.get("/domicilios/?por_pagina=100", self.repartidor))
        fila = next(d for d in cuerpo["domicilios"]
                    if d["ID_Domicilio"] == id_dom)
        self.assertEqual(fila["Observaciones"], "Timbre dañado")

    def test_el_admin_la_ve_en_el_pedido(self):
        # Quien atiende reclamos la necesita sin tener que abrir el domicilio.
        id_dom = self.domicilio_en_camino()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO, "Observaciones": "Se entregó al vecino"}))
        dom = self.db.query(Domicilio).filter(
            Domicilio.ID_Domicilio == id_dom).first()
        venta = self.afirmar_ok(
            self.get(f"/ventas/{dom.ID_Venta}", self.admin))
        self.assertEqual(venta["observaciones_domicilio"], "Se entregó al vecino")

    def test_no_mandarla_no_borra_la_que_habia(self):
        # Un cambio de estado sin comentario no puede vaciar lo que ya se
        # escribió: se perdería la única explicación de lo que pasó.
        id_dom = self.domicilio_en_camino()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_EN_CAMINO, "Observaciones": "Dirección confusa"}))
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor,
            {"Estado": DOM_ENTREGADO}))
        self.assertEqual(
            self.leer(id_dom)["Observaciones"], "Dirección confusa")


if __name__ == "__main__":
    unittest.main()
