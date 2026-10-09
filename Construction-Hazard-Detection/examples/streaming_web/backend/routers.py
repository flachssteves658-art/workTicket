from __future__ import annotations

import inspect
import json
from pathlib import Path
from datetime import datetime
import redis
from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Request
from fastapi import Security
from fastapi import UploadFile
from fastapi import WebSocket
from fastapi_jwt import JwtAuthorizationCredentials
from fastapi_limiter.depends import RateLimiter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from examples.auth.config import Settings
from examples.auth.database import get_db
from examples.auth.jwt_config import jwt_access
from examples.auth.models import Site
from examples.auth.models import StreamConfig
from examples.auth.redis_pool import get_redis_pool
from examples.auth.redis_pool import get_redis_pool_ws
from examples.auth.user_service import get_user_and_sites
from examples.shared.ws_helpers import get_auto_register_jti
from examples.streaming_web.backend.redis_service import scan_for_labels
from examples.streaming_web.backend.redis_service import store_to_redis
from examples.streaming_web.backend.schemas import FramePostResponse
from examples.streaming_web.backend.schemas import LabelListResponse
from examples.streaming_web.backend.utils import Utils
from examples.streaming_web.backend.ws_handlers import handle_frames_ws
from examples.streaming_web.backend.ws_handlers import handle_label_stream_ws
from examples.streaming_web.backend.ws_handlers import handle_stream_ws


# Settings and router
settings: Settings = Settings()
router: APIRouter = APIRouter()

# Rate limiters
rate_limiter_index: RateLimiter = RateLimiter(times=60, seconds=60)
rate_limiter_label: RateLimiter = RateLimiter(times=600, seconds=60)

# Env-configured behaviour
AUTO_REGISTER_JTI: bool = get_auto_register_jti()

class ConfigPayload(BaseModel):
    config: list[dict[str, object]]


async def get_redis_pool_safe(
    request: Request,
) -> redis.Redis | None:
    override = request.app.dependency_overrides.get(get_redis_pool)
    if override is not None:
        try:
            result = override()
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception:
            return None
    try:
        return await get_redis_pool(request)
    except Exception:
        return None

def _normalise_expire_date(expire_date: object) -> str | None:
    if expire_date is None:
        return 'No Expire Date'
    if isinstance(expire_date, str):
        if expire_date == 'No Expire Date':
            return expire_date
        if len(expire_date) >= 10 and expire_date[4] == '-' and expire_date[7] == '-':
            return expire_date[:10]
        return expire_date
    if isinstance(expire_date, datetime):
        return expire_date.date().isoformat()
    return None


def _ensure_detection_items(cfg: dict[str, object]) -> dict[str, bool]:
    src = cfg.get('detection_items')
    if isinstance(src, dict):
        base = {k: bool(v) for k, v in src.items() if isinstance(k, str)}
    else:
        base = {}

    for key in (
        'detect_no_safety_vest_or_helmet',
        'detect_near_machinery_or_vehicle',
        'detect_in_restricted_area',
        'detect_in_utility_pole_restricted_area',
        'detect_machinery_close_to_pole',
    ):
        if key not in base:
            v = cfg.get(key)
            base[key] = bool(v) if v is not None else False
    return base


def _normalise_config_dict(raw: dict[str, object]) -> dict[str, object]:
    cfg = dict(raw)
    cfg['expire_date'] = _normalise_expire_date(cfg.get('expire_date'))
    cfg['detect_with_server'] = bool(cfg.get('detect_with_server'))
    cfg['store_in_redis'] = bool(cfg.get('store_in_redis'))
    cfg['work_start_hour'] = int(cfg.get('work_start_hour') or 7)
    cfg['work_end_hour'] = int(cfg.get('work_end_hour') or 18)
    cfg['detection_items'] = _ensure_detection_items(cfg)
    if 'notifications' not in cfg:
        cfg['notifications'] = {}
    return cfg


