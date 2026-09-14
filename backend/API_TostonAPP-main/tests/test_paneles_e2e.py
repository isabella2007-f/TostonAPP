"""Los tres paneles, recorridos por HTTP contra la API real.

Cada clase es una pantalla o un recorrido: crear el pedido de todas las formas
que existen, el panel del cliente, el del administrador, el de producción, el
del domiciliario y las devoluciones. El andamiaje está en `panel.py`.

Corre sin credenciales:
    python tests/test_paneles_e2e.py
"""
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from panel import *  # noqa: F401,F403
from panel import (
    DEV_APROBADA, DEV_PENDIENTE, DEV_RECHAZADA,
    DOM_ASIGNADO, DOM_CANCELADO, DOM_EN_CAMINO, DOM_ENTREGADO, DOM_PENDIENTE,
    GRAMOS_POR_TORTA, ID_CLIENTE, ID_HARINA, ID_OTRO_CLIENTE, ID_REPARTIDOR,
    ID_OTRO_REPARTIDOR, ID_TORTA, ID_TOSTON, ORDEN_CANCELADA, ORDEN_COMPLETADA,
    ORDEN_EN_PROCESO, ORDEN_PENDIENTE, PEDIDO_CANCELADO, PEDIDO_CONFIRMADO,
    PEDIDO_EN_CAMINO, PEDIDO_EN_PRODUCCION, PEDIDO_ENTREGADO,
    PEDIDO_FECHA_PROPUESTA,
    PEDIDO_FECHA_RECHAZADA, PEDIDO_LISTO, PEDIDO_PENDIENTE, PRECIO,
    STOCK_HARINA, STOCK_TORTA, STOCK_TOSTON, PanelBase,
)
from src.features.ventas.devoluciones.services.service import (
    HORAS_LIMITE_DEVOLUCION,
)


COSTO_DOMICILIO = Decimal("5000")


# ══════════════════════════════════════════════════════════════════════════
# 1. Crear el pedido de todas las maneras que existen
# ══════════════════════════════════════════════════════════════════════════
class CrearPedidoTests(PanelBase):
    """Cada camino por el que entra un pedido a la panadería."""

    def test_efectivo_para_recoger_en_tienda(self):
        pedido = self.crear_pedido()
        self.assertEqual(Decimal(pedido["Total"]), Decimal("20000.00"))
        self.assertEqual(pedido["Estado"], PEDIDO_PENDIENTE)
        self.assertIsNone(self.domicilio())
        # Recoger en tienda: el stock no se toca hasta confirmar.
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON)

    def test_efectivo_con_domicilio_suma_el_costo_de_envio(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        self.assertEqual(Decimal(pedido["Total"]), Decimal("20000") + COSTO_DOMICILIO)
        dom = self.domicilio()
        self.assertIsNotNone(dom)
        self.assertEqual(dom.Estado, DOM_PENDIENTE)   # sin repartidor todavía

    def test_transferencia_con_comprobante_queda_esperando_validacion(self):
        pedido = self.crear_pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        self.assertEqual(self.venta(pedido["ID_Venta"]).Estado_Pago, "pendiente_validacion")

    def test_mixto_reparte_el_total_entre_efectivo_y_transferencia(self):
        pedido = self.crear_pedido(
            Metodo_Pago="Mixto",
            pago_efectivo_monto=7000,
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        venta = self.venta(pedido["ID_Venta"])
        self.assertEqual(Decimal(str(venta.Monto_Efectivo)), Decimal("7000.00"))
        self.assertEqual(
            Decimal(str(venta.Monto_Efectivo)) + Decimal(str(venta.Monto_Transferencia)),
            Decimal(str(venta.Total)),
        )

    def test_con_saldo_a_favor_baja_el_total_y_se_descuenta_del_saldo(self):
        self.dar_saldo(15000)
        pedido = self.crear_pedido(usar_credito=True, credito_monto=15000)
        self.assertEqual(Decimal(pedido["Total"]), Decimal("5000.00"))
        self.assertEqual(self.saldo(), Decimal("0"))

    def test_el_saldo_parcial_deja_el_resto_guardado(self):
        self.dar_saldo(15000)
        self.crear_pedido(usar_credito=True, credito_monto=5000)
        self.assertEqual(self.saldo(), Decimal("10000"))

    def test_el_mostrador_crea_el_pedido_ya_confirmado_y_reserva_stock(self):
        pedido = self.crear_pedido(quien=self.admin, creado_por_admin=True)
        self.assertEqual(pedido["Estado"], PEDIDO_CONFIRMADO)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON - 2)

    def test_el_pedido_con_faltante_abre_su_orden_de_produccion(self):
        pedido = self.pedido_con_faltante()
        venta = self.venta(pedido["ID_Venta"])
        self.assertEqual(venta.Sobre_Stock, 1)
        self.assertEqual(venta.Requiere_Anticipo, 1)
        orden = self.orden(pedido["ID_Venta"])
        self.assertIsNotNone(orden)
        self.assertEqual(orden.Cantidad, 6 - STOCK_TORTA)

    def test_el_faltante_chico_entra_sin_pedir_anticipo(self):
        """3 tortas = $30.000: una por hornear, por debajo del umbral."""
        pedido = self.crear_pedido(
            productos=[{"ID_Producto": ID_TORTA, "Cantidad": 3}],
        )
        venta = self.venta(pedido["ID_Venta"])
        self.assertEqual(venta.Sobre_Stock, 1)
        self.assertEqual(venta.Requiere_Anticipo or 0, 0)

    def test_el_pedido_grande_por_encargo_sin_anticipo_se_rechaza(self):
        respuesta = self.post("/ventas/", self.cliente, self.cuerpo_pedido(
            productos=[{"ID_Producto": ID_TORTA, "Cantidad": 6}],
        ))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("anticipo", self.detalle(respuesta).lower())

    def test_sin_telefono_no_se_puede_pedir_a_domicilio(self):
        from src.shared.services.models import Usuario
        u = self.db.query(Usuario).filter(Usuario.ID_Usuario == ID_CLIENTE).first()
        u.Telefono = None
        self.db.commit()

        respuesta = self.post("/ventas/", self.cliente, self.cuerpo_pedido(
            domicilio=self.direccion(),
        ))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("teléfono", self.detalle(respuesta).lower())

    def test_un_producto_fuera_de_la_tienda_no_se_puede_pedir(self):
        from src.shared.services.models import Producto
        p = self.db.query(Producto).filter(Producto.ID_Producto == ID_TOSTON).first()
        p.Publicado = 0
        self.db.commit()

        respuesta = self.post("/ventas/", self.cliente, self.cuerpo_pedido())
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("disponible", self.detalle(respuesta).lower())

    def test_un_producto_que_no_existe_da_404(self):
        respuesta = self.post("/ventas/", self.cliente, self.cuerpo_pedido(
            productos=[{"ID_Producto": 999, "Cantidad": 1}],
        ))
        self.assertEqual(respuesta.status_code, 404)

    def test_el_mostrador_si_puede_vender_a_nombre_de_un_cliente(self):
        """La regla es solo para clientes: el personal vende en mostrador."""
        cuerpo = self.crear_pedido(
            quien=self.admin, creado_por_admin=True, ID_Usuario=ID_OTRO_CLIENTE,
        )
        self.assertEqual(self.venta(cuerpo["ID_Venta"]).ID_Usuario, ID_OTRO_CLIENTE)

    def test_el_pedido_queda_a_nombre_de_quien_lo_hace(self):
        """El ID del cuerpo no puede mandar sobre el del token.

        Si mandara, cualquier cliente podría hacer pedidos a nombre de otro
        —y gastarle el saldo a favor, que se toma del ID_Usuario del pedido—.
        """
        self.dar_saldo(50000, id_usuario=ID_OTRO_CLIENTE)
        cuerpo = self.afirmar_ok(self.post("/ventas/", self.cliente, self.cuerpo_pedido(
            ID_Usuario=ID_OTRO_CLIENTE,
            usar_credito=True,
            credito_monto=20000,
        )), 201)
        self.assertEqual(
            self.venta(cuerpo["ID_Venta"]).ID_Usuario, ID_CLIENTE,
            "el pedido quedó a nombre de otro cliente",
        )
        self.assertEqual(
            self.saldo(ID_OTRO_CLIENTE), Decimal("50000"),
            "se gastó el saldo a favor de otro cliente",
        )
        # Y el pedido no aparece en el historial de la otra persona.
        ajenas = self.afirmar_ok(self.get("/ventas/mis-ventas", self.otro_cliente))
        self.assertEqual(ajenas["total"], 0)


# ══════════════════════════════════════════════════════════════════════════
# 2. Panel del cliente
# ══════════════════════════════════════════════════════════════════════════
class PanelClienteTests(PanelBase):
    """Lo que el cliente ve y puede hacer con sus propios pedidos."""

    def test_mis_ventas_solo_trae_las_suyas(self):
        self.crear_pedido()
        self.post("/ventas/", self.otro_cliente, self.cuerpo_pedido(ID_Usuario=ID_OTRO_CLIENTE))

        cuerpo = self.afirmar_ok(self.get("/ventas/mis-ventas", self.cliente))
        self.assertEqual(cuerpo["total"], 1)
        self.assertEqual(cuerpo["ventas"][0]["ID_Usuario"], ID_CLIENTE)

    def test_no_puede_abrir_el_pedido_de_otro(self):
        pedido = self.crear_pedido()
        respuesta = self.get(f"/ventas/mis-ventas/{pedido['ID_Venta']}", self.otro_cliente)
        self.assertIn(respuesta.status_code, (403, 404))

    def test_ve_su_saldo_a_favor(self):
        self.dar_saldo(12000)
        cuerpo = self.afirmar_ok(self.get("/ventas/mi-credito", self.cliente))
        self.assertEqual(Decimal(str(cuerpo["saldo"])), Decimal("12000"))

    def test_el_detalle_trae_lo_que_la_pantalla_muestra(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        cuerpo = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{pedido['ID_Venta']}", self.cliente)
        )
        self.assertEqual(cuerpo["estado_label"], "Pendiente")
        self.assertTrue(cuerpo["productos"])
        self.assertEqual(cuerpo["productos"][0]["nombre_producto"], "Tostón")
        self.assertTrue(cuerpo["tiene_domicilio"])
        self.assertEqual(cuerpo["direccion_entrega"], "Calle 10 #20-30")
        self.assertIsNotNone(cuerpo["ID_Domicilio"])

    def test_cancela_su_propio_pedido_pendiente(self):
        pedido = self.crear_pedido()
        self.afirmar_ok(
            self.patch(f"/pedidos/{pedido['ID_Venta']}/cancelar-mi-pedido", self.cliente)
        )
        self.assertEqual(self.venta(pedido["ID_Venta"]).Estado, PEDIDO_CANCELADO)

    def test_no_cancela_el_pedido_de_otro(self):
        pedido = self.crear_pedido()
        respuesta = self.patch(
            f"/pedidos/{pedido['ID_Venta']}/cancelar-mi-pedido", self.otro_cliente
        )
        self.assertIn(respuesta.status_code, (403, 404))
        self.assertEqual(self.venta(pedido["ID_Venta"]).Estado, PEDIDO_PENDIENTE)

    def test_cancelar_devuelve_el_saldo_que_se_habia_usado(self):
        self.dar_saldo(15000)
        pedido = self.crear_pedido(usar_credito=True, credito_monto=15000)
        self.assertEqual(self.saldo(), Decimal("0"))

        self.afirmar_ok(
            self.patch(f"/pedidos/{pedido['ID_Venta']}/cancelar-mi-pedido", self.cliente)
        )
        self.assertEqual(self.saldo(), Decimal("15000"))

    def test_acepta_la_fecha_que_le_propone_el_administrador(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        fecha = (datetime.now() + timedelta(days=3)).isoformat()

        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin, {"fecha_entrega": fecha}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_FECHA_PROPUESTA)

        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aceptar-fecha", self.cliente))
        self.assertIn(
            self.venta(id_venta).Estado, (PEDIDO_CONFIRMADO, PEDIDO_EN_PRODUCCION)
        )

    def test_rechazar_la_fecha_no_cancela_el_pedido(self):
        """Rechazar deja el pedido esperando otra fecha, no lo mata.

        Antes se cancelaba, y el de recoger en tienda se perdía sin que nadie
        pudiera proponer una segunda fecha.
        """
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        fecha = (datetime.now() + timedelta(days=3)).isoformat()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin, {"fecha_entrega": fecha}
        ))

        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/rechazar-fecha", self.cliente))
        venta = self.venta(id_venta)
        self.assertEqual(venta.Estado, PEDIDO_FECHA_RECHAZADA)
        self.assertEqual(venta.intentos_rechazo, 1)

        # Y se le puede proponer otra, que es de lo que se trataba.
        otra = (datetime.now() + timedelta(days=5)).isoformat()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin, {"fecha_entrega": otra}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_FECHA_PROPUESTA)

    def test_no_acepta_la_fecha_de_un_pedido_ajeno(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        fecha = (datetime.now() + timedelta(days=3)).isoformat()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin, {"fecha_entrega": fecha}
        ))

        respuesta = self.patch(f"/ventas/{id_venta}/aceptar-fecha", self.otro_cliente)
        self.assertIn(respuesta.status_code, (403, 404))

    def test_el_cliente_no_entra_al_panel_de_gestion(self):
        self.crear_pedido()
        for ruta in ("/pedidos/", "/ventas/", "/domicilios/", "/devoluciones/"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.get(ruta, self.cliente).status_code, 403)


