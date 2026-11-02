"""One continuous Vietnamese script, one VoxCPM2 synthesis call, 60-second MP4."""

import time

import httpx

from backend import media, store
from tests.one_minute_voice_smoke import ROOT, VIDEO, prepare

SCRIPT = (
    'Buổi sáng hôm ấy, Lan tìm thấy một lá thư trước cửa nhà. '
    'Nét chữ quen thuộc khiến cô đứng lặng. '
    'Đó là thư của cha, người đã rời đi nhiều năm trước. '
    'Trong thư, ông chỉ viết một câu: Hãy đến ngọn hải đăng trước khi mặt trời lặn. '
    'Lan cầm chiếc chìa khóa cũ trong ngăn bàn và đi dọc bờ biển. '
    'Gió nổi lên, sóng vỗ vào những tảng đá, nhưng cô không dừng lại. '
    'Khi đến nơi, chiếc chìa khóa vừa khít cánh cửa gỗ. '
    'Bên trong, không có vàng bạc hay bí mật lớn lao. '
    'Trên chiếc bàn nhỏ là những bức ảnh của gia đình, được ông gìn giữ qua từng năm. '
    'Lan chạm vào tấm ảnh cuối cùng và hiểu rằng, dù xa cách, cha vẫn luôn nghĩ về cô. '
    'Cô ôm chiếc hộp vào lòng, rồi mỉm cười nhìn về phía biển. '
    'Trên mặt sau mỗi tấm ảnh, cha viết ngày tháng và vài lời nhắn. '
    'Có tấm chụp Lan lần đầu biết đi, có tấm chụp cả nhà trong một buổi chiều mưa. '
    'Cô từng nghĩ những ký ức ấy đã mất từ lâu, nhưng ông đã âm thầm giữ lại tất cả. '
    'Ở cuối hộp, Lan thấy một lá thư khác. '
    'Cha xin lỗi vì những năm tháng vắng mặt, và mong cô đừng để quá khứ níu giữ. '
    'Lan gấp lá thư, bước ra hiên hải đăng. '
    'Hoàng hôn phủ lên mặt biển màu vàng dịu. '
    'Lần đầu tiên sau nhiều năm, cô cảm thấy lòng mình nhẹ nhõm.'
)


def main():
    prepare()
    srt = ROOT / 'single-script.vi-VN.srt'
    srt.write_text('1\n00:00:00,000 --> 00:01:00,000\n' + SCRIPT + '\n', encoding='utf-8')
    print(f'WORDS={len(SCRIPT.split())}', flush=True)
    with httpx.Client(base_url='http://127.0.0.1:8765', timeout=120) as client:
        with VIDEO.open('rb') as video, srt.open('rb') as subtitles:
            response = client.post('/api/projects', data={
                'name': 'Thử 1 giọng · 1 kịch bản · 1 phút',
                'locale': 'vi-VN', 'srt_kind': 'translated', 'audio_mode': 'voxcpm'},
                files={'video': ('one-minute-single-script.mp4', video, 'video/mp4'),
                       'subtitles': ('one-minute-single-script.vi-VN.srt', subtitles, 'text/plain')})
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
        cache = list((store.ROOT / identifier / 'cache').glob('*.wav'))
        if len(cache) != 1:
            raise RuntimeError(f'Phải có đúng một lần tổng hợp giọng, thấy {len(cache)} tệp cache.')
        print(f'COMPLETED duration={duration:.3f}s video={output / "video.mp4"} voice_wav={cache[0]}', flush=True)


if __name__ == '__main__':
    main()