def _parse_expire_date(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        if not value or value == 'No Expire Date':
            return None
        try:
            return datetime.fromisoformat(value[:10])
        except Exception:
            return None
    return None


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


async def _sync_db_config(
    db: AsyncSession,
    rds: redis.Redis | None,
    payload_items: list[dict[str, object]],
    user_site_names: list[str],
    user_role: str,
) -> None:
    if user_role == 'admin':
        sites_result = await db.execute(select(Site))
    else:
        if not user_site_names:
            if not payload_items:
                return
            raise HTTPException(status_code=403, detail='No accessible sites')
        sites_result = await db.execute(
            select(Site).where(Site.name.in_(user_site_names)),
        )
    sites = list(sites_result.unique().scalars().all())
    site_map = {site.name: site for site in sites}
    site_name_by_id = {site.id: site.name for site in sites}

    for cfg in payload_items:
        site_name = cfg.get('site')
        if not isinstance(site_name, str) or not site_name:
            raise HTTPException(status_code=400, detail='Site name is required')
        if user_role != 'admin' and site_name not in user_site_names:
            raise HTTPException(
                status_code=403,
                detail=f'Permission denied for site "{site_name}"',
            )
        if site_name not in site_map:
            raise HTTPException(
                status_code=404,
                detail=f'Site "{site_name}" not found',
            )

    site_ids_scope = [site.id for site in sites]
    if not site_ids_scope:
        return

    existing_result = await db.execute(
        select(StreamConfig)
        .options(
            selectinload(StreamConfig.site),
            selectinload(StreamConfig.group),
        )
        .where(StreamConfig.site_id.in_(site_ids_scope)),
    )
    existing_configs = list(existing_result.scalars().all())
    existing_map = {
        (cfg.site_id, cfg.stream_name): cfg for cfg in existing_configs
    }

    desired_keys: set[tuple[int, str]] = set()
    for cfg in payload_items:
        site_name = cfg.get('site')
        stream_name = cfg.get('stream_name')
        if not isinstance(stream_name, str) or not stream_name:
            raise HTTPException(
                status_code=400, detail='Stream name is required',
            )
        site_obj = site_map.get(site_name)
        if site_obj is None:
            raise HTTPException(
                status_code=404,
                detail=f'Site "{site_name}" not found',
            )
        desired_key = (site_obj.id, stream_name)
        if desired_key in desired_keys:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'Duplicate stream name "{stream_name}" '
                    f'for site "{site_name}"'
                ),
            )
        desired_keys.add(desired_key)

    for cfg in existing_configs:
        if (cfg.site_id, cfg.stream_name) not in desired_keys:
            if rds is not None:
                site_name = site_name_by_id.get(cfg.site_id)
                if site_name:
                    redis_key = (
                        f"stream_frame:{Utils.encode(site_name)}|"
                        f"{Utils.encode(cfg.stream_name)}"
                    )
                    try:
                        await rds.delete(redis_key)
                    except Exception as e:
                        print(
                            f"Failed to delete redis key {redis_key}: {e}",
                        )
            await db.delete(cfg)

    for cfg in payload_items:
        site_name = cfg.get('site')
        stream_name = cfg.get('stream_name')
        video_url = cfg.get('video_url')
        if not isinstance(video_url, str) or not video_url:
            raise HTTPException(
                status_code=400, detail='Video URL is required',
            )
        site_obj = site_map.get(site_name)
        if site_obj is None:
            raise HTTPException(
                status_code=404,
                detail=f'Site "{site_name}" not found',
            )
        group_id = site_obj.group_id
        if group_id is None:
            raise HTTPException(
                status_code=400,
                detail=f'Site "{site_obj.name}" has no group assigned',
            )

        detection_items = _ensure_detection_items(cfg)
        expires = _parse_expire_date(cfg.get('expire_date'))
        model_key = cfg.get('model_key') or 'yolo11n'
        detect_with_server = bool(cfg.get('detect_with_server'))
        store_in_redis = bool(cfg.get('store_in_redis'))
        work_start_hour = _coerce_int(cfg.get('work_start_hour'), 7)
        work_end_hour = _coerce_int(cfg.get('work_end_hour'), 18)

        existing = existing_map.get((site_obj.id, stream_name))
        if existing:
            existing.video_url = video_url
            existing.model_key = str(model_key)
            existing.detect_with_server = detect_with_server
            existing.store_in_redis = store_in_redis
            existing.work_start_hour = work_start_hour
            existing.work_end_hour = work_end_hour
            existing.expire_date = expires
            existing.detect_no_safety_vest_or_helmet = detection_items[
                'detect_no_safety_vest_or_helmet'
            ]
            existing.detect_near_machinery_or_vehicle = detection_items[
                'detect_near_machinery_or_vehicle'
            ]
            existing.detect_in_restricted_area = detection_items[
                'detect_in_restricted_area'
            ]
            existing.detect_in_utility_pole_restricted_area = detection_items[
                'detect_in_utility_pole_restricted_area'
            ]
            existing.detect_machinery_close_to_pole = detection_items[
                'detect_machinery_close_to_pole'
            ]
            existing.updated_at = datetime.now()
        else:
            db.add(
                StreamConfig(
                    group_id=group_id,
                    site_id=site_obj.id,
                    stream_name=stream_name,
                    video_url=video_url,
                    model_key=str(model_key),
                    detect_with_server=detect_with_server,
                    store_in_redis=store_in_redis,
                    work_start_hour=work_start_hour,
                    work_end_hour=work_end_hour,
                    expire_date=expires,
                    detect_no_safety_vest_or_helmet=detection_items[
                        'detect_no_safety_vest_or_helmet'
                    ],
                    detect_near_machinery_or_vehicle=detection_items[
                        'detect_near_machinery_or_vehicle'
                    ],
                    detect_in_restricted_area=detection_items[
                        'detect_in_restricted_area'
                    ],
                    detect_in_utility_pole_restricted_area=detection_items[
                        'detect_in_utility_pole_restricted_area'
                    ],
                    detect_machinery_close_to_pole=detection_items[
                        'detect_machinery_close_to_pole'
                    ],
                ),
            )

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f'Database error: {e}')


