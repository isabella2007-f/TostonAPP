from sqlalchemy.orm import Session
from src.shared.services.models import ConfiguracionLanding


# Campos del horario de atención — solo un admin puede modificarlos.
CAMPOS_HORARIO = ("horaApertura", "horaCierre", "diasAtencion")

_MAPPING = {
    "heroBadge":              "hero_badge",
    "heroTitle":              "hero_title",
    "heroDescription":        "hero_description",
    "historyTitle":           "history_title",
    "historyDescription":     "history_description",
    "ctaTitle":               "cta_title",
    "ctaDescription":         "cta_description",
    "contactPhone1":          "contact_phone1",
    "contactPhone2":          "contact_phone2",
    "contactEmail":           "contact_email",
    "contactAddressLine":     "contact_address_line",
    "contactCity":            "contact_city",
    "contactInstagramUrl":    "contact_instagram_url",
    "contactInstagramHandle": "contact_instagram_handle",
    "mapLat":                 "map_lat",
    "mapLng":                 "map_lng",
    "horaApertura":           "hora_apertura",
    "horaCierre":             "hora_cierre",
    "diasAtencion":           "dias_atencion",
    "pedidoMinimo":           "pedido_minimo",
}


def _fila(db: Session) -> ConfiguracionLanding:
    """Devuelve la fila singleton (ID=1); la crea si no existe."""
    fila = db.query(ConfiguracionLanding).filter(ConfiguracionLanding.ID == 1).first()
    if not fila:
        fila = ConfiguracionLanding(ID=1)
        db.add(fila)
        db.commit()
        db.refresh(fila)
    return fila


def _to_dict(fila: ConfiguracionLanding) -> dict:
    out = {campo_js: getattr(fila, campo_db) for campo_js, campo_db in _MAPPING.items()}
    for k in ("mapLat", "mapLng"):
        out[k] = float(out[k]) if out[k] is not None else None
    return out


def obtener_config(db: Session) -> dict:
    return _to_dict(_fila(db))


def guardar_config(db: Session, datos: dict) -> dict:
    fila = _fila(db)
    for campo_js, campo_db in _MAPPING.items():
        valor = datos.get(campo_js)
        if valor is not None:
            setattr(fila, campo_db, valor)
    db.commit()
    db.refresh(fila)
    return _to_dict(fila)
