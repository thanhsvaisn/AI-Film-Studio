import re

TIME = r'(\d{2,}):(\d{2}):(\d{2}),(\d{3})'


def seconds(parts):
    h, m, s, ms = map(int, parts)
    if m > 59 or s > 59:
        raise ValueError('Phút và giây phải nhỏ hơn 60.')
    return h * 3600 + m * 60 + s + ms / 1000


def timeline_manifest(segments):
    """Stable millisecond timeline used to ensure translation never shifts cues."""
    return [{'id': int(s['id']), 'start_ms': round(float(s['start']) * 1000),
             'end_ms': round(float(s['end']) * 1000)} for s in segments]


def validate_timeline(segments, manifest):
    actual = timeline_manifest(segments)
    if actual != manifest:
        expected_by_id = {row['id']: row for row in manifest}
        actual_by_id = {row['id']: row for row in actual}
        changed = next((cue_id for cue_id in actual_by_id
                        if actual_by_id[cue_id] != expected_by_id.get(cue_id)), None)
        raise ValueError(f'Timestamp phụ đề bị thay đổi tại dòng {changed or "?"}; đã dừng để không xuất sai khớp hình.')


def timeline_manifest_from_srt(text):
    """Read cue IDs and timestamps from ordinary or over-spaced SRT text."""
    lines = [line.strip() for line in text.lstrip('\ufeff').replace('\r\n', '\n').split('\n') if line.strip()]
    rows = []
    index = 0
    while index + 1 < len(lines):
        if lines[index].isdigit() and '-->' in lines[index + 1]:
            match = re.fullmatch(TIME + r'\s*-->\s*' + TIME, lines[index + 1])
            if not match:
                raise ValueError(f'Timestamp SRT không hợp lệ tại dòng {lines[index]}.')
            groups = match.groups()
            start = round(seconds(groups[:4]) * 1000)
            end = round(seconds(groups[4:]) * 1000)
            rows.append({'id': int(lines[index]), 'start_ms': start, 'end_ms': end})
            index += 2
        else:
            index += 1
    if not rows:
        raise ValueError('Không đọc được timeline từ SRT nguồn.')
    return rows


def parse_srt(text):
    blocks = re.split(r'\n\s*\n', text.lstrip('\ufeff').replace('\r\n', '\n').strip())
    result = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].isdigit():
            raise ValueError('SRT cần số thứ tự, thời gian và nội dung trong từng khối.')
        match = re.fullmatch(TIME + r'\s*-->\s*' + TIME, lines[1])
        if not match:
            raise ValueError(f'Thời gian không hợp lệ tại dòng {lines[0]}.')
        result.append(dict(id=int(lines[0]), start=seconds(match.groups()[:4]),
                           end=seconds(match.groups()[4:]), text='\n'.join(lines[2:])))
    validate(result)
    return result


def parse_srt_overspaced(text):
    """Recover legacy imports that inserted blank lines between every SRT field."""
    lines = [line.strip() for line in text.lstrip('\ufeff').replace('\r\n', '\n').split('\n') if line.strip()]
    result = []
    index = 0
    while index < len(lines):
        if index + 2 >= len(lines) or not lines[index].isdigit():
            raise ValueError('SRT nguồn không đọc được ID và timestamp.')
        match = re.fullmatch(TIME + r'\s*-->\s*' + TIME, lines[index + 1])
        if not match:
            raise ValueError(f'Timestamp SRT nguồn không hợp lệ tại dòng {lines[index]}.')
        cue_id = int(lines[index])
        index += 2
        body = []
        while index < len(lines):
            if (index + 1 < len(lines) and lines[index].isdigit() and
                    re.fullmatch(TIME + r'\s*-->\s*' + TIME, lines[index + 1])):
                break
            body.append(lines[index])
            index += 1
        result.append({'id': cue_id, 'start': seconds(match.groups()[:4]),
                       'end': seconds(match.groups()[4:]), 'text': '\n'.join(body)})
    validate(result)
    return result


def validate(segments, duration=None):
    import math
    ids, previous, flags = set(), -1, []
    if not segments:
        raise ValueError('Phụ đề trống.')
    for i, s in enumerate(segments):
        if s['id'] in ids or s['id'] <= 0:
            raise ValueError('ID phụ đề bị trùng hoặc không hợp lệ.')
        ids.add(s['id'])
        if not all(math.isfinite(s[k]) for k in ('start', 'end')):
            raise ValueError('Thời gian phải là số hữu hạn.')
        if s['start'] < 0 or s['end'] <= s['start'] or s['start'] < previous:
            raise ValueError(f'Thứ tự/thời gian sai tại dòng {s["id"]}.')
        if not s['text'].strip() or len(s['text']) > 5000:
            raise ValueError('Nội dung phụ đề trống hoặc quá dài.')
        if duration is not None and s['end'] > duration + .1:
            raise ValueError(f'Dòng {s["id"]} vượt thời lượng video.')
        if i and s['start'] < segments[i - 1]['end']:
            flags.append(f'Dòng {s["id"]}: phụ đề chồng thời gian.')
        if len(s['text']) / (s['end'] - s['start']) > 25:
            flags.append(f'Dòng {s["id"]}: cần kiểm tra tốc độ đọc.')
        previous = s['start']
    return flags


def timestamp(value):
    ms = round(value * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def serialize(segments):
    return '\n\n'.join(f'{s["id"]}\n{timestamp(s["start"])} --> {timestamp(s["end"])}\n{s["text"]}' for s in segments) + '\n'
