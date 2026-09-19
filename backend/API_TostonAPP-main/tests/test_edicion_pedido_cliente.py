# -*- coding: utf-8 -*-
"""La edicion del pedido por parte del cliente, regla por regla.

El servidor es la autoridad: la web y la app deciden que mostrar, pero lo
que vale es lo que se acepta aca. Cada prueba de este archivo intenta lo que
un cliente podria intentar llamando al endpoint directo, sin pasar por la
pantalla.
"""
import sys
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from panel import PanelBase, ID_BARRIO, ID_CLIENTE, ID_TOSTON

from src.shared.services.models import Venta, Domicilio, Usuario
from src.features.ventas.gestion_ventas.services.service import _now

PEDIDO_CONFIRMADO = 4
PEDIDO_ESPERANDO_PAGO = 20
URL = "https://ejemplo/comprobante.jpg"


class EdicionBase(PanelBase):
    def setUp(self):
        super().setUp()
        # El cliente del panel tiene direccion pero no barrio: sin el, el
        # respaldo de "usa la direccion que ya tiene" no puede resolverse.
        cliente = self.db.query(Usuario).filter(
            Usuario.ID_Usuario == ID_CLIENTE).first()
        cliente.ID_Barrio = ID_BARRIO
        self.db.commit()

    def editar(self, id_venta, cuerpo):
        return self.patch(f"/pedidos/{id_venta}/editar-mi-pedido",
                          self.cliente, cuerpo)

    def envejecer(self, id_venta, minutos=30):
        """Mueve la creacion del pedido al pasado: la ventana ya vencio."""
        venta = self.db.query(Venta).filter(
            Venta.ID_Venta == id_venta).first()
        venta.Fecha_Venta = _now() - timedelta(minutes=minutos)
        self.db.commit()
        return id_venta

    def pedido_transferencia(self, **kw):
        return self.crear_pedido(Metodo_Pago="Transferencia", **kw)["ID_Venta"]

    def pedido_con_anticipo(self):
        """11 tostones = $110.000: por encima del umbral del anticipo."""
        return self.crear_pedido(
            Metodo_Pago="Transferencia",
            productos=[{"ID_Producto": ID_TOSTON, "Cantidad": 11}],
        )["ID_Venta"]


# ══════════════════════════════════════════════════════════════════════
# 1. La ventana de 10 minutos
# ══════════════════════════════════════════════════════════════════════
class VentanaDeEdicionTest(EdicionBase):
    def test_dentro_de_los_diez_minutos_se_puede(self):
        id_venta = self.pedido_transferencia()
        self.afirmar_ok(self.editar(id_venta, {"Metodo_Pago": "Efectivo"}))

    def test_pasados_los_diez_minutos_no_se_puede_esperando_pago(self):
        # "Esperando pago" estaba exento de la ventana entera: bastaba con
        # que el pedido llevara transferencia para poder editarlo para
        # siempre.
        id_venta = self.envejecer(self.pedido_transferencia())
        r = self.editar(id_venta, {"Metodo_Pago": "Efectivo"})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_pasados_los_diez_minutos_no_se_puede_pendiente(self):
        # Un pedido con produccion vive en "Pendiente" hasta que el admin
        # aprueba la fecha: tambien quedaba editable indefinidamente.
        id_venta = self.envejecer(self.pedido_con_faltante()["ID_Venta"])
        r = self.editar(id_venta, {"quiere_domicilio": True,
                                   "ID_Barrio": ID_BARRIO})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_confirmado_no_se_edita(self):
        id_venta = self.envejecer(self.crear_pedido()["ID_Venta"])
        self.poner_estado(id_venta, PEDIDO_CONFIRMADO)
        r = self.editar(id_venta, {"Metodo_Pago": "Transferencia"})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_el_comprobante_sigue_pudiendose_adjuntar_despues(self):
        # Transferir y tomar la captura lleva mas de diez minutos: eso no es
        # editar el pedido, es cumplirlo.
        id_venta = self.envejecer(self.pedido_transferencia())
        detalle = self.afirmar_ok(
            self.editar(id_venta, {"Comprobante_Pago": URL}))
        self.assertEqual(detalle["estado_pago"], "pendiente_validacion")

    def test_la_negociacion_de_fecha_sigue_abierta_despues(self):
        # Rechazar la fecha y contraofertar ocurre dias despues por diseno.
        id_venta = self.envejecer(self.pedido_con_faltante()["ID_Venta"])
        self.afirmar_ok(self.editar(id_venta, {
            "productos": [{"ID_Producto": 2, "Cantidad": 3}]}))