async def _fetch_db_config(
    db: AsyncSession,
    user_site_names: list[str],
    user_role: str,
) -> list[dict[str, object]]:
    stmt = select(StreamConfig).options(selectinload(StreamConfig.site))
    result = await db.execute(stmt)
    configs: list[StreamConfig] = list(result.scalars().all())

    items: list[dict[str, object]] = []
    for cfg in configs:
        site_name = cfg.site.name if cfg.site else ''
        if not site_name:
            continue
        if user_role != 'admin' and site_name not in user_site_names:
            continue
        items.append(
            _normalise_config_dict(
                {
                    'site': site_name,
                    'stream_name': cfg.stream_name,
                    'video_url': cfg.video_url,
                    'model_key': cfg.model_key,
                    'detect_with_server': cfg.detect_with_server,
                    'expire_date': cfg.expire_date,
                    'work_start_hour': cfg.work_start_hour,
                    'work_end_hour': cfg.work_end_hour,
                    'store_in_redis': cfg.store_in_redis,
                    'detect_no_safety_vest_or_helmet': cfg.detect_no_safety_vest_or_helmet,
                    'detect_near_machinery_or_vehicle': cfg.detect_near_machinery_or_vehicle,
                    'detect_in_restricted_area': cfg.detect_in_restricted_area,
                    'detect_in_utility_pole_restricted_area': cfg.detect_in_utility_pole_restricted_area,
                    'detect_machinery_close_to_pole': cfg.detect_machinery_close_to_pole,
                    'notifications': {},
                },
            ),
        )
    return items


