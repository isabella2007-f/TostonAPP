"""Pago mixto: una parte en efectivo y otra por transferencia.

El cliente dice cuánta plata pone en efectivo; el servidor la recorta contra
el total real y manda el resto a transferencia. Lo que se cobra en mano al
entregar es solo esa parte.
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.features.ventas.gestion_ventas.services.service import (
    UMBRAL_ANTICIPO,
    _es_mixto,
    _es_transferencia,
    _mixto_bloqueado_por_anticipo,
    _partir_pago_mixto,
    _pide_anticipo,
)
from src.features.ventas.pedidos.services.service import (
    _ESTADOS_MIXTO_A_MEDIAS,
    _lleva_transferencia,
)


class EsMixtoTests(unittest.TestCase):

    def test_reconoce_el_metodo(self):
        for metodo in ["Mixto", "mixto", "  MIXTO  "]:
            with self.subTest(metodo=metodo):
                self.assertTrue(_es_mixto(metodo))

    def test_los_otros_metodos_no_son_mixtos(self):
        for metodo in ["Efectivo", "Transferencia", "Contra entrega", None, ""]:
            with self.subTest(metodo=metodo):
                self.assertFalse(_es_mixto(metodo))

    def test_mixto_no_se_confunde_con_transferencia(self):
        """Son reglas distintas: la de transferencia sigue mirando su palabra."""
        self.assertFalse(_es_transferencia("Mixto"))


class MixtoConAnticipoTests(unittest.TestCase):
    """Un pedido con anticipo no se puede pagar en mixto.

    La parte en efectivo del mixto se cobra al entregar, o sea después de
    producir: no alcanza a respaldar el anticipo, que va antes.
    """

    def test_el_pedido_con_anticipo_rechaza_el_mixto(self):
        self.assertTrue(_mixto_bloqueado_por_anticipo("Mixto", True))

    def test_el_pedido_sin_anticipo_sigue_aceptando_el_mixto(self):
        """El caso de siempre, y ahora también el pedido chico sobre stock.

        Superar el stock ya no basta para cerrarle el mixto: si el pedido no
        pide anticipo (`_pide_anticipo`), no hay nada que respaldar antes de
        producir y el cliente puede repartir el pago como quiera.
        """
        self.assertFalse(_mixto_bloqueado_por_anticipo("Mixto", False))

    def test_los_otros_metodos_pasan_aunque_haya_anticipo(self):
        """Transferencia y efectivo conservan sus propias reglas de anticipo."""
        for metodo in ["Transferencia", "Efectivo", "Créditos", None, ""]:
            with self.subTest(metodo=metodo):
                self.assertFalse(_mixto_bloqueado_por_anticipo(metodo, True))

    def test_reconoce_el_mixto_escrito_de_cualquier_forma(self):
        for metodo in ["mixto", "  MIXTO  ", "Pago Mixto"]:
            with self.subTest(metodo=metodo):
                self.assertTrue(_mixto_bloqueado_por_anticipo(metodo, True))


class PideAnticipoTests(unittest.TestCase):
    """Qué pedido pide anticipo: puramente por monto (prompt-pedidos-2, 3.1).

    Antes hacía falta ADEMÁS que el pedido necesitara producción. Ahora un
    pedido que supera el umbral pide anticipo salga o no del stock del día.
    """

    def test_el_pedido_que_supera_el_umbral_pide_anticipo(self):
        self.assertTrue(_pide_anticipo(Decimal("100001")))

    def test_lo_que_sale_del_stock_tambien_pide_si_pesa(self):
        """Ya no importa si hay que fabricar: solo el monto decide."""
        self.assertTrue(_pide_anticipo(Decimal("500000")))

    def test_el_pedido_chico_no_pide_anticipo_aunque_haya_que_hornearlo(self):
        self.assertFalse(_pide_anticipo(Decimal("30000")))

    def test_el_umbral_no_se_cuenta_a_sí_mismo(self):
        """Justo $100.000 todavía no pide: la regla es "más de"."""
        self.assertFalse(_pide_anticipo(UMBRAL_ANTICIPO))
        self.assertTrue(_pide_anticipo(UMBRAL_ANTICIPO + Decimal("1")))

    def test_acepta_el_total_venga_como_venga(self):
        """El total llega como Decimal, float o str según quién pregunte."""
        for total in (Decimal("200000"), 200000.0, 200000, "200000"):
            with self.subTest(total=total):
                self.assertTrue(_pide_anticipo(total))


class PartirPagoMixtoTests(unittest.TestCase):

    def test_el_monto_que_pide_el_cliente_se_respeta(self):
        """El caso que motivó el cambio: $3.500 sueltos de un pedido de $22.500."""
        efectivo, transferencia = _partir_pago_mixto(Decimal("22500"), Decimal("3500"))
        self.assertEqual(efectivo, Decimal("3500.00"))
        self.assertEqual(transferencia, Decimal("19000.00"))

    def test_mitad_y_mitad(self):
        efectivo, transferencia = _partir_pago_mixto(Decimal("100000"), Decimal("50000"))
        self.assertEqual(efectivo, Decimal("50000.00"))
        self.assertEqual(transferencia, Decimal("50000.00"))

    def test_las_dos_partes_siempre_suman_el_total(self):
        for total in ["33333.33", "77777", "1", "0.05", "199999.99", "22500"]:
            for pedido in ["0", "1", "3500", "0.01", "12345.67", "99999999"]:
                with self.subTest(total=total, pedido=pedido):
                    t = Decimal(total)
                    efectivo, transferencia = _partir_pago_mixto(t, Decimal(pedido))
                    self.assertEqual(efectivo + transferencia, t)
                    self.assertGreaterEqual(efectivo, Decimal("0"))
                    self.assertGreaterEqual(transferencia, Decimal("0"))

    def test_no_se_puede_poner_en_efectivo_mas_de_lo_que_vale(self):
        """Se recorta al total: el pedido no puede quedar pagado de más."""
        efectivo, transferencia = _partir_pago_mixto(Decimal("50000"), Decimal("90000"))
        self.assertEqual(efectivo, Decimal("50000.00"))
        self.assertEqual(transferencia, Decimal("0.00"))

    def test_un_monto_negativo_se_trata_como_cero(self):
        efectivo, transferencia = _partir_pago_mixto(Decimal("50000"), Decimal("-4000"))
        self.assertEqual(efectivo, Decimal("0.00"))
        self.assertEqual(transferencia, Decimal("50000.00"))

    def test_sin_monto_no_va_nada_en_efectivo(self):
        efectivo, transferencia = _partir_pago_mixto(Decimal("50000"), None)
        self.assertEqual(efectivo, Decimal("0.00"))
        self.assertEqual(transferencia, Decimal("50000.00"))

    def test_acepta_el_monto_como_texto_o_float(self):
        """Del request llega como venga; no debe romperse por el tipo."""
        self.assertEqual(_partir_pago_mixto(Decimal("22500"), "3500")[0], Decimal("3500.00"))
        self.assertEqual(_partir_pago_mixto(Decimal("22500"), 3500.0)[0], Decimal("3500.00"))

    def test_los_centavos_no_se_pierden(self):
        efectivo, transferencia = _partir_pago_mixto(Decimal("22500.75"), Decimal("3500.25"))
        self.assertEqual(efectivo, Decimal("3500.25"))
        self.assertEqual(transferencia, Decimal("19000.50"))


class ComprobanteYCobroTests(unittest.TestCase):
    """Las dos puertas que dejaban al mixto sin botones en el panel."""

    def test_el_mixto_tiene_comprobante_que_revisar(self):
        self.assertTrue(_lleva_transferencia("Mixto"))
        self.assertTrue(_lleva_transferencia("Transferencia"))

    def test_el_efectivo_puro_no_tiene_comprobante(self):
        self.assertFalse(_lleva_transferencia("Efectivo"))
        self.assertFalse(_lleva_transferencia("Contra entrega"))
        self.assertFalse(_lleva_transferencia(None))

    def test_desde_donde_falta_la_otra_mitad(self):
        """Estados en los que el mixto todavia no tiene su comprobante aprobado."""
        for estado in ["pendiente", "pendiente_validacion", "comprobante_rechazado"]:
            with self.subTest(estado=estado):
                self.assertIn(estado, _ESTADOS_MIXTO_A_MEDIAS)

    def test_con_una_mitad_dentro_ya_no_esta_a_medias(self):
        """Si el comprobante ya se aprobo, cobrar el efectivo cierra el pedido."""
        for estado in ["anticipo_pagado", "pagado_completo", "efectivo_recibido"]:
            with self.subTest(estado=estado):
                self.assertNotIn(estado, _ESTADOS_MIXTO_A_MEDIAS)


if __name__ == "__main__":
    unittest.main()