# ══════════════════════════════════════════════════════════════════════════
# 3. Panel del administrador
# ══════════════════════════════════════════════════════════════════════════
class PanelAdminTests(PanelBase):

    def test_ve_el_pedido_en_su_listado(self):
        self.crear_pedido()
        cuerpo = self.afirmar_ok(self.get("/pedidos/", self.admin))
        self.assertEqual(cuerpo["total"], 1)
        self.assertEqual(cuerpo["pedidos"][0]["estado_label"], "Pendiente")

    def test_confirma_el_pedido_y_reserva_el_stock(self):
        pedido = self.crear_pedido()
        self.confirmar_si_pendiente(pedido['ID_Venta'])
        self.assertEqual(self.venta(pedido["ID_Venta"]).Estado, PEDIDO_CONFIRMADO)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON - 2)

    def test_no_confirma_con_el_comprobante_sin_revisar(self):
        pedido = self.crear_pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        # El pedido queda esperando que alguien mire el comprobante: pedir
        # que se confirme no lo mueve de ahí.
        self.patch(f"/pedidos/{pedido['ID_Venta']}/confirmar", self.admin)
        self.assertEqual(
            self.venta(pedido["ID_Venta"]).Estado, PEDIDO_ESPERANDO_PAGO,
            "se confirmó un pedido cuyo comprobante nadie revisó")

    def test_aprobado_el_comprobante_el_pedido_se_confirma(self):
        pedido = self.crear_pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/aprobar-comprobante", self.admin))
        self.assertEqual(self.venta(id_venta).Estado_Pago, "pagado_completo")

        self.confirmar_si_pendiente(id_venta)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CONFIRMADO)

    def test_el_comprobante_rechazado_bloquea_la_confirmacion(self):
        pedido = self.crear_pedido(
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/rechazar-comprobante", self.admin,
            {"motivo": "La imagen no se ve"},
        ))
        # Rechazado el comprobante, el pedido no avanza por más que se pida
        # confirmarlo: el cliente tiene que mandar uno que sirva.
        self.patch(f"/pedidos/{id_venta}/confirmar", self.admin)
        self.assertNotEqual(
            self.venta(id_venta).Estado, PEDIDO_CONFIRMADO,
            "se confirmó un pedido con el comprobante rechazado")

    def test_registra_el_cobro_en_efectivo(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/registrar-cobro", self.admin,
            {"recibido": True, "monto": 20000},
        ))
        self.assertEqual(self.venta(id_venta).Estado_Pago, "efectivo_recibido")

    def test_el_recorrido_completo_de_un_pedido_en_tienda(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.llevar_a_listo(id_venta)
        self.cobrar_en_tienda(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_ENTREGADO}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_ENTREGADO)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON - 2)
        self.assertIsNotNone(self.venta(id_venta).Fecha_entrega)

    def test_cancelar_un_pedido_confirmado_devuelve_el_stock(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON - 2)

        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CANCELADO)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON)

    def test_no_entrega_en_tienda_sin_registrar_el_cobro(self):
        """La misma regla del domicilio, ahora también en el mostrador."""
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.llevar_a_listo(id_venta)
        respuesta = self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_ENTREGADO}
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("efectivo", self.detalle(respuesta).lower())
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_LISTO)

    def test_declarar_que_no_se_cobro_tambien_deja_entregar_en_tienda(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.llevar_a_listo(id_venta)
        self.afirmar_ok(self.patch(
            f"/pedidos/{id_venta}/registrar-cobro", self.admin,
            {"recibido": False, "motivo": "se lo llevó y paga el lunes"},
        ))
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_ENTREGADO}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_ENTREGADO)

    def test_un_empleado_sin_permiso_no_toca_los_pedidos(self):
        from panel import ROL_EMPLEADO, _token
        from src.shared.services.models import Usuario
        self.db.add(Usuario(
            ID_Usuario=99, Nombre="Emi", Apellidos="Empleado",
            Correo="emi@toston.test", ID_Rol=ROL_EMPLEADO, Estado=1,
        ))
        self.db.commit()
        sin_permiso = {"Authorization": "Bearer " + _token(99, "empleado", "Empleado")}

        self.crear_pedido()
        self.assertEqual(self.get("/pedidos/", sin_permiso).status_code, 403)


