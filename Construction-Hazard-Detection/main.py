from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import logging
import math
import multiprocessing
import os
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from multiprocessing import Process
from typing import TypedDict

import cv2
from asyncmy import create_pool
from dotenv import load_dotenv
from sqlalchemy.engine.url import make_url
import httpx

from src.danger_detector import DangerDetector
from src.frame_sender import BackendFrameSender
from src.live_stream_detection import LiveStreamDetector
from src.monitor_logger import LoggerConfig
from src.notifiers.fcm_notifier import FCMSender
from src.latest_frame_capture import LatestFrameCapture as StreamCapture
from src.utils import RedisManager
from src.utils import Utils
from src.violation_sender import ViolationSender

load_dotenv()


class StreamConfig(TypedDict, total=False):
    """
    Represents the configuration structure for a video stream as retrieved
    from the database.
    """
    video_url: str
    updated_at: str
    model_key: str
    site: str
    stream_name: str
    detect_with_server: bool
    expire_date: str | None
    detection_items: dict[str, bool]
    work_start_hour: int
    work_end_hour: int
    store_in_redis: bool
    active_ticket_no: str | None
    active_from: str | None
    active_to: str | None


def _parse_stream_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(
            tzinfo=None,
        )
    except ValueError:
        return None


class MainApp:
    """
    Core application responsible for:
        - Polling stream configuration from database periodically
        - Dynamically spawning/stopping child processes for each video stream
        - Cleaning up expired or modified configurations
    """

    def __init__(self, poll_interval: int = 10) -> None:
        """
        Initialise the application.

        Args:
            poll_interval (int): Interval in seconds to poll the database for
                stream configuration updates.
        """
        self.poll_interval = poll_interval
        self.logger = LoggerConfig().get_logger()
        # video_url → process info dict
        self.running_processes: dict[str, dict] = {}
        self.lock = asyncio.Lock()  # Prevent overlapping reloads
        self.db_pool = None  # Will hold MySQL connection pool

        # Process pool management to improve performance
        self.max_workers = min(multiprocessing.cpu_count(), 8)
        self.process_executor: ProcessPoolExecutor | None = None

    async def _ensure_db_pool(self) -> None:
        """
        Ensure a connection pool to the database is
        established before querying.
        """
        if self.db_pool is None:
            database_url = os.getenv('DATABASE_URL')
            if database_url is None:
                raise RuntimeError(
                    'DATABASE_URL environment variable is required',
                )
            url = make_url(database_url)
            self.logger.info(f"Connecting to DB: {url.host}:{url.port}")
            self.db_pool = await create_pool(
                host=url.host,
                port=url.port or 3306,
                user=url.username,
                password=url.password,
                db=url.database,
                minsize=2,  # Minimum connections
                maxsize=10,  # Maximum connections
                pool_recycle=3600,  # 1 hour connection recycling
                autocommit=True,
                echo=False,  # Disable SQL logging for performance
                charset='utf8mb4',
            )

    async def fetch_stream_configs(self) -> list[StreamConfig]:
        """
        Query the database for current stream configurations.

        Returns:
            list[StreamConfig]: All active stream configuration records.
        """
        await self._ensure_db_pool()
        if self.db_pool is None:
            raise RuntimeError(
                'Database pool is not initialized. Check DATABASE_URL and '
                'DB connectivity.',
            )
        sql = """
        SELECT sc.video_url,
               sc.updated_at,
               sc.model_key,
               s.name              AS site,
               sc.stream_name,
               sc.detect_with_server,
               sc.expire_date,
               sc.work_start_hour,
               sc.work_end_hour,
               sc.store_in_redis,
               sc.detect_no_safety_vest_or_helmet,
               sc.detect_near_machinery_or_vehicle,
               sc.detect_in_restricted_area,
               sc.detect_in_utility_pole_restricted_area,
               sc.detect_machinery_close_to_pole,
               sc.active_ticket_no,
               sc.active_from,
               sc.active_to
        FROM stream_configs sc
        JOIN sites s ON sc.site_id = s.id
        """
        async with self.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                rows = await cur.fetchall()

        configs: list[StreamConfig] = []
        self.logger.info(f"Found {len(rows)} active streams")

        for row in rows:
            if len(row) >= 18:
                (
                    video_url,
                    updated_at,
                    model_key,
                    site,
                    stream_name,
                    detect_with_server,
                    expire_date,
                    work_start,
                    work_end,
                    store_in_redis,
                    vest_helmet,
                    near_vehicle,
                    in_area,
                    in_pole_area,
                    machine_close_pole,
                    active_ticket_no,
                    active_from,
                    active_to,
                ) = row
            else:
                (
                    video_url,
                    updated_at,
                    model_key,
                    site,
                    stream_name,
                    detect_with_server,
                    expire_date,
                    work_start,
                    work_end,
                    store_in_redis,
                    vest_helmet,
                    near_vehicle,
                    in_area,
                    in_pole_area,
                    machine_close_pole,
                ) = row
                active_ticket_no = None
                active_from = None
                active_to = None

            self.logger.info(f"Loaded stream: {site} ({video_url})")

            # Organise detection flags into a dictionary
            detection_items = {
                'detect_no_safety_vest_or_helmet': bool(vest_helmet),
                'detect_near_machinery_or_vehicle': bool(near_vehicle),
                'detect_in_restricted_area': bool(in_area),
                'detect_in_utility_pole_restricted_area': bool(in_pole_area),
                'detect_machinery_close_to_pole': bool(machine_close_pole),
            }

            configs.append(
                StreamConfig(
                    video_url=video_url,
                    updated_at=updated_at.isoformat(),
                    model_key=model_key,
                    site=site,
                    stream_name=stream_name,
                    detect_with_server=bool(detect_with_server),
                    expire_date=(
                        expire_date.isoformat() if expire_date else None
                    ),
                    detection_items=detection_items,
                    work_start_hour=int(work_start or 7),
                    work_end_hour=int(work_end or 18),
                    store_in_redis=bool(store_in_redis),
                    active_ticket_no=str(active_ticket_no) if active_ticket_no else None,
                    active_from=active_from.isoformat() if active_from else None,
                    active_to=active_to.isoformat() if active_to else None,
                ),
            )

        return configs

    async def poll_and_reload(self) -> None:
        """
        Periodically poll the database and trigger reload logic.
        This function will run indefinitely unless interrupted.
        """
        while True:
            try:
                await self.reload_configurations()
            except Exception as e:
                self.logger.exception(f"[poll] Reload error: {e}")
            await asyncio.sleep(self.poll_interval)

    async def reload_configurations(self) -> None:
        """
        Main configuration reload logic:
            - Stops expired or deleted stream processes
            - Restarts modified streams (based on updated_at)
            - Starts newly added streams not yet tracked
        """
        async with self.lock:
            configs = await self.fetch_stream_configs()
            cfg_map = {c['video_url']: c for c in configs}

            # 1. Stop removed or expired streams
            for video_url in list(self.running_processes.keys()):
                proc_info = self.running_processes[video_url]
                cfg = cfg_map.get(video_url)

                if not cfg or Utils.is_expired(cfg.get('expire_date')):
                    self.logger.info(f"Stop stream {video_url}")
                    self.stop_process(proc_info['process'])

                    if proc_info['cfg'].get('store_in_redis'):
                        redis_key = (
                            f"stream_frame:"
                            f"{Utils.encode(proc_info['cfg']['site'])}"
                            f"|{Utils.encode(proc_info['cfg']['stream_name'])}"
                        )
                        redis_manager = RedisManager()
                        await redis_manager.delete(redis_key)

                    del self.running_processes[video_url]
                    continue

                # 2. Restart if config updated or the worker exited unexpectedly.
                if (
                    cfg['updated_at'] != proc_info['updated_at']
                    or not proc_info['process'].is_alive()
                ):
                    restart_reason = (
                        'configuration updated'
                        if cfg['updated_at'] != proc_info['updated_at']
                        else 'worker exited unexpectedly'
                    )
                    self.logger.info(
                        f"Restart stream {video_url} ({restart_reason})",
                    )
                    self.stop_process(proc_info['process'])

                    if proc_info['cfg'].get('store_in_redis'):
                        redis_key = (
                            f"stream_frame:"
                            f"{Utils.encode(proc_info['cfg']['site'])}"
                            f"|{Utils.encode(proc_info['cfg']['stream_name'])}"
                        )
                        redis_manager = RedisManager()
                        await redis_manager.delete(redis_key)

                    new_proc = self.start_process(cfg)
                    self.running_processes[video_url] = {
                        'process': new_proc,
                        'updated_at': cfg['updated_at'],
                        'cfg': cfg,
                    }

            # 3. Start any new streams
            for video_url, cfg in cfg_map.items():
                if Utils.is_expired(cfg.get('expire_date')):
                    continue
                if video_url not in self.running_processes:
                    self.logger.info(
                        f"Launch new stream {video_url}",
                    )
                    proc = self.start_process(cfg)
                    self.running_processes[video_url] = {
                        'process': proc,
                        'updated_at': cfg['updated_at'],
                        'cfg': cfg,
                    }

    def start_process(self, cfg: StreamConfig) -> Process:
        """
        Launch a new child process to handle stream detection.

        Args:
            cfg (StreamConfig): Configuration for the stream.

        Returns:
            Process: The new multiprocessing.Process object.
        """
        p = Process(target=process_single_stream, args=(cfg,))
        p.start()
        return p

    def stop_process(self, proc: Process) -> None:
        """
        Gracefully terminate a child process.

        Args:
            proc (Process): The process to be terminated.
        """
        try:
            # Attempt graceful termination
            proc.terminate()
            proc.join(timeout=10)  # Wait for up to 10 seconds

            if proc.is_alive():
                # If still alive, force kill
                proc.kill()
                proc.join()
        except Exception as e:
            self.logger.error(f"Error stopping process: {e}")

    async def cleanup_resources(self) -> None:
        """
        Clean up all resources
        """
        # Stop all processes
        for info in self.running_processes.values():
            self.stop_process(info['process'])
        self.running_processes.clear()

        # Close process pool
        if self.process_executor:
            self.process_executor.shutdown(wait=True)

        # Close database connection pool
        if self.db_pool:
            self.db_pool.close()
            await self.db_pool.wait_closed()

    async def run(self) -> None:
        """
        Start the application loop that continuously checks the stream configs.
        """
        try:
            await self.poll_and_reload()
        except KeyboardInterrupt:
            self.logger.info('Received keyboard interrupt, shutting down...')
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            await self.cleanup_resources()


