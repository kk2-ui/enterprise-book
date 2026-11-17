"""Install the checked-in enterprise book editions into a development workspace."""
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1]
sys.path.insert(0, str(APP))

from app import Store, encode, now, uid
from seed import CHAPTERS


def remap(value, original_id, company_id):
    if isinstance(value, dict):
        return {key: remap(item, original_id, company_id) for key, item in value.items()}
    if isinstance(value, list):
        return [remap(item, original_id, company_id) for item in value]
    if isinstance(value, str) and original_id and original_id != company_id:
        return company_id if value == original_id else value.replace(
            f'/company/{original_id}/', f'/company/{company_id}/')
    return value


def install_case(store, path):
    case = json.loads(path.read_text())
    profile = case['company']
    code = profile['code']
    edition_id = case.get('edition_id')
    stamp = case.get('created_at') or now()

    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        rows = conn.execute(
            "SELECT id,data FROM companies WHERE json_extract(data,'$.code')=?",
            (code,),
        ).fetchall()
        if len(rows) > 1:
            raise ValueError(f'{code} 存在重复企业档案')
        fresh = not rows
        company_id = uid() if fresh else rows[0]['id']
        if fresh:
            company = {
                'id': company_id, 'created_at': stamp, 'stage': '基础档案',
                'summary': '当前仅有企业基础档案，长期经营序列待补。',
                'color': 'teal', 'chapters': ['本档案暂无正式整本。'] * len(CHAPTERS),
                **profile,
            }
            conn.execute('INSERT INTO companies VALUES(?,?,?)',
                         (company_id, encode(company), encode({'forecasts': []})))
        else:
            company = json.loads(rows[0]['data'])

        if not edition_id:
            return code, '新增基础档案' if fresh else '已有基础档案'
        existing = conn.execute(
            'SELECT company_id FROM book_editions WHERE id=?', (edition_id,),
        ).fetchone()
        if existing:
            if existing[0] != company_id:
                raise ValueError(f'{edition_id} 已属于其他企业')
            return code, '已有当前整本'

        for sid, fields in case['sources'].items():
            old = conn.execute('SELECT company_id FROM sources WHERE id=?', (sid,)).fetchone()
            if old:
                if old[0] != company_id:
                    raise ValueError(f'资料 {sid} 已属于其他企业')
                continue
            meta = {'title': fields['title'], 'kind': '', 'chapter': '', 'url': '',
                    'fact_period': '', 'published_on': '', 'path': '', 'notes': '',
                    'origin': '公开企业书发行包', 'original_filename': ''}
            meta.update({key: fields[key] for key in meta if key in fields})
            if asset := fields.get('asset'):
                if not re.fullmatch(r'figures/[\w-]+\.(?:png|jpg|jpeg|webp)', asset):
                    raise ValueError(f'图片路径无效：{asset}')
                file = path.parent / asset
                if not file.is_file():
                    raise FileNotFoundError(file)
                meta.update(path=str(file), original_filename=file.name)
            conn.execute('INSERT INTO sources VALUES(?,?,?,?)',
                         (sid, company_id, encode(meta), stamp))

        edition = case['edition']
        if snapshot := edition.get('snapshot'):
            edition = remap(edition, snapshot['id'], company_id)
            snapshot = edition['snapshot']
            source_list = conn.execute('SELECT id,data FROM sources WHERE company_id=?', (company_id,)).fetchall()
            snapshot['sources'] = [
                {'id': row['id'], 'company_id': company_id, **json.loads(row['data'])}
                for row in source_list if row['id'] in case['sources']
            ]
        conn.execute('INSERT INTO book_editions VALUES(?,?,?,?)',
                     (edition_id, company_id, encode(edition), stamp))

        previous = conn.execute(
            'SELECT data FROM book_editions WHERE company_id=? AND id=?',
            (company_id, company.get('default_book_edition_id', '')),
        ).fetchone()
        replaces_seed = bool(previous and code == '601857.SH' and
                             json.loads(previous['data'])['title'] == '中国石油企业书 · 修订版 v1')
        if fresh or replaces_seed:
            company['default_book_edition_id'] = edition_id
            conn.execute('UPDATE companies SET data=? WHERE id=?', (encode(company), company_id))
    return code, edition_id


def install(directory, case=None):
    store = Store(directory)
    paths = [HERE / case / 'case.json'] if case else sorted(HERE.glob('*/case.json'))
    return [install_case(store, path) for path in paths]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=APP / 'data')
    parser.add_argument('--case', choices=sorted(path.parent.name for path in HERE.glob('*/case.json')))
    args = parser.parse_args()
    for company_code, edition in install(args.data_dir, args.case):
        print(f'{company_code}  {edition}')
