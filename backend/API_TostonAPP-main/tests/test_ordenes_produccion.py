import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DB_USER", "u")
os.environ.setdefault("DB_PASSWORD", "p")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "test")

from src.features.ventas.gestion_ventas.services.service import _crear_ordenes_produccion_para_venta
from src.shared.services.models import (
    FichaTecnica, OrdenProduccion, Producto, VentaXProducto,
)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def order_by(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        return list(self.rows)

    def count(self):
        return len(self.rows)


class FakeDB:
    """Resuelve consultas por modelo y por columna suelta.

    El service solo pide el id cuando le basta con saber qué productos son
    fabricables, así que esas ramas devuelven tuplas de una columna.
    """

    def __init__(self, venta_productos, productos, ordenes=None, fichas=None):
        self.venta_productos = venta_productos
        self.productos       = productos
        self.ordenes         = ordenes or []
        self.fichas          = fichas or []
        self.added           = []

    def query(self, model, *_):
        if model is VentaXProducto:
            return FakeQuery(self.venta_productos)
        if model is Producto:
            return FakeQuery(self.productos)
        if model is FichaTecnica:
            return FakeQuery(self.fichas)
        if model is OrdenProduccion:
            return FakeQuery(self.ordenes)
        if model is Producto.ID_Producto:
            return FakeQuery([
                (p.ID_Producto,) for p in self.productos
                if getattr(p, "Requiere_Produccion", 0)
            ])
        if model is FichaTecnica.ID_Producto:
            return FakeQuery([(f.ID_Producto,) for f in self.fichas])
        if model is OrdenProduccion.ID_Producto:
            return FakeQuery([
                (o.ID_Producto,) for o in self.ordenes if o.Estado != 5
            ])
        return FakeQuery([])

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, obj):
        return None


def _ficha(id_producto, id_ficha=30, dias_vida_util=5):
    return type("Ficha", (), {
        "ID_Producto":    id_producto,
        "ID_Ficha":       id_ficha,
        "Estado":         1,
        "Dias_Vida_Util": dias_vida_util,
    })()


class OrdenesProduccionTests(unittest.TestCase):
    def test_crea_orden_para_producto_con_ficha(self):
        # Cantidad_Preorden es lo que se fabrica (el déficit contra el stock);
        # sin stock coincide con lo pedido.
        venta_producto = type("VentaProducto", (), {
            "ID_Venta": 10, "ID_Producto": 6,
            "Cantidad": 2, "Cantidad_Preorden": 2,
        })()
        producto = type("Producto", (), {"ID_Producto": 6, "Requiere_Produccion": 1, "Stock": 0})()
        db = FakeDB([venta_producto], [producto], fichas=[_ficha(6, id_ficha=30)])

        _crear_ordenes_produccion_para_venta(db, 10, "2026-01-01")

        self.assertEqual(len(db.added), 1)
        orden = db.added[0]
        self.assertEqual(orden.ID_Venta, 10)
        self.assertEqual(orden.ID_Producto, 6)
        self.assertEqual(orden.Cantidad, 2)
        self.assertEqual(orden.Estado, 1)
        self.assertEqual(orden.ID_Ficha, 30)

    def test_la_orden_cubre_solo_el_faltante(self):
        """5 en stock y 10 pedidos → se manda a producir 5, no 10."""
        venta_producto = type("VentaProducto", (), {
            "ID_Venta": 11, "ID_Producto": 6,
            "Cantidad": 10, "Cantidad_Preorden": 5,
        })()
        producto = type("Producto", (), {"ID_Producto": 6, "Requiere_Produccion": 1, "Stock": 5})()
        db = FakeDB([venta_producto], [producto], fichas=[_ficha(6)])

        creadas = _crear_ordenes_produccion_para_venta(db, 11, "2026-01-01")

        self.assertEqual(creadas, 1)
        self.assertEqual(db.added[0].Cantidad, 5)
        self.assertEqual(db.added[0].Estado, 1)  # nace Pendiente

    def test_producto_sin_ficha_no_genera_orden(self):
        """3.10 — sin ficha técnica no se puede fabricar: no se abre la orden."""
        venta_producto = type("VentaProducto", (), {
            "ID_Venta": 12, "ID_Producto": 6,
            "Cantidad": 4, "Cantidad_Preorden": 4,
        })()
        producto = type("Producto", (), {"ID_Producto": 6, "Requiere_Produccion": 1, "Stock": 0})()
        db = FakeDB([venta_producto], [producto])   # sin fichas

        creadas = _crear_ordenes_produccion_para_venta(db, 12, "2026-01-01")

        self.assertEqual(creadas, 0)
        self.assertEqual(db.added, [])

    def test_ficha_sin_dias_vida_util_no_genera_orden(self):
        """Ficha sin Dias_Vida_Util se trata igual que sin ficha: no se abre la orden."""
        venta_producto = type("VentaProducto", (), {
            "ID_Venta": 13, "ID_Producto": 6,
            "Cantidad": 3, "Cantidad_Preorden": 3,
        })()
        producto = type("Producto", (), {"ID_Producto": 6, "Requiere_Produccion": 1, "Stock": 0})()
        db = FakeDB([venta_producto], [producto], fichas=[_ficha(6, dias_vida_util=None)])

        creadas = _crear_ordenes_produccion_para_venta(db, 13, "2026-01-01")

        self.assertEqual(creadas, 0)
        self.assertEqual(db.added, [])


if __name__ == "__main__":
    unittest.main()
