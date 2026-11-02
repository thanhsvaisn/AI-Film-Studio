import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault('FILM_STUDIO_DATA', tempfile.mkdtemp())

from backend import youtube, youtube_publish


class FakeResponse:
    def __init__(self, status, headers=None, data=None):
        self.status_code = status
        self.headers = headers or {}
        self._data = data or {}

    def json(self):
        return self._data


class FakeClient:
    def __init__(self):
        self.posts = []
        self.puts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(200, {'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'})

    def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        return (FakeResponse(308, {'Range': 'bytes=0-3'}) if len(self.puts) == 1
                else FakeResponse(201, data={'id': 'YT_VIDEO_123'}))


class YouTubePublishTest(unittest.TestCase):
    def test_proxy_accepts_supported_schemes_without_exposing_credentials(self):
        for value in ('http://user:secret@proxy.example:8080',
                      'https://proxy.example:8443', 'socks5://proxy.example:1080'):
            self.assertEqual(youtube.validate_proxy(value), value)
        for value in ('file:///tmp/x', 'http://proxy.example', 'http://proxy.example:0',
                      'http://proxy.example:8080/other'):
            with self.assertRaises(ValueError):
                youtube.validate_proxy(value)
        with patch.object(youtube.keyring, 'set_password'):
            display = youtube.set_proxy('channel', 'http://user:secret@proxy.example:8080')
        self.assertEqual(display, 'http://proxy.example:8080')

    def test_one_resumable_upload_uses_two_chunks_and_returns_video_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'video.mp4'
            path.write_bytes(b'12345678')
            record = {'project_id': 'p', 'channel_id': 'c', 'seo': {
                'title': 'Film', 'description': 'Story', 'tags': ['film'],
                'category_id': '24', 'privacy': 'private',
                'made_for_kids': False, 'synthetic_media': True}}
            client = FakeClient()
            def save(current, **changes):
                current.update(changes)
            with patch.object(youtube_publish, 'CHUNK', 4), patch.object(youtube_publish, '_save', save):
                result = youtube_publish._upload_video(client, 'token', record, 'th-TH', path)
            self.assertEqual(result, 'YT_VIDEO_123')
            self.assertEqual(len(client.posts), 1)
            self.assertEqual(len(client.puts), 2)
            self.assertEqual(client.puts[0][1]['headers']['Content-Range'], 'bytes 0-3/8')
            self.assertEqual(client.puts[1][1]['headers']['Content-Range'], 'bytes 4-7/8')
            self.assertEqual(client.posts[0][1]['json']['snippet']['defaultLanguage'], 'th')
            self.assertTrue(client.posts[0][1]['json']['status']['containsSyntheticMedia'])

    def test_rejects_session_uri_outside_google_upload_endpoint(self):
        with self.assertRaises(ValueError):
            youtube_publish._session_valid('http://localhost:8080/steal')

    def test_refresh_token_request_uses_channel_proxy(self):
        response = FakeResponse(200, data={'access_token': 'short_lived'})
        client = MagicMock()
        client.__enter__.return_value.post.return_value = response
        with patch.object(youtube.keyring, 'get_password', side_effect=['refresh_token', 'socks5://proxy.example:1080']), \
             patch.object(youtube, 'credentials', return_value=('client', 'secret')), \
             patch.object(youtube.httpx, 'Client', return_value=client) as constructor:
            token = youtube.access_token('YT_CHANNEL')
        self.assertEqual(token, 'short_lived')
        self.assertEqual(constructor.call_args.kwargs['proxy'], 'socks5://proxy.example:1080')

    def test_channel_lookup_accepts_handle_and_channel_url(self):
        self.assertEqual(youtube.channel_filter('@GoogleDevelopers'), ('forHandle', 'GoogleDevelopers'))
        self.assertEqual(youtube.channel_filter('https://www.youtube.com/@GoogleDevelopers/videos'),
                         ('forHandle', 'GoogleDevelopers'))
        self.assertEqual(youtube.channel_filter('UC_x5XG1OV2P6uZZ5FSM9Ttw'),
                         ('id', 'UC_x5XG1OV2P6uZZ5FSM9Ttw'))
        with self.assertRaises(ValueError):
            youtube.channel_filter('https://not-youtube.example/@GoogleDevelopers')


if __name__ == '__main__':
    unittest.main()
