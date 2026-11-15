"""Revisioned research, reproducible trial calculations, and editorial handoffs."""
import json
import uuid
from datetime import datetime, date
from copy import deepcopy
from topics import SOURCE_MARKER
from owner_cash_scenarios import calculate
from owner_cash_bridge import calculate as calculate_bridge, METHOD as BRIDGE_METHOD
from layered_owner_cash import calculate as calculate_layered, METHOD as LAYERED_METHOD
from owner_cash_paths import calculate as calculate_paths, METHOD as PATHS_METHOD
from three_step_valuation import METHODS as THREE_STEP_METHODS, calculate as calculate_three_step, bind_growth

SCHEMA = '''
CREATE TABLE IF NOT EXISTS research_projects(
 company_id TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,
 data TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(company_id,id,revision));
CREATE TABLE IF NOT EXISTS research_calculations(
 company_id TEXT NOT NULL,id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS research_handoffs(
 company_id TEXT NOT NULL,id TEXT PRIMARY KEY,project_id TEXT NOT NULL,
 project_revision INTEGER NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
'''
ACTIVITIES = ['问题界定', '行业与企业背景', '获取证据', '经营分析', '反方检验',
              '正常收益与现金', '估值研究', '研究审阅', '跟踪复盘', '写作反馈']


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def unpack(row):
    return dict(json.loads(row['data']), **{k: row[k] for k in row.keys() if k != 'data'})


def required(data, key, label):
    value = data.get(key, '')
    if not isinstance(value, str) or not value.strip():
        raise ValueError('请填写' + label)
    return value.strip()


def day(value, label):
    try:
        date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError(label + '须为年月日')
    return value


def associations(conn, cid, data, text=''):
    result = {}
    for key, table in [('source_ids', 'sources'), ('topic_ids', 'research_topics'), ('record_ids', 'records')]:
        ids = data.get(key, [])
        if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
            raise ValueError('关联内容须为编号列表')
        if key == 'source_ids':
            ids = ids + [m[0] for m in SOURCE_MARKER.findall(text)]
        allowed = {r[0] for r in conn.execute(f'SELECT id FROM {table} WHERE company_id=?', (cid,))}
        if not set(ids) <= allowed:
            raise ValueError('关联资料、专题或记录不属于该企业')
        result[key] = list(dict.fromkeys(ids))
    chapters = data.get('chapter_indices', [])
    if not isinstance(chapters, list) or any(type(x) is not int or not 0 <= x < 8 for x in chapters):
        raise ValueError('请选择有效的总论章节')
    result['chapter_indices'] = list(dict.fromkeys(chapters))
    return result


def project_row(conn, cid, pid, revision=None):
    if revision is None:
        row = conn.execute('SELECT * FROM research_projects WHERE company_id=? AND id=? ORDER BY revision DESC LIMIT 1', (cid, pid)).fetchone()
    else:
        row = conn.execute('SELECT * FROM research_projects WHERE company_id=? AND id=? AND revision=?', (cid, pid, revision)).fetchone()
    if row is None:
        raise ValueError('研究或所选版本不存在')
    return unpack(row)


def require_subject(conn, cid):
    """Peers can have research without first acquiring a complete enterprise book."""
    if conn.execute('SELECT id FROM companies WHERE id=?',(cid,)).fetchone():return
    exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='monitor_subjects'").fetchone()
    if exists and conn.execute("SELECT id FROM monitor_subjects WHERE id=? AND kind='issuer'",(cid,)).fetchone():return
    raise ValueError('企业或研究主体不存在')


def listing(store, cid):
    with store.connect() as conn:
        require_subject(conn,cid)
    with store.connect() as conn:
        rows = conn.execute('''SELECT p.* FROM research_projects p WHERE company_id=? AND revision=
            (SELECT MAX(revision) FROM research_projects q WHERE q.company_id=p.company_id AND q.id=p.id)
            ORDER BY p.rowid DESC''', (cid,)).fetchall()
        return [dict((k, v) for k, v in unpack(r).items() if k != 'entries') for r in rows]


def read(store, cid, pid, revision=None):
    with store.connect() as conn:
        p = project_row(conn, cid, pid, revision)
        p['history'] = [dict(revision=r['revision'], created_at=r['created_at'],
                             change_note=json.loads(r['data'])['change_note']) for r in conn.execute(
            'SELECT * FROM research_projects WHERE company_id=? AND id=? ORDER BY revision DESC', (cid, pid))]
        p['latest_revision'] = p['history'][0]['revision']
        p['calculations'] = []
        for row in conn.execute('SELECT * FROM research_calculations WHERE company_id=? AND project_id=? ORDER BY rowid DESC', (cid, pid)):
            r = unpack(row)
            p['calculations'].append(dict({k: v for k, v in r.items() if k not in ('inputs', 'result')},
                                          method=r['inputs'].get('method', 'conditional_owner_cash_scenarios')))
        p['handoffs'] = [unpack(r) for r in conn.execute(
            'SELECT * FROM research_handoffs WHERE company_id=? AND project_id=? ORDER BY rowid DESC', (cid, pid))]
        p['publications'] = []
        for row in conn.execute('SELECT version,data,created_at FROM dossiers WHERE company_id=? ORDER BY rowid DESC', (cid,)):
            dossier = json.loads(row['data'])
            basis = dossier.get('research_basis', {})
            if basis.get('project_id') == pid:
                p['publications'].append(dict(basis, book_version=row['version'], published_at=row['created_at']))
        return p


