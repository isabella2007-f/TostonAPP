# -*- coding: utf-8 -*-
"""Que cada novedad del pedido salga al celular del cliente.

Un pedido con anticipo pasa por varias manos después de confirmarse: entra a
producción, queda listo, se le asigna un repartidor, sale a la calle. Cada uno
de esos pasos lo mueve un módulo distinto, y dos de ellos movían el pedido sin
avisarle a nadie:

- La cocina cambiaba `Venta.Estado` directamente. "En preparación" y "Listo"
  —los dos momentos que el cliente más espera— no mandaban ningún push.
- La asignación del domicilio avisaba al repartidor y al panel, pero no al
  cliente, que es quien va a abrir la puerta.

Estas pruebas no miran Firebase: interceptan la salida del push y comprueban
que el servidor la manda, con el pedido y el estado correctos.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_CLIENTE, ID_REPARTIDOR

from src.features.ventas.pedidos.services.estados import EstadoPedido


class NovedadesDelPedidoTest(PanelBase):
    """Cada paso del pedido, visto desde el celular del cliente."""

    def _pedido_con_orden(self):
        """Un pedido con faltante, con la fecha ya aprobada.

        Aprobar la fecha ya lo deja En producción y le abre la orden: ese paso
        avisa por el camino normal de `cambiar_estado`. Lo que sigue —que la
        cocina lo termine— lo mueve el módulo de producción, que es el que no
        avisaba.
        """
        pedido = self.pedido_con_faltante_aprobado()
        id_venta = pedido["ID_Venta"]
        orden = self.orden(id_venta)
        self.assertIsNotNone(orden, "el pedido debería tener orden de producción")
        return id_venta, orden

    def test_al_aprobarse_la_fecha_avisa_que_entro_a_produccion(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        with patch(
            "src.shared.services.fcm_service.notificar_cambio_pedido_push"
        ) as push:
            self.afirmar_ok(self.aprobar_fecha(id_venta))
        push.assert_called_once()
        self.assertEqual(push.call_args.kwargs["id_venta"], id_venta)
        # Aprobar la fecha ya no manda el encargo al horno: por transferencia
        # queda esperando el pago, y ese es el aviso que le toca al cliente
        # —el de producción llega cuando el pago se aprueba—.
        self.assertEqual(
            push.call_args.kwargs["nuevo_estado"], EstadoPedido.ESPERANDO_PAGO
        )

    def test_al_quedar_listo_avisa(self):
        id_venta, orden = self._pedido_con_orden()
        # Arrancar la orden no mueve el pedido: ya estaba En producción.
        self.afirmar_ok(self.patch(
            f"/ordenes-produccion/{orden.ID_Orden_Produccion}/estado",
            self.admin, {"Estado": 13},
        ))
        with patch(
            "src.shared.services.fcm_service.notificar_cambio_pedido_push"
        ) as push:
            self.afirmar_ok(self.patch(
                f"/ordenes-produccion/{orden.ID_Orden_Produccion}/estado",
                self.admin, {"Estado": 11},   # 11 = Completada
            ))
        push.assert_called_once()
        self.assertEqual(push.call_args.kwargs["id_venta"], id_venta)
        self.assertEqual(
            push.call_args.kwargs["nuevo_estado"], EstadoPedido.LISTO
        )

    def test_arrancar_la_orden_no_avisa_dos_veces(self):
        # El pedido ya estaba En producción: repetir el aviso sería mandarle
        # al cliente la misma novedad otra vez.
        _, orden = self._pedido_con_orden()
        with patch(
            "src.shared.services.fcm_service.notificar_cambio_pedido_push"
        ) as push:
            self.afirmar_ok(self.patch(
                f"/ordenes-produccion/{orden.ID_Orden_Produccion}/estado",
                self.admin, {"Estado": 13},
            ))
        push.assert_not_called()

    def test_el_cliente_se_entera_de_quien_le_lleva_el_pedido(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        dom = self.domicilio(id_venta)
        self.assertIsNotNone(dom)

        with patch(
            "src.shared.services.fcm_service.notificar_repartidor_asignado_push"
        ) as push:
            self.afirmar_ok(self.patch(
                f"/domicilios/{dom.ID_Domicilio}/repartidor",
                self.admin, {"ID_Empleado": ID_REPARTIDOR},
            ))
        push.assert_called_once()
        self.assertEqual(push.call_args.kwargs["id_venta"], id_venta)
        self.assertEqual(push.call_args.kwargs["id_usuario_cliente"], ID_CLIENTE)
        # El nombre es el dato que sirve: quién va a tocar el timbre.
        self.assertTrue(push.call_args.kwargs["repartidor"].strip())


if __name__ == "__main__":
    unittest.main()
