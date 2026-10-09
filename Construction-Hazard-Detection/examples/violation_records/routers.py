from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Query
from fastapi import Security
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from fastapi_jwt import JwtAuthorizationCredentials
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from werkzeug.utils import secure_filename

from examples.auth import user_service as _user_service
from examples.auth.database import get_db
from examples.auth.jwt_config import jwt_access
from examples.auth.models import Site
from examples.auth.models import User
from examples.auth.models import Violation
from examples.violation_records.path_utils import _determine_media_type
from examples.violation_records.path_utils import _normalize_safe_rel_path
from examples.violation_records.path_utils import _resolve_and_authorize
from examples.violation_records.schemas import SiteOut
from examples.violation_records.schemas import UploadViolationResponse
from examples.violation_records.schemas import ViolationItem
from examples.violation_records.schemas import ViolationList
from examples.violation_records.schemas import ViolationsIntent
from examples.violation_records.schemas import ViolationsSummary
from examples.violation_records.settings import STATIC_DIR
from examples.violation_records.violation_manager import ViolationManager
from src.llm_utils import call_ollama
from src.llm_utils import call_openai_compatible

if TYPE_CHECKING:
    from examples.violation_records.search_utils import SearchUtils

# Re-export for backward compatibility with tests
get_user_sites_cached = _user_service.get_user_sites_cached

# Instantiate a global ViolationManager for handling image saving
# and record creation.
violation_manager: ViolationManager = ViolationManager(base_dir=STATIC_DIR)

search_util: SearchUtils | None = None
_search_util_init_attempted: bool = False

_SEGMENTS_CACHE: list[dict] | None = None
_SEGMENTS_MTIME: float | None = None
_DEMO_STATIC_DIR: Path = Path(__file__).resolve().parent / 'static'
_SEGMENTS_PATH: Path = _DEMO_STATIC_DIR / 'test3_segments.json'
_TEST3_VIDEO_PATH: Path = Path(__file__).resolve().parents[2] / 'test3.mp4'


def _get_search_util() -> SearchUtils | None:
    global search_util
    global _search_util_init_attempted
    if _search_util_init_attempted:
        return search_util
    _search_util_init_attempted = True
    try:
        # CKIP imports PyTorch and can take minutes on some Windows machines.
        # Load it only when keyword expansion is actually requested; ordinary
        # upload/list routes should be available immediately after startup.
        from examples.violation_records.search_utils import SearchUtils

        search_util = SearchUtils(device=-1)
        return search_util
    except Exception:
        logging.getLogger(__name__).warning(
            '[violation_search] SearchUtils init failed; fallback to basic keyword matching',
            exc_info=True,
        )
        search_util = None
        return None


def _estimate_test3_duration_sec() -> float:
    try:
        import cv2
    except Exception:
        return 0.0
    try:
        cap = cv2.VideoCapture(str(_TEST3_VIDEO_PATH))
        if not cap.isOpened():
            cap.release()
            return 0.0
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        cap.release()
        if fps <= 0 or total_frames <= 0:
            return 0.0
        return float(total_frames / fps)
    except Exception:
        return 0.0


def _generate_fallback_segments(duration_sec: float, segment_sec: float) -> list[dict]:
    duration = float(duration_sec or 0.0)
    if duration <= 0:
        return []
    step = float(segment_sec or 0.0)
    if step <= 0:
        step = 3.0
    step = max(0.5, step)
    items: list[dict] = []
    segment_id = 0
    start = 0.0
    while start < duration:
        end = min(start + step, duration)
        if end <= start:
            break
        items.append(
            {
                'segment_id': segment_id,
                'start_sec': float(start),
                'end_sec': float(end),
                'image_path': '',
                'objects': [],
                'rules': [],
                'caption': (
                    f'test3.mp4 片段 {segment_id}，時間約為 {start:.1f}s'
                    f' - {end:.1f}s。'
                ),
            },
        )
        segment_id += 1
        start = end
    return items


def _load_segments() -> list[dict]:
    global _SEGMENTS_CACHE
    global _SEGMENTS_MTIME
    try:
        mtime = _SEGMENTS_PATH.stat().st_mtime if _SEGMENTS_PATH.is_file() else None
    except Exception:
        mtime = None
    if _SEGMENTS_CACHE is not None and _SEGMENTS_MTIME == mtime:
        return _SEGMENTS_CACHE
    if not _SEGMENTS_PATH.is_file():
        fallback_duration_raw = os.getenv('DEMO_SEGMENTS_FALLBACK_DURATION_SEC')
        fallback_duration = 0.0
        if fallback_duration_raw:
            try:
                fallback_duration = float(str(fallback_duration_raw).strip())
            except Exception:
                fallback_duration = 0.0
        if fallback_duration <= 0:
            fallback_duration = _estimate_test3_duration_sec()
        if fallback_duration <= 0:
            fallback_duration = 60.0
        segment_sec_raw = os.getenv('DEMO_SEGMENTS_FALLBACK_SEGMENT_SEC')
        segment_sec = 3.0
        if segment_sec_raw:
            try:
                segment_sec = float(str(segment_sec_raw).strip())
            except Exception:
                segment_sec = 3.0
        _SEGMENTS_CACHE = _generate_fallback_segments(
            duration_sec=fallback_duration,
            segment_sec=segment_sec,
        )
        _SEGMENTS_MTIME = mtime
        return _SEGMENTS_CACHE
    try:
        with _SEGMENTS_PATH.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            _SEGMENTS_CACHE = data
        else:
            _SEGMENTS_CACHE = _generate_fallback_segments(
                duration_sec=_estimate_test3_duration_sec() or 60.0,
                segment_sec=3.0,
            )
        _SEGMENTS_MTIME = mtime
    except Exception:
        logging.getLogger(__name__).error(
            f'[segments] Failed to load segments from: {_SEGMENTS_PATH}',
            exc_info=True,
        )
        _SEGMENTS_CACHE = _generate_fallback_segments(
            duration_sec=_estimate_test3_duration_sec() or 60.0,
            segment_sec=3.0,
        )
        _SEGMENTS_MTIME = mtime
    return _SEGMENTS_CACHE


def _filter_segments(
    keyword: str | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
    time_ranges: list[tuple[float, float]] | None = None,
) -> list[dict]:
    segments = _load_segments()
    kw = (keyword or '').strip()
    time_filtered: list[dict] = []
    ranges = [(float(s), float(e)) for (s, e) in (time_ranges or []) if e > s]
    for seg in segments:
        seg_start = float(seg.get('start_sec') or 0.0)
        seg_end = float(seg.get('end_sec') or 0.0)
        if ranges:
            matched = False
            for rs, re_ in ranges:
                if seg_end <= rs or seg_start >= re_:
                    continue
                matched = True
                break
            if not matched:
                continue
        else:
            if start_sec is not None and seg_end <= start_sec:
                continue
            if end_sec is not None and seg_start >= end_sec:
                continue
        time_filtered.append(seg)

    if not kw:
        time_filtered.sort(key=lambda x: float(x.get('start_sec') or 0.0))
        return time_filtered

    tokens = [t for t in re.split(r'\s+', kw.lower()) if t]
    if not tokens:
        time_filtered.sort(key=lambda x: float(x.get('start_sec') or 0.0))
        return time_filtered

    def seg_text(seg: dict) -> str:
        caption = str(seg.get('caption') or '')
        objects = ' '.join(seg.get('objects') or [])
        rules = ' '.join(seg.get('rules') or [])
        return ' '.join([caption, objects, rules]).lower()

    any_token_seen = any(
        any(token in seg_text(seg) for token in tokens)
        for seg in time_filtered
    )
    if not any_token_seen:
        time_filtered.sort(key=lambda x: float(x.get('start_sec') or 0.0))
        return time_filtered

    results = [seg for seg in time_filtered if all(token in seg_text(seg) for token in tokens)]
    results.sort(key=lambda x: float(x.get('start_sec') or 0.0))
    return results


