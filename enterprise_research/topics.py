"""Company research topics: free-form content, shared evidence, append-only editions."""
import json
import re
import uuid
import frameworks
from pathlib import Path
from datetime import datetime

SCHEMA = '''CREATE TABLE IF NOT EXISTS research_topics(
    company_id TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
    data TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(company_id,id,revision));'''
SOURCE_MARKER = re.compile(r'\[\[source:([\w-]+)(?:@(\d+))?\|([^\]\n]+)\]\]')
FIGURE_MARKER = re.compile(r'^[ \t]*\[\[figure:([\w-]+)\|([^\]\n]+)\]\][ \t]*$', re.MULTILINE)


def unpack(row, summary=False):
    result = json.loads(row['data'])
    if summary:
        result.pop('body', None)
    return dict(result, id=row['id'], revision=row['revision'], updated_at=row['created_at'])


def listing(conn, cid):
    rows = conn.execute('''SELECT t.* FROM research_topics t JOIN
        (SELECT id,MAX(revision) AS revision FROM research_topics WHERE company_id=? GROUP BY id) latest
        ON t.id=latest.id AND t.revision=latest.revision
        WHERE t.company_id=? ORDER BY t.rowid DESC''', (cid, cid))
    return [unpack(r, summary=True) for r in rows]


def read(store, cid, tid, revision=None):
    with store.connect() as conn:
        history = conn.execute('SELECT * FROM research_topics WHERE company_id=? AND id=? ORDER BY revision DESC', (cid, tid)).fetchall()
        if not history:
            raise ValueError('专题不存在')
        row = next((r for r in history if revision is None or r['revision'] == revision), None)
        if row is None:
            raise ValueError('该专题版本不存在')
        return dict(unpack(row), latest_revision=history[0]['revision'],
                    history=[dict(revision=r['revision'], updated_at=r['created_at'],
                                  title=json.loads(r['data'])['title'],
                                  change_note=json.loads(r['data']).get('change_note', '')) for r in history])


def export(conn, cid):
    return [unpack(r) for r in conn.execute('SELECT * FROM research_topics WHERE company_id=? ORDER BY id,revision', (cid,))]


def save(store, cid, data, tid=None):
    title = str(data.get('title', '')).strip()
    body = str(data.get('body', '')).strip()
    if not title or not body:
        raise ValueError('请填写专题标题和正文')
    arrays = {}
    for key in ('chapter_indices', 'source_ids', 'record_ids', 'forecast_ids', 'factor_ids'):
        values = data.get(key, [])
        if not isinstance(values, list):
            raise ValueError('关联内容须为列表')
        if key == 'chapter_indices':
            if any(type(v) is not int or not 0 <= v < 8 for v in values):
                raise ValueError('请选择有效的总论章节')
        elif any(not isinstance(v, str) for v in values):
            raise ValueError('关联编号须为文字')
        arrays[key] = list(dict.fromkeys(values))
    figure_ids = [m[0] for m in FIGURE_MARKER.findall(body)]
    arrays['source_ids'] = list(dict.fromkeys(arrays['source_ids'] + [m[0] for m in SOURCE_MARKER.findall(body)] + figure_ids))
    tid = tid or uuid.uuid4().hex[:16]
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        company = conn.execute('SELECT original FROM companies WHERE id=?', (cid,)).fetchone()
        if not company:
            raise ValueError('企业不存在')
        for key, table in [('source_ids', 'sources'), ('record_ids', 'records')]:
            allowed = {r[0] for r in conn.execute(f'SELECT id FROM {table} WHERE company_id=?', (cid,))}
            if not set(arrays[key]) <= allowed:
                raise ValueError('关联资料或记录不属于该企业')
        for sid in set(figure_ids):
            source = json.loads(conn.execute('SELECT data FROM sources WHERE id=?', (sid,)).fetchone()[0])
            if Path(source.get('path', '')).suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('正文配图请选择已上传的 PNG、JPG 或 WebP 图片')
        forecasts = {f['id'] for f in json.loads(company[0]).get('forecasts', [])}
        forecasts.update(json.loads(r[0])['forecast_id'] for r in conn.execute("SELECT data FROM records WHERE company_id=? AND kind='prediction'", (cid,)))
        if not set(arrays['forecast_ids']) <= forecasts:
            raise ValueError('关联预测不属于该企业')
        current = conn.execute('SELECT MAX(revision) FROM research_topics WHERE company_id=? AND id=?', (cid, tid)).fetchone()[0] or 0
        if data.get('base_revision', 0) != current:
            raise ValueError('专题已有更新，请保留当前编辑文字，关闭后重新打开最新版本再合并')
        framework = frameworks.current(conn, cid)
        factor_map = {f['id']: f['name'] for f in framework['factors']} if framework else {}
        if current and 'factor_ids' not in data:
            old = conn.execute('SELECT data FROM research_topics WHERE company_id=? AND id=? AND revision=?', (cid, tid, current)).fetchone()
            arrays['factor_ids'] = json.loads(old[0]).get('factor_ids', [])
        if not set(arrays['factor_ids']) <= factor_map.keys():
            raise ValueError('请选择该企业当前框架内的因素')
        clean = dict(title=title, body=body, category=str(data.get('category', '')).strip() or '未分类',
                     framework_revision=framework['revision'] if framework else None,
                     factor_labels=[factor_map[fid] for fid in arrays['factor_ids']],
                     summary=str(data.get('summary', '')).strip(), change_note=str(data.get('change_note', '')).strip(), **arrays)
        conn.execute('INSERT INTO research_topics VALUES(?,?,?,?,?)',
                     (cid, tid, current + 1, json.dumps(clean, ensure_ascii=False), datetime.now().astimezone().isoformat(timespec='seconds')))
    return dict(id=tid, revision=current + 1)
