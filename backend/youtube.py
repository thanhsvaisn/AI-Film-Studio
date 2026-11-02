"""Local YouTube OAuth, per-channel proxy and YouTube API access."""
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, unquote

import httpx
import keyring

SCOPES = ('https://www.googleapis.com/auth/youtube.readonly '
          'https://www.googleapis.com/auth/yt-analytics.readonly '
          'https://www.googleapis.com/auth/youtube.upload')
SERVICE = 'AI Film Studio YouTube'
PROXY_SERVICE = 'AI Film Studio YouTube Proxy'
PENDING = {}


def credentials():
    client_id = os.getenv('FILM_GOOGLE_CLIENT_ID') or os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('FILM_GOOGLE_CLIENT_SECRET') or os.getenv('GOOGLE_CLIENT_SECRET')
    if not client_id or not client_secret:
        root_env = Path(__file__).resolve().parents[3] / '.env'
        if root_env.is_file():
            for line in root_env.read_text(encoding='utf-8-sig').splitlines():
                key, separator, value = line.partition('=')
                if separator and key.strip() in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'):
                    if key.strip() == 'GOOGLE_CLIENT_ID' and not client_id:
                        client_id = value.strip().strip('"\'')
                    if key.strip() == 'GOOGLE_CLIENT_SECRET' and not client_secret:
                        client_secret = value.strip().strip('"\'')
    return client_id, client_secret


def configured():
    return all(credentials())


def public_api_key():
    value = os.getenv('YOUTUBE_API_KEY')
    if value:
        return value
    root_env = Path(__file__).resolve().parents[3] / '.env'
    if root_env.is_file():
        for line in root_env.read_text(encoding='utf-8-sig').splitlines():
            key, separator, candidate = line.partition('=')
            if separator and key.strip() == 'YOUTUBE_API_KEY':
                return candidate.strip().strip('"\'')
    return None


def channel_filter(query):
    query = query.strip()
    if not query or len(query) > 200:
        raise ValueError('Nhập @handle hoặc URL kênh YouTube hợp lệ.')
    if query.startswith(('http://', 'https://')):
        parsed = urlsplit(query)
        if parsed.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            raise ValueError('Chỉ nhận URL kênh youtube.com.')
        parts = [unquote(part) for part in parsed.path.split('/') if part]
        if len(parts) < 1:
            raise ValueError('URL kênh chưa đủ thông tin.')
        if parts[0] == 'channel' and len(parts) >= 2:
            query = parts[1]
        elif parts[0].startswith('@'):
            query = parts[0]
        else:
            raise ValueError('Hãy dùng URL /@handle hoặc /channel/UC…')
    if query.startswith('UC') and len(query) == 24 and query.replace('_', '').replace('-', '').isalnum():
        return 'id', query
    if query.startswith('@'):
        query = query[1:]
    if not query or len(query) > 100 or not all(c.isalnum() or c in '._-' for c in query):
        raise ValueError('Handle YouTube không hợp lệ.')
    return 'forHandle', query


def lookup_channel(query):
    key = public_api_key()
    if not key:
        raise ValueError('Chưa cấu hình YouTube API key.')
    field, value = channel_filter(query)
    with httpx.Client(timeout=25) as client:
        response = client.get('https://www.googleapis.com/youtube/v3/channels', params={
            'part': 'snippet,statistics', field: value, 'key': key})
    if response.status_code != 200:
        raise ValueError(f'YouTube Data API trả về HTTP {response.status_code}. Kiểm tra khóa và hạn mức API.')
    items = response.json().get('items', [])
    if not items:
        raise ValueError('Không tìm thấy kênh này trên YouTube.')
    item = items[0]
    snippet, statistics = item.get('snippet', {}), item.get('statistics', {})
    return {'id': item['id'], 'title': snippet.get('title', ''),
            'description': snippet.get('description', '')[:400],
            'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url', ''),
            'country': snippet.get('country'), 'handle': snippet.get('customUrl'),
            'subscribers': statistics.get('subscriberCount'),
            'videos': statistics.get('videoCount'), 'views': statistics.get('viewCount')}


