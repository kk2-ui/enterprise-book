"""Three company-specific economic factors, with dated revisions."""
import json
import uuid
from datetime import datetime

SCHEMA = '''CREATE TABLE IF NOT EXISTS company_frameworks(
    company_id TEXT NOT NULL, revision INTEGER NOT NULL,
    data TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(company_id,revision));'''


def unpack(row):
    return dict(json.loads(row['data']), revision=row['revision'], updated_at=row['created_at'])


def current(conn, cid):
    row = conn.execute('SELECT * FROM company_frameworks WHERE company_id=? ORDER BY revision DESC LIMIT 1', (cid,)).fetchone()
    return unpack(row) if row else None


def versions(conn, cid):
    return [unpack(r) for r in conn.execute('SELECT * FROM company_frameworks WHERE company_id=? ORDER BY revision DESC', (cid,))]


def read(store, cid, revision=None):
    with store.connect() as conn:
        rows = versions(conn, cid)
    chosen = next((v for v in rows if revision is None or v['revision'] == revision), None)
    if chosen is None:
        raise ValueError('该企业框架或版本不存在')
    return dict(chosen, history=[{k: v[k] for k in ('revision', 'updated_at', 'title', 'change_note')} for v in rows])


def save(store, cid, data):
    title = str(data.get('title', '')).strip()
    rationale = str(data.get('rationale', '')).strip()
    if not title or not rationale:
        raise ValueError('请填写行业框架名称，以及为何选择这三个因素')
    factors = data.get('factors', [])
    if not isinstance(factors, list) or len(factors) != 3:
        raise ValueError('请确定三个重点因素')
    clean_factors = []
    for factor in factors:
        if not isinstance(factor, dict):
            raise ValueError('因素内容格式不正确')
        clean = {key: str(factor.get(key, '')).strip() for key in ('name', 'question', 'assessment', 'watch')}
        if not clean['name'] or not clean['question']:
            raise ValueError('每个因素须有名称和要回答的经营问题')
        clean['id'] = str(factor.get('id') or uuid.uuid4().hex[:16])
        clean_factors.append(clean)
    if len({f['id'] for f in clean_factors}) != 3 or len({f['name'] for f in clean_factors}) != 3:
        raise ValueError('三个因素的名称和编号不能重复')
    clean = dict(title=title, rationale=rationale, synthesis=str(data.get('synthesis', '')).strip(),
                 factors=clean_factors, change_note=str(data.get('change_note', '')).strip())
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT 1 FROM companies WHERE id=?', (cid,)).fetchone():
            raise ValueError('企业不存在')
        previous = current(conn, cid)
        revision = previous['revision'] if previous else 0
        if data.get('base_revision', 0) != revision:
            raise ValueError('行业框架已有更新，请保留编辑内容，重新打开最新版本再合并')
        conn.execute('INSERT INTO company_frameworks VALUES(?,?,?,?)',
                     (cid, revision+1, json.dumps(clean, ensure_ascii=False), datetime.now().astimezone().isoformat(timespec='seconds')))
    return dict(revision=revision+1)
