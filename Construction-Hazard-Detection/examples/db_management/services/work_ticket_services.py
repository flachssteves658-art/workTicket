from __future__ import annotations

import ipaddress
import json
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from examples.db_management.schemas.work_ticket import CatalogImportRequest
from examples.db_management.schemas.work_ticket import CameraStreamBindingRequest
from examples.db_management.schemas.work_ticket import WorkTicketMatchRequest


load_dotenv(Path(__file__).resolve().parents[3] / '.camera.env', override=False)


def _clean(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _norm(value: Any) -> str:
    value_text = _clean(value).upper()
    value_text = value_text.replace('Ⅲ', 'III').replace('Ⅱ', 'II').replace('Ⅰ', 'I')
    return re.sub(r'[\s:：,，。;；()（）\-_/]+', '', value_text)


def _flatten(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [text_value for item in value.values() for text_value in _flatten(item)]
    if isinstance(value, list):
        return [text_value for item in value for text_value in _flatten(item)]
    value_text = _clean(value)
    return [value_text] if value_text else []


def _first(value: Any) -> str:
    values = _flatten(value)
    return values[0] if values else ''


def _work_area(value: Any) -> str:
    value_text = _clean(value)
    if not value_text:
        return ''
    area = re.split(r'[：:]', value_text, maxsplit=1)[0].strip()
    return area or value_text


def _work_locations(data: dict[str, Any]) -> list[str]:
    task_values: list[str] = []
    for task_group in (data.get('work_tasks'), data.get('工作任务')):
        tasks = task_group if isinstance(task_group, list) else [task_group]
        for task in tasks:
            if not isinstance(task, dict):
                continue
            for field in (
                'location_and_equipment',
                'work_location',
                '工作地点或地段',
                '工作地点或设备',
                '工作地点及设备双重名称',
            ):
                location = _work_area(task.get(field))
                if location:
                    task_values.append(location)
                    break
    if task_values:
        return list(dict.fromkeys(task_values))
    return list(dict.fromkeys(_flatten(data.get('work_location'))))


def _rows(result) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


def _build_rtsp_url(value: Any) -> str | None:
    ip_value = _clean(value)
    if not ip_value:
        return None
    try:
        parsed_ip = ipaddress.ip_address(ip_value)
    except ValueError as exc:
        raise ValueError(f'摄像头IP地址格式不正确: {ip_value}') from exc

    username = os.getenv('CAMERA_RTSP_USERNAME', '').strip()
    password = os.getenv('CAMERA_RTSP_PASSWORD', '').strip()
    if not username or not password:
        raise ValueError('未配置 CAMERA_RTSP_USERNAME 或 CAMERA_RTSP_PASSWORD')
    try:
        port = int(os.getenv('CAMERA_RTSP_PORT', '554'))
    except ValueError as exc:
        raise ValueError('CAMERA_RTSP_PORT 必须是数字') from exc
    if not 1 <= port <= 65535:
        raise ValueError('CAMERA_RTSP_PORT 必须在 1 到 65535 之间')

    stream_path = os.getenv('CAMERA_RTSP_PATH', 'stream0').strip().lstrip('/')
    if not stream_path:
        raise ValueError('CAMERA_RTSP_PATH 不能为空')
    host = f'[{parsed_ip}]' if parsed_ip.version == 6 else str(parsed_ip)
    return (
        f"rtsp://{quote(username, safe='')}:{quote(password, safe='')}"
        f'@{host}:{port}/{stream_path}'
    )


async def import_catalogs(
    payload: CatalogImportRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    equipment_sql = text(
        """
        INSERT INTO equipment_catalog (
            source_key, station_name, equipment_name, voltage_level,
            equipment_type, asset_no, running_no, interval_name, asset_status,
            running_status, dispatch_name, install_location, equipment_code,
            functional_location_code, normalized_search
        ) VALUES (
            :source_key, :station_name, :equipment_name, :voltage_level,
            :equipment_type, :asset_no, :running_no, :interval_name,
            :asset_status, :running_status, :dispatch_name, :install_location,
            :equipment_code, :functional_location_code, :normalized_search
        ) ON DUPLICATE KEY UPDATE
            station_name=VALUES(station_name), equipment_name=VALUES(equipment_name),
            voltage_level=VALUES(voltage_level), equipment_type=VALUES(equipment_type),
            asset_no=VALUES(asset_no), running_no=VALUES(running_no),
            interval_name=VALUES(interval_name), asset_status=VALUES(asset_status),
            running_status=VALUES(running_status), dispatch_name=VALUES(dispatch_name),
            install_location=VALUES(install_location), equipment_code=VALUES(equipment_code),
            functional_location_code=VALUES(functional_location_code),
            normalized_search=VALUES(normalized_search)
        """,
    )
    camera_sql = text(
        """
        INSERT INTO cameras (
            camera_id, station_name, nvr_name, channel_no, install_location,
            monitor_area, ip_address, running_status, retention_period
        ) VALUES (
            :camera_id, :station_name, :nvr_name, :channel_no,
            :install_location, :monitor_area, :ip_address,
            :running_status, :retention_period
        ) ON DUPLICATE KEY UPDATE
            station_name=VALUES(station_name), nvr_name=VALUES(nvr_name),
            channel_no=VALUES(channel_no), install_location=VALUES(install_location),
            monitor_area=VALUES(monitor_area), running_status=VALUES(running_status),
            ip_address=COALESCE(NULLIF(VALUES(ip_address), ''), ip_address),
            retention_period=VALUES(retention_period)
        """,
    )
    await db.execute(equipment_sql, [item.model_dump() for item in payload.equipment])
    await db.execute(camera_sql, [item.model_dump() for item in payload.cameras])
    await db.commit()
    return {
        'storage': 'mysql',
        'equipment_count': len(payload.equipment),
        'camera_count': len(payload.cameras),
        'equipment_source': payload.equipment_source,
        'camera_source': payload.camera_source,
    }


async def catalog_status(db: AsyncSession) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM equipment_catalog) equipment_count,
                    (SELECT COUNT(*) FROM cameras) camera_count,
                    (SELECT COUNT(*) FROM work_tickets) ticket_count,
                    (SELECT MAX(updated_at) FROM equipment_catalog) equipment_updated_at,
                    (SELECT MAX(updated_at) FROM cameras) camera_updated_at
                """,
            ),
        )
    ).mappings().first()
    values = dict(row or {})
    equipment_count = int(values.pop('equipment_count', 0) or 0)
    camera_count = int(values.pop('camera_count', 0) or 0)
    updated_values = [
        value
        for value in (
            values.pop('equipment_updated_at', None),
            values.pop('camera_updated_at', None),
        )
        if value is not None
    ]
    imported_at = max(updated_values).isoformat() if updated_values else None
    return {
        'ready': equipment_count > 0 and camera_count > 0,
        'storage': 'mysql',
        'equipment_count': equipment_count,
        'camera_count': camera_count,
        'ticket_count': int(values.get('ticket_count', 0) or 0),
        'imported_at': imported_at,
    }


def _station_for_ticket(
    corpus: str,
    equipment: list[dict[str, Any]],
    cameras: list[dict[str, Any]],
) -> str | None:
    stations = {
        _clean(item.get('station_name'))
        for item in [*equipment, *cameras]
        if item.get('station_name')
    }
    return next(
        (station for station in sorted(stations, key=len, reverse=True) if _norm(station) in corpus),
        None,
    )


def _match_equipment(
    corpus: str,
    station: str | None,
    equipment: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    for item in equipment:
        if station and _clean(item.get('station_name')) != station:
            continue
        aliases = [item.get('equipment_name'), item.get('running_no'), item.get('dispatch_name')]
        hit = next(
            (alias for alias in aliases if len(_norm(alias)) >= 4 and _norm(alias) in corpus),
            None,
        )
        if not hit:
            continue
        score = 55 + (35 if station else 0)
        if _norm(item.get('interval_name')) and _norm(item.get('interval_name')) in corpus:
            score += 10
        matches[item['source_key']] = {
            'source_key': item['source_key'],
            'raw_hit': _clean(hit),
            'equipment_name': _clean(item.get('equipment_name')),
            'equipment_code': _clean(item.get('equipment_code')),
            'functional_location_code': _clean(item.get('functional_location_code')),
            'interval_name': _clean(item.get('interval_name')),
            'equipment_type': _clean(item.get('equipment_type')),
            'voltage_level': _clean(item.get('voltage_level')),
            'status': _clean(item.get('running_status') or item.get('asset_status')),
            'confidence': min(score, 100) / 100,
        }
    return sorted(matches.values(), key=lambda item: item['confidence'], reverse=True)[:50]


def _number_conflict(equipment_name: str, camera_text: str) -> bool:
    equipment_units = set(re.findall(r'([12])号主变', equipment_name))
    camera_units = set(re.findall(r'([12])号主变', camera_text))
    return bool(equipment_units and camera_units and equipment_units != camera_units)


def _match_cameras(
    corpus: str,
    station: str | None,
    equipment: list[dict[str, Any]],
    cameras: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for camera in cameras:
        if station and _clean(camera.get('station_name')) != station:
            continue
        install_location = _clean(camera.get('install_location'))
        install_norm = _norm(install_location)
        if len(install_norm) < 3 or not corpus:
            continue
        if install_norm == corpus:
            score = 95
        elif install_norm in corpus:
            score = 90
        elif len(corpus) >= 4 and corpus in install_norm:
            score = 85
        else:
            continue
        reasons = ['工作地点命中摄像头安装位置']
        if station:
            reasons.insert(0, '站点一致')
        if _clean(camera.get('running_status')) == '正常':
            score += 5
            reasons.append('摄像头运行正常')
        confidence = max(0, min(score, 100)) / 100
        results.append(
            {
                'camera_id': camera['camera_id'],
                'channel_no': _clean(camera.get('channel_no')),
                'nvr_name': _clean(camera.get('nvr_name')),
                'station_name': _clean(camera.get('station_name')),
                'install_location': _clean(camera.get('install_location')),
                'monitor_area': _clean(camera.get('monitor_area')),
                'ip_address': _clean(camera.get('ip_address')) or None,
                'running_status': _clean(camera.get('running_status')),
                'stream_config_id': camera.get('stream_config_id'),
                'confidence': confidence,
                'decision': (
                    'auto_matched' if confidence >= 0.8
                    else 'needs_confirmation' if confidence >= 0.6
                    else 'candidate'
                ),
                'reasons': list(dict.fromkeys(reasons)),
                'linked_equipment': None,
                'linked_equipment_source_key': None,
            },
        )
    return sorted(results, key=lambda item: item['confidence'], reverse=True)


async def match_ticket(
    payload: WorkTicketMatchRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    equipment = _rows(await db.execute(text('SELECT * FROM equipment_catalog')))
    cameras = _rows(await db.execute(text('SELECT * FROM cameras')))
    if not equipment or not cameras:
        return {'status': 'catalog_required', 'catalog': await catalog_status(db)}
    existing_task_status = await db.scalar(
        text(
            'SELECT status FROM ai_detection_tasks WHERE ticket_no=:ticket_no',
        ),
        {'ticket_no': payload.ticket_no},
    )
    if existing_task_status in {'active', 'scheduled', 'ready'}:
        raise ValueError('该工作票已有就绪的AI检测任务，请先停止任务再重新匹配')
    if existing_task_status:
        await db.execute(
            text('DELETE FROM ai_detection_tasks WHERE ticket_no=:ticket_no'),
            {'ticket_no': payload.ticket_no},
        )
    corpus = _norm(' '.join(_flatten(payload.structured_data)))
    station = _station_for_ticket(corpus, equipment, cameras)
    equipment_matches = _match_equipment(corpus, station, equipment)
    data = payload.structured_data
    work_location = '；'.join(_work_locations(data))
    camera_matches = _match_cameras(
        _norm(work_location),
        station,
        equipment_matches,
        cameras,
    )
    await db.execute(
        text(
            """
            INSERT INTO work_tickets (
                ticket_no, station_name, work_leader, planned_start_time,
                planned_end_time, actual_start_time, actual_end_time,
                status, source_file, structured_json
            ) VALUES (
                :ticket_no, :station_name, :work_leader, :planned_start_time,
                :planned_end_time, :actual_start_time, :actual_end_time,
                'recognized', :source_file, :structured_json
            ) ON DUPLICATE KEY UPDATE station_name=VALUES(station_name),
                work_leader=VALUES(work_leader), planned_start_time=VALUES(planned_start_time),
                planned_end_time=VALUES(planned_end_time), actual_start_time=VALUES(actual_start_time),
                actual_end_time=VALUES(actual_end_time), source_file=VALUES(source_file),
                structured_json=VALUES(structured_json)
            """,
        ),
        {
            'ticket_no': payload.ticket_no,
            'station_name': station,
            'work_leader': _first(data.get('work_leader')),
            'planned_start_time': _first(data.get('planned_start_time')),
            'planned_end_time': _first(data.get('planned_end_time')),
            'actual_start_time': _first(data.get('actual_start_time')),
            'actual_end_time': _first(data.get('actual_end_time')),
            'source_file': payload.source_file,
            'structured_json': json.dumps(data, ensure_ascii=False),
        },
    )
    await db.execute(text('DELETE FROM ticket_camera_binding WHERE ticket_no=:ticket_no'), {'ticket_no': payload.ticket_no})
    await db.execute(text('DELETE FROM ticket_equipment WHERE ticket_no=:ticket_no'), {'ticket_no': payload.ticket_no})
    if equipment_matches:
        await db.execute(
            text(
                """
                INSERT INTO ticket_equipment (
                    ticket_no, equipment_source_key, raw_equipment_name,
                    standard_equipment_name, equipment_code, interval_name,
                    functional_location_code, match_confidence, match_method
                ) VALUES (
                    :ticket_no, :source_key, :raw_hit, :equipment_name,
                    :equipment_code, :interval_name, :functional_location_code,
                    :confidence, '站点+设备名称/运行编号/调度命名+所属间隔'
                )
                """,
            ),
            [{**item, 'ticket_no': payload.ticket_no} for item in equipment_matches],
        )
    if camera_matches:
        await db.execute(
            text(
                """
                INSERT INTO ticket_camera_binding (
                    ticket_no, equipment_source_key, camera_id, match_score,
                    match_method, decision, confirmed, monitor_start_time,
                    monitor_end_time
                ) VALUES (
                    :ticket_no, :linked_equipment_source_key, :camera_id,
                    :confidence, :match_method, :decision, FALSE,
                    :monitor_start_time, :monitor_end_time
                )
                """,
            ),
            [
                {
                    **item,
                    'ticket_no': payload.ticket_no,
                    'match_method': json.dumps(item['reasons'], ensure_ascii=False),
                    'monitor_start_time': _first(data.get('actual_start_time') or data.get('planned_start_time')),
                    'monitor_end_time': _first(data.get('actual_end_time') or data.get('planned_end_time')),
                }
                for item in camera_matches
            ],
        )
    await db.commit()
    return {
        'status': 'matched' if camera_matches else 'needs_manual_mapping',
        'storage': 'mysql',
        'ticket_no': payload.ticket_no,
        'station_name': station,
        'work_location': work_location or None,
        'equipment_matches': equipment_matches,
        'camera_matches': camera_matches,
        'summary': {
            'equipment_count': len(equipment_matches),
            'camera_count': len(camera_matches),
            'auto_matched_camera_count': sum(
                item['decision'] == 'auto_matched' for item in camera_matches
            ),
            'needs_confirmation': any(
                item['decision'] != 'auto_matched' for item in camera_matches
            ),
        },
    }


async def get_ticket_matches(ticket_no: str, db: AsyncSession) -> dict[str, Any] | None:
    ticket = (
        await db.execute(
            text('SELECT * FROM work_tickets WHERE ticket_no=:ticket_no'),
            {'ticket_no': ticket_no},
        )
    ).mappings().first()
    if not ticket:
        return None
    equipment = _rows(
        await db.execute(
            text('SELECT * FROM ticket_equipment WHERE ticket_no=:ticket_no ORDER BY match_confidence DESC'),
            {'ticket_no': ticket_no},
        ),
    )
    cameras = _rows(
        await db.execute(
            text(
                """
                SELECT b.*, c.station_name, c.nvr_name, c.channel_no,
                       c.install_location, c.monitor_area, c.running_status,
                       c.ip_address, c.stream_config_id
                FROM ticket_camera_binding b
                JOIN cameras c ON c.camera_id=b.camera_id
                WHERE b.ticket_no=:ticket_no ORDER BY b.match_score DESC
                """,
            ),
            {'ticket_no': ticket_no},
        ),
    )
    for item in cameras:
        item['confidence'] = float(item.pop('match_score'))
        item['confirmed'] = bool(item['confirmed'])
        try:
            item['reasons'] = json.loads(item.pop('match_method') or '[]')
        except json.JSONDecodeError:
            item['reasons'] = []
    for item in equipment:
        if isinstance(item.get('match_confidence'), Decimal):
            item['match_confidence'] = float(item['match_confidence'])
    return {
        'status': 'matched',
        'storage': 'mysql',
        'ticket_no': ticket_no,
        'station_name': ticket.get('station_name'),
        'work_location': '；'.join(
            _work_locations(json.loads(ticket['structured_json'])),
        ) or None,
        'equipment_matches': equipment,
        'camera_matches': cameras,
    }


def _parse_datetime_value(value: Any, field_name: str) -> datetime | None:
    raw_value = _clean(value)
    if not raw_value:
        return None

    normalized = raw_value.strip().replace('T', ' ')
    normalized = normalized.replace('年', '-').replace('月', '-').replace('日', ' ')
    normalized = normalized.replace('时', ':').replace('分', '').replace('秒', '')
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    normalized = re.sub(r'\s*[-/]\s*', '-', normalized)
    normalized = re.sub(r'\s*:\s*', ':', normalized)
    try:
        parsed = datetime.fromisoformat(normalized.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    match = re.search(
        r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})',
        raw_value,
    )
    if match:
        try:
            return datetime(*(int(part) for part in match.groups()))
        except ValueError:
            pass
    raise ValueError(f'{field_name}无法解析: {raw_value}')


def _monitor_window(data: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start_value = _first(data.get('actual_start_time')) or _first(
        data.get('planned_start_time'),
    )
    end_value = _first(data.get('actual_end_time')) or _first(
        data.get('planned_end_time'),
    )
    start_time = _parse_datetime_value(start_value, '工作票开始时间')
    end_time = _parse_datetime_value(end_value, '工作票结束时间')
    if start_time and end_time and start_time >= end_time:
        raise ValueError('工作票结束时间必须晚于开始时间')
    return start_time, end_time


def _ranges_overlap(
    start_a: datetime | None,
    end_a: datetime | None,
    start_b: datetime | None,
    end_b: datetime | None,
) -> bool:
    if end_a and start_b and end_a <= start_b:
        return False
    if end_b and start_a and end_b <= start_a:
        return False
    return True


def _serialize_datetimes(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.isoformat(sep=' ') if isinstance(value, datetime) else value
        for key, value in item.items()
    }


async def list_stream_options(db: AsyncSession) -> dict[str, Any]:
    rows = _rows(
        await db.execute(
            text(
                """
                SELECT sc.id stream_config_id, sc.stream_name,
                       s.id site_id, s.name station_name,
                       sc.active_ticket_no, sc.active_from, sc.active_to,
                       (
                           SELECT c.camera_id
                           FROM cameras c
                           WHERE c.stream_config_id=sc.id
                           LIMIT 1
                       ) mapped_camera_id
                FROM stream_configs sc
                JOIN sites s ON s.id=sc.site_id
                ORDER BY s.name, sc.stream_name, sc.id
                """,
            ),
        ),
    )
    return {
        'storage': 'mysql',
        'streams': [_serialize_datetimes(item) for item in rows],
    }


async def bind_camera_streams(
    payload: CameraStreamBindingRequest,
    db: AsyncSession,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    try:
        for binding in payload.bindings:
            camera = (
                await db.execute(
                    text(
                        """
                        SELECT camera_id, station_name, stream_config_id
                        FROM cameras
                        WHERE camera_id=:camera_id
                        FOR UPDATE
                        """,
                    ),
                    {'camera_id': binding.camera_id},
                )
            ).mappings().first()
            if not camera:
                raise ValueError(f'摄像头不存在: {binding.camera_id}')

            if binding.stream_config_id is None:
                await db.execute(
                    text(
                        """
                        UPDATE cameras
                        SET stream_config_id=NULL
                        WHERE camera_id=:camera_id
                        """,
                    ),
                    {'camera_id': binding.camera_id},
                )
                results.append(
                    {
                        'camera_id': binding.camera_id,
                        'stream_config_id': None,
                        'status': 'unbound',
                    },
                )
                continue

            stream = (
                await db.execute(
                    text(
                        """
                        SELECT sc.id stream_config_id, sc.stream_name,
                               s.name station_name
                        FROM stream_configs sc
                        JOIN sites s ON s.id=sc.site_id
                        WHERE sc.id=:stream_config_id
                        FOR UPDATE
                        """,
                    ),
                    {'stream_config_id': binding.stream_config_id},
                )
            ).mappings().first()
            if not stream:
                raise ValueError(
                    f'视频流配置不存在: {binding.stream_config_id}',
                )

            duplicate = (
                await db.execute(
                    text(
                        """
                        SELECT camera_id
                        FROM cameras
                        WHERE stream_config_id=:stream_config_id
                          AND camera_id<>:camera_id
                        LIMIT 1
                        """,
                    ),
                    {
                        'stream_config_id': binding.stream_config_id,
                        'camera_id': binding.camera_id,
                    },
                )
            ).scalar_one_or_none()
            if duplicate:
                raise ValueError(
                    f'视频流 {binding.stream_config_id} 已绑定摄像头 {duplicate}',
                )

            station_mismatch = (
                _norm(camera['station_name']) != _norm(stream['station_name'])
            )
            if station_mismatch and not payload.allow_station_mismatch:
                raise ValueError(
                    f"摄像头 {binding.camera_id} 属于 {camera['station_name']}，"
                    f"视频流属于 {stream['station_name']}；站点不一致",
                )

            await db.execute(
                text(
                    """
                    UPDATE cameras
                    SET stream_config_id=:stream_config_id
                    WHERE camera_id=:camera_id
                    """,
                ),
                {
                    'stream_config_id': binding.stream_config_id,
                    'camera_id': binding.camera_id,
                },
            )
            results.append(
                {
                    'camera_id': binding.camera_id,
                    'stream_config_id': binding.stream_config_id,
                    'stream_name': stream['stream_name'],
                    'station_name': stream['station_name'],
                    'station_mismatch': station_mismatch,
                    'status': 'bound',
                },
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {'storage': 'mysql', 'bindings': results}


async def get_detection_task(
    ticket_no: str,
    db: AsyncSession,
) -> dict[str, Any] | None:
    task = (
        await db.execute(
            text(
                """
                SELECT *
                FROM ai_detection_tasks
                WHERE ticket_no=:ticket_no
                """,
            ),
            {'ticket_no': ticket_no},
        )
    ).mappings().first()
    if not task:
        return None
    streams = _rows(
        await db.execute(
            text(
                """
                SELECT d.camera_id, d.stream_config_id,
                       sc.stream_name, s.name station_name
                FROM ai_detection_task_streams d
                LEFT JOIN stream_configs sc ON sc.id=d.stream_config_id
                LEFT JOIN sites s ON s.id=sc.site_id
                WHERE d.task_id=:task_id
                ORDER BY d.camera_id
                """,
            ),
            {'task_id': task['id']},
        ),
    )
    result = _serialize_datetimes(dict(task))
    result['streams'] = streams
    return result


async def cancel_detection_task(
    ticket_no: str,
    db: AsyncSession,
) -> dict[str, Any] | None:
    task = await get_detection_task(ticket_no, db)
    if not task:
        return None
    try:
        await db.execute(
            text(
                """
                UPDATE stream_configs
                SET active_ticket_no=NULL, active_from=NULL, active_to=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE active_ticket_no=:ticket_no
                """,
            ),
            {'ticket_no': ticket_no},
        )
        await db.execute(
            text(
                """
                UPDATE ai_detection_tasks
                SET status='cancelled', status_message='任务已取消'
                WHERE ticket_no=:ticket_no
                """,
            ),
            {'ticket_no': ticket_no},
        )
        await db.execute(
            text(
                """
                UPDATE work_tickets
                SET status='matched'
                WHERE ticket_no=:ticket_no
                """,
            ),
            {'ticket_no': ticket_no},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {
        'task_id': task['id'],
        'task_key': task['task_key'],
        'ticket_no': ticket_no,
        'status': 'cancelled',
        'message': '任务已取消，相关视频流将在下一次轮询后停止该工作票的AI检测',
    }


async def _ensure_camera_stream(
    camera: dict[str, Any],
    db: AsyncSession,
) -> int | None:
    current_id = camera.get('stream_config_id')
    if current_id:
        return int(current_id)

    video_url = _build_rtsp_url(camera.get('ip_address'))
    if not video_url:
        return None

    station_name = _clean(camera.get('station_name'))
    if not station_name:
        raise ValueError(f"摄像头 {camera['camera_id']} 缺少所属站点")
    group_id = await db.scalar(
        text('SELECT id FROM group_info ORDER BY id LIMIT 1'),
    )
    if group_id is None:
        raise ValueError('数据库中没有可用的工地群组，无法创建视频流')

    await db.execute(
        text(
            """
            INSERT INTO sites (name, group_id)
            VALUES (:station_name, :group_id)
            ON DUPLICATE KEY UPDATE
                id=LAST_INSERT_ID(id),
                group_id=COALESCE(group_id, VALUES(group_id))
            """,
        ),
        {'station_name': station_name, 'group_id': group_id},
    )
    site_id = await db.scalar(
        text('SELECT id FROM sites WHERE name=:station_name'),
        {'station_name': station_name},
    )
    if site_id is None:
        raise ValueError(f'无法为站点 {station_name} 创建视频流')

    camera_id = _clean(camera.get('camera_id'))
    await db.execute(
        text(
            """
            INSERT INTO stream_configs (
                group_id, site_id, stream_name, video_url, model_key,
                detect_no_safety_vest_or_helmet,
                detect_near_machinery_or_vehicle,
                detect_in_restricted_area,
                detect_in_utility_pole_restricted_area,
                detect_machinery_close_to_pole,
                detect_with_server, expire_date, work_start_hour,
                work_end_hour, store_in_redis
            ) VALUES (
                :group_id, :site_id, :stream_name, :video_url, :model_key,
                TRUE, TRUE, TRUE, FALSE, FALSE, TRUE, NULL, 0, 24, TRUE
            ) ON DUPLICATE KEY UPDATE
                video_url=VALUES(video_url),
                updated_at=CURRENT_TIMESTAMP
            """,
        ),
        {
            'group_id': group_id,
            'site_id': site_id,
            'stream_name': camera_id,
            'video_url': video_url,
            'model_key': os.getenv('CAMERA_DEFAULT_MODEL_KEY', 'yolo11n'),
        },
    )
    stream_config_id = await db.scalar(
        text(
            """
            SELECT id FROM stream_configs
            WHERE site_id=:site_id AND stream_name=:stream_name
            """,
        ),
        {'site_id': site_id, 'stream_name': camera_id},
    )
    if stream_config_id is None:
        raise ValueError(f'无法为摄像头 {camera_id} 创建视频流')
    await db.execute(
        text(
            """
            UPDATE cameras SET stream_config_id=:stream_config_id
            WHERE camera_id=:camera_id
            """,
        ),
        {'stream_config_id': stream_config_id, 'camera_id': camera_id},
    )
    camera['stream_config_id'] = int(stream_config_id)
    return int(stream_config_id)


async def confirm_ticket_cameras(
    ticket_no: str,
    camera_ids: list[str],
    confirmed_by: str,
    db: AsyncSession,
) -> dict[str, Any]:
    match_result = await get_ticket_matches(ticket_no, db)
    if not match_result:
        raise ValueError('未找到工作票匹配结果')
    available = {item['camera_id']: item for item in match_result['camera_matches']}
    missing = [camera_id for camera_id in camera_ids if camera_id not in available]
    if missing:
        raise ValueError(f"摄像头不在候选列表中: {', '.join(missing)}")
    selected = [available[camera_id] for camera_id in camera_ids]
    ticket = (
        await db.execute(
            text('SELECT structured_json FROM work_tickets WHERE ticket_no=:ticket_no'),
            {'ticket_no': ticket_no},
        )
    ).mappings().first()
    structured_data = json.loads(ticket['structured_json']) if ticket else {}
    monitor_start_time, monitor_end_time = _monitor_window(structured_data)

    valid_streams: dict[str, dict[str, Any]] = {}
    missing_stream_camera_ids: list[str] = []
    missing_ip_camera_ids: list[str] = []
    conflicts: list[str] = []
    for item in selected:
        stream_config_id = await _ensure_camera_stream(item, db)
        if not stream_config_id:
            missing_stream_camera_ids.append(item['camera_id'])
            if not item.get('ip_address'):
                missing_ip_camera_ids.append(item['camera_id'])
            continue
        stream = (
            await db.execute(
                text(
                    """
                    SELECT sc.id stream_config_id, sc.stream_name,
                           sc.active_ticket_no, sc.active_from, sc.active_to,
                           s.name station_name
                    FROM stream_configs sc
                    JOIN sites s ON s.id=sc.site_id
                    WHERE sc.id=:stream_config_id
                    FOR UPDATE
                    """,
                ),
                {'stream_config_id': stream_config_id},
            )
        ).mappings().first()
        if not stream:
            missing_stream_camera_ids.append(item['camera_id'])
            continue
        if _norm(item['station_name']) != _norm(stream['station_name']):
            missing_stream_camera_ids.append(item['camera_id'])
            continue
        if (
            stream['active_ticket_no']
            and stream['active_ticket_no'] != ticket_no
            and _ranges_overlap(
                monitor_start_time,
                monitor_end_time,
                stream['active_from'],
                stream['active_to'],
            )
        ):
            conflicts.append(
                f"{item['camera_id']} / {stream['stream_name']} "
                f"已分配给工作票 {stream['active_ticket_no']}",
            )
        valid_streams[item['camera_id']] = dict(stream)
    if conflicts:
        raise ValueError('视频流任务时间冲突: ' + '; '.join(conflicts))

    if len(valid_streams) != len(selected):
        task_status = 'awaiting_stream_configuration'
        if missing_ip_camera_ids:
            status_message = (
                '请先在 cameras.ip_address 中填写摄像头IP，然后再次确认: '
                + ', '.join(missing_ip_camera_ids)
            )
        else:
            status_message = '请先把缺少配置的摄像头绑定到同站点视频流，然后再次确认'
    else:
        now = datetime.now()
        if monitor_end_time and now > monitor_end_time:
            task_status = 'expired'
            status_message = '工作票时间窗已经结束，任务仅作为历史记录保存，不会启动AI检测'
        elif monitor_start_time and now < monitor_start_time:
            task_status = 'scheduled'
            status_message = '任务已排期，监控进程将在工作票开始时间进入AI检测'
        else:
            task_status = 'active'
            status_message = '任务已激活，监控进程将在下一次轮询后执行AI检测'

    try:
        await db.execute(
            text(
                """
                INSERT INTO ai_detection_tasks (
                    task_key, ticket_no, monitor_start_time, monitor_end_time,
                    status, confirmed_by, status_message
                ) VALUES (
                    :task_key, :ticket_no, :monitor_start_time,
                    :monitor_end_time, :status, :confirmed_by, :status_message
                ) ON DUPLICATE KEY UPDATE
                    monitor_start_time=VALUES(monitor_start_time),
                    monitor_end_time=VALUES(monitor_end_time),
                    status=VALUES(status), confirmed_by=VALUES(confirmed_by),
                    status_message=VALUES(status_message)
                """,
            ),
            {
                'task_key': f'ticket:{ticket_no}',
                'ticket_no': ticket_no,
                'monitor_start_time': monitor_start_time,
                'monitor_end_time': monitor_end_time,
                'status': task_status,
                'confirmed_by': confirmed_by,
                'status_message': status_message,
            },
        )
        task_id = await db.scalar(
            text(
                'SELECT id FROM ai_detection_tasks WHERE ticket_no=:ticket_no',
            ),
            {'ticket_no': ticket_no},
        )
        await db.execute(
            text('DELETE FROM ai_detection_task_streams WHERE task_id=:task_id'),
            {'task_id': task_id},
        )
        await db.execute(
            text(
                """
                INSERT INTO ai_detection_task_streams (
                    task_id, camera_id, stream_config_id
                ) VALUES (:task_id, :camera_id, :stream_config_id)
                """,
            ),
            [
                {
                    'task_id': task_id,
                    'camera_id': item['camera_id'],
                    'stream_config_id': (
                        valid_streams.get(item['camera_id'], {}).get(
                            'stream_config_id',
                        )
                    ),
                }
                for item in selected
            ],
        )
        await db.execute(
            text(
                """
                UPDATE ticket_camera_binding
                SET confirmed=FALSE, confirmed_by=NULL
                WHERE ticket_no=:ticket_no
                """,
            ),
            {'ticket_no': ticket_no},
        )
        for camera_id in camera_ids:
            await db.execute(
                text(
                    """
                    UPDATE ticket_camera_binding
                    SET confirmed=TRUE, confirmed_by=:confirmed_by
                    WHERE ticket_no=:ticket_no AND camera_id=:camera_id
                    """,
                ),
                {
                    'ticket_no': ticket_no,
                    'camera_id': camera_id,
                    'confirmed_by': confirmed_by,
                },
            )

        # Clear this ticket's previous assignment before applying the current
        # confirmed set.  Other tickets are never touched.
        await db.execute(
            text(
                """
                UPDATE stream_configs
                SET active_ticket_no=NULL, active_from=NULL, active_to=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE active_ticket_no=:ticket_no
                """,
            ),
            {'ticket_no': ticket_no},
        )
        if task_status in {'active', 'scheduled'}:
            await db.execute(
                text(
                    """
                    UPDATE stream_configs
                    SET active_ticket_no=:ticket_no,
                        active_from=:active_from,
                        active_to=:active_to,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:stream_config_id
                    """,
                ),
                [
                    {
                        'ticket_no': ticket_no,
                        'active_from': monitor_start_time,
                        'active_to': monitor_end_time,
                        'stream_config_id': stream['stream_config_id'],
                    }
                    for stream in valid_streams.values()
                ],
            )
        await db.execute(
            text('UPDATE work_tickets SET status=:status WHERE ticket_no=:ticket_no'),
            {'status': task_status, 'ticket_no': ticket_no},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    stream_ids = [
        valid_streams[camera_id]['stream_config_id']
        for camera_id in camera_ids
        if camera_id in valid_streams
    ]
    return {
        'task_id': task_id,
        'task_key': f'ticket:{ticket_no}',
        'ticket_no': ticket_no,
        'camera_ids': camera_ids,
        'stream_config_ids': stream_ids,
        'cameras': selected,
        'missing_stream_camera_ids': missing_stream_camera_ids,
        'missing_ip_camera_ids': missing_ip_camera_ids,
        'monitor_start_time': monitor_start_time.isoformat(sep=' ') if monitor_start_time else None,
        'monitor_end_time': monitor_end_time.isoformat(sep=' ') if monitor_end_time else None,
        'status': task_status,
        'message': status_message,
    }
