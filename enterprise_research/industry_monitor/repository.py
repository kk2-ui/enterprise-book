"""Monitoring persistence in the existing research database.

Sources and authored research remain owned by their existing modules. This
repository stores identities, queryable observations and frozen run references.
"""
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


SCHEMA = '''
CREATE TABLE IF NOT EXISTS monitor_subjects(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,company_id TEXT,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS monitor_securities(
 code TEXT PRIMARY KEY,subject_id TEXT NOT NULL,currency TEXT NOT NULL,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS monitor_universes(
 id TEXT NOT NULL,version TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS monitor_profiles(
 id TEXT NOT NULL,version TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS monitor_facts(
 id TEXT PRIMARY KEY,subject_id TEXT NOT NULL,metric TEXT NOT NULL,
 period_start TEXT NOT NULL,period_end TEXT NOT NULL,scope TEXT NOT NULL,
 currency TEXT NOT NULL,unit TEXT NOT NULL,value REAL,available_on TEXT,
 vintage TEXT NOT NULL,source_key TEXT NOT NULL,revision INTEGER NOT NULL,
 data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS monitor_facts_lookup ON monitor_facts(subject_id,metric,period_end,available_on);
CREATE INDEX IF NOT EXISTS monitor_facts_source ON monitor_facts(source_key,revision);
CREATE TABLE IF NOT EXISTS monitor_observations(
 id TEXT PRIMARY KEY,subject_id TEXT NOT NULL,kind TEXT NOT NULL,as_of TEXT NOT NULL,
 source_key TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS monitor_obs_lookup ON monitor_observations(subject_id,kind,as_of);
CREATE TABLE IF NOT EXISTS monitor_adjustments(
 id TEXT PRIMARY KEY,subject_id TEXT NOT NULL,revision INTEGER NOT NULL,
 status TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS monitor_jobs(
 id TEXT PRIMARY KEY,scope TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS monitor_runs(
 id TEXT PRIMARY KEY,scope TEXT NOT NULL,as_of TEXT NOT NULL,status TEXT NOT NULL,
 data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS monitor_current(
 scope TEXT PRIMARY KEY,run_id TEXT NOT NULL);
'''


