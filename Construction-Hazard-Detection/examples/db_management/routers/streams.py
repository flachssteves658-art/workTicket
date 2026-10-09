from __future__ import annotations

import base64
import hmac
import os

import redis.asyncio as redis
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from examples.auth.database import get_db
from examples.auth.models import Site
from examples.auth.models import StreamConfig
from examples.auth.redis_pool import get_redis_pool
from examples.db_management.deps import _site_permission
from examples.db_management.deps import get_current_user
from examples.db_management.deps import is_super_admin
from examples.db_management.deps import require_admin
from examples.db_management.schemas.stream_config import StreamConfigCreate
from examples.db_management.schemas.stream_config import ApplyTicketToSiteRequest
from examples.db_management.schemas.stream_config import ApplyTicketToSiteResponse
from examples.db_management.schemas.stream_config import StreamConfigRead
from examples.db_management.schemas.stream_config import StreamConfigUpdate
from examples.db_management.services.stream_config_services import (
    create_stream_config,
)
from examples.db_management.services.stream_config_services import (
    delete_stream_config,
)
from examples.db_management.services.stream_config_services import (
    get_group_stream_limit,
)
from examples.db_management.services.stream_config_services import (
    list_stream_configs,
)
from examples.db_management.services.stream_config_services import (
    update_stream_config,
)

router = APIRouter(tags=['stream-config'])


def _require_integration_token(x_integration_token: str | None) -> None:
    expected = os.getenv('INTEGRATION_TOKEN', '')
    if not expected:
        raise HTTPException(status_code=500, detail='Integration token not configured.')
    if not x_integration_token or not hmac.compare_digest(x_integration_token, expected):
        raise HTTPException(status_code=401, detail='Invalid integration token.')


@router.get('/list_stream_configs', response_model=list[StreamConfigRead])
async def endpoint_list_stream_configs(
    site_id: int,
    db: AsyncSession = Depends(get_db),
    me=Depends(get_current_user),
) -> list[StreamConfigRead]:
    """List all stream configurations for a given site.

    Args:
        site_id (int): The identifier of the site.
        db (AsyncSession): The database session.
        me (User): The currently authenticated user.

    Returns:
        List[StreamConfigRead]: A list of stream configuration details.

    Raises:
        HTTPException: If the site does not exist or the user lacks permission.
    """
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail='Site not found.')

    _site_permission(me, site=site)

    stream_configs = await list_stream_configs(site_id, db)

    # Retrieve current stream count and group limit
    current, _ = await get_group_stream_limit(site.group_id, db)

    return [
        StreamConfigRead(
            id=c.id,
            stream_name=c.stream_name,
            video_url=c.video_url,
            model_key=c.model_key,
            detect_with_server=c.detect_with_server,
            store_in_redis=c.store_in_redis,
            work_start_hour=c.work_start_hour,
            work_end_hour=c.work_end_hour,
            detect_no_safety_vest_or_helmet=c.detect_no_safety_vest_or_helmet,
            detect_near_machinery_or_vehicle=(
                c.detect_near_machinery_or_vehicle
            ),
            detect_in_restricted_area=c.detect_in_restricted_area,
            detect_in_utility_pole_restricted_area=(
                c.detect_in_utility_pole_restricted_area
            ),
            detect_machinery_close_to_pole=c.detect_machinery_close_to_pole,
            expire_date=c.expire_date,
            active_ticket_no=c.active_ticket_no,
            active_from=c.active_from,
            active_to=c.active_to,
            total_stream_in_group=current,
            max_allowed_streams=site.group.max_allowed_streams,
            updated_at=c.updated_at,
        )
        for c in stream_configs
    ]


@router.post('/apply_ticket_to_site', response_model=ApplyTicketToSiteResponse)
async def endpoint_apply_ticket_to_site(
    payload: ApplyTicketToSiteRequest,
    x_integration_token: str | None = Header(None, alias='X-Integration-Token'),
    db: AsyncSession = Depends(get_db),
) -> ApplyTicketToSiteResponse:
    _require_integration_token(x_integration_token)

    site = await db.scalar(select(Site).where(Site.name == payload.site_name))
    if not site:
        raise HTTPException(status_code=404, detail='Site not found.')

    result = await db.execute(
        select(StreamConfig).where(StreamConfig.site_id == site.id),
    )
    cfgs = result.scalars().all()

    update_data = payload.model_dump(exclude_unset=True)
    ticket_no = update_data.pop('ticket_no', '')
    active_from = update_data.pop('active_from', None)
    active_to = update_data.pop('active_to', None)
    update_data['active_ticket_no'] = ticket_no
    update_data['active_from'] = active_from
    update_data['active_to'] = active_to

    updated_ids: list[int] = []
    for cfg in cfgs:
        for k, v in update_data.items():
            setattr(cfg, k, v)
        updated_ids.append(cfg.id)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f'Database error: {e}')

    return ApplyTicketToSiteResponse(
        site_name=payload.site_name,
        ticket_no=ticket_no,
        updated_stream_config_ids=updated_ids,
    )