async def _run_single_stream(cfg: StreamConfig) -> None:
    """Run one stream processing coroutine for the given configuration."""
    video_url = cfg['video_url']
    model_key = cfg['model_key']
    site = cfg['site']
    stream_name = cfg['stream_name']
    detect_with_server = cfg['detect_with_server']
    detection_items = cfg['detection_items']
    work_start_hour = cfg['work_start_hour']
    work_end_hour = cfg['work_end_hour']
    store_in_redis = cfg['store_in_redis']
    active_ticket_no = cfg.get('active_ticket_no')
    active_from = _parse_stream_datetime(cfg.get('active_from'))
    active_to = _parse_stream_datetime(cfg.get('active_to'))

    # Initialise logging for this process
    logger_config = LoggerConfig(log_file='streams.log')
    logger = logger_config.get_logger()

    # Propagate logs from libraries (like frame_sender) to our file
    root_logger = logging.getLogger()
    if not root_logger.hasHandlers():
        for handler in logger.handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    logger.info(f"[{site}:{stream_name}] Starting stream process for {video_url}")

    agent_report_mode = (os.getenv('AGENT_REPORT_MODE') or 'llm').strip().lower()
    try:
        agent_report_min_interval_seconds = int(
            os.getenv('AGENT_REPORT_MIN_INTERVAL_SECONDS') or '0',
        )
    except Exception:
        agent_report_min_interval_seconds = 0
    try:
        agent_report_cache_ttl_seconds = int(
            os.getenv('AGENT_REPORT_CACHE_TTL_SECONDS') or '3600',
        )
    except Exception:
        agent_report_cache_ttl_seconds = 3600
    try:
        agent_report_top_detections = int(
            os.getenv('AGENT_REPORT_TOP_DETECTIONS') or '5',
        )
    except Exception:
        agent_report_top_detections = 5

    last_agent_report_key: str | None = None
    last_agent_report_content: str | None = None
    last_agent_report_time: float = 0.0

    async def _generate_agent_report(
        ticket_no: str | None,
        site_name: str,
        stream: str,
        detected_at: datetime,
        warnings: dict,
        detections: list,
    ) -> str | None:
        nonlocal last_agent_report_key
        nonlocal last_agent_report_content
        nonlocal last_agent_report_time

        mode = agent_report_mode
        if mode in ('off', 'disabled', 'false', '0', 'none'):
            return None

        warnings_dict = warnings if isinstance(warnings, dict) else {}
        warning_parts: list[str] = []
        for key, value in warnings_dict.items():
            count = 0
            if isinstance(value, dict):
                raw = value.get('count')
                try:
                    count = int(raw) if raw is not None else 0
                except Exception:
                    count = 0
            if count:
                warning_parts.append(f"{key}: {count}")

        counts_by_class: dict[int, int] = {}
        top_detections: list[dict[str, int | float]] = []
        if isinstance(detections, list):
            candidates: list[tuple[float, int]] = []
            for row in detections:
                if not isinstance(row, list) or len(row) < 6:
                    continue
                try:
                    conf = float(row[4])
                    cls_id = int(row[5])
                except Exception:
                    continue
                if not math.isfinite(conf):
                    continue
                counts_by_class[cls_id] = counts_by_class.get(cls_id, 0) + 1
                candidates.append((conf, cls_id))
            candidates.sort(reverse=True)
            for conf, cls_id in candidates[: max(0, agent_report_top_detections)]:
                top_detections.append({'class_id': cls_id, 'confidence': conf})

        normalized_violation = {
            'ticket_no': ticket_no or '',
            'site': site_name,
            'stream_name': stream,
            'warnings': warnings_dict,
            'detection_counts': counts_by_class,
            'top_detections': top_detections,
        }
        key_source = json.dumps(normalized_violation, ensure_ascii=False, sort_keys=True)
        cache_key = hashlib.sha256(key_source.encode('utf-8')).hexdigest()
        now = time.time()

        if (
            last_agent_report_key == cache_key
            and (now - last_agent_report_time) < max(0, agent_report_cache_ttl_seconds)
        ):
            return last_agent_report_content

        if (
            agent_report_min_interval_seconds > 0
            and (now - last_agent_report_time) < agent_report_min_interval_seconds
        ):
            return last_agent_report_content

        if mode in ('mock', 'test'):
            if warning_parts:
                last_agent_report_key = cache_key
                last_agent_report_time = now
                last_agent_report_content = (
                    f"【测试模式】{site_name} / {stream} 在 {detected_at.isoformat()} "
                    f"检测到风险事件：{'；'.join(warning_parts)}。"
                )
                return last_agent_report_content
            return None

        base_url = os.getenv('TICKET_AGENT_API_URL') or 'http://127.0.0.1:8011/api/v1/generate_violation_report'
        if not base_url:
            return None
        payload: dict = {
            'ticket_no': ticket_no or '',
            'enable_llm': mode not in ('api_no_llm', 'no_llm', 'without_llm'),
            'violation': {
                'site': site_name,
                'stream_name': stream,
                'detection_time': detected_at.isoformat(),
                'warnings': warnings_dict,
                'detections_summary': {
                    'counts_by_class': counts_by_class,
                    'top_detections': top_detections,
                },
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
            ) as client:
                resp = await client.post(base_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"[{site_name}:{stream}] Agent report error: {e}")
            data = {}
        agent_report = data.get('agent_report') if isinstance(data, dict) else None
        if isinstance(agent_report, str) and agent_report.strip():
            last_agent_report_key = cache_key
            last_agent_report_time = now
            last_agent_report_content = agent_report
            return agent_report
        if warning_parts:
            last_agent_report_key = cache_key
            last_agent_report_time = now
            last_agent_report_content = (
                f"{site_name} / {stream} 在 {detected_at.isoformat()} "
                f"检测到风险事件：{'；'.join(warning_parts)}。"
            )
            return last_agent_report_content
        return None

    # Initialise components
    try:
        capture_interval = max(
            0.05,
            float(os.getenv('CAPTURE_INTERVAL_SECONDS') or '0.2'),
        )
    except ValueError:
        capture_interval = 0.2
    try:
        process_frame_width = max(
            0,
            int(os.getenv('PROCESS_FRAME_WIDTH') or '1280'),
        )
    except ValueError:
        process_frame_width = 1280
    streaming_capture = StreamCapture(
        stream_url=video_url,
        capture_interval=capture_interval,
    )
    live_stream_detector = LiveStreamDetector(
        api_url=os.getenv('DETECT_API_URL'),
        model_key=model_key,
        output_folder=site,
        detect_with_server=detect_with_server,
    )
    danger_detector = DangerDetector(detection_items)
    fcm_sender = FCMSender(api_url=os.getenv('FCM_API_URL') or '')
    violation_sender = ViolationSender(
        api_url=os.getenv('VIOLATION_RECORD_API_URL') or '',
    )
    frame_sender = BackendFrameSender(
        api_url=os.getenv('STREAMING_API_URL') or '',
        max_retries=3,
        timeout=30,  # Increase timeout
        reconnect_backoff=2.0,  # Moderate backoff time
    )

    last_notification_time: int = 0
    redis_key = (
        f"stream_frame:{Utils.encode(site)}|{Utils.encode(stream_name)}"
    )
    redis_manager = RedisManager()
    frame_cache: deque[tuple[int, bytes]] = deque(maxlen=60)
    processed_frame_no = 0
    last_window_skip_log = 0.0
    notification_tasks: set[asyncio.Task[None]] = set()
    latest_detection_payload: dict[str, str] = {
        'warnings_json': '{}',
        'cone_polygons_json': '[]',
        'pole_polygons_json': '[]',
        'detection_items_json': '[]',
    }
    try:
        preview_fps = max(1.0, float(os.getenv('PREVIEW_FPS') or '10'))
    except ValueError:
        preview_fps = 10.0
    try:
        preview_jpeg_quality = min(
            95,
            max(30, int(os.getenv('PREVIEW_JPEG_QUALITY') or '75')),
        )
    except ValueError:
        preview_jpeg_quality = 75

    async def _run_preview_stream() -> None:
        """Continuously publish fresh frames independently of inference."""
        preview_interval = 1.0 / preview_fps
        last_source_sequence = -1
        sent_frames = 0
        window_started = time.monotonic()

        while True:
            loop_started = time.monotonic()
            latest = streaming_capture.get_latest_frame()
            if latest is not None:
                preview_frame, _, source_sequence = latest
                if source_sequence != last_source_sequence:
                    if (
                        process_frame_width
                        and preview_frame.shape[1] > process_frame_width
                    ):
                        scale = process_frame_width / preview_frame.shape[1]
                        preview_frame = cv2.resize(
                            preview_frame,
                            (
                                process_frame_width,
                                int(preview_frame.shape[0] * scale),
                            ),
                            interpolation=cv2.INTER_AREA,
                        )

                    payload = latest_detection_payload
                    try:
                        result = await frame_sender.send_optimized_frame(
                            frame=preview_frame,
                            site=site,
                            stream_name=stream_name,
                            encoding_format='jpeg',
                            jpeg_quality=preview_jpeg_quality,
                            use_websocket=True,
                            warnings_json=payload['warnings_json'],
                            cone_polygons_json=payload[
                                'cone_polygons_json'
                            ],
                            pole_polygons_json=payload[
                                'pole_polygons_json'
                            ],
                            detection_items_json=payload[
                                'detection_items_json'
                            ],
                        )
                        if result.get('status') != 'ok':
                            logger.error(
                                f"[{site}:{stream_name}] Preview send failed: "
                                f"{result}",
                            )
                        else:
                            sent_frames += 1
                            last_source_sequence = source_sequence
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error(
                            f"[{site}:{stream_name}] Preview send error: "
                            f"{exc}",
                        )

            now = time.monotonic()
            if now - window_started >= 10.0:
                actual_fps = sent_frames / (now - window_started)
                logger.info(
                    f"[{site}:{stream_name}] PREVIEW "
                    f"target_fps={preview_fps:.1f} "
                    f"actual_fps={actual_fps:.1f} "
                    f"latest_source_frame={last_source_sequence}",
                )
                sent_frames = 0
                window_started = now

            remaining = preview_interval - (time.monotonic() - loop_started)
            await asyncio.sleep(max(0.001, remaining))

    async def _deliver_alert_in_background(
        detected_at_dt: datetime,
        alert_frame_bytes: bytes,
        alert_warnings: dict,
        alert_track_data: list,
        alert_cone_polys: list,
        alert_pole_polys: list,
    ) -> None:
        """Send slow auxiliary requests without blocking live detection."""
        agent_report_content = await _generate_agent_report(
            active_ticket_no,
            site,
            stream_name,
            detected_at_dt,
            alert_warnings,
            alert_track_data,
        )

        violation_id_str: str | None = None
        try:
            violation_id_str = await violation_sender.send_violation(
                site=site,
                stream_name=stream_name,
                warnings_json=json.dumps(alert_warnings),
                detection_time=detected_at_dt,
                image_bytes=alert_frame_bytes,
                detections_json=json.dumps(alert_track_data),
                cone_polygon_json=json.dumps(alert_cone_polys),
                pole_polygon_json=json.dumps(alert_pole_polys),
                agent_report=agent_report_content,
            )
        except Exception as exc:
            logger.error(
                f"[{site}:{stream_name}] Violation upload failed in "
                f"background; detection continues: {exc}",
            )

        try:
            violation_id = (
                int(violation_id_str)
                if violation_id_str is not None
                else None
            )
        except (TypeError, ValueError):
            violation_id = None

        if os.getenv('FCM_ENABLED', '1').strip().lower() in {'0', 'false', 'off', 'no'}:
            return

        try:
            await fcm_sender.send_fcm_message_to_site(
                site=site,
                stream_name=stream_name,
                message=alert_warnings,
                image_path=None,
                violation_id=violation_id,
            )
        except Exception as exc:
            logger.error(
                f"[{site}:{stream_name}] Notification failed in background; "
                f"detection continues: {exc}",
            )

    preview_task: asyncio.Task[None] | None = None
    if store_in_redis:
        preview_task = asyncio.create_task(
            _run_preview_stream(),
            name=f"preview-{site}-{stream_name}",
        )

    try:
        # Process each frame
        async for frame, ts in streaming_capture.execute_capture():
            processed_frame_no += 1
            start = time.time()
            perf_start = time.perf_counter()
            frame_started_at = datetime.now()
            capture_time = datetime.fromtimestamp(float(ts))
            start_delay = max(0.0, start - float(ts))
            source_frame_no = streaming_capture.last_delivered_sequence
            logger.info(
                f"[{site}:{stream_name}] "
                f"[process_frame={processed_frame_no}] "
                f"[source_frame={source_frame_no}] START "
                f"capture_time={capture_time.isoformat(timespec='milliseconds')} "
                f"start_time={frame_started_at.isoformat(timespec='milliseconds')} "
                f"start_delay={start_delay:.3f}s "
                f"source_size={frame.shape[1]}x{frame.shape[0]}",
            )
            detection_time = datetime.fromtimestamp(int(ts))
            outside_ticket_window = bool(
                active_ticket_no
                and (
                    (active_from and detection_time < active_from)
                    or (active_to and detection_time > active_to)
                )
            )
            if outside_ticket_window:
                latest_detection_payload = {
                    'warnings_json': '{}',
                    'cone_polygons_json': '[]',
                    'pole_polygons_json': '[]',
                    'detection_items_json': '[]',
                }
                now_monotonic = time.monotonic()
                if now_monotonic - last_window_skip_log >= 10.0:
                    logger.info(
                        f"[{site}:{stream_name}] "
                        f"AI SKIP outside ticket window "
                        f"ticket={active_ticket_no} "
                        f"capture_time={detection_time.isoformat()}",
                    )
                    last_window_skip_log = now_monotonic
                continue
            if process_frame_width and frame.shape[1] > process_frame_width:
                scale = process_frame_width / frame.shape[1]
                frame = cv2.resize(
                    frame,
                    (process_frame_width, int(frame.shape[0] * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            resize_finished = time.perf_counter()
            is_working = (
                work_start_hour <= detection_time.hour < work_end_hour
            )

            datas, track_data = (
                await live_stream_detector.generate_detections(
                    frame,
                    float(ts),
                )
            )
            inference_finished = time.perf_counter()
            warnings_raw, cone_polys, pole_polys = (
                danger_detector.detect_danger(
                    track_data,
                )
            )
            warnings_filtered = Utils.filter_warnings_by_working_hour(
                warnings_raw, is_working,
            )
            danger_finished = time.perf_counter()

            # Detection only updates metadata.  The independent preview task
            # combines this latest result with fresh camera frames.
            latest_detection_payload = {
                'warnings_json': json.dumps(warnings_raw),
                'cone_polygons_json': json.dumps(cone_polys),
                'pole_polygons_json': json.dumps(pole_polys),
                'detection_items_json': json.dumps(track_data),
            }

            # Use optimized frame encoding (JPEG for better compression)
            frame_bytes = Utils.encode_frame(frame, 'jpeg', 85)
            frame_cache.append((int(ts), frame_bytes))
            encode_finished = time.perf_counter()

            # Frame delivery is handled by _run_preview_stream().
            frame_send_finished = time.perf_counter()

            # Send violation record + FCM push if needed
            if warnings_filtered and Utils.should_notify(
                int(ts),
                last_notification_time,
            ):
                chosen_frame_bytes = frame_bytes
                chosen_ts = int(ts)
                if isinstance(track_data, list) and frame_cache:
                    best: tuple[float, int] | None = None
                    for row in track_data:
                        if not isinstance(row, list) or len(row) < 9:
                            continue
                        try:
                            cls_id = int(row[5])
                            conf = float(row[4])
                            ev_ts = float(row[8])
                        except Exception:
                            continue
                        if cls_id not in (2, 4):
                            continue
                        if not math.isfinite(ev_ts):
                            continue
                        ev_int = int(ev_ts)
                        if ev_int <= 0:
                            continue
                        if best is None or conf > best[0] or (
                            conf == best[0] and ev_int > best[1]
                        ):
                            best = (conf, ev_int)
                    if best is not None:
                        target_ts = best[1]
                        cached = next(
                            (b for t, b in frame_cache if t == target_ts),
                            None,
                        )
                        if cached is None:
                            nearest: tuple[int, bytes] | None = None
                            for t, b in frame_cache:
                                if abs(t - target_ts) <= 2 and (
                                    nearest is None
                                    or abs(t - target_ts) < abs(nearest[0] - target_ts)
                                ):
                                    nearest = (t, b)
                            if nearest is not None:
                                chosen_ts, chosen_frame_bytes = nearest
                        else:
                            chosen_ts, chosen_frame_bytes = target_ts, cached
                detected_at_dt = datetime.fromtimestamp(chosen_ts)
                # Apply the normal notification cooldown even when an
                # auxiliary service is down, otherwise every detected frame
                # would immediately retry and overload that service.
                last_notification_time = int(ts)
                task = asyncio.create_task(
                    _deliver_alert_in_background(
                        detected_at_dt,
                        chosen_frame_bytes,
                        warnings_filtered,
                        track_data,
                        cone_polys,
                        pole_polys,
                    ),
                    name=f"alert-{site}-{stream_name}-{chosen_ts}",
                )
                notification_tasks.add(task)
                task.add_done_callback(notification_tasks.discard)
            alert_schedule_finished = time.perf_counter()

            # Record processing time.  The RTSP reader keeps draining frames
            # in the background, so the next iteration receives the newest
            # frame instead of waiting through an old FFmpeg buffer.
            proc_time = time.perf_counter() - perf_start
            resize_ms = (resize_finished - perf_start) * 1000
            inference_ms = (inference_finished - resize_finished) * 1000
            danger_ms = (danger_finished - inference_finished) * 1000
            encode_ms = (encode_finished - danger_finished) * 1000
            frame_send_ms = (frame_send_finished - encode_finished) * 1000
            alert_schedule_ms = (
                alert_schedule_finished - frame_send_finished
            ) * 1000
            frame_finished_at = datetime.now()
            finish_delay = max(0.0, time.time() - float(ts))
            logger.info(
                f"[{site}:{stream_name}] "
                f"[process_frame={processed_frame_no}] "
                f"[source_frame={source_frame_no}] END "
                f"capture_time={capture_time.isoformat(timespec='milliseconds')} "
                f"end_time={frame_finished_at.isoformat(timespec='milliseconds')} "
                f"duration={proc_time:.3f}s "
                f"finish_delay={finish_delay:.3f}s "
                f"warnings={len(warnings_raw)} "
                f"stages_ms="
                f"resize:{resize_ms:.1f},"
                f"inference:{inference_ms:.1f},"
                f"danger:{danger_ms:.1f},"
                f"encode:{encode_ms:.1f},"
                f"frame_send:{frame_send_ms:.1f},"
                f"alert_schedule:{alert_schedule_ms:.1f}",
            )

        await streaming_capture.release_resources()
        gc.collect()

    except Exception:
        logger.exception(
            f"[{site}:{stream_name}] Stream process failed unexpectedly",
        )
        raise
    finally:
        # Ensure cleanup
        logger.info(f"[{site}:{stream_name}] Stopping stream process")
        if preview_task is not None:
            preview_task.cancel()
            await asyncio.gather(preview_task, return_exceptions=True)
        for task in list(notification_tasks):
            task.cancel()
        if notification_tasks:
            await asyncio.gather(*notification_tasks, return_exceptions=True)
        await live_stream_detector.close()
        await streaming_capture.release_resources()
        await frame_sender.close()  # Ensure WebSocket connection is closed
        await violation_sender.close()
        await fcm_sender.close()
        if store_in_redis:
            try:
                await redis_manager.delete(redis_key)
            except Exception as e:
                logger.warning(
                    f"[WARN] Failed to delete redis key {redis_key}: {e}",
                )


def process_single_stream(cfg: StreamConfig) -> None:
    """
    Logic executed by each child process to capture frames, detect hazards,
    and send results to backend or Redis.

    Args:
        cfg (StreamConfig): The configuration dict for this stream.
    """
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_run_single_stream(cfg))


async def main() -> None:
    """
    Parse command-line arguments and run the MainApp.
    """
    parser = argparse.ArgumentParser(
        description='Hazard detection from DB configs or JSON file',
    )
    parser.add_argument(
        '--poll', type=int, default=10,
        help='DB polling interval in seconds',
    )
    parser.add_argument(
        '--config', type=str,
        help='Path to JSON config file for stream configs',
    )
    args = parser.parse_args()

    if args.config:
        # Load configs from JSON file
        with open(args.config, encoding='utf-8') as f:
            configs = json.load(f)
        # Start a process for each config
        procs = []
        for cfg in configs:
            proc = Process(target=process_single_stream, args=(cfg,))
            proc.start()
            procs.append(proc)
        try:
            while any(p.is_alive() for p in procs):
                for p in procs:
                    p.join(timeout=1)
        except KeyboardInterrupt:
            print('\n[INFO] KeyboardInterrupt, shutting down...')
        finally:
            for p in procs:
                if p.is_alive():
                    p.terminate()
                    p.join()
    else:
        app = MainApp(poll_interval=args.poll)
        try:
            await app.run()
        except KeyboardInterrupt:
            print('\n[INFO] KeyboardInterrupt, shutting down...')
        finally:
            # Ensure all child processes are stopped and DB closed
            for info in app.running_processes.values():
                app.stop_process(info['process'])
            if app.db_pool:
                app.db_pool.close()
                await app.db_pool.wait_closed()


if __name__ == '__main__':
    multiprocessing.set_start_method('spawn', force=True)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
