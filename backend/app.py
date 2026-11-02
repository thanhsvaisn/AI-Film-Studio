import shutil
import uuid
import csv
import io
import json
from datetime import date, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator
from . import store, media, worker, youtube, youtube_publish
from .providers import readiness
from .subtitles import parse_srt, validate, timeline_manifest
from .translation import model_ready
from .locales import LOCALES


@asynccontextmanager
async def lifespan(app):
    for p in store.all_projects():
        if p['status'] in worker.ACTIVE:
            p.update(status='paused', error='Ứng dụng đã dừng; đang tự tiếp tục.')
            store.save(p)
            worker.enqueue(p['id'])
    for upload in store.all_uploads():
        if upload.get('status') in ('uploading', 'setting_thumbnail'):
            youtube_publish.enqueue(upload['project_id'], upload['channel_id'])
    yield


app = FastAPI(title='AI Film Studio', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])


@app.middleware('http')
async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        return JSONResponse({'detail': 'Origin không được phép.'}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


def project(identifier):
    try:
        return store.get(identifier)
    except KeyError:
        raise HTTPException(404, 'Không tìm thấy dự án.')


@app.get('/api/health')
def health():
    return dict(ffmpeg=bool(shutil.which('ffmpeg')), ffprobe=bool(shutil.which('ffprobe')),
                tts=readiness(), disk_free_bytes=shutil.disk_usage(store.ROOT).free,
                delivery_root=str(store.ROOT / 'deliveries'),
                translation=dict(installed=model_ready(),
                                 source='zh', target='vi-VN', paid_api=False),
                locales=[{'id': key, 'country': value[0]} for key, value in LOCALES.items()],
                paid_api=False, stage=1)


@app.post('/api/voices/default/{locale}/preview')
def create_default_voice_preview(locale: str):
    if locale not in LOCALES:
        raise HTTPException(404, 'Ngôn ngữ giọng mặc định không được hỗ trợ.')
    if not all(readiness()[key] for key in ('installed', 'model_ready')):
        raise ValueError('VoxCPM2 chưa sẵn sàng để tạo giọng thử.')
    existed = (store.ROOT / ('default_voice.wav' if locale == 'vi-VN' else f'default_voice_{locale}.wav')).is_file()
    path = worker.default_voice_path(locale)
    return {'locale': locale, 'cached': existed, 'audio_url': f'/api/voices/default/{locale}/preview.wav'}


@app.get('/api/voices/default/{locale}/preview.wav')
def get_default_voice_preview(locale: str):
    if locale not in LOCALES:
        raise HTTPException(404, 'Ngôn ngữ giọng mặc định không được hỗ trợ.')
    path = store.ROOT / ('default_voice.wav' if locale == 'vi-VN' else f'default_voice_{locale}.wav')
    if not path.is_file():
        raise HTTPException(404, 'Chưa tạo giọng thử cho ngôn ngữ này.')
    return FileResponse(path, media_type='audio/wav')


@app.get('/api/voices/designs')
def list_voice_designs():
    return [{'locale': code, 'language': country, 'preset_id': preset_id, 'name': definition[0],
             'model': 'VoxCPM2',
             'description': definition[1], 'kind': 'model_generated_voice_design'}
            for code, (country, _) in LOCALES.items()
            for preset_id, definition in worker.VOICE_DESIGNS.items()]


@app.post('/api/voices/design/{locale}/{preset_id}/preview')
def create_voice_design_preview(locale: str, preset_id: str):
    if locale not in LOCALES or preset_id not in worker.VOICE_DESIGNS:
        raise HTTPException(404, 'Mẫu giọng không được hỗ trợ.')
    if not all(readiness()[key] for key in ('installed', 'model_ready')):
        raise ValueError('VoxCPM2 chưa sẵn sàng để tạo giọng thử.')
    path = store.ROOT / 'designed_voices' / locale / f'{preset_id}_preview3.wav'
    cached = path.is_file()
    worker.designed_voice_path(locale, preset_id)
    return {'locale': locale, 'preset_id': preset_id, 'cached': cached,
            'audio_url': f'/api/voices/design/{locale}/{preset_id}/preview.wav'}


@app.get('/api/voices/design/{locale}/{preset_id}/preview.wav')
def get_voice_design_preview(locale: str, preset_id: str):
    if locale not in LOCALES or preset_id not in worker.VOICE_DESIGNS:
        raise HTTPException(404, 'Mẫu giọng không được hỗ trợ.')
    path = store.ROOT / 'designed_voices' / locale / f'{preset_id}_preview3.wav'
    if not path.is_file():
        raise HTTPException(404, 'Mẫu này chưa được tạo. Hãy bấm Tạo & nghe thử.')
    return FileResponse(path, media_type='audio/wav')


@app.get('/api/projects')
def projects():
    return [{k: v for k, v in p.items() if k != 'segments'} for p in store.all_projects()]


@app.get('/api/batches/{batch_id}/report.csv')
def batch_report(batch_id: str):
    rows = [p for p in store.all_projects() if p.get('batch_id') == batch_id]
    if not rows:
        raise HTTPException(404, 'Không tìm thấy lô.')
    output = io.StringIO(newline='')
    columns = ['video', 'locale', 'channels', 'status', 'progress', 'srt_kind',
               'voice', 'warnings', 'error', 'delivery_folder']
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
    for p in rows:
        report = p.get('report') or {}
        writer.writerow({key: safe(value) for key, value in dict(video=p.get('source_filename') or p['name'],
                             locale=p['locale'], channels=';'.join(p.get('channel_ids', [])),
                             status=p['status'], progress=p.get('progress', 0),
                             srt_kind=p.get('srt_kind', ''), voice=p.get('voice', ''),
                             warnings='; '.join(p.get('warnings', [])),
                             error=p.get('error') or '',
                             delivery_folder=report.get('delivery_folder', '')).items()})
    return Response('\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="batch-{batch_id}.csv"'})