# ══════════════════════════════════════════════════════════════════════
# 2. El metodo de pago
# ══════════════════════════════════════════════════════════════════════
class MetodoDePagoTest(EdicionBase):
    def test_a_efectivo_el_pedido_deja_de_esperar_pago(self):
        # El bug reportado: el pedido seguia "Esperando pago" y las dos
        # pantallas seguian pidiendo el comprobante de una transferencia que
        # ya nadie va a hacer.
        id_venta = self.pedido_transferencia()
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_ESPERANDO_PAGO)

        detalle = self.afirmar_ok(
            self.editar(id_venta, {"Metodo_Pago": "Efectivo"}))
        self.assertEqual(detalle["Estado"], PEDIDO_CONFIRMADO,
                         "en efectivo no hay nada que esperar")

    def test_a_efectivo_se_borra_el_comprobante(self):
        id_venta = self.pedido_transferencia(comprobante_pago=URL)
        self.afirmar_ok(self.editar(id_venta, {"Metodo_Pago": "Efectivo"}))
        venta = self.venta(id_venta)
        self.db.refresh(venta)
        self.assertIsNone(venta.Comprobante_Pago)
        self.assertIsNone(venta.Monto_Efectivo)
        self.assertIsNone(venta.Monto_Transferencia)

    def test_a_transferencia_el_comprobante_viene_despues(self):
        # Durante la ventana se elige COMO se paga; el comprobante pertenece
        # a la etapa de pago (ver test_estado_inicial_y_comprobante.py).
        id_venta = self.crear_pedido()["ID_Venta"]      # nace en efectivo
        detalle = self.afirmar_ok(
            self.editar(id_venta, {"Metodo_Pago": "Transferencia"}))
        self.assertEqual(detalle["Metodo_Pago"], "Transferencia")
        self.assertIsNone(detalle["comprobante_pago"])

    def test_a_transferencia_sin_comprobante_queda_pendiente(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        detalle = self.afirmar_ok(
            self.editar(id_venta, {"Metodo_Pago": "Transferencia"}))
        self.assertEqual(detalle["estado_pago"], "pendiente")

    def test_el_anticipo_no_se_paga_en_efectivo(self):
        # El anticipo es el 50% por transferencia. Cambiar el metodo a
        # efectivo lo saltaba entero: solo estaba bloqueado el mixto.
        id_venta = self.pedido_con_anticipo()
        venta = self.venta(id_venta)
        self.assertTrue(venta.Requiere_Anticipo, "el umbral es $100.000")

        r = self.editar(id_venta, {"Metodo_Pago": "Efectivo"})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_el_anticipo_tampoco_en_mixto(self):
        id_venta = self.pedido_con_anticipo()
        r = self.editar(id_venta, {"Metodo_Pago": "Mixto",
                                   "Monto_Efectivo": 10000})
        self.assertEqual(r.status_code, 400, self.detalle(r))


# ══════════════════════════════════════════════════════════════════════
# 3. El pago mixto
# ══════════════════════════════════════════════════════════════════════
class PagoMixtoTest(EdicionBase):
    def test_reparte_el_total_entre_las_dos_formas(self):
        id_venta = self.crear_pedido()["ID_Venta"]      # $20.000
        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Mixto", "Monto_Efectivo": 8000}))
        self.assertEqual(Decimal(str(detalle["monto_efectivo"])),
                         Decimal("8000"))
        self.assertEqual(
            Decimal(str(detalle["monto_efectivo"]))
            + Decimal(str(detalle["monto_transferencia"])),
            Decimal(str(detalle["Total"])),
            "efectivo + transferencia tiene que dar el total")

    def test_sin_decir_cuanto_en_efectivo_no_es_mixto(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        r = self.editar(id_venta, {"Metodo_Pago": "Mixto"})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_el_efectivo_no_puede_ser_todo_el_total(self):
        # Antes se recortaba en silencio: el pedido quedaba "Mixto" con
        # transferencia $0, que no es mixto ni es efectivo.
        id_venta = self.crear_pedido()["ID_Venta"]
        r = self.editar(id_venta, {"Metodo_Pago": "Mixto",
                                   "Monto_Efectivo": 20000})
        self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_el_efectivo_no_puede_ser_cero_ni_negativo(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        for monto in (0, -5000):
            r = self.editar(id_venta, {"Metodo_Pago": "Mixto",
                                       "Monto_Efectivo": monto})
            self.assertEqual(r.status_code, 400, self.detalle(r))

    def test_el_comprobante_de_la_transferencia_entera_no_vale_para_el_mixto(self):
        # Pagaba $20.000 por transferencia y tiene la captura de esos
        # $20.000. Ahora transfiere $12.000: esa captura respalda otra cifra.
        id_venta = self.pedido_transferencia(comprobante_pago=URL)
        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Mixto", "Monto_Efectivo": 8000}))
        self.assertIsNone(detalle["comprobante_pago"],
                          "respaldaba un monto distinto")
        self.assertEqual(detalle["estado_pago"], "pendiente")

    def test_con_comprobante_nuevo_el_mixto_queda_en_revision(self):
        id_venta = self.pedido_transferencia(comprobante_pago=URL)
        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Mixto", "Monto_Efectivo": 8000,
            "Comprobante_Pago": "https://ejemplo/nuevo.jpg"}))
        self.assertEqual(detalle["comprobante_pago"],
                         "https://ejemplo/nuevo.jpg")
        self.assertEqual(detalle["estado_pago"], "pendiente_validacion")

    def test_agregar_domicilio_recalcula_la_parte_transferida(self):
        # El domicilio sube el total DESPUES de repartir: la transferencia
        # quedaba corta y el pedido cobraba de menos.
        id_venta = self.crear_pedido()["ID_Venta"]
        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Mixto", "Monto_Efectivo": 8000,
            "quiere_domicilio": True, "ID_Barrio": ID_BARRIO}))
        self.assertEqual(
            Decimal(str(detalle["monto_efectivo"]))
            + Decimal(str(detalle["monto_transferencia"])),
            Decimal(str(detalle["Total"])),
            "el domicilio tambien se paga")


