"""Chinese SRT translation through the selected local Gemma 4 Ollama model."""
import json
import os
import re
from pathlib import Path

import httpx

from .locales import LOCALES
from .translation_quality import (build_profile, build_locale_profile, build_source_profile,
    vocabulary, audit, audit_profile_consistency)
import time

CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
MODEL = os.getenv('TRANSLATION_MODEL', 'gemma4:12b-it-q4_K_M')
OLLAMA = os.getenv('OLLAMA_BASE_URL', 'http://192.168.1.210:11434').rstrip('/')
try:
    BATCH_SIZE = max(4, min(24, int(os.getenv('TRANSLATION_BATCH_SIZE', '16'))))
except ValueError:
    BATCH_SIZE = 16
PROFILES = Path(__file__).resolve().parents[1] / 'data' / 'translation_quality' / 'style_profiles.json'
GLOSSARY = Path(os.environ['TRANSLATION_GLOSSARY']) if os.getenv('TRANSLATION_GLOSSARY') else None
FLAGS = ('unknown_name', 'ambiguous_kinship', 'fragment', 'unsure', 'asr_suspect', 'name_unverified')
OUTPUT_SCHEMA = {
    'type': 'object', 'properties': {'cues': {'type': 'array', 'items': {
        'type': 'object', 'properties': {
            'id': {'type': 'integer'}, 'text': {'type': 'string'},
            'flags': {'type': 'array', 'items': {'type': 'string', 'enum': list(FLAGS)}}},
        'required': ['id', 'text', 'flags'], 'additionalProperties': False}}},
    'required': ['cues'], 'additionalProperties': False,
}
REVIEW_SCHEMA = {
    'type': 'object', 'properties': {'cues': {'type': 'array', 'items': {
        'type': 'object', 'properties': {
            'id': {'type': 'integer'}, 'action': {'type': 'string', 'enum': ['keep', 'revise']},
            'text': {'type': 'string'}, 'reason': {'type': 'string'}},
        'required': ['id', 'action', 'text', 'reason'], 'additionalProperties': False}}},
    'required': ['cues'], 'additionalProperties': False,
}


def has_chinese(text):
    return bool(CJK.search(text))


def model_ready():
    try:
        with httpx.Client(timeout=4) as client:
            response = client.get(f'{OLLAMA}/api/tags')
            response.raise_for_status()
            return any(m.get('name') == MODEL or m.get('model') == MODEL for m in response.json().get('models', []))
    except (httpx.HTTPError, ValueError):
        return False


def _style(locale):
    profiles = json.loads(PROFILES.read_text(encoding='utf-8'))['profiles']
    p = profiles.get(locale)
    if not p:
        # Conservative draft defaults keep all supported locales on a consistent quality floor.
        # Language-specific honorifics remain model/context driven until native review is available.
        rules = [
            '- Draft subtitle profile: use natural, concise ' + LOCALES[locale][0] + ' suitable for spoken dialogue.',
            '- Preserve every source fact, speaker intent, name, number, negation, and relationship.',
            '- Use standard spelling and punctuation for the target locale; do not mix writing systems.',
            '- Do not infer speaker gender, social rank, or family relationships without context.',
            '- Keep recurring names and terms consistent with the project glossary.',
            '- This profile is an unreviewed baseline, not a native-speaker-approved style guide.',
        ]
        if locale == 'vi-VN':
            rules += [
                '- Translate into Vietnamese throughout; never insert English glosses or English-translated phrases.',
                '- Render Chinese names with conventional Hán-Việt readings when clear; never leave Mandarin pinyin.',
                '- Translate titles and forms of address into natural Vietnamese.',
            ]
        return '\n'.join(rules)
    rules = [p['register'], p['kinship_policy'], p['proper_name_policy']]
    rules += p['pronouns_and_politeness'] + p['subtitle_policy']
    rules += ['Preserve every source fact, speaker intent, name, number, negation, and relationship.',
              'Do not infer speaker gender or social rank without clear context.']
    return '\n'.join(f'- {rule}' for rule in rules)


def _glossary(locale, batch):
    if locale != 'th-TH' or GLOSSARY is None or not GLOSSARY.is_file():
        return ''
    names = json.loads(GLOSSARY.read_text(encoding='utf-8'))['names']
    source = ' '.join(s['text'] for s in batch)
    return '\n'.join(f"{n['source']} = {n['canonical']}" for n in names if n['source'] in source)