@app.get('/api/projects/{identifier}')
def read_project(identifier: str):
    return project(identifier)


def copy_upload(upload, target, maximum):
    total = 0
    with target.open('wb') as out:
        while data := upload.file.read(1024 * 1024):
            total += len(data)
            if total > maximum:
                raise ValueError('Tệp vượt giới hạn dung lượng.')
            out.write(data)


@app.post('/api/projects', status_code=201)
def create(name: str = Form(...), locale: str = Form(...),
           video: UploadFile = File(...), subtitles: UploadFile = File(...),
           audio_mode: Literal['approved', 'voxcpm'] = Form('voxcpm'),
           audio: UploadFile | None = File(None), confirmed: bool = Form(False),
           batch_id: str | None = Form(None), source_filename: str | None = Form(None),
           channel_ids: str = Form('[]'), srt_kind: Literal['auto','source_zh','translated'] = Form('auto')):
    if locale not in LOCALES:
        raise ValueError('Ngôn ngữ đầu ra chưa được hỗ trợ.')
    if audio_mode == 'voxcpm' and not all(readiness()[k] for k in ('installed', 'model_ready')):
        raise ValueError('Cần cài VoxCPM2 và mô hình cục bộ trước khi chạy tự động.')
    if audio_mode == 'approved' and audio is None:
        raise ValueError('Cần WAV đã đồng bộ nếu chọn nguồn âm thanh này.')
    if audio_mode == 'voxcpm' and audio is not None and not confirmed:
        raise ValueError('Cần xác nhận quyền sử dụng mẫu giọng riêng.')
    if not name.strip() or len(name) > 150:
        raise ValueError('Tên dự án cần từ 1–150 ký tự.')
    if batch_id and (len(batch_id) != 36 or not all(c in '0123456789abcdef-' for c in batch_id.lower())):
        raise ValueError('Mã lô không hợp lệ.')
    try:
        selected_ids = __import__('json').loads(channel_ids)
    except ValueError:
        raise ValueError('Danh sách kênh không hợp lệ.')
    if not isinstance(selected_ids, list) or not selected_ids or len(selected_ids) > 100 or any(not isinstance(x, str) for x in selected_ids):
        raise ValueError('Danh sách kênh không hợp lệ.')
    known = {c['id']: c for c in store.all_channels()}
    if any(identifier not in known or not known[identifier].get('youtube_channel_id') or
           not known[identifier].get('configured') or
           known[identifier]['locale'] != locale or known[identifier]['voice'] != 'default' for identifier in selected_ids):
        raise ValueError('Phải chọn kênh YouTube đã kết nối và cấu hình đúng ngôn ngữ, giọng.')
    if any(not youtube.has_refresh_token(known[identifier]['youtube_channel_id']) for identifier in selected_ids):
        raise ValueError('Kênh YouTube đã mất kết nối. Hãy kết nối lại trước khi chạy.')
    source_filename = (source_filename or video.filename or '').replace('\\', '/')
    if not source_filename or len(source_filename) > 500 or '..' in source_filename.split('/'):
        raise ValueError('Tên tệp nguồn không hợp lệ.')
    if batch_id:
        for existing in store.all_projects():
            if (existing.get('batch_id') == batch_id and existing.get('source_filename') == source_filename
                    and existing.get('locale') == locale and existing.get('audio_mode') == audio_mode
                    and existing.get('channel_ids', []) == selected_ids):
                return existing
    identifier = uuid.uuid4().hex
    folder = store.ROOT / identifier
    folder.mkdir()
    try:
        copy_upload(video, folder / 'source.mp4', 100 * 1024**3)
        duration, streams = media.probe(folder / 'source.mp4')
        if not any(s['codec_type'] == 'video' for s in streams):
            raise ValueError('Tệp không chứa video.')
        text = subtitles.file.read(5 * 1024**2 + 1)
        if len(text) > 5 * 1024**2:
            raise ValueError('SRT vượt 5 MB.')
        try:
            segments = parse_srt(text.decode('utf-8-sig'))
        except UnicodeDecodeError:
            raise ValueError('Hãy lưu SRT bằng UTF-8.')
        attention_error = None
        try:
            warnings = validate(segments, duration)
        except ValueError as exc:
            # Keep parseable uploads as a recoverable project when the video/SRT
            # pairing needs attention; never silently trim or shift cue timing.
            if 'vượt thời lượng video' not in str(exc):
                raise
            attention_error = str(exc)
            warnings = validate(segments)
        from .translation import has_chinese, model_ready
        contains_chinese = any(has_chinese(s['text']) for s in segments)
        if srt_kind == 'source_zh' and not contains_chinese:
            raise ValueError('Đã chọn SRT nguồn tiếng Trung nhưng không thấy chữ Trung. Kiểm tra lại loại SRT.')
        if srt_kind == 'translated' and contains_chinese and locale != 'ja-JP':
            raise ValueError('Đã chọn SRT dịch sẵn nhưng còn chữ Trung. Hãy chọn SRT nguồn hoặc sửa track dịch.')
        needs_translation = srt_kind == 'source_zh' or (srt_kind == 'auto' and contains_chinese and locale != 'ja-JP')
        if needs_translation and not model_ready():
            attention_error = attention_error or f'SRT nguồn tiếng Trung cần Ollama và Gemma 4 12B đang chạy để dịch sang {locale}.'
        if audio is not None:
            filename = 'approved.wav' if audio_mode == 'approved' else 'reference.wav'
            copy_upload(audio, folder / filename, 4 * 1024**3)
            audio_duration, audio_streams = media.probe(folder / filename)
            if not any(s['codec_type'] == 'audio' for s in audio_streams):
                raise ValueError('Tệp không chứa âm thanh.')
            if audio_mode == 'approved' and abs(audio_duration - duration) > .25:
                raise ValueError('WAV đã duyệt phải có cùng thời lượng video.')
            if audio_mode == 'voxcpm' and not 1 <= audio_duration <= 30:
                raise ValueError('Mẫu giọng cần dài từ 1 đến 30 giây.')
        p = dict(id=identifier, name=name.strip(), locale=locale, duration=duration,
                 segments=segments, warnings=warnings, status='needs_attention' if attention_error else 'draft', progress=0,
                 audio_mode=audio_mode, voice='uploaded' if audio_mode == 'voxcpm' and audio else 'default' if audio_mode == 'voxcpm' else 'approved',
                 revision=1, error=attention_error, paid_api=False, batch_id=batch_id,
                 source_filename=source_filename, channel_ids=selected_ids,
                 srt_kind='source_zh' if needs_translation else 'translated',
                 timeline_manifest=timeline_manifest(segments))
        (folder / 'original.srt').write_text(text.decode('utf-8-sig'), encoding='utf-8')
        store.save(p)
        if not attention_error:
            worker.enqueue(identifier)
        return store.get(identifier)
    except Exception:
        # Only this newly created UUID upload directory is removed.
        shutil.rmtree(folder)
        raise


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str


