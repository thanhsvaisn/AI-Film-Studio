"""One-minute voice demo with natural dialogue density; runs against the local app."""

import time

import httpx

from backend import media, store
from tests.one_minute_voice_smoke import ROOT, VIDEO, prepare

SENTENCES = [
    'Sáng sớm, Lan thấy một lá thư trước cửa.',
    'Nét chữ của cha khiến cô khựng lại.',
    'Ông dặn cô đến ngọn hải đăng lúc chiều.',
    'Lan cầm chiếc chìa khóa cũ rồi lên đường.',
    'Con đường ven biển hôm nay yên ắng lạ.',
    'Gió thổi mạnh, nhưng cô vẫn bước tiếp.',
    'Đến nơi, cô nhìn thấy cánh cửa đã khóa.',
    'Chiếc chìa xoay nhẹ, một tiếng tách vang lên.',
    'Bên trong tối, chỉ có ánh nắng cuối ngày.',
    'Trên bàn là những bức ảnh gia đình.',
    'Mỗi tấm ảnh kể lại một kỷ niệm xưa.',
    'Lan hiểu rằng cha chưa từng quên cô.',
    'Cô ôm chiếc hộp nhỏ vào lòng.',
    'Rồi cô mỉm cười, quay về phía biển.',
]


def main():
    prepare()
    srt = ROOT / 'source-dense.vi-VN.srt'
    blocks = []
    for index, text in enumerate(SENTENCES):
        start_ms = 1000 + index * 4200
        end_ms = start_ms + 4200
        def stamp(ms):
            hours, ms = divmod(ms, 3600000)
            minutes, ms = divmod(ms, 60000)
            seconds, ms = divmod(ms, 1000)
            return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'
        blocks.append(f'{index + 1}\n{stamp(start_ms)} --> {stamp(end_ms)}\n{text}')
    srt.write_text('\n\n'.join(blocks) + '\n', encoding='utf-8')
    with httpx.Client(base_url='http://127.0.0.1:8765', timeout=120) as client:
        with VIDEO.open('rb') as video, srt.open('rb') as subtitles:
            response = client.post('/api/projects', data={
                'name': 'Thử giọng 1 phút · nhịp thoại tự nhiên',
                'locale': 'vi-VN', 'srt_kind': 'translated', 'audio_mode': 'voxcpm'},
                files={'video': ('one-minute-dense.mp4', video, 'video/mp4'),
                       'subtitles': ('one-minute-dense.vi-VN.srt', subtitles, 'text/plain')})
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
            raise TimeoutError(f'Quá 15 phút: {identifier}')
        if project['status'] != 'completed':
            raise RuntimeError(f"{project['status']}: {project.get('error')}")
        output = store.ROOT / identifier / 'output'
        duration, streams = media.probe(output / 'video.mp4')
        if abs(duration - 60) > .25 or not {'video', 'audio'} <= {s['codec_type'] for s in streams}:
            raise RuntimeError('MP4 đầu ra không hợp lệ.')
        if len(project['segments']) != len(SENTENCES):
            raise RuntimeError('Số câu đầu ra không khớp.')
        print(f'COMPLETED duration={duration:.3f}s segments={len(SENTENCES)} video={output / "video.mp4"}', flush=True)


if __name__ == '__main__':
    main()