def _terms(locale, batch):
    profile = json.loads(PROFILES.read_text(encoding='utf-8'))['profiles'].get(locale, {})
    source = ' '.join(s['text'] for s in batch)
    return '\n'.join(f'{term} = {target}' for term, target in profile.get('terms', {}).items() if term in source)


def _translate_batch(client, batch, locale, before=(), after=(), profile=None, retry_hint='', source_profile=None):
    language = LOCALES[locale][0]
    source = [{'id': s['id'], 'text': s['text'],
               'max_chars': max(12, min(80, round((s['end'] - s['start']) * 18)))} for s in batch]
    context = {'context_before': [{'id': s['id'], 'text': s['text']} for s in before],
               'cues': source,
               'context_after': [{'id': s['id'], 'text': s['text']} for s in after]}
    voice_profile = os.getenv('TRANSLATION_VOICE_PROFILE', 'Unknown speaker; do not infer gender or add gendered particles without evidence.')
    name_rendering_rule = (
        'For Vietnamese, use established Hán-Việt readings for Chinese names when clear; never leave Mandarin pinyin. '
        if locale == 'vi-VN' else
        'Use the project glossary and the conventional name style for this locale; preserve established romanized names only when customary.'
    )
    prompt = (
        f'Translate Chinese subtitle cues into natural {language} ({locale}). '
        'Return exactly one translation per input ID as JSON with cues containing id, text, flags. '
        'Preserve IDs and order. Never merge, omit, split or reorder cues. '
        'Cues are fragments of continuous speech. Translate each cue own words only; '
        'never move words between cues. Keep incomplete fragments incomplete and flag fragment. '
        'Context before and after is for understanding only: do not translate or output it. '
        'Meaning comes first. Shorten wording only when no meaning is lost. '
        'Never drop a person, number, negation, or named group to fit max_chars. '
        'Never reverse meaning. Preserve meaning if max_chars cannot be met. '
        'Never split a target-language word between cues. Flag unsure if the source cuts a word. '
        'Do not silently correct ambiguous ASR; flag asr_suspect. '
        'Write the translation in the requested target language throughout. Do not insert English translations, '
        'or English glosses into a non-English target sentence. Use the project glossary when available. '
        + name_rendering_rule + ' Keep one consistent localized spelling. Any English meaning in project notes is for understanding '
        'only: translate it into the target language and never copy it into the subtitle. '
        + ('Japanese kanji is allowed; do not output Chinese sentences or pinyin. ' if locale == 'ja-JP'
           else 'Do not leave Chinese characters or pinyin. ') +
        'No explanations, speaker labels or notes. '
        f'Allowed flags: {", ".join(FLAGS)}. Use an empty list when confident.\n'
        f'Voice profile: {voice_profile}\nLocale rules:\n{_style(locale)}\n'
        f'Names (use exactly):\n{_glossary(locale, batch)}\n'
        f'Terms (use exactly):\n{_terms(locale, batch)}\n'
        f'Project vocabulary and meaning anchors (keep translations in target-language script):\n{vocabulary(profile, batch, source_profile)}\n'
        f'Setting observations (not speaker labels):\n{json.dumps((profile or {}).get("setting_notes", [])[:3], ensure_ascii=False)}\n'
        f'Retry instructions: {retry_hint}\n'
        f'Input:\n{json.dumps(context, ensure_ascii=False)}'
    )
    response = client.post(f'{OLLAMA}/api/chat', json={
        'model': MODEL, 'stream': False, 'format': OUTPUT_SCHEMA, 'think': False,
        'messages': [{'role': 'user', 'content': prompt}],
        'options': {'temperature': 0.1, 'num_ctx': 4096, 'num_predict': 2048},
    })
    response.raise_for_status()
    raw = response.json()['message']['content']
    items = json.loads(raw)['cues']
    expected = [s['id'] for s in batch]
    if not isinstance(items, list) or [item.get('id') for item in items] != expected:
        raise ValueError(f'Gemma trả thiếu hoặc lệch ID phụ đề: {expected}')
    result = []
    for original, item in zip(batch, items):
        text = item.get('text')
        if not isinstance(text, str) or not text.strip() or (locale != 'ja-JP' and has_chinese(text)):
            raise ValueError(f'Bản dịch dòng {original["id"]} trống hoặc còn chữ Trung.')
        flags = item.get('flags')
        if not isinstance(flags, list) or any(flag not in FLAGS for flag in flags):
            raise ValueError(f'Cờ kiểm tra không hợp lệ tại dòng {original["id"]}.')
        result.append((text.strip(), flags))
    return result


