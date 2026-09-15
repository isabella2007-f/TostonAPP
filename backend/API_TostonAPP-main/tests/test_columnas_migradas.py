# -*- coding: utf-8 -*-
"""Que cada columna del modelo exista también en la base de datos real.

SQLAlchemy nombra TODAS las columnas del modelo en cada consulta. Una columna
que está en el modelo y no en la base hace que MySQL conteste 1054 "Unknown
column", y eso sale por la API como un 500 en todo lo que toque esa tabla:
cargar pedidos, crear pedidos, el detalle, el panel.

Las pruebas no lo notan solas, y ese es el problema: el arnés crea las tablas
a partir del modelo, así que las columnas siempre existen y la suite queda
verde con la base real rota. Pasó exactamente así —cinco columnas nuevas en
Ventas sin su `ALTER TABLE`— y se descubrió desde la app, con un 500.

Esta prueba es el canario: si alguien agrega una columna y no la migra, falla
acá y dice qué falta.
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.append(str(RAIZ))

from src.shared.services.models import Venta, Domicilio, ConfiguracionLanding


# Columnas que venían en el esquema original de la base, de antes de que
# existiera el bloque de migraciones de `main.py`. No necesitan ALTER porque
# nunca se agregaron: estaban desde el CREATE TABLE.
DEL_ESQUEMA_ORIGINAL = {
    "Ventas": {"ID_Venta", "ID_Usuario", "Total", "Estado", "Metodo_Pago",
               "Fecha_Venta", "Fecha_pedido", "Fecha_Rechazada"},
    "Domicilios": {"ID_Domicilio", "ID_Venta", "ID_Empleado", "Estado",
                   "Direccion_entrega", "Municipio_entrega",
                   "Departamento_entrega", "Fecha_asignacion",
                   "Fecha_entrega", "Observaciones"},
    "Configuracion_Landing": {"ID"},
}

TABLAS = (Venta, Domicilio, ConfiguracionLanding)


class ColumnasMigradasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_py = (RAIZ / "src" / "main.py").read_text(encoding="utf-8")

    def test_cada_columna_nueva_tiene_su_migracion(self):
        sin_migrar = []
        for modelo in TABLAS:
            tabla = modelo.__tablename__
            originales = DEL_ESQUEMA_ORIGINAL.get(tabla, set())
            for col in modelo.__table__.columns:
                if col.name in originales:
                    continue
                # Basta con que `main.py` la nombre: las migraciones están
                # escritas de varias formas (sentencia suelta, lista de
                # tuplas), y lo que importa es que alguien se acordó de ella.
                if col.name not in self.main_py:
                    sin_migrar.append(f"{tabla}.{col.name}")

        self.assertEqual(
            sin_migrar, [],
            "Estas columnas están en el modelo y no en las migraciones de "
            "main.py. Tal como está, la API devuelve 500 contra la base real:\n"
            + "\n".join(f"  ALTER TABLE ... ADD COLUMN {c}" for c in sin_migrar),
        )

    def test_las_columnas_del_ultimo_cambio_estan(self):
        # Las cinco que rompieron la app, fijadas por nombre para que no se
        # pierdan en un merge.
        for col in (
            "Intentos_Rechazo_Comprobante_Anticipo",
            "Intentos_Rechazo_Comprobante_Saldo",
            "Saldo_Comprobante_Url",
            "Fecha_Retenido_En_Tienda",
            "Stock_Reservado",
        ):
            with self.subTest(col=col):
                self.assertIn(col, {c.name for c in Venta.__table__.columns})
                self.assertIn(f"ADD COLUMN {col}", self.main_py)

    def test_el_esquema_original_no_crece_a_escondidas(self):
        # Si alguien agrega una columna a esta lista en vez de migrarla, la
        # prueba de arriba pasa y la base real sigue rota. Al menos que quede
        # constancia de cuántas son.
        self.assertEqual(
            {t: len(c) for t, c in DEL_ESQUEMA_ORIGINAL.items()},
            {"Ventas": 8, "Domicilios": 10, "Configuracion_Landing": 1},
        )


if __name__ == "__main__":
    unittest.main()
