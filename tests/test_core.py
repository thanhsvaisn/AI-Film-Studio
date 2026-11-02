import unittest
import tempfile
import os
import time
import wave
import json
from unittest.mock import patch
from pathlib import Path

temporary = tempfile.TemporaryDirectory()
os.environ['FILM_STUDIO_DATA'] = temporary.name
from backend.subtitles import parse_srt, parse_srt_overspaced, serialize, validate
from backend.worker import audio_key
from backend.media import run, probe
from backend.audio_mix import mix_dialogue, fit_clip
from backend.locales import LOCALES, default_sample, default_style

SRT = '1\n00:00:00,100 --> 00:00:01,500\nXin chào.\n\n2\n00:00:02,000 --> 00:00:03,500\nHẹn gặp lại.\n'


class SubtitlesTest(unittest.TestCase):
    def test_new_market_locales_have_default_samples(self):
        for locale in ('fil-PH', 'ms-MY', 'es-MX', 'de-DE', 'fr-FR'):
            self.assertIn(locale, LOCALES)
            self.assertTrue(default_sample(locale).strip())
        self.assertIn('Mexican', default_style('es-MX'))

    def test_roundtrip_unicode(self):
        s = parse_srt('\ufeff' + SRT.replace('\n', '\r\n'))
        self.assertEqual(parse_srt(serialize(s)), s)

    def test_recover_legacy_overspaced_source_without_shifting_timestamps(self):
        overspaced = '\n\n'.join(line for line in SRT.splitlines() if line.strip())
        self.assertEqual(parse_srt_overspaced(overspaced), parse_srt(SRT))

    def test_duplicate_backwards_and_invalid_minutes(self):
        for invalid in [SRT.replace('\n2\n', '\n1\n'), SRT.replace('00:00:03,500', '00:00:01,000'), SRT.replace('00:00:02,000', '00:70:02,000')]:
            with self.assertRaises(ValueError):
                parse_srt(invalid)

    def test_end_beyond_movie_and_nan(self):
        with self.assertRaises(ValueError):
            validate(parse_srt(SRT), 2)
        s = parse_srt(SRT)
        s[0]['start'] = float('nan')
        with self.assertRaises(ValueError):
            validate(s)

    def test_targeted_cache(self):
        s = parse_srt(SRT)[0]
        key = audio_key(s, 'voice', 'model')
        self.assertEqual(key, audio_key(dict(s, start=.2), 'voice', 'model'))
        self.assertNotEqual(key, audio_key(dict(s, text='Khác'), 'voice', 'model'))
        self.assertNotEqual(key, audio_key(s, 'other', 'model'))


