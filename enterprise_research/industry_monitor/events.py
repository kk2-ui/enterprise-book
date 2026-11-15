"""Announcement evidence alongside price factors; titles never establish causation."""
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

from .disclosures import download
from .ingestion import subject_id
from .sources import register_report


TOPICS = {
    'control': ('收購守則', '要約', '私有化', '股權出現變動'),
    'legal': ('清盤', '訴訟', '仲裁', '調查', '違約', '紀律行動', '未經授權', '還款催繳'),
    'operations': ('盈利警告', '盈利預告', '須予披露的交易', '重大交易', '關連交易', '內幕消息'),
    'trading': ('停牌', '復牌', '恢復買賣', '撤銷上市'),
}


def topics(record):
    if record.get('kind') in ('annual_report', 'interim_report', 'monthly_return', 'annual_results', 'interim_results'):
        return []
    text = record['title'] + ' ' + record.get('category', '')
    return [key for key, words in TOPICS.items() if any(word in text for word in words)]


def selected(index, cutoff):
    start = (date.fromisoformat(cutoff) - timedelta(days=366)).isoformat()
    return [r for r in index.get('records', []) if start <= r['published_on'] <= cutoff and topics(r)]


def acquire(root, members, cutoff, progress=None):
    root = Path(root)
    failures = []
    records = []
    for member in members:
        path = root / 'hkex_index' / (member['code'] + '.json')
        if not path.exists():
            continue
        records.extend(selected(json.loads(path.read_text()), cutoff))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(download, record, root / 'company_events'): record for record in records}
        for future in as_completed(futures):
            record = futures[future]
            try:
                future.result()
            except Exception as error:
                failure = dict(code=record['code'], document_id=record['id'], kind='company_event',
                               status='failed', error=str(error))
                failures.append(failure)
                if progress:
                    progress(failure)
    return failures


def ingest(repo, root, members, cutoff):
    root = Path(root)
    count = 0
    for member in members:
        path = root / 'hkex_index' / (member['code'] + '.json')
        if not path.exists():
            continue
        for record in selected(json.loads(path.read_text()), cutoff):
            name = record['code'] + '-' + record['published_on'] + '-' + record['id'] + '.json'
            local = root / 'company_events' / name
            source_id = None
            if local.exists():
                document = register_report(repo.directory, json.loads(local.read_text()))
                source_id = document['representations']['original']
            repo.observe(subject_id(member['code']), 'company_event', record['published_on'], 'event-' + record['id'],
                         dict(document_id=record['id'], title=record['title'], published_at=record['published_at'],
                              source_url=record['url'], source_id=source_id, topics=topics(record),
                              available_on=record['published_on'],
                              evidence_status='original_acquired' if source_id else 'title_only',
                              boundary='公告主题是研究提示；未据标题确认事件完成，也不据其认定涨跌因果。'))
            count += 1
    return count


def visible(rows, cutoff):
    start = (date.fromisoformat(cutoff) - timedelta(days=366)).isoformat()
    return sorted([r for r in rows if start <= r['as_of'] <= cutoff and r.get('available_on', r['as_of']) <= cutoff],
                  key=lambda r: (r['published_at'], r['document_id']), reverse=True)


def newly_disclosed(previous, rows, previous_cutoff, cutoff):
    """Do not trigger on an old event merely ageing out of the display window."""
    known = {r['document_id'] for r in previous}
    # Same-day announcements and previously missed older originals also matter.
    return [r for r in visible(rows, cutoff) if r['document_id'] not in known]