def _merge_segments_to_clips(
    segments: list[dict],
    merge_gap_sec: float = 0.2,
) -> list[dict]:
    if not segments:
        return []
    sorted_segs = sorted(segments, key=lambda x: float(x.get('start_sec') or 0.0))

    clips: list[dict] = []
    current: dict | None = None
    for seg in sorted_segs:
        seg_start = float(seg.get('start_sec') or 0.0)
        seg_end = float(seg.get('end_sec') or 0.0)
        if seg_end <= seg_start:
            continue
        seg_id = seg.get('segment_id')
        rel_path = str(seg.get('image_path') or '').strip()

        if current is None:
            current = {
                'clip_id': 0,
                'start_sec': seg_start,
                'end_sec': seg_end,
                'segment_ids': [seg_id] if seg_id is not None else [],
                'segments_count': 1,
                'thumbnail_path': rel_path,
                'caption': str(seg.get('caption') or '').strip(),
            }
            continue

        cur_end = float(current.get('end_sec') or 0.0)
        if seg_start <= cur_end + max(0.0, float(merge_gap_sec)):
            current['end_sec'] = max(cur_end, seg_end)
            current['segments_count'] = int(current.get('segments_count') or 0) + 1
            if seg_id is not None and isinstance(current.get('segment_ids'), list):
                current['segment_ids'].append(seg_id)
            if not str(current.get('thumbnail_path') or '').strip() and rel_path:
                current['thumbnail_path'] = rel_path
            if not str(current.get('caption') or '').strip():
                current['caption'] = str(seg.get('caption') or '').strip()
            continue

        clips.append(current)
        current = {
            'clip_id': len(clips),
            'start_sec': seg_start,
            'end_sec': seg_end,
            'segment_ids': [seg_id] if seg_id is not None else [],
            'segments_count': 1,
            'thumbnail_path': rel_path,
            'caption': str(seg.get('caption') or '').strip(),
        }

    if current is not None:
        clips.append(current)
    return clips


def _parse_sec_ranges_from_strings(
    ranges: list[str] | None,
    duration_sec: float,
) -> list[tuple[float, float]]:
    items: list[tuple[float, float]] = []
    for raw in (ranges or []):
        text = str(raw or '').strip()
        if not text:
            continue
        m = re.match(r'^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$', text)
        if not m:
            continue
        a = float(m.group(1))
        b = float(m.group(2))
        s = max(0.0, min(a, b))
        e = max(a, b)
        if duration_sec > 0:
            e = min(duration_sec, e)
            s = min(s, e)
        if e > s:
            items.append((s, e))
    return items


def _segments_duration_sec() -> float:
    segments = _load_segments()
    best = 0.0
    for seg in segments:
        try:
            best = max(best, float(seg.get('end_sec') or 0.0))
        except Exception:
            continue
    return best


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _parse_loop_start_at(now: datetime) -> datetime:
    raw = str(os.getenv('DEMO_SEGMENTS_LOOP_START_AT') or '').strip()
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=now.tzinfo)
            return dt.astimezone(now.tzinfo)
        except Exception:
            pass
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day


def _extract_demo_location(text: str) -> str:
    raw = str(text or '').strip()
    if not raw:
        return ''
    def accept(value: str) -> str:
        candidate = str(value or '').strip()
        if not candidate:
            return ''
        if re.fullmatch(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', candidate):
            return ''
        if re.fullmatch(r'\d{1,2}[/-]\d{1,2}(?:[/-]\d{1,2})?', candidate):
            return ''
        if re.fullmatch(r'\d+(?:\.\d+)?', candidate):
            return ''
        if re.fullmatch(r'\d{1,2}(?::|点)\d{1,2}', candidate):
            return ''
        if re.fullmatch(r'\d{1,2}点', candidate):
            return ''
        return candidate
    m = re.search(
        r'([\u4e00-\u9fffA-Za-z0-9_-]{2,32})(?:变电站|站|工地|现场|地点|位置|厂区)',
        raw,
    )
    if m:
        out = accept(m.group(1))
        if out:
            return out
    m2 = re.search(
        r'(?:在|到|去|查|查询|检索|回放)\s*([\u4e00-\u9fffA-Za-z0-9_-]{2,32})',
        raw,
    )
    if m2:
        out = accept(m2.group(1))
        if out:
            return out
    return ''


def _parse_real_datetime_range(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    raw = str(text or '').strip()
    if not raw:
        return None

    tz = now.tzinfo
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)

    date_m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', raw)
    if date_m:
        try:
            y, mo, d = int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3))
            base = datetime(y, mo, d, tzinfo=tz)
        except Exception:
            base = base
    else:
        if '前天' in raw:
            base = base - timedelta(days=2)
        elif '昨天' in raw or '昨日' in raw:
            base = base - timedelta(days=1)
        elif '明天' in raw:
            base = base + timedelta(days=1)

    def build(h: int, m: int) -> datetime:
        return base.replace(hour=h, minute=m, second=0, microsecond=0)

    hm_range = re.search(
        r'(?<!\d)(\d{1,2})(?::|点)(\d{1,2})?\s*(?:到|至|-|~|—|－|–|～)\s*(\d{1,2})(?::|点)(\d{1,2})?',
        raw,
    )
    if hm_range:
        sh = int(hm_range.group(1))
        sm = int(hm_range.group(2) or 0)
        eh = int(hm_range.group(3))
        em = int(hm_range.group(4) or 0)
        start = build(sh, sm)
        end = build(eh, em)
        if end <= start:
            end = end + timedelta(days=1)
        return start, end

    hm_single = re.search(r'(?<!\d)(\d{1,2})(?::|点)(\d{1,2})', raw)
    if hm_single:
        h = int(hm_single.group(1))
        m = int(hm_single.group(2))
        at = build(h, m)
        return at - timedelta(minutes=10), at + timedelta(minutes=10)

    h_range = re.search(
        r'(?<!\d)(\d{1,2})\s*点\s*(?:到|至|-|~|—|－|–|～)\s*(\d{1,2})\s*点',
        raw,
    )
    if h_range:
        sh = int(h_range.group(1))
        eh = int(h_range.group(2))
        start = build(sh, 0)
        end = build(eh, 0)
        if end <= start:
            end = end + timedelta(days=1)
        return start, end

    rel_m = re.search(r'(?:近|最近|前)\s*(\d{1,3})\s*(?:分钟|分)', raw)
    if rel_m:
        mins = int(rel_m.group(1))
        end = now
        start = now - timedelta(minutes=max(1, mins))
        return start, end

    if '下午' in raw:
        return build(13, 0), build(18, 0)
    if '上午' in raw:
        return build(8, 0), build(12, 0)
    if '中午' in raw:
        return build(11, 0), build(13, 0)
    if '晚上' in raw or '夜间' in raw or '夜里' in raw:
        return build(18, 0), build(23, 59)
    if '凌晨' in raw:
        return build(0, 0), build(6, 0)
    if '今天' in raw or '昨日' in raw or '昨天' in raw or date_m:
        return build(0, 0), build(23, 59)

    return None


def _sec_ranges_from_real_time(
    real_start: datetime,
    real_end: datetime,
    loop_start: datetime,
    duration_sec: float,
) -> list[tuple[float, float]]:
    if duration_sec <= 0:
        return []
    start = real_start
    end = real_end
    if end <= start:
        end = start + timedelta(seconds=1)
    window = (end - start).total_seconds()
    if window >= duration_sec:
        return [(0.0, float(duration_sec))]

    def mod_sec(t: datetime) -> float:
        delta = (t - loop_start).total_seconds()
        v = delta % duration_sec
        if v < 0:
            v += duration_sec
        return float(v)

    s = mod_sec(start)
    e = mod_sec(end)
    if e >= s:
        return [(s, e)]
    return [(s, float(duration_sec)), (0.0, e)]


