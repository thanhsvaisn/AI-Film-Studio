"""Project-specific vocabulary and language-neutral translation audit.

Model-proposed vocabulary is provisional. Evidence is checked against the source;
confidence scores are model claims, not independently measured probabilities.
"""
import json
import hashlib
import re
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

PROFILE_SCHEMA = {'type': 'object', 'properties': {
    'setting': {'type': 'string'},
    'entries': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'source': {'type': 'string'}, 'target': {'type': 'string'},
        'kind': {'type': 'string', 'enum': ['name', 'term']},
        'meaning': {'type': 'string'}, 'evidence_ids': {'type': 'array', 'items': {'type': 'integer'}}},
        'required': ['source', 'target', 'kind', 'meaning', 'evidence_ids'], 'additionalProperties': False}}},
    'required': ['setting', 'entries'], 'additionalProperties': False}
SOURCE_PROFILE_SCHEMA = {'type': 'object', 'properties': {
    'setting': {'type': 'string'},
    'entries': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'source': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['name', 'term']},
        'meaning': {'type': 'string'}, 'evidence_ids': {'type': 'array', 'items': {'type': 'integer'}}},
        'required': ['source', 'kind', 'meaning', 'evidence_ids'], 'additionalProperties': False}}},
    'required': ['setting', 'entries'], 'additionalProperties': False}

# Meanings are independent of target language. Thai wording remains a draft.
SEMANTIC_TERMS = {
    '愚孝': {'meaning': 'blind or foolish filial obedience; NOT lack of filial piety',
             'th-TH': 'กตัญญูอย่างงมงาย', 'forbid_th': ['ไม่กตัญญู', 'อกตัญญู', 'เนรคุณ']},
    '流民': {'meaning': 'displaced people/refugees fleeing upheaval or famine, not ordinary villagers', 'th-TH': 'ผู้อพยพ'},
    '逃荒': {'meaning': 'leave home to flee famine; preserve both fleeing and famine'},
    '村长': {'meaning': 'village head', 'th-TH': 'ผู้ใหญ่บ้าน'},
    '老弱妇孺': {'meaning': 'all four groups: old people, weak people, women, and children'},
    '死期': {'meaning': 'the time of death / final day, not a death anniversary',
             'vi-VN': 'ngày tận số', 'forbid_vi': ['ngày giỗ', 'giáp trần']},
}
NATIVE_SCRIPT = {'th-TH': r'[\u0e00-\u0e7f]', 'hi-IN': r'[\u0900-\u097f]',
                 'ja-JP': r'[\u3040-\u30ff\u3400-\u9fff]', 'ko-KR': r'[\uac00-\ud7af]',
                 'ar-SA': r'[\u0600-\u06ff]', 'ru-RU': r'[\u0400-\u04ff]'}
SOURCE_REVIEW_TOKENS = ('偷装', '老弱妇璃', '保息', '一员破猫', '一是破猫', '老工')
PROFILE_CACHE = Path(__file__).resolve().parents[1] / 'data' / 'translation_quality' / 'profile_cache'
SOURCE_PROFILE_CACHE = Path(__file__).resolve().parents[1] / 'data' / 'translation_quality' / 'source_profile_cache'


def adjacent_source_candidates(segments, threshold=0.7, min_length=2):
    """Return near-duplicate neighboring source cues for human ASR review only."""
    candidates = []
    for left, right in zip(segments, segments[1:]):
        a = re.sub(r'[^\w]', '', left['text'], flags=re.UNICODE)
        b = re.sub(r'[^\w]', '', right['text'], flags=re.UNICODE)
        if min(len(a), len(b)) < min_length:
            continue
        similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
        if similarity >= threshold:
            candidates.append({'left_id': left['id'], 'right_id': right['id'],
                               'similarity': round(similarity, 3),
                               'left_source': left['text'], 'right_source': right['text']})
    return candidates


