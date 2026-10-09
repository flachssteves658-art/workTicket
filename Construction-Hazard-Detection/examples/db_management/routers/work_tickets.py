from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from examples.auth.database import get_db
from examples.db_management.schemas.work_ticket import CameraConfirmRequest
from examples.db_management.schemas.work_ticket import CameraStreamBindingRequest
from examples.db_management.schemas.work_ticket import CatalogImportRequest
from examples.db_management.schemas.work_ticket import WorkTicketMatchRequest
from examples.db_management.services.work_ticket_services import bind_camera_streams
from examples.db_management.services.work_ticket_services import cancel_detection_task
from examples.db_management.services.work_ticket_services import catalog_status
from examples.db_management.services.work_ticket_services import confirm_ticket_cameras
from examples.db_management.services.work_ticket_services import get_detection_task
from examples.db_management.services.work_ticket_services import get_ticket_matches
from examples.db_management.services.work_ticket_services import import_catalogs
from examples.db_management.services.work_ticket_services import list_stream_options
from examples.db_management.services.work_ticket_services import match_ticket


router = APIRouter(prefix='/integration', tags=['work-ticket-integration'])


def _require_integration_token(token: str | None) -> None:
    expected = os.getenv('INTEGRATION_TOKEN', '')
    if not expected:
        raise HTTPException(status_code=500, detail='Integration token not configured.')
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail='Invalid integration token.')


@router.get('/catalog/status')
async def endpoint_catalog_status(
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    return await catalog_status(db)


@router.post('/catalog/import')
async def endpoint_catalog_import(
    payload: CatalogImportRequest,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    return await import_catalogs(payload, db)


@router.post('/tickets/match')
async def endpoint_match_ticket(
    payload: WorkTicketMatchRequest,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    try:
        return await match_ticket(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/streams/options')
async def endpoint_stream_options(
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    return await list_stream_options(db)


@router.post('/cameras/bind-streams')
async def endpoint_bind_camera_streams(
    payload: CameraStreamBindingRequest,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    try:
        return await bind_camera_streams(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/tickets/{ticket_no}/matches')
async def endpoint_ticket_matches(
    ticket_no: str,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    result = await get_ticket_matches(ticket_no, db)
    if result is None:
        raise HTTPException(status_code=404, detail='Ticket match result not found.')
    return result


@router.post('/tickets/{ticket_no}/confirm-cameras')
async def endpoint_confirm_cameras(
    ticket_no: str,
    payload: CameraConfirmRequest,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    try:
        return await confirm_ticket_cameras(
            ticket_no,
            payload.camera_ids,
            payload.confirmed_by,
            db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/tickets/{ticket_no}/task')
async def endpoint_detection_task(
    ticket_no: str,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    task = await get_detection_task(ticket_no, db)
    if task is None:
        raise HTTPException(status_code=404, detail='Detection task not found.')
    return task


@router.post('/tickets/{ticket_no}/cancel-task')
async def endpoint_cancel_detection_task(
    ticket_no: str,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_token(x_integration_token)
    task = await cancel_detection_task(ticket_no, db)
    if task is None:
        raise HTTPException(status_code=404, detail='Detection task not found.')
    return task