def _parse_segments_intent(user_query: str) -> dict:
    text = str(user_query or '').strip()
    duration = _segments_duration_sec()
    if duration <= 0:
        duration = 30.0

    start_sec: float | None = None
    end_sec: float | None = None
    ranges: list[str] = []
    sec_ranges: list[tuple[float, float]] = []

    now = _local_now()
    loop_start = _parse_loop_start_at(now)
    location = _extract_demo_location(text)
    real_range = _parse_real_datetime_range(text, now)

    sec_ranges_from_query: list[tuple[float, float]] = []
    for m in re.finditer(
        r'(\d+(?:\.\d+)?)\s*(?:秒|s)\s*(?:到|至|-|~|—|－|–|～)\s*(\d+(?:\.\d+)?)\s*(?:秒|s)',
        text,
    ):
        s = float(m.group(1))
        e = float(m.group(2))
        seg_s = max(0.0, min(s, e))
        seg_e = min(duration, max(s, e))
        if seg_e > seg_s:
            sec_ranges_from_query.append((seg_s, seg_e))
    if sec_ranges_from_query:
        if len(sec_ranges_from_query) == 1:
            start_sec, end_sec = sec_ranges_from_query[0]
        else:
            ranges = [f'{s:.3f}-{e:.3f}' for s, e in sec_ranges_from_query]
            sec_ranges = sec_ranges_from_query

    if start_sec is None and end_sec is None:
        m_front = re.search(r'前\s*(\d+(?:\.\d+)?)\s*(?:秒|s)', text)
        if m_front:
            n = float(m_front.group(1))
            start_sec = 0.0
            end_sec = min(duration, n)

    if start_sec is None and end_sec is None:
        m_last = re.search(r'(?:后|最後|最后)\s*(\d+(?:\.\d+)?)\s*(?:秒|s)', text)
        if m_last:
            n = float(m_last.group(1))
            start_sec = max(0.0, duration - n)
            end_sec = duration

    if start_sec is None and end_sec is None and not ranges:
        if any(k in text for k in ('开头', '開始', '开始', '最开始', '前面', '起始')):
            start_sec = 0.0
            end_sec = min(duration, max(3.0, duration * 0.33))
        elif any(k in text for k in ('中间', '中段', '中間')):
            start_sec = max(0.0, duration * 0.33)
            end_sec = min(duration, duration * 0.66)
        elif any(k in text for k in ('结尾', '結尾', '最后', '最後', '末尾', '尾段')):
            start_sec = max(0.0, duration * 0.66)
            end_sec = duration

    real_start_time: str = ''
    real_end_time: str = ''
    loop_start_time: str = loop_start.isoformat()
    if start_sec is None and end_sec is None and not ranges and real_range is not None:
        real_start, real_end = real_range
        real_start_time = real_start.isoformat()
        real_end_time = real_end.isoformat()
        sec_ranges = _sec_ranges_from_real_time(real_start, real_end, loop_start, duration)
        ranges = [f'{s:.3f}-{e:.3f}' for s, e in sec_ranges if e > s]
        if len(sec_ranges) == 1:
            start_sec, end_sec = sec_ranges[0]

    keyword = text
    keyword = re.sub(r'(\d+(?:\.\d+)?\s*(?:秒|s))', '', keyword)
    keyword = re.sub(r'(到|至|-|~|—|－|–|～)', ' ', keyword)
    keyword = re.sub(
        r'(片段|视频|影片|畫面|监控|录像|錄像|摄像|摄像头|test3\.mp4|test3|mp4|演示|demo|查一下|查询|帮我|看看|给我|检索|回放)',
        ' ',
        keyword,
        flags=re.IGNORECASE,
    )
    keyword = re.sub(
        r'(开头|開始|开始|最开始|前面|起始|中间|中段|中間|结尾|結尾|最后|最後|末尾|尾段)',
        ' ',
        keyword,
    )
    keyword = re.sub(r'[，,。.;；:：!?！？、/\\|（）()\[\]{}<>“”"\'`]', ' ', keyword)
    keyword = re.sub(r'\d{4}\s*[/-]\s*\d{1,2}\s*[/-]\s*\d{1,2}', ' ', keyword)
    keyword = re.sub(r'(?<!\d)\d{1,2}\s*(?::|点)\s*\d{1,2}(?!\d)', ' ', keyword)
    keyword = re.sub(r'(?<!\d)\d{1,2}\s*点(?!\d)', ' ', keyword)
    keyword = re.sub(r'\s+', ' ', keyword).strip()
    if keyword:
        stopwords = {
            '的', '呢', '吧', '啊', '呀', '哦', '啦', '嘛', '吗', '么',
            '我', '帮', '帮我', '一下', '一下子', '一下啊', '一下呢',
            '请', '麻烦', '给', '给我', '看看', '查', '查询', '检索', '回放',
        }
        tokens = [t for t in keyword.split(' ') if t]
        cleaned = []
        for token in tokens:
            token = re.sub(r'(的|呢|吧|啊|呀|哦|啦|嘛|吗|么)$', '', token)
            if not token or token in stopwords:
                continue
            if re.fullmatch(r'\d+(?:\.\d+)?', token):
                continue
            if re.fullmatch(r'\d{4}[/-]\d{1,2}[/-]\d{1,2}', token):
                continue
            if re.fullmatch(r'\d{1,2}:\d{2}', token):
                continue
            if re.fullmatch(r'\d{1,2}点\d{1,2}', token):
                continue
            if re.fullmatch(r'\d{1,2}点', token):
                continue
            if token and token not in stopwords:
                cleaned.append(token)
        keyword = ' '.join(cleaned).strip()
    else:
        keyword = ''

    note = ''
    if real_range is not None:
        note = '演示模式：按循环映射将真实时间段映射到 test3.mp4 时间轴'

    time_ranges: list[dict] = []
    if sec_ranges:
        time_ranges = [{'start_sec': float(s), 'end_sec': float(e)} for s, e in sec_ranges if e > s]
    elif start_sec is not None and end_sec is not None and end_sec > start_sec:
        time_ranges = [{'start_sec': float(start_sec), 'end_sec': float(end_sec)}]

    return {
        'keyword': keyword,
        'start_sec': start_sec,
        'end_sec': end_sec,
        'ranges': ranges,
        'time_ranges': time_ranges,
        'location': location,
        'real_start_time': real_start_time,
        'real_end_time': real_end_time,
        'loop_start_time': loop_start_time,
        'note': note,
        'duration_sec': duration,
        'confidence': 0.5,
    }

# Create a FastAPI router for violations-related endpoints.
router: APIRouter = APIRouter()

# Note: get_user_sites_cached is provided by examples.auth.user_service


_WARNING_TEMPLATES: dict[str, str] = {
    'warning_people_in_controlled_area': '警告: 有{count}个人进入受控区域!',
    'warning_no_hardhat': '警告: 有{count}人未佩戴安全帽!',
    'warning_no_safety_vest': '警告: 有{count}人未穿着安全背心!',
    'warning_close_to_machinery': '警告: 有{count}人过于靠近机具!',
    'warning_close_to_vehicle': '警告: 有{count}人过于靠近车辆!',
    'warning_people_in_utility_pole_controlled_area': '警告: 有{count}人进入电杆管制区!',
    'detect_machinery_close_to_pole': '警告: 有{count}个机具过于靠近电杆!',
}


