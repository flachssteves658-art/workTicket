from __future__ import annotations

import argparse
import asyncio
import base64
import gc
import json
import logging
import os
import time
from pathlib import Path
from typing import cast
from typing import TypedDict

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from ultralytics import YOLO

from src.net.net_client import NetClient
from src.utils import TokenManager
from src.llm_utils import call_ollama, call_openai_compatible

load_dotenv()


class SharedToken(TypedDict, total=False):
    access_token: str
    refresh_token: str
    is_refreshing: bool


class BailianVLCorrection(TypedDict, total=False):
    label: int
    confidence: float
    ts: float
    evidence_ts: float


class BailianVLRefiner:
    def __init__(
        self,
        *,
        enabled: bool,
        provider: str = 'aliyun',
        api_key: str,
        base_url: str,
        model: str,
        low_conf_threshold: float,
        cache_ttl_sec: float,
        cooldown_sec: float,
        max_concurrency: int,
        timeout_sec: float,
        min_crop_size: int,
        pad_ratio: float,
        allowed_class_ids: set[int] | None,
        class_names: dict[int, str] | None,
    ) -> None:
        self.enabled = enabled
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.low_conf_threshold = low_conf_threshold
        self.cache_ttl_sec = cache_ttl_sec
        self.cooldown_sec = cooldown_sec
        self.timeout_sec = timeout_sec
        self.min_crop_size = min_crop_size
        self.pad_ratio = pad_ratio
        self.allowed_class_ids = allowed_class_ids
        self.class_names = class_names or {
            0: 'hardhat',
            # 1: 'mask',
            2: 'no_hardhat',
            # 3: 'no_mask',
            4: 'no_safety_vest',
            5: 'person',
            6: 'safety_cone',
            7: 'safety_vest',
            8: 'machinery',
            9: 'vehicle',
        }

        self._log = logging.getLogger(__name__)
        self._cache: dict[int, BailianVLCorrection] = {}
        self._pending: dict[int, float] = {}
        self._last_bbox: dict[int, list[int]] = {}
        self._sem = asyncio.Semaphore(max(1, max_concurrency))

    def apply_to_tracked(self, tracked: list[list[float]]) -> list[list[float]]:
        if not self.enabled:
            return tracked

        now = time.time()
        self._cleanup(now)

        out: list[list[float]] = []
        present_ids: set[int] = set()
        for row in tracked:
            if len(row) < 7:
                out.append(row)
                continue
            tid = int(row[6])
            if tid != -1:
                present_ids.add(tid)
                corr = self._cache.get(tid)
                if corr is not None:
                    new_row = list(row)
                    new_row[4] = max(float(new_row[4]), float(corr['confidence']))
                    new_row[5] = int(corr['label'])
                    ev_ts = corr.get('evidence_ts')
                    if ev_ts is not None:
                        if len(new_row) >= 9:
                            new_row[8] = float(ev_ts)
                        else:
                            new_row.append(float(ev_ts))
                    out.append(new_row)
                    continue
            out.append(row)

        if self._cache and self._last_bbox:
            ttl = self.cache_ttl_sec
            for tid, corr in list(self._cache.items()):
                if tid in present_ids:
                    continue
                bbox = self._last_bbox.get(tid)
                if bbox is None:
                    continue
                if ttl > 0 and now - float(corr['ts']) > ttl:
                    continue
                if len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = bbox
                label = int(corr['label'])
                conf = float(corr['confidence'])
                ev_ts = corr.get('evidence_ts')
                out.append(
                    [
                        float(x1),
                        float(y1),
                        float(x2),
                        float(y2),
                        conf,
                        label,
                        int(tid),
                        0,
                        float(ev_ts) if ev_ts is not None else float('nan'),
                    ],
                )
        return out

    def schedule_for_frame(
        self,
        frame_bgr: np.ndarray,
        tracked: list[list[float]],
        frame_ts: float | None = None,
    ) -> None:
        if not self.enabled or not tracked:
            return

        now = time.time()
        self._cleanup(now)

        for row in tracked:
            if len(row) < 7:
                continue
            conf = float(row[4])
            cls_id = int(row[5])
            tid = int(row[6])
            if tid == -1:
                continue
            if self.allowed_class_ids is not None and cls_id not in self.allowed_class_ids:
                continue
            if conf >= self.low_conf_threshold:
                continue
            if tid in self._cache:
                continue
            last = self._pending.get(tid, 0.0)
            if now - last < self.cooldown_sec:
                continue
            self._pending[tid] = now
            bbox = [int(row[0]), int(row[1]), int(row[2]), int(row[3])]
            self._last_bbox[tid] = bbox
            evidence_ts = time.time() if frame_ts is None else float(frame_ts)
            asyncio.create_task(
                self._refine_one(frame_bgr, bbox, cls_id, tid, evidence_ts),
            )

    async def _refine_one(
        self,
        frame_bgr: np.ndarray,
        bbox: list[int],
        yolo_cls_id: int,
        track_id: int,
        evidence_ts: float,
    ) -> None:
        try:
            crop_b64 = self._crop_to_base64(frame_bgr, bbox)
            if crop_b64 is None:
                return
            prompt = self._make_prompt(yolo_cls_id)
            content = await self._post_chat_completions(crop_b64, prompt)
            parsed = self._parse_llm_json(content)
            if parsed is None:
                return
            new_id, new_conf = parsed
            now = time.time()
            self._cache[track_id] = {
                'label': new_id,
                'confidence': new_conf,
                'ts': now,
                'evidence_ts': float(evidence_ts),
            }
        except Exception as e:
            self._log.error('LLM refine task failed: %s', e)

    def _crop_to_base64(
        self,
        frame_bgr: np.ndarray,
        bbox: list[int],
    ) -> str | None:
        h, w = frame_bgr.shape[:2]
        x1, y1, x2, y2 = bbox
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        pad_x = int(bw * self.pad_ratio)
        pad_y = int(bh * self.pad_ratio)
        x1p = max(0, x1 - pad_x)
        y1p = max(0, y1 - pad_y)
        x2p = min(w, x2 + pad_x)
        y2p = min(h, y2 + pad_y)
        if (x2p - x1p) < self.min_crop_size or (y2p - y1p) < self.min_crop_size:
            return None
        crop = frame_bgr[y1p:y2p, x1p:x2p]
        ok, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        return base64.b64encode(buf).decode('ascii')

    def _make_prompt(self, yolo_cls_id: int) -> str:
        yolo_name = self.class_names.get(yolo_cls_id, str(yolo_cls_id))
        classes = {int(k): str(v) for k, v in self.class_names.items()}
        return (
            '你是施工现场安全检测的复核助手。'
            '我会给你一张图片裁剪（来自检测框），以及候选类别表。'
            '请判断裁剪图里最符合的类别，并只输出一个 JSON 对象，格式严格为：'
            '{"id": <int>, "confidence": <float>}。'
            '不要输出任何额外文字。'
            f'当前 YOLO 预测类别是：{yolo_name}（id={yolo_cls_id}）。'
            f'候选类别表（id->name）为：{json.dumps(classes, ensure_ascii=False)}。'
        )

    async def _post_chat_completions(self, image_b64: str, prompt: str) -> str:
        if self.provider == 'ollama':
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64]
                }
            ]
            return await call_ollama(
                self.model,
                messages,
                temperature=0.1,
                base_url=self.base_url
            )
        else:
            messages = [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {
                            'type': 'image_url',
                            'image_url': {'url': f'data:image/jpeg;base64,{image_b64}'},
                        },
                    ],
                },
            ]
            return await call_openai_compatible(
                self.base_url,
                self.api_key,
                self.model,
                messages,
                temperature=0.1
            )

    def _parse_llm_json(self, content: str) -> tuple[int, float] | None:
        if not content:
            return None
        s = content.strip()
        if s.startswith('```'):
            first_nl = s.find('\n')
            if first_nl != -1:
                s = s[first_nl + 1:]
            if s.endswith('```'):
                s = s[:-3]
            s = s.strip()
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            l = s.find('{')
            r = s.rfind('}')
            if l == -1 or r == -1 or r <= l:
                return None
            try:
                obj = json.loads(s[l:r + 1])
            except json.JSONDecodeError:
                return None
        if not isinstance(obj, dict):
            return None
        try:
            cid = int(obj.get('id'))
            conf = float(obj.get('confidence', 0.8))
        except Exception:
            return None
        conf = max(0.0, min(1.0, conf))
        return cid, conf

    def _cleanup(self, now: float) -> None:
        ttl = self.cache_ttl_sec
        if ttl > 0:
            expired = [
                tid for tid, c in self._cache.items()
                if now - float(c['ts']) > ttl
            ]
            for tid in expired:
                self._cache.pop(tid, None)
                self._last_bbox.pop(tid, None)
        pending_expired = [
            tid for tid, ts in self._pending.items()
            if now - ts > max(self.cooldown_sec * 2.0, 10.0)
        ]
        for tid in pending_expired:
            self._pending.pop(tid, None)


