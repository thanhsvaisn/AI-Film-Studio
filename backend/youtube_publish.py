"""Resumable YouTube uploads; one upload record per project and destination channel."""
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import store, youtube

CHUNK = 16 * 1024 * 1024
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='youtube-upload')
lock = threading.RLock()
running = set()


def video_path(project_id):
    return store.ROOT / project_id / 'output' / 'video.mp4'


def thumbnail_path(project_id, channel_id):
    return store.ROOT / project_id / 'youtube' / f'{channel_id}.thumb'


def _save(record, **changes):
    with lock:
        record.update(changes)
        store.save_upload(record)


def _error(response):
    try:
        detail = response.json().get('error', {}).get('message', '')
    except (ValueError, AttributeError):
        detail = ''
    raise ValueError(f'YouTube API HTTP {response.status_code}: {detail[:200]}')


def _session_valid(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'www.googleapis.com' or parsed.path != '/upload/youtube/v3/videos':
        raise ValueError('Phiên tải lên YouTube không hợp lệ.')
    return url


def _position(response):
    value = response.headers.get('Range', '')
    match = re.fullmatch(r'bytes=0-(\d+)', value)
    return int(match.group(1)) + 1 if match else 0


def _metadata(record, locale):
    seo = record['seo']
    return {'snippet': {'title': seo['title'], 'description': seo['description'],
                        'tags': seo['tags'], 'categoryId': seo['category_id'],
                        'defaultLanguage': locale.split('-')[0]},
            'status': {'privacyStatus': seo['privacy'],
                       'selfDeclaredMadeForKids': seo['made_for_kids'],
                       'containsSyntheticMedia': seo['synthetic_media']}}


def _start_session(client, token, record, locale, size):
    response = client.post('https://www.googleapis.com/upload/youtube/v3/videos',
                           params={'uploadType': 'resumable', 'part': 'snippet,status'},
                           json=_metadata(record, locale),
                           headers={'Authorization': f'Bearer {token}',
                                    'X-Upload-Content-Length': str(size),
                                    'X-Upload-Content-Type': 'video/mp4',
                                    'Content-Type': 'application/json; charset=UTF-8'})
    if response.status_code != 200:
        _error(response)
    session = _session_valid(response.headers.get('Location', ''))
    _save(record, session_uri=session, uploaded_bytes=0, status='uploading')
    return session


def _probe(client, token, session, size):
    response = client.put(session, content=b'', headers={
        'Authorization': f'Bearer {token}', 'Content-Range': f'bytes */{size}',
        'Content-Length': '0'})
    if response.status_code == 308:
        return _position(response), None
    if response.status_code in (200, 201):
        return size, response.json().get('id')
    if response.status_code == 404:
        raise ValueError('Phiên tải lên đã hết hạn. Kiểm tra kênh trước khi tạo lại phiên.')
    _error(response)


def _upload_video(client, token, record, locale, path):
    size = path.stat().st_size
    session = record.get('session_uri')
    if session:
        session = _session_valid(session)
        position, video_id = _probe(client, token, session, size)
        if video_id:
            return video_id
    else:
        session = _start_session(client, token, record, locale, size)
        position = 0
    with path.open('rb') as source:
        while position < size:
            source.seek(position)
            data = source.read(min(CHUNK, size - position))
            if not data:
                raise ValueError('Không đọc được video đã xuất.')
            last = position + len(data) - 1
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'video/mp4',
                       'Content-Range': f'bytes {position}-{last}/{size}'}
            for attempt in range(4):
                try:
                    response = client.put(session, content=data, headers=headers)
                    if response.status_code == 308:
                        new_position = _position(response)
                        if new_position <= position:
                            raise ValueError('YouTube không xác nhận phần dữ liệu vừa tải.')
                        position = new_position
                        _save(record, uploaded_bytes=position, progress=round(100 * position / size, 1))
                        break
                    if response.status_code in (200, 201):
                        video_id = response.json().get('id')
                        if not video_id:
                            raise ValueError('YouTube không trả về mã video.')
                        return video_id
                    if response.status_code == 401:
                        token = youtube.access_token(record['youtube_channel_id'])
                        headers['Authorization'] = f'Bearer {token}'
                        continue
                    if response.status_code not in (500, 502, 503, 504):
                        _error(response)
                except httpx.HTTPError:
                    pass
                if attempt == 3:
                    raise ValueError('Đường truyền proxy/YouTube bị gián đoạn nhiều lần. Có thể bấm thử lại.')
                position, video_id = _probe(client, token, session, size)
                if video_id:
                    return video_id
                if position > last:
                    _save(record, uploaded_bytes=position, progress=round(100 * position / size, 1))
                    break
                source.seek(position)
                data = source.read(min(CHUNK, size - position))
                last = position + len(data) - 1
                headers['Content-Range'] = f'bytes {position}-{last}/{size}'
            else:
                raise ValueError('Không thể tiếp tục tải video lên YouTube.')
    position, video_id = _probe(client, token, session, size)
    if video_id:
        return video_id
    raise ValueError(f'YouTube mới nhận {position}/{size} byte, chưa hoàn tất.')


def _set_thumbnail(client, token, record):
    path = thumbnail_path(record['project_id'], record['channel_id'])
    if not path.is_file():
        return
    data = path.read_bytes()
    mime = 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
    response = client.post('https://www.googleapis.com/upload/youtube/v3/thumbnails/set',
                           params={'videoId': record['youtube_video_id']}, content=data,
                           headers={'Authorization': f'Bearer {token}', 'Content-Type': mime})
    if response.status_code != 200:
        _error(response)


def _run(project_id, channel_id):
    try:
        record = store.get_upload(project_id, channel_id)
        channel = next(c for c in store.all_channels() if c['id'] == channel_id)
        project = store.get(project_id)
        yt_id = channel['youtube_channel_id']
        proxy = youtube.proxy_for(yt_id)
        token = youtube.access_token(yt_id)
        with httpx.Client(proxy=proxy, timeout=300, follow_redirects=False) as client:
            own = youtube.mine(token, proxy)
            if yt_id not in {c['id'] for c in own}:
                raise ValueError('Tài khoản Google không còn quản lý kênh đã chọn.')
            if record.get('youtube_video_id'):
                video_id = record['youtube_video_id']
            else:
                video_id = _upload_video(client, token, record, project['locale'], video_path(project_id))
                _save(record, youtube_video_id=video_id, progress=100, status='setting_thumbnail')
            if thumbnail_path(project_id, channel_id).is_file():
                token = youtube.access_token(yt_id)
            _set_thumbnail(client, token, record)
        _save(record, status='uploaded', error=None, session_uri=None, progress=100)
    except Exception as exc:
        record = store.get_upload(project_id, channel_id)
        message = ('Không kết nối được proxy hoặc YouTube. Kiểm tra proxy rồi thử lại.'
                   if isinstance(exc, httpx.HTTPError) else str(exc))
        _save(record, status='failed', error=message[:500])
    finally:
        with lock:
            running.discard((project_id, channel_id))


def enqueue(project_id, channel_id):
    key = (project_id, channel_id)
    with lock:
        if key in running:
            return False
        running.add(key)
    executor.submit(_run, project_id, channel_id)
    return True