# ══════════════════════════════════════════════════════════════════════
# 4. El tipo de entrega
# ══════════════════════════════════════════════════════════════════════
class TipoDeEntregaTest(EdicionBase):
    def test_de_recoger_a_domicilio_usa_la_direccion_registrada(self):
        # No hay que volver a escribir lo que ya esta en la cuenta.
        id_venta = self.crear_pedido()["ID_Venta"]
        total_antes = Decimal(str(self.venta(id_venta).Total))

        detalle = self.afirmar_ok(self.editar(
            id_venta, {"quiere_domicilio": True}))

        self.assertTrue(detalle["tiene_domicilio"])
        self.assertEqual(detalle["direccion_entrega"], "Calle 10 #20-30")
        self.assertGreater(Decimal(str(detalle["Total"])), total_antes)
        self.assertGreater(detalle["costo_domicilio_total"], 0)

    def test_de_recoger_a_domicilio_con_otra_direccion(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        detalle = self.afirmar_ok(self.editar(id_venta, {
            "quiere_domicilio": True, "ID_Barrio": ID_BARRIO,
            "Direccion_Entrega": "Cra 45 #9-11"}))
        self.assertEqual(detalle["direccion_entrega"], "Cra 45 #9-11")

    def test_de_domicilio_a_recoger_deja_de_ser_domicilio(self):
        # Se marcaba el domicilio como cancelado pero la fila seguia ahi, y
        # todo lo que pregunta "?tiene domicilio?" seguia diciendo que si:
        # el detalle mostraba la direccion y el costo del envio.
        id_venta = self.crear_pedido(domicilio=self.direccion())["ID_Venta"]
        total_antes = Decimal(str(self.venta(id_venta).Total))

        detalle = self.afirmar_ok(self.editar(
            id_venta, {"quiere_domicilio": False}))

        self.assertFalse(detalle["tiene_domicilio"])
        self.assertIsNone(detalle["direccion_entrega"])
        self.assertEqual(detalle["costo_domicilio_total"], 0)
        self.assertLess(Decimal(str(detalle["Total"])), total_antes)

    def test_con_repartidor_asignado_ya_no_se_cambia(self):
        id_venta = self.crear_pedido(domicilio=self.direccion())["ID_Venta"]
        dom = self.db.query(Domicilio).filter(
            Domicilio.ID_Venta == id_venta).first()
        dom.ID_Empleado = 3
        self.db.commit()
        r = self.editar(id_venta, {"quiere_domicilio": False})
        self.assertEqual(r.status_code, 400, self.detalle(r))


# ══════════════════════════════════════════════════════════════════════
# 5. Casos combinados del flujo real
# ══════════════════════════════════════════════════════════════════════
class CasosCombinadosTest(EdicionBase):
    def test_recoger_efectivo_pasa_a_domicilio_transferencia(self):
        id_venta = self.crear_pedido()["ID_Venta"]
        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Transferencia", "quiere_domicilio": True}))
        self.assertTrue(detalle["tiene_domicilio"])
        self.assertEqual(detalle["Metodo_Pago"], "Transferencia")
        self.assertEqual(detalle["estado_pago"], "pendiente")
        self.assertGreater(detalle["costo_domicilio_total"], 0)

    def test_domicilio_transferencia_pasa_a_recoger_efectivo(self):
        id_venta = self.crear_pedido(
            domicilio=self.direccion(), Metodo_Pago="Transferencia",
            comprobante_pago=URL)["ID_Venta"]

        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Efectivo", "quiere_domicilio": False}))

        self.assertFalse(detalle["tiene_domicilio"])
        self.assertEqual(detalle["costo_domicilio_total"], 0)
        self.assertIsNone(detalle["comprobante_pago"])
        self.assertEqual(detalle["Metodo_Pago"], "Efectivo")

    def test_domicilio_efectivo_pasa_a_mixto_conservando_el_envio(self):
        id_venta = self.crear_pedido(domicilio=self.direccion())["ID_Venta"]
        envio_antes = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{id_venta}",
                     self.cliente))["costo_domicilio_total"]

        detalle = self.afirmar_ok(self.editar(id_venta, {
            "Metodo_Pago": "Mixto", "Monto_Efectivo": 5000}))

        self.assertTrue(detalle["tiene_domicilio"])
        self.assertEqual(detalle["costo_domicilio_total"], envio_antes)
        self.assertEqual(
            Decimal(str(detalle["monto_efectivo"]))
            + Decimal(str(detalle["monto_transferencia"])),
            Decimal(str(detalle["Total"])))