class LiveStreamDetector:
    """
    A class to perform live stream detection and tracking
    using YOLO with SAHI.
    """

    def __init__(
        self,
        api_url: str | None = None,
        model_key: str = 'yolo11n',
        output_folder: str | None = None,
        detect_with_server: bool = False,
        shared_token: SharedToken | None = None,
        use_ultralytics: bool = True,
        movement_thr: float = 40.0,
        fps: int = 1,
        max_id_keep: int = 10,
        ws_frame_size: tuple[int, int] | None = None,
        use_jpeg_ws: bool = True,
        remote_tracker: str = 'centroid',
        remote_cost_threshold: float = 0.7,
    ) -> None:
        """Initialise the LiveStreamDetector with specified configuration.

        Args:
            api_url: Base URL for the detection API server
                (env DETECT_API_URL if None).
            model_key: YOLO model identifier.
            output_folder: Optional directory for saving outputs.
            detect_with_server: Use remote WebSocket service if True.
            shared_token: Shared token dict for auth.
            use_ultralytics: Use Ultralytics engine (else SAHI slicing).
            movement_thr: Pixel movement threshold (centroid distance).
            fps: Target FPS (reserved for future time-based logic).
            max_id_keep: Frames to retain inactive track IDs.
            ws_frame_size: Optional (w,h) resize before WS send.
            use_jpeg_ws: JPEG (True) or PNG (False) for WS transmission.
            remote_tracker: 'centroid' or 'hungarian' for remote tracking.
            remote_cost_threshold: Cost cutoff (0-1) for Hungarian match.
        """
        # Resolve API URL
        if api_url is None:
            api_url = os.getenv(
                'DETECT_API_URL', 'https://changdar-server.mooo.com/api',
            )
        self.api_url = api_url.rstrip('/')
        self.model_key = model_key
        self.output_folder = output_folder
        self.detect_with_server = detect_with_server
        self.use_ultralytics = use_ultralytics

        # Tokens
        self.shared_token: SharedToken = shared_token or SharedToken(
            access_token='', refresh_token='', is_refreshing=False,
        )
        # Cast to the TokenManager expected type (dict[str, str | bool])
        self.token_manager = TokenManager(
            shared_token=cast('dict[str, str | bool]', self.shared_token),
        )

        # Models (local inference path)
        if not detect_with_server:
            # Uncomment for local inference using .engine files
            # (quantised from .pt)
            # if self.use_ultralytics:
            #     self.ultralytics_model = YOLO(
            #         f"models/int8_engine/best_{self.model_key}.engine",
            #     )

            if self.use_ultralytics:
                self.ultralytics_model = YOLO(
                    f"models/pt/best_{self.model_key}.pt",
                )
            else:
                self.model = AutoDetectionModel.from_pretrained(
                    'yolo11',
                    model_path=str(
                        Path('models/pt') /
                        f"best_{self.model_key}.pt",
                    ),
                    device='cuda:0',
                )

        # Networking via shared NetClient
        self.net = NetClient(
            base_url=self.api_url,
            token_manager=self.token_manager,
            ws_heartbeat=30,
            ws_send_timeout=10.0,
            ws_recv_timeout=15.0,
            ws_connect_attempts=3,
        )
        self._logger = logging.getLogger(__name__)

        # Tracking state stores
        self.remote_tracks: dict[int, dict] = {}
        self.next_remote_id = 0
        self.prev_centers: dict[int, tuple[float, float]] = {}
        self.prev_centers_last_seen: dict[int, int] = {}
        self.movement_thr = movement_thr
        self.movement_thr_sq = movement_thr * movement_thr
        self.frame_count = 0
        self.max_id_keep = max_id_keep

        # WS transmission config
        self.ws_frame_size = ws_frame_size
        self.use_jpeg_ws = use_jpeg_ws

        # Remote tracking configuration
        self.remote_tracker = remote_tracker
        self.remote_cost_threshold = remote_cost_threshold

        enable_refine = os.getenv('LLM_REFINE_ENABLED', '').lower() in (
            '1', 'true', 'yes', 'on',
        )
        llm_provider = os.getenv('LLM_PROVIDER', 'aliyun').lower()
        aliyun_key = os.getenv('ALIYUN_API_KEY', '')
        aliyun_base = os.getenv(
            'ALIYUN_BASE_URL',
            'https://dashscope.aliyuncs.com/compatible-mode/v1',
        )
        aliyun_model = os.getenv(
            'ALIYUN_MODEL_NAME',
            'qwen-vl-max-2025-08-13',
        )
        low_thr = float(os.getenv('LLM_REFINE_LOW_CONF_THRESHOLD', '0.35'))
        ttl_sec = float(os.getenv('LLM_REFINE_CACHE_TTL_SEC', '8'))
        cooldown_sec = float(os.getenv('LLM_REFINE_COOLDOWN_SEC', '3'))
        max_conc = int(os.getenv('LLM_REFINE_MAX_CONCURRENCY', '2'))
        timeout_sec = float(os.getenv('LLM_REFINE_TIMEOUT_SEC', '10'))
        min_crop = int(os.getenv('LLM_REFINE_MIN_CROP_SIZE', '48'))
        pad_ratio = float(os.getenv('LLM_REFINE_PAD_RATIO', '0.1'))
        allowed_raw = os.getenv('LLM_REFINE_CLASSES', '').strip()
        allowed: set[int] | None = None
        if allowed_raw:
            try:
                allowed = {int(x.strip()) for x in allowed_raw.split(',') if x.strip()}
            except Exception:
                allowed = None

        class_names = None
        try:
            if hasattr(self, 'ultralytics_model') and hasattr(self.ultralytics_model, 'names'):
                names_any = self.ultralytics_model.names
                if isinstance(names_any, dict):
                    class_names = {int(k): str(v) for k, v in names_any.items()}
        except Exception:
            class_names = None

        self._vl_refiner: BailianVLRefiner | None = None
        if enable_refine:
            self._vl_refiner = BailianVLRefiner(
                enabled=True,
                provider=llm_provider,
                api_key=aliyun_key,
                base_url=aliyun_base,
                model=aliyun_model,
                low_conf_threshold=low_thr,
                cache_ttl_sec=ttl_sec,
                cooldown_sec=cooldown_sec,
                max_concurrency=max_conc,
                timeout_sec=timeout_sec,
                min_crop_size=min_crop,
                pad_ratio=pad_ratio,
                allowed_class_ids=allowed,
                class_names=class_names,
            )

    # NetClient handles WS connections; legacy WS connect helpers removed

    async def _detect_cloud_ws(self, frame: np.ndarray) -> list[list[float]]:
        """
        Perform object detection using WebSocket connection to remote server.

        Args:
            frame: Input image frame as numpy array for detection.

        Returns:
            List of detection results, where each detection is represented as
            [x1, y1, x2, y2, confidence, class_id].

        Note:
            Returns empty list if all retry attempts fail to prevent system
            crashes.
        """
        backoff: float = 1.0
        max_backoff: float = 15.0
        retry_count: int = 0
        max_retries: int = 3

        while retry_count < max_retries:
            try:
                result = await self._attempt_ws_detect(frame)
                if result is not None:
                    return result
            except Exception as e:
                if await self._handle_exception(e):
                    await self.close()
                self._logger.error(
                    'WS error: %s, retrying (%d/%d) after %.1fs.',
                    e,
                    retry_count + 1,
                    max_retries,
                    backoff,
                )
            await self.close()
            retry_count += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, max_backoff)

        # If all retries fail,
        # return empty results instead of raising exception
        self._logger.error(
            f"WebSocket connection failed after {max_retries} retries, "
            'returning empty results',
        )
        return []

    async def _attempt_ws_detect(
        self, frame: np.ndarray,
    ) -> list[list[float]] | None:
        """Single attempt to send frame and parse server response.

        Returns parsed detections or None to indicate retry.
        """
        await self._maybe_refresh_token_and_reset_ws()

        frame_to_send = self._prepare_frame(frame)
        img_buf = self._encode_frame(frame_to_send)
        if img_buf is None:
            return []

        ws_data = await self.net.ws_send_and_receive(
            '/ws/detect',
            img_buf,
            headers={'x-model-key': self.model_key},
        )
        if ws_data is None:
            return None
        return await self._handle_response_data(ws_data)

    async def _maybe_refresh_token_and_reset_ws(self) -> None:
        """Refresh token proactively if expiring and reset WS if needed."""
        if not self.token_manager.is_token_expired():
            return
        self._logger.info(
            'Token expiring soon, preemptively refreshing...',
        )
        try:
            await self.token_manager.refresh_token()
            await self.close()
        except Exception as e:
            self._logger.warning(
                'Preemptive token refresh failed: %s', e,
            )

    def _prepare_frame(self, frame: np.ndarray) -> np.ndarray:
        """Prepare frame for transmission by resizing if needed."""
        if self.ws_frame_size:
            return cv2.resize(frame, self.ws_frame_size)
        return frame

    def _encode_frame(self, frame: np.ndarray) -> bytes | None:
        """Encode frame to bytes for WebSocket transmission."""
        if self.use_jpeg_ws:
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 80]
            success, img_buf = cv2.imencode('.jpg', frame, encode_params)
        else:
            encode_params = [cv2.IMWRITE_PNG_COMPRESSION, 7]
            success, img_buf = cv2.imencode('.png', frame, encode_params)

        if not success:
            self._logger.error('Failed to encode frame.')
            return None

        return img_buf.tobytes()

    async def _process_message(self, msg) -> list[list[float]] | None:
        """Deprecated; NetClient returns parsed JSON dict or list directly."""
        try:
            data = json.loads(msg)
        except Exception:
            return []
        return await self._handle_response_data(data)

    async def _handle_response_data(self, data) -> list[list[float]] | None:
        """Handle different types of response data."""
        try:
            # Treat as mapping-like (dict)
            _ = data.get  # may raise AttributeError if not dict-like
        except AttributeError:
            # Not a mapping; if it's a JSON array, return as-is
            if type(data) is list:
                return data
            self._logger.warning(f"Unexpected data format: {type(data)}")
            return []

        # Handle ping messages
        if data.get('type') == 'ping':
            return None

        # Handle error messages
        if 'error' in data:
            return await self._handle_server_error(data['error'])

        # Extract detections if present in known keys
        dets = data.get('detections')
        if type(dets) is list:
            return dets
        dets2 = data.get('data')
        if type(dets2) is list:
            return dets2

        # No special handling for initial 'ready' in simplified protocol
        self._logger.debug('No detection payload in message; ignoring.')
        return []

    async def _handle_server_error(self, error_msg: str) -> list[list[float]]:
        """Handle server error messages."""
        self._logger.error(f"Server error: {error_msg}")

        if any(
            keyword in error_msg.lower() for keyword in [
                'expired', 'unauthorized', 'invalid token',
            ]
        ):
            self._logger.warning(
                'Token-related server error, attempting refresh...',
            )
            try:
                await self.token_manager.refresh_token()
                await self.close()
            except Exception as refresh_error:
                self._logger.error(f"Token refresh failed: {refresh_error}")

        return []

    async def _handle_exception(self, e: Exception) -> bool:
        """Handle exceptions and return True if token refresh was attempted."""
        error_message = str(e).lower()
        if any(
            keyword in error_message for keyword in [
                'expired', '401', 'unauthorized', 'invalid token',
            ]
        ):
            self._logger.warning(
                (
                    f"Token-related error in detection: {e}. "
                    'Attempting refresh...'
                ),
            )
            try:
                await self.token_manager.refresh_token()
                return True
            except Exception as refresh_error:
                self._logger.error(
                    f"Token refresh failed during detection: {refresh_error}",
                )
        return False

    async def _detect_local(self, frame: np.ndarray) -> list[list[float]]:
        """Perform object detection using local YOLO models.

        This method runs inference locally using either Ultralytics YOLO or
        SAHI AutoDetectionModel, depending on the configuration.

        Args:
            frame: Input image frame as numpy array for detection.

        Returns:
            List of detection results, where each detection is represented as
            [x1, y1, x2, y2, confidence, class_id].
        """
        if self.use_ultralytics:
            # Use Ultralytics YOLO for direct inference
            result = self.ultralytics_model(frame)
            boxes = result[0].boxes
            return [
                [
                    *map(float, boxes.xyxy[i].tolist()),
                    float(boxes.conf[i].item()),
                    int(boxes.cls[i].item()),
                ]
                for i in range(len(boxes))
            ]
        else:
            # Use SAHI for sliced inference on large images
            result = get_sliced_prediction(
                frame, self.model,
                slice_height=376, slice_width=376,
                overlap_height_ratio=0.3, overlap_width_ratio=0.3,
            )
            return [
                [
                    *map(int, obj.bbox.to_voc_bbox()),
                    float(obj.score.value),
                    int(obj.category.id),
                ]
                for obj in result.object_prediction_list
            ]

    async def generate_detections(
        self,
        frame: np.ndarray,
        frame_ts: float | None = None,
    ) -> tuple[list[list[float]], list[list[float]]]:
        """Generate object detections with tracking information.

        This is the main detection method that coordinates between local and
        remote inference, applies object tracking, and manages frame counting.

        Args:
            frame: Input image frame as numpy array for detection.

        Returns:
            Tuple containing:
                - List of raw detection results
                  [x1, y1, x2, y2, confidence, class_id]
                - List of tracked detection results
                  [x1, y1, x2, y2, confidence, class_id, track_id, is_moving]
        """
        self.frame_count += 1
        if self.detect_with_server:
            datas = await self._detect_cloud_ws(frame)
            datas = [d for d in datas if int(d[5]) not in (1, 3)]
            tracked = self._track_remote(datas)
        else:
            results = self.ultralytics_model.track(
                frame, persist=True, verbose=False,
            )
            boxes = results[0].boxes

            if len(boxes) == 0:
                self._cleanup_prev_centers()
                datas: list[list[float]] = []
                tracked: list[list[float]] = []
                if self._vl_refiner is not None and self._vl_refiner.enabled:
                    tracked = self._vl_refiner.apply_to_tracked(tracked)
                    if tracked:
                        for row in tracked:
                            if len(row) >= 6:
                                datas.append(
                                    [
                                        float(row[0]),
                                        float(row[1]),
                                        float(row[2]),
                                        float(row[3]),
                                        float(row[4]),
                                        float(row[5]),
                                    ],
                                )
                return datas, tracked

            ids = results[0].boxes.id if results[0].boxes.id is not None else [
                -1,
            ] * len(boxes)

            # Batch calculate all bounding box data
            xyxy_batch = boxes.xyxy.tolist()
            conf_batch = boxes.conf.tolist()
            cls_batch = boxes.cls.tolist()

            datas = []
            tracked = []

            for i in range(len(boxes)):
                xyxy = xyxy_batch[i]
                conf = float(conf_batch[i])
                cls = int(cls_batch[i])
                if cls in (1, 3):
                    continue

                tid = (
                    int(ids[i]) if ids is not None and ids[i] is not None
                    else -1
                )

                # Calculate centre point and movement status
                cx, cy = (xyxy[0] + xyxy[2]) * 0.5, (xyxy[1] + xyxy[3]) * 0.5
                is_moving = 0

                if tid != -1:
                    prev_c = self.prev_centers.get(tid)
                    if prev_c:
                        # Use pre-computed square distance comparison
                        distance_sq = (
                            (cx - prev_c[0]) ** 2 + (cy - prev_c[1]) ** 2
                        )
                        is_moving = (
                            1 if distance_sq > self.movement_thr_sq else 0
                        )

                    self.prev_centers[tid] = (cx, cy)
                    self.prev_centers_last_seen[tid] = self.frame_count

                datas.append(xyxy + [conf, cls])
                tracked.append(xyxy + [conf, cls, tid, is_moving])
            self._cleanup_prev_centers()
            if self._vl_refiner is not None and self._vl_refiner.enabled:
                tracked = self._vl_refiner.apply_to_tracked(tracked)
                for j in range(min(len(datas), len(tracked))):
                    datas[j][4] = float(tracked[j][4])
                    datas[j][5] = int(tracked[j][5])
                self._vl_refiner.schedule_for_frame(frame, tracked, frame_ts)
            return datas, tracked
        self._cleanup_prev_centers()
        if self._vl_refiner is not None and self._vl_refiner.enabled:
            tracked = self._vl_refiner.apply_to_tracked(tracked)
            for j in range(min(len(datas), len(tracked))):
                datas[j][4] = float(tracked[j][4])
                datas[j][5] = int(tracked[j][5])
            self._vl_refiner.schedule_for_frame(frame, tracked, frame_ts)
        return datas, tracked

    def _cleanup_prev_centers(self) -> None:
        """Clean up tracking data for inactive object IDs.

        This method removes tracking information for objects that haven't been
        seen for more than max_id_keep frames to prevent memory leaks and
        maintain tracking performance.
        """
        # Clean up IDs that haven't appeared for more than max_id_keep frames
        if self.frame_count % 10 == 0:
            current_frame = self.frame_count
            expired_ids = [
                tid for tid, last_seen in self.prev_centers_last_seen.items()
                if current_frame - last_seen > self.max_id_keep
            ]
            for tid in expired_ids:
                self.prev_centers.pop(tid, None)
                self.prev_centers_last_seen.pop(tid, None)

    def _track_remote(self, dets: list[list[float]]) -> list[list[float]]:
        """Dispatch to the configured remote tracker implementation."""
        if self.remote_tracker == 'hungarian':
            return self._track_remote_hungarian(dets)
        # Default / fallback
        return self._track_remote_centroid(dets)

    # Small utilities for tracking readability
    # Centralised numeric constants for the Hungarian helpers
    _LARGE_COST: float = 1e6
    _ZERO_EPS: float = 1e-12

    def _bbox_center(
            self, x1: float, y1: float, x2: float, y2: float,
    ) -> tuple[float, float]:
        """
        Return the center point (cx, cy) of a bbox.

        Args:
            x1: The x1 coordinate of the bbox.
            y1: The y1 coordinate of the bbox.
            x2: The x2 coordinate of the bbox.
            y2: The y2 coordinate of the bbox.

        Returns:
            The center point (cx, cy) of the bbox.
        """
        return (x1 + x2) * 0.5, (y1 + y2) * 0.5

    def _bbox_iou(
        self,
        a: tuple[float, float, float, float],
        b: tuple[float, float, float, float],
    ) -> float:
        """
        Compute IoU for two boxes (x1,y1,x2,y2).

        Args:
            a: The first box (x1, y1, x2, y2).
            b: The second box (x1, y1, x2, y2).

        Returns:
            The IoU (Intersection over Union) of the two boxes.
        """
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        if inter_x2 > inter_x1 and inter_y2 > inter_y1:
            inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        else:
            inter_area = 0.0
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        union = area_a + area_b - inter_area
        return inter_area / union if union > 0 else 0.0

    def _squared_distance(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> float:
        """
        Return squared Euclidean distance between points p1 and p2.

        Args:
            p1: The first point (x, y).
            p2: The second point (x, y).

        Returns:
            The squared Euclidean distance.
        """
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return dx * dx + dy * dy

    def _set_remote_track(
        self,
        tid: int,
        bbox: tuple[float, float, float, float],
        cls_id: int,
        center: tuple[float, float],
    ) -> None:
        """
        Upsert a remote track's latest state.

        Args:
            tid: The track ID.
            bbox: The bounding box (x1, y1, x2, y2).
            cls_id: The class ID.
            center: The center point (cx, cy).

        Returns:
            None
        """
        self.remote_tracks[tid] = {
            'bbox': bbox,
            'center': center,
            'last_seen': self.frame_count,
            'cls': cls_id,
        }

    def _new_track_for_det(self, det: list[float]) -> list[float]:
        """
        Create a new track entry for a single detection.

        Args:
            det: A single detection [x1, y1, x2, y2, conf, cls_id].

        Returns:
            A tracked row [x1, y1, x2, y2, conf, cls_id, track_id, is_moving].
        """
        x1, y1, x2, y2, conf, cls_id = det
        cx, cy = self._bbox_center(x1, y1, x2, y2)
        tid = self.next_remote_id
        self.next_remote_id += 1
        self._set_remote_track(tid, (x1, y1, x2, y2), int(cls_id), (cx, cy))
        return [x1, y1, x2, y2, conf, cls_id, tid, 0]

    # Centroid tracker (original simple implementation)
    def _track_remote_centroid(
        self, dets: list[list[float]],
    ) -> list[list[float]]:
        """Simple centroid-based tracker for remote detections.

        Args:
            dets: List of detections [x1, y1, x2, y2, conf, cls].

        Returns:
            List with tracking info [x1, y1, x2, y2, conf, cls, track_id,
            is_moving].
        """
        if not dets:
            if self.frame_count % 10 == 0:
                self._prune_remote_tracks()
            return []

        assigned_tracks: list[list[float]] = []
        used_track_ids: set[int] = set()
        track_items = list(self.remote_tracks.items())
        track_centers = [info['center'] for _, info in track_items]
        track_cls = [info['cls'] for _, info in track_items]

        for det in dets:
            x1, y1, x2, y2, conf, cls_id = det
            cx, cy = self._bbox_center(x1, y1, x2, y2)
            best_tid = None
            best_dist_sq = float('inf')
            for (tid, _), (tcx, tcy), tcls in zip(
                track_items, track_centers, track_cls,
            ):
                if tid in used_track_ids or tcls != cls_id:
                    continue
                dist_sq = self._squared_distance((cx, cy), (tcx, tcy))
                if (
                    dist_sq < best_dist_sq and
                    dist_sq < (self.movement_thr_sq * 4)
                ):
                    best_dist_sq = dist_sq
                    best_tid = tid
            if best_tid is None:
                # new track
                tracked_row = self._new_track_for_det(det)
                assigned_tracks.append(tracked_row)
                continue
            else:
                tid = best_tid
                used_track_ids.add(tid)
                prev_center = self.remote_tracks[tid]['center']
                dist_sq_move = self._squared_distance((cx, cy), prev_center)
                moving_flag = 1 if dist_sq_move > self.movement_thr_sq else 0
            self._set_remote_track(
                tid, (x1, y1, x2, y2),
                int(cls_id), (cx, cy),
            )
            assigned_tracks.append(
                [x1, y1, x2, y2, conf, cls_id, tid, moving_flag],
            )
        if self.frame_count % 10 == 0:
            self._prune_remote_tracks()
        return assigned_tracks

    # Hungarian (global) assignment tracker
    def _track_remote_hungarian(
        self, dets: list[list[float]],
    ) -> list[list[float]]:
        """
        Global assignment tracker using Hungarian algorithm.

        Args:
            dets: List of detections [x1, y1, x2, y2, conf, cls].

        Returns:
            List with tracking info [x1, y1, x2, y2, conf, cls, track_id,
            is_moving].
        """
        if not dets:
            if self.frame_count % 10 == 0:
                self._prune_remote_tracks()
            return []

        # Build arrays for existing tracks
        track_items = list(self.remote_tracks.items())  # (tid, info)
        num_tracks = len(track_items)

        # If no existing tracks, create new ones directly
        if num_tracks == 0:
            return self._assign_new_tracks_for_all(dets)

        # Prepare cost matrix and solve assignment
        cost_matrix = self._build_cost_matrix(dets, track_items)
        matches, unmatched_dets, _ = self._hungarian_assign(
            cost_matrix, self.remote_cost_threshold,
        )

        assigned, used_track_ids = self._update_matched_tracks(
            dets, track_items, matches,
        )
        assigned += self._create_tracks_for_unmatched(dets, unmatched_dets)

        # (Optionally) we could retire unmatched tracks after grace period;
        # pruning handles this
        if self.frame_count % 10 == 0:
            self._prune_remote_tracks()
        return assigned

    def _assign_new_tracks_for_all(
        self, dets: list[list[float]],
    ) -> list[list[float]]:
        """
        Create brand-new tracks for each detection when no tracks exist.

        Args:
            dets: List of detections [x1, y1, x2, y2, conf, cls].

        Returns:
            List with tracking info [x1, y1, x2, y2, conf, cls, track_id,
            is_moving].
        """
        assigned: list[list[float]] = []
        for det in dets:
            assigned.append(self._new_track_for_det(det))
        return assigned

    def _build_cost_matrix(
        self,
        dets: list[list[float]],
        track_items: list[tuple[int, dict]],
    ) -> np.ndarray:
        """
        Compute the cost matrix for detections vs tracks.

        Args:
            dets: List of detections [x1, y1, x2, y2, conf, cls].
            track_items: List of track items [(track_id, info), ...].

        Returns:
            Cost matrix as a NumPy array.
        """
        num_dets = len(dets)
        num_tracks = len(track_items)
        cost_matrix = np.full(
            (num_dets, num_tracks),
            self._LARGE_COST, dtype=float,
        )

        for d_idx, det in enumerate(dets):
            for t_idx, (_tid, info) in enumerate(track_items):
                cost_matrix[d_idx, t_idx] = self._compute_pair_cost(det, info)
        return cost_matrix

    def _compute_pair_cost(self, det: list[float], info: dict) -> float:
        """
        Compute combined IoU and distance based cost for a pair.

        Args:
            det: Detection [x1, y1, x2, y2, conf, cls].
            info: Track info dictionary.

        Returns:
            Combined cost as a float.
        """
        x1, y1, x2, y2, _conf, cls_id = det
        if info['cls'] != cls_id:
            return self._LARGE_COST
        tx1, ty1, tx2, ty2 = info['bbox']
        tcx, tcy = info['center']
        # IoU
        iou = self._bbox_iou((x1, y1, x2, y2), (tx1, ty1, tx2, ty2))
        # Distance normalised
        cx, cy = self._bbox_center(x1, y1, x2, y2)
        dist_sq = self._squared_distance((cx, cy), (tcx, tcy))
        dist_norm = min(dist_sq / (self.movement_thr_sq * 4), 1.0)
        return 0.5 * (1 - iou) + 0.5 * dist_norm

    def _update_matched_tracks(
        self,
        dets: list[list[float]],
        track_items: list[tuple[int, dict]],
        matches: list[tuple[int, int]],
    ) -> tuple[list[list[float]], set[int]]:
        """
        Update matched tracks and compute moving flags.

        Args:
            dets:
                List of detections [x1, y1, x2, y2, conf, cls].
            track_items:
                List of track items [(track_id, info), ...].
            matches:
                List of matched pairs [(detection_index, track_index), ...].

        Returns:
            Tuple of (assigned_tracks, used_track_ids).
        """
        assigned: list[list[float]] = []
        used_track_ids: set[int] = set()

        # Update matched tracks
        for d_idx, t_idx in matches:
            x1, y1, x2, y2, conf, cls_id = dets[d_idx]
            tid, info = track_items[t_idx]
            cx, cy = self._bbox_center(x1, y1, x2, y2)
            prev_center = info['center']
            dist_sq_move = self._squared_distance((cx, cy), prev_center)
            moving_flag = 1 if dist_sq_move > self.movement_thr_sq else 0
            self._set_remote_track(
                tid, (x1, y1, x2, y2),
                int(cls_id), (cx, cy),
            )
            assigned.append([x1, y1, x2, y2, conf, cls_id, tid, moving_flag])
            used_track_ids.add(tid)
        return assigned, used_track_ids

    def _create_tracks_for_unmatched(
        self, dets: list[list[float]], unmatched_dets: list[int],
    ) -> list[list[float]]:
        """
        Create tracks for unmatched detections.

        Args:
            dets: List of detections [x1, y1, x2, y2, conf, cls].
            unmatched_dets: List of unmatched detection indices.

        Returns:
            List of new track representations.
        """
        assigned: list[list[float]] = []
        for d_idx in unmatched_dets:
            assigned.append(self._new_track_for_det(dets[d_idx]))
        return assigned

    # Hungarian assignment helper
    def _hungarian_assign(
        self, cost: np.ndarray, cost_threshold: float,
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        """
        Apply Hungarian algorithm on cost matrix and filter by threshold.

        Args:
            cost: Cost matrix as a 2D numpy array.
            cost_threshold: Cost threshold for filtering matches.

        Returns:
            (matches, unmatched_rows, unmatched_cols)
        """
        # Copy and square-pad
        cost_matrix = cost.copy()
        num_rows, num_cols = cost_matrix.shape
        cost_matrix, n = self._pad_to_square(cost_matrix)

        # Reduce
        self._row_col_reduce(cost_matrix)

        # Iteratively cover zeros and adjust
        while True:
            covered_rows, covered_cols = self._cover_zeros(cost_matrix)
            if len(covered_rows) + len(covered_cols) >= n:
                break
            if not self._adjust_matrix_with_min(
                cost_matrix, covered_rows, covered_cols,
            ):
                break

        # Extract assignment greedily from zeros (since matrix reduced)
        assigned_cols = set()
        matches_all: list[tuple[int, int]] = []
        for r in range(n):
            zero_cols = [
                c for c in range(n)
                if (
                    abs(cost_matrix[r, c]) < self._ZERO_EPS
                    and c not in assigned_cols
                )
            ]
            if zero_cols:
                c_sel = zero_cols[0]
                assigned_cols.add(c_sel)
                matches_all.append((r, c_sel))
            else:  # pragma: no cover (degenerate no-zero row after reduction)
                pass

        # Filter to original matrix size and cost threshold
        matches: list[tuple[int, int]] = []
        used_rows = set()
        used_cols = set()
        for r, c in matches_all:
            if r < num_rows and c < num_cols:
                original_cost = cost[r, c]
                if original_cost <= cost_threshold:
                    matches.append((r, c))
                    used_rows.add(r)
                    used_cols.add(c)

        unmatched_rows = [r for r in range(num_rows) if r not in used_rows]
        unmatched_cols = [c for c in range(num_cols) if c not in used_cols]
        return matches, unmatched_rows, unmatched_cols

    def _pad_to_square(self, mat: np.ndarray) -> tuple[np.ndarray, int]:
        """
        Pad a rectangular matrix to square by filling with large cost.

        Args:
            mat: Input matrix to pad.

        Returns:
            Tuple of (padded_matrix, new_size).
        """
        num_rows, num_cols = mat.shape
        n = max(num_rows, num_cols)
        if num_rows == num_cols:
            return mat, n
        padded = np.full((n, n), self._LARGE_COST, dtype=float)
        padded[:num_rows, :num_cols] = mat
        return padded, n

    def _row_col_reduce(self, mat: np.ndarray) -> None:
        """Perform row and column reduction in-place."""
        mat -= mat.min(axis=1, keepdims=True)
        mat -= mat.min(axis=0, keepdims=True)

    def _cover_zeros(
        self, mat: np.ndarray,
    ) -> tuple[set[int], set[int]]:
        """
        Cover all zeros using minimum number of horizontal/vertical lines.

        Args:
            mat: Input matrix to cover zeros.

        Returns:
            Tuple of (covered_rows, covered_cols).
        """
        n_local = mat.shape[0]
        covered_rows: set[int] = set()
        covered_cols: set[int] = set()
        zero_locs = [
            (r, c) for r in range(n_local)
            for c in range(n_local) if abs(mat[r, c]) < self._ZERO_EPS
        ]
        row_zero_count = {r: 0 for r in range(n_local)}
        col_zero_count = {c: 0 for c in range(n_local)}
        for r, c in zero_locs:
            row_zero_count[r] += 1
            col_zero_count[c] += 1
        while zero_locs:
            row_counts = {r: 0 for r in range(n_local)}
            col_counts = {c: 0 for c in range(n_local)}
            for (r, c) in zero_locs:
                if r not in covered_rows and c not in covered_cols:
                    row_counts[r] += 1
                    col_counts[c] += 1
            if (
                row_counts and (
                    not col_counts or
                    max(row_counts.values()) >= max(col_counts.values())
                )
            ):
                r_sel = max(row_counts, key=lambda k: row_counts[k])
                covered_rows.add(r_sel)
            else:
                c_sel = max(col_counts, key=lambda k: col_counts[k])
                covered_cols.add(c_sel)
            zero_locs = [
                zc for zc in zero_locs
                if zc[0] not in covered_rows and zc[1] not in covered_cols
            ]
        return covered_rows, covered_cols

    def _adjust_matrix_with_min(
        self, mat: np.ndarray, covered_rows: set[int], covered_cols: set[int],
    ) -> bool:
        """
        Adjust the matrix by subtracting the minimum value from uncovered
        cells and adding it to the intersections of covered rows and columns.

        Args:
            mat: Input matrix to adjust.
            covered_rows: Set of covered row indices.
            covered_cols: Set of covered column indices.

        Returns:
            True if adjustment was applied, False otherwise.
        """
        n = mat.shape[0]
        uncovered = [
            mat[r, c] for r in range(n)
            if r not in covered_rows for c in range(n)
            if c not in covered_cols
        ]
        if not uncovered:
            return False
        m = min(uncovered)
        for r in range(n):
            for c in range(n):
                if r not in covered_rows and c not in covered_cols:
                    mat[r, c] -= m
                elif r in covered_rows and c in covered_cols:
                    mat[r, c] += m
        return True

    def _prune_remote_tracks(self) -> None:
        """
        Remove remote tracks that have not been updated
        within max_id_keep frames.
        """
        threshold = self.frame_count - self.max_id_keep
        stale = [
            tid for tid, info in self.remote_tracks.items()
            if info['last_seen'] < threshold
        ]
        for tid in stale:
            self.remote_tracks.pop(tid, None)

    async def run_detection(self, stream_url: str) -> None:
        """Run continuous object detection on a video stream.

        This method opens a video stream, performs real-time object detection
        with tracking, and displays the results in a window. The detection
        loop continues until the user presses 'q' to quit.

        Args:
            stream_url: URL or path to the video stream source.

        Raises:
            ValueError: If the stream cannot be opened.
        """
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            raise ValueError('Failed to open stream.')
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    await asyncio.sleep(1)
                    continue
                datas, tracked = await self.generate_detections(frame)
                disp = frame.copy()  # Use copy of original frame for display
                for d in tracked:
                    x1, y1, x2, y2, _, _, tid, mov = d
                    cv2.rectangle(
                        disp, (int(x1), int(y1)),
                        (int(x2), int(y2)), (0, 255, 0), 2,
                    )
                    cv2.putText(
                        disp, f"ID{tid} M{mov}", (int(x1), int(y1)-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                    )
                cv2.imshow('Stream', disp)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()
            await self.net.close()

    async def close(self) -> None:
        """Close WebSocket and aiohttp session to prevent resource leaks.

        This method properly closes all network connections and cleans up
        resources to prevent memory leaks and thread exceptions.
        """
        try:
            await self.net.close()
        except Exception as e:
            self._logger.error(f"Error closing NetClient: {e}")

    def remove_overlapping_labels(self, datas):
        """
        Removes overlapping labels for Hardhat and Safety Vest categories.

        Args:
            datas (list): A list of detection data in YOLO format.

        Returns:
            list: A list of detection data with overlapping labels removed.
        """
        # Indices of Hardhat detections
        hardhat_indices = [
            i for i, d in enumerate(
                datas,
            ) if d[5] == 0
        ]
        # Indices of NO-Hardhat detections
        no_hardhat_indices = [i for i, d in enumerate(datas) if d[5] == 2]
        # Indices of Safety Vest detections
        safety_vest_indices = [i for i, d in enumerate(datas) if d[5] == 7]
        # Indices of NO-Safety Vest detections
        no_safety_vest_indices = [i for i, d in enumerate(datas) if d[5] == 4]

        to_remove = set()
        for hardhat_index in hardhat_indices:
            for no_hardhat_index in no_hardhat_indices:
                overlap = self.overlap_percentage(
                    datas[hardhat_index][:4], datas[no_hardhat_index][:4],
                )
                if overlap > 0.8:
                    to_remove.add(no_hardhat_index)

        for safety_vest_index in safety_vest_indices:
            for no_safety_vest_index in no_safety_vest_indices:
                overlap = self.overlap_percentage(
                    datas[safety_vest_index][:4],
                    datas[no_safety_vest_index][:4],
                )
                if overlap > 0.8:
                    to_remove.add(no_safety_vest_index)

        for index in sorted(to_remove, reverse=True):
            datas.pop(index)

        gc.collect()
        return datas

    def overlap_percentage(self, bbox1, bbox2):
        """
        Calculates the percentage of overlap between two bounding boxes.

        Args:
            bbox1 (list): The first bounding box [x1, y1, x2, y2].
            bbox2 (list): The second bounding box [x1, y1, x2, y2].

        Returns:
            float: The percentage of overlap between the two bounding boxes.
        """
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])

        intersection_area = max(0, x2 - x1 + 1) * max(0, y2 - y1 + 1)
        bbox1_area = (bbox1[2] - bbox1[0] + 1) * (bbox1[3] - bbox1[1] + 1)
        bbox2_area = (bbox2[2] - bbox2[0] + 1) * (bbox2[3] - bbox2[1] + 1)

        overlap_percentage = intersection_area / float(
            bbox1_area + bbox2_area - intersection_area,
        )
        gc.collect()

        return overlap_percentage

    def is_contained(self, inner_bbox, outer_bbox):
        """
        Determines if one bounding box is completely contained within another.

        Args:
            inner_bbox (list): The inner bounding box [x1, y1, x2, y2].
            outer_bbox (list): The outer bounding box [x1, y1, x2, y2].

        Returns:
            bool: Checks if inner box is fully within outer bounding box.
        """
        return (
            inner_bbox[0] >= outer_bbox[0]
            and inner_bbox[2] <= outer_bbox[2]
            and inner_bbox[1] >= outer_bbox[1]
            and inner_bbox[3] <= outer_bbox[3]
        )

    def remove_completely_contained_labels(self, datas):
        """
        Removes labels fully contained in Hardhat/Safety Vest categories.

        Args:
            datas (list): A list of detection data in YOLO format.

        Returns:
            list: Detection data with fully contained labels removed.
        """
        # Indices of Hardhat detections
        hardhat_indices = [
            i
            for i, d in enumerate(
                datas,
            )
            if d[5] == 0
        ]

        # Indices of NO-Hardhat detections
        no_hardhat_indices = [i for i, d in enumerate(datas) if d[5] == 2]

        # Indices of Safety Vest detections
        safety_vest_indices = [i for i, d in enumerate(datas) if d[5] == 7]

        # Indices of NO-Safety Vest detections
        no_safety_vest_indices = [i for i, d in enumerate(datas) if d[5] == 4]

        to_remove = set()
        # Check hardhats
        for hardhat_index in hardhat_indices:
            for no_hardhat_index in no_hardhat_indices:
                if self.is_contained(
                    datas[no_hardhat_index][:4],
                    datas[hardhat_index][:4],
                ):
                    to_remove.add(no_hardhat_index)
                elif self.is_contained(
                    datas[hardhat_index][:4],
                    datas[no_hardhat_index][:4],
                ):
                    to_remove.add(hardhat_index)

        # Check safety vests
        for safety_vest_index in safety_vest_indices:
            for no_safety_vest_index in no_safety_vest_indices:
                if self.is_contained(
                    datas[no_safety_vest_index][:4],
                    datas[safety_vest_index][:4],
                ):
                    to_remove.add(no_safety_vest_index)
                elif self.is_contained(
                    datas[safety_vest_index][:4],
                    datas[no_safety_vest_index][:4],
                ):
                    to_remove.add(safety_vest_index)

        for index in sorted(to_remove, reverse=True):
            datas.pop(index)

        return datas


async def main() -> None:
    """Main execution block for command-line interface.

    Args:
        None
    """
    parser = argparse.ArgumentParser(
        description='Live stream detection with WebSocket support',
    )
    parser.add_argument(
        '--url', type=str, required=True,
        help='Stream URL or video file path',
    )
    parser.add_argument(
        '--api_url', type=str,
        default=os.getenv('DETECT_API_URL', 'http://localhost:8000'),
        help='Base API URL for remote inference',
    )
    parser.add_argument(
        '--model_key', type=str,
        default='yolo11n', help='YOLO model identifier key',
    )
    parser.add_argument(
        '--detect_with_server',
        action='store_true', help='Enable remote WebSocket inference',
    )
    parser.add_argument(
        '--use_ultralytics', action='store_true',
        help='Use Ultralytics YOLO for local inference',
    )
    args = parser.parse_args()

    # Initialise shared token dictionary for authentication
    shared_token: SharedToken = SharedToken(
        access_token='', refresh_token='', is_refreshing=False,
    )

    # Create detector instance with parsed arguments
    detector = LiveStreamDetector(
        api_url=args.api_url,
        model_key=args.model_key,
        detect_with_server=args.detect_with_server,
        shared_token=shared_token,
        use_ultralytics=args.use_ultralytics,
    )

    # Run detection loop
    await detector.run_detection(args.url)

if __name__ == '__main__':
    asyncio.run(main())
