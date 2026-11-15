#!/usr/bin/env python3
"""Acquire a declared public source pack and index PDF pages for company books.

The manifest keeps issuer, fact period, publication date and research topic apart.
Existing local copies are reused; this does not generate company judgments.
"""
import argparse, concurrent.futures, json, subprocess, urllib.request
import shutil
import tempfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .repository import identifier


class VisibleText(HTMLParser):
    def __init__(self): super().__init__(); self.hidden = 0; self.out = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'br'): self.out.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden: self.out.append(data)


class ArticleText(HTMLParser):
    """Declared HTML content class: exclude navigation, recommendations and AI widgets."""
    VOID={'br','img','meta','link','input','hr','source','wbr','area','base','embed','param','track','col'}
    def __init__(self, content_class):
        super().__init__();self.content_class=content_class;self.stack=[];self.out=[];self.found=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        selected=self.content_class in attrs.get('class','').split()
        active=selected or any(x[1] for x in self.stack)
        if selected:self.found=True
        if active and tag in {'p','div','br','li','h1','h2','h3'}:self.out.append('\n')
        if tag not in self.VOID:self.stack.append((tag,active))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                self.stack=self.stack[:i];break
    def handle_data(self,data):
        if any(x[1] for x in self.stack) and not any(x[0] in {'script','style','noscript'} for x in self.stack):self.out.append(data)


def acquire(entry, directory, retrieved_on=None):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / entry['file']
    if not target.exists():
        if entry.get('capture_method') == 'browser_notes':
            raise ValueError(entry['id'] + ': browser notes must be saved after reading the page')
        req = urllib.request.Request(entry['url'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=90) as r: body = r.read()
        if target.suffix == '.pdf' and not body.startswith(b'%PDF'): raise ValueError(entry['id'] + ': not a PDF')
        target.write_bytes(body)
    # Browser reading notes are authored excerpts, not HTML or a full source copy.
    text = target if target.suffix.lower() in ('.txt', '.md') else target.with_suffix('.txt')
    if not text.exists():
        if target.suffix == '.pdf':
            subprocess.run(['pdftotext', '-layout', str(target), str(text)], check=True, capture_output=True)
        else:
            parser = ArticleText(entry['html_content_class']) if entry.get('html_content_class') else VisibleText()
            parser.feed(target.read_text(errors='replace'))
            if entry.get('html_content_class') and not parser.found:
                raise ValueError(entry['id']+': 指定网页正文区域不存在，不能用整页导航代替')
            text.write_text('\n'.join(x.strip() for x in ''.join(parser.out).splitlines() if x.strip()))
    pages = text.read_text().split('\f')
    hits = {term: [i + 1 for i, page in enumerate(pages) if term.casefold() in page.casefold()] for term in entry.get('find', [])}
    return dict(entry, local_path=str(target), text_path=str(text), page_hits=hits,
                acquired_on=entry.get('retrieved_on') or retrieved_on or date.today().isoformat())


def collect_document(repo, cid, spec, acquired_on=None):
    """Import a selected local source or fetch one public URL; record failure honestly.

    This does not discover URLs, infer accounting facts, or classify authored notes
    as an original. The caller declares the document's identity and nature.
    """
    did = identifier(spec.get('id'))
    attempt = {k:spec.get(k, '') for k in ['id', 'title', 'url', 'issuer', 'fact_period', 'published_on']}
    attempt['acquired_on'] = acquired_on or date.today().isoformat()
    try:
        if spec.get('capture_method') == 'browser_notes':
            raise ValueError('阅读笔记不能作为独立分析包的原件或全文')
        if spec.get('nature') not in {'company_disclosure', 'public_reporting', 'industry_reference', 'external_analysis', 'research_output'}:
            raise ValueError('先声明资料性质')
        with tempfile.TemporaryDirectory(prefix='source-acquire-') as tmp:
            directory = Path(tmp)
            source_id = spec.get('original_source_id')
            original = repo.source(source_id) if source_id else None
            path = (original or {}).get('path') or spec.get('local_path')
            suffix = Path(path or urlparse(spec.get('url', '')).path).suffix.lower()
            if suffix not in {'.pdf', '.txt', '.md', '.html'}:
                suffix = '.html'
            target = directory / ('original' + suffix)
            if path:
                shutil.copyfile(path, target)
            text_id = spec.get('text_source_id')
            text_source = repo.source(text_id) if text_id else None
            text_path = (text_source or {}).get('path') or spec.get('text_path')
            if text_path and suffix not in {'.txt', '.md'}:
                shutil.copyfile(text_path, target.with_suffix('.txt'))
            entry = dict(spec, id=did, file=target.name)
            result = acquire(entry, directory, attempt['acquired_on'])
            fulltext = Path(result['text_path'])
            if not fulltext.read_text().strip():
                raise ValueError('原件已取得但全文为空，需要OCR或其他可读原件')
            meta = {k:spec.get(k, '') for k in ['title', 'url', 'fact_period', 'published_on']}
            meta.update(kind=spec.get('kind') or '原始资料', origin='资料模块采集', notes='')
            source_id = source_id or repo.add_source(cid, meta, target.read_bytes(), did + suffix)
            if fulltext == target:
                text_id = source_id
            else:
                text_id = text_id or repo.add_source(cid, dict(meta, title=meta['title']+' · 全文'), fulltext.read_bytes(), did+'.txt')
            document = {k:spec.get(k, '') for k in ['title', 'nature', 'issuer', 'fact_period', 'published_on', 'url', 'description', 'group', 'html_content_class']}
            document.update(id=did, representations=dict(original=source_id, text=text_id),
                            acquired_on=attempt['acquired_on'], text_status=spec.get('text_status', 'machine_extracted'),
                            rows=spec.get('rows', []), periods=spec.get('periods', {}),
                            extraction_status='declared_rows' if spec.get('rows') else 'not_extracted')
            saved = repo.save_document(cid, document)
        attempt.update(status='available', document_revision=saved['revision'], method='local_import' if path else 'public_url')
        attempt['attempt_id'] = repo.record_acquisition(cid, attempt)
        return dict(document=saved, acquisition=attempt)
    except Exception as error:
        attempt.update(status='failed', error=str(error))
        attempt['attempt_id'] = repo.record_acquisition(cid, attempt)
        return dict(document=None, acquisition=attempt)


