from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field


class EquipmentCatalogItem(BaseModel):
    source_key: str
    station_name: str
    equipment_name: str
    voltage_level: str = ''
    equipment_type: str = ''
    asset_no: str = ''
    running_no: str = ''
    interval_name: str = ''
    asset_status: str = ''
    running_status: str = ''
    dispatch_name: str = ''
    install_location: str = ''
    equipment_code: str = ''
    functional_location_code: str = ''
    normalized_search: str = ''


class CameraCatalogItem(BaseModel):
    camera_id: str
    station_name: str
    nvr_name: str = ''
    channel_no: str = ''
    install_location: str = ''
    monitor_area: str = ''
    ip_address: str = ''
    running_status: str = ''
    retention_period: str = ''


class CatalogImportRequest(BaseModel):
    equipment: list[EquipmentCatalogItem]
    cameras: list[CameraCatalogItem]
    equipment_source: str = ''
    camera_source: str = ''


class WorkTicketMatchRequest(BaseModel):
    ticket_no: str
    source_file: str = ''
    structured_data: dict[str, Any] = Field(default_factory=dict)


class CameraConfirmRequest(BaseModel):
    camera_ids: list[str] = Field(min_length=1)
    confirmed_by: str = 'manual'


class CameraStreamBindingItem(BaseModel):
    camera_id: str = Field(min_length=1, max_length=80)
    stream_config_id: int | None = Field(default=None, ge=1)


class CameraStreamBindingRequest(BaseModel):
    bindings: list[CameraStreamBindingItem] = Field(min_length=1)
    allow_station_mismatch: bool = False
