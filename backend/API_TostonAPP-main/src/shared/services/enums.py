"""
Constantes de columnas de texto libre que en realidad son enums de negocio.
Cada clase refleja el CHECK constraint homónimo aplicado en models.py / migrations.
No usar strings mágicos para estos campos en código nuevo — importar de aquí.
"""


class TipoAccionFecha:
    """Historial_Fechas_Propuestas.Tipo_Accion"""
    PROPUESTA = "propuesta"
    ACEPTADA = "aceptada"
    PROPUESTA_FINAL = "propuesta_final"
    RECHAZADA_FINAL = "rechazada_final"

    TODOS = (PROPUESTA, ACEPTADA, PROPUESTA_FINAL, RECHAZADA_FINAL)


class TipoSalida:
    """Salidas.Tipo"""
    VENCIMIENTO = "vencimiento"
    DANO = "daño"
    AJUSTE = "ajuste"
    CONSUMO = "consumo"
    DEVOLUCION = "devolución"

    TODOS = (VENCIMIENTO, DANO, AJUSTE, CONSUMO, DEVOLUCION)


class TipoDescuento:
    """Descuentos.Tipo"""
    CUPON = "cupon"
    ANTIGUEDAD = "antiguedad"
    EMISION = "emision"

    TODOS = (CUPON, ANTIGUEDAD, EMISION)


class TipoOfertaDomicilio:
    """Ofertas_Domicilio.Tipo"""
    DESCUENTO = "descuento"
    RECARGO = "recargo"

    TODOS = (DESCUENTO, RECARGO)


class TipoRemitenteChat:
    """MensajesChat.Tipo_Remitente"""
    CLIENTE = "cliente"
    ADMIN = "admin"
    DOMICILIARIO = "domiciliario"

    TODOS = (CLIENTE, ADMIN, DOMICILIARIO)