# ══════════════════════════════════════════════════════════════════════════
# 4. Producción, desde el panel
# ══════════════════════════════════════════════════════════════════════════
class PanelProduccionTests(PanelBase):

    def test_la_orden_aparece_en_el_listado_del_panel(self):
        self.pedido_con_faltante()
        cuerpo = self.afirmar_ok(self.get("/ordenes-produccion/", self.admin))
        self.assertEqual(cuerpo["total"], 1)
        orden = cuerpo["ordenes"][0]
        self.assertEqual(orden["nombre_producto"], "Torta Tropical")
        self.assertEqual(orden["Cantidad"], 6 - STOCK_TORTA)
        self.assertEqual(orden["Estado"], ORDEN_PENDIENTE)

    def test_iniciarla_aparta_los_insumos_y_completarla_los_descuenta(self):
        pedido = self.pedido_con_faltante()
        # La orden de un pedido solo se gestiona a mano con el pedido confirmado.
        self.confirmar_si_pendiente(pedido['ID_Venta'])
        id_orden = self.orden(pedido["ID_Venta"]).ID_Orden_Produccion

        self.afirmar_ok(self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_EN_PROCESO},
        ))
        # Apartada, no gastada: la harina sigue en bodega.
        self.assertAlmostEqual(self.harina(), STOCK_HARINA, places=3)

        self.afirmar_ok(self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_COMPLETADA},
        ))
        gastado = GRAMOS_POR_TORTA * (6 - STOCK_TORTA)
        self.assertAlmostEqual(self.harina(), STOCK_HARINA - gastado, places=3)
        # FEFO: primero se vacía el lote que vence antes.
        self.assertAlmostEqual(float(self.lote_compra(1).Cantidad_Actual), 200.0, places=3)
        self.assertAlmostEqual(float(self.lote_compra(2).Cantidad_Actual), 3000.0, places=3)

    def test_completarla_repone_el_producto_y_crea_su_lote(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.hornear(id_venta)   # confirma el pedido y luego produce

        # Al confirmar (recoger en tienda) se reservan las 2 de vitrina; al
        # completar la orden entran las 4 horneadas → quedan esas 4.
        self.assertEqual(self.stock(ID_TORTA), 6 - STOCK_TORTA)
        lote = self.lote_producto()
        self.assertIsNotNone(lote)
        self.assertEqual(lote.Cantidad, 6 - STOCK_TORTA)

    def test_el_pedido_no_pasa_a_listo_con_la_orden_abierta(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_EN_PRODUCCION)

        respuesta = self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_LISTO}
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("producción", self.detalle(respuesta).lower())

    def test_completada_la_orden_el_pedido_queda_listo(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.hornear(id_venta)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_LISTO)

    def test_sin_insumos_la_orden_no_arranca_y_no_toca_nada(self):
        pedido = self.pedido_con_faltante()
        self.confirmar_si_pendiente(pedido['ID_Venta'])
        id_orden = self.orden(pedido["ID_Venta"]).ID_Orden_Produccion
        from src.shared.services.models import Insumo
        insumo = self.db.query(Insumo).filter(Insumo.ID_Insumo == ID_HARINA).first()
        insumo.Stock_Actual = 100.0
        self.db.commit()

        respuesta = self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_EN_PROCESO},
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("insuficiente", self.detalle(respuesta).lower())
        self.assertEqual(self.orden().Estado, ORDEN_PENDIENTE)
        self.assertAlmostEqual(self.harina(), 100.0, places=3)

    def test_no_se_cancela_por_separado_la_orden_de_un_pedido(self):
        """3.12 — desde el panel de producción no se cancela la orden de un
        pedido: se cancela cancelando el pedido."""
        pedido = self.pedido_con_faltante()
        self.confirmar_si_pendiente(pedido['ID_Venta'])
        id_orden = self.orden(pedido["ID_Venta"]).ID_Orden_Produccion
        self.afirmar_ok(self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_EN_PROCESO},
        ))
        respuesta = self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_CANCELADA},
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("pedido", self.detalle(respuesta).lower())
        # Nada se tocó: la orden sigue en proceso con sus insumos apartados.
        self.assertEqual(self.orden().Estado, ORDEN_EN_PROCESO)
        self.assertAlmostEqual(self.harina(), STOCK_HARINA, places=3)

    def test_el_inventario_cierra_al_entregar_en_tienda(self):
        """El faltante horneado también tiene que salir del stock."""
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.hornear(id_venta)
        self.afirmar_ok(self.post(
            f"/ventas/{id_venta}/registrar-pago-final", self.admin,
            {"monto": 30000, "metodo_pago": "Efectivo"},
        ))
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_ENTREGADO}
        ))
        self.assertEqual(self.stock(ID_TORTA), 0)


# ══════════════════════════════════════════════════════════════════════════
# 5. Panel del domiciliario
# ══════════════════════════════════════════════════════════════════════════
class PanelDomiciliarioTests(PanelBase):
    """Lo que ve y hace el repartidor desde su app."""

    def preparar_domicilio(self, aprobar_comprobante=False, **kw):
        """Pedido a domicilio, confirmado, listo y asignado al repartidor.

        El pedido que llega con comprobante no se confirma hasta que alguien
        lo aprueba, así que el recorrido del repartidor arranca después de
        ese paso.
        """
        pedido = self.crear_pedido(domicilio=self.direccion(), **kw)
        id_venta = pedido["ID_Venta"]
        if aprobar_comprobante:
            self.afirmar_ok(self.patch(
                f"/pedidos/{id_venta}/aprobar-comprobante", self.admin
            ))
        self.confirmar_si_pendiente(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_LISTO}
        ))
        dom = self.domicilio(id_venta)
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/repartidor", self.admin,
            {"ID_Empleado": ID_REPARTIDOR},
        ))
        return id_venta, dom.ID_Domicilio

    def test_asignarlo_lo_pasa_a_asignado(self):
        _, id_dom = self.preparar_domicilio()
        self.assertEqual(self.domicilio().Estado, DOM_ASIGNADO)
        self.assertEqual(self.domicilio().ID_Empleado, ID_REPARTIDOR)

    def test_el_repartidor_ve_su_resumen_del_dia(self):
        self.preparar_domicilio()
        cuerpo = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        self.assertEqual(cuerpo["activos"], 1)
        self.assertEqual(cuerpo["entregados_hoy"], 0)

    def test_el_listado_solo_le_muestra_lo_suyo(self):
        self.preparar_domicilio()
        # Un segundo domicilio, de otro repartidor.
        pedido = self.crear_pedido(domicilio=self.direccion())
        otro = self.domicilio(pedido["ID_Venta"])
        self.afirmar_ok(self.patch(
            f"/domicilios/{otro.ID_Domicilio}/repartidor", self.admin,
            {"ID_Empleado": ID_OTRO_REPARTIDOR},
        ))

        cuerpo = self.afirmar_ok(self.get("/domicilios/", self.repartidor))
        self.assertEqual(cuerpo["total"], 1)
        self.assertEqual(cuerpo["domicilios"][0]["ID_Empleado"], ID_REPARTIDOR)

    def test_no_abre_el_domicilio_de_otro_repartidor(self):
        _, id_dom = self.preparar_domicilio()
        respuesta = self.get(f"/domicilios/{id_dom}", self.otro_repartidor)
        self.assertEqual(respuesta.status_code, 403)

    def test_no_cambia_el_estado_de_un_domicilio_ajeno(self):
        _, id_dom = self.preparar_domicilio()
        respuesta = self.patch(
            f"/domicilios/{id_dom}/estado", self.otro_repartidor,
            {"Estado": DOM_EN_CAMINO},
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_el_detalle_trae_lo_que_necesita_para_entregar(self):
        _, id_dom = self.preparar_domicilio()
        cuerpo = self.afirmar_ok(self.get(f"/domicilios/{id_dom}", self.repartidor))
        self.assertEqual(cuerpo["telefono_cliente"], "3001234567")
        self.assertEqual(cuerpo["Direccion_entrega"], "Calle 10 #20-30")
        self.assertEqual(cuerpo["metodo_pago"], "Efectivo")
        self.assertTrue(cuerpo["productos"])
        self.assertEqual(cuerpo["indicaciones_cliente"], "Portón verde")
        # El código de entrega se quitó del flujo: ya no viaja en la respuesta.
        self.assertNotIn("otp", cuerpo)

    def test_sale_en_camino_y_el_pedido_lo_sigue(self):
        id_venta, id_dom = self.preparar_domicilio()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_EN_CAMINO}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_EN_CAMINO)

    def test_no_entrega_sin_registrar_el_cobro_en_efectivo(self):
        _, id_dom = self.preparar_domicilio()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_EN_CAMINO}
        ))
        respuesta = self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_ENTREGADO}
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("cobro", self.detalle(respuesta).lower())

    def test_registrado_el_cobro_entrega_y_descuenta_el_stock(self):
        id_venta, id_dom = self.preparar_domicilio()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_EN_CAMINO}
        ))
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/registrar-pago-efectivo", self.repartidor,
            {"recibido": True, "monto": 25000},
        ))
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_ENTREGADO}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_ENTREGADO)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON - 2)

    def test_el_cobro_exige_el_monto_exacto(self):
        _, id_dom = self.preparar_domicilio()
        respuesta = self.patch(
            f"/domicilios/{id_dom}/registrar-pago-efectivo", self.repartidor,
            {"recibido": True, "monto": 1000},
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_declarar_que_no_cobro_exige_un_motivo(self):
        _, id_dom = self.preparar_domicilio()
        respuesta = self.patch(
            f"/domicilios/{id_dom}/registrar-pago-efectivo", self.repartidor,
            {"recibido": False, "motivo": "no"},
        )
        self.assertIn(respuesta.status_code, (400, 422))

    def test_declarar_que_no_cobro_con_motivo_deja_entregar(self):
        id_venta, id_dom = self.preparar_domicilio()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_EN_CAMINO}
        ))
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/registrar-pago-efectivo", self.repartidor,
            {"recibido": False, "motivo": "el cliente no tenia el efectivo"},
        ))
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_ENTREGADO}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_ENTREGADO)

    def test_el_cobro_no_se_registra_dos_veces(self):
        _, id_dom = self.preparar_domicilio()
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/registrar-pago-efectivo", self.repartidor,
            {"recibido": True, "monto": 25000},
        ))
        respuesta = self.patch(
            f"/domicilios/{id_dom}/registrar-pago-efectivo", self.repartidor,
            {"recibido": True, "monto": 25000},
        )
        self.assertEqual(respuesta.status_code, 409)

    def test_entregar_ya_no_pide_ningun_codigo(self):
        """El código de entrega se retiró: sus endpoints ya no existen."""
        _, id_dom = self.preparar_domicilio()
        for ruta in (f"/domicilios/{id_dom}/verificar-otp",
                     f"/domicilios/{id_dom}/regenerar-otp"):
            with self.subTest(ruta=ruta):
                respuesta = self.post(ruta, self.repartidor, {"codigo": "123456"})
                self.assertEqual(respuesta.status_code, 404)
        self.assertIsNone(self.domicilio().OTP)

    def test_el_chat_lo_ven_el_cliente_y_su_repartidor(self):
        _, id_dom = self.preparar_domicilio()
        self.afirmar_ok(self.post(
            f"/domicilios/{id_dom}/mensajes", self.repartidor, {"Contenido": "Voy llegando"}
        ))
        self.afirmar_ok(self.post(
            f"/domicilios/{id_dom}/mensajes", self.cliente, {"Contenido": "Gracias"}
        ))
        mensajes = self.afirmar_ok(self.get(f"/domicilios/{id_dom}/mensajes", self.cliente))
        self.assertEqual(len(mensajes), 2)
        self.assertEqual(mensajes[0]["Tipo_Remitente"], "domiciliario")

    def test_el_chat_no_lo_ve_un_extraño(self):
        _, id_dom = self.preparar_domicilio()
        for quien, etiqueta in ((self.otro_cliente, "otro cliente"),
                                (self.otro_repartidor, "otro repartidor")):
            with self.subTest(quien=etiqueta):
                respuesta = self.get(f"/domicilios/{id_dom}/mensajes", quien)
                self.assertEqual(respuesta.status_code, 403)

    def test_el_pedido_mixto_pide_cobrar_solo_la_parte_en_efectivo(self):
        id_venta, id_dom = self.preparar_domicilio(
            aprobar_comprobante=True,
            Metodo_Pago="Mixto",
            pago_efectivo_monto=10000,
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        cuerpo = self.afirmar_ok(self.get(f"/domicilios/{id_dom}", self.repartidor))
        self.assertEqual(Decimal(str(cuerpo["monto_efectivo"])), Decimal("10000.00"))

    def test_el_mixto_no_se_entrega_solo_con_el_comprobante_aprobado(self):
        id_venta, id_dom = self.preparar_domicilio(
            aprobar_comprobante=True,
            Metodo_Pago="Mixto",
            pago_efectivo_monto=10000,
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_EN_CAMINO}
        ))
        respuesta = self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_ENTREGADO}
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("efectivo", self.detalle(respuesta).lower())