class Repository:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / 'research.db'
        with self.connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def subject(self, sid):
        with self.connect() as c:
            row = c.execute('SELECT * FROM monitor_subjects WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise ValueError('研究主体不存在')
        return dict(json.loads(row['data']), id=row['id'], kind=row['kind'],
                    name=row['name'], company_id=row['company_id'])

    def register(self, sid, kind, name, company_id=None, **data):
        with self.connect() as c:
            c.execute('INSERT INTO monitor_subjects VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,data=excluded.data,company_id=COALESCE(excluded.company_id,monitor_subjects.company_id)',
                      (sid, kind, name, company_id, encode(data)))

    def security(self, code, sid, currency, **data):
        with self.connect() as c:
            c.execute('INSERT INTO monitor_securities VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET data=excluded.data',
                      (code, sid, currency, encode(data)))

    def freeze(self, table, identity, version, data):
        if table not in ('monitor_universes', 'monitor_profiles'):
            raise ValueError('不支持的版本对象')
        raw = encode(data)
        with self.connect() as c:
            row = c.execute(f'SELECT data FROM {table} WHERE id=? AND version=?', (identity, version)).fetchone()
            if row and row['data'] != raw:
                raise ValueError('已保存版本不可覆盖，请使用新版本')
            if not row:
                c.execute(f'INSERT INTO {table} VALUES(?,?,?,?)', (identity, version, raw, now()))

    def add_fact(self, fact, connection=None):
        f = dict(fact)
        for key in ('subject_id', 'metric', 'period_end', 'scope', 'currency', 'unit', 'source_key'):
            if not f.get(key):
                raise ValueError('财务事实缺少 ' + key)
        if f.get('value') is not None and (isinstance(f['value'], bool) or not math.isfinite(float(f['value']))):
            raise ValueError('财务事实金额无效')
        f.setdefault('period_start', '')
        f.setdefault('available_on', None)
        f.setdefault('vintage', 'unknown')
        f.setdefault('value', None)
        f.pop('id', None)
        f.pop('revision', None)
        raw = encode(f)
        with (nullcontext(connection) if connection is not None else self.connect()) as c:
            row = c.execute('''SELECT id,revision,data FROM monitor_facts WHERE subject_id=? AND metric=?
                AND period_start=? AND period_end=? AND scope=? AND currency=? AND source_key=?
                ORDER BY revision DESC LIMIT 1''', tuple(f[k] for k in ('subject_id','metric','period_start','period_end','scope','currency','source_key'))).fetchone()
            if row and row['data'] == raw:
                return row['id']
            revision = row['revision'] + 1 if row else 1
            fid = uuid.uuid4().hex[:16]
            c.execute('INSERT INTO monitor_facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (fid, f['subject_id'], f['metric'], f['period_start'], f['period_end'], f['scope'],
                       f['currency'], f['unit'], f['value'], f['available_on'], f['vintage'],
                       f['source_key'], revision, raw, now()))
        return fid

    def facts(self, sid):
        with self.connect() as c:
            rows = c.execute('SELECT id,revision,data FROM monitor_facts WHERE subject_id=? ORDER BY period_end,revision', (sid,)).fetchall()
        return [dict(json.loads(r['data']), id=r['id'], revision=r['revision']) for r in rows]

    def observe(self, sid, kind, as_of, source_key, data):
        raw = encode(data)
        with self.connect() as c:
            row = c.execute('SELECT id,data FROM monitor_observations WHERE subject_id=? AND kind=? AND as_of=? AND source_key=? ORDER BY rowid DESC LIMIT 1', (sid,kind,as_of,source_key)).fetchone()
            if row and row['data'] == raw:
                return row['id']
            oid = uuid.uuid4().hex[:16]
            c.execute('INSERT INTO monitor_observations VALUES(?,?,?,?,?,?,?)', (oid,sid,kind,as_of,source_key,raw,now()))
        return oid

    def observations(self, sid, kind=None):
        query = 'SELECT * FROM monitor_observations WHERE subject_id=?'
        args = [sid]
        if kind:
            query += ' AND kind=?'; args.append(kind)
        with self.connect() as c:
            rows = c.execute(query+' ORDER BY as_of,rowid', args).fetchall()
        return [dict(json.loads(r['data']), id=r['id'], observation_kind=r['kind'], as_of=r['as_of'], source_key=r['source_key']) for r in rows]

    def adjustment(self, sid, data):
        for key in ('key', 'basis', 'reason', 'evidence', 'rival', 'switch_condition', 'status', 'as_of'):
            if not data.get(key):
                raise ValueError('经济调整缺少 ' + key)
        if data['status'] not in ('proposed', 'adopted', 'rejected', 'unknown'):
            raise ValueError('经济调整状态无效')
        if data['status'] == 'adopted' and not data.get('research_reference'):
            raise ValueError('采用调整须引用研究版本')
        with self.connect() as c:
            previous = [r for r in c.execute('SELECT * FROM monitor_adjustments WHERE subject_id=? ORDER BY rowid DESC', (sid,)) if json.loads(r['data'])['key'] == data['key']]
            if previous and previous[0]['data'] == encode(data):
                return previous[0]['id']
            aid = uuid.uuid4().hex[:16]
            revision = previous[0]['revision']+1 if previous else 1
            c.execute('INSERT INTO monitor_adjustments VALUES(?,?,?,?,?,?)', (aid,sid,revision,data['status'],encode(data),now()))
        return aid

    def adjustments(self, sid):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM monitor_adjustments WHERE subject_id=? ORDER BY rowid', (sid,)).fetchall()
        return [dict(json.loads(r['data']), id=r['id'], revision=r['revision']) for r in rows]

    def new_job(self, scope, **data):
        jid = uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute('INSERT INTO monitor_jobs VALUES(?,?,?,?,?,?)', (jid,scope,'queued',encode(data),now(),now()))
        return jid

    def update_job(self, jid, status, **updates):
        with self.connect() as c:
            row = c.execute('SELECT data FROM monitor_jobs WHERE id=?', (jid,)).fetchone()
            if not row: raise ValueError('任务不存在')
            data = json.loads(row['data']); data.update(updates)
            c.execute('UPDATE monitor_jobs SET status=?,data=?,updated_at=? WHERE id=?', (status,encode(data),now(),jid))

    def job(self, jid):
        with self.connect() as c:
            row = c.execute('SELECT * FROM monitor_jobs WHERE id=?', (jid,)).fetchone()
        if not row: raise ValueError('任务不存在')
        return dict(json.loads(row['data']), **{k:row[k] for k in row.keys() if k != 'data'})

    def publish(self, scope, as_of, data, status='ready'):
        if status not in ('ready', 'partial'):
            raise ValueError('失败任务不能替换已发布快照')
        rid = uuid.uuid4().hex[:16]
        with self.connect() as c:
            c.execute('INSERT INTO monitor_runs VALUES(?,?,?,?,?,?)', (rid,scope,as_of,status,encode(data),now()))
            c.execute('INSERT INTO monitor_current VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET run_id=excluded.run_id', (scope,rid))
        return rid

    def current(self, scope, run_id=None):
        with self.connect() as c:
            if run_id:
                row = c.execute('SELECT * FROM monitor_runs WHERE scope=? AND id=?', (scope,run_id)).fetchone()
            else:
                row = c.execute('SELECT r.* FROM monitor_runs r JOIN monitor_current p ON r.id=p.run_id WHERE p.scope=?', (scope,)).fetchone()
        if not row: return None
        return dict(json.loads(row['data']), run_id=row['id'], as_of=row['as_of'], status=row['status'], captured_at=row['created_at'])
