# -*- coding: utf-8 -*-
"""Dos reglas que se tocan: en que estado nace un pedido, y desde cuando se
puede respaldar el pago.

- Un pedido normal —con stock, sin produccion, en efectivo— nacia CONFIRMADO,
  saltandose 'Pendiente'. Con eso el cliente perdia su ventana de 10 minutos:
  'Confirmado' no esta entre los estados que puede cancelar, asi que el boton
  no existia desde el primer segundo. Y el stock se reservaba al crear, aunque
  el sistema ya tiene un mecanismo para reservarlo cuando la ventana cierra.

- El comprobante pertenece a una ETAPA del pedido, no a un metodo de pago.
  Durante los 10 minutos el cliente define COMO va a pagar; el pago en si
  viene despues, cuando el pedido llega a 'Esperando pago' —que en un pedido
  programado es despues de acordar la fecha—. `pagar_pedido` ya lo exigia,
  pero se podia colar por el endpoint de edicion.
"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_TOSTON, ID_TORTA

from src.shared.services.models import Venta
from src.features.ventas.gestion_ventas.services.service import _now

PENDIENTE       = 1
CONFIRMADO      = 4
FECHA_PROPUESTA = 16
ESPERANDO_PAGO  = 20
URL = "https://ejemplo/comprobante.jpg"


class Base(PanelBase):
    def envejecer(self, id_venta, minutos=30):
        venta = self.db.query(Venta).filter(Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=minutos)
        self.db.commit()
        return id_venta

    def editar(self, id_venta, cuerpo):
        return self.patch(f"/pedidos/{id_venta}/editar-mi-pedido",
                          self.cliente, cuerpo)


# ══════════════════════════════════════════════════════════════════════
# 1. En qué estado nace cada tipo de pedido
# ══════════════════════════════════════════════════════════════════════
class EstadoInicialTest(Base):
    def test_el_pedido_normal_nace_pendiente(self):
        # Hay stock, no hay produccion, se paga en efectivo: no hay nada que
        # esperar... salvo los 10 minutos del cliente.
        id_venta = self.crear_pedido()["ID_Venta"]
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)

    def test_el_pedido_normal_todavia_no_reserva_stock(self):
        # La reserva la hace `_evaluar_cierre_ventana` cuando la ventana
        # cierra. Reservar al crear dejaba ese mecanismo sin uso y apartaba
        # mercancia de un pedido que el cliente todavia puede cancelar.
        antes = self.stock(ID_TOSTON)
        id_venta = self.crear_pedido()["ID_Venta"]
        self.assertEqual(self.stock(ID_TOSTON), antes)
        self.assertFalse(self.venta(id_venta).Stock_Reservado)

    def test_el_cliente_puede_cancelarlo_de_una(self):
        # Esto es lo que se habia perdido.
        id_venta = self.crear_pedido()["ID_Venta"]
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/cancelar-mi-pedido", self.cliente))
        self.assertEqual(self.venta(id_venta).Estado, 5)

    def test_el_panel_no_lo_confirma_antes_de_tiempo(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        r = self.patch(f"/pedidos/{id_venta}/confirmar", self.admin)
        self.assertEqual(r.status_code, 400, self.detalle(r))
        self.assertIn("edición del cliente", self.detalle(r))

    def test_pasada_la_ventana_el_panel_lo_confirma_y_reserva(self):
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        antes = self.stock(ID_TOSTON)
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/confirmar", self.admin))
        self.assertEqual(self.venta(id_venta).Estado, CONFIRMADO)
        self.assertLess(self.stock(ID_TOSTON), antes, "se aparta lo vendido")

    def test_el_de_transferencia_espera_el_pago_al_confirmarse(self):
        # Nace PENDIENTE como todos, y llega a "Esperando pago" cuando el
        # panel lo acepta: antes de eso no hay nada que cobrar.
        id_venta = self.crear_pedido(Metodo_Pago="Transferencia")["ID_Venta"]
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)
        self.assertEqual(self.venta(self.pedido_esperando_pago()).Estado,
                         ESPERANDO_PAGO)

    def test_el_programado_sigue_pendiente_de_aprobacion(self):
        id_venta = self.pedido_con_faltante()["ID_Venta"]
        self.assertEqual(self.venta(id_venta).Estado, PENDIENTE)
        self.assertTrue(self.venta(id_venta).Necesita_Produccion)


# ══════════════════════════════════════════════════════════════════════
# 2. El comprobante pertenece a una etapa, no a un método de pago
# ══════════════════════════════════════════════════════════════════════
class ComprobanteSegunLaEtapaTest(Base):
    def programado(self, cantidad=6):
        """Pedido sobre stock: vive en 'Pendiente de Aprobación'."""
        return self.pedido_con_faltante(cantidad=cantidad)["ID_Venta"]

    def test_recien_creado_no_se_puede_respaldar_el_pago(self):
        id_venta = self.programado()
        r = self.editar(id_venta, {"Comprobante_Pago": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))
        self.assertIsNone(self.venta(id_venta).Comprobante_Pago)

    def test_pero_si_se_puede_elegir_como_se_va_a_pagar(self):
        id_venta = self.programado()
        detalle = self.afirmar_ok(
            self.editar(id_venta, {"Metodo_Pago": "Transferencia"}))
        self.assertEqual(detalle["Metodo_Pago"], "Transferencia")
        self.assertIsNone(detalle["comprobante_pago"])

    def test_el_mixto_se_reparte_sin_comprobante(self):
        id_venta = self.programado()
        detalle = self.afirmar_ok(self.editar(
            id_venta, {"Metodo_Pago": "Mixto", "Monto_Efectivo": 10000}))
        self.assertEqual(float(detalle["monto_efectivo"]), 10000)
        self.assertIsNone(detalle["comprobante_pago"])
        self.assertEqual(
            float(detalle["monto_efectivo"]) + float(detalle["monto_transferencia"]),
            float(detalle["Total"]))

    def test_ir_y_volver_de_metodo_no_deja_rastro(self):
        # Lo que hay que hornear se paga por transferencia, así que el ida y
        # vuelta se hace entre los dos métodos que sí admite.
        id_venta = self.programado()
        for metodo in ("Transferencia", "Mixto", "Transferencia"):
            cuerpo = {"Metodo_Pago": metodo}
            if metodo == "Mixto":
                cuerpo["Monto_Efectivo"] = 10000
            self.afirmar_ok(self.editar(id_venta, cuerpo))
        self.assertIsNone(self.venta(id_venta).Comprobante_Pago)

    def test_negociando_la_fecha_tampoco(self):
        id_venta = self.programado()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin,
            {"fecha_entrega": (_now() + timedelta(days=5)).isoformat()}))
        self.assertEqual(self.venta(id_venta).Estado, FECHA_PROPUESTA)

        r = self.editar(id_venta, {"Comprobante_Pago": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_por_el_endpoint_de_pago_directo_tampoco(self):
        # El mismo intento, saltándose la pantalla.
        id_venta = self.programado()
        r = self.patch(f"/pedidos/{id_venta}/pagar", self.cliente,
                       {"comprobante_url": URL})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_acordada_la_fecha_el_pago_se_habilita(self):
        # 11 tortas = $110.000: pasa el umbral, así que al aprobar la fecha
        # el pedido queda 'Esperando pago' pidiendo el anticipo.
        id_venta = self.pedido_con_faltante(cantidad=11)["ID_Venta"]
        self.afirmar_ok(self.aprobar_fecha(id_venta))
        self.assertEqual(self.venta(id_venta).Estado, ESPERANDO_PAGO)

        venta = self.venta(id_venta)
        detalle = self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/pagar", self.cliente,
            {"comprobante_url": URL,
             "monto": float(venta.Anticipo_Requerido or 0)}))
        self.assertEqual(detalle["comprobante_pago"], URL)
        self.assertEqual(detalle["estado_pago"], "pendiente_validacion")

    def test_esperando_pago_el_comprobante_tambien_entra_por_la_edicion(self):
        # Es el camino que usa el panel cuando el cliente manda la captura
        # por otro medio: sigue valiendo, pero solo en esa etapa.
        id_venta = self.pedido_esperando_pago()
        detalle = self.afirmar_ok(
            self.editar(id_venta, {"Comprobante_Pago": URL}))
        self.assertEqual(detalle["comprobante_pago"], URL)


if __name__ == "__main__":
    unittest.main()