# ══════════════════════════════════════════════════════════════════════════
# 6. Devoluciones
# ══════════════════════════════════════════════════════════════════════════
class DevolucionesTests(PanelBase):

    def pedido_entregado(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.llevar_a_listo(id_venta)
        self.cobrar_en_tienda(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_ENTREGADO}
        ))
        return id_venta

    def cuerpo_devolucion(self, id_venta, **kw):
        cuerpo = {
            "ID_Venta": id_venta,
            "Motivo": "Llegó en mal estado",
            "productos": [
                {"ID_Producto": ID_TOSTON, "Cantidad": 1, "PrecioUnitario": 10000}
            ],
        }
        cuerpo.update(kw)
        return cuerpo

    def test_el_cliente_pide_la_devolucion_de_su_pedido_entregado(self):
        id_venta = self.pedido_entregado()
        cuerpo = self.afirmar_ok(
            self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)), 201
        )
        self.assertEqual(cuerpo["Estado"], DEV_PENDIENTE)
        self.assertEqual(Decimal(cuerpo["TotalDevuelto"]), Decimal("10000"))

    def test_no_se_puede_devolver_un_pedido_que_no_se_entrego(self):
        pedido = self.crear_pedido()
        respuesta = self.post(
            "/devoluciones/", self.cliente, self.cuerpo_devolucion(pedido["ID_Venta"])
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("entregados", self.detalle(respuesta).lower())

    def test_no_se_puede_devolver_el_pedido_de_otro(self):
        id_venta = self.pedido_entregado()
        respuesta = self.post(
            "/devoluciones/", self.otro_cliente, self.cuerpo_devolucion(id_venta)
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_no_se_puede_pedir_dos_veces_por_el_mismo_pedido(self):
        id_venta = self.pedido_entregado()
        self.afirmar_ok(
            self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)), 201
        )
        respuesta = self.post(
            "/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("activa", self.detalle(respuesta).lower())

    def test_no_se_puede_devolver_un_producto_que_no_se_compro(self):
        id_venta = self.pedido_entregado()
        respuesta = self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(
            id_venta,
            productos=[{"ID_Producto": ID_TORTA, "Cantidad": 1, "PrecioUnitario": 10000}],
        ))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("no pertenece", self.detalle(respuesta).lower())

    def test_no_se_pueden_devolver_mas_unidades_de_las_compradas(self):
        id_venta = self.pedido_entregado()
        respuesta = self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(
            id_venta,
            productos=[{"ID_Producto": ID_TOSTON, "Cantidad": 5, "PrecioUnitario": 10000}],
        ))
        self.assertEqual(respuesta.status_code, 400)

    def test_pasado_el_plazo_ya_no_se_puede_pedir(self):
        id_venta = self.pedido_entregado()
        venta = self.venta(id_venta)
        # Atado a la constante: con un número fijo la prueba se queda atrás
        # cada vez que el plazo cambia, y deja de probar lo que dice probar.
        venta.Fecha_entrega = datetime.now() - timedelta(
            hours=HORAS_LIMITE_DEVOLUCION + 4)
        self.db.commit()

        respuesta = self.post(
            "/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("plazo", self.detalle(respuesta).lower())

    def test_aprobarla_le_devuelve_el_saldo_al_cliente(self):
        id_venta = self.pedido_entregado()
        devolucion = self.afirmar_ok(
            self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)), 201
        )
        self.afirmar_ok(self.patch(
            f"/devoluciones/{devolucion['ID_Devolucion']}/resolver", self.admin,
            {"Estado": DEV_APROBADA, "Comentario": "Procede"},
        ))
        self.assertEqual(self.saldo(), Decimal("10000"))

    def test_rechazarla_no_le_devuelve_nada(self):
        id_venta = self.pedido_entregado()
        devolucion = self.afirmar_ok(
            self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)), 201
        )
        self.afirmar_ok(self.patch(
            f"/devoluciones/{devolucion['ID_Devolucion']}/resolver", self.admin,
            {"Estado": DEV_RECHAZADA, "Comentario": "No procede"},
        ))
        self.assertEqual(self.saldo(), Decimal("0"))

    def test_el_cliente_ve_sus_devoluciones_y_no_las_ajenas(self):
        id_venta = self.pedido_entregado()
        self.afirmar_ok(
            self.post("/devoluciones/", self.cliente, self.cuerpo_devolucion(id_venta)), 201
        )
        cuerpo = self.afirmar_ok(self.get("/devoluciones/mis-devoluciones", self.cliente))
        self.assertEqual(cuerpo["total"], 1)

        ajenas = self.afirmar_ok(
            self.get("/devoluciones/mis-devoluciones", self.otro_cliente)
        )
        self.assertEqual(ajenas["total"], 0)

    def test_el_precio_de_la_devolucion_lo_pone_el_servidor(self):
        """El cliente no puede declarar cuánto vale lo que devuelve.

        `PrecioUnitario` llega en el cuerpo y termina en `TotalDevuelto`, que al
        aprobarse se abona como saldo a favor. Si el servidor lo acepta tal
        cual, un pedido de $20.000 puede pedir la devolución de un millón.
        """
        id_venta = self.pedido_entregado()
        cuerpo = self.afirmar_ok(self.post(
            "/devoluciones/", self.cliente, self.cuerpo_devolucion(
                id_venta,
                productos=[
                    {"ID_Producto": ID_TOSTON, "Cantidad": 1,
                     "PrecioUnitario": 1000000}
                ],
            )), 201)
        self.assertEqual(
            Decimal(cuerpo["TotalDevuelto"]), PRECIO,
            "el cliente fijó el monto a devolver",
        )
        self.assertEqual(Decimal(cuerpo["productos"][0]["PrecioUnitario"]), PRECIO)

        # Y aprobarla abona el precio real, no el declarado.
        self.afirmar_ok(self.patch(
            f"/devoluciones/{cuerpo['ID_Devolucion']}/resolver", self.admin,
            {"Estado": DEV_APROBADA},
        ))
        self.assertEqual(self.saldo(), PRECIO)

    def test_no_se_devuelve_mas_de_lo_que_se_facturó(self):
        """Tope contra una subida de precios posterior a la compra.

        El precio del catálogo es el de hoy y el pedido pudo comprarse con
        otro; sin el tope, devolver saldría ganancia.
        """
        id_venta = self.pedido_entregado()
        from src.shared.services.models import Producto
        producto = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TOSTON
        ).first()
        producto.Precio_venta = PRECIO * 10
        self.db.commit()

        cuerpo = self.afirmar_ok(self.post(
            "/devoluciones/", self.cliente, self.cuerpo_devolucion(
                id_venta,
                productos=[{"ID_Producto": ID_TOSTON, "Cantidad": 2,
                            "PrecioUnitario": 100000}],
            )), 201)
        # Se pagó $20.000 por las dos unidades: no se devuelve más que eso.
        self.assertEqual(Decimal(cuerpo["TotalDevuelto"]), Decimal("20000"))


