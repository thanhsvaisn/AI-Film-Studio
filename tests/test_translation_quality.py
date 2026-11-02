import unittest
import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from backend.translation_quality import (audit, build_profile, build_source_profile,
    build_locale_profile, adjacent_source_candidates, vocabulary,
    evaluate_golden_set, audit_profile_consistency)
from backend.translation import _review_batch
from backend.translation import _style
from backend.locales import LOCALES


class QualityTests(unittest.TestCase):
    def cue(self, text, **changes):
        return {'id': 1, 'start': 0, 'end': 2, 'text': text, **changes}

    def test_inversion_is_error(self):
        issues = audit([self.cue('这个爹太愚孝')], [self.cue('พ่อไม่กตัญญู')], 'th-TH')
        self.assertTrue(any(i['rule'] == 'meaning_inversion' and i['severity'] == 'error' for i in issues))

    def test_japanese_kanji_not_chinese_leak(self):
        issues = audit([self.cue('村长')], [self.cue('村長')], 'ja-JP')
        self.assertFalse(any(i['rule'] == 'han_residual' for i in issues))

    def test_timing_changes_rejected(self):
        self.assertTrue(any(i['rule'] == 'structure' for i in audit([self.cue('娘')], [self.cue('mother', end=3)], 'en-US')))

    def test_spelled_out_number_requires_review_not_error(self):
        issues = audit([self.cue('3个人')], [self.cue('three people')], 'en-US')
        self.assertTrue(any(i['rule'] == 'number_needs_review' and i['severity'] == 'warn' for i in issues))

    def test_suspected_asr_flagged_without_changing_source(self):
        original = self.cue('有人偷装')
        issues = audit([original], [self.cue('Someone is installing something secretly')], 'en-US')
        self.assertEqual(original['text'], '有人偷装')
        self.assertTrue(any(i['rule'] == 'source_asr_needs_audio' for i in issues))

    def test_chinese_number_is_not_misread_as_ascii_digit(self):
        source = self.cue('杖责五十')
        issues = audit([source], [self.cue('Phạt năm trượng')], 'vi-VN')
        self.assertFalse(any(i['rule'] == 'number_needs_review' for i in issues))
        self.assertEqual(source['text'], '杖责五十')

    def test_unsupported_expansion_is_review_only(self):
        issues = audit([self.cue('底料配方给我')], [self.cue('Đưa công thức gia vị để tôi kiếm lời nhiều nhất')], 'vi-VN')
        finding = next(i for i in issues if i['rule'] == 'length_expansion_needs_review')
        self.assertEqual(finding['severity'], 'warn')

    def test_near_duplicate_source_cues_are_only_candidates(self):
        rows = [self.cue('逼三'), {**self.cue('逼三'), 'id': 2, 'start': 2, 'end': 4},
                {**self.cue('完全不同的内容'), 'id': 3, 'start': 4, 'end': 6}]
        candidates = adjacent_source_candidates(rows)
        self.assertEqual([(c['left_id'], c['right_id']) for c in candidates], [(1, 2)])

    def test_hallucinated_profile_entry_is_rejected(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                import json
                return {'message': {'content': json.dumps({'setting': 'unknown', 'entries': [
                    {'source': '不存在', 'target': 'Invented', 'kind': 'name', 'meaning': 'name', 'evidence_ids': [1]}]})}}
        class Client:
            def post(self, *args, **kwargs): return Response()
        profile = build_profile(Client(), 'http://unused', 'test', [self.cue('娘')], 'en-US')
        self.assertEqual(profile['entries'], [])
        self.assertEqual(len(profile['rejected_entries']), 1)

    def test_latin_profile_target_rejected_for_thai(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                import json
                return {'message': {'content': json.dumps({'setting': 'unknown', 'entries': [
                    {'source': '苗苗', 'target': 'Miao Miao', 'kind': 'name', 'meaning': 'name', 'evidence_ids': [1]}]})}}
        class Client:
            def post(self, *args, **kwargs): return Response()
        profile = build_profile(Client(), 'http://unused', 'test', [self.cue('苗苗')], 'th-TH')
        self.assertEqual(profile['entries'], [])
        self.assertEqual(len(profile['rejected_entries']), 1)

    def test_profile_cache_reuses_only_identical_source(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                import json
                return {'message': {'content': json.dumps({'setting': 'drama', 'entries': [
                    {'source': '苗苗', 'target': 'เหมียวเหมียว', 'kind': 'name',
                     'meaning': 'character name', 'evidence_ids': [1]}]})}}
        class Client:
            def __init__(self): self.calls = 0
            def post(self, *args, **kwargs): self.calls += 1; return Response()
        cache_path = Path(__file__).resolve().parents[1] / 'data' / 'test_profile_cache' / uuid4().hex
        cache_path.mkdir(parents=True)
        try:
            with patch('backend.translation_quality.PROFILE_CACHE', cache_path):
                client = Client()
                original = [self.cue('苗苗')]
                first = build_profile(client, 'http://unused', 'test', original, 'th-TH')
                second = build_profile(client, 'http://unused', 'test', original, 'th-TH')
                changed = build_profile(client, 'http://unused', 'test', [self.cue('苗苗来了')], 'th-TH')
        finally:
            shutil.rmtree(cache_path, ignore_errors=True)
        self.assertEqual(client.calls, 2)
        self.assertFalse(first['cache_hit'])
        self.assertTrue(second['cache_hit'])
        self.assertFalse(changed['cache_hit'])

    def test_targeted_reviewer_preserves_candidate_ids(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                import json
                return {'message': {'content': json.dumps({'cues': [
                    {'id': 7, 'action': 'keep', 'text': 'เก็บไว้', 'reason': 'Meaning is preserved'}]})}}
        class Client:
            def post(self, url, json):
                self.payload = json
                return Response()
        client = Client()
        rows = [{'id': 7, 'source': '来源', 'translation': 'เก็บไว้'}]
        result = _review_batch(client, rows, [], 'th-TH')
        self.assertEqual(result[0]['id'], 7)
        self.assertIn('Do not rewrite for stylistic preference', client.payload['messages'][0]['content'])

    def test_shared_source_profile_contains_only_evidence_backed_terms(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                import json
                return {'message': {'content': json.dumps({'setting': 'period drama', 'entries': [
                    {'source': '苗苗', 'kind': 'name', 'meaning': 'character name', 'evidence_ids': [1]},
                    {'source': '虚构词', 'kind': 'term', 'meaning': 'invented', 'evidence_ids': [1]}]})}}
        class Client:
            def post(self, *args, **kwargs): return Response()
        cache_path = Path(__file__).resolve().parents[1] / 'data' / 'test_source_profile_cache' / uuid4().hex
        cache_path.mkdir(parents=True)
        try:
            with patch('backend.translation_quality.SOURCE_PROFILE_CACHE', cache_path):
                profile = build_source_profile(Client(), 'http://unused', 'test', [self.cue('苗苗')])
        finally:
            shutil.rmtree(cache_path, ignore_errors=True)
        self.assertEqual([entry['source'] for entry in profile['entries']], ['苗苗'])
        lines = vocabulary({'locale': 'vi-VN', 'entries': []}, [self.cue('苗苗')], profile)
        self.assertEqual(lines, '')  # English extraction notes must not enter Vietnamese prompts.
        thai_lines = vocabulary({'locale': 'th-TH', 'entries': []}, [self.cue('苗苗')], profile)
        self.assertIn('character name', thai_lines)

    def test_vietnamese_audit_catches_gloss_leaks_and_false_death_anniversary(self):
        sources = [self.cue('萧承'), {**self.cue('今日就是你的死期'), 'id': 2},
                   {**self.cue('请天龙'), 'id': 3}]
        translated = [{**sources[0], 'text': 'Xiao Cheng'},
                      {**sources[1], 'text': 'Hôm nay là ngày giỗ của ngươi'},
                      {**sources[2], 'text': 'Mời Heavenly Dragon'}]
        source_profile = {'entries': [
            {'source': '萧承', 'meaning': 'Xiao Cheng'},
            {'source': '天龙', 'meaning': 'Heavenly Dragon'}]}
        errors = {(issue['cue'], issue['rule']) for issue in
                  audit(sources, translated, 'vi-VN', source_profile) if issue['severity'] == 'error'}
        self.assertEqual(errors, {(1, 'english_gloss_leak'), (2, 'meaning_inversion'),
                                  (3, 'english_gloss_leak')})

    def test_locale_mapping_uses_shared_evidence_and_target_script(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                import json
                return {'message': {'content': json.dumps({'setting': 'drama', 'entries': [
                    {'source': '苗苗', 'target': 'เหมียวเหมียว', 'kind': 'name',
                     'meaning': 'character name', 'evidence_ids': [1]}]})}}
        class Client:
            def post(self, *args, **kwargs): return Response()
        cache_path = Path(__file__).resolve().parents[1] / 'data' / 'test_locale_profile_cache' / uuid4().hex
        cache_path.mkdir(parents=True)
        try:
            with patch('backend.translation_quality.PROFILE_CACHE', cache_path):
                profile = build_locale_profile(Client(), 'http://unused', 'test', [self.cue('苗苗')], 'th-TH', {
                    'setting': ['drama'], 'cache_hit': True, 'entries': [{'source': '苗苗', 'kind': 'name',
                        'meaning': 'character name', 'evidence_ids': [1], 'occurrences': 1}]})
        finally:
            shutil.rmtree(cache_path, ignore_errors=True)
        self.assertEqual(profile['entries'][0]['target'], 'เหมียวเหมียว')
        self.assertEqual(profile['entries'][0]['meaning'], 'character name')

    def test_every_supported_locale_gets_a_conservative_style_card(self):
        self.assertEqual(len(LOCALES), 17)
        for locale in LOCALES:
            rules = _style(locale)
            self.assertIn('Preserve every source fact', rules, locale)
            self.assertTrue(rules.strip(), locale)

    def test_golden_set_requires_human_review_and_scores_by_cue_id(self):
        golden = {'locale': 'vi-VN', 'review_status': 'reviewed', 'items': [
            {'id': 'g1', 'cue_id': 9, 'source_language': 'zh', 'source_text': '你好',
             'approved_translation': 'Xin chào'}]}
        report = evaluate_golden_set(golden, [{'id': 9, 'text': 'Xin chào'}])
        self.assertEqual(report['exact_matches'], 1)
        golden['review_status'] = 'draft'
        with self.assertRaises(ValueError):
            evaluate_golden_set(golden, [{'id': 9, 'text': 'Xin chào'}])

    def test_profile_consistency_flags_missing_name_as_review_only(self):
        findings = audit_profile_consistency([self.cue('苗苗来了')], [self.cue('Cô ấy đã đến')],
            {'entries': [{'source': '苗苗', 'target': 'Miêu Miêu', 'kind': 'name'}]})
        self.assertEqual(findings[0]['rule'], 'profile_term_missing')
        self.assertEqual(findings[0]['severity'], 'warn')


if __name__ == '__main__':
    unittest.main()