def authorization_url(redirect_uri):
    client_id, _ = credentials()
    if not client_id:
        raise ValueError('Chưa cấu hình Google OAuth client ID và secret.')
    now = time.time()
    for state, created in list(PENDING.items()):
        if now - created > 600:
            PENDING.pop(state, None)
    state = secrets.token_urlsafe(32)
    PENDING[state] = now
    params = dict(client_id=client_id, redirect_uri=redirect_uri, response_type='code',
                  scope=SCOPES, access_type='offline', prompt='consent', state=state)
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)


def validate_proxy(value):
    value = value.strip()
    if not value:
        return ''
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https', 'socks5') or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Proxy phải có dạng http://, https:// hoặc socks5://host:port.')
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('Cổng proxy không hợp lệ.')
    if not port:
        raise ValueError('Proxy cần có cổng, ví dụ :8080.')
    return value


def set_proxy(channel_id, value):
    value = validate_proxy(value)
    if value:
        keyring.set_password(PROXY_SERVICE, channel_id, value)
        parsed = urlsplit(value)
        return f'{parsed.scheme}://{parsed.hostname}:{parsed.port}'
    try:
        keyring.delete_password(PROXY_SERVICE, channel_id)
    except keyring.errors.PasswordDeleteError:
        pass
    return ''


def proxy_for(channel_id):
    return keyring.get_password(PROXY_SERVICE, channel_id) or None


def exchange(code, state, redirect_uri):
    created = PENDING.pop(state, None)
    if created is None or time.time() - created > 600:
        raise ValueError('Phiên kết nối đã hết hạn. Hãy thử lại.')
    client_id, client_secret = credentials()
    response = httpx.post('https://oauth2.googleapis.com/token', data=dict(
        code=code, client_id=client_id, client_secret=client_secret,
        redirect_uri=redirect_uri, grant_type='authorization_code'), timeout=25)
    response.raise_for_status()
    token = response.json()
    if not token.get('refresh_token'):
        raise ValueError('Google chưa cấp quyền duy trì kết nối. Hãy kết nối lại.')
    return token


def api_get(url, access_token, params=None, proxy=None):
    with httpx.Client(proxy=proxy, timeout=25) as client:
        response = client.get(url, params=params,
                              headers={'Authorization': f'Bearer {access_token}'})
    if response.status_code >= 400:
        raise ValueError(f'YouTube API trả về HTTP {response.status_code}: {response.text[:300]}')
    return response.json()


def mine(access_token, proxy=None):
    result = api_get('https://www.googleapis.com/youtube/v3/channels', access_token,
                     {'part': 'snippet,statistics', 'mine': 'true', 'maxResults': 50}, proxy)
    return result.get('items', [])


def save_refresh_token(youtube_channel_id, token):
    keyring.set_password(SERVICE, youtube_channel_id, token)


def has_refresh_token(youtube_channel_id):
    return bool(keyring.get_password(SERVICE, youtube_channel_id))


def access_token(youtube_channel_id):
    refresh = keyring.get_password(SERVICE, youtube_channel_id)
    if not refresh:
        raise ValueError('Kênh đã mất kết nối Google. Hãy kết nối lại.')
    client_id, client_secret = credentials()
    with httpx.Client(proxy=proxy_for(youtube_channel_id), timeout=25) as client:
        response = client.post('https://oauth2.googleapis.com/token', data=dict(
            client_id=client_id, client_secret=client_secret,
            refresh_token=refresh, grant_type='refresh_token'))
    if response.status_code >= 400:
        raise ValueError('Không thể làm mới quyền YouTube. Hãy kết nối lại kênh.')
    return response.json()['access_token']


def analytics(youtube_channel_id, start_date, end_date):
    token = access_token(youtube_channel_id)
    proxy = proxy_for(youtube_channel_id)
    base = {'ids': 'channel==MINE', 'startDate': start_date, 'endDate': end_date,
            'metrics': 'views,estimatedMinutesWatched,subscribersGained'}
    daily = api_get('https://youtubeanalytics.googleapis.com/v2/reports', token,
                    {**base, 'dimensions': 'day', 'sort': 'day'}, proxy)
    country = api_get('https://youtubeanalytics.googleapis.com/v2/reports', token,
                      {**base, 'dimensions': 'country', 'sort': '-views', 'maxResults': 10}, proxy)
    return {'daily': daily, 'country': country}