class Channel(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=80)
    locale: str
    voice: Literal['default'] = 'default'

    @field_validator('locale')
    @classmethod
    def supported_locale(cls, value):
        if value not in LOCALES:
            raise ValueError('Ngôn ngữ kênh chưa được hỗ trợ.')
        return value



@app.get('/api/channels')
def channels():
    return store.all_channels()


@app.get('/api/youtube/status')
def youtube_status(request: Request):
    return {'configured': youtube.configured(), 'connected_channels': sum(
        bool(c.get('youtube_channel_id')) for c in store.all_channels()),
        'public_api_key_configured': bool(youtube.public_api_key()),
        'redirect_uri': str(request.base_url).rstrip('/') + '/api/youtube/callback'}


@app.get('/api/youtube/lookup')
def youtube_lookup(query: str):
    return youtube.lookup_channel(query)


@app.get('/api/youtube/connect')
def youtube_connect(request: Request):
    redirect_uri = str(request.base_url).rstrip('/') + '/api/youtube/callback'
    return RedirectResponse(youtube.authorization_url(redirect_uri))


@app.get('/api/youtube/callback')
def youtube_callback(request: Request, code: str = '', state: str = '', error: str = ''):
    if error:
        raise ValueError(f'Google từ chối kết nối: {error}')
    redirect_uri = str(request.base_url).rstrip('/') + '/api/youtube/callback'
    token = youtube.exchange(code, state, redirect_uri)
    items = youtube.mine(token['access_token'])
    if not items:
        raise ValueError('Tài khoản Google này không có kênh YouTube để nhập.')
    existing = {c.get('youtube_channel_id'): c for c in store.all_channels()}
    for item in items:
        channel_id = item['id']
        old = existing.get(channel_id, {})
        snippet = item.get('snippet', {})
        channel = {'id': old.get('id', uuid.uuid4().hex),
                   'name': snippet.get('title') or channel_id,
                   'country': old.get('country') or snippet.get('country') or 'Chưa chọn',
                   'locale': old.get('locale') or 'vi-VN', 'voice': old.get('voice') or 'default',
                   'youtube_channel_id': channel_id,
                   'youtube_thumbnail': snippet.get('thumbnails', {}).get('default', {}).get('url', ''),
                   'youtube_subscribers': item.get('statistics', {}).get('subscriberCount'),
                   'configured': old.get('configured', False),
                   'upload_scope_granted': 'https://www.googleapis.com/auth/youtube.upload' in token.get('scope', '').split(),
                   'connected_at': date.today().isoformat()}
        youtube.save_refresh_token(channel_id, token['refresh_token'])
        store.save_channel(channel)
    return RedirectResponse('/?tab=channels&youtube=connected')