_RULE_DEFINITIONS: dict[str, dict] = {
    'warning_people_in_controlled_area': {
        'id': 'RULE-001',
        'name': '人员进入受控区域',
        'level': '高',
        'description': '受控作业区应实施围栏和警戒，非现场作业人员不得进入。',
        'category': '作业区域管理',
    },
    'warning_no_hardhat': {
        'id': 'RULE-002',
        'name': '未按规定佩戴安全帽',
        'level': '高',
        'description': '进入施工现场的人员必须正确佩戴安全帽，系紧帽带。',
        'category': '个体防护',
    },
    'warning_no_safety_vest': {
        'id': 'RULE-003',
        'name': '未按规定穿着反光背心',
        'level': '中',
        'description': '在车辆、机具运行区域作业时应穿着显著标识的安全反光背心。',
        'category': '个体防护',
    },
    'warning_close_to_machinery': {
        'id': 'RULE-004',
        'name': '人员与机具安全距离不足',
        'level': '高',
        'description': '人员应与运行中的机械设备保持规定的安全距离，避免夹击和碰撞风险。',
        'category': '机具作业安全',
    },
    'warning_close_to_vehicle': {
        'id': 'RULE-005',
        'name': '人员与车辆安全距离不足',
        'level': '高',
        'description': '在车辆出入和倒车区域应设置警戒并保持安全距离。',
        'category': '交通组织',
    },
    'warning_people_in_utility_pole_controlled_area': {
        'id': 'RULE-006',
        'name': '人员进入电杆管制区',
        'level': '高',
        'description': '带电线路、电杆周边应划定警戒区，非作业状态人员不得停留。',
        'category': '电气安全',
    },
    'detect_machinery_close_to_pole': {
        'id': 'RULE-007',
        'name': '机具接近电杆或线路',
        'level': '高',
        'description': '起重机械、工程车辆在接近电杆和导线时应采取限位和监护措施。',
        'category': '起重与吊装',
    },
}

_RISK_LEVEL_ORDER: dict[str, int] = {'低': 1, '中': 2, '高': 3}


async def _summarise_with_llm(
    user_query: str | None,
    total: int,
    samples: list[Violation],
) -> str | None:
    model_mode = os.getenv('VIOLATION_SUMMARY_LLM_MODE', '').strip()
    if not model_mode:
        aliyun_base = os.getenv('ALIYUN_BASE_URL', '').strip()
        aliyun_key = os.getenv('ALIYUN_API_KEY', '').strip()
        aliyun_model = os.getenv('ALIYUN_MODEL_NAME', '').strip()
        if aliyun_base and aliyun_key and aliyun_model:
            model_mode = 'api'
        else:
            return None
    messages: list[dict] = []
    system_prompt = (
        '你是一名电力施工安全督查专家，负责根据违章记录为管理人员生成简要总结，'
        '说明本次查询的整体风险情况、主要违章类型、集中发生的时间段或工地，并给出简短的管理建议。'
    )
    messages.append({'role': 'system', 'content': system_prompt})
    if user_query:
        messages.append({'role': 'user', 'content': f'本次查询的原始问题是：{user_query}'})
    lines: list[str] = []
    lines.append(f'本次查询命中的违章总数为: {total}')
    lines.append('以下是部分代表性违章记录:')
    for v in samples:
        time_str = v.detection_time.isoformat()
        warnings = _parse_json_dict(v.warnings_json)
        warning_parts: list[str] = []
        for key, value in warnings.items():
            count = 0
            if isinstance(value, dict):
                raw = value.get('count')
                try:
                    count = int(raw) if raw is not None else 0
                except Exception:
                    count = 0
            if count <= 0:
                continue
            warning_parts.append(f'{key}={count}')
        warning_text = '、'.join(warning_parts) if warning_parts else '无结构化告警信息'
        lines.append(
            f'- 站点:{v.site} 串流:{v.stream_name} 时间:{time_str} 告警:{warning_text}',
        )
        if v.agent_report and isinstance(v.agent_report, str):
            agent = v.agent_report.strip()
            if agent:
                lines.append(f'  agent_report: {agent}')
    messages.append({'role': 'user', 'content': '\n'.join(lines)})
    try:
        mode = model_mode.lower()
        if mode == 'ollama':
            model = os.getenv('VIOLATION_SUMMARY_OLLAMA_MODEL', '').strip() or 'qwen2.5:7b'
            base_url = os.getenv('VIOLATION_SUMMARY_OLLAMA_BASE_URL', '').strip() or 'http://localhost:11434'
            return await call_ollama(model=model, messages=messages, base_url=base_url)
        if mode in ('openai_compatible', 'api', 'aliyun', 'openai'):
            base_url = (
                os.getenv('VIOLATION_SUMMARY_OPENAI_BASE_URL', '').strip()
                or os.getenv('ALIYUN_BASE_URL', '').strip()
            )
            api_key = (
                os.getenv('VIOLATION_SUMMARY_OPENAI_API_KEY', '').strip()
                or os.getenv('ALIYUN_API_KEY', '').strip()
            )
            model = (
                os.getenv('VIOLATION_SUMMARY_OPENAI_MODEL', '').strip()
                or os.getenv('ALIYUN_MODEL_NAME', '').strip()
            )
            if not base_url or not api_key or not model:
                return None
            return await call_openai_compatible(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
            )
    except Exception as exc:
        logging.getLogger(__name__).error(
            f'[violations_summary] LLM summary failed: {exc}',
        )
    return None


def _extract_first_json_object(text: str | None) -> dict | None:
    if not text or not isinstance(text, str):
        return None
    candidates: list[str] = []
    raw = text.strip()
    if '```' in raw:
        parts = [p.strip() for p in raw.split('```') if p.strip()]
        candidates.extend(parts)
    candidates.append(raw)
    for candidate in candidates:
        cleaned = candidate.strip()
        cleaned = cleaned.removeprefix('json').strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            snippet = match.group(0)
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return None


def _parse_iso_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    raw = raw.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


async def _parse_intent_with_llm(
    user_query: str,
    sites: list[Site],
) -> dict | None:
    model_mode = os.getenv('VIOLATION_INTENT_LLM_MODE', '').strip()
    if not model_mode:
        aliyun_base = os.getenv('ALIYUN_BASE_URL', '').strip()
        aliyun_key = os.getenv('ALIYUN_API_KEY', '').strip()
        aliyun_model = os.getenv('ALIYUN_MODEL_NAME', '').strip()
        if aliyun_base and aliyun_key and aliyun_model:
            model_mode = 'api'
        else:
            return None
    sites_text = '\n'.join([f'- id={s.id} name={s.name}' for s in sites])
    system_prompt = (
        '你是一个电力施工安全视频检索助手。你的任务是将用户的自然语言检索指令解析为结构化查询条件。'
        '你只能输出严格 JSON 对象，不能输出任何解释、Markdown、代码块。'
    )
    user_prompt = (
        '可选站点列表如下（只能从中选择，允许多选；无法确定则返回空数组）：\n'
        f'{sites_text}\n\n'
        f'用户指令：{user_query}\n\n'
        '输出 JSON 格式如下：\n'
        '{'
        '"site_ids":[1,2],'
        '"keyword":"吊车 作业",'
        '"start_time":"2026-01-26T12:00:00",'
        '"end_time":"2026-01-26T18:00:00",'
        '"query_mode":"search",'
        '"confidence":0.0'
        '}\n'
        '规则：\n'
        '- site_ids 必须是整数数组；未知就 []。\n'
        '- keyword 为用于搜索的关键词（不包含站点名与时间表达）；未知就空字符串。\n'
        '- start_time/end_time 为 ISO 8601 时间字符串或 null。\n'
        '- query_mode 只能为 search。\n'
        '- confidence 为 0-1 之间的小数，代表你对解析结果的把握。\n'
    )
    messages: list[dict] = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]
    try:
        mode = model_mode.lower()
        if mode == 'ollama':
            model = os.getenv('VIOLATION_INTENT_OLLAMA_MODEL', '').strip() or 'qwen2.5:7b'
            base_url = os.getenv('VIOLATION_INTENT_OLLAMA_BASE_URL', '').strip() or 'http://localhost:11434'
            content = await call_ollama(model=model, messages=messages, base_url=base_url)
            return _extract_first_json_object(content)
        if mode in ('openai_compatible', 'api', 'aliyun', 'openai'):
            base_url = (
                os.getenv('VIOLATION_INTENT_OPENAI_BASE_URL', '').strip()
                or os.getenv('ALIYUN_BASE_URL', '').strip()
            )
            api_key = (
                os.getenv('VIOLATION_INTENT_OPENAI_API_KEY', '').strip()
                or os.getenv('ALIYUN_API_KEY', '').strip()
            )
            model = (
                os.getenv('VIOLATION_INTENT_OPENAI_MODEL', '').strip()
                or os.getenv('ALIYUN_MODEL_NAME', '').strip()
            )
            if not base_url or not api_key or not model:
                return None
            content = await call_openai_compatible(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
            )
            return _extract_first_json_object(content)
    except Exception as exc:
        logging.getLogger(__name__).error(
            f'[violations_intent] LLM intent failed: {exc}',
        )
    return None


