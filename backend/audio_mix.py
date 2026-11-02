"""Bounded-memory placement of dialogue clips on the original timeline."""

import os
import wave
from pathlib import Path

import numpy as np

from . import media

RATE = 48000
MAX_SPEED = 1.15


def fit_clip(source: Path, target: Path, slot_frames: int) -> tuple[Path, int, bool]:
    with wave.open(str(source), 'rb') as clip:
        frames = clip.getnframes()
    if frames <= slot_frames:
        return source, frames, False
    # Use only the speed needed to fit; a fixed 1.15x can create a long silent tail.
    speed = min(MAX_SPEED, max(1.0, frames / slot_frames * 1.005))
    media.run(['ffmpeg', '-y', '-v', 'error', '-i', str(source), '-filter:a',
               f'atempo={speed:.6f}', '-ac', '1', '-ar', str(RATE),
               '-c:a', 'pcm_s16le', str(target)])
    with wave.open(str(target), 'rb') as clip:
        fitted = clip.getnframes()
    return target, fitted, fitted > slot_frames


def mix_dialogue(segments: list[dict], audio_files: list[Path], output: Path,
                 duration: float, checkpoint=lambda: None) -> list[str]:
    """Mix overlaps without dropping dialogue; raise if speech exceeds video end."""
    total = round(duration * RATE)
    raw = output.with_suffix('.partial.pcm')
    warnings = []
    try:
        with raw.open('w+b') as stream:
            stream.truncate(total * 2)
            for index, (segment, source) in enumerate(zip(segments, audio_files)):
                checkpoint(index, len(segments))
                start = round(segment['start'] * RATE)
                slot = round((segment['end'] - segment['start']) * RATE)
                fitted_path = source.with_suffix('.fitted.wav')
                chosen, frames, overflow = fit_clip(source, fitted_path, slot)
                if overflow:
                    warnings.append(f'Dòng {segment["id"]}: giọng còn dài hơn khung sau khi tăng tốc tối đa 1,15×; phần dư được phối chồng, cần nghe kiểm tra.')
                if start + frames > total:
                    raise ValueError(f'Dòng {segment["id"]}: lời thoại vượt cuối video sau khi tăng tốc 1,15×. Cần kéo dài khung cuối hoặc sửa bản dịch; không cắt lời.')
                with wave.open(str(chosen), 'rb') as clip:
                    if clip.getnchannels() != 1 or clip.getsampwidth() != 2 or clip.getframerate() != RATE:
                        raise ValueError('Âm thanh TTS phải là WAV mono 48 kHz, 16 bit.')
                    offset = start * 2
                    while data := clip.readframes(RATE):
                        stream.seek(offset)
                        existing = stream.read(len(data))
                        new = np.frombuffer(data, dtype='<i2').astype(np.int32)
                        old = np.frombuffer(existing, dtype='<i2').astype(np.int32)
                        mixed = np.clip(old + new, -32768, 32767).astype('<i2')
                        stream.seek(offset)
                        stream.write(mixed.tobytes())
                        offset += len(data)
                fitted_path.unlink(missing_ok=True)
            checkpoint(len(segments), len(segments))
        temporary = output.with_suffix('.partial.wav')
        with wave.open(str(temporary), 'wb') as wav, raw.open('rb') as stream:
            wav.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            while data := stream.read(RATE * 2):
                wav.writeframesraw(data)
        os.replace(temporary, output)
    finally:
        raw.unlink(missing_ok=True)
    return warnings