@app.get('/api/youtube/channels/{identifier}/analytics')
def youtube_analytics(identifier: str, days: int = 28):
    if days not in {7, 28, 90}:
        raise HTTPException(422, 'Khoảng thống kê phải là 7, 28 hoặc 90 ngày.')
    channel = next((c for c in store.all_channels() if c['id'] == identifier), None)
    if not channel or not channel.get('youtube_channel_id'):
        raise HTTPException(404, 'Kênh YouTube chưa kết nối.')
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=days - 1)
    return {'period': {'days': days, 'start': start.isoformat(), 'end': end.isoformat()},
            **youtube.analytics(channel['youtube_channel_id'], start.isoformat(), end.isoformat())}


class ProxySettings(BaseModel):
    url: str = Field(max_length=500)


@app.put('/api/youtube/channels/{identifier}/proxy')
def save_proxy(identifier: str, body: ProxySettings):
    channel = next((c for c in store.all_channels() if c['id'] == identifier), None)
    if not channel or not channel.get('youtube_channel_id'):
        raise HTTPException(404, 'Kênh YouTube chưa kết nối.')
    display = youtube.set_proxy(channel['youtube_channel_id'], body.url)
    channel.update(proxy_enabled=bool(display), proxy_display=display)
    store.save_channel(channel)
    return {'proxy_enabled': bool(display), 'proxy_display': display}


@app.post('/api/youtube/channels/{identifier}/proxy/test')
def test_proxy(identifier: str):
    channel = next((c for c in store.all_channels() if c['id'] == identifier), None)
    if not channel or not channel.get('youtube_channel_id'):
        raise HTTPException(404, 'Kênh YouTube chưa kết nối.')
    if not channel.get('proxy_enabled'):
        raise ValueError('Hãy lưu proxy cho kênh trước.')
    try:
        token = youtube.access_token(channel['youtube_channel_id'])
        items = youtube.mine(token, youtube.proxy_for(channel['youtube_channel_id']))
    except Exception:
        raise ValueError('Không kết nối được Google qua proxy này. Kiểm tra địa chỉ, tài khoản và cổng.')
    if channel['youtube_channel_id'] not in {item['id'] for item in items}:
        raise ValueError('Google không xác nhận quyền quản lý kênh qua proxy này.')
    return {'ok': True, 'channel': channel['name']}


