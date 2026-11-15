"""Source ownership, document editions, acquisition attempts and frozen data packages.

This module does not import the application, company prose or valuation models.
The existing sources table/IDs remain the canonical file references.
"""
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def uid():
    return uuid.uuid4().hex[:16]


def encode(data):
    return json.dumps(data, ensure_ascii=False)


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(value or '')):
        raise ValueError('标识只使用字母、数字、下划线或短横线')
    return value


NATURES = {'company_disclosure', 'public_reporting', 'industry_reference', 'external_analysis', 'research_output'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_documents(company_id TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(company_id,id,revision));
CREATE TABLE IF NOT EXISTS source_acquisitions(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_packages(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
'''


class SourceRepository:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / 'research.db'
        (self.directory / 'uploads').mkdir(exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def source(self, sid):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
        if not row:
            raise ValueError('资料不存在')
        return dict(id=row['id'], company_id=row['company_id'], **json.loads(row['data']))

    def list_sources(self, cid):
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM sources WHERE company_id=? ORDER BY rowid', (cid,)).fetchall()
        return [dict(id=r['id'], company_id=cid, created_at=r['created_at'], **json.loads(r['data'])) for r in rows]

    def add_source(self, cid, data, content=None, filename=None):
        if not data.get('title', '').strip():
            raise ValueError('请填写资料标题')
        url = data.get('url', '').strip()
        if url and urlparse(url).scheme not in ('http', 'https'):
            raise ValueError('链接须为 http 或 https')
        if not content and not url and not data.get('notes', '').strip():
            raise ValueError('请上传文件、填写链接或资料正文')
        sid, path = uid(), ''
        if content is not None:
            ext = Path(filename or 'document').suffix.lower()
            if ext not in ('.pdf', '.md', '.txt', '.json', '.csv', '.xlsx', '.docx', '.png', '.jpg', '.jpeg', '.webp', '.html'):
                raise ValueError('不支持的资料文件类型')
            path = str(self.directory / 'uploads' / (sid + ext))
            Path(path).write_bytes(content)
        clean = {k: str(data.get(k, '')) for k in ['title', 'kind', 'chapter', 'url', 'fact_period', 'published_on', 'notes']}
        clean.update(path=path, origin=data.get('origin', '用户录入'), original_filename=filename or '')
        with self.connect() as conn:
            conn.execute('INSERT INTO sources VALUES(?,?,?,?)', (sid, cid, encode(clean), now()))
        return sid

    def update_source(self, sid, data):
        source = self.source(sid)
        if not str(data.get('title', '')).strip():
            raise ValueError('资料标题不能为空')
        if data.get('url') and urlparse(data['url']).scheme not in ('http', 'https'):
            raise ValueError('链接须为http或https')
        fields = ['title', 'kind', 'chapter', 'fact_period', 'published_on', 'notes', 'url']
        source.setdefault('metadata_history', []).append(dict({k: source.get(k, '') for k in fields}, replaced_on=now()))
        for key in fields:
            source[key] = str(data.get(key, source.get(key, '')))
        source.pop('id'); source.pop('company_id')
        with self.connect() as conn:
            conn.execute('UPDATE sources SET data=? WHERE id=?', (encode(source), sid))

    def document(self, cid, did, revision=None):
        with self.connect() as conn:
            query = 'SELECT * FROM source_documents WHERE company_id=? AND id=?'
            args = [cid, did]
            if revision is not None:
                query += ' AND revision=?'; args.append(int(revision))
            row = conn.execute(query + ' ORDER BY revision DESC LIMIT 1', args).fetchone()
        if not row:
            raise ValueError('资料版本不存在')
        return dict(id=did, company_id=cid, revision=row['revision'], created_at=row['created_at'], **json.loads(row['data']))

    def documents(self, cid):
        with self.connect() as conn:
            ids = [r[0] for r in conn.execute('SELECT DISTINCT id FROM source_documents WHERE company_id=? ORDER BY id', (cid,))]
        return [self.document(cid, did) for did in ids]

    def save_document(self, cid, data):
        data = json.loads(encode(data))
        did = identifier(data.pop('id', None))
        for key in ['company_id', 'revision', 'created_at']:
            data.pop(key, None)
        if not data.get('title') or data.get('nature') not in NATURES:
            raise ValueError('资料须有标题及明确性质')
        reps = data.get('representations', {})
        if not reps.get('original') or not reps.get('text'):
            raise ValueError('资料须关联原件及可读全文；未完成采集留在取得记录中')
        for sid in reps.values():
            source = self.source(sid)
            if source['company_id'] != cid:
                raise ValueError('资料关联企业不符')
            if not source.get('path') or not Path(source['path']).is_file():
                raise ValueError('资料文件尚未取得')
        data.setdefault('rows', [])
        for meaning in data.get('periods', {}).values():
            for key in ['start','end']:
                if meaning.get(key):date.fromisoformat(meaning[key])
        if data['rows']:
            from .disclosures import extract_row
            pages=Path(self.source(reps['text'])['path']).read_text().split('\f')
            for row in data['rows']:
                actual=extract_row(pages,row)
                if actual['values']!=row['values'] or actual['source_excerpt']!=row['source_excerpt']:
                    raise ValueError('披露行与实际原件不符：'+row['id'])
        data.setdefault('extraction_status', 'not_extracted')
        with self.connect() as conn:
            old = conn.execute('SELECT * FROM source_documents WHERE company_id=? AND id=? ORDER BY revision DESC LIMIT 1', (cid, did)).fetchone()
            if old and json.loads(old['data']) == data:
                return self.document(cid, did, old['revision'])
            revision = old['revision'] + 1 if old else 1
            conn.execute('INSERT INTO source_documents VALUES(?,?,?,?,?)', (cid, did, revision, encode(data), now()))
        return self.document(cid, did, revision)

    def record_acquisition(self, cid, data):
        aid = uid()
        with self.connect() as conn:
            conn.execute('INSERT INTO source_acquisitions VALUES(?,?,?,?)', (aid, cid, encode(data), now()))
        return aid

    def acquisitions(self, cid):
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM source_acquisitions WHERE company_id=? ORDER BY rowid DESC', (cid,)).fetchall()
        return [dict(json.loads(r['data']), document_id=json.loads(r['data']).get('id'), id=r['id'], created_at=r['created_at']) for r in rows]

    def save_package(self, cid, data):
        pid = identifier(data['id'])
        with self.connect() as conn:
            if conn.execute('SELECT 1 FROM source_packages WHERE id=?', (pid,)).fetchone():
                raise ValueError('资料包版本已存在，请另建版本')
            conn.execute('INSERT INTO source_packages VALUES(?,?,?,?)', (pid, cid, encode(data), now()))
        return data

    def package(self, cid, pid):
        with self.connect() as conn:
            row = conn.execute('SELECT data FROM source_packages WHERE company_id=? AND id=?', (cid, pid)).fetchone()
        if not row:
            raise ValueError('资料包不存在')
        return json.loads(row[0])

    def packages(self, cid):
        with self.connect() as conn:
            return [json.loads(r[0]) for r in conn.execute('SELECT data FROM source_packages WHERE company_id=? ORDER BY rowid DESC', (cid,))]

    def overview(self, cid):
        docs = self.documents(cid)
        return dict(documents=[{**{k:v for k,v in d.items() if k != 'rows'}, 'row_count':len(d['rows'])} for d in docs],
                    packages=self.packages(cid), acquisitions=self.acquisitions(cid))