def _fallback_intent_by_sites(
    user_query: str,
    sites: list[Site],
) -> dict:
    lower = user_query.lower()
    site_ids: list[int] = []
    for site in sites:
        name = str(site.name or '').strip()
        if not name:
            continue
        if name.lower() in lower:
            site_ids.append(int(site.id))
    keyword = user_query
    for site in sites:
        name = str(site.name or '').strip()
        if not name:
            continue
        keyword = keyword.replace(name, '')
    keyword = keyword.strip()
    return {
        'site_ids': site_ids,
        'keyword': keyword,
        'start_time': None,
        'end_time': None,
        'query_mode': 'search',
        'confidence': 0.1,
    }


def _build_rule_stats(samples: list[Violation]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for v in samples:
        warnings = _parse_json_dict(v.warnings_json)
        for key, value in warnings.items():
            if not isinstance(key, str):
                continue
            count = 0
            if isinstance(value, dict):
                raw = value.get('count')
                try:
                    count = int(raw) if raw is not None else 0
                except Exception:
                    count = 0
            if count <= 0:
                continue
            stats[key] = stats.get(key, 0) + count
    return stats


def _build_default_summary(
    user_query: str | None,
    total: int,
    samples: list[Violation],
) -> str:
    if total <= 0:
        if user_query:
            return f'根据当前问题“{user_query}”，未在违章记录中找到匹配结果。可以尝试放宽时间范围或调整描述。'
        return '当前条件下未在违章记录中找到匹配结果，可以尝试放宽时间范围或调整描述。'
    rule_stats = _build_rule_stats(samples)
    parts: list[str] = []
    parts.append(f'本次检索共命中违章记录 {total} 条。')
    if rule_stats:
        sorted_items = sorted(rule_stats.items(), key=lambda x: x[1], reverse=True)
        top_parts: list[str] = []
        for key, count in sorted_items[:5]:
            rule_def = _RULE_DEFINITIONS.get(key) or {}
            name = rule_def.get('name') or key
            top_parts.append(f'{name} {count} 次')
        parts.append('主要违章类型集中在：' + '，'.join(top_parts) + '。')
    else:
        parts.append('这些记录中未能解析出结构化告警类型。')
    times: list[datetime] = [v.detection_time for v in samples if v.detection_time]
    if times:
        first = min(times)
        last = max(times)
        parts.append(
            f'代表性记录的时间分布约在 {first.isoformat()} 到 {last.isoformat()} 之间。',
        )
    parts.append('建议对高频出现的违章类型开展针对性的安全培训和现场抽查。')
    return ''.join(parts)


def _parse_json_dict(raw: str | None) -> dict:
    if not raw or not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fallback_agent_report(
    site: str,
    stream_name: str,
    detection_time: datetime,
    warnings_json: str | None,
) -> str | None:
    warnings = _parse_json_dict(warnings_json)
    parts: list[str] = []
    for key, value in warnings.items():
        if not isinstance(key, str):
            continue
        count = 0
        if isinstance(value, dict):
            raw_count = value.get('count')
            try:
                count = int(raw_count) if raw_count is not None else 0
            except Exception:
                count = 0
        if count <= 0:
            continue
        template = _WARNING_TEMPLATES.get(key)
        if template:
            parts.append(template.format(count=count))
        else:
            parts.append(f'{key}: {count}')
    if not parts:
        return None
    return (
        f'{site} / {stream_name} 在 {detection_time.isoformat()} '
        f'检测到风险事件：{"；".join(parts)}。'
    )


def _get_agent_report_for_violation(v: Violation) -> str | None:
    raw = getattr(v, 'agent_report', None)
    if isinstance(raw, str) and raw.strip():
        return raw
    return _fallback_agent_report(
        v.site,
        v.stream_name,
        v.detection_time,
        v.warnings_json,
    )


def _map_rule_violations_from_warnings(
    warnings_json: str | None,
) -> list[dict]:
    warnings = _parse_json_dict(warnings_json)
    results: list[dict] = []
    for key, value in warnings.items():
        definition = _RULE_DEFINITIONS.get(str(key))
        if not definition:
            continue
        count = 0
        if isinstance(value, dict):
            raw_count = value.get('count')
            try:
                count = int(raw_count) if raw_count is not None else 0
            except Exception:
                count = 0
        if count <= 0:
            continue
        results.append(
            {
                'rule_id': definition.get('id'),
                'name': definition.get('name'),
                'level': definition.get('level'),
                'category': definition.get('category'),
                'description': definition.get('description'),
                'violation_count': count,
            },
        )
    return results


def _calculate_risk_level(violations: list[dict]) -> str:
    if not violations:
        return '低'
    highest = 0
    for item in violations:
        level = str(item.get('level') or '').strip()
        score = _RISK_LEVEL_ORDER.get(level, 0)
        if score > highest:
            highest = score
    if highest <= 1:
        return '低'
    if highest == 2:
        return '中'
    return '高'


def _build_markdown_report(
    violation: Violation,
    rule_violations: list[dict],
    risk_level: str,
    image_path: str | None,
) -> str:
    def _table_escape(value: object) -> str:
        text = str(value or '')
        text = text.replace('\n', ' ').replace('\r', ' ')
        return text.replace('|', '\\|')

    violation_id = getattr(violation, 'id', '')
    detection_time = (
        violation.detection_time.isoformat()
        if getattr(violation, 'detection_time', None)
        else ''
    )
    created_at = (
        violation.created_at.isoformat()
        if getattr(violation, 'created_at', None)
        else ''
    )

    warnings = _parse_json_dict(getattr(violation, 'warnings_json', None))
    warning_lines: list[str] = []
    for raw_key, raw_value in warnings.items():
        key = str(raw_key or '').strip()
        if not key:
            continue
        count = 0
        if isinstance(raw_value, dict):
            raw_count = raw_value.get('count')
            try:
                count = int(raw_count) if raw_count is not None else 0
            except Exception:
                count = 0
        if count <= 0:
            continue
        template = _WARNING_TEMPLATES.get(key)
        if template:
            warning_lines.append(template.format(count=count))
        else:
            warning_lines.append(f'{key}: {count}')
    if not warning_lines:
        warning_lines.append('无告警信息')

    agent_report = _get_agent_report_for_violation(violation)

    lines: list[str] = []
    lines.append(f'# 违章预警报告（ID: {violation_id}）')
    lines.append('')
    lines.append('## 一、事件概述')
    lines.append(f'- 综合风险等级: {risk_level}')
    lines.append('- 告警摘要:')
    for msg in warning_lines:
        lines.append(f'  - {msg}')

    lines.append('')
    lines.append('## 二、基本信息')
    lines.append('| 字段 | 值 |')
    lines.append('| --- | --- |')
    lines.append(f'| 站点 | {_table_escape(getattr(violation, "site", ""))} |')
    lines.append(
        f'| 串流 | {_table_escape(getattr(violation, "stream_name", ""))} |',
    )
    if detection_time:
        lines.append(f'| 检测时间 | {_table_escape(detection_time)} |')
    if created_at:
        lines.append(f'| 记录时间 | {_table_escape(created_at)} |')
    lines.append(f'| 综合风险等级 | {_table_escape(risk_level)} |')

    lines.append('')
    lines.append('## 三、规则与风险')
    if not rule_violations:
        lines.append('- 当前记录未匹配到配置的安全规则。')
    else:
        lines.append('| 序号 | 规则ID | 规则名称 | 等级 | 类别 | 次数 | 说明 |')
        lines.append('| --- | --- | --- | --- | --- | --- | --- |')
        for idx, item in enumerate(rule_violations, start=1):
            rule_id = _table_escape(item.get('rule_id') or '')
            name = _table_escape(item.get('name') or '')
            level = _table_escape(item.get('level') or '')
            category = _table_escape(item.get('category') or '')
            count = _table_escape(item.get('violation_count') or 0)
            desc = _table_escape(item.get('description') or '')
            lines.append(
                f'| {idx} | {rule_id} | {name} | {level} | {category} | {count} | {desc} |',
            )

    lines.append('')
    lines.append('## 四、证据与追溯')
    if image_path:
        normalized_path = str(image_path).replace('\\', '/')
        lines.append(f'- 图片路径: `{normalized_path}`')
        lines.append('- 获取图片接口:')
        lines.append('```text')
        lines.append(f'/get_violation_image?image_path={normalized_path}')
        lines.append('```')
        lines.append('![违章截图](/get_violation_image?image_path={})'.format(normalized_path))
    else:
        lines.append('- 本条记录未保存违章截图路径。')

    lines.append('')
    lines.append('## 五、建议处置')
    if risk_level == '高':
        lines.append('- 建议立即停止相关作业并组织现场核查，完成整改后复工。')
    elif risk_level == '中':
        lines.append('- 建议尽快安排整改与复核，并纳入班前会通报。')
    else:
        lines.append('- 建议记录在案并持续观察，必要时纳入抽查。')
    if rule_violations:
        for item in rule_violations:
            name = str(item.get('name') or '').strip()
            if name:
                lines.append(f'- 针对「{name}」立即核查整改，留存整改记录。')

    if agent_report:
        lines.append('')
        lines.append('## 六、智能分析报告')
        lines.append('')
        lines.append(str(agent_report).rstrip())

    lines.append('')
    lines.append('## 七、附录：原始数据')
    if getattr(violation, 'warnings_json', None):
        lines.append('### 1. 告警摘要 JSON')
        lines.append('')
        lines.append('```json')
        lines.append(str(violation.warnings_json))
        lines.append('```')
    if getattr(violation, 'detections_json', None):
        lines.append('')
        lines.append('### 2. 检测结果 JSON')
        lines.append('')
        lines.append('```json')
        lines.append(str(violation.detections_json))
        lines.append('```')
    return '\n'.join(lines)


@router.get(
    '/my_sites',
    response_model=list[SiteOut],
    summary='Get all accessible sites',
    description='Return a list of sites the user has access to.',
)
async def get_my_sites(
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> list[SiteOut]:
    """
    Retrieve all sites accessible by the currently logged-in user.

    Args:
        db (AsyncSession): The SQLAlchemy async session.
        credentials (JwtAuthorizationCredentials): The JWT credentials from
            the request.

    Returns:
        list[dict]: A list of dictionaries containing the site's ID, name,
            creation timestamp, and update timestamp.

    Raises:
        HTTPException: If the token is invalid (401) or the user is not found
            (404).
    """
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    stmt_user = (
        select(User)
        .where(User.username == username)
        .options(selectinload(User.sites))
    )
    result_user = await db.execute(stmt_user)
    user_obj: User | None = result_user.scalar()
    if not user_obj:
        raise HTTPException(status_code=404, detail='User not found')

    return [
        SiteOut(
            id=s.id,
            name=s.name,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in user_obj.sites
    ]


@router.get(
    '/violations/intent',
    response_model=ViolationsIntent,
    summary='Parse natural language query into search intent',
)
async def get_violations_intent(
    user_query: str = Query(..., min_length=1),
    default_site_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> ViolationsIntent:
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    stmt_user = (
        select(User)
        .where(User.username == username)
        .options(selectinload(User.sites))
    )
    result_user = await db.execute(stmt_user)
    user_obj: User | None = result_user.scalar()
    if not user_obj:
        raise HTTPException(status_code=404, detail='User not found')

    sites: list[Site] = list(user_obj.sites or [])
    if not sites:
        return ViolationsIntent(
            site_ids=[],
            site_names=[],
            keyword=None,
            start_time=None,
            end_time=None,
            query_mode='search',
            confidence=0.0,
        )

    allowed_ids: dict[int, Site] = {int(s.id): s for s in sites}

    intent = await _parse_intent_with_llm(user_query, sites)
    if not isinstance(intent, dict):
        intent = _fallback_intent_by_sites(user_query, sites)

    selected_ids: list[int] = []

    raw_site_ids = intent.get('site_ids')
    if isinstance(raw_site_ids, list):
        for v in raw_site_ids:
            try:
                sid = int(v)
            except Exception:
                continue
            if sid in allowed_ids and sid not in selected_ids:
                selected_ids.append(sid)

    raw_site_names = intent.get('site_names')
    if isinstance(raw_site_names, list) and len(selected_ids) == 0:
        for raw_name in raw_site_names:
            name = str(raw_name or '').strip()
            if not name:
                continue
            lower = name.lower()
            for site in sites:
                site_name = str(site.name or '').strip()
                if not site_name:
                    continue
                site_lower = site_name.lower()
                if lower == site_lower or lower in site_lower or site_lower in lower:
                    sid = int(site.id)
                    if sid in allowed_ids and sid not in selected_ids:
                        selected_ids.append(sid)

    if default_site_id is not None and int(default_site_id) in allowed_ids and not selected_ids:
        selected_ids.append(int(default_site_id))

    keyword = intent.get('keyword')
    if isinstance(keyword, str):
        keyword = keyword.strip()
        if not keyword:
            keyword = None
    else:
        keyword = None

    start_time = _parse_iso_datetime(intent.get('start_time'))
    end_time = _parse_iso_datetime(intent.get('end_time'))

    query_mode = str(intent.get('query_mode') or 'search').strip().lower()
    if query_mode != 'search':
        query_mode = 'search'

    confidence = intent.get('confidence')
    if isinstance(confidence, (int, float)):
        confidence = float(confidence)
        if confidence < 0 or confidence > 1:
            confidence = None
    else:
        confidence = None

    return ViolationsIntent(
        site_ids=selected_ids,
        site_names=[allowed_ids[sid].name for sid in selected_ids if sid in allowed_ids],
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        query_mode=query_mode,
        confidence=confidence,
    )


@router.get(
    '/segments',
    summary='Search precomputed video segments for demo',
)
async def get_segments(
    keyword: str | None = None,
    start_sec: float | None = Query(None, ge=0.0),
    end_sec: float | None = Query(None, ge=0.0),
    ranges: list[str] | None = Query(None, alias='range'),
) -> list[dict]:
    duration = _segments_duration_sec()
    time_ranges = _parse_sec_ranges_from_strings(ranges, duration_sec=duration)
    matches = _filter_segments(
        keyword=keyword,
        start_sec=start_sec,
        end_sec=end_sec,
        time_ranges=time_ranges if time_ranges else None,
    )
    items: list[dict] = []
    for seg in matches:
        rel_path = str(seg.get('image_path') or '').strip()
        seg_out = dict(seg)
        seg_out['image_url'] = (
            f'/segments/image?image_path={rel_path}'
            if rel_path
            else ''
        )
        seg_out['video_url'] = '/segments/video'
        items.append(seg_out)
    return items


@router.get(
    '/segments/clips',
    summary='Search merged video clips for demo',
)
async def get_segments_clips(
    keyword: str | None = None,
    start_sec: float | None = Query(None, ge=0.0),
    end_sec: float | None = Query(None, ge=0.0),
    ranges: list[str] | None = Query(None, alias='range'),
    merge_gap_sec: float = Query(0.2, ge=0.0, le=5.0),
    max_clips: int = Query(10, gt=0, le=50),
) -> list[dict]:
    duration = _segments_duration_sec()
    time_ranges = _parse_sec_ranges_from_strings(ranges, duration_sec=duration)
    matches = _filter_segments(
        keyword=keyword,
        start_sec=start_sec,
        end_sec=end_sec,
        time_ranges=time_ranges if time_ranges else None,
    )
    clips = _merge_segments_to_clips(matches, merge_gap_sec=merge_gap_sec)
    items: list[dict] = []
    for clip in clips[: int(max_clips)]:
        rel_path = str(clip.get('thumbnail_path') or '').strip()
        out = dict(clip)
        out['thumbnail_url'] = (
            f'/segments/image?image_path={rel_path}'
            if rel_path
            else ''
        )
        out['video_url'] = '/segments/video'
        items.append(out)
    return items


@router.get(
    '/segments/intent',
    summary='Parse natural language query into segment search intent',
)
async def get_segments_intent(
    user_query: str = Query(..., min_length=1),
) -> dict:
    return _parse_segments_intent(user_query)


@router.get(
    '/segments/image',
    summary='Get segment image',
)
async def get_segment_image(
    image_path: str = Query(..., min_length=1),
) -> Response:
    safe_rel_path = _normalize_safe_rel_path(image_path, path_cls=Path)
    base_dir: Path = _DEMO_STATIC_DIR.resolve()
    full_path: Path = _resolve_and_authorize(
        base_dir,
        safe_rel_path,
        'anonymous',
        path_cls=Path,
    )
    if not full_path.exists():
        raise HTTPException(status_code=404, detail='Image not found')
    media_type: str = _determine_media_type(full_path)
    return FileResponse(
        path=full_path,
        media_type=media_type,
        headers={
            'Content-Disposition': (
                f'inline; filename="{secure_filename(full_path.name)}"'
            ),
        },
    )


@router.get(
    '/segments/video',
    summary='Get demo video file (test3.mp4)',
)
async def get_segments_video() -> Response:
    full_path = _TEST3_VIDEO_PATH.resolve()
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail='Video not found')
    return FileResponse(
        path=full_path,
        media_type='video/mp4',
        headers={
            'Content-Disposition': (
                f'inline; filename="{secure_filename(full_path.name)}"'
            ),
        },
    )


@router.get(
    '/violations',
    response_model=ViolationList,
    summary='Get paginated violation records',
    description='Supports filtering by site_id, keyword, and time range.',
)
async def get_violations(
    site_id: int | None = None,
    keyword: str | None = None,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    limit: int = Query(
        20, gt=0, le=100, description='Records per page (1-100)',
    ),
    offset: int = Query(0, ge=0, description='Starting record offset'),
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> ViolationList:
    """
    Retrieve a paginated list of violation records.

    Args:
        site_id (int | None): The ID of the site to filter violations by.
        keyword (str | None): A keyword to search for in violation records.
        start_time (datetime | None): The start of the detection time range.
        end_time (datetime | None): The end of the detection time range.
        limit (int): The maximum number of records to return (default is 20).
        offset (int): The starting record offset (default is 0).
        db (AsyncSession): The SQLAlchemy async session.
        credentials (JwtAuthorizationCredentials):
            The JWT credentials from the request.

    Returns:
        ViolationList: A dictionary with:
            - 'total': the total count of matching violations,
            - 'items': a list of violation records (paginated).

    Raises:
        HTTPException: If the token is invalid (401), if the user is not found
            (404), if the user lacks access to the site (403), or if any other
            error occurs.
    """
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    # Retrieve user sites using the cache
    site_names: list[str] = await get_user_sites_cached(username, db)
    if not site_names:
        return ViolationList(total=0, items=[])

    conditions: list = [Violation.site.in_(site_names)]

    if site_id is not None:
        site_stmt = select(Site).where(Site.id == site_id)
        site_obj: Site | None = (await db.execute(site_stmt)).scalar()
        if not site_obj or site_obj.name not in site_names:
            raise HTTPException(status_code=403, detail='No access to site_id')
        conditions.append(Violation.site == site_obj.name)

    if keyword:
        util = _get_search_util()
        if util:
            synonyms: list[str] = util.expand_synonyms(keyword)
        else:
            synonyms = [p for p in re.split(r'\s+', keyword.strip()) if p] or [keyword]
        or_list: list = []
        for syn in synonyms:
            or_list.append(Violation.stream_name.ilike(f"%{syn}%"))
            or_list.append(Violation.warnings_json.ilike(f"%{syn}%"))
            or_list.append(Violation.agent_report.ilike(f"%{syn}%"))
        if or_list:
            conditions.append(or_(*or_list))

    if start_time:
        conditions.append(Violation.detection_time >= start_time)
    if end_time:
        conditions.append(Violation.detection_time <= end_time)

    count_task = db.execute(
        select(func.count())
        .select_from(Violation)
        .where(and_(*conditions)),
    )

    violations_task = db.scalars(
        select(Violation)
        .where(and_(*conditions))
        .order_by(Violation.detection_time.desc())
        .offset(offset)
        .limit(limit),
    )

    total_result = await count_task
    violations_result = await violations_task

    total: int = total_result.scalar()
    violations: list[Violation] = violations_result.all()

    # Construct response items in batch
    items: list[ViolationItem] = [
        ViolationItem(
            id=v.id,
            site_name=v.site,
            stream_name=v.stream_name,
            detection_time=v.detection_time,
            image_path=v.image_path,
            created_at=v.created_at,
            detection_items=v.detections_json,
            warnings=v.warnings_json,
            cone_polygons=v.cone_polygon_json,
            pole_polygons=v.pole_polygon_json,
            agent_report=_get_agent_report_for_violation(v),
        )
        for v in violations
    ]

    return ViolationList(total=total, items=items)


@router.get(
    '/violations/summary',
    response_model=ViolationsSummary,
    summary='Summarise violation search results with optional LLM',
)
async def get_violations_summary(
    site_id: int | None = None,
    keyword: str | None = None,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    user_query: str | None = Query(None),
    sample_limit: int = Query(
        20, gt=1, le=50, description='Maximum number of sample violations',
    ),
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> ViolationsSummary:
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')
    site_names: list[str] = await get_user_sites_cached(username, db)
    if not site_names:
        return ViolationsSummary(summary='当前账号没有可访问的工地，因此没有违章记录用于总结。', total=0, sample_count=0)
    conditions: list = [Violation.site.in_(site_names)]
    if site_id is not None:
        site_stmt = select(Site).where(Site.id == site_id)
        site_obj: Site | None = (await db.execute(site_stmt)).scalar()
        if not site_obj or site_obj.name not in site_names:
            raise HTTPException(status_code=403, detail='No access to site_id')
        conditions.append(Violation.site == site_obj.name)
    if keyword:
        util = _get_search_util()
        if util:
            synonyms: list[str] = util.expand_synonyms(keyword)
        else:
            synonyms = [p for p in re.split(r'\s+', keyword.strip()) if p] or [keyword]
        or_list: list = []
        for syn in synonyms:
            or_list.append(Violation.stream_name.ilike(f'%{syn}%'))
            or_list.append(Violation.warnings_json.ilike(f'%{syn}%'))
            or_list.append(Violation.agent_report.ilike(f'%{syn}%'))
        if or_list:
            conditions.append(or_(*or_list))
    if start_time:
        conditions.append(Violation.detection_time >= start_time)
    if end_time:
        conditions.append(Violation.detection_time <= end_time)
    count_stmt = select(func.count()).select_from(Violation).where(and_(*conditions))
    samples_stmt = (
        select(Violation)
        .where(and_(*conditions))
        .order_by(Violation.detection_time.desc())
        .limit(sample_limit)
    )
    total_result = await db.execute(count_stmt)
    samples_result = await db.execute(samples_stmt)
    total: int = total_result.scalar() or 0
    rows = samples_result.scalars().all()
    samples: list[Violation] = list(rows)
    summary_text = await _summarise_with_llm(user_query, total, samples)
    if not summary_text:
        summary_text = _build_default_summary(user_query, total, samples)
    return ViolationsSummary(
        summary=summary_text,
        total=total,
        sample_count=len(samples),
    )


@router.get(
    '/violations/{violation_id}',
    response_model=ViolationItem,
    summary='Get single violation details',
    description='Retrieve a single violation record by its ID.',
)
async def get_single_violation(
    violation_id: int,
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> dict:
    """
    Retrieve detailed information for a specific violation record.

    Args:
        violation_id (int):
            The ID of the violation to retrieve.
        db (AsyncSession):
            The SQLAlchemy async session.
        credentials (JwtAuthorizationCredentials):
            The JWT credentials from the request.

    Returns:
        dict: A dictionary containing details of the violation, including:
            - 'id': The ID of the violation.
            - 'site_name': The name of the site.
            - 'stream_name': The name of the stream.
            - 'detection_time': The time of detection.
            - 'image_path': The path to the image.
            - 'created_at': The creation timestamp.
            - 'detection_items': JSON string with detection items.
            - 'warnings': JSON string with warnings.
            - 'cone_polygons': JSON string with cone polygons.
            - 'pole_polygons': JSON string with pole polygons.

    Raises:
        HTTPException: If the token is invalid (401), if the user is not found
            (404), if the user lacks access to the violation's site (403), or
            if the violation ID does not exist (404).
    """
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    # Retrieve user sites using the cache
    site_names: list[str] = await get_user_sites_cached(username, db)

    stmt_violation = select(Violation).where(Violation.id == violation_id)
    violation: Violation | None = (await db.execute(stmt_violation)).scalar()

    if not violation or violation.site not in site_names:
        print(
            f"[get_single_violation] No access to violation_id {violation_id}",
        )
        raise HTTPException(
            status_code=403, detail='No access to this violation',
        )

    return ViolationItem(
        id=violation.id,
        site_name=violation.site,
        stream_name=violation.stream_name,
        detection_time=violation.detection_time,
        image_path=violation.image_path,
        created_at=violation.created_at,
        detection_items=violation.detections_json,
        warnings=violation.warnings_json,
        cone_polygons=violation.cone_polygon_json,
        pole_polygons=violation.pole_polygon_json,
        agent_report=_get_agent_report_for_violation(violation),
    )


@router.get(
    '/get_violation_image',
    summary='Get a violation image file',
    description="Retrieve an image file from the 'static' directory.",
)
async def get_violation_image(
    image_path: str,
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> FileResponse:
    """
    Retrieve a violation image file from the "static" directory.

    Args:
        image_path (str): The relative path of the image within the "static"
            directory.
        credentials (JwtAuthorizationCredentials): The JWT credentials from the
            request.

    Returns:
        FileResponse: The requested image file with inline Content-Disposition.

    Raises:
        HTTPException: If the token is invalid (401), if the path contains '..'
            (400), if the path is outside "static" (403), or if the file is not
            found (404).
    """
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    # Normalize and authorize path
    safe_rel_path = _normalize_safe_rel_path(image_path, path_cls=Path)
    base_dir: Path = Path(STATIC_DIR).resolve()
    full_path: Path = _resolve_and_authorize(
        base_dir, safe_rel_path, username, path_cls=Path,
    )

    if not full_path.exists():
        raise HTTPException(status_code=404, detail='Image not found')

    media_type: str = _determine_media_type(full_path)

    return FileResponse(
        path=full_path,
        media_type=media_type,
        headers={
            'Content-Disposition': (
                f'inline; filename="{secure_filename(full_path.name)}"'
            ),
        },
    )


@router.post(
    '/upload',
    response_model=UploadViolationResponse,
    summary='Upload a new violation record',
    description='Upload a violation image and associated metadata.',
)
async def upload_violation(
    site: str = Form(...),
    stream_name: str = Form(...),
    detection_time: datetime | None = Form(None),
    warnings_json: str | None = Form(None),
    detections_json: str | None = Form(None),
    cone_polygon_json: str | None = Form(None),
    pole_polygon_json: str | None = Form(None),
    agent_report: str | None = Form(None),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
) -> dict:
    """
    Upload a new violation record, including an image and associated metadata.

    Args:
        site (str):
            The name of the site where the violation occurred.
        stream_name (str):
            The name of the video stream or camera.
        detection_time (datetime | None):
            The detection time; defaults to UTC now.
        warnings_json (str | None):
            JSON string describing warnings.
        detections_json (str | None):
            JSON string describing detected items.
        cone_polygon_json (str | None):
            JSON string with cone polygon data.
        pole_polygon_json (str | None):
            JSON string with pole polygon data.
        image (UploadFile):
            The violation image file.
        db (AsyncSession):
            The SQLAlchemy async session.
        credentials (JwtAuthorizationCredentials):
            The JWT credentials.

    Returns:
        dict: A dictionary containing a success message and the violation ID.

    Raises:
        HTTPException: If the token is invalid (401), if the user has no access
            to the site (403), or if any error occurs during file reading or
            database operations (400, 500).
    """
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    site_stmt = await db.execute(
        select(Site)
        .join(User.sites)
        .where(User.username == username, Site.name == site),
    )
    site_obj: Site | None = site_stmt.scalar()
    if not site_obj:
        print(f"[upload_violation] No access to site {site}")
        raise HTTPException(status_code=403, detail='No access to this site')

    detection_time = detection_time or datetime.now(timezone.utc)

    try:
        image_bytes: bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail='Empty image file')
    except Exception as exc:
        logging.error(f"[upload_violation] read error: {exc}")
        raise HTTPException(
            status_code=400, detail='Failed to read image file',
        )

    violation_id: int | None = await violation_manager.save_violation(
        db=db,
        site=site,
        stream_name=stream_name,
        detection_time=detection_time,
        image_bytes=image_bytes,
        warnings_json=warnings_json,
        detections_json=detections_json,
        cone_polygon_json=cone_polygon_json,
        pole_polygon_json=pole_polygon_json,
        agent_report=agent_report,
    )
    if not violation_id:
        raise HTTPException(
            status_code=500, detail='Failed to create violation record',
        )

    return UploadViolationResponse(
        message='Violation uploaded successfully.',
        violation_id=violation_id,
    )


@router.get(
    '/violations/{violation_id}/export',
    summary='Export a structured violation report file',
    description='Export a structured safety warning report for a single violation.',
)
async def export_violation_report(
    violation_id: int,
    format: str = Query(
        'markdown',
        pattern='^(markdown|md|txt|json)$',
        description='Export format: markdown (default), txt, or json.',
    ),
    db: AsyncSession = Depends(get_db),
    credentials: JwtAuthorizationCredentials = Security(jwt_access),
):
    username: str | None = credentials.subject.get('username')
    if not username:
        raise HTTPException(status_code=401, detail='Invalid token')

    site_names: list[str] = await get_user_sites_cached(username, db)

    stmt_violation = select(Violation).where(Violation.id == violation_id)
    violation: Violation | None = (await db.execute(stmt_violation)).scalar()

    if not violation or violation.site not in site_names:
        raise HTTPException(
            status_code=403, detail='No access to this violation',
        )

    rule_violations = _map_rule_violations_from_warnings(
        violation.warnings_json,
    )
    risk_level = _calculate_risk_level(rule_violations)
    agent_report = _get_agent_report_for_violation(violation)

    export_data = {
        'id': violation.id,
        'site_name': violation.site,
        'stream_name': violation.stream_name,
        'detection_time': (
            violation.detection_time.isoformat()
            if violation.detection_time
            else None
        ),
        'created_at': (
            violation.created_at.isoformat()
            if violation.created_at
            else None
        ),
        'image_path': violation.image_path,
        'risk_level': risk_level,
        'rule_violations': rule_violations,
        'warnings_json': violation.warnings_json,
        'detections_json': violation.detections_json,
        'agent_report': agent_report,
    }

    fmt = (format or 'markdown').strip().lower()
    if fmt == 'json':
        return JSONResponse(content=export_data)

    filename_suffix = 'md' if fmt in ('markdown', 'md') else 'txt'
    filename = f'violation-report-{violation_id}.{filename_suffix}'

    markdown_body = _build_markdown_report(
        violation=violation,
        rule_violations=rule_violations,
        risk_level=risk_level,
        image_path=violation.image_path,
    )

    media_type = (
        'text/markdown; charset=utf-8'
        if fmt in ('markdown', 'md')
        else 'text/plain; charset=utf-8'
    )

    return Response(
        content=markdown_body,
        media_type=media_type,
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
        },
    )
