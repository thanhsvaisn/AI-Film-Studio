import json
import subprocess
from pathlib import Path


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise ValueError('FFmpeg/ffprobe: ' + result.stderr[-1500:])
    return result.stdout


def probe(path):
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))
    duration = float(info['format']['duration'])
    if duration <= 0 or duration > 6 * 3600:
        raise ValueError('Thời lượng phải lớn hơn 0 và tối đa 6 giờ.')
    return duration, info['streams']


def mux(video, audio, output, duration):
    temporary = output.with_suffix('.partial.mp4')
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(video), '-i', str(audio),
         '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
         '-af', 'apad', '-t', str(duration), '-movflags', '+faststart', str(temporary)])
    actual, streams = probe(temporary)
    if abs(actual - duration) > .25 or not any(s['codec_type'] == 'audio' for s in streams):
        raise ValueError('Kiểm tra thời lượng/âm thanh đầu ra thất bại.')
    temporary.replace(output)


def normalize_wav(source, target):
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(source), '-ac', '1', '-ar', '48000', '-c:a', 'pcm_s16le', str(target)])