# ══════════════════════════════════════════════════════════════════════
# 5b. El panel hace lo mismo que la app
# ══════════════════════════════════════════════════════════════════════
class ElPanelTest(EdicionBase):
    def test_a_efectivo_el_pedido_deja_de_esperar_pago(self):
        # El panel mostraba el mismo pedido "Esperando pago" con el aviso de
        # comprobante pendiente, sobre un pedido que ya era en efectivo.
        id_venta = self.pedido_transferencia(comprobante_pago=URL)
        detalle = self.afirmar_ok(
            self.put(f"/pedidos/{id_venta}", self.admin,
                     {"Metodo_Pago": "Efectivo"}))
        self.assertEqual(detalle["Estado"], PEDIDO_CONFIRMADO)
        self.assertIsNone(detalle["comprobante_pago"])


# ══════════════════════════════════════════════════════════════════════
# 6. Cancelar: lo que la app tiene que espejar
# ══════════════════════════════════════════════════════════════════════
class CancelarTest(EdicionBase):
    def cancelar(self, id_venta):
        return self.patch(f"/pedidos/{id_venta}/cancelar-mi-pedido",
                          self.cliente)

    def test_un_pedido_caro_se_puede_cancelar_si_no_pago_nada(self):
        # La app lo bloqueaba por "requiere anticipo"; el servidor bloquea
        # por "anticipo registrado", que es otra cosa: exigido no es pagado.
        id_venta = self.pedido_con_anticipo()
        self.assertTrue(self.venta(id_venta).Requiere_Anticipo)
        self.afirmar_ok(self.cancelar(id_venta))

    def test_esperando_pago_se_cancela_pasada_la_ventana(self):
        # El reloj solo protege el arrepentimiento inmediato en "Pendiente".
        id_venta = self.envejecer(self.pedido_transferencia())
        self.afirmar_ok(self.cancelar(id_venta))

    def test_pendiente_pasada_la_ventana_ya_no(self):
        id_venta = self.envejecer(self.pedido_con_faltante()["ID_Venta"])
        r = self.cancelar(id_venta)
        self.assertEqual(r.status_code, 400, self.detalle(r))


if __name__ == "__main__":
    unittest.main()
