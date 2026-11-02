import hashlib
import json
import os
import re
import shutil
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import store, media
from .providers import VoxCPMProvider
from .subtitles import (parse_srt, parse_srt_overspaced, serialize, timeline_manifest, timeline_manifest_from_srt,
                        validate, validate_timeline)
from .translation import translate_segments, has_chinese
from .audio_mix import mix_dialogue
from .locales import LOCALES, default_sample, default_style, voice_preview_sample

pool = ThreadPoolExecutor(max_workers=1)
lock = threading.RLock()
futures = {}
_provider = None
_provider_path = None
_voice_lock = threading.Lock()
VOICE_DESIGNS = {
    'female_warm': ('Nữ ấm', 'A warm adult female voice, clear diction, gentle and steady pace.'),
    'male_deep': ('Nam trầm', 'A mature male voice, low and resonant, calm pace, clear diction.'),
    'storyteller': ('Kể chuyện', 'An expressive storyteller voice, clear articulation, measured dramatic pacing.'),
    'youthful': ('Trẻ trung', 'A youthful bright voice, friendly tone, natural conversational pace.'),
}
ACTIVE = {'queued', 'translation', 'tts', 'audio_mixing', 'qa', 'mux'}
STAGE_RETRY_LIMIT = 3


def checkpoint(identifier, **changes):
    with lock:
        p = store.get(identifier)
        if p['status'] in ('paused', 'canceled'):
            raise InterruptedError()
        p.update(changes)
        store.save(p)


def retry_step(identifier, *, stage, status, progress, message, operation,
               retry_history, cleanup=None, on_attempt=None, attempts=STAGE_RETRY_LIMIT):
    """Retry one pipeline operation a bounded number of times and expose attempts to the UI."""
    last_error = None
    for attempt in range(1, attempts + 1):
        if on_attempt:
            on_attempt(attempt)
        checkpoint(identifier, status=status, progress=progress, error=None,
                   retry_history=retry_history,
                   progress_detail={'phase': stage, 'completed': 0, 'total': 1,
                                    'attempt': attempt, 'max_attempts': attempts,
                                    'message': message if attempt == 1 else
                                        f'{message} · lần thử {attempt}/{attempts}'})
        try:
            return operation()
        except InterruptedError:
            raise
        except Exception as exc:
            last_error = exc
            retry_history.append({'stage': stage, 'attempt': attempt,
                                  'error': str(exc)[:400]})
            checkpoint(identifier, retry_history=retry_history,
                       progress_detail={'phase': stage, 'completed': 0, 'total': 1,
                                        'attempt': attempt, 'max_attempts': attempts,
                                        'message': (f'{stage}: lỗi lần {attempt}/{attempts} · '
                                                    f'{str(exc)[:180]}')})
            if cleanup:
                cleanup()
            if attempt >= attempts:
                break
            try:
                import torch
                torch.cuda.empty_cache()
            except (ImportError, RuntimeError):
                pass
            time.sleep(min(2 ** (attempt - 1), 4))
    raise last_error