def audit_profile_consistency(source, translated, profile):
    """Flag missing or inconsistent recurring names/terms; never auto-normalize wording."""
    target_by_id = {row['id']: row['text'] for row in translated}
    findings = []
    for entry in (profile or {}).get('entries', []):
        source_form, target_form = entry.get('source', ''), entry.get('target', '')
        if not source_form or not target_form or entry.get('kind') not in ('name', 'term'):
            continue
        for row in source:
            if source_form not in row['text']:
                continue
            translated_text = target_by_id.get(row['id'], '')
            if target_form not in translated_text:
                findings.append({'cue': row['id'], 'rule': 'profile_term_missing', 'severity': 'warn',
                    'source_term': source_form, 'expected_form': target_form,
                    'translation': translated_text})
    return findings


def evaluate_golden_set(golden, translated):
    """Score only manually approved cue references; this is a regression signal, not a semantic judge."""
    items = golden.get('items', [])
    if golden.get('review_status') != 'reviewed':
        raise ValueError('Bộ câu chuẩn cần review_status=reviewed trước khi chấm.')
    if not items:
        raise ValueError('Bộ câu chuẩn chưa có cue.')
    actual = {row['id']: row['text'] for row in translated}
    results = []
    for item in items:
        reference = item.get('approved_translation', '').strip()
        if not reference or item.get('source_language') != 'zh' or not item.get('source_text', '').strip():
            raise ValueError(f"Cue chuẩn chưa đủ dữ liệu: {item.get('id', '?')}")
        candidate = actual.get(item.get('cue_id'), '')
        norm = lambda value: re.sub(r'\s+', '', value).casefold()
        a, b = norm(reference), norm(candidate)
        ratio = SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0
        results.append({'golden_id': item.get('id'), 'cue_id': item.get('cue_id'),
            'exact_match': bool(a and a == b), 'character_similarity': round(ratio, 4),
            'candidate': candidate, 'approved_translation': reference})
    return {'locale': golden.get('locale', ''), 'items': len(results),
        'exact_matches': sum(row['exact_match'] for row in results),
        'mean_character_similarity': round(sum(row['character_similarity'] for row in results) / len(results), 4),
        'results': results,
        'note': 'Similarity is a regression aid; a low score may still be a valid paraphrase and needs reviewer judgment.'}


