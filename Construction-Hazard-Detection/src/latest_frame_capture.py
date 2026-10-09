from __future__ import annotations

import asyncio
import gc
import os
import threading
import time
from collections.abc import AsyncGenerator

import cv2
import numpy as np


class LatestFrameCapture:
    """Continuously drain a live stream and expose only its newest frame.

    Detection is intentionally kept out of the reader thread.  If inference is
    slower than the camera, intermediate frames are overwritten instead of
    being queued and processed many seconds later.
    """

    def __init__(
        self,
        stream_url: str,
        capture_interval: float = 0.2,
        reconnect_after_failures: int = 5,
    ) -> None:
        self.stream_url = stream_url
        self.capture_interval = max(0.0, capture_interval)
        self.reconnect_after_failures = max(1, reconnect_after_failures)
        self.cap: cv2.VideoCapture | None = None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_timestamp = 0.0
        self._latest_sequence = 0
        self.last_delivered_sequence = 0

    def _open_stream(self) -> cv2.VideoCapture | None:
        # OpenCV passes these options to FFmpeg.  TCP prevents most packet-loss
        # corruption; nobuffer/low_delay reduce latency for a live source.
        if self.stream_url.lower().startswith('rtsp://'):
            os.environ.setdefault(
                'OPENCV_FFMPEG_CAPTURE_OPTIONS',
                'rtsp_transport;tcp|fflags;nobuffer|flags;low_delay',
            )

        try:
            cap = cv2.VideoCapture(
                self.stream_url,
                cv2.CAP_FFMPEG,
                [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                    5000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                    3000,
                ],
            )
        except (cv2.error, TypeError):
            # Older OpenCV builds do not accept constructor parameters.
            cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            cap.release()
            return None

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _release_capture(self) -> None:
        cap = self.cap
        self.cap = None
        if cap is not None:
            cap.release()

    def _reader_loop(self) -> None:
        failure_count = 0
        while not self._stop_event.is_set():
            if self.cap is None:
                self.cap = self._open_stream()
                if self.cap is None:
                    print('[capture] RTSP open failed; retrying in 2 seconds')
                    self._stop_event.wait(2.0)
                    continue
                print('[capture] RTSP connected; latest-frame reader started')
                failure_count = 0

            ret, frame = self.cap.read()
            if not ret or frame is None:
                failure_count += 1
                print(
                    '[capture] Failed to read frame; dropping it. '
                    f'consecutive_failures={failure_count}/'
                    f'{self.reconnect_after_failures}',
                )
                if failure_count >= self.reconnect_after_failures:
                    print('[capture] Failure threshold reached; reconnecting RTSP')
                    self._release_capture()
                    failure_count = 0
                    self._stop_event.wait(1.0)
                else:
                    self._stop_event.wait(0.02)
                continue

            failure_count = 0
            captured_at = time.time()
            with self._lock:
                self._latest_frame = frame
                self._latest_timestamp = captured_at
                self._latest_sequence += 1

        self._release_capture()

    def _start_reader(self) -> None:
        if self._reader_thread is not None and self._reader_thread.is_alive():
            return
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name='latest-frame-reader',
            daemon=True,
        )
        self._reader_thread.start()

    async def execute_capture(
        self,
    ) -> AsyncGenerator[tuple[np.ndarray, float]]:
        self._start_reader()
        last_sequence = -1
        last_yield_at = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()
            if now - last_yield_at < self.capture_interval:
                await asyncio.sleep(0.01)
                continue

            with self._lock:
                sequence = self._latest_sequence
                if sequence == last_sequence or self._latest_frame is None:
                    frame = None
                    timestamp = 0.0
                else:
                    # Give inference a stable image while the reader replaces
                    # the shared latest-frame slot in the background.
                    frame = self._latest_frame.copy()
                    timestamp = self._latest_timestamp

            if frame is None:
                await asyncio.sleep(0.01)
                continue

            last_sequence = sequence
            self.last_delivered_sequence = sequence
            last_yield_at = now
            yield frame, timestamp

    def update_capture_interval(self, new_interval: float) -> None:
        self.capture_interval = max(0.0, new_interval)

    def get_latest_frame(self) -> tuple[np.ndarray, float, int] | None:
        """Return an independent copy of the newest decoded frame.

        Returns:
            A ``(frame, captured_at, source_sequence)`` tuple, or ``None``
            before the first frame has been decoded.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            return (
                self._latest_frame.copy(),
                self._latest_timestamp,
                self._latest_sequence,
            )

    async def release_resources(self) -> None:
        self._stop_event.set()
        # VideoCapture is opened, read and released exclusively by the reader
        # thread.  Releasing it here while FFmpeg is inside read() can trigger
        # libavcodec's `fctx->async_lock` assertion and terminate the process.
        thread = self._reader_thread
        if thread is not None and thread.is_alive():
            await asyncio.to_thread(thread.join, 5.0)
        if thread is not None and thread.is_alive():
            print(
                '[capture] Reader is still leaving FFmpeg read(); '
                'capture will be released by the reader thread',
            )
        self._reader_thread = None
        with self._lock:
            self._latest_frame = None
        gc.collect()