def valid_tts_wav(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            return (audio.getnframes() > 0 and audio.getnchannels() == 1 and
                    audio.getsampwidth() == 2 and audio.getframerate() == 48000)
    except (OSError, EOFError, wave.Error):
        return False


def wav_fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as audio:
        while block := audio.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def audio_key(segment, voice_hash, model):
    return hashlib.sha256(json.dumps([segment['text'], voice_hash, model, 2.0, 10, 'v2'], ensure_ascii=False).encode()).hexdigest()


def voice_provider():
    global _provider, _provider_path
    path = os.environ.get('VOXCPM_MODEL_DIR', '')
    if _provider is None or _provider_path != path:
        _provider = VoxCPMProvider()
        _provider_path = path
    return _provider


def default_voice_path(locale):
    """Create and cache the model-designed default reference voice for one locale."""
    if locale not in LOCALES:
        raise ValueError('Ngôn ngữ giọng mặc định không được hỗ trợ.')
    path = store.ROOT / ('default_voice.wav' if locale == 'vi-VN' else f'default_voice_{locale}.wav')
    with _voice_lock:
        if path.is_file() and path.stat().st_size > 44:
            return path
        raw = path.with_name(path.stem + '.raw.wav')
        temporary = path.with_name(path.stem + '.partial.wav')
        try:
            provider = voice_provider()
            provider.synthesize(default_style(locale) + default_sample(locale), raw)
            media.normalize_wav(raw, temporary)
            temporary.replace(path)
        finally:
            raw.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
    return path


def designed_voice_path(locale, preset_id):
    """Generate one Voice Design catalog sample and cache it for repeat playback."""
    if locale not in LOCALES or preset_id not in VOICE_DESIGNS:
        raise ValueError('Mẫu giọng không được hỗ trợ.')
    folder = store.ROOT / 'designed_voices' / locale
    path = folder / f'{preset_id}_preview3.wav'
    with _voice_lock:
        if path.is_file() and path.stat().st_size > 44:
            return path
        folder.mkdir(parents=True, exist_ok=True)
        raw = path.with_suffix('.raw.wav')
        temporary = path.with_suffix('.partial.wav')
        label, control = VOICE_DESIGNS[preset_id]
        try:
            voice_provider().synthesize(f'({control}) {voice_preview_sample(locale)}', raw)
            media.normalize_wav(raw, temporary)
            temporary.replace(path)
        finally:
            raw.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
    return path


def deliver_project(project, output):
    batch_id = project.get('batch_id')
    source = project.get('source_filename') or project['name']
    stem = source.replace('\\', '/').split('/')[-1].rsplit('.', 1)[0]
    stem = re.sub(r'[^\w.-]+', '_', stem, flags=re.UNICODE).strip('._')[:60] or 'video'
    group = batch_id or 'projects'
    delivery = store.ROOT / 'deliveries' / group / f'{stem}_{project["id"][:8]}'
    delivery.mkdir(parents=True, exist_ok=True)
    for filename in ('video.mp4', 'subtitles.srt', 'source.srt', 'report.json', 'translation_quality.json'):
        source_file = output / filename
        if filename == 'translation_quality.json' and not source_file.exists():
            continue
        target = delivery / filename
        temporary = delivery / (filename + '.partial')
        temporary.unlink(missing_ok=True)
        try:
            os.link(source_file, temporary)
        except OSError:
            shutil.copy2(source_file, temporary)
        temporary.replace(target)
    return str(delivery)


def execute(identifier):
    started = time.monotonic()
    try:
        p = store.get(identifier)
        retry_history = list(p.get('retry_history', []))
        folder = store.ROOT / identifier
        manifest = p.get('timeline_manifest')
        if not manifest:
            try:
                manifest = timeline_manifest_from_srt((folder / 'original.srt').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                # Legacy projects may have no readable source file; lock their
                # currently saved timeline before continuing the pipeline.
                manifest = timeline_manifest(p['segments'])
            checkpoint(identifier, timeline_manifest=manifest)
            p['timeline_manifest'] = manifest
        validate_timeline(p['segments'], manifest)
        validate(p['segments'], p['duration'])
        if p.get('srt_kind') == 'source_zh' or (p.get('srt_kind') is None and any(has_chinese(s['text']) for s in p['segments'])):
            global _provider
            _provider = None
            import gc
            gc.collect()
            try:
                import torch
                torch.cuda.empty_cache()
            except ImportError:
                pass
        source_project = (p.get('srt_kind') == 'source_zh' or
                          (p.get('srt_kind') is None and any(has_chinese(s['text']) for s in p['segments'])))
        translated_project = source_project and all(not has_chinese(s['text']) for s in p['segments'])
        verified_translation = (translated_project and
            p.get('translation_quality', {}).get('mode') == 'gate_on_error' and
            p['translation_quality'].get('error_cues') == 0)
        if translated_project and not verified_translation:
            # A legacy run may have reached TTS with English glosses in its
            # subtitles. Resume from the preserved Chinese source and run the
            # current quality gate before using any cached voice clips.
            original_text = (folder / 'original.srt').read_text(encoding='utf-8')
            try:
                source_segments = parse_srt(original_text)
            except ValueError:
                source_segments = parse_srt_overspaced(original_text)
            validate_timeline(source_segments, manifest)
            p['segments'] = source_segments
            store.clear_translation_checkpoint(identifier)
        needs_translation = source_project and not verified_translation
        if needs_translation:
            # Publish the real active stage before the potentially long local-model call.
            checkpoint(identifier, status='translation', progress=0, error=None,
                       progress_detail={'phase': 'profile', 'completed': 0, 'total': 2,
                                        'message': 'Đang chuẩn bị phân tích phụ đề…'})
        if not needs_translation:
            translated_from = p.get('translated_from') if verified_translation else None
            checkpoint(identifier, progress=20,
                       progress_detail={'phase': 'translation', 'completed': len(p['segments']),
                                        'total': len(p['segments']), 'message': 'SRT đã dịch sẵn · bỏ qua bước dịch'})
        else:
            translation_quality = {}
            translation_attempt = {'value': 1}
            def translation_progress(update):
                store.save_translation_cues(identifier, update.get('cues', []))
                phase = update['phase']
                completed, total = update['completed'], update['total']
                ratio = min(1.0, completed / total) if total else 1.0
                ranges = {'profile': (0, 3), 'translation': (3, 15), 'quality': (15, 1),
                          'retry': (16, 2), 'review': (18, 1), 'done': (20, 0)}
                start, span = ranges.get(phase, (0, 0))
                checkpoint(identifier, status='translation', progress=round(start + span * ratio, 1),
                           progress_detail={'phase': phase, 'completed': completed, 'total': total,
                                            'attempt': translation_attempt['value'],
                                            'max_attempts': STAGE_RETRY_LIMIT,
                                            'message': update['message']})
            p['segments'], translated_from = retry_step(
                identifier, stage='translation', status='translation', progress=0,
                message='Đang dịch phụ đề…', retry_history=retry_history,
                on_attempt=lambda attempt: translation_attempt.update(value=attempt),
                operation=lambda: translate_segments(
                    p['segments'], p['locale'], translation_quality,
                    progress_callback=translation_progress,
                    resume_translations=store.translation_checkpoint(identifier)))
            validate_timeline(p['segments'], manifest)
            (folder / 'translation_quality.json').write_text(json.dumps(translation_quality, ensure_ascii=False, indent=2), encoding='utf-8')
            p['translation_quality'] = translation_quality
            translated_from = translated_from or p.get('translated_from')
        checkpoint(identifier, status='translation' if translated_from else ('tts' if p['audio_mode'] == 'voxcpm' else 'audio_mixing'),
                   segments=p['segments'], translated_from=translated_from,
                   translation_quality=p.get('translation_quality'), progress=20 if p['audio_mode'] == 'voxcpm' else 78,
                   progress_detail={'phase': 'tts' if p['audio_mode'] == 'voxcpm' else 'audio_mixing',
                                    'completed': 0, 'total': len(p['segments']),
                                    'message': 'Bắt đầu tạo giọng đọc…' if p['audio_mode'] == 'voxcpm' else 'Bắt đầu ghép âm…'})
        store.clear_translation_checkpoint(identifier)
        checkpoint(identifier, status='tts' if p['audio_mode'] == 'voxcpm' else 'audio_mixing', error=None)
        mix = folder / 'mix.wav'
        mix_warnings = []
        if p['audio_mode'] == 'voxcpm':
            provider = None
            reference = folder / 'reference.wav'
            if not reference.exists():
                reference = default_voice_path(p['locale'])
            voice_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
            model = os.environ.get('VOXCPM_MODEL_DIR', '')
            audio_files = []
            cache = folder / 'cache'
            cache.mkdir(exist_ok=True)
            def render_cue(index, segment):
                nonlocal provider
                key = audio_key(segment, voice_hash, model)
                audio = cache / (key + '.wav')
                raw = cache / (key + '.raw.wav')
                temp = cache / (key + '.partial.wav')
                if audio.exists() and valid_tts_wav(audio):
                    return audio
                audio.unlink(missing_ok=True)

                def generate():
                    nonlocal provider
                    raw.unlink(missing_ok=True)
                    temp.unlink(missing_ok=True)
                    if provider is None:
                        provider = voice_provider()
                    provider.synthesize(segment['text'], raw, reference)
                    media.normalize_wav(raw, temp)
                    if not valid_tts_wav(temp):
                        raise ValueError(f'WAV tạo ra ở dòng {segment["id"]} bị rỗng hoặc sai định dạng.')
                    temp.replace(audio)
                    raw.unlink(missing_ok=True)
                    return audio

                def reset_provider():
                    global _provider, _provider_path
                    nonlocal provider
                    provider = None
                    _provider = None
                    _provider_path = None
                    raw.unlink(missing_ok=True)
                    temp.unlink(missing_ok=True)

                return retry_step(identifier, stage='tts', status='tts',
                    progress=20 + index / max(1, len(p['segments'])) * 58,
                    message=f'Đang tạo giọng câu {index + 1:,}/{len(p["segments"]):,}',
                    operation=generate, cleanup=reset_provider, retry_history=retry_history)

            for index, segment in enumerate(p['segments']):
                checkpoint(identifier, progress=20 + index / len(p['segments']) * 58,
                           progress_detail={'phase': 'tts', 'completed': index, 'total': len(p['segments']),
                                            'attempt': 1, 'max_attempts': STAGE_RETRY_LIMIT,
                                            'message': f'Đã tạo giọng {index:,}/{len(p["segments"]):,} câu'})
                audio_files.append(render_cue(index, segment))

            # Prevent a broken TTS run from producing a valid-looking MP4 whose
            # different subtitle cues all contain the same first voice clip.
            for duplicate_pass in range(1, 3):
                by_fingerprint = {}
                for index, (segment, audio) in enumerate(zip(p['segments'], audio_files)):
                    fingerprint = wav_fingerprint(audio)
                    by_fingerprint.setdefault(fingerprint, []).append(index)
                duplicate_indices = sorted({index for indices in by_fingerprint.values()
                    if len({re.sub(r'\s+', ' ', p['segments'][i]['text']).strip().casefold() for i in indices}) >= 3
                    for index in indices})
                if not duplicate_indices:
                    break
                for index in duplicate_indices:
                    segment = p['segments'][index]
                    audio_files[index].unlink(missing_ok=True)
                    audio_files[index] = render_cue(index, segment)
            else:
                raise ValueError('Nhiều câu thoại khác nhau nhận cùng một đoạn giọng sau khi thử lại; dừng xuất để tránh video lặp lời đầu.')
            checkpoint(identifier, status='audio_mixing', progress=78,
                       progress_detail={'phase': 'audio_mixing', 'completed': 0, 'total': len(p['segments']),
                                        'message': 'Bắt đầu ghép các câu thoại vào timeline…'})
            mixing_attempt = {'value': 1}
            def mixing_progress(completed, total):
                checkpoint(identifier, status='audio_mixing', progress=78 + (4 * completed / total if total else 4),
                           progress_detail={'phase': 'audio_mixing', 'completed': completed, 'total': total,
                                            'attempt': mixing_attempt['value'],
                                            'max_attempts': STAGE_RETRY_LIMIT,
                                            'message': f'Đang ghép âm {completed:,}/{total:,} câu'})
            def clean_mix_partials():
                mix.with_suffix('.partial.pcm').unlink(missing_ok=True)
                mix.with_suffix('.partial.wav').unlink(missing_ok=True)
            mix_warnings = retry_step(identifier, stage='audio_mixing', status='audio_mixing',
                progress=78, message='Đang ghép các câu thoại vào timeline…', retry_history=retry_history,
                on_attempt=lambda attempt: mixing_attempt.update(value=attempt),
                operation=lambda: mix_dialogue(p['segments'], audio_files, mix, p['duration'],
                                               checkpoint=mixing_progress),
                cleanup=clean_mix_partials)
        else:
            # User explicitly confirms this full-length track is already aligned.
            retry_step(identifier, stage='audio_mixing', status='audio_mixing', progress=78,
                message='Đang chuẩn hóa âm thanh đã căn sẵn…', retry_history=retry_history,
                operation=lambda: media.normalize_wav(folder / 'approved.wav', mix),
                cleanup=lambda: mix.with_suffix('.partial.wav').unlink(missing_ok=True))
        def qa_audio():
            actual_duration, streams = media.probe(mix)
            if abs(actual_duration - p['duration']) > .25:
                raise ValueError('WAV phải khớp thời lượng video (sai lệch tối đa 0,25 giây).')
            if not any(stream.get('codec_type') == 'audio' for stream in streams):
                raise ValueError('Âm thanh đầu ra không có luồng audio hợp lệ.')
            return actual_duration
        retry_step(identifier, stage='qa', status='qa', progress=85,
                   message='Đang kiểm tra âm thanh và thời lượng…', retry_history=retry_history,
                   operation=qa_audio)
        output = folder / 'output'
        output.mkdir(exist_ok=True)
        validate_timeline(p['segments'], manifest)
        video_output = output / 'video.mp4'
        retry_step(identifier, stage='mux', status='mux', progress=92,
                   message='Đang xuất MP4 bàn giao…', retry_history=retry_history,
                   operation=lambda: media.mux(folder / 'source.mp4', mix, video_output, p['duration']),
                   cleanup=lambda: video_output.with_suffix('.partial.mp4').unlink(missing_ok=True))
        srt_output = serialize(p['segments'])
        validate_timeline(parse_srt(srt_output), manifest)
        (output / 'subtitles.srt').write_text(srt_output, encoding='utf-8')
        (output / 'source.srt').write_text((folder / 'original.srt').read_text(encoding='utf-8'), encoding='utf-8')
        if p.get('translation_quality'):
            (output / 'translation_quality.json').write_text(json.dumps(p['translation_quality'], ensure_ascii=False, indent=2), encoding='utf-8')
        report = dict(duration=p['duration'], segments=len(p['segments']), api_cost_usd=0,
                      voice=p.get('voice', 'approved'),
                      channel_ids=p.get('channel_ids', []),
                      skipped=['asr'] + (['translation'] if not translated_from else []) + (['tts'] if p['audio_mode'] == 'approved' else []),
                      translated_from=translated_from,
                      elapsed_seconds=round(time.monotonic() - started, 2), warnings=p['warnings'] + mix_warnings,
                      retry_history=retry_history,
                      translation_flags={str(s['id']): s['translation_flags'] for s in p['segments'] if s.get('translation_flags')},
                      audio_policy='replace original audio', picture='stream copy')
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        delivery = deliver_project(p, output)
        if delivery:
            report['delivery_folder'] = delivery
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            # Keep the delivered report in sync with the project report.
            (Path(delivery) / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        checkpoint(identifier, status='completed', progress=100,
                   progress_detail={'phase': 'completed', 'completed': 1, 'total': 1,
                                    'message': 'Đã hoàn tất video và lưu thư mục bàn giao'}, report=report,
                   warnings=report['warnings'])
    except InterruptedError:
        pass
    except Exception as exc:
        with lock:
            p = store.get(identifier)
            if p['status'] not in ('paused', 'canceled'):
                if 'translation_quality' in locals() and translation_quality:
                    p['translation_quality'] = translation_quality
                    (folder / 'translation_quality.json').write_text(
                        json.dumps(translation_quality, ensure_ascii=False, indent=2), encoding='utf-8')
                p.update(status='needs_attention' if isinstance(exc, ValueError) else 'failed',
                         error=str(exc)[:2000])
                store.save(p)


def enqueue(identifier):
    with lock:
        if identifier in futures and not futures[identifier].done():
            raise ValueError('Tác vụ đang kết thúc bước hiện tại; vui lòng đợi rồi tiếp tục.')
        p = store.get(identifier)
        if p['status'] in ACTIVE:
            raise ValueError('Dự án đang được xử lý.')
        p.update(status='queued', error=None)
        store.save(p)
        futures[identifier] = pool.submit(execute, identifier)