def save(store, cid, data, pid=None):
    clean = {k: str(data.get(k, '')).strip() for k in ('current_view', 'rival', 'next_step', 'change_note')}
    clean.update(title=required(data, 'title', '研究标题'), question=required(data, 'question', '要研究的问题'),
                 as_of=day(data.get('as_of'), '研究时点'))
    entries = data.get('entries', [])
    if not isinstance(entries, list):
        raise ValueError('研究过程须为记录列表')
    clean['entries'] = []
    for e in entries:
        if e.get('activity') not in ACTIVITIES:
            raise ValueError('请选择研究活动')
        clean['entries'].append(dict(id=e.get('id') or uuid.uuid4().hex[:16], activity=e['activity'],
                                    title=required(e, 'title', '过程记录标题'), body=required(e, 'body', '完整研究内容')))
    if len({e['id'] for e in clean['entries']}) != len(entries):
        raise ValueError('过程记录编号重复')
    pid = pid or uuid.uuid4().hex[:16]
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        require_subject(conn,cid)
        current = conn.execute('SELECT MAX(revision) FROM research_projects WHERE company_id=? AND id=?', (cid, pid)).fetchone()[0] or 0
        if data.get('base_revision', 0) != current:
            raise ValueError('研究已有更新。请保留编辑内容，重新打开最新版本后合并。')
        text = '\n'.join([clean['question'], clean['current_view'], clean['rival'], clean['next_step']] + [e['body'] for e in clean['entries']])
        clean.update(associations(conn, cid, data, text))
        conn.execute('INSERT INTO research_projects VALUES(?,?,?,?,?)',
                     (cid, pid, current + 1, json.dumps(clean, ensure_ascii=False), now()))
    return dict(id=pid, revision=current + 1)


def calculation(store, cid, pid, rid):
    with store.connect() as conn:
        row = conn.execute('SELECT * FROM research_calculations WHERE company_id=? AND project_id=? AND id=?', (cid, pid, rid)).fetchone()
        if not row:
            raise ValueError('计算记录不存在')
        return unpack(row)


def compute(store, cid, pid, data, persist=False):
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        p = project_row(conn, cid, pid)
        if data.get('project_revision') != p['revision']:
            raise ValueError('研究已有新版本，请先核对最新研究再计算。')
        inputs = deepcopy(data.get('inputs'))
        if not isinstance(inputs, dict) or inputs.get('company_id') != cid:
            raise ValueError('计算输入的企业与当前研究不一致')
        method = inputs.get('method', 'conditional_owner_cash_scenarios')
        if method in THREE_STEP_METHODS and inputs.get('valuation_date'):
            day(inputs['valuation_date'], '底稿估值时点')
            if inputs.get('as_of') and inputs['as_of'] != inputs['valuation_date']:
                raise ValueError('底稿估值时点与计算时点不一致；请明确重估，不自动滚动日期')
            inputs['as_of'] = inputs['valuation_date']
        day(inputs.get('as_of'), '计算时点')
        if method not in THREE_STEP_METHODS or inputs.get('price_date'):
            day(inputs.get('price_date'), '参考价格日期')
        if inputs.get('price_date', '') > inputs['as_of']:
            raise ValueError('参考价格日期不能晚于计算时点')
        if method == 'growth':
            source_id = inputs.get('epv_calculation_id')
            if source_id:
                row = conn.execute('SELECT * FROM research_calculations WHERE company_id=? AND project_id=? AND id=?',
                                   (cid, pid, source_id)).fetchone()
                if not row or row['project_revision'] != p['revision']:
                    raise ValueError('请选择本研究当前版本的EPV；旧依据请核对后另存，不自动继承')
                bind_growth(inputs, unpack(row))
            elif inputs.get('growth_route', {}).get('action') == 'evaluate':
                raise ValueError('评价增长须选择已保存的EPV计算')
            if inputs.get('growth_route', {}).get('action') == 'evaluate':
                quotes = [inputs.get('price', {})]
                quotes += inputs.get('price_grid', [])
                quotes += [s['price'] for s in inputs.get('scenarios', []) if 'price' in s]
                for price in quotes:
                    for quote in price.get('quotes', [price]):
                        if quote.get('value') is None and not quote.get('date'):
                            continue  # Missing quote remains unknown; no implicit market fetch.
                        day(quote.get('date'), '增长报价日期')
                        if quote['date'] > inputs['as_of']:
                            raise ValueError('增长报价日期不能晚于计算时点')
        refs = associations(conn, cid, {'source_ids': data.get('source_ids', [])}, json.dumps(inputs, ensure_ascii=False))
        try:
            if method not in ('conditional_owner_cash_scenarios', LAYERED_METHOD, PATHS_METHOD, BRIDGE_METHOD, *THREE_STEP_METHODS):
                raise ValueError('未支持的计算方法')
            calculator = calculate_three_step if method in THREE_STEP_METHODS else {LAYERED_METHOD: calculate_layered, PATHS_METHOD: calculate_paths, BRIDGE_METHOD: calculate_bridge}.get(method, calculate)
            result = calculator(inputs)
        except (KeyError, TypeError, StopIteration) as error:
            raise ValueError('计算输入不完整，请检查情景、基准名称、参数及压力条件。') from error
        clean = dict(title=required(data, 'title', '本次计算名称'),
                     change_note=required(data, 'change_note', '假设依据或本次变化理由'),
                     source_ids=refs['source_ids'], inputs=inputs, result=result)
        if not persist:
            return dict(clean, project_revision=p['revision'], saved=False)
        rid = uuid.uuid4().hex[:16]
        conn.execute('INSERT INTO research_calculations VALUES(?,?,?,?,?,?)',
                     (cid, rid, pid, p['revision'], json.dumps(clean, ensure_ascii=False), now()))
    return calculation(store, cid, pid, rid)


