"""Manual hardware smoke test: creates a synthetic video and a real VoxCPM dub."""
import os
import time
from pathlib import Path

from fastapi.testclient import TestClient
from backend.app import app
from backend.media import run, probe

root = Path(__file__).resolve().parents[1]
fixture = root / 'data' / 'voice-fixture.mp4'
fixture.parent.mkdir(parents=True, exist_ok=True)
run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=#597256:s=320x180:r=24:d=20',
     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(fixture)])
srt = '1\n00:00:00,500 --> 00:00:08,500\nXin chào, đây là giọng đọc mặc định.\n\n2\n00:00:10,000 --> 00:00:19,000\nHẹn gặp lại trong bộ phim tiếp theo.\n'
with TestClient(app) as client, fixture.open('rb') as video:
    response = client.post('/api/projects', data={'name':'Kiểm thử giọng thật', 'locale':'vi-VN', 'audio_mode':'voxcpm'},
        files={'video':('fixture.mp4', video, 'video/mp4'), 'subtitles':('fixture.srt', srt.encode(), 'text/plain')})
    response.raise_for_status()
    identifier = response.json()['id']
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        p = client.get('/api/projects/' + identifier).json()
        if p['status'] in ('completed', 'failed'):
            break
        time.sleep(2)
    assert p['status'] == 'completed', p
    output = root / 'data' / identifier / 'output' / 'video.mp4'
    duration, streams = probe(output)
    assert abs(duration - 20) < .25
    assert {'video', 'audio'} <= {s['codec_type'] for s in streams}
    assert (root / 'data' / 'default_voice.wav').exists()
    print('REAL_VOICE_OK', identifier, output, flush=True)