# ══════════════════════════════════════════════════════════════════════════
# 7. Cancelar: lo que hay que devolver y lo que hay que cerrar
# ══════════════════════════════════════════════════════════════════════════
class CancelarTests(PanelBase):
    """Un pedido cancelado tiene que dejar todo como estaba.

    Es el recorrido donde más cosas quedan a medias: el saldo que el cliente
    puso, el stock que se le reservó, la orden de producción que se abrió y
    los insumos que esa orden ya gastó.
    """

    def domicilio_en_curso(self, **kw):
        pedido = self.crear_pedido(domicilio=self.direccion(), **kw)
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_LISTO}
        ))
        dom = self.domicilio(id_venta)
        self.afirmar_ok(self.patch(
            f"/domicilios/{dom.ID_Domicilio}/repartidor", self.admin,
            {"ID_Empleado": ID_REPARTIDOR},
        ))
        return id_venta, dom.ID_Domicilio

    def test_cancelar_desde_el_panel_de_reparto_devuelve_el_saldo(self):
        """El mismo pedido cancelado por el otro camino sí lo devolvía.

        El módulo de domicilios escribía el estado de la venta a mano, saltando
        toda la devolución: al cliente le cancelaban el pedido y perdía la
        plata que había puesto.
        """
        self.dar_saldo(15000)
        id_venta, id_dom = self.domicilio_en_curso(
            usar_credito=True, credito_monto=15000,
        )
        self.assertEqual(self.saldo(), Decimal("0"))

        self.afirmar_ok(self.patch(
            f"/domicilios/{id_dom}/estado", self.repartidor, {"Estado": DOM_CANCELADO}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CANCELADO)
        self.assertEqual(self.domicilio(id_venta).Estado, DOM_CANCELADO)
        self.assertEqual(self.saldo(), Decimal("15000"))

    def test_cancelar_desde_gestion_cierra_el_domicilio(self):
        id_venta, _ = self.domicilio_en_curso()
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        self.assertEqual(self.domicilio(id_venta).Estado, DOM_CANCELADO)

    def test_cancelar_cierra_la_orden_de_produccion_del_pedido(self):
        """Si no, el panel de producción queda con trabajo de un pedido muerto."""
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.assertEqual(self.orden(id_venta).Estado, ORDEN_PENDIENTE)

        # Ya no lo cancela el cliente: en producción la decisión es de la
        # panadería.
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        self.assertEqual(self.orden(id_venta).Estado, ORDEN_CANCELADA)

    def test_cancelar_con_la_orden_ya_empezada_suelta_los_insumos(self):
        """La harina nunca salió de bodega: se suelta la reserva y ya."""
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        id_orden = self.orden(id_venta).ID_Orden_Produccion
        self.afirmar_ok(self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_EN_PROCESO},
        ))

        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        self.assertEqual(self.orden(id_venta).Estado, ORDEN_CANCELADA)
        self.assertAlmostEqual(self.harina(), STOCK_HARINA, places=3)

    def test_lo_ya_horneado_se_queda_en_el_stock(self):
        """Las tortas existen: no se tiran porque el cliente se arrepienta."""
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.hornear(id_venta)
        self.assertEqual(self.stock(ID_TORTA), 6 - STOCK_TORTA)

        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        # Vuelven también las 2 que se habían reservado de la vitrina.
        self.assertEqual(self.stock(ID_TORTA), 6)

    def test_un_pedido_entregado_ya_no_se_cancela(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.llevar_a_listo(id_venta)
        self.cobrar_en_tienda(id_venta)
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_ENTREGADO}
        ))
        respuesta = self.patch(f"/pedidos/{id_venta}/cancelar", self.admin)
        self.assertEqual(respuesta.status_code, 404)

    def test_el_anticipo_vuelve_solo_si_no_se_alcanzo_a_hornear(self):
        """Sin hornear la panadería no gastó nada: la plata del cliente vuelve.

        Horneado es otra cosa: los insumos ya se fueron, y qué pasa con esa
        plata lo acuerdan el cliente y quien atiende. El sistema no decide por
        ellos ni le abona nada a nadie por su cuenta.
        """
        for producido in (False, True):
            with self.subTest(ya_producido=producido):
                self.setUp()
                pedido = self.pedido_con_faltante()
                id_venta = pedido["ID_Venta"]
                self.confirmar_si_pendiente(id_venta)
                anticipo = Decimal(str(self.venta(id_venta).Anticipo_Monto or 0))
                self.assertGreater(anticipo, 0, "el pedido tiene que pedir anticipo")
                # El anticipo, cobrado. Solo se devuelve lo que de verdad
                # entró: el exigido no es plata que esté en la caja.
                venta = self.venta(id_venta)
                venta.Anticipo_Registrado = 1
                self.db.commit()
                if producido:
                    self.hornear(id_venta)

                self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
                self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CANCELADO)
                self.assertEqual(
                    self.saldo(),
                    Decimal("0") if producido else anticipo,
                    "horneado no vuelve solo; sin hornear sí",
                )

    def test_el_saldo_a_favor_del_cliente_si_vuelve(self):
        """Es plata suya que puso en el pedido y nunca llegó a gastarse.

        El saldo que ya tenía en la casa vuelve siempre: no es el anticipo, es
        plata que aplicó al pagar. Y como este pedido no se alcanzó a hornear,
        el anticipo vuelve también.
        """
        self.dar_saldo(60000)
        pedido = self.pedido_con_faltante(usar_credito=True, credito_monto=60000)
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.assertEqual(self.saldo(), Decimal("0"))
        venta = self.venta(id_venta)
        anticipo = (Decimal(str(venta.Anticipo_Monto or 0))
                    if venta.Anticipo_Registrado else Decimal("0"))

        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        self.assertEqual(self.saldo(), Decimal("60000") + anticipo)

    def test_el_cliente_solo_cancela_mientras_este_pendiente(self):
        """Aceptado el pedido, la cancelación la decide la panadería."""
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)

        respuesta = self.patch(f"/pedidos/{id_venta}/cancelar-mi-pedido", self.cliente)
        self.assertEqual(respuesta.status_code, 400)
        # Se comprueba que el rechazo le explique al cliente qué hacer, no la
        # redacción exacta: atarse a una palabra convierte cualquier arreglo de
        # estilo en una prueba roja.
        detalle = self.detalle(respuesta).lower()
        self.assertIn("no puede cancelarse", detalle)
        self.assertIn("escríbenos", detalle)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CONFIRMADO)

    def test_el_cliente_tampoco_cancela_lo_que_ya_esta_en_produccion(self):
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_EN_PRODUCCION)

        respuesta = self.patch(f"/pedidos/{id_venta}/cancelar-mi-pedido", self.cliente)
        self.assertEqual(respuesta.status_code, 400)

    def test_la_panaderia_si_puede_cancelar_lo_que_ya_acepto(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CANCELADO)

    def test_no_se_cancela_dos_veces(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.patch(f"/pedidos/{id_venta}/cancelar", self.admin))
        respuesta = self.patch(f"/pedidos/{id_venta}/cancelar", self.admin)
        self.assertEqual(respuesta.status_code, 404)


# ══════════════════════════════════════════════════════════════════════════
# 8. La máquina de estados y los accesos
# ══════════════════════════════════════════════════════════════════════════
class EstadosYAccesosTests(PanelBase):

    def test_un_pedido_pendiente_no_salta_pasos(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        for estado, nombre in ((PEDIDO_ENTREGADO, "entregado"),
                               (PEDIDO_LISTO, "listo"),
                               (PEDIDO_EN_CAMINO, "en camino")):
            with self.subTest(destino=nombre):
                respuesta = self.patch(
                    f"/ventas/{id_venta}/estado", self.admin, {"Estado": estado}
                )
                self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_PENDIENTE)

    def test_un_pedido_para_recoger_no_sale_en_camino(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.llevar_a_listo(id_venta)
        respuesta = self.patch(
            f"/ventas/{id_venta}/estado", self.admin, {"Estado": PEDIDO_EN_CAMINO}
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_confirmar_dos_veces_no_descuenta_el_stock_dos_veces(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.confirmar_si_pendiente(id_venta)
        self.patch(f"/pedidos/{id_venta}/confirmar", self.admin)
        self.assertEqual(self.stock(ID_TOSTON), STOCK_TOSTON - 2)

    def test_el_repartidor_no_entra_a_los_otros_modulos(self):
        for ruta in ("/pedidos/", "/ventas/", "/devoluciones/", "/ordenes-produccion/"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.get(ruta, self.repartidor).status_code, 403)

    def test_sin_token_no_se_entra_a_ningun_panel(self):
        for ruta in ("/pedidos/", "/domicilios/", "/ventas/mis-ventas"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.get(ruta, {}).status_code, 401)

    def test_una_cuenta_desactivada_no_entra(self):
        from src.shared.services.models import Usuario
        usuario = self.db.query(Usuario).filter(
            Usuario.ID_Usuario == ID_CLIENTE
        ).first()
        usuario.Estado = 2
        self.db.commit()
        respuesta = self.get("/ventas/mis-ventas", self.cliente)
        self.assertEqual(respuesta.status_code, 401)

    def test_el_listado_de_repartidores_alimenta_el_selector(self):
        cuerpo = self.afirmar_ok(self.get("/domicilios/repartidores", self.admin))
        ids = {r["id"] for r in cuerpo}
        self.assertEqual(ids, {ID_REPARTIDOR, ID_OTRO_REPARTIDOR})


# ══════════════════════════════════════════════════════════════════════════
# 9. Editar un pedido desde el panel
# ══════════════════════════════════════════════════════════════════════════
class EditarPedidoTests(PanelBase):
    """Cambiar el tipo de entrega tiene que mover el total y armar el domicilio."""

    def test_pasar_a_domicilio_cobra_el_envio(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin, {
            "Domicilio": True,
            "Direccion_Entrega": "Cra 50 #1-2",
            "ID_Barrio": ID_BARRIO,
        }))
        self.assertEqual(
            Decimal(str(self.venta(id_venta).Total)), Decimal("20000") + COSTO_DOMICILIO
        )

    def test_el_domicilio_agregado_nace_con_un_estado_valido(self):
        """Se creaba con el estado 1, que es "Pendiente" de un PEDIDO.

        No es un estado válido de domicilio, así que el panel lo listaba sin
        etiqueta.
        """
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin, {
            "Domicilio": True,
            "Direccion_Entrega": "Cra 50 #1-2",
            "ID_Barrio": ID_BARRIO,
        }))
        self.assertEqual(self.domicilio(id_venta).Estado, DOM_PENDIENTE)

        listado = self.afirmar_ok(self.get("/domicilios/", self.admin))
        self.assertEqual(listado["domicilios"][0]["estado_label"], "Pendiente")

    def test_quitar_el_domicilio_devuelve_el_envio(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        id_venta = pedido["ID_Venta"]
        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin, {"Domicilio": False}))
        self.assertEqual(Decimal(str(self.venta(id_venta).Total)), Decimal("20000"))
        self.assertIsNone(self.domicilio(id_venta))

    def test_guardar_dos_veces_no_cobra_el_envio_dos_veces(self):
        pedido = self.crear_pedido()
        id_venta = pedido["ID_Venta"]
        cuerpo = {
            "Domicilio": True,
            "Direccion_Entrega": "Cra 50 #1-2",
            "ID_Barrio": ID_BARRIO,
        }
        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin, cuerpo))
        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin, cuerpo))
        self.assertEqual(
            Decimal(str(self.venta(id_venta).Total)), Decimal("20000") + COSTO_DOMICILIO
        )

    def test_editar_sin_tocar_la_entrega_no_mueve_el_total(self):
        pedido = self.crear_pedido(domicilio=self.direccion())
        id_venta = pedido["ID_Venta"]
        antes = Decimal(str(self.venta(id_venta).Total))
        self.afirmar_ok(self.put(f"/pedidos/{id_venta}", self.admin, {
            "Metodo_Pago": "Transferencia",
        }))
        self.assertEqual(Decimal(str(self.venta(id_venta).Total)), antes)


