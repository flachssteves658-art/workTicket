from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2


@dataclass
class SegmentRecord:
    segment_id: int
    start_sec: float
    end_sec: float
    image_path: str
    objects: list[str]
    rules: list[str]
    caption: str


def generate_segments(
    video_path: str,
    output_dir: str,
    segment_seconds: float = 3.0,
) -> list[SegmentRecord]:
    video_file = Path(video_path)
    if not video_file.is_file():
        raise FileNotFoundError(f'Video file not found: {video_path}')
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    static_dir = out_dir.parent

    cap = cv2.VideoCapture(str(video_file))
    if not cap.isOpened():
        raise RuntimeError(f'Failed to open video: {video_path}')

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    if fps <= 0 or total_frames <= 0:
        cap.release()
        raise RuntimeError('Invalid video metadata (fps or frame count).')

    duration_sec = total_frames / fps

    segments: list[SegmentRecord] = []
    segment_id = 0
    current_start = 0.0

    while current_start < duration_sec:
        start_sec = current_start
        end_sec = min(current_start + segment_seconds, duration_sec)
        center_sec = (start_sec + end_sec) / 2.0
        center_frame = int(center_sec * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, center_frame)
        ok, frame = cap.read()
        if not ok or frame is None:
            current_start = end_sec
            continue

        image_filename = f'test3_segment_{segment_id:03d}.jpg'
        image_path = out_dir / image_filename
        ok, encoded = cv2.imencode(image_path.suffix, frame)
        if not ok:
            raise RuntimeError(f'Failed to encode image: {image_path}')
        encoded.tofile(str(image_path))
        rel_image_path = image_path.relative_to(static_dir).as_posix()

        caption = (
            f'test3.mp4 片段 {segment_id}，時間約為 {start_sec:.1f}s'
            f' - {end_sec:.1f}s。'
        )

        record = SegmentRecord(
            segment_id=segment_id,
            start_sec=start_sec,
            end_sec=end_sec,
            image_path=rel_image_path,
            objects=[],
            rules=[],
            caption=caption,
        )
        segments.append(record)

        segment_id += 1
        current_start = end_sec

    cap.release()
    return segments


def save_segments_to_json(
    segments: list[SegmentRecord],
    json_path: str,
) -> None:
    data: list[dict[str, Any]] = [asdict(s) for s in segments]
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    video = root / 'test3.mp4'
    demo_static_dir = Path(__file__).resolve().parent / 'static'
    output_dir = demo_static_dir / 'test3_segments'
    json_path = demo_static_dir / 'test3_segments.json'

    segments = generate_segments(str(video), str(output_dir))
    save_segments_to_json(segments, str(json_path))


if __name__ == '__main__':
    main()