class SeoDraft(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    category_id: str = Field(default='24', pattern=r'^\d{1,3}$')
    privacy: Literal['private', 'unlisted', 'public'] = 'private'
    made_for_kids: bool = False
    synthetic_media: bool = False

    @field_validator('description')
    @classmethod
    def description_bytes(cls, value):
        if len(value.encode('utf-8')) > 5000:
            raise ValueError('Mô tả vượt 5000 byte của YouTube.')
        return value

    @field_validator('tags')
    @classmethod
    def valid_tags(cls, value):
        if any(not tag.strip() or len(tag) > 100 for tag in value) or sum(len(x) for x in value) > 500:
            raise ValueError('Thẻ SEO vượt giới hạn.')
        return value


def upload_channel(project_id, channel_id):
    p = project(project_id)
    channel = next((c for c in store.all_channels() if c['id'] == channel_id), None)
    if not channel or channel_id not in p.get('channel_ids', []):
        raise HTTPException(404, 'Kênh không thuộc bản xuất này.')
    return p, channel


def public_upload(record):
    return {key: value for key, value in record.items() if key not in ('session_uri', 'youtube_channel_id')}


@app.get('/api/projects/{identifier}/youtube')
def project_youtube(identifier: str):
    p = project(identifier)
    channels = {c['id']: c for c in store.all_channels()}
    saved = {u['channel_id']: u for u in store.project_uploads(identifier)}
    results = []
    for channel_id in p.get('channel_ids', []):
        channel = channels.get(channel_id)
        if not channel:
            continue
        record = saved.get(channel_id) or {
            'project_id': identifier, 'channel_id': channel_id, 'status': 'draft',
            'seo': {'title': p['name'][:100], 'description': '', 'tags': [],
                    'category_id': '24', 'privacy': 'private',
                    'made_for_kids': False, 'synthetic_media': False}}
        results.append({**public_upload(record), 'channel_name': channel['name'],
                        'proxy_enabled': channel.get('proxy_enabled', False),
                        'proxy_display': channel.get('proxy_display', ''),
                        'upload_scope_granted': channel.get('upload_scope_granted', False),
                        'completed': p['status'] == 'completed'})
    return results


@app.put('/api/projects/{identifier}/youtube/{channel_id}/seo')
def save_seo(identifier: str, channel_id: str, body: SeoDraft):
    p, channel = upload_channel(identifier, channel_id)
    record = store.get_upload(identifier, channel_id) or {'project_id': identifier,
        'channel_id': channel_id, 'youtube_channel_id': channel.get('youtube_channel_id'),
        'status': 'draft', 'progress': 0}
    if record.get('youtube_video_id') or record.get('status') in ('uploading', 'setting_thumbnail', 'uploaded'):
        raise HTTPException(409, 'Video đã hoặc đang đăng. Không sửa SEO của lượt đăng này.')
    record['seo'] = body.model_dump()
    store.save_upload(record)
    return public_upload(record)


@app.post('/api/projects/{identifier}/youtube/{channel_id}/thumbnail')
def save_thumbnail(identifier: str, channel_id: str, image: UploadFile = File(...)):
    p, channel = upload_channel(identifier, channel_id)
    if p['status'] != 'completed':
        raise HTTPException(409, 'Cần bản xuất hoàn tất trước khi đặt ảnh bìa.')
    record = store.get_upload(identifier, channel_id)
    if record and record.get('status') in ('uploading', 'setting_thumbnail', 'uploaded'):
        raise HTTPException(409, 'Video đang hoặc đã đăng.')
    data = image.file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise ValueError('Ảnh bìa vượt 50 MB.')
    if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')):
        raise ValueError('Ảnh bìa phải là PNG hoặc JPEG.')
    path = youtube_publish.thumbnail_path(identifier, channel_id)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return {'saved': True, 'bytes': len(data)}


@app.post('/api/projects/{identifier}/youtube/{channel_id}/publish', status_code=202)
def publish_video(identifier: str, channel_id: str):
    p, channel = upload_channel(identifier, channel_id)
    if p['status'] != 'completed' or not youtube_publish.video_path(identifier).is_file():
        raise HTTPException(409, 'Chưa có MP4 hoàn tất để đăng.')
    if not channel.get('youtube_channel_id') or not channel.get('upload_scope_granted'):
        raise ValueError('Kênh chưa cấp quyền đăng video. Hãy kết nối Google lại trong mục Kênh.')
    if not channel.get('proxy_enabled') or not youtube.proxy_for(channel['youtube_channel_id']):
        raise ValueError('Hãy lưu proxy cho kênh trước khi đăng.')
    record = store.get_upload(identifier, channel_id)
    if not record or not record.get('seo'):
        raise ValueError('Hãy lưu SEO của video trước khi đăng.')
    if record.get('status') == 'uploaded':
        raise HTTPException(409, 'Video này đã đăng lên kênh.')
    if record.get('status') in ('uploading', 'setting_thumbnail'):
        raise HTTPException(409, 'Video đang được đăng.')
    record.update(status='uploading', error=None, youtube_channel_id=channel['youtube_channel_id'])
    store.save_upload(record)
    youtube_publish.enqueue(identifier, channel_id)
    return public_upload(record)


@app.post('/api/channels', status_code=201)
def add_channel(body: Channel):
    channel = {'id': uuid.uuid4().hex, **body.model_dump()}
    store.save_channel(channel)
    return channel


@app.put('/api/channels/{identifier}')
def edit_channel(identifier: str, body: Channel):
    old = next((c for c in store.all_channels() if c['id'] == identifier), None)
    if old is None:
        raise HTTPException(404, 'Không tìm thấy kênh.')
    if body.country.strip().lower() == 'chưa chọn':
        raise ValueError('Hãy chọn quốc gia thật cho kênh.')
    channel = {**old, **body.model_dump(), 'configured': bool(old.get('youtube_channel_id'))}
    store.save_channel(channel)
    return channel


@app.delete('/api/channels/{identifier}')
def remove_channel(identifier: str):
    if not store.delete_channel(identifier):
        raise HTTPException(404, 'Không tìm thấy kênh.')
    return {'deleted': identifier}


class Edit(BaseModel):
    revision: int
    segments: list[Segment] = Field(min_length=1, max_length=100000)


@app.put('/api/projects/{identifier}/subtitles')
def edit(identifier: str, body: Edit):
    with worker.lock:
        p = project(identifier)
        if p['status'] in worker.ACTIVE:
            raise HTTPException(409, 'Tạm dừng trước khi chỉnh sửa.')
        if identifier in worker.futures and not worker.futures[identifier].done():
            raise HTTPException(409, 'Đang dừng bước hiện tại; vui lòng đợi trước khi sửa.')
        if p['revision'] != body.revision:
            raise HTTPException(409, 'Phụ đề đã thay đổi. Hãy tải lại dự án.')
        segments = [s.model_dump() for s in body.segments]
        warnings = validate(segments, p['duration'])
        folder = store.ROOT / identifier
        (folder / f'revision-{p["revision"]}.json').write_text(__import__('json').dumps(p['segments'], ensure_ascii=False), encoding='utf-8')
        p.update(segments=segments, timeline_manifest=timeline_manifest(segments), warnings=warnings,
                 revision=p['revision'] + 1, status='draft', progress=0, error=None)
        store.save(p)
        return p


@app.post('/api/projects/{identifier}/{action}')
def action(identifier: str, action: Literal['start', 'pause', 'cancel']):
    with worker.lock:
        p = project(identifier)
        if action == 'start':
            if p.get('status') == 'needs_attention' and p.get('error'):
                raise ValueError('Hãy xử lý cảnh báo và lưu phụ đề trước khi chạy lại.')
            if p['audio_mode'] == 'voxcpm' and not all(readiness()[k] for k in ('installed', 'model_ready')):
                raise ValueError('Chưa cài VoxCPM hoặc chưa cấu hình thư mục mô hình.')
            worker.enqueue(identifier)
        else:
            p['status'] = 'paused' if action == 'pause' else 'canceled'
            store.save(p)
        return project(identifier)


@app.get('/api/projects/{identifier}/files/{kind}')
def download(identifier: str, kind: Literal['video', 'srt', 'report', 'source', 'original_srt']):
    p = project(identifier)
    folder = store.ROOT / identifier
    if kind == 'source':
        return FileResponse(folder / 'source.mp4', media_type='video/mp4')
    if kind == 'original_srt':
        return FileResponse(folder / 'original.srt', filename=f'{p["locale"]}_original.srt')
    if p['status'] != 'completed':
        raise HTTPException(409, 'Chưa có bản xuất hoàn tất cho phiên bản này.')
    filename = {'video': 'video.mp4', 'srt': 'subtitles.srt', 'report': 'report.json'}[kind]
    return FileResponse(folder / 'output' / filename, filename=f'{p["locale"]}_{filename}')


frontend = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
if frontend.exists():
    app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