# ══════════════════════════════════════════════════════════════════════════
# 10. El día del repartidor: resumen e historial
# ══════════════════════════════════════════════════════════════════════════
class DiaDelRepartidorTests(PanelBase):
    """Lo que el panel del domiciliario le dice que hizo hoy.

    El caso que lo destapó: el repartidor entregó dos pedidos, uno de ellos de
    un pedido que había entrado ayer. El resumen decía 2 entregas y el
    historial le mostraba 1, en la misma pantalla. El rango de fechas se medía
    contra `Fecha_asignacion`, que pese al nombre es la fecha en que se CREÓ el
    domicilio: nadie la toca al asignarle repartidor.
    """

    def test_el_historial_de_hoy_trae_lo_entregado_hoy(self):
        de_ayer = self.entrega_del_repartidor(creado_hace=1, entregado_hace=0)
        de_hoy  = self.entrega_del_repartidor(creado_hace=0, entregado_hace=0)
        self.entrega_del_repartidor(creado_hace=5, entregado_hace=5)

        desde, hasta = self.rango_de_hoy()
        cuerpo = self.afirmar_ok(self.get(
            f"/domicilios/?por_pagina=100&id_empleado={ID_REPARTIDOR}"
            f"&fecha_inicio={desde}&fecha_fin={hasta}", self.repartidor
        ))
        entregados = [d["ID_Domicilio"] for d in cuerpo["domicilios"]
                      if d["estado_label"] == "Entregado"]
        self.assertEqual(sorted(entregados), sorted([de_ayer, de_hoy]))

    def test_el_resumen_y_el_historial_dicen_lo_mismo(self):
        self.entrega_del_repartidor(creado_hace=1, entregado_hace=0)
        self.entrega_del_repartidor(creado_hace=0, entregado_hace=0)
        self.entrega_del_repartidor(creado_hace=3, entregado_hace=3)

        resumen = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        desde, hasta = self.rango_de_hoy()
        cuerpo = self.afirmar_ok(self.get(
            f"/domicilios/?por_pagina=100&id_empleado={ID_REPARTIDOR}"
            f"&fecha_inicio={desde}&fecha_fin={hasta}", self.repartidor
        ))
        entregados = [d for d in cuerpo["domicilios"] if d["estado_label"] == "Entregado"]
        self.assertEqual(resumen["entregados_hoy"], len(entregados))

    def test_lo_que_sigue_abierto_cuenta_por_el_dia_en_que_entro(self):
        """Sin fecha de entrega, el domicilio pertenece al día en que se creó."""
        abierto_hoy = self.entrega_del_repartidor(creado_hace=0, entregado=False)
        self.entrega_del_repartidor(creado_hace=4, entregado=False)

        desde, hasta = self.rango_de_hoy()
        cuerpo = self.afirmar_ok(self.get(
            f"/domicilios/?por_pagina=100&id_empleado={ID_REPARTIDOR}"
            f"&fecha_inicio={desde}&fecha_fin={hasta}", self.repartidor
        ))
        self.assertEqual(
            [d["ID_Domicilio"] for d in cuerpo["domicilios"]], [abierto_hoy]
        )

    def test_el_total_del_dia_son_pesos_y_no_un_conteo(self):
        """Contaba los domicilios CREADOS hoy bajo una etiqueta que promete plata."""
        self.entrega_del_repartidor(creado_hace=1, entregado_hace=0)
        self.entrega_del_repartidor(creado_hace=0, entregado_hace=0)

        resumen = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        # Dos pedidos de $20.000 + $5.000 de envío.
        esperado = float((Decimal("20000") + COSTO_DOMICILIO) * 2)
        self.assertEqual(resumen["entregados_hoy"], 2)
        self.assertEqual(resumen["total_hoy"], esperado)

    def test_el_efectivo_del_dia_es_solo_lo_que_recibio_en_mano(self):
        # Efectivo: entra completo.
        self.entrega_del_repartidor(creado_hace=0, entregado_hace=0)
        # Transferencia: no pasó por sus manos.
        self.entrega_del_repartidor(
            creado_hace=0, entregado_hace=0, estado_pago="pagado_completo",
            Metodo_Pago="Transferencia",
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )

        resumen = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        self.assertEqual(resumen["total_hoy"], float((Decimal("20000") + COSTO_DOMICILIO) * 2))
        self.assertEqual(resumen["efectivo_hoy"], float(Decimal("20000") + COSTO_DOMICILIO))

    def test_del_mixto_solo_cuenta_la_parte_en_efectivo(self):
        self.entrega_del_repartidor(
            creado_hace=0, entregado_hace=0, estado_pago="pagado_completo",
            Metodo_Pago="Mixto", pago_efectivo_monto=9000,
            comprobante_pago="https://cloudinary.test/comp.jpg",
        )
        resumen = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        self.assertEqual(resumen["efectivo_hoy"], 9000.0)

    def test_lo_que_no_se_pudo_cobrar_no_le_cuenta_como_recogido(self):
        self.entrega_del_repartidor(
            creado_hace=0, entregado_hace=0, estado_pago="no_recibido",
        )
        resumen = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        self.assertEqual(resumen["entregados_hoy"], 1)
        self.assertEqual(resumen["efectivo_hoy"], 0.0)

    def test_el_resumen_es_de_cada_repartidor(self):
        self.entrega_del_repartidor(creado_hace=0, entregado_hace=0)
        self.entrega_del_repartidor(
            creado_hace=0, entregado_hace=0, quien=ID_OTRO_REPARTIDOR,
        )

        mio = self.afirmar_ok(self.get("/domicilios/resumen", self.repartidor))
        self.assertEqual(mio["entregados_hoy"], 1)
        del_otro = self.afirmar_ok(self.get("/domicilios/resumen", self.otro_repartidor))
        self.assertEqual(del_otro["entregados_hoy"], 1)

    def test_el_listado_llega_ordenado_por_lo_ultimo_que_paso(self):
        viejo = self.entrega_del_repartidor(creado_hace=9, entregado_hace=9)
        reciente = self.entrega_del_repartidor(creado_hace=9, entregado_hace=0)

        cuerpo = self.afirmar_ok(self.get(
            f"/domicilios/?por_pagina=100&id_empleado={ID_REPARTIDOR}", self.repartidor
        ))
        ids = [d["ID_Domicilio"] for d in cuerpo["domicilios"]]
        self.assertEqual(ids.index(reciente), 0)
        self.assertLess(ids.index(reciente), ids.index(viejo))


