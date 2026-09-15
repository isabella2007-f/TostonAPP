"""Lo que el detalle de un pedido tiene que traer para poder mostrarse.

La pantalla de detalle —la del panel web y la de la app, admin y cliente—
muestra a dónde va el pedido, quién lo lleva, qué escribió el cliente al
pedirlo, cuánto se abonó y cuánto queda debiendo. Todo eso sale de la
respuesta de un solo endpoint.

Esa respuesta pasa por un esquema Pydantic, y un campo que el servicio arma
pero el esquema no declara desaparece sin que nadie se entere: ya pasó dos
veces en este módulo —el correo y el teléfono del cliente por un lado, el
stock de la ficha técnica por otro—, y las dos veces el síntoma fue una
pantalla a medio llenar sin ningún error en el camino.

Este archivo recorre la API de verdad y mira la respuesta campo por campo,
para las dos puertas: la del gestor (`/ventas/{id}`) y la del cliente
(`/ventas/mis-ventas/{id}`), que comparten esquema pero no permisos.

Corre sin credenciales:
    python tests/test_detalle_pedido_movil.py
"""
import unittest

from panel import ID_CLIENTE, ID_TORTA, PanelBase


# Lo que las pantallas leen de cada pedido. Si un nombre de acá deja de venir,
# la pantalla que lo muestra se queda con un hueco y no se entera nadie.
CAMPOS_DEL_PEDIDO = [
    # Quién pidió
    "ID_Venta", "ID_Usuario", "nombre_cliente", "correo_cliente",
    "telefono_cliente",
    # Cuánto
    "Total", "subtotal_bruto", "credito_aplicado", "descuento_aplicado",
    # En qué anda
    "Estado", "estado_label", "Fecha_pedido", "Fecha_entrega",
    "Fecha_entrega_esperada",
    # A dónde va
    "tiene_domicilio", "ID_Domicilio", "direccion_entrega",
    "municipio_entrega", "departamento_entrega", "observaciones_domicilio",
    "nombre_domiciliario",
    # Cómo se paga
    "Metodo_Pago", "estado_pago", "comprobante_pago",
    "monto_efectivo", "monto_transferencia",
    # El anticipo y el saldo
    "sobre_stock", "requiere_anticipo", "anticipo_requerido",
    "anticipo_pagado", "anticipo_monto", "anticipo_metodo_pago",
    "anticipo_comprobante_url", "anticipo_registrado",
    "pago_final_registrado", "pago_final_monto", "pago_final_metodo_pago",
    "pago_final_comprobante_url", "pago_final_fecha",
    # Producción
    "requiere_produccion", "requiere_fecha_propuesta", "fecha_rechazada", "intentos_rechazo",
    "ordenes_produccion_pendientes", "ordenes_en_espera",
    # Qué se pidió
    "productos",
]

# Y de cada línea del pedido.
CAMPOS_DE_LA_LINEA = [
    "ID_Producto", "nombre_producto", "Cantidad", "precio_unitario",
    "subtotal", "imagen", "cantidad_preorden", "stock_disponible",
]


