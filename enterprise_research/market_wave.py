"""Detect material price swings and read or save source-reviewed Gemini research."""

from datetime import date, timedelta
import json
from pathlib import Path
from urllib.parse import urlsplit

from market_data import read_json, write_json

SEED = Path(__file__).with_name('market_wave_cases.json')
MOVE = .07
REVERSAL = .04
REVISIT = .03
RECENT_DAYS = 120


def price_points(chart, code, cutoff):
    return [(row['date'], close) for row in chart if row['date'] <= cutoff
            and (close := row['values'].get(code)) is not None and close > 0]


def detect(points):
    """Retain the opening pivot and first signal while the extreme evolves."""
    if not points:
        return []
    low = high = extreme = points[0]
    pivot = signal = None
    direction = 0
    waves = []

    def record(closed):
        waves.append(dict(id=f'{pivot[0]}:{signal[0]}', start=pivot[0], end=extreme[0],
                          signal_on=signal[0], change=round(100 * (extreme[1] / pivot[1] - 1), 2),
                          start_price=pivot[1], end_price=extreme[1], closed=closed))

    for point in points[1:]:
        if direction and direction * (point[1] / extreme[1] - 1) <= -REVERSAL:
            record(True)
            low = high = extreme
            direction = 0
        if not direction:
            if point[1] >= low[1] * (1 + MOVE):
                direction, pivot = 1, low
                signal = extreme = point
            elif point[1] <= high[1] * (1 - MOVE):
                direction, pivot = -1, high
                signal = extreme = point
            else:
                if point[1] <= low[1]:
                    low = point
                if point[1] >= high[1]:
                    high = point
        elif direction * (point[1] - extreme[1]) > 0:
            extreme = point
    if direction:
        record(False)
    return waves


def path_for(directory, code):
    return directory / 'market_observation' / 'attribution' / code


def cases(directory, code):
    seed = json.loads(SEED.read_text(encoding='utf-8'))
    by_span = {(item['start'], item['end']): item for item in seed.get(code, [])}
    for file in path_for(directory, code).glob('*.json'):
        item = read_json(file)
        if item:
            by_span[item['start'], item['end']] = item
    return sorted(by_span.values(), key=lambda item: (item['end'], item['start']))


def response(directory, code, chart, cutoff):
    if not code:
        return dict(reviewed=[], pending=[])
    reviewed = []
    research = cases(directory, code)
    for item in research:
        notes = [note for note in item['notes'] if note['date'] <= cutoff]
        if notes and item['start'] <= cutoff:
            reviewed.append(dict(item, end=min(item['end'], cutoff), notes=notes,
                                 id=f"review:{item['start']}:{item['end']}"))
    low = (date.fromisoformat(cutoff) - timedelta(days=RECENT_DAYS)).isoformat()
    points = price_points(chart, code, cutoff)
    close_by_day = dict(points)

    def already_covered(wave, item):
        if item['end'] > cutoff or item['start'] > wave['start']:
            return False
        if wave['end'] <= item['end']:
            return True
        end_price = close_by_day.get(item['end'])
        return (item['start'] == wave['start'] and end_price is not None
                and abs(wave['end_price'] / end_price - 1) < REVISIT)

    pending = [wave for wave in detect(points) if wave['end'] >= low
               and not any(already_covered(wave, item) for item in research)]
    return dict(reviewed=reviewed, pending=pending, code=code, threshold_pct=100 * MOVE)


def publish(directory, code, item, cutoff):
    """Accept the reviewed case through the local app, retaining distinct dated versions."""
    if not code or item.get('model') != 'Gemini' or item.get('reviewed_by') != 'Codex':
        raise ValueError('请提交 Gemini 原稿经 Codex 核源后的归因。')
    start, end = (date.fromisoformat(item.get(field, '')).isoformat() for field in ('start', 'end'))
    if not start < end <= cutoff:
        raise ValueError('波段日期必须落在已知行情范围。')
    notes = item.get('notes')
    if not isinstance(notes, list) or not notes:
        raise ValueError('请填写至少一条有日期和来源的结论。')
    for note in notes:
        stamp = date.fromisoformat(note.get('date', '')).isoformat()
        if not start <= stamp <= end or not note.get('title', '').strip() or not note.get('text', '').strip():
            raise ValueError('结论需注明本波段内的证据公开日和正文。')
        sources = note.get('sources')
        if not isinstance(sources, list) or not sources:
            raise ValueError('每条结论需含可查看的来源。')
        for source in sources:
            link = urlsplit(source.get('url', ''))
            if link.scheme not in ('http', 'https') or not link.netloc or not source.get('label', '').strip():
                raise ValueError('来源需注明标题及网页链接。')
    saved = dict(start=start, end=end, model='Gemini', reviewed_by='Codex',
                 notes=sorted(notes, key=lambda note: note['date']))
    write_json(path_for(directory, code) / f'{start}_{end}.json', saved)
    return saved