@router.post(
    '/create_stream_config',
    dependencies=[Depends(require_admin)],
)
async def endpoint_create_stream_config(
    payload: StreamConfigCreate,
    db: AsyncSession = Depends(get_db),
    me=Depends(get_current_user),
) -> dict[str, str | int]:
    """Create a new stream configuration for a site.

    Args:
        payload (StreamConfigCreate): The stream configuration data.
        db (AsyncSession): The database session.
        me (User): The currently authenticated user.

    Returns:
        Dict[str, str | int]: Confirmation message and the created config ID.

    Raises:
        HTTPException: If the site does not exist
            or group stream limit is exceeded.
    """
    site = await db.get(Site, payload.site_id)
    if not site:
        raise HTTPException(status_code=404, detail='Site not found.')

    _site_permission(me, site=site)

    current, limit = await get_group_stream_limit(site.group_id, db)
    if current >= limit:
        raise HTTPException(
            status_code=403, detail='Stream limit reached for group.',
        )

    payload_with_group = payload.model_copy(update={'group_id': site.group_id})
    cfg = await create_stream_config(payload_with_group, db)

    return {
        'id': cfg.id,
        'message': 'Stream configuration created successfully.',
    }


@router.put(
    '/stream_config/update/{cfg_id}',
    dependencies=[Depends(require_admin)],
)
async def endpoint_update_stream_config(
    cfg_id: int,
    payload: StreamConfigUpdate,
    db: AsyncSession = Depends(get_db),
    me=Depends(get_current_user),
) -> dict[str, str]:
    """Update an existing stream configuration.

    Args:
        cfg_id (int): The stream configuration identifier.
        payload (StreamConfigUpdate): Updated stream configuration details.
        db (AsyncSession): The database session.
        me (User): The currently authenticated user.

    Returns:
        Dict[str, str]: Confirmation message of successful update.

    Raises:
        HTTPException: If config does not exist, permission denied,
            or name conflict.
    """
    # Eagerly load the site relationship to avoid lazy load errors
    result = await db.execute(
        select(StreamConfig)
        .options(selectinload(StreamConfig.site))
        .where(StreamConfig.id == cfg_id)
    )
    cfg = result.scalar_one_or_none()
    
    if not cfg:
        raise HTTPException(
            status_code=404, detail='Stream configuration not found.',
        )

    _site_permission(me, site=cfg.site)

    # Check for name duplication within the same site
    if payload.stream_name and payload.stream_name != cfg.stream_name:
        exists = await db.scalar(
            select(StreamConfig).where(
                StreamConfig.site_id == cfg.site_id,
                StreamConfig.stream_name == payload.stream_name,
            ),
        )
        if exists:
            raise HTTPException(
                status_code=400, detail='Stream name already exists in site.',
            )

    await update_stream_config(cfg, payload, db)

    return {'message': 'Stream configuration updated successfully.'}


@router.delete(
    '/delete_stream_config/{cfg_id}',
    dependencies=[Depends(require_admin)],
)
async def endpoint_delete_stream_config(
    cfg_id: int,
    db: AsyncSession = Depends(get_db),
    me=Depends(get_current_user),
    rds: redis.Redis = Depends(get_redis_pool),
) -> dict[str, str]:
    """Delete an existing stream configuration.

    Args:
        cfg_id (int): The identifier of the stream configuration.
        db (AsyncSession): The database session.
        me (User): The currently authenticated user.

    Returns:
        Dict[str, str]: Confirmation message.

    Raises:
        HTTPException: If configuration not found or permission denied.
    """
    cfg = await db.get(StreamConfig, cfg_id)
    if not cfg:
        raise HTTPException(
            status_code=404, detail='Stream configuration not found.',
        )

    _site_permission(me, site=cfg.site)
    site_name = str(cfg.site.name)
    stream_name = str(cfg.stream_name)
    encoded_site = base64.urlsafe_b64encode(
        site_name.encode('utf-8'),
    ).decode('ascii')
    encoded_stream_name = base64.urlsafe_b64encode(
        stream_name.encode('utf-8'),
    ).decode('ascii')
    redis_key = f'stream_frame:{encoded_site}|{encoded_stream_name}'
    if hasattr(rds, 'delete'):
        await rds.delete(redis_key)
    await delete_stream_config(cfg, db)

    return {'message': 'Stream configuration deleted successfully.'}


@router.get(
    '/group_stream_limit',
    dependencies=[Depends(get_current_user)],
)
async def endpoint_group_stream_limit(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    me=Depends(get_current_user),
) -> dict[str, int]:
    """Retrieve the stream limit and current usage for a group.

    Args:
        group_id (int): The identifier of the group.
        db (AsyncSession): The database session.
        me (User): The currently authenticated user.

    Returns:
        Dict[str, int]: Details of stream usage and limits.

    Raises:
        HTTPException: If the user lacks permission to view the group's limits.
    """
    # Super admin has unlimited access, admins restricted to their group
    if not (
        is_super_admin(me)
        or (me.role == 'admin' and me.group_id == group_id)
    ):
        raise HTTPException(status_code=403, detail='Permission denied.')

    current, limit = await get_group_stream_limit(group_id, db)

    return {
        'group_id': group_id,
        'max_allowed_streams': limit,
        'current_streams_count': current,
    }