class DetalleDelPedidoTests(PanelBase):
    """Un pedido especial visto desde las dos puertas."""

    def pedido_completo(self):
        """Un pedido con todo lo que un pedido puede tener.

        Va a domicilio, supera el stock, lleva anticipo pagado por
        transferencia y trae indicaciones del cliente: es el caso que más
        campos enciende de una sola vez.
        """
        return self.pedido_con_faltante(
            domicilio=self.direccion(
                Observaciones="Timbre dañado, llamar al llegar",
            ),
        )

    def test_el_gestor_recibe_el_pedido_completo(self):
        creado = self.pedido_completo()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/{creado['ID_Venta']}", self.admin))

        faltan = [c for c in CAMPOS_DEL_PEDIDO if c not in pedido]
        self.assertEqual(faltan, [], f"el esquema borró: {faltan}")

    def test_el_cliente_recibe_el_mismo_pedido(self):
        """El cliente ve su propio pedido con el mismo detalle.

        Es otro endpoint y otro permiso; comparten esquema, pero eso es una
        decisión que se puede deshacer sin querer.
        """
        creado = self.pedido_completo()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{creado['ID_Venta']}", self.cliente))

        faltan = [c for c in CAMPOS_DEL_PEDIDO if c not in pedido]
        self.assertEqual(faltan, [], f"el esquema borró: {faltan}")

    def test_cada_producto_dice_cuánto_hay_que_hornear(self):
        """`cantidad_preorden` es lo que no alcanzaba el stock.

        Es la parte del pedido que hay que fabricar, y la única forma de
        explicar en pantalla por qué se pidió un anticipo.
        """
        creado = self.pedido_completo()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/{creado['ID_Venta']}", self.admin))

        self.assertTrue(pedido["productos"], "el pedido llegó sin líneas")
        linea = pedido["productos"][0]
        faltan = [c for c in CAMPOS_DE_LA_LINEA if c not in linea]
        self.assertEqual(faltan, [], f"el esquema borró: {faltan}")

        self.assertEqual(linea["ID_Producto"], ID_TORTA)
        self.assertEqual(linea["Cantidad"], 6)
        # Hay 2 tortas en vitrina: 4 hay que hornearlas.
        self.assertEqual(linea["cantidad_preorden"], 4)

    def test_la_dirección_llega_entera(self):
        """Dirección, ciudad y departamento: los tres, no solo el primero."""
        creado = self.pedido_completo()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/{creado['ID_Venta']}", self.admin))

        self.assertTrue(pedido["tiene_domicilio"])
        self.assertEqual(pedido["direccion_entrega"], "Calle 10 #20-30")
        self.assertEqual(pedido["municipio_entrega"], "Medellín")
        self.assertEqual(pedido["departamento_entrega"], "Antioquia")

    def test_las_indicaciones_del_cliente_llegan(self):
        """Lo que el cliente escribió al pedir.

        Quien entrega lo necesita, y hasta ahora no salía en ninguna de las
        dos pantallas de la app.
        """
        creado = self.pedido_completo()
        for ruta, quien in (
            (f"/ventas/{creado['ID_Venta']}", self.admin),
            (f"/ventas/mis-ventas/{creado['ID_Venta']}", self.cliente),
        ):
            with self.subTest(ruta=ruta):
                pedido = self.afirmar_ok(self.get(ruta, quien))
                self.assertEqual(
                    pedido["observaciones_domicilio"],
                    "Timbre dañado, llamar al llegar",
                )

    def test_el_anticipo_llega_con_su_respaldo(self):
        """Cuánto se abonó, con qué se pagó y qué comprobante lo respalda."""
        creado = self.pedido_completo()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/{creado['ID_Venta']}", self.admin))

        self.assertTrue(pedido["sobre_stock"])
        self.assertTrue(pedido["requiere_anticipo"])
        self.assertTrue(pedido["anticipo_registrado"])
        self.assertEqual(float(pedido["anticipo_monto"]), 30000.0)
        self.assertEqual(pedido["anticipo_metodo_pago"], "Transferencia")
        self.assertEqual(
            pedido["anticipo_comprobante_url"], "https://cloudinary.test/ant.jpg")
        self.assertEqual(pedido["estado_pago"], "anticipo_pagado")

    def test_el_saldo_llega_con_su_respaldo(self):
        """Cobrado el saldo, la respuesta dice cuánto, con qué y cuándo.

        Sin estos campos la pantalla no puede decir "pagado completo" con
        cifras: solo repetir la etiqueta del estado.
        """
        creado = self.pedido_completo()
        id_venta = creado["ID_Venta"]
        self.hornear(id_venta)

        saldo = float(creado["Total"]) - 30000.0
        self.afirmar_ok(self.post(
            f"/ventas/{id_venta}/registrar-pago-final", self.admin,
            {
                "monto": saldo,
                "metodo_pago": "Efectivo",
            },
        ))

        pedido = self.afirmar_ok(self.get(f"/ventas/{id_venta}", self.admin))
        self.assertTrue(pedido["pago_final_registrado"])
        self.assertEqual(float(pedido["pago_final_monto"]), saldo)
        self.assertEqual(pedido["pago_final_metodo_pago"], "Efectivo")
        self.assertIsNotNone(pedido["pago_final_fecha"])

    def test_un_pedido_normal_no_finge_anticipo(self):
        """Sin anticipo, los campos vienen apagados y no en null a medias.

        La pantalla decide con ellos si dibuja la sección del anticipo; un
        `None` donde debería ir `false` la enciende igual.
        """
        creado = self.crear_pedido()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/{creado['ID_Venta']}", self.admin))

        self.assertFalse(pedido["sobre_stock"])
        self.assertFalse(pedido["requiere_anticipo"])
        self.assertFalse(pedido["anticipo_registrado"])
        self.assertFalse(pedido["pago_final_registrado"])
        self.assertEqual(pedido["productos"][0]["cantidad_preorden"], 0)

    def test_el_pedido_en_tienda_lo_dice(self):
        """Sin domicilio no hay dirección que mostrar, y eso también se informa."""
        creado = self.crear_pedido()
        pedido = self.afirmar_ok(
            self.get(f"/ventas/{creado['ID_Venta']}", self.admin))

        self.assertFalse(pedido["tiene_domicilio"])
        self.assertIsNone(pedido["direccion_entrega"])
        self.assertIsNone(pedido["nombre_domiciliario"])

    def proponer(self, idv, dia="20"):
        return self.afirmar_ok(self.patch(
            f"/ventas/{idv}/proponer-fecha", self.admin,
            {"fecha_entrega": f"2027-09-{dia}T10:00:00"}))

    def rechazar(self, idv, dia="25", motivo="No puedo recibirlo ese día"):
        return self.afirmar_ok(self.patch(
            f"/ventas/{idv}/rechazar-fecha", self.cliente,
            {"fecha_propuesta": f"2027-09-{dia}T10:00:00", "motivo": motivo}))

    def test_rechazar_la_fecha_no_mata_el_pedido(self):
        """Rechazar deja el pedido en Fecha propuesta final (21), con la
        contraoferta del cliente, esperando al admin (prompt-pedidos-2, 3.4).

        Antes se cancelaba —y el de recoger en tienda se perdía—, así que la
        app lo mandaba al historial. Ahora sigue vivo.
        """
        creado = self.pedido_completo()
        idv = creado["ID_Venta"]
        self.proponer(idv)

        antes = self.afirmar_ok(self.get(f"/ventas/{idv}", self.admin))
        self.assertIsNone(antes["fecha_rechazada"], "nadie rechazó nada todavía")
        self.assertEqual(antes["intentos_rechazo"], 0)

        self.rechazar(idv)
        despues = self.afirmar_ok(self.get(f"/ventas/{idv}", self.admin))

        self.assertEqual(despues["Estado"], 21, "Fecha propuesta final")
        self.assertIsNotNone(despues["fecha_rechazada"])
        self.assertEqual(despues["intentos_rechazo"], 1)
        # La fecha que queda es la contraoferta del cliente, no la del admin.
        self.assertIsNotNone(despues["Fecha_entrega_esperada"])
        self.assertTrue(despues["requiere_fecha_propuesta"])

    def test_el_rechazo_final_del_admin_escala_el_pedido(self):
        """Una sola ronda: el cliente contraoferta, el admin no puede
        cumplirla → Escalado a admin (3.4.1). Ya no hay ciclo de reintentos.
        """
        creado = self.pedido_completo()
        idv = creado["ID_Venta"]
        self.proponer(idv)
        self.rechazar(idv)

        self.afirmar_ok(self.patch(f"/ventas/{idv}/rechazar-fecha-final", self.admin))
        v = self.afirmar_ok(self.get(f"/ventas/{idv}", self.admin))
        self.assertEqual(v["Estado"], 19, "Escalado a admin")

    def test_aceptar_la_fecha_final_borra_la_cuenta_de_rechazos(self):
        """Si el admin acepta la contraoferta del cliente, el rechazo anterior
        deja de importar."""
        creado = self.pedido_completo()
        idv = creado["ID_Venta"]
        self.proponer(idv, "20")
        self.rechazar(idv, "21")
        self.afirmar_ok(self.patch(f"/ventas/{idv}/aprobar-fecha", self.admin))

        v = self.afirmar_ok(self.get(f"/ventas/{idv}", self.admin))
        self.assertEqual(v["intentos_rechazo"], 0)

    def test_el_cliente_no_puede_leer_el_pedido_de_otro(self):
        """La puerta del cliente devuelve lo suyo y nada más."""
        creado = self.pedido_completo()
        ajeno = self.afirmar_ok(
            self.get(f"/ventas/mis-ventas/{creado['ID_Venta']}", self.cliente))
        self.assertEqual(ajeno["ID_Usuario"], ID_CLIENTE)

        respuesta = self.get(
            f"/ventas/mis-ventas/{creado['ID_Venta']}", self.repartidor)
        self.assertNotEqual(respuesta.status_code, 200, self.detalle(respuesta))


if __name__ == "__main__":
    unittest.main(verbosity=2)