def calculation_ids(data):
    """A new handoff can adopt several methods; old single-result books remain valid."""
    ids = data.get('calculation_ids', [])
    if not isinstance(ids, list) or any(not isinstance(rid, str) or not rid for rid in ids):
        raise ValueError('采用的计算须为有效编号列表')
    primary = data.get('calculation_id', '')
    return list(dict.fromkeys(([primary] if primary else []) + ids))


def validate_calculations(conn, cid, pid, revision, ids):
    for rid in ids:
        row = conn.execute('SELECT project_revision FROM research_calculations WHERE company_id=? AND project_id=? AND id=?',
                           (cid, pid, rid)).fetchone()
        if not row or row[0] != revision:
            raise ValueError('所选计算不属于当前研究版本，请核对假设后重算，或不附计算。')


def handoff(store, cid, pid, data):
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        p = project_row(conn, cid, pid)
        if data.get('project_revision') != p['revision']:
            raise ValueError('研究已有更新，请打开最新研究后交接。')
        ids = calculation_ids(data)
        validate_calculations(conn, cid, pid, p['revision'], ids)
        rid = data.get('calculation_id', '')
        dossier = conn.execute('SELECT version FROM dossiers WHERE company_id=? ORDER BY rowid DESC LIMIT 1', (cid,)).fetchone()
        topic_versions = []
        for tid in p['topic_ids']:
            row = conn.execute('SELECT id,revision,data FROM research_topics WHERE company_id=? AND id=? ORDER BY revision DESC LIMIT 1', (cid, tid)).fetchone()
            topic_versions.append(dict(id=tid, revision=row['revision'], title=json.loads(row['data'])['title']))
        clean = dict(note=required(data, 'note', '交接内容和写作范围'), calculation_id=rid, calculation_ids=ids,
                     book_version_at_handoff=dossier[0] if dossier else '',
                     chapter_indices=p['chapter_indices'], topic_versions=topic_versions)
        hid = uuid.uuid4().hex[:16]
        conn.execute('INSERT INTO research_handoffs VALUES(?,?,?,?,?,?)',
                     (cid, hid, pid, p['revision'], json.dumps(clean, ensure_ascii=False), now()))
    return dict(id=hid, **clean)


def validate_publication(store, cid, basis):
    """A book must cite the actual research, calculation and handoff it adopted."""
    with store.connect() as conn:
        pid = basis.get('project_id')
        revision = basis.get('research_revision')
        if type(revision) is not int or revision < 1:
            raise ValueError('成稿须指定实际采用的研究版本')
        project_row(conn, cid, pid, revision)
        ids = calculation_ids(basis)
        validate_calculations(conn, cid, pid, revision, ids)
        handoff = conn.execute('SELECT project_revision,data FROM research_handoffs WHERE company_id=? AND project_id=? AND id=?', (cid,pid,basis.get('handoff_id'))).fetchone()
        if not handoff or handoff[0] != revision or set(calculation_ids(json.loads(handoff[1]))) != set(ids):
            raise ValueError('成稿与指定写作交接不一致')
        for topic in basis.get('topic_versions', []):
            if not conn.execute('SELECT 1 FROM research_topics WHERE company_id=? AND id=? AND revision=?', (cid,topic['id'],topic['revision'])).fetchone():
                raise ValueError('成稿关联的专题版本不存在')


def export(conn, cid):
    return {key: [unpack(r) for r in conn.execute(f'SELECT * FROM {table} WHERE company_id=? ORDER BY rowid', (cid,))]
            for key, table in [('research_project_versions', 'research_projects'),
                               ('research_calculations', 'research_calculations'), ('research_handoffs', 'research_handoffs')]}
