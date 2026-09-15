from pydantic import BaseModel
from typing import Optional
from decimal import Decimal


class LandingConfigResponse(BaseModel):
    heroBadge:              Optional[str] = None
    heroTitle:              Optional[str] = None
    heroDescription:        Optional[str] = None
    historyTitle:           Optional[str] = None
    historyDescription:     Optional[str] = None
    ctaTitle:               Optional[str] = None
    ctaDescription:         Optional[str] = None
    contactPhone1:          Optional[str] = None
    contactPhone2:          Optional[str] = None
    contactEmail:           Optional[str] = None
    contactAddressLine:     Optional[str] = None
    contactCity:            Optional[str] = None
    contactInstagramUrl:    Optional[str] = None
    contactInstagramHandle: Optional[str] = None
    mapLat:                 Optional[Decimal] = None
    mapLng:                 Optional[Decimal] = None
    horaApertura:           Optional[str] = None   # "08:00"
    horaCierre:             Optional[str] = None   # "20:00"
    diasAtencion:           Optional[str] = None   # CSV ISO 1..7 (1=Lun)
    pedidoMinimo:           Optional[int] = None   # mínimo para domicilio (0 = sin mínimo)

    class Config:
        from_attributes = True


class LandingConfigUpdate(BaseModel):
    heroBadge:              Optional[str] = None
    heroTitle:              Optional[str] = None
    heroDescription:        Optional[str] = None
    historyTitle:           Optional[str] = None
    historyDescription:     Optional[str] = None
    ctaTitle:               Optional[str] = None
    ctaDescription:         Optional[str] = None
    contactPhone1:          Optional[str] = None
    contactPhone2:          Optional[str] = None
    contactEmail:           Optional[str] = None
    contactAddressLine:     Optional[str] = None
    contactCity:            Optional[str] = None
    contactInstagramUrl:    Optional[str] = None
    contactInstagramHandle: Optional[str] = None
    mapLat:                 Optional[Decimal] = None
    mapLng:                 Optional[Decimal] = None
    horaApertura:           Optional[str] = None
    horaCierre:             Optional[str] = None
    diasAtencion:           Optional[str] = None
    pedidoMinimo:           Optional[int] = None