class AudioMixTest(unittest.TestCase):
    def test_speed_adjustment_uses_only_needed_amount(self):
        source = Path(temporary.name) / 'slightly-long.wav'
        target = Path(temporary.name) / 'slightly-long.fitted.wav'
        with wave.open(str(source), 'wb') as wav:
            wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * round(1.02 * 48000))
        _, frames, overflow = fit_clip(source, target, 48000)
        self.assertFalse(overflow)
        self.assertGreater(frames, round(.96 * 48000))
        self.assertLessEqual(frames, 48000)

    def test_long_and_overlapping_dialogue_is_kept(self):
        folder = Path(temporary.name)
        clips = []
        for index in range(2):
            path = folder / f'clip-{index}.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                wav.writeframes((1000).to_bytes(2, 'little', signed=True) * 48000)
            clips.append(path)
        output = folder / 'mixed.wav'
        warnings = mix_dialogue([
            {'id': 1, 'start': 0, 'end': .5},
            {'id': 2, 'start': .4, 'end': 1.4},
        ], clips, output, 2)
        self.assertEqual(len(warnings), 1)
        with wave.open(str(output), 'rb') as wav:
            self.assertEqual(wav.getnframes(), 96000)
            wav.setpos(round(.6 * 48000))
            sample = int.from_bytes(wav.readframes(1), 'little', signed=True)
        self.assertGreater(sample, 1000)

    def test_speech_past_end_needs_review(self):
        folder = Path(temporary.name)
        source = folder / 'clip-end.wav'
        with wave.open(str(source), 'wb') as wav:
            wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * 48000)
        with self.assertRaisesRegex(ValueError, 'không cắt lời'):
            mix_dialogue([{'id': 1, 'start': .5, 'end': .8}], [source], folder / 'end.wav', 1)


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app import app
        cls.client = TestClient(app)
        cls.video = Path(temporary.name) / 'fixture.mp4'
        cls.audio = Path(temporary.name) / 'fixture.wav'
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=24:d=4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)])
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4', '-ar', '48000', str(cls.audio)])
        from backend import store
        cls.channel_id = 'connected-test-channel'
        store.save_channel({'id': cls.channel_id, 'name': 'Test', 'country': 'Việt Nam',
                            'locale': 'vi-VN', 'voice': 'default', 'youtube_channel_id': 'YT_TEST',
                            'configured': True})
        cls.token_patcher = patch('backend.app.youtube.has_refresh_token', return_value=True)
        cls.token_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.token_patcher.stop()

    def create(self):
        with self.video.open('rb') as video, self.audio.open('rb') as audio:
            response = self.client.post('/api/projects', data={'name':'Kiểm thử', 'locale':'vi-VN', 'audio_mode':'approved', 'confirmed':'true', 'channel_ids': json.dumps([self.channel_id])},
                files={'video':('test.mp4',video,'video/mp4'), 'audio':('test.wav',audio,'audio/wav'), 'subtitles':('test.srt',SRT.encode(),'text/plain')})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_full_export_and_revision(self):
        p = self.create()
        endpoint = '/api/projects/' + p['id']
        self.assertIn(p['status'], ('queued', 'translation', 'tts', 'audio_mixing', 'qa', 'mux', 'completed'))
        for _ in range(200):
            p = self.client.get(endpoint).json()
            if p['status'] in ('failed', 'completed'):
                break
            time.sleep(.1)
        self.assertEqual(p['status'], 'completed', p)
        self.assertEqual(p['report']['api_cost_usd'], 0)
        self.assertEqual(p['report']['skipped'], ['asr','translation','tts'])
        self.assertEqual(parse_srt(self.client.get(endpoint+'/files/srt').text), parse_srt(SRT))
        result = Path(temporary.name) / p['id'] / 'output' / 'video.mp4'
        duration, streams = probe(result)
        self.assertAlmostEqual(duration, 4, delta=.25)
        self.assertEqual({s['codec_type'] for s in streams}, {'video','audio'})
        p['segments'][0]['text'] = 'Đã chỉnh sửa.'
        edit = {'revision':p['revision'], 'segments':p['segments']}
        self.assertEqual(self.client.put(endpoint+'/subtitles',json=edit).status_code, 200)
        self.assertEqual(self.client.put(endpoint+'/subtitles',json=edit).status_code, 409)
        self.assertEqual(self.client.get(endpoint+'/files/video').status_code, 409)

    def test_origin_and_missing_project(self):
        self.assertEqual(self.client.post('/api/projects/nope/start',headers={'Origin':'https://example.com'}).status_code, 403)
        self.assertEqual(self.client.get('/api/projects/nope').status_code, 404)

    def test_project_requires_connected_channel(self):
        with self.video.open('rb') as video, self.audio.open('rb') as audio:
            response = self.client.post('/api/projects', data={'name':'Thiếu kênh','locale':'vi-VN','audio_mode':'approved'},
                files={'video':('test.mp4',video,'video/mp4'), 'audio':('test.wav',audio,'audio/wav'), 'subtitles':('test.srt',SRT.encode(),'text/plain')})
        self.assertEqual(response.status_code, 400)

    def test_youtube_seo_is_saved_per_channel_and_requires_proxy(self):
        p = self.create()
        endpoint = f"/api/projects/{p['id']}/youtube"
        rows = self.client.get(endpoint).json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['seo']['privacy'], 'private')
        seo = {'title': 'Phim kiểm thử', 'description': 'Nội dung', 'tags': ['phim'],
               'category_id': '24', 'privacy': 'private',
               'made_for_kids': False, 'synthetic_media': True}
        saved = self.client.put(endpoint + '/' + self.channel_id + '/seo', json=seo)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get(endpoint).json()[0]['seo']['title'], seo['title'])
        from backend import store
        channel = next(c for c in store.all_channels() if c['id'] == self.channel_id)
        channel['upload_scope_granted'] = True
        store.save_channel(channel)
        for _ in range(200):
            if self.client.get('/api/projects/' + p['id']).json()['status'] == 'completed':
                break
            time.sleep(.1)
        with patch('backend.app.youtube.proxy_for', return_value=None):
            response = self.client.post(endpoint + '/' + self.channel_id + '/publish')
        self.assertEqual(response.status_code, 400)
        self.assertIn('proxy', response.json()['detail'])

    def test_additional_country_and_japanese_translated_srt(self):
        channel = self.client.post('/api/channels', json={
            'name': 'Drama Nhật', 'country': 'Nhật Bản', 'locale': 'ja-JP', 'voice': 'default'})
        self.assertEqual(channel.status_code, 201, channel.text)
        from backend import store
        imported = channel.json()
        imported['youtube_channel_id'] = 'YT_JAPAN'
        imported['configured'] = True
        store.save_channel(imported)
        japanese = '1\n00:00:00,100 --> 00:00:01,500\n今日は晴れです。\n'
        with self.video.open('rb') as video, self.audio.open('rb') as audio:
            response = self.client.post('/api/projects', data={
                'name': 'Bản Nhật', 'locale': 'ja-JP', 'audio_mode': 'approved',
                'srt_kind': 'translated', 'channel_ids': __import__('json').dumps([channel.json()['id']])},
                files={'video': ('test.mp4', video, 'video/mp4'),
                       'audio': ('test.wav', audio, 'audio/wav'),
                       'subtitles': ('test.ja-JP.srt', japanese.encode(), 'text/plain')})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['srt_kind'], 'translated')

    def test_five_new_market_channels_are_accepted(self):
        for locale in ('fil-PH', 'ms-MY', 'es-MX', 'de-DE', 'fr-FR'):
            response = self.client.post('/api/channels', json={
                'name': 'Drama ' + locale, 'country': LOCALES[locale][0],
                'locale': locale, 'voice': 'default'})
            self.assertEqual(response.status_code, 201, response.text)
        health = self.client.get('/api/health').json()
        self.assertEqual(len(health['locales']), 17)

    def test_batch_retry_does_not_create_duplicate_job(self):
        payload={'name':'Tập 01','locale':'vi-VN','audio_mode':'approved',
                 'batch_id':'7b0d03dd-755f-4f0c-b4ee-a41fa0866d61',
                 'source_filename':'series/tap01.mp4', 'channel_ids':json.dumps([self.channel_id])}
        ids=[]
        for _ in range(2):
            with self.video.open('rb') as video, self.audio.open('rb') as audio:
                response=self.client.post('/api/projects',data=payload,files={
                    'video':('tap01.mp4',video,'video/mp4'),
                    'audio':('dub.wav',audio,'audio/wav'),
                    'subtitles':('tap01.srt',SRT.encode(),'text/plain')})
            self.assertEqual(response.status_code,201,response.text)
            ids.append(response.json()['id'])
        self.assertEqual(ids[0],ids[1])
        csv_response = self.client.get('/api/batches/' + payload['batch_id'] + '/report.csv')
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn('tap01.mp4', csv_response.text)

    def test_default_voice_reused_across_projects(self):
        calls = []
        instances = []
        class FakeVoice:
            def __init__(self):
                instances.append(self)
            def synthesize(self, text, output, reference=None):
                calls.append(reference)
                with wave.open(str(output), 'wb') as wav:
                    wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                    wav.writeframes(b'\0\0' * 4800)
        with patch('backend.app.readiness', return_value={'installed': True, 'model_ready': True}), patch('backend.worker.VoxCPMProvider', FakeVoice):
            for _ in range(2):
                with self.video.open('rb') as video:
                    response = self.client.post('/api/projects', data={'name':'Giọng mặc định','locale':'vi-VN','audio_mode':'voxcpm','channel_ids':json.dumps([self.channel_id])},
                        files={'video':('test.mp4', video, 'video/mp4'), 'subtitles':('test.srt', SRT.encode(), 'text/plain')})
                self.assertEqual(response.status_code, 201, response.text)
                identifier = response.json()['id']
                for _ in range(200):
                    p = self.client.get('/api/projects/' + identifier).json()
                    if p['status'] in ('completed', 'failed'):
                        break
                    time.sleep(.1)
                self.assertEqual(p['status'], 'completed', p)
        self.assertTrue((Path(temporary.name) / 'default_voice.wav').exists())
        self.assertEqual(calls.count(None), 1)
        self.assertEqual(len(calls), 5)
        self.assertEqual(len(instances), 1)


if __name__ == '__main__':
    unittest.main()