def _review_batch(client, candidates, source, locale):
    language = LOCALES[locale][0]
    prompt = (
        f'Quality-review {language} subtitle translations against the Chinese source. '
        'Keep an acceptable translation unchanged. Revise only a clear meaning error, omitted named entity, '
        'wrong number, wrong negation, or obvious ASR-context mistake. Do not rewrite for stylistic preference. '
        'Never invent facts or silently change the Chinese source. Context is reference only. '
        'Return exactly the candidate IDs in order as JSON; for keep, copy the existing translation exactly. '
        'For revise, write a concise natural translation with the same meaning. Explain reason briefly in English.\n'
        + json.dumps({'cues': candidates}, ensure_ascii=False))
    response = client.post(f'{OLLAMA}/api/chat', json={
        'model': MODEL, 'stream': False, 'format': REVIEW_SCHEMA, 'think': False,
        'messages': [{'role': 'user', 'content': prompt}],
        'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2048},
    })
    response.raise_for_status()
    items = json.loads(response.json()['message']['content'])['cues']
    if [item.get('id') for item in items] != [cue['id'] for cue in candidates]:
        raise ValueError('Kiểm định dịch trả thiếu hoặc lệch ID cue.')
    return items


def translate_segments(segments, locale, quality_report=None, progress_callback=None, resume_translations=None):
    if locale not in LOCALES:
        raise ValueError(f'Ngôn ngữ đầu ra không hỗ trợ: {locale}')
    pending = [i for i, segment in enumerate(segments) if has_chinese(segment['text'])]
    if not pending:
        return segments, None
    if not model_ready():
        raise ValueError(f'Chưa kết nối được Ollama hoặc thiếu model {MODEL} tại {OLLAMA}.')
    translated = [dict(s) for s in segments]
    resume_translations = resume_translations or {}
    completed_before = 0
    for index in pending:
        cached = resume_translations.get(str(segments[index]['id']))
        if isinstance(cached, dict) and isinstance(cached.get('text'), str) and cached['text'].strip():
            translated[index]['text'] = cached['text']
            translated[index]['translation_flags'] = cached.get('translation_flags', [])
            completed_before += 1
    remaining = [index for index in pending if str(segments[index]['id']) not in resume_translations]
    started = time.monotonic()
    def report_progress(phase, completed, total, message, cues=None):
        if progress_callback:
            progress_callback({'phase': phase, 'completed': completed, 'total': total,
                               'message': message, 'cues': cues or []})

    with httpx.Client(timeout=180) as client:
        report_progress('profile', 0, 2, 'Đang phân tích nội dung và thuật ngữ…')
        source_profile = build_source_profile(client, OLLAMA, MODEL, segments)
        report_progress('profile', 1, 2, 'Đã phân tích nguồn · đang lập hồ sơ ngôn ngữ…')
        profile = (build_locale_profile(client, OLLAMA, MODEL, segments, locale, source_profile)
                   if source_profile.get('entries') else build_profile(client, OLLAMA, MODEL, segments, locale))
        report_progress('translation', completed_before, len(pending),
                        f'Tiếp tục dịch · đã có {completed_before:,}/{len(pending):,} câu')
        translation_started = time.monotonic()
        remaining_batches = []
        for index in remaining:
            if (not remaining_batches or len(remaining_batches[-1]) >= BATCH_SIZE or
                    index != remaining_batches[-1][-1] + 1):
                remaining_batches.append([])
            remaining_batches[-1].append(index)
        newly_completed = 0
        for indices in remaining_batches:
            batch = [segments[i] for i in indices]
            before = segments[max(0, indices[0] - 3):indices[0]]
            after = segments[indices[-1] + 1:indices[-1] + 3]
            try:
                texts = _translate_batch(client, batch, locale, before, after, profile,
                                         source_profile=source_profile)
            except (ValueError, KeyError, httpx.HTTPError):
                texts = [_translate_batch(client, [segment], locale,
                         segments[max(0, index - 3):index], segments[index + 1:index + 3], profile,
                         source_profile=source_profile)[0]
                         for index, segment in zip(indices, batch)]
            for index, (text, flags) in zip(indices, texts):
                translated[index]['text'] = text
                translated[index]['translation_flags'] = flags
            newly_completed += len(indices)
            completed = completed_before + newly_completed
            cues = [{'id': segments[index]['id'], 'text': translated[index]['text'],
                     'translation_flags': translated[index].get('translation_flags', [])} for index in indices]
            report_progress('translation', completed, len(pending),
                            f'Đã dịch {completed:,}/{len(pending):,} câu', cues=cues)
        translation_seconds = time.monotonic() - translation_started
        report_progress('quality', 0, 1, 'Đang rà soát độ chính xác bản dịch…')
        before_issues = audit(segments, translated, locale, source_profile)
        retry_started = time.monotonic()
        retries = []
        retry_indices = [index for index in pending if any(
            issue['cue'] == segments[index]['id'] and issue['severity'] == 'error' for issue in before_issues)]
        retry_batches = []
        for index in retry_indices:
            if (not retry_batches or len(retry_batches[-1]) >= BATCH_SIZE or
                    index != retry_batches[-1][-1] + 1):
                retry_batches.append([])
            retry_batches[-1].append(index)
        retry_completed = 0
        retry_language_rule = ('Use Vietnamese Hán-Việt names where clear; remove all English glosses and Mandarin pinyin.'
                               if locale == 'vi-VN' else
                               f'Write only natural {LOCALES[locale][0]}; remove untranslated English glosses and use the locale\'s accepted name rendering.')
        for indices in retry_batches:
            errors = [issue for issue in before_issues
                      if issue['cue'] in {segments[index]['id'] for index in indices}
                      and issue['severity'] == 'error']
            candidates = [segments[index] for index in indices]
            texts = _translate_batch(client, candidates, locale,
                segments[max(0, indices[0] - 3):indices[0]],
                segments[indices[-1] + 1:indices[-1] + 3], profile,
                'Fix every listed cue error. ' + retry_language_rule + ' '
                'Use the Chinese source and nearby context. Issues: ' + json.dumps(errors, ensure_ascii=False),
                source_profile)
            cues = []
            for index, (text, flags) in zip(indices, texts):
                candidate = {**translated[index], 'text': text, 'translation_flags': flags}
                candidate_issues = audit([segments[index]], [candidate], locale, source_profile)
                accepted = not any(i['severity'] == 'error' for i in candidate_issues)
                retries.append({'cue': segments[index]['id'], 'accepted': accepted})
                if accepted:
                    translated[index] = candidate
                cues.append({'id': segments[index]['id'], 'text': translated[index]['text'],
                             'translation_flags': translated[index].get('translation_flags', [])})
                retry_completed += 1
            report_progress('retry', retry_completed, len(retry_indices),
                            f'Đang sửa câu cần kiểm tra {retry_completed:,}/{len(retry_indices):,}', cues=cues)
        # A second pass is limited to explicit ASR uncertainty and high-confidence source warnings.
        # It is deliberately not run on every fragment or stylistic warning.
        review_ids = set()
        for index in pending:
            cue_id = segments[index]['id']
            flags = set(translated[index].get('translation_flags', []))
            if 'asr_suspect' in flags or any(token in segments[index]['text'] for token in ('偷装', '老弱妇璃', '保息')):
                review_ids.add(index)
        review_log = []
        review_started = time.monotonic()
        review_indices = sorted(review_ids)
        report_progress('review', 0, len(review_indices),
                        f'Đang rà soát sâu {len(review_indices):,} câu nghi vấn…')
        for offset in range(0, len(review_indices), 8):
            indices = review_indices[offset:offset + 8]
            candidates = []
            for index in indices:
                cue = segments[index]
                candidates.append({'id': cue['id'], 'source': cue['text'],
                    'translation': translated[index]['text'],
                    'context_before': [s['text'] for s in segments[max(0, index - 2):index]],
                    'context_after': [s['text'] for s in segments[index + 1:index + 3]],
                    'flags': translated[index].get('translation_flags', [])})
            try:
                reviewed = _review_batch(client, candidates, segments, locale)
            except (ValueError, KeyError, httpx.HTTPError) as error:
                review_log.append({'cues': [segments[i]['id'] for i in indices], 'error': str(error)[:300]})
                completed = min(offset + len(indices), len(review_indices))
                report_progress('review', completed, len(review_indices),
                                f'Đã rà soát {completed:,}/{len(review_indices):,} câu nghi vấn')
                continue
            for index, item in zip(indices, reviewed):
                old_text = translated[index]['text']
                new_text = item['text'].strip()
                changed = item['action'] == 'revise' and new_text and new_text != old_text
                candidate = {**translated[index], 'text': new_text}
                if changed:
                    candidate['translation_flags'] = [flag for flag in candidate.get('translation_flags', [])
                                                      if flag != 'asr_suspect']
                valid = changed and (locale == 'ja-JP' or not has_chinese(new_text)) and not any(
                    issue['severity'] == 'error' for issue in audit([segments[index]], [candidate], locale, source_profile))
                if valid:
                    translated[index] = candidate
                review_log.append({'cue': segments[index]['id'], 'changed': bool(valid),
                    'reason': item['reason'][:300]})
            completed = min(offset + len(indices), len(review_indices))
            report_progress('review', completed, len(review_indices),
                            f'Đã rà soát {completed:,}/{len(review_indices):,} câu nghi vấn',
                            cues=[{'id': segments[index]['id'], 'text': translated[index]['text'],
                                   'translation_flags': translated[index].get('translation_flags', [])}
                                  for index in indices])
        targeted_review_seconds = time.monotonic() - review_started
        # Try one isolated translation without any project vocabulary when a
        # bad glossary or batch context keeps reproducing the same leak.
        unresolved = {issue['cue'] for issue in audit(segments, translated, locale, source_profile)
                      if issue['severity'] == 'error'}
        isolated_retries = []
        for index in pending:
            cue_id = segments[index]['id']
            if cue_id not in unresolved:
                continue
            try:
                text, flags = _translate_batch(client, [segments[index]], locale,
                    segments[max(0, index - 3):index], segments[index + 1:index + 3],
                    profile={'locale': locale, 'entries': [], 'setting_notes': []},
                    retry_hint='Translate this one Chinese cue independently. No English or pinyin. '
                               'Preserve its exact meaning and do not copy words from neighboring cues.',
                    source_profile=None)[0]
                candidate = {**translated[index], 'text': text, 'translation_flags': flags}
                accepted = not any(issue['severity'] == 'error' for issue in
                                   audit([segments[index]], [candidate], locale, source_profile))
                if accepted:
                    translated[index] = candidate
                isolated_retries.append({'cue': cue_id, 'accepted': accepted})
                if accepted:
                    report_progress('retry', len(isolated_retries), len(unresolved),
                                    f'Đã sửa riêng {len(isolated_retries):,}/{len(unresolved):,} câu',
                                    cues=[{'id': cue_id, 'text': text, 'translation_flags': flags}])
            except (ValueError, KeyError, httpx.HTTPError) as error:
                isolated_retries.append({'cue': cue_id, 'accepted': False, 'error': str(error)[:200]})
        issues = audit(segments, translated, locale, source_profile)
        consistency_issues = audit_profile_consistency(segments, translated, profile)
        issues.extend(consistency_issues)
        hard_errors = sorted({issue['cue'] for issue in issues if issue['severity'] == 'error'})
        if not hard_errors:
            report_progress('done', len(pending), len(pending), 'Đã dịch và rà soát xong phụ đề')
    if quality_report is not None:
        review_by_cue = {}
        for issue in issues:
            if issue['severity'] in ('warn', 'error'):
                review_by_cue.setdefault(issue['cue'], set()).add(issue['rule'])
        quality_report.update({'model': MODEL, 'locale': locale, 'profile': profile,
            'profile_seconds': profile['elapsed_seconds'], 'translation_seconds': round(translation_seconds, 2),
            'retry_seconds': round(time.monotonic() - retry_started, 2),
            'total_seconds': round(time.monotonic() - started, 2), 'retries': retries,
            'targeted_review_seconds': round(targeted_review_seconds, 2),
            'targeted_review': review_log,
            'issues': issues, 'mode': 'gate_on_error', 'source_profile': source_profile,
            'isolated_retries': isolated_retries,
            'profile_consistency_issues': consistency_issues,
            'source_profile_cache_hit': source_profile.get('cache_hit', False),
            'source_profile_seconds': source_profile.get('elapsed_seconds', 0),
            'batch_size': BATCH_SIZE,
            'profile_cache_hit': profile.get('cache_hit', False),
            'review_cues': [{'cue': cue, 'rules': sorted(rules)} for cue, rules in sorted(review_by_cue.items())],
            'error_cues': len({i['cue'] for i in issues if i['severity'] == 'error'})})
    if hard_errors:
        preview = ', '.join(str(cue) for cue in hard_errors[:12])
        raise ValueError(f'Còn {len(hard_errors)} câu dịch lỗi nặng ({preview}); đã dừng trước khi tạo giọng và xuất video. Vui lòng kiểm tra báo cáo dịch.')
    return translated, 'zh'