def _try_load_file_config(repo_root: Path) -> list[dict[str, object]]:
    config_path = repo_root / 'config' / 'configuration.json'
    if not config_path.exists():
        return []
    try:
        raw = json.loads(config_path.read_text(encoding='utf-8'))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    items: list[dict[str, object]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        items.append(_normalise_config_dict(entry))
    return items


@router.get('/config')
async def get_config(
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
    db: AsyncSession = Depends(get_db),
    rds: redis.Redis | None = Depends(get_redis_pool_safe),
) -> dict[str, object]:
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token: no subject')

    _, user_site_names, user_role = await get_user_and_sites(db, username)

    raw = None
    if rds is not None:
        try:
            raw = await rds.get(b'chd:config')
        except Exception:
            raw = None
    if not raw:
        db_config = await _fetch_db_config(db, user_site_names, user_role)
        if db_config:
            return {'config': db_config}
        repo_root = Path(__file__).resolve().parents[3]
        file_config = _try_load_file_config(repo_root)
        if user_role != 'admin':
            file_config = [
                cfg
                for cfg in file_config
                if isinstance(cfg.get('site'), str)
                and cfg.get('site') in user_site_names
            ]
        return {'config': file_config}

    try:
        parsed = json.loads(raw.decode('utf-8'))
    except Exception:
        db_config = await _fetch_db_config(db, user_site_names, user_role)
        return {'config': db_config}

    config = parsed.get('config') if isinstance(parsed, dict) else parsed
    if not isinstance(config, list):
        db_config = await _fetch_db_config(db, user_site_names, user_role)
        return {'config': db_config}

    if user_role != 'admin':
        config = [
            cfg
            for cfg in config
            if isinstance(cfg, dict)
            and isinstance(cfg.get('site'), str)
            and cfg.get('site') in user_site_names
        ]

    config_dicts = [cfg for cfg in config if isinstance(cfg, dict)]
    if not config_dicts:
        db_config = await _fetch_db_config(db, user_site_names, user_role)
        if db_config:
            return {'config': db_config}
        repo_root = Path(__file__).resolve().parents[3]
        file_config = _try_load_file_config(repo_root)
        if user_role != 'admin':
            file_config = [
                cfg
                for cfg in file_config
                if isinstance(cfg.get('site'), str)
                and cfg.get('site') in user_site_names
            ]
        return {'config': file_config}

    return {'config': [_normalise_config_dict(cfg) for cfg in config_dicts]}


@router.post('/config')
async def set_config(
    payload: ConfigPayload,
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
    db: AsyncSession = Depends(get_db),
    rds: redis.Redis | None = Depends(get_redis_pool_safe),
) -> dict[str, str]:
    try:
        username: str | None = credentials.subject.get('username')
        if not username:
            raise HTTPException(status_code=401, detail='Invalid token: no subject')

        _, user_site_names, user_role = await get_user_and_sites(db, username)
        payload_items = [
            cfg for cfg in payload.config if isinstance(cfg, dict)
        ]

        await _sync_db_config(
            db,
            rds,
            payload_items,
            user_site_names,
            user_role,
        )

        data = {'config': [_normalise_config_dict(cfg) for cfg in payload_items]}
        if rds is not None:
            try:
                await rds.set(
                    b'chd:config',
                    json.dumps(data).encode('utf-8'),
                    ex=3600,
                )
            except Exception:
                pass
        return {'status': 'success'}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in set_config: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.get(
    '/labels',
    response_model=LabelListResponse,
    dependencies=[Depends(rate_limiter_index)],
)
async def get_labels_route(
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
    db: AsyncSession = Depends(get_db),
) -> LabelListResponse:
    try:
        username: str | None = credentials.subject.get('username')
        if not username:
            raise HTTPException(
                status_code=401, detail='Invalid token: no subject',
            )

        _, user_site_names, user_role = await get_user_and_sites(db, username)

        if user_role == 'admin':
            stmt = select(Site.name)
            result = await db.execute(stmt)
            labels = sorted(
                {
                    name
                    for (name,) in result.all()
                    if isinstance(name, str) and name
                },
            )
        else:
            labels = sorted(
                {
                    name
                    for name in user_site_names
                    if isinstance(name, str) and name
                },
            )

        return LabelListResponse(labels=labels)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to fetch labels: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch labels: {str(e)}",
        )


@router.post(
    '/frames',
    response_model=FramePostResponse,
)
async def post_frame(
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
    label: str = Form(...),
    key: str = Form(...),
    file: UploadFile = File(...),
    warnings_json: str = Form(''),
    cone_polygons_json: str = Form(''),
    pole_polygons_json: str = Form(''),
    detection_items_json: str = Form(''),
    width: int = Form(0),
    height: int = Form(0),
    rds: redis.Redis = Depends(get_redis_pool),
) -> FramePostResponse:
    try:
        frame_bytes: bytes = await file.read()
        await store_to_redis(
            rds,
            label,
            key,
            frame_bytes,
            warnings_json,
            cone_polygons_json,
            pole_polygons_json,
            detection_items_json,
            width,
            height,
        )
        return FramePostResponse(
            status='ok', message='Frame stored successfully.',
        )
    except Exception as e:
        print(f"Failed to store frame: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to store frame: {str(e)}",
        )