def _profile_cache_key(segments, locale, model):
    canonical = json.dumps({'schema': 1, 'locale': locale, 'model': model,
        'segments': [(s['id'], s['start'], s['end'], s['text']) for s in segments]},
        ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def build_source_profile(client, endpoint, model, segments):
    """Extract language-neutral names, terms and setting once; never edits source cues."""
    started = time.monotonic()
    key = _profile_cache_key(segments, 'source-zh', model)
    cache_path = SOURCE_PROFILE_CACHE / f'{key}.json'
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        cached['cache_hit'] = True
        cached['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return cached
    proposals = defaultdict(list)
    settings, errors, rejected = [], [], []
    for offset in range(0, len(segments), 80):
        chunk = segments[offset:offset + 80]
        cue_map = {row['id']: row['text'] for row in chunk}
        prompt = ('Analyze these Chinese drama subtitles. Identify recurring character names and plot-specific terms. '
                  'For each, give a concise English meaning, exact Chinese spelling, kind, and cue IDs that contain it. '
                  'Do not infer gender or relationships without direct evidence. Do not correct ASR or rewrite subtitles. '
                  'Report setting only when supported; otherwise say uncertain. Return structured JSON.\n' +
                  json.dumps(chunk, ensure_ascii=False))
        try:
            response = client.post(endpoint + '/api/chat', json={'model': model, 'stream': False,
                'think': False, 'format': SOURCE_PROFILE_SCHEMA,
                'messages': [{'role': 'user', 'content': prompt}],
                'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2048}})
            response.raise_for_status()
            data = json.loads(response.json()['message']['content'])
            settings.append(data['setting'])
            for entry in data['entries']:
                word = entry.get('source', '').strip()
                evidence = [i for i in entry.get('evidence_ids', []) if i in cue_map and word and word in cue_map[i]]
                if not word or not entry.get('meaning', '').strip() or not evidence:
                    rejected.append(entry)
                    continue
                proposals[(entry['kind'], word)].append({**entry, 'source': word, 'evidence_ids': evidence})
        except Exception as error:
            errors.append({'offset': offset, 'error': str(error)})
    entries = []
    for (kind, word), rows in proposals.items():
        meanings = Counter(row['meaning'].strip() for row in rows)
        meaning = meanings.most_common(1)[0][0]
        entries.append({'source': word, 'kind': kind, 'meaning': meaning,
            'evidence_ids': sorted({cue for row in rows for cue in row['evidence_ids']}),
            'occurrences': sum(row['text'].count(word) for row in segments),
            'status': 'provisional', 'meaning_variants': dict(meanings),
            'conflict': len(meanings) > 1})
    result = {'setting': settings[:8], 'entries': entries, 'errors': errors,
              'rejected_entries': rejected, 'cache_hit': False,
              'elapsed_seconds': round(time.monotonic() - started, 2)}
    if not errors:
        SOURCE_PROFILE_CACHE.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix('.partial')
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        temporary.replace(cache_path)
    return result


def build_profile(client, endpoint, model, segments, locale, on_progress=None):
    started = time.monotonic()
    cache_path = PROFILE_CACHE / f'{_profile_cache_key(segments, locale, model)}.json'
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        cached['cache_hit'] = True
        cached['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return cached
    proposals = defaultdict(list)
    settings, rejected, errors = [], [], []
    for offset in range(0, len(segments), 80):
        chunk = segments[offset:offset + 80]
        by_id = {s['id']: s['text'] for s in chunk}
        prompt = (
            f'Analyze these Chinese drama subtitles for translation into {locale}. '
            'Extract recurring character names and important terms. Provide one consistent target-language spelling, '
            'a short English meaning, and exact cue IDs containing the Chinese source spelling. '
            f'The target field MUST be written in the native writing system of {locale}; '
            'only the meaning field is English. For Thai use Thai characters, for Japanese use Japanese characters, '
            'for Arabic use Arabic characters. Never put romanized Chinese names in target for a non-Latin locale. '
            'Do not invent characters, gender or relationships. Do not translate whole sentences. '
            'Setting must describe uncertainty if the genre is unclear. Return JSON setting and entries.\n'
            + json.dumps([{'id': s['id'], 'text': s['text']} for s in chunk], ensure_ascii=False))
        try:
            r = client.post(endpoint + '/api/chat', json={'model': model, 'stream': False,
                'think': False, 'format': PROFILE_SCHEMA,
                'messages': [{'role': 'user', 'content': prompt}],
                'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2048}})
            r.raise_for_status()
            data = json.loads(r.json()['message']['content'])
            settings.append(data['setting'])
            for entry in data['entries']:
                word = entry.get('source', '')
                evidence = [i for i in entry.get('evidence_ids', []) if i in by_id and word and word in by_id[i]]
                target = entry.get('target', '').strip()
                wrong_script = (locale != 'ja-JP' and bool(re.search(r'[\u3400-\u9fff]', target))) or (
                    locale in NATIVE_SCRIPT and (not re.search(NATIVE_SCRIPT[locale], target) or re.search(r'[A-Za-z]', target)))
                if not evidence or not target or wrong_script:
                    rejected.append(entry)
                    continue
                proposals[(entry['kind'], word)].append({**entry, 'evidence_ids': evidence})
        except Exception as error:
            # Extraction failure is visible; it must not masquerade as verified vocabulary.
            errors.append({'offset': offset, 'error': str(error)})
        if on_progress is not None:
            on_progress(min(offset + len(chunk), len(segments)), len(segments))
    entries = []
    for (kind, word), variants in proposals.items():
        votes = Counter(e['target'] for e in variants)
        target, _ = votes.most_common(1)[0]
        chosen = next(e for e in variants if e['target'] == target)
        entries.append({**chosen, 'kind': kind, 'source': word, 'target': target,
            'occurrences': sum(s['text'].count(word) for s in segments),
            'variants': dict(votes), 'status': 'provisional',
            'conflict': len(votes) > 1})
    result = {'locale': locale, 'setting_notes': settings, 'entries': entries,
            'rejected_entries': rejected, 'errors': errors,
            'elapsed_seconds': round(time.monotonic() - started, 2), 'cache_hit': False}
    if not errors:
        PROFILE_CACHE.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix('.partial')
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        temporary.replace(cache_path)
    return result


def build_locale_profile(client, endpoint, model, segments, locale, source_profile):
    """Map shared source facts into one locale, instead of re-analyzing every source cue."""
    started = time.monotonic()
    key = _profile_cache_key(segments, locale + '-mapped-v3', model)
    cache_path = PROFILE_CACHE / f'{key}.json'
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        cached['cache_hit'] = True
        cached['elapsed_seconds'] = round(time.monotonic() - started, 3)
        return cached
    facts = source_profile.get('entries', [])
    entries, rejected, errors = [], [], []
    cue_map = {s['id']: s['text'] for s in segments}
    for offset in range(0, len(facts), 60):
        chunk = facts[offset:offset + 60]
        locale_name_rule = ('For Vietnamese (vi-VN), convert Chinese names to conventional Hán-Việt readings when clear; '
            'do not use Mandarin pinyin or English glosses. Translate titles into Vietnamese.'
            if locale == 'vi-VN' else
            f'Use conventional name rendering and terms for {locale}; do not return English glosses as target text.')
        prompt = (f'Map these evidence-backed Chinese names and terms for natural {locale} subtitles. '
            'For each item, return the same exact Chinese source spelling, a consistent native-script target spelling, '
            'the provided English meaning unchanged in substance, kind, and evidence cue IDs. Do not invent entries. '
            'For names, use an established localized rendering; for terms, use a natural equivalent. ' +
            locale_name_rule + ' Output only schema JSON.\n' +
            json.dumps(chunk, ensure_ascii=False))
        try:
            response = client.post(endpoint + '/api/chat', json={'model': model, 'stream': False,
                'think': False, 'format': PROFILE_SCHEMA,
                'messages': [{'role': 'user', 'content': prompt}],
                'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2048}})
            response.raise_for_status()
            data = json.loads(response.json()['message']['content'])
            for entry in data['entries']:
                word = entry.get('source', '').strip()
                evidence = [i for i in entry.get('evidence_ids', []) if i in cue_map and word and word in cue_map[i]]
                target = entry.get('target', '').strip()
                wrong_script = (locale != 'ja-JP' and bool(re.search(r'[\u3400-\u9fff]', target))) or (
                    locale in NATIVE_SCRIPT and (not re.search(NATIVE_SCRIPT[locale], target) or re.search(r'[A-Za-z]', target)))
                original = next((f for f in chunk if f['source'] == word), None)
                # A mapped English gloss is not a Vietnamese name or term. It
                # previously entered the project vocabulary as if verified.
                english_gloss = (locale == 'vi-VN' and original is not None and
                    target.casefold() == original.get('meaning', '').strip().casefold())
                if not evidence or not target or wrong_script or english_gloss or original is None:
                    rejected.append(entry)
                    continue
                entries.append({**entry, 'source': word, 'kind': original['kind'],
                    'meaning': original['meaning'], 'evidence_ids': evidence,
                    'occurrences': original.get('occurrences', 0), 'status': 'provisional'})
        except Exception as error:
            errors.append({'offset': offset, 'error': str(error)})
    result = {'locale': locale, 'setting_notes': source_profile.get('setting', []),
        'entries': entries, 'rejected_entries': rejected, 'errors': errors,
        'elapsed_seconds': round(time.monotonic() - started, 2), 'cache_hit': False,
        'source_profile_cache_hit': source_profile.get('cache_hit', False)}
    if not errors:
        PROFILE_CACHE.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix('.partial')
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        temporary.replace(cache_path)
    return result


def vocabulary(profile, batch, source_profile=None):
    source = ' '.join(s['text'] for s in batch)
    locale = (profile or {}).get('locale', '')
    lines = []
    for entry in (profile or {}).get('entries', []):
        if entry['source'] in source:
            lines.append(f"{entry['source']} = {entry['target']}" if locale == 'vi-VN' else
                         f"{entry['source']} = {entry['target']} // English meaning for understanding only; never copy to output: {entry['meaning']}")
    for word, data in SEMANTIC_TERMS.items():
        if word in source:
            target = data.get(locale, '')
            if locale == 'vi-VN':
                if target:
                    lines.append(f'{word} = {target}')
            else:
                lines.append(f"{word}: {data['meaning']}" + (f'; suggested wording: {target}' if target else ''))
    source_rows = (source_profile or {}).get('entries', [])
    for entry in source_rows if locale != 'vi-VN' else []:
        if entry['source'] in source:
            lines.append(f"{entry['source']}: English semantic clue only, translate into the requested language and never copy verbatim: {entry['meaning']} ({entry['kind']}, provisional)")
    return '\n'.join(lines)


def audit(source, translated, locale, source_profile=None):
    issues = []
    source_facts = (source_profile or {}).get('entries', [])
    if [(s['id'], s['start'], s['end']) for s in source] != [(s['id'], s['start'], s['end']) for s in translated]:
        issues.append({'cue': 0, 'severity': 'error', 'rule': 'structure'})
    for original, target in zip(source, translated):
        text = target['text']
        def add(rule, severity='warn', evidence=''):
            issues.append({'cue': original['id'], 'rule': rule, 'severity': severity, 'evidence': evidence})
        for token in SOURCE_REVIEW_TOKENS:
            if token in original['text']:
                add('source_asr_needs_audio', evidence=token)
        if not text.strip():
            add('empty', 'error')
        if locale != 'ja-JP' and re.search(r'[\u3400-\u9fff]', text):
            add('han_residual', 'error')
        if locale in NATIVE_SCRIPT and re.search(r'[A-Za-z]{2,}', text):
            add('latin_needs_review', 'error')
        # A Chinese source cue translated into a Latin-script language can still
        # contain untranslated English or pinyin without triggering a script check.
        # Source-profile glosses are a strong signal; a generic Title Case span
        # alone is not, because valid Hán-Việt names also use that spelling.
        if locale == 'vi-VN' and re.search(r'[\u3400-\u9fff]', original['text']):
            for fact in source_facts:
                if fact.get('source') not in original['text']:
                    continue
                gloss = fact.get('meaning', '').strip()
                if gloss and len(gloss) >= 4 and re.search(r'(?<![A-Za-z])' + re.escape(gloss) + r'(?![A-Za-z])', text, re.I):
                    add('english_gloss_leak', 'error', gloss)
            for span in re.findall(r'(?<![\w])[A-Z][a-z]+(?:[ \u00a0]+[A-Z][a-z]+)+(?![\w])', text):
                if not re.search(r'[À-ỹ]', span):
                    add('unaccented_name_needs_review', evidence=span)
        for number in re.findall(r'\d+', original['text']):
            if number not in text:
                add('number_needs_review', evidence=number)  # spelled-out numbers may be valid
        if re.search(r'<\/?think>|```|(?:translation|note)\s*:', text, re.I):
            add('model_note', 'error')
        for word, data in SEMANTIC_TERMS.items():
            if locale == 'th-TH' and word in original['text']:
                for forbidden in data.get('forbid_th', []):
                    if forbidden in text:
                        add('meaning_inversion', 'error', forbidden)
            if locale == 'vi-VN' and word in original['text']:
                for forbidden in data.get('forbid_vi', []):
                    if forbidden.casefold() in text.casefold():
                        add('meaning_inversion', 'error', forbidden)
        for flag in target.get('translation_flags', []):
            add('model:' + flag, 'info' if flag == 'fragment' else 'warn')
        if original['end'] > original['start'] and len(text) / (original['end'] - original['start']) > 25:
            add('reading_speed')
        # A heuristic for additions like an unsupported motive or adjective. It only flags;
        # short source fragments can legitimately expand, so never treat this as proof.
        src_len = len(re.sub(r'\s+', '', original['text']))
        dst_len = len(re.sub(r'\s+', '', text))
        if src_len >= 4 and dst_len >= 24 and dst_len > src_len * 4:
            add('length_expansion_needs_review', evidence=f'{src_len}->{dst_len} chars')
    return issues
