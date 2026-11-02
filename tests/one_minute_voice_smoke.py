"""Real local HTTP smoke test: 60-second video + Vietnamese SRT -> VoxCPM2 -> MP4/SRT.

Run from tool2 after checking that the machine has enough free RAM for VoxCPM2.
No model download or paid API is used.
"""

import time
from pathlib import Path

import httpx

from backend import media, store

ROOT = store.ROOT / 'one_minute_smoke'
VIDEO = ROOT / 'source.mp4'
SRT = ROOT / 'source.vi-VN.srt'
SENTENCES = [
    'Sáng hôm ấy, Lan tìm thấy một lá thư trước cửa nhà.',
    'Trong thư chỉ có một dòng: hãy đến ngọn hải đăng lúc hoàng hôn.',
    'Cô đi dọc bờ biển, mang theo chiếc chìa khóa của cha.',
    'Khi mặt trời lặn, cánh cửa cũ cuối cùng cũng mở ra.',
    'Bên trong không có kho báu, chỉ có những bức ảnh gia đình.',
    'Lan mỉm cười. Đó là món quà cô đã tìm kiếm bấy lâu.',
]


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    if not VIDEO.exists():
        media.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                   'color=c=#475c63:s=320x180:r=24:d=60', '-c:v', 'libx264',
                   '-pix_fmt', 'yuv420p', str(VIDEO)])
    blocks = []
    for index, sentence in enumerate(SENTENCES):
        start = 2 + index * 10
        end = 10 + index * 10 if index < 5 else 59
        blocks.append(f'{index + 1}\n00:00:{start:02},000 --> 00:00:{end:02},000\n{sentence}')
    SRT.write_text('\n\n'.join(blocks) + '\n', encoding='utf-8')
    return VIDEO, SRT


def main():
    prepare()
    with httpx.Client(base_url='http://127.0.0.1:8765', timeout=120) as client:
        health = client.get('/api/health').json()
        if not health['tts']['model_ready']:
            raise RuntimeError('VoxCPM2 chưa sẵn sàng.')
        with VIDEO.open('rb') as video, SRT.open('rb') as subtitles:
            response = client.post('/api/projects', data={
                'name': 'Thử giọng 1 phút · Lá thư ở hải đăng',
                'locale': 'vi-VN', 'srt_kind': 'translated', 'audio_mode': 'voxcpm'},
                files={'video': ('one-minute.mp4', video, 'video/mp4'),
                       'subtitles': ('one-minute.vi-VN.srt', subtitles, 'text/plain')})
        response.raise_for_status()
        identifier = response.json()['id']
        print(f'PROJECT_ID={identifier}', flush=True)
        deadline = time.monotonic() + 900
        last_status = None
        while time.monotonic() < deadline:
            project = client.get(f'/api/projects/{identifier}').json()
            if project['status'] != last_status:
                print(f"STATUS={project['status']} PROGRESS={project.get('progress', 0)}", flush=True)
                last_status = project['status']
            if project['status'] in ('completed', 'failed', 'needs_attention'):
                break
            time.sleep(3)
        else:
            raise TimeoutError(f'Bài thử quá 15 phút: {identifier}')
        if project['status'] != 'completed':
            raise RuntimeError(f"{project['status']}: {project.get('error')}")
        output = store.ROOT / identifier / 'output'
        duration, streams = media.probe(output / 'video.mp4')
        if abs(duration - 60) > .25 or not {'video', 'audio'} <= {s['codec_type'] for s in streams}:
            raise RuntimeError('Kiểm tra MP4 đầu ra thất bại.')
        if not (output / 'subtitles.srt').exists() or not (output / 'report.json').exists():
            raise RuntimeError('Thiếu SRT hoặc báo cáo.')
        print(f'COMPLETED duration={duration:.3f}s video={output / "video.mp4"}', flush=True)


if __name__ == '__main__':
    main()