@router.delete(
    '/simulator/cleanup',
    dependencies=[Depends(rate_limiter_label)],
)
async def cleanup_simulator_streams(
    label: str,
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
    db: AsyncSession = Depends(get_db),
    rds: redis.Redis = Depends(get_redis_pool),
) -> dict[str, object]:
    try:
        username: str | None = credentials.subject.get('username')
        if not username:
            raise HTTPException(
                status_code=401,
                detail='Invalid token: no subject',
            )

        _, user_site_names, user_role = await get_user_and_sites(db, username)
        if user_role != 'admin' and label not in user_site_names:
            raise HTTPException(
                status_code=403,
                detail=f'Permission denied for label "{label}"',
            )

        encoded_label = Utils.encode(label)
        cursor: int = 0
        deleted_streams: list[str] = []
        deleted_keys: int = 0

        while True:
            cursor, keys = await rds.scan(
                cursor=cursor,
                match=f"stream_frame:{encoded_label}|*",
                count=500,
            )
            for raw_key in keys:
                redis_key = (
                    raw_key.decode('utf-8', errors='ignore')
                    if isinstance(raw_key, (bytes, bytearray))
                    else str(raw_key)
                )
                if not redis_key.startswith('stream_frame:'):
                    continue
                parts = redis_key.split('|', 1)
                if len(parts) != 2:
                    continue
                stream_name = Utils.decode(parts[1])
                if not stream_name.startswith('DEMO-CAM-'):
                    continue
                try:
                    deleted = await rds.delete(redis_key)
                except Exception:
                    deleted = 0
                if deleted:
                    deleted_keys += int(deleted)
                    deleted_streams.append(stream_name)

            if cursor == 0:
                break

        return {
            'status': 'ok',
            'deleted_keys': deleted_keys,
            'deleted_streams': sorted(set(deleted_streams)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Failed to cleanup simulator streams: {str(e)}',
        )


@router.websocket('/ws/labels/{label}')
async def websocket_label_stream(
    websocket: WebSocket,
    label: str,
    rds: redis.Redis = Depends(get_redis_pool_ws),
) -> None:
    await handle_label_stream_ws(
        websocket=websocket,
        label=label,
        rds=rds,
        settings=settings,
    )


@router.websocket('/hazard/ws/labels/{label}')
async def websocket_label_stream_hazard(
    websocket: WebSocket,
    label: str,
    rds: redis.Redis = Depends(get_redis_pool_ws),
) -> None:
    await handle_label_stream_ws(
        websocket=websocket,
        label=label,
        rds=rds,
        settings=settings,
    )


@router.websocket('/ws/stream/{label}/{key}')
async def websocket_stream(
    websocket: WebSocket,
    label: str,
    key: str,
    rds: redis.Redis = Depends(get_redis_pool_ws),
) -> None:
    await handle_stream_ws(
        websocket=websocket,
        label=label,
        key=key,
        rds=rds,
        settings=settings,
    )


@router.websocket('/hazard/ws/stream/{label}/{key}')
async def websocket_stream_hazard(
    websocket: WebSocket,
    label: str,
    key: str,
    rds: redis.Redis = Depends(get_redis_pool_ws),
) -> None:
    await handle_stream_ws(
        websocket=websocket,
        label=label,
        key=key,
        rds=rds,
        settings=settings,
    )


@router.websocket('/ws/frames')
async def websocket_frames(
    websocket: WebSocket,
    rds: redis.Redis = Depends(get_redis_pool_ws),
) -> None:
    await handle_frames_ws(websocket=websocket, rds=rds, settings=settings)


@router.websocket('/hazard/ws/frames')
async def websocket_frames_hazard(
    websocket: WebSocket,
    rds: redis.Redis = Depends(get_redis_pool_ws),
) -> None:
    await handle_frames_ws(websocket=websocket, rds=rds, settings=settings)
