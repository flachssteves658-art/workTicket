from __future__ import annotations

from datetime import datetime

from examples.db_management.services.work_ticket_services import _match_cameras
from examples.db_management.services.work_ticket_services import _build_rtsp_url
from examples.db_management.services.work_ticket_services import _monitor_window
from examples.db_management.services.work_ticket_services import _norm
from examples.db_management.services.work_ticket_services import _work_locations


def _equipment(source_key: str) -> dict[str, str]:
    return {
        'source_key': source_key,
        'equipment_name': 'ABC123设备',
        'equipment_code': source_key,
        'functional_location_code': '',
        'interval_name': '',
        'equipment_type': '测试设备',
        'voltage_level': '110kV',
        'status': '正常',
    }


def test_empty_camera_location_is_not_a_match() -> None:
    result = _match_cameras(
        corpus=_norm('测试站 ABC123设备'),
        station='测试站',
        equipment=[_equipment('eq-1')],
        cameras=[
            {
                'camera_id': 'empty-camera',
                'station_name': '测试站',
                'install_location': '',
                'monitor_area': '',
                'ip_address': '',
                'running_status': '正常',
                'stream_config_id': None,
            },
        ],
    )

    assert result == []


def test_work_location_matches_install_location_and_returns_ip() -> None:
    result = _match_cameras(
        corpus=_norm('主变及无功补偿保护小室：111B站用变保护屏前后'),
        station='测试站',
        equipment=[_equipment('eq-1')],
        cameras=[
            {
                'camera_id': 'camera-1',
                'station_name': '测试站',
                'install_location': '主变及无功补偿保护小室',
                'monitor_area': '完全不同的监控描述',
                'ip_address': '192.168.31.123',
                'running_status': '正常',
                'stream_config_id': None,
            },
        ],
    )

    assert len(result) == 1
    assert result[0]['confidence'] == 0.95
    assert result[0]['ip_address'] == '192.168.31.123'
    assert '工作地点命中摄像头安装位置' in result[0]['reasons']


def test_work_locations_falls_back_to_structured_work_tasks() -> None:
    result = _work_locations(
        {
            'work_tasks': [
                {'location_and_equipment': '1000kV1号保护小室：二次设备屏柜前和后'},
                {'location_and_equipment': '自动化机房：二次设备屏柜前和后'},
            ],
        },
    )

    assert result == [
        '1000kV1号保护小室',
        '自动化机房',
    ]


def test_work_locations_reads_chinese_double_name_field() -> None:
    result = _work_locations(
        {
            '工作任务': [
                {'工作地点及设备双重名称': '自动化机房：电力系统相量测量主机屏前和后'},
            ],
        },
    )

    assert result == ['自动化机房']


def test_work_locations_prefers_task_area_over_explicit_model_value() -> None:
    result = _work_locations(
        {
            'work_location': '保护小室；自动化机房',
            'work_tasks': [{'location_and_equipment': '保护小室'}],
        },
    )

    assert result == ['保护小室']


def test_monitor_area_alone_does_not_match() -> None:
    result = _match_cameras(
        corpus=_norm('主变及无功补偿保护小室'),
        station='测试站',
        equipment=[],
        cameras=[
            {
                'camera_id': 'camera-1',
                'station_name': '测试站',
                'install_location': '500kV设备区',
                'monitor_area': '主变及无功补偿保护小室',
                'ip_address': '192.168.31.123',
                'running_status': '正常',
                'stream_config_id': None,
            },
        ],
    )

    assert result == []


def test_build_rtsp_url_from_camera_ip(monkeypatch) -> None:
    monkeypatch.setenv('CAMERA_RTSP_USERNAME', 'admin')
    monkeypatch.setenv('CAMERA_RTSP_PASSWORD', 'p@ss word')
    monkeypatch.setenv('CAMERA_RTSP_PORT', '554')
    monkeypatch.setenv('CAMERA_RTSP_PATH', 'stream0')

    assert _build_rtsp_url('192.168.31.123') == (
        'rtsp://admin:p%40ss%20word@192.168.31.123:554/stream0'
    )


def test_monitor_window_prefers_actual_times() -> None:
    start, end = _monitor_window(
        {
            'planned_start_time': '2026-05-05 08:00',
            'planned_end_time': '2026-05-07 18:00',
            'actual_start_time': '2026年05月05日14时01分',
            'actual_end_time': '2026年05月07日17时32分',
        },
    )

    assert start == datetime(2026, 5, 5, 14, 1)
    assert end == datetime(2026, 5, 7, 17, 32)