# ══════════════════════════════════════════════════════════════════════════
# 11. La fecha propuesta: la mueve el cliente, no el horno
# ══════════════════════════════════════════════════════════════════════════
class FechaPropuestaTests(PanelBase):
    """Un pedido esperando respuesta del cliente no avanza solo.

    Terminar de hornear no responde por él: mientras la fecha esté propuesta,
    el pedido espera. Es la aceptación la que lo pone en marcha, y si para
    entonces ya no falta nada, lo deja Listo directo.
    """

    def esperando_respuesta(self):
        """Pedido con faltante, confirmado y con la fecha ya propuesta."""
        pedido = self.pedido_con_faltante()
        id_venta = pedido["ID_Venta"]
        fecha = (datetime.now() + timedelta(days=3)).isoformat()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin, {"fecha_entrega": fecha}
        ))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_FECHA_PROPUESTA)
        return id_venta

    def test_hornear_con_fecha_propuesta_sin_aceptar_queda_bloqueado(self):
        """El cliente todavía no dijo que sí: la orden no se gestiona a mano
        hasta que acepte o rechace la fecha (ver bloqueo en `cambiar_estado`).

        Reemplaza a los dos tests que asumían que se podía hornear con la
        fecha propuesta y sin aceptar: ese escenario ya no es posible con la
        regla vigente (la orden queda bloqueada, igual que en «Pendiente»).
        """
        id_venta = self.esperando_respuesta()
        id_orden = self.orden(id_venta).ID_Orden_Produccion
        respuesta = self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_EN_PROCESO},
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("fecha", self.detalle(respuesta).lower())
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_FECHA_PROPUESTA)

    def test_aceptar_con_la_produccion_a_medias_lo_manda_a_producir(self):
        id_venta = self.esperando_respuesta()

        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aceptar-fecha", self.cliente))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_EN_PRODUCCION)

    def test_terminada_despues_de_aceptar_el_pedido_queda_listo(self):
        """El camino de siempre: se acepta, se hornea, queda listo."""
        id_venta = self.esperando_respuesta()
        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aceptar-fecha", self.cliente))
        self.hornear(id_venta)
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_LISTO)

    def test_aceptar_no_deja_listo_lo_que_ya_no_se_puede_fabricar(self):
        """Aceptar la fecha no inventa el producto.

        El pedido se hizo cuando la torta tenía receta; después alguien la
        borró y le quitó la marca de producción. El cliente dice que sí a la
        fecha y el pedido queda Confirmado —no Listo—: sigue faltando la
        mercancía y nadie la va a hornear.
        """
        from src.shared.services.models import Producto

        pedido = self.pedido_con_faltante(cantidad=6)
        id_venta = pedido["ID_Venta"]

        torta = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TORTA
        ).first()
        torta.Requiere_Produccion = 0
        self.db.query(FichaTecnica).delete()
        # Y la orden que se había abierto se cancela: nadie la va a hornear.
        for orden in self.db.query(OrdenProduccion).filter(
            OrdenProduccion.ID_Venta == id_venta
        ).all():
            orden.Estado = ORDEN_CANCELADA
        self.db.commit()

        fecha = (datetime.now() + timedelta(days=3)).isoformat()
        self.afirmar_ok(self.patch(
            f"/ventas/{id_venta}/proponer-fecha", self.admin, {"fecha_entrega": fecha}
        ))
        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/aceptar-fecha", self.cliente))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_CONFIRMADO)

        # Y sigue sin poder darse por Listo: la mercancía no existe.
        respuesta = self.patch(f"/ventas/{id_venta}/estado", self.admin,
                               {"Estado": PEDIDO_LISTO})
        self.assertEqual(respuesta.status_code, 400, self.detalle(respuesta))

    def test_lo_que_no_se_fabrica_ni_se_puede_pedir(self):
        """La puerta de entrada: sin receta y sin stock, el pedido se rechaza.

        Antes se creaba y quedaba trabado esperando a que alguien repusiera.
        """
        from src.shared.services.models import Producto
        torta = self.db.query(Producto).filter(
            Producto.ID_Producto == ID_TORTA
        ).first()
        torta.Requiere_Produccion = 0
        self.db.query(FichaTecnica).delete()
        self.db.commit()

        respuesta = self.post("/ventas/", self.cliente, self.cuerpo_pedido(
            productos=[{"ID_Producto": ID_TORTA, "Cantidad": 6}],
        ))
        self.assertEqual(respuesta.status_code, 400, self.detalle(respuesta))
        self.assertIn("no se fabrican por encargo", self.detalle(respuesta))

    def test_rechazar_con_fecha_propuesta_deja_el_pedido_esperando_otra_fecha(self):
        """Rechazar la fecha no depende de que haya producción en curso: la
        orden sigue bloqueada (ver test de bloqueo arriba) y el pedido queda
        esperando una nueva propuesta.
        """
        id_venta = self.esperando_respuesta()

        self.afirmar_ok(self.patch(f"/ventas/{id_venta}/rechazar-fecha", self.cliente))
        self.assertEqual(self.venta(id_venta).Estado, PEDIDO_FECHA_RECHAZADA)


# ══════════════════════════════════════════════════════════════════════════
# 12. La receta se lee en las unidades en que está escrita
# ══════════════════════════════════════════════════════════════════════════
class RecetaEnDistintasUnidadesTests(PanelBase):
    """El caso del azúcar: 4 tortas × 20 g contra 100 kg en bodega.

    Decía "insumos insuficientes" y daba la azúcar por cero. Dos cosas la
    rompían: el servidor comparaba los símbolos tal cual venían escritos, y el
    stock de la ficha ni siquiera llegaba al panel —el esquema lo borraba al
    responder—, así que la pantalla lo buscaba en un listado aparte y, si no
    estaba ahí, asumía cero.
    """

    AZUCAR = 9
    POR_TORTA = 20.0     # gramos de azúcar por torta
    EN_BODEGA = 100.0    # kilos

    def receta_de_azucar(self, unidad_insumo="kg", unidad_ficha="g"):
        from src.shared.services.models import (
            FichaTecnica as _F, FichaTecnicaInsumo as _FI, Insumo as _I,
            LoteCompra as _LC, UnidadMedida as _UM,
        )
        self.db.query(_FI).delete()
        self.db.query(_F).delete()
        self.db.add(_UM(ID_Unidad_Medida=9, Simbolo=unidad_insumo,
                        Unidad_Medida=unidad_insumo))
        self.db.add(_I(ID_Insumo=self.AZUCAR, Nombre="Azúcar blanca",
                       Unidad_Medida=9, Stock_Actual=self.EN_BODEGA,
                       Stock_Minimo=1, Estado=1))
        self.db.add(_LC(
            ID_Lote_Compra=9, ID_Insumo=self.AZUCAR,
            Fecha_Vencimiento=datetime.now() + timedelta(days=200),
            Cantidad_Inicial=self.EN_BODEGA, Cantidad_Actual=self.EN_BODEGA,
            Estado=1,
        ))
        self.db.add(_F(ID_Ficha=9, ID_Producto=ID_TORTA, Version="1", Estado=1,
                       Dias_Vida_Util=5, Vida_Util_Unidad="dias"))
        self.db.add(_FI(ID_Ficha_Insumo=9, ID_Ficha=9, ID_Insumo=self.AZUCAR,
                        Cantidad=self.POR_TORTA, Unidad=unidad_ficha))
        self.db.commit()

    def azucar(self):
        from src.shared.services.models import Insumo as _I
        self.db.expire_all()
        return float(self.db.query(_I).filter(
            _I.ID_Insumo == self.AZUCAR
        ).first().Stock_Actual)

    def iniciar_la_orden(self):
        # La orden se abre cuando el admin aprueba la fecha, no al crear el
        # pedido: antes de eso no hay nada que iniciar.
        pedido = self.pedido_con_faltante_aprobado()  # 6 tortas, stock 2 → orden de 4
        orden = self.orden(pedido["ID_Venta"])
        self.assertEqual(orden.Cantidad, 4)
        return self.patch(
            f"/ordenes-produccion/{orden.ID_Orden_Produccion}/estado",
            self.admin, {"Estado": ORDEN_EN_PROCESO},
        )

    def completar_la_orden(self):
        return self.patch(
            f"/ordenes-produccion/{self.orden().ID_Orden_Produccion}/estado",
            self.admin, {"Estado": ORDEN_COMPLETADA},
        )

    def test_la_orden_arranca_y_al_completarse_descuenta_lo_que_pesa(self):
        self.receta_de_azucar()
        self.afirmar_ok(self.iniciar_la_orden())
        # Apartada: la bodega todavía tiene los 100 kg.
        self.assertAlmostEqual(self.azucar(), self.EN_BODEGA, places=4)

        self.afirmar_ok(self.completar_la_orden())
        # 20 g × 4 = 80 g = 0,08 kg de los 100 que hay.
        self.assertAlmostEqual(self.azucar(), 99.92, places=4)

    def test_da_igual_como_esté_escrita_la_unidad(self):
        for unidad_insumo, unidad_ficha in (("kg", "g"), ("Kg", "gr"),
                                            ("KG", "G"), ("kilos", "gramos")):
            with self.subTest(insumo=unidad_insumo, ficha=unidad_ficha):
                self.setUp()
                self.receta_de_azucar(unidad_insumo, unidad_ficha)
                self.afirmar_ok(self.iniciar_la_orden())
                self.afirmar_ok(self.completar_la_orden())
                self.assertAlmostEqual(self.azucar(), 99.92, places=4)

    def test_el_panel_recibe_el_stock_y_la_unidad_del_insumo(self):
        """Sin estos dos campos el panel no puede comparar nada.

        El esquema de respuesta no los declaraba y Pydantic los borraba, así
        que la pantalla caía a un listado de insumos limitado a 100 y al que no
        estuviera ahí le daba stock cero.
        """
        self.receta_de_azucar()
        producto = self.afirmar_ok(self.get(f"/productos/{ID_TORTA}", self.admin))
        insumo = producto["ficha_tecnica"]["insumos"][0]
        self.assertEqual(insumo["nombre_insumo"], "Azúcar blanca")
        self.assertEqual(insumo["Stock_Actual"], self.EN_BODEGA)
        self.assertEqual(insumo["simbolo_unidad"], "kg")
        self.assertEqual(insumo["Unidad"], "g")

    def test_el_listado_de_productos_también_los_trae(self):
        self.receta_de_azucar()
        listado = self.afirmar_ok(self.get("/productos/?por_pagina=50", self.admin))
        fichas = [p["ficha_tecnica"] for p in listado["productos"]
                  if p.get("ficha_tecnica")]
        self.assertTrue(fichas)
        insumo = fichas[0]["insumos"][0]
        self.assertEqual(insumo["Stock_Actual"], self.EN_BODEGA)
        self.assertEqual(insumo["simbolo_unidad"], "kg")

    def test_cuando_de_verdad_falta_insumo_lo_dice_en_su_unidad(self):
        self.receta_de_azucar()
        from src.shared.services.models import Insumo as _I
        azucar = self.db.query(_I).filter(_I.ID_Insumo == self.AZUCAR).first()
        azucar.Stock_Actual = 0.01          # 10 g, hacen falta 80
        self.db.commit()

        respuesta = self.iniciar_la_orden()
        self.assertEqual(respuesta.status_code, 400)
        detalle = self.detalle(respuesta).lower()
        self.assertIn("insuficiente", detalle)
        self.assertIn("azúcar blanca", detalle)
        self.assertIn("kg", detalle)

    def test_unidades_que_no_se_pueden_comparar_lo_dicen(self):
        """Litros contra gramos: hay que arreglar la ficha, no comprar azúcar."""
        self.receta_de_azucar(unidad_insumo="l", unidad_ficha="g")
        respuesta = self.iniciar_la_orden()
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("no se puede convertir", self.detalle(respuesta).lower())


# ══════════════════════════════════════════════════════════════════════════
# 13. Dos órdenes que necesitan la misma harina
# ══════════════════════════════════════════════════════════════════════════
class InsumoApartadoTests(PanelBase):
    """Arrancar una orden pisa sus insumos; completarla es lo que los gasta.

    Con 2 kg de harina en bodega y dos órdenes que necesitan 2 kg cada una,
    solo una puede arrancar. Antes las dos arrancaban —la primera descontaba y
    la segunda encontraba el stock en cero, o peor, ambas pasaban la validación
    antes de que la otra descontara— y la panadería se quedaba con una masa a
    medias en la mesa.
    """

    HARINA = 1

    def dos_ordenes(self, gramos_por_torta=500.0, harina=4000.0):
        """Dos órdenes de 4 tortas cada una sobre la misma harina.

        Con 500 g por torta, cada orden necesita 2 kg y en bodega hay 4 kg:
        alcanza justo para las dos, y bajando la bodega alcanza para una.
        """
        from src.shared.services.models import (
            FichaTecnicaInsumo as _FI, Insumo as _I, LoteCompra as _LC,
        )
        self.db.query(_FI).filter(_FI.ID_Ficha == 1).update(
            {"Cantidad": gramos_por_torta}
        )
        insumo = self.db.query(_I).filter(_I.ID_Insumo == self.HARINA).first()
        insumo.Stock_Actual = harina
        for lote in self.db.query(_LC).all():
            lote.Cantidad_Actual = harina / 2
            lote.Cantidad_Inicial = harina / 2
        self.db.commit()

        primera = self.pedido_con_faltante()
        segunda = self.pedido_con_faltante()
        self.venta_primera = primera["ID_Venta"]
        self.venta_segunda = segunda["ID_Venta"]
        self.confirmar_si_pendiente(self.venta_primera)
        self.confirmar_si_pendiente(self.venta_segunda)
        return (self.orden_de(self.venta_primera), self.orden_de(self.venta_segunda))

    def orden_de(self, id_venta):
        from src.shared.services.models import OrdenProduccion as _OP
        self.db.expire_all()
        return self.db.query(_OP).filter(
            _OP.ID_Venta == id_venta
        ).first().ID_Orden_Produccion

    def arrancar(self, id_orden):
        return self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_EN_PROCESO},
        )

    def completar(self, id_orden):
        return self.patch(
            f"/ordenes-produccion/{id_orden}/estado", self.admin,
            {"Estado": ORDEN_COMPLETADA},
        )

    def test_la_segunda_orden_no_arranca_con_la_harina_apartada(self):
        """Justo para una: la primera la pisa y la segunda espera."""
        primera, segunda = self.dos_ordenes(harina=2000.0)

        self.afirmar_ok(self.arrancar(primera))
        respuesta = self.arrancar(segunda)

        self.assertEqual(respuesta.status_code, 400)
        detalle = self.detalle(respuesta).lower()
        self.assertIn("apartado por otra orden", detalle)
        self.assertIn("harina", detalle)
        # Y la harina sigue en bodega: apartada, no gastada.
        self.assertAlmostEqual(self.harina(), 2000.0, places=3)

    def test_completada_la_primera_la_segunda_ya_no_puede(self):
        """Ahí la harina sí se gastó: no queda para la otra."""
        primera, segunda = self.dos_ordenes(harina=2000.0)
        self.afirmar_ok(self.arrancar(primera))
        self.afirmar_ok(self.completar(primera))
        self.assertAlmostEqual(self.harina(), 0.0, places=3)

        respuesta = self.arrancar(segunda)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("stock insuficiente", self.detalle(respuesta).lower())

    def test_cancelado_el_primer_pedido_la_segunda_orden_arranca(self):
        """La reserva se suelta sola al dejar de estar en proceso.

        La orden de un pedido no se anula por su cuenta: se cancela el pedido.
        """
        primera, segunda = self.dos_ordenes(harina=2000.0)
        self.afirmar_ok(self.arrancar(primera))
        self.assertEqual(self.arrancar(segunda).status_code, 400)

        self.afirmar_ok(self.patch(
            f"/pedidos/{self.venta_primera}/cancelar", self.admin
        ))
        self.afirmar_ok(self.arrancar(segunda))
        # Y la harina nunca se movió: solo cambió de dueño.
        self.assertAlmostEqual(self.harina(), 2000.0, places=3)

    def test_si_alcanza_para_las_dos_las_dos_arrancan(self):
        primera, segunda = self.dos_ordenes(harina=4000.0)

        self.afirmar_ok(self.arrancar(primera))
        self.afirmar_ok(self.arrancar(segunda))
        self.assertAlmostEqual(self.harina(), 4000.0, places=3)

        self.afirmar_ok(self.completar(primera))
        self.assertAlmostEqual(self.harina(), 2000.0, places=3)
        self.afirmar_ok(self.completar(segunda))
        self.assertAlmostEqual(self.harina(), 0.0, places=3)

    def test_una_tercera_orden_no_pasa_con_las_dos_apartadas(self):
        primera, segunda = self.dos_ordenes(harina=4000.0)
        self.afirmar_ok(self.arrancar(primera))
        self.afirmar_ok(self.arrancar(segunda))

        id_venta_tercera = self.pedido_con_faltante()["ID_Venta"]
        self.confirmar_si_pendiente(id_venta_tercera)
        tercera = self.orden_de(id_venta_tercera)
        respuesta = self.arrancar(tercera)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("apartado por otra orden", self.detalle(respuesta).lower())

    def test_el_mensaje_distingue_apartado_de_agotado(self):
        """No es lo mismo: mandar a comprar harina que está en bodega no arregla nada."""
        primera, segunda = self.dos_ordenes(harina=2000.0)
        self.afirmar_ok(self.arrancar(primera))

        apartado = self.detalle(self.arrancar(segunda)).lower()
        self.assertIn("complet", apartado)          # "completá o anulá esa orden"
        self.assertNotIn("stock insuficiente", apartado)

        self.afirmar_ok(self.completar(primera))
        agotado = self.detalle(self.arrancar(segunda)).lower()
        self.assertIn("stock insuficiente", agotado)

    def test_el_panel_ve_lo_que_queda_libre_y_no_el_stock_a_secas(self):
        """Si el panel mira el stock total, da luz verde a algo que el servidor
        va a rechazar. La ficha viaja con lo que de verdad queda disponible."""
        primera, _segunda = self.dos_ordenes(harina=4000.0)

        antes = self.afirmar_ok(self.get(f"/productos/{ID_TORTA}", self.admin))
        harina = antes["ficha_tecnica"]["insumos"][0]
        self.assertEqual(harina["Stock_Actual"], 4000.0)
        self.assertEqual(harina["Stock_Disponible"], 4000.0)

        self.afirmar_ok(self.arrancar(primera))
        despues = self.afirmar_ok(self.get(f"/productos/{ID_TORTA}", self.admin))
        harina = despues["ficha_tecnica"]["insumos"][0]
        # El stock no se movió; lo que bajó es lo que queda libre.
        self.assertEqual(harina["Stock_Actual"], 4000.0)
        self.assertEqual(harina["Stock_Disponible"], 2000.0)

    def test_completar_libera_la_reserva_y_baja_el_stock(self):
        primera, _segunda = self.dos_ordenes(harina=4000.0)
        self.afirmar_ok(self.arrancar(primera))
        self.afirmar_ok(self.completar(primera))

        harina = self.afirmar_ok(
            self.get(f"/productos/{ID_TORTA}", self.admin)
        )["ficha_tecnica"]["insumos"][0]
        self.assertEqual(harina["Stock_Actual"], 2000.0)
        self.assertEqual(harina["Stock_Disponible"], 2000.0)

    def test_la_reserva_no_bloquea_a_la_orden_que_ya_la_tiene(self):
        """Completar la propia orden no puede chocar con su propia reserva."""
        primera, _segunda = self.dos_ordenes(harina=2000.0)
        self.afirmar_ok(self.arrancar(primera))
        self.afirmar_ok(self.completar(primera))
        self.assertAlmostEqual(self.harina(), 0.0, places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
